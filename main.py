"""Run the planner through a single command for both initial packs and updates."""

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import monotonic

from contracts import InputBatch, RunBudget
from report import render


def load_input(path):
    raw = path.read_bytes()
    return InputBatch(hashlib.sha256(raw).hexdigest(), str(path), raw.decode("utf-8"))


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
            ledger = previous.get("ledger", {})
            extraction = extract(batch, ledger, budget, record)
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

    run_log["attempts"] = budget.attempts
    run_log["seconds_before_reporting"] = round(monotonic() - started, 3)
    session["runs"].append(run_log)
    plain, html = render(session)
    atomic_write(session_path, json.dumps(session, ensure_ascii=False, allow_nan=False))
    atomic_write(runtime / "submission.txt", plain)
    atomic_write(runtime / "report.html", html)
    print(plain, end="")
    return int(run_log["status"] == "failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    try:
        from extract import extract
        from state import apply_update

        return run(args.file, Path("runtime"), extract, apply_update)
    except (ImportError, OSError, ValueError) as error:
        print(f"Planner could not run: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
