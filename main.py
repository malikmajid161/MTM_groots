"""Run the planner through a single command for both initial packs and updates."""

import argparse
import hashlib
import json
import re
import sys
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict
from email.utils import parsedate_to_datetime
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import monotonic

from contracts import Extraction, InputBatch, ModelCall, RunBudget, UpdateResult
from report import render


def load_input(path):
    raw = path.read_bytes()
    return InputBatch(hashlib.sha256(raw).hexdigest(), str(path), raw.decode("utf-8-sig"))


def atomic_write(path, content):
    with NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="\n", dir=path.parent, delete=False
    ) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(content)
        except BaseException:
            stream.close()
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def session_lock(runtime):
    # Keep the lock file in place so processes always lock the same file.
    with (runtime / ".session.lock").open("a+b") as lock:
        lock.seek(0)
        if sys.platform == "win32":
            import msvcrt

            acquire = lambda: msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            acquire = lambda: fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            acquire()
        except OSError as error:
            raise OSError("Could not lock this session. Retry after the active run finishes.") from error
        yield


def run(path, runtime, extract, apply_update):
    started = monotonic()
    batch = load_input(path)
    runtime.mkdir(parents=True, exist_ok=True)
    with session_lock(runtime):
        return run_session(batch, runtime, extract, apply_update, started)


def plan_snapshot(result):
    if result is None:
        return None
    return {key: result.get(key) for key in ("status", "plan", "last_valid")}


def run_session(batch, runtime, extract, apply_update, started):
    session_path = runtime / "session.json"
    session = (
        json.loads(session_path.read_text(encoding="utf-8"))
        if session_path.exists() else {"result": None, "sources": {}, "runs": []}
    )
    updating = session["result"] is not None
    budget = RunBudget(started + (55 if updating else 115), 5 if updating else None)
    calls = []
    offset = sum(len(run["calls"]) for run in session["runs"])
    run_log = {
        "number": len(session["runs"]) + 1,
        "source_id": batch.source_id,
        "source_path": batch.path,
        "status": "completed",
        "calls": calls,
        "before": plan_snapshot(session["result"]),
    }

    prediction_path = runtime / "predicted_tags.txt"
    prediction = None
    if updating and prediction_path.exists():
        prediction = sorted(set(prediction_path.read_text(encoding="utf-8").split()))
        if set(prediction) - {"reading", "venue", "schedule", "food", "judging", "budget"}:
            run_log["prediction_error"] = "Prediction contains an invalid model-call tag"
            prediction = None

    def record(call):
        calls.append({"number": offset + len(calls) + 1, **asdict(call)})

    if not batch.text.strip() or batch.source_id in session["sources"]:
        run_log["decisions"] = [{
            "outcome": "ignored",
            "reason": "Empty input" if not batch.text.strip() else "Exact duplicate input",
        }]
    else:
        try:
            previous = session["result"] or {}
            ledger = deepcopy(previous.get("ledger", {}))
            extraction = extract(batch, deepcopy(ledger), budget, record)
            candidate = asdict(apply_update(ledger, extraction))
            if not budget.remaining():
                raise TimeoutError("Run exceeded the time reserved for planning")
            if len(calls) != budget.attempts:
                raise RuntimeError("Recorded model calls do not match reserved attempts")
            json.dumps(candidate, allow_nan=False)
            session["result"] = candidate
            session["sources"][batch.source_id] = asdict(batch)
            run_log["decisions"] = candidate["decisions"]
            run_log["affected_areas"] = candidate["affected_areas"]
        except Exception as error:
            run_log["status"] = "failed"
            run_log["error"] = f"{type(error).__name__}: {error}"

    if prediction is not None:
        actual = sorted({call["area"] for call in calls})
        run_log["prediction"] = {
            "predicted": prediction, "actual": actual, "match": prediction == actual,
        }

    run_log["attempts"] = budget.attempts
    run_log["seconds_before_reporting"] = round(monotonic() - started, 3)
    run_log["after"] = plan_snapshot(session["result"])
    if batch.source_id not in session["sources"]:
        run_log["input_text"] = batch.text
    session["runs"].append(run_log)
    plain, html = render(session)
    atomic_write(session_path, json.dumps(session, ensure_ascii=False, allow_nan=False))
    atomic_write(runtime / "submission.txt", plain)
    atomic_write(runtime / "report.html", html)
    if prediction is not None:
        prediction_path.unlink()
    print(plain, end="")
    return int(run_log["status"] == "failed")


