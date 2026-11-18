import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from time import monotonic

from contracts import BudgetExceeded, Extraction, ModelCall, RunBudget, UpdateResult
from main import run


class IntegrationTests(unittest.TestCase):
    def test_initial_update_duplicate_and_failed_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime"
            source = root / "input.txt"
            calls = []

            def extract(batch, context, budget, record):
                budget.reserve_attempt()
                record(ModelCall("mock", "reading", batch.text, "<script>", total_tokens=10))
                calls.append((batch.text, context.copy(), budget.max_attempts))
                if batch.text == "broken":
                    context["revision"] = 99
                    raise ValueError("Malformed response")
                return Extraction()

            def apply_update(ledger, extraction):
                revision = ledger.get("revision", 0) + 1
                return UpdateResult({"revision": revision}, {"revision": revision}, "VALID")

            with contextlib.redirect_stdout(io.StringIO()) as output:
                for payload, expected in [
                    (b"initial\r\npack", 0),
                    (b"multi\r\nline\r\nupdate", 0),
                    (b"multi\r\nline\r\nupdate", 0),
                    (b"broken", 1),
                ]:
                    if payload == b"broken":
                        (runtime / "predicted_tags.txt").write_text("reading", encoding="utf-8")
                    source.write_bytes(payload)
                    self.assertEqual(run(source, runtime, extract, apply_update), expected)
                    self.assertEqual(source.read_bytes(), payload)

            self.assertEqual(calls[0], ("initial\r\npack", {}, None))
            self.assertEqual(calls[1], ("multi\r\nline\r\nupdate", {"revision": 1}, 5))
            session = json.loads((runtime / "session.json").read_text(encoding="utf-8"))
            self.assertEqual(session["result"]["ledger"]["revision"], 2)
            self.assertEqual(session["runs"][2]["calls"], [])
            self.assertTrue(session["runs"][3]["prediction"]["match"])
            self.assertFalse((runtime / "predicted_tags.txt").exists())
            submission = (runtime / "submission.txt").read_text(encoding="utf-8")
            self.assertIn("Model call 3 | mock | reading", submission)
            self.assertIn("Total tokens: 30", submission)
            self.assertIn("Malformed response", output.getvalue())
            html = (runtime / "report.html").read_text(encoding="utf-8")
            self.assertIn("&lt;script&gt;", html)
            self.assertNotIn("<script>", html)

    def test_attempt_limit_and_deadline(self):
        budget = RunBudget(monotonic() + 60, 5)
        for number in range(1, 6):
            self.assertEqual(budget.reserve_attempt(), number)
        with self.assertRaises(BudgetExceeded):
            budget.reserve_attempt()
        with self.assertRaises(BudgetExceeded):
            RunBudget(monotonic() - 1, None).reserve_attempt()
