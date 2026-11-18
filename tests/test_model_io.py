import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from model_io import RunBudget, BudgetExceeded, TraceRecorder, ModelClient, http_transport

class ProviderTests(unittest.TestCase):
    def test_usage_and_cumulative_trace(self):
        response={'model':'server-model','choices':[{'message':{'content':'{}'}}], 'usage':{'prompt_tokens':7,'completion_tokens':3,'total_tokens':10}}
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'trace.jsonl'
            trace=TraceRecorder(path)
            c=ModelClient('https://provider.invalid/chat','configured-model','secret',transport=lambda *args:response)
            self.assertEqual(c.call([],RunBudget(),trace),'{}')
            restored=TraceRecorder(path)
            c.call([],RunBudget(),restored)
            self.assertEqual(restored.records[1]['number'],2)
            self.assertEqual(restored.totals()['total_tokens'],20)
            self.assertEqual(restored.records[0]['reported_model'],'server-model')
            output=io.StringIO(); restored.print_trace(output)
            self.assertIn('Total tokens:',output.getvalue())
            self.assertNotIn('secret',path.read_text())

    def test_missing_usage_never_estimated(self):
        trace=TraceRecorder()
        ModelClient('https://example.invalid','m','s',transport=lambda *a:{'choices':[{'message':{'content':'x'}}]}).call([],RunBudget(),trace)
        self.assertIsNone(trace.totals()['total_tokens'])

    def test_failure_recorded_no_hidden_retry(self):
        attempts=[]
        def fail(*args):
            attempts.append(1); raise TimeoutError('secret')
        trace=TraceRecorder(); budget=RunBudget()
        with self.assertRaises(TimeoutError):
            ModelClient('https://example.invalid','m','s',transport=fail).call([],budget,trace)
        self.assertEqual(len(attempts),1)
        self.assertEqual(budget.attempts,1)
        self.assertEqual(trace.records[0]['error'],'TimeoutError')
        self.assertIsNone(trace.records[0]['usage']['total_tokens'])

    def test_shared_budget_and_time_reserve(self):
        now=[0.0]
        budget=RunBudget(seconds=10,max_calls=2,reserve_seconds=3,clock=lambda:now[0])
        self.assertEqual(budget.acquire(),7)
        now[0]=7
        with self.assertRaises(BudgetExceeded): budget.acquire()
        self.assertEqual(budget.attempts,1)
        budget=RunBudget(max_calls=1)
        trace=TraceRecorder()
        c=ModelClient('https://example.invalid','m','s',transport=lambda *a:{'choices':[{'message':{'content':'ok'}}]})
        c.call([],budget,trace)
        with self.assertRaises(BudgetExceeded): c.call([],budget,trace)
        self.assertEqual(len(trace.records),1)

    def test_worker_has_absolute_timeout(self):
        with patch('model_io.subprocess.run', side_effect=__import__('subprocess').TimeoutExpired('worker',0.01)) as run:
            with self.assertRaises(__import__('subprocess').TimeoutExpired):
                http_transport('https://example.invalid','secret',{},0.01)
            self.assertEqual(run.call_args.kwargs['timeout'],0.01)
            self.assertNotIn('secret',str(run.call_args.args))

    def test_usage_survives_malformed_response(self):
        trace=TraceRecorder()
        c=ModelClient('https://example.invalid','m','s',transport=lambda *a:{'usage':{'total_tokens':9}})
        with self.assertRaises(KeyError): c.call([],RunBudget(),trace)
        self.assertEqual(trace.totals()['total_tokens'],9)

    def test_allowlist_and_tag(self):
        with self.assertRaises(ValueError): ModelClient('https://x.invalid','m','s',approved_models=['different'])
        with self.assertRaises(ValueError): ModelClient('http://remote.invalid','m','s')
        budget=RunBudget()
        with self.assertRaises(ValueError): ModelClient('https://x.invalid','m','s').call([],budget,TraceRecorder(),tag='fake')
        self.assertEqual(budget.attempts,0)

    def test_http_failures_preserve_raw_response_and_usage(self):
        from model_io import ProviderResponseError
        body='{"error":{"message":"rate limited"},"usage":{"total_tokens":4}}'
        def fail(*args): raise ProviderResponseError(429,body)
        trace=TraceRecorder(); budget=RunBudget()
        with self.assertRaises(ProviderResponseError):
            ModelClient('https://example.invalid','m','s',transport=fail).call([],budget,trace)
        self.assertEqual(trace.records[0]['output'],{'http_status':429,'body':body})
        self.assertEqual(trace.totals()['total_tokens'],4)
        self.assertEqual(budget.attempts,1)

    def test_real_http_error_and_malformed_response_not_retried(self):
        from http.server import BaseHTTPRequestHandler, HTTPServer
        from threading import Thread
        from model_io import ProviderResponseError
        requests=[]
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                requests.append(1)
                self.send_response(429 if len(requests)==1 else 200)
                self.end_headers(); self.wfile.write(b'raw provider response')
            def log_message(self,*args): pass
        with HTTPServer(('127.0.0.1',0),Handler) as server:
            thread=Thread(target=server.serve_forever,daemon=True); thread.start()
            try:
                for status in (429,200):
                    with self.assertRaises(ProviderResponseError) as error:
                        http_transport(f'http://127.0.0.1:{server.server_port}/chat','dummy',{},2)
                    self.assertEqual(error.exception.status,status)
                    self.assertEqual(error.exception.body,'raw provider response')
                self.assertEqual(len(requests),2)
            finally:
                server.shutdown();thread.join()
