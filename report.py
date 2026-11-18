"""Render the same cumulative session to terminal, text, and offline HTML."""

import json
from html import escape


def pretty(value):
    return json.dumps(value, indent=2, ensure_ascii=False)


def sections(session):
    result = session.get("result") or {}
    latest = session["runs"][-1]["status"]
    title = "Saved plan before failed run" if latest == "failed" else "Current plan"
    yield title, pretty({"status": result.get("status", "UNVERIFIED"), "plan": result.get("plan")})
    if result.get("last_valid") is not None and result.get("status") != "VALID":
        yield "Last valid plan", pretty(result["last_valid"])
    decisions = [
        {"run": run["number"], **decision}
        for run in session["runs"] for decision in run.get("decisions", [])
    ]
    yield "Rejected and unresolved messages", pretty([
        decision for decision in decisions if decision.get("outcome") in {"rejected", "unresolved"}
    ])
    for run in session["runs"]:
        details = {key: value for key, value in run.items() if key != "calls"}
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
    body = "\n".join(
        f"<details><summary>{escape(title)}</summary><pre>{escape(content)}</pre></details>"
        if title.startswith("Model call ") else
        f"<section><h2>{escape(title)}</h2><pre>{escape(content)}</pre></section>"
        for title, content in blocks
    )
    html = (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Hackathon plan and trace</title><style>'
        'body{font:1rem system-ui;max-width:75rem;margin:2rem auto;padding:0 1rem}'
        'pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f5f7;padding:1rem}'
        '</style><main><h1>Hackathon plan and trace</h1>' + body + '</main></html>'
    )
    return plain, html
