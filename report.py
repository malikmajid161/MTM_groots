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


def readable_lines(value, indent=0):
    """Format a plan as labeled text, without provider payloads."""
    prefix = ' ' * indent
    if isinstance(value, dict):
        for key, item in value.items():
            label = key.replace('_', ' ').capitalize()
            if isinstance(item, (dict, list, tuple)):
                yield prefix + label + ':'
                yield from readable_lines(item, indent + 2)
            else:
                yield prefix + label + ': ' + ('Yes' if item is True else 'No' if item is False else str(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, (dict, list, tuple)):
                yield prefix + '-'
                yield from readable_lines(item, indent + 2)
            else:
                yield prefix + '- ' + str(item)


def render_plan(session):
    result = session.get('result') or {}
    runs = session.get('runs') or []
    latest = runs[-1] if runs else {}
    plan = result.get('plan') or {}
    lines = ['EVENT PLAN', 'Status: ' + result.get('status', 'NO RESULT'), '']
    if latest.get('status') == 'failed':
        lines += ['Latest attempt failed: ' + latest.get('error', 'Unknown error'),
                  'Any saved plan below belongs to an earlier run.' if result else 'No plan was generated.', '']
    if result.get('status') == 'UNVERIFIED':
        lines += ['The plan could not be verified. This is not an approved plan.', '']
    elif result.get('status') == 'INFEASIBLE':
        lines += ['No candidate satisfies the supported requirements.', '']
    if plan.get('issues'):
        lines += ['NEEDS ATTENTION', *('- ' + str(issue) for issue in plan['issues']), '']
    areas = plan.get('areas') or {}
    if not any(areas.values()):
        lines += ['No complete plan is available.', '']
    for area in ('venue', 'schedule', 'food', 'judging', 'budget'):
        lines += [area.upper()]
        values = areas.get(area) or {}
        lines += list(readable_lines(values)) if values else ['Not available.']
        lines += ['']
    decisions = [item for item in latest.get('decisions', []) if item.get('outcome') in {'rejected', 'unresolved'}]
    if decisions:
        lines += ['MESSAGE DECISIONS', *(f"- {item['outcome']}: {item.get('reason', '')}" for item in decisions), '']
    if result.get('last_valid') and result.get('status') != 'VALID':
        lines += ['HISTORICAL LAST-VALID PLAN (not the current plan)', *readable_lines(result['last_valid']), '']
    return '\n'.join(lines).rstrip() + '\n'


def render_trace(session):
    calls = [call for run in session.get('runs', []) for call in run.get('calls', [])]
    lines = ['CUMULATIVE EXECUTION TRACE', '', 'AI CALL SUMMARY']
    for call in calls:
        purpose = call.get('area', 'unknown')
        if purpose == 'reading':
            payload = call.get('input') or {}
            messages = payload.get('messages', []) if isinstance(payload, dict) else payload
            reviewing = False
            for message in messages:
                if not isinstance(message, dict):
                    continue
                if 'draft_extraction' in message:
                    reviewing = True
                elif message.get('role') == 'user':
                    try:
                        reviewing |= 'draft_extraction' in json.loads(message.get('content', '{}'))
                    except (ValueError, TypeError):
                        pass
            purpose = 'Reviewing extracted facts' if reviewing else 'Reading messages'
        tokens = call.get('total_tokens')
        lines.append(f"Call {call['number']} | Model: {call.get('configured_model') or call.get('model', 'unknown')} | Purpose: {purpose} | Tokens: {tokens if tokens is not None else 'unknown'}" + (' | FAILED' if call.get('error') else ''))
    lines += ['', 'INPUT EVIDENCE', pretty(session.get('sources', {}))]
    calls = []
    for run in session.get('runs', []):
        lines += ['', f"RUN {run['number']}", pretty({key: value for key, value in run.items() if key != 'calls'})]
        for call in run.get('calls', []):
            calls.append(call)
            lines += ['', f"MODEL CALL {call['number']} | {call.get('model', 'unknown')} | {call.get('area', 'unknown')}", pretty(call)]
    usage = [call.get('total_tokens') for call in calls]
    missing = usage.count(None)
    subtotal = sum(value for value in usage if value is not None)
    lines += ['', 'TOKEN TOTALS', f'Model attempts: {len(calls)}']
    lines += [f'Total tokens: {subtotal}' if not missing else
              f'Total tokens: unknown; reported subtotal: {subtotal}; unavailable for {missing} of {len(calls)} calls']
    return '\n'.join(lines) + '\n'
