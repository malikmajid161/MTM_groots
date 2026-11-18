"""Serve the local planner dashboard on a loopback address."""

import argparse
import base64
import binascii
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from main import atomic_write, extract_for_cli, plan_for_cli, run

from report import render_dashboard
from uploads import MAX_FILE, MAX_TEXT, read_upload

ASSETS = Path(__file__).resolve().parent
RUNTIME = Path("runtime")
PREDICTION_TAGS = ("reading", "venue", "schedule", "food", "judging", "budget")
EXPORTS = {"/" + name: name for name in ("report.html", "submission.txt", "plan.txt", "trace.txt", "session.json")}


def connected_page(session):
    html = render_dashboard(session)
    controls = ASSETS.joinpath("planner_panel.html").read_text(encoding="utf-8")
    script = ASSETS.joinpath("planner_panel.js").read_text(encoding="utf-8")
    # Keep the stand-alone dashboard offline. Only the local server enables API access.
    html = html.replace("script-src 'unsafe-inline';", "script-src 'unsafe-inline'; connect-src 'self';", 1)
    html = html.replace('<main id="pages"></main>', controls + '<main id="pages"></main>', 1)
    return html.replace("</body>", f"<script>{script}</script></body>", 1)



class Dashboard(BaseHTTPRequestHandler):
    def reply(self, status, body, media_type):
        self.send_response(status)
        self.send_header("Content-Type", media_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(body)

    def json(self, status, body):
        self.reply(status, json.dumps(body, ensure_ascii=False).encode(), "application/json")

    def valid_host(self):
        return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

    def session(self):
        path = RUNTIME / "session.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {"result": None, "runs": []}

    def do_GET(self):
        if not self.valid_host():
            self.send_error(HTTPStatus.FORBIDDEN)
        elif self.path == "/api/session":
            self.json(HTTPStatus.OK, self.session())
        elif self.path == "/":
            self.reply(HTTPStatus.OK, connected_page(self.session()).encode(), "text/html; charset=utf-8")
        elif self.path in EXPORTS and (RUNTIME / EXPORTS[self.path]).is_file():
            path = RUNTIME / EXPORTS[self.path]
            media_type = {".html": "text/html", ".json": "application/json"}.get(path.suffix, "text/plain")
            self.reply(HTTPStatus.OK, path.read_bytes(), media_type + "; charset=utf-8")
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self):
        if not self.valid_host() or self.headers.get("Origin") != f"http://{self.headers.get('Host')}":
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if self.path not in {"/api/run", "/api/preview"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if self.headers.get_content_type() != "application/json":
            self.json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "Send JSON."})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            limit = 2 * MAX_FILE if self.path == "/api/preview" else 6 * MAX_TEXT + 1024
            if not 0 < size <= limit:
                raise ValueError("Request exceeds the input size limit.")
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict):
                raise ValueError("Expected a JSON object.")
            if self.path == "/api/preview":
                name, encoded = payload.get("name"), payload.get("data")
                if not isinstance(name, str) or not isinstance(encoded, str):
                    raise ValueError("Choose a supported file.")
                try:
                    data = base64.b64decode(encoded, validate=True)
                except (ValueError, binascii.Error) as error:
                    raise ValueError("Invalid upload encoding.") from error
                self.json(HTTPStatus.OK, {"text": read_upload(name, data)})
                return
            text = payload.get("text")
            if not isinstance(text, str) or not text.strip():
                raise ValueError("Enter or upload a message pack.")
            if len(text.encode("utf-8")) > MAX_TEXT:
                raise ValueError("Message text exceeds 512 KiB.")
            tags = payload.get("prediction")
            if tags is not None and (
                not isinstance(tags, list) or any(tag not in PREDICTION_TAGS for tag in tags)
            ):
                raise ValueError("Invalid prediction tags.")
            RUNTIME.mkdir(parents=True, exist_ok=True)
            if tags is not None and self.session()["result"] is not None:
                atomic_write(RUNTIME / "predicted_tags.txt", "\n".join(tags))
            with TemporaryDirectory() as directory:
                source = Path(directory) / "message.txt"
                source.write_bytes(text.encode("utf-8"))
                run(source, RUNTIME, extract_for_cli, plan_for_cli)
            self.json(HTTPStatus.OK, self.session())
        except (ValueError, OSError) as error:
            self.json(HTTPStatus.BAD_REQUEST, {"error": str(error)})


def main():
    global RUNTIME
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--runtime", type=Path, default=RUNTIME, help="Session and export directory")
    args = parser.parse_args()
    RUNTIME = args.runtime
    with HTTPServer(("127.0.0.1", args.port), Dashboard) as server:
        print(f"http://127.0.0.1:{server.server_port}", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
