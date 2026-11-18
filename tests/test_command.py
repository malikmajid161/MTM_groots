import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from shutil import copy2


class CommandTests(unittest.TestCase):
    def test_rehearsal_uses_same_command_and_persists_each_update(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("main.py", "report.py", "contracts.py"):
                copy2(repo / name, root / name)
            (root / "extract.py").write_text(
                "def extract(batch, context, budget, record):\n"
                "    budget.acquire()\n"
                "    usage = dict(prompt_tokens=None, completion_tokens=None, total_tokens=None)\n"
                "    record.append(dict(model='mock-extractor', reported_model=None,\n"
                "                       tag='reading', input=batch['text'], output={},\n"
                "                       usage=usage, elapsed_seconds=0, error=None))\n"
                "    return dict(status='EXTRACTED', claims=[{'v': batch['text']}],\n"
                "                ambiguous=[], irrelevant=[])\n",
                encoding="utf-8",
            )
            (root / "state.py").write_text(
                "from contracts import UpdateResult\n"
                "def apply_update(ledger, extraction):\n"
                "    revision = ledger.get('revision', 0) + 1\n"
                "    decisions = []\n"
                "    if '74 meal boxes' in extraction.claims[0]['v']:\n"
                "        decisions.append({'outcome': 'rejected', 'reason': '74 < 104 meals'})\n"
                "    return UpdateResult({'revision': revision}, {'revision': revision},\n"
                "                        'VALID', decisions=decisions)\n",
                encoding="utf-8",
            )
            (root / "mock_cli.py").write_text(
                "from main import main\nfrom state import apply_update\n"
                "raise SystemExit(main(apply_update))\n",
                encoding="utf-8",
            )
            environment = {**os.environ, "PYTHONIOENCODING": "utf-8"}
            for number, name in enumerate(("pack", "venue", "invalid", "attendance"), 1):
                if name == "venue":
                    (root / "runtime" / "predicted_tags.txt").write_text("reading", encoding="utf-8")
                source = repo / "tests" / "fixtures" / f"rehearsal_{name}.txt"
                result = subprocess.run(
                    [sys.executable, "mock_cli.py", str(source)],
                    cwd=root, env=environment, encoding="utf-8",
                    capture_output=True, timeout=120 if number == 1 else 60,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f"Model call {number} | mock-extractor | reading", result.stdout)
            submission = (root / "runtime" / "submission.txt").read_text(encoding="utf-8")
            self.assertIn('"match": true', submission)
            self.assertIn("74 < 104 meals", submission)
            self.assertIn("Total tokens: unavailable for 4 of 4 calls", submission)
            html = (root / "runtime" / "report.html").read_text(encoding="utf-8")
            self.assertIn("Rejected and unresolved messages", html)
            self.assertIn("74 &lt; 104 meals", html)
