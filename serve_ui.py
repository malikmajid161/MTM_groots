"""Local messages-upload dashboard: python3 serve_ui.py."""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread
from uuid import uuid4

from cli import load_env
from main import run, extract_for_cli, plan_for_cli
from report import render

ROOT = Path(__file__).resolve().parent
MAX_UPLOAD = 2 * 1024 * 1024


def make_server(port=8000, initial=None, extractor=extract_for_cli, planner=plan_for_cli):
    jobs, lock = {}, Lock()
    initial = initial or {'runs': [], 'sources': {}, 'result': None}
    # sections() expects at least one run for an empty dashboard.
    empty = {'runs': [{'number': 0, 'status': 'ready', 'calls': []}], 'sources': {}, 'result': None}

    def update(job, **values):
        with lock:
            jobs[job].update(values)

    def work(job, path, destination):
        try:
            def extract(batch, context, budget, record):
                update(job, progress=15, message='Reading messages and extracting facts…')
                def recorded(call):
                    record(call)
                    update(job, progress=45, message='AI call completed; reviewing extracted facts…')
                return extractor(batch, context, budget, recorded)
            def plan(ledger, extraction):
                update(job, progress=75, message='Checking venue, schedule, food, judges and budget…')
                return planner(ledger, extraction)
            run(path, destination, extract, plan)
            session = json.loads((destination / 'session.json').read_text())
            failed = session['runs'][-1]['status'] == 'failed'
            update(job, status='failed' if failed else 'completed', progress=100,
                   message=session['runs'][-1].get('error', 'Plan ready.'), session=session,
                   directory=str(destination))
        except Exception as error:
            update(job, status='failed', progress=100, message=f'{type(error).__name__}: {error}')

    class Handler(BaseHTTPRequestHandler):
        def send(self, status, body, kind='application/json'):
            data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
            self.send_response(status)
            self.send_header('Content-Type', kind + '; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path in ('/', '/report.html'):
                return self.send(200, render(empty)[1], 'text/html')
            if self.path.startswith('/api/jobs/'):
                with lock:
                    job = dict(jobs.get(self.path.rsplit('/', 1)[-1], {}))
                return self.send(200 if job else 404, job or {'message': 'Unknown session'})
            self.send(404, {'message': 'Not found'})

        def do_POST(self):
            if self.path not in ('/api/sessions', '/api/updates'):
                return self.send(404, {'message': 'Not found'})
            # Only the local dashboard may start model requests; no cross-origin uploads.
            origin = self.headers.get('Origin')
            if origin and origin != 'http://' + self.headers.get('Host', ''):
                return self.send(403, {'message': 'Cross-origin requests are not allowed'})
            is_update = self.path == '/api/updates'
            if self.headers.get_content_type() != ('application/json' if is_update else 'text/plain'):
                return self.send(415, {'message': 'Upload a UTF-8 messages TXT file'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= MAX_UPLOAD:
                    raise ValueError('Choose a nonempty TXT file smaller than 2 MB')
                raw = self.rfile.read(length)
                seed = None
                if is_update:
                    payload = json.loads(raw)
                    seed = payload.get('session')
                    message = payload.get('message')
                    if not isinstance(seed, dict) or not seed.get('result') or not isinstance(seed.get('runs'), list) or not isinstance(seed.get('sources'), dict):
                        raise ValueError('Open or create a completed session before adding an update')
                    if not isinstance(message, str):
                        raise ValueError('Enter an update message')
                    raw = message.encode('utf-8')
                if not raw.decode('utf-8-sig').strip():
                    raise ValueError('Messages file is empty')
            except (ValueError, UnicodeError, AttributeError) as error:
                return self.send(400, {'message': str(error)})
            job = uuid4().hex
            destination = ROOT / 'runtime' / 'ui' / job
            destination.mkdir(parents=True)
            if seed is not None:
                (destination / 'session.json').write_text(json.dumps(seed), encoding='utf-8')
            path = destination / 'messages.txt'
            path.write_bytes(raw)
            with lock:
                jobs[job] = {'status': 'running', 'progress': 5, 'message': 'Messages received…'}
            Thread(target=work, args=(job, path, destination), daemon=True).start()
            self.send(202, {'id': job})

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    load_env(ROOT / '.env')
    server = make_server(args.port)
    print(f'Dashboard: http://127.0.0.1:{server.server_port}/', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
