import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import cli
from contracts import Extraction
from test_plan import fixture


class LauncherTests(unittest.TestCase):
    def test_prompted_path_prints_plan_and_saves_separate_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            source=root/'messages with spaces.txt';source.write_text('Synthetic test input')
            result=root/'result'
            output=io.StringIO()
            with patch('builtins.input',return_value=str(source)), patch.object(cli,'load_env'), patch.object(cli,'extract_for_cli',return_value=Extraction(claims=fixture())),contextlib.redirect_stdout(output):
                code=cli.main(['--session',str(result)])
            self.assertEqual(code,0)
            self.assertIn('EVENT PLAN',output.getvalue())
            self.assertIn('Total: 377',output.getvalue())
            self.assertNotIn('CUMULATIVE EXECUTION TRACE',output.getvalue())
            self.assertTrue((result/'plan.txt').exists())
            self.assertIn('CUMULATIVE EXECUTION TRACE',(result/'trace.txt').read_text())
            self.assertEqual(source.read_text(),'Synthetic test input')

    def test_missing_file_does_not_call_provider(self):
        with patch.object(cli,'extract_for_cli') as extract,contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(['/missing/test.txt']),1)
            extract.assert_not_called()
