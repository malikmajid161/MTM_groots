import json
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import time

import serve_ui


class UploadTests(unittest.TestCase):
    def test_txt_upload_runs_fresh_session_and_returns_saved_result(self):
        session = {'runs': [{'number': 1, 'status': 'completed', 'calls': []}],
                   'sources': {}, 'result': {'status': 'VALID', 'plan': {}}}
        def fake_run(path, destination, extract, plan):
            self.assertEqual(path.read_text(), 'From: organiser\nHello')
            (destination / 'session.json').write_text(json.dumps(session))
        with TemporaryDirectory() as temp, patch.object(serve_ui, 'ROOT', Path(temp)), patch.object(serve_ui, 'run', fake_run):
            server = serve_ui.make_server(0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f'http://127.0.0.1:{server.server_port}'
            try:
                html = urlopen(base).read().decode()
                self.assertIn('messages-upload', html)
                req = Request(base+'/api/sessions', data=b'From: organiser\nHello', headers={'Content-Type': 'text/plain'})
                job_id = json.load(urlopen(req))['id']
                for _ in range(100):
                    job = json.load(urlopen(base+'/api/jobs/'+job_id))
                    if job['status'] != 'running':
                        break
                    time.sleep(.01)
                self.assertEqual(job['session'], session)
                self.assertEqual(job['progress'], 100)
                req = Request(base+'/api/sessions', data=b'bad', headers={'Content-Type': 'text/plain', 'Origin': 'https://example.com'})
                with self.assertRaises(HTTPError) as caught:
                    urlopen(req)
                self.assertEqual(caught.exception.code, 403)
                caught.exception.close()
                req = Request(base+'/api/sessions', data=b' ', headers={'Content-Type': 'text/plain'})
                with self.assertRaises(HTTPError) as caught:
                    urlopen(req)
                self.assertEqual(caught.exception.code, 400)
                caught.exception.close()
            finally:
                server.shutdown()
                server.server_close()
