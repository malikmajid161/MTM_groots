"""Run the planner through a single command for both initial packs and updates."""

import argparse
import hashlib
import json
import sys
from copy import deepcopy
from dataclasses import asdict
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


def run(path, runtime, extract, apply_update):
    started = monotonic()
    batch = load_input(path)
    runtime.mkdir(parents=True, exist_ok=True)
    session_path = runtime / "session.json"
    session = (
        json.loads(session_path.read_text(encoding="utf-8"))
        if session_path.exists() else {"result": None, "sources": {}, "runs": []}
    )
    updating = session_path.exists()
    budget = RunBudget(started + (55 if updating else 115), 5 if updating else None)
    calls = []
    offset = sum(len(run["calls"]) for run in session["runs"])
    run_log = {
        "number": len(session["runs"]) + 1,
        "source_id": batch.source_id,
        "source_path": batch.path,
        "status": "completed",
        "calls": calls,
    }

    prediction_path = runtime / "predicted_tags.txt"
    prediction = None
    if updating and prediction_path.exists():
        prediction = sorted(set(prediction_path.read_text(encoding="utf-8").split()))
        if set(prediction) - {"reading", "venue", "schedule", "food", "judging", "budget"}:
            raise ValueError("Prediction contains an invalid model-call tag")

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
    session["runs"].append(run_log)
    plain, html = render(session)
    atomic_write(session_path, json.dumps(session, ensure_ascii=False, allow_nan=False))
    atomic_write(runtime / "submission.txt", plain)
    atomic_write(runtime / "report.html", html)
    if prediction is not None:
        prediction_path.unlink()
    print(plain, end="")
    return int(run_log["status"] == "failed")


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
            ))

    source = {"src": batch.source_id, "digest": batch.source_id,
              "path": batch.path, "text": batch.text}
    result = extract(source, {
        "active_claims": context.get("active", []),
    }, ProviderBudget(), ProviderRecorder())
    if result["status"] == "UNRESOLVED":
        raise ValueError("Extraction response unresolved: " + result["ambiguous"][0]["reason"])
    return Extraction(
        claims=result["claims"],
        ambiguities=result["ambiguous"],
        irrelevant_ids=result["irrelevant"],
        sources={batch.source_id: batch.text},
    )


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
