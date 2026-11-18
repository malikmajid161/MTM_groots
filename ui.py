"""Generate a small offline result page from an existing planner session."""
import argparse
from html import escape
import json
from pathlib import Path


def text(value):
    return escape(str(value))


def details(label, value):
    return f'<details><summary>{text(label)}</summary><pre>{text(json.dumps(value, indent=2, ensure_ascii=False))}</pre></details>'


def render_result(session):
    result = session.get('result') or {}
    plan = result.get('plan') or {}
    runs = session.get('runs') or []
    latest = runs[-1] if runs else {}
    status = result.get('status') or 'NO RESULT'
    tone = 'good' if status == 'VALID' else 'warn'
    calls = [call for run in runs for call in run.get('calls', [])]
    known = [call['total_tokens'] for call in calls if call.get('total_tokens') is not None]
    usage = f'{sum(known):,}' if len(known) == len(calls) else f'{sum(known):,} reported; {len(calls)-len(known)} unknown'
    latest_calls = latest.get('calls', [])
    model = next((call.get('configured_model') or call.get('model') for call in reversed(calls)), 'Unavailable')
    banner = ''
    if latest.get('status') == 'failed':
        banner = '<aside><strong>Latest run failed.</strong> ' + text(latest.get('error', 'No error details'))
        if result:
            banner += ' The result below is from the previous saved run.'
        banner += '</aside>'
    issues = plan.get('issues') or []
    issue_html = ('<section><h2>Needs attention</h2><ul>' + ''.join(f'<li>{text(issue)}</li>' for issue in issues) + '</ul></section>') if issues else ''
    cards = []
    for area in ('venue', 'schedule', 'food', 'judging', 'budget'):
        values = (plan.get('areas') or {}).get(area) or {}
        rows = []
        for key, value in values.items():
            label = key.replace('_', ' ').capitalize()
            if isinstance(value, (list, dict)):
                rows.append(details(f'{label} ({len(value)})', value))
            else:
                rows.append(f'<div class="row"><span>{text(label)}</span><strong>{text(value)}</strong></div>')
        cards.append(f'<article><h2>{area.capitalize()}</h2>' + (''.join(rows) or '<p class="muted">No result available.</p>') + '</article>')
    decisions = latest.get('decisions') or []
    decision_html = ('<section><h2>Latest decisions</h2><div class="decisions">' + ''.join(
        f'<div class="decision"><span class="outcome">{text(item.get("outcome", "unknown"))}</span><span>{text(item.get("reason", ""))}</span></div>'
        for item in decisions) + '</div></section>') if decisions else ''
    historical = details('Historical last-valid plan', result['last_valid']) if result.get('last_valid') and status != 'VALID' else ''
    seconds = latest.get('seconds_before_reporting')
    metrics = f'<span>Run {text(latest.get("number", "—"))}</span><span>{len(latest_calls)} calls this run</span><span>{text(usage)} cumulative tokens</span>'
    if seconds is not None:
        metrics += f'<span>{text(seconds)}s before reporting</span>'
    return '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Planner result</title><style>
*{box-sizing:border-box}body{margin:0;background:#fafaf9;color:#202520;font:15px/1.5 system-ui,sans-serif}main{max-width:1040px;margin:48px auto;padding:0 24px}header{display:flex;justify-content:space-between;align-items:center;gap:16px}h1{font-size:28px;letter-spacing:-.8px;margin:0}h2{font-size:15px;margin:0 0 14px}.badge{font-size:12px;font-weight:700;border-radius:6px;padding:7px 12px}.good{background:#e4f2e8;color:#245c34}.warn{background:#fff0d8;color:#7b4f0d}.muted,.meta{color:#717771}.meta{display:flex;flex-wrap:wrap;gap:6px 20px;font-size:13px;margin:14px 0 8px}.model{color:#717771;font-size:12px;margin:0 0 28px;overflow-wrap:anywhere}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}article,section{background:white;border:1px solid #e3e6e1;border-radius:10px;padding:20px}section{margin:20px 0}article:last-child{grid-column:1/-1}.row{display:flex;justify-content:space-between;gap:20px;padding:7px 0;border-top:1px solid #f0f1ee}.row span{color:#717771}.row strong{text-align:right;overflow-wrap:anywhere}aside{padding:16px 20px;background:#fff0d8;border-radius:8px;margin:20px 0;overflow-wrap:anywhere}ul{padding-left:20px;margin:0}li{margin:8px 0;overflow-wrap:anywhere}details{margin:10px 0}summary{cursor:pointer;color:#536653;font-size:13px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;background:#f6f7f4;padding:14px;border-radius:6px;max-height:340px;overflow:auto}.decision{display:grid;grid-template-columns:95px 1fr;gap:12px;padding:10px 0;border-top:1px solid #f0f1ee}.outcome{font-size:12px;color:#717771}.decision span{overflow-wrap:anywhere}footer{display:flex;gap:20px;margin:24px 0;color:#717771;font-size:13px}a{color:#436348}a:focus-visible,summary:focus-visible{outline:2px solid #436348;outline-offset:4px}@media(max-width:600px){main{margin:24px auto;padding:0 16px}.grid{grid-template-columns:1fr}header{align-items:flex-start}h1{font-size:24px}.decision{grid-template-columns:1fr;gap:3px}}
</style></head><body><main>''' + f'<header><h1>Planner result</h1><span class="badge {tone}">{text(status)}</span></header><div class="meta">{metrics}</div><p class="model">{text(model)}</p>' + banner + issue_html + '<div class="grid">' + ''.join(cards) + '</div>' + historical + decision_html + '<footer><a href="report.html">Full trace</a><a href="submission.txt">Submission text</a></footer></main></body></html>'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session', nargs='?', type=Path, default=Path('runtime/session.json'))
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    output = args.output or args.session.with_name('result.html')
    try:
        session = json.loads(args.session.read_text(encoding='utf-8'))
        output.write_text(render_result(session), encoding='utf-8')
    except (OSError, ValueError) as error:
        parser.exit(1, f'Could not render result: {error}\n')
    print(output.resolve())


if __name__ == '__main__':
    main()
