"""Render the same cumulative session to terminal, text, and offline HTML."""

import json
from html import escape
from pathlib import Path


def pretty(value):
    return json.dumps(value, indent=2, ensure_ascii=False)


def sections(session):
    result = session.get("result") or {}
    latest = session["runs"][-1]["status"]
    title = "Saved plan before failed run" if latest == "failed" else "Current plan"
    yield title, pretty({"status": result.get("status", "UNVERIFIED"), "plan": result.get("plan")})
    if result.get("last_valid") is not None and result.get("status") != "VALID":
        yield "Last valid plan", pretty(result["last_valid"])
    sources = dict(result.get("ledger", {}).get("sources", ()))
    decisions = [
        {"run": run["number"], **decision}
        for run in session["runs"] for decision in run.get("decisions", [])
    ]
    yield "Rejected and unresolved messages", pretty([
        {**decision, "message": sources.get(decision.get("source"))}
        for decision in decisions if decision.get("outcome") in {"rejected", "unresolved"}
    ])
    for run in session["runs"]:
        details = {key: value for key, value in run.items()
                   if key not in {"calls", "before", "after", "input_text"}}
        yield f"Run {run['number']}", pretty(details)
        for call in run["calls"]:
            yield f"Model call {call['number']} | {call['model']} | {call['area']}", pretty(call)
    calls = [call for run in session["runs"] for call in run["calls"]]
    usage = [call["total_tokens"] for call in calls]
    missing = usage.count(None)
    total = sum(count for count in usage if count is not None)
    yield "Token totals", (
        f"Total tokens: {total}" if not missing else
        f"Total tokens: unavailable for {missing} of {len(calls)} calls; reported subtotal: {total}"
    )


def render(session):
    blocks = list(sections(session))
    plain = "\n\n".join(f"{title}\n{content}" for title, content in blocks) + "\n"
    template = Path(__file__).with_name("dashboard.html").read_text(encoding="utf-8")
    script = Path(__file__).with_name("dashboard.js").read_text(encoding="utf-8")
    # Keep untrusted strings in inert text. The dashboard uses textContent.
    data = escape(json.dumps(session, ensure_ascii=False, allow_nan=False), quote=False)
    html = template.replace("<!-- DASHBOARD_SCRIPT -->", script, 1)
    return plain, html.replace("<!-- SESSION_DATA -->", data, 1)
