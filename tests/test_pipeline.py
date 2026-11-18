"""Exercise the production CLI, HTTP transport, extractor, and planner together."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread

from test_plan import claim, fixture


class PipelineTests(unittest.TestCase):
    def test_initial_pack_and_three_updates_over_local_http(self):
        responses = [
            fixture(),
            [claim("budget", "expense", "existing", "committed_cost", 47, currency="PKR")],
            [claim("food", "vendor_item", "meal", "quantity", 12, kind="reported_action",
                   actor="caterer")],
            [claim("venue", "venue_option", "hall", "capacity", 25)],
        ]
        requests = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                source = json.loads(body["messages"][-1]["content"])["source"]
                requests.append(source["text"])
                claims = [
                    {"kind": "fact", "modality": "none", "u": "items",
                     "price_basis": record.get("scope", "fixed"), **record, "src": source["src"],
                     "v": int(record["v"]) if record["k"] == "budget_cap" else record["v"]}
                    for record in responses[len(requests) - 1]
                ]
                extracted = {"claims": claims, "irrelevant": [], "ambiguous": []}
                payload = json.dumps({
                    "model": "mock-http",
                    "choices": [{"message": {"content": json.dumps(extracted)}}],
                    "usage": {"prompt_tokens": 11, "completion_tokens": 9, "total_tokens": 20},
                }).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *_):
                pass

        repo = Path(__file__).resolve().parents[1]
        with HTTPServer(("127.0.0.1", 0), Handler) as server, tempfile.TemporaryDirectory() as tmp:
            worker = Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                env = {
                    **os.environ, "PYTHONIOENCODING": "utf-8", "MODEL_NAME": "mock-http",
                    "MODEL_APPROVED_MODELS": "mock-http", "MODEL_API_KEY": "dummy",
                    "MODEL_ENDPOINT": f"http://127.0.0.1:{server.server_port}/chat/completions",
                }
                root = Path(tmp)
                inputs = (
                    "Initial workshop pack", "Finance updates the existing expense.",
                    "Supplier claims an order reduction.", "Venue confirms an amended seating limit.",
                )
                for i, text in enumerate(inputs):
                    path = root / f"input-{i}.txt"
                    path.write_text(text, encoding="utf-8")
                    result = subprocess.run(
                        [sys.executable, str(repo / "main.py"), str(path)], cwd=root,
                        env=env, capture_output=True, encoding="utf-8", timeout=60 if i else 120,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
                    if i == 0:
                        self.assertIn('"status": "VALID"', result.stdout)
                session = json.loads((root / "runtime" / "session.json").read_text(encoding="utf-8"))
                self.assertEqual(requests, list(inputs))
                self.assertEqual([run["attempts"] for run in session["runs"]], [1] * 4)
                self.assertEqual(session["runs"][2]["decisions"][0]["outcome"], "rejected")
                plan = session["result"]["plan"]["areas"]
                self.assertEqual(plan["food"]["quantity"], 27)
                self.assertEqual(plan["budget"]["total"], "381")
                self.assertEqual(plan["venue"]["capacity"], 25)
                self.assertIn("Total tokens: 80", result.stdout)
            finally:
                server.shutdown()
                worker.join()
