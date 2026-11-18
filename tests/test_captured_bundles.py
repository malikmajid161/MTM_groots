"""Replay captured extraction responses; these tests make no network calls."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from contracts import InputBatch, Extraction
from extract import extract, load_input
from main import message_sources, plan_for_cli
from model_io import ModelClient, RunBudget, TraceRecorder
from plan import parse_stamp


class CapturedBundleTests(unittest.TestCase):
    def test_medium_pack_and_capacity_update_match_external_oracle(self):
        fixture = json.loads((Path(__file__).parent/'fixtures/medium_captured_responses.json').read_text())
        ledger = {}
        with tempfile.TemporaryDirectory() as directory, patch.dict('os.environ', {'MODEL_VERIFY_EXTRACTION':'0'}):
            for item in fixture['runs']:
                path = Path(directory)/'input.txt'
                path.write_text(item['text'])
                source = load_input(path)
                sources = message_sources(InputBatch(source['src'],str(path),source['text']))
                source['messages'] = sources
                client = ModelClient('https://example.invalid','captured-fixture','fixture-key',
                                     transport=lambda *args: item['response'])
                context = {'active_claims':[*ledger.get('active',[]),*ledger.get('constraints',[])]}
                result = extract(source,context,RunBudget(),TraceRecorder(),client)
                updated = plan_for_cli(ledger,Extraction(claims=result['claims'],sources=sources,
                    ambiguities=result['ambiguous'],irrelevant_ids=result['irrelevant']))
                expected = item['expected']
                self.assertEqual(updated.status,expected['status'],updated.plan['issues'])
                areas = updated.plan['areas']
                self.assertEqual(areas['budget']['total'],expected['total'])
                self.assertEqual(areas['venue']['option'],expected['venue'])
                self.assertEqual(areas['venue']['people'],expected['people'])
                self.assertEqual(areas['food']['quantity'],expected['quantity'])
                assignments = areas['judging']['assignments']
                self.assertEqual(len({a['team'] for a in assignments}),areas['judging']['teams'])
                for judge in areas['judging']['engaged']:
                    times = sorted((parse_stamp(a['start']),parse_stamp(a['end']))
                                   for a in assignments if a['judge'] == judge)
                    self.assertTrue(all(left[1] <= right[0] for left,right in zip(times,times[1:])))
                ledger = updated.ledger
