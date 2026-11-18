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


def display_fields(fields):
    if not fields:
        return "<p>No details available.</p>"
    rows = []
    for key, value in fields.items():
        label = escape(key.replace("_", " ").capitalize())
        if isinstance(value, (dict, list, tuple)):
            formatted = f"<pre>{escape(pretty(value))}</pre>"
        else:
            formatted = escape(str(value)) if value is not None else "Unavailable"
        rows.append(f"<div><dt>{label}</dt><dd>{formatted}</dd></div>")
    return "<dl>" + "".join(rows) + "</dl>"


def plan_panel(title, content):
    stored = json.loads(content)
    plan = stored.get("plan") or {}
    cards = "".join(
        f'<article><h3>{escape(area.title())}</h3>{display_fields(fields)}</article>'
        for area, fields in plan.get("areas", {}).items()
    )
    issues = "".join(f"<li>{escape(str(issue))}</li>" for issue in plan.get("issues", ()))
    status = stored["status"]
    return (
        f'<section id="plan"><h2>{escape(title)}</h2>'
        f'<p class="status" data-state="{escape(status, quote=True)}">{escape(status)}</p>'
        + (f"<ul>{issues}</ul>" if issues else "")
        + (f'<div class="grid">{cards}</div>' if cards else "<p>No plan available.</p>")
        + "</section>"
    )


def decisions_panel(title, content):
    cards = []
    for entry in json.loads(content):
        message = entry.get("message")
        cards.append(
            f'<article><h3>{escape(entry["outcome"].capitalize())} · Run {escape(str(entry["run"]))}</h3>'
            f'<p>{escape(entry.get("reason", ""))}</p>'
            + (f"<details><summary>Source message</summary><pre>{escape(message)}</pre></details>"
               if message else "")
            + "</article>"
        )
    return (
        f'<section id="review"><h2>{escape(title)}</h2>'
        + ("".join(cards) if cards else "<p>No messages needed review.</p>")
        + "</section>"
    )


def render(session):
    blocks = list(sections(session))
    plain = "\n\n".join(f"{title}\n{content}" for title, content in blocks) + "\n"
    plan_title, plan_content = blocks[0]
    trace = []
    review = ""
    for title, content in blocks[1:]:
        if title == "Rejected and unresolved messages":
            review = decisions_panel(title, content)
        else:
            trace.append(
                f"<details><summary>{escape(title)}</summary><pre>{escape(content)}</pre></details>"
            )
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Hackathon plan and trace</title><style>'
        'body{margin:0;background:#eef2f5;color:#172b39;font:1rem/1.55 system-ui,sans-serif}'
        'header{background:#132b3a;color:#fff;padding:2rem max(1rem,calc((100% - 72rem)/2))}'
        'h1,h2,h3,p{margin:0 0 .65rem}nav{display:flex;flex-wrap:wrap;gap:1rem}'
        'a{color:inherit}main{width:min(72rem,calc(100% - 2rem));margin:2rem auto}'
        'section{margin-bottom:2rem}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,19rem),1fr));gap:1rem}'
        'article,details{background:#fff;border:1px solid #ccd8e0;border-radius:.65rem;padding:1rem;min-width:0}'
        '#review article,details{margin-bottom:.65rem}summary{cursor:pointer;font-weight:650}'
        '.status{display:inline-block;background:#f8e7c5;color:#573a00;padding:.2rem .7rem;border-radius:1rem;font-weight:700}'
        '.status[data-state="VALID"]{background:#d2f0df;color:#135433}'
        '.status[data-state="INFEASIBLE"]{background:#fae0db;color:#861f13}'
        'dl{margin:0}dl div{border-top:1px solid #e3ebef;padding:.45rem 0}dt{color:#465d6b}dd{margin:0;overflow-wrap:anywhere}'
        'pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f1f5f7;padding:.75rem;border-radius:.35rem}'
        '</style></head><body><header><h1>Hackathon plan and trace</h1>'
        '<nav aria-label="Report sections"><a href="#plan">Plan</a><a href="#review">Message review</a>'
        '<a href="#trace">Run history and trace</a></nav></header><main>'
        + plan_panel(plan_title, plan_content)
        + review
        + '<section id="trace"><h2>Run history and trace</h2>'
        + "".join(trace)
        + '</section></main></body></html>'
    )
    return plain, html