def message_sources(batch):
    # Only split at explicit, unquoted headers. Preserve any leading preamble.
    headers = list(re.finditer(r"(?im)^From:[ \t]+[^\r\n]+", batch.text))
    starts = [0, *(match.start() for match in headers if match.start())]
    if len(starts) == 1:
        return {batch.source_id: batch.text}
    ends = [*starts[1:], len(batch.text)]
    return {
        f"{batch.source_id}:{index}": batch.text[start:end]
        for index, (start, end) in enumerate(zip(starts, ends), 1)
    }


def extract_for_cli(batch, context, budget, record):
    from extract import extract

    class ProviderBudget:
        def acquire(self):
            budget.reserve_attempt()
            return budget.remaining()

    class ProviderRecorder:
        def append(self, row):
            usage = row["usage"]
            record(ModelCall(
                model=row["reported_model"] or row["model"],
                area=row["tag"],
                input=row["input"],
                output=row["output"],
                prompt_tokens=usage["prompt_tokens"],
                completion_tokens=usage["completion_tokens"],
                total_tokens=usage["total_tokens"],
                elapsed_seconds=row["elapsed_seconds"],
                error=row["error"],
                configured_model=row["model"],
            ))

    messages = message_sources(batch)
    source = {"src": batch.source_id, "digest": batch.source_id,
              "path": batch.path, "text": batch.text}
    if len(messages) > 1:
        source["messages"] = messages
    result = extract(source, {
        "active_claims": [*context.get("active", []), *context.get("constraints", []),
                          *(item["record"] for item in context.get("review_records", []))],
    }, ProviderBudget(), ProviderRecorder())
    if result["status"] == "UNRESOLVED":
        raise ValueError("Extraction response unresolved: " + result["ambiguous"][0]["reason"])
    return Extraction(
        claims=result["claims"],
        ambiguities=result["ambiguous"],
        irrelevant_ids=result["irrelevant"],
        sources=messages,
    )


def source_dates(sources):
    dates = {}
    for source, text in sources.items():
        lines = text.splitlines()
        if not lines or not lines[0].lower().startswith("from:"):
            continue
        for line in lines[1:]:
            field, separator, value = line.partition(":")
            if not separator or field.lower() not in {"date", "to", "subject"}:
                break
            if field.lower() != "date":
                continue
            value = value.strip()
            try:
                try:
                    date = datetime.fromisoformat(value)
                except ValueError:
                    date = parsedate_to_datetime(value)
                if date.utcoffset() is not None:
                    dates[source] = date.isoformat()
            except (TypeError, ValueError, OverflowError):
                pass
            break
    return dates


def plan_for_cli(ledger, extraction):
    from plan import Plan
    from state import Decision, State, apply_update

    saved = dict(ledger)
    for key in ("plan", "last_valid"):
        if saved.get(key) is not None:
            plan = saved[key]
            saved[key] = Plan(plan["status"], plan["areas"], tuple(plan["issues"]))
    saved["decisions"] = tuple(Decision(**item) for item in saved.get("decisions", ()))
    claims = []
    for item in extraction.claims:
        claim = dict(item)
        if claim.get("k") == "unit_price" and not claim.get("scope") and claim.get("price_basis"):
            claim["scope"] = claim["price_basis"]
        if claim.get("op") == "==":
            claim["op"] = "="
        claims.append(claim)
    claims.extend(extraction.constraints)
    result = apply_update(State(**saved), {
        "claims": claims,
        "sources": extraction.sources,
        "trusted_message_dates": source_dates(extraction.sources),
        "irrelevant": extraction.irrelevant_ids,
        "ambiguous": [item.get("src", "(missing source)") for item in extraction.ambiguities],
    })
    current = result.state.plan
    return UpdateResult(
        ledger=asdict(result.state),
        plan={"areas": current.areas, "issues": current.issues},
        status=current.status,
        last_valid=asdict(result.state.last_valid) if result.state.last_valid else None,
        decisions=[asdict(item) for item in result.decisions],
        affected_areas=list(result.affected_areas),
    )


def main(planner=plan_for_cli):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    try:
        return run(args.file, Path("runtime"), extract_for_cli, planner)
    except (ImportError, OSError, ValueError) as error:
        print(f"Planner could not run: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
