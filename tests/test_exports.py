import unittest
from dataclasses import asdict
from contracts import Extraction
from main import plan_for_cli
from report import render_plan, render_trace
from test_plan import fixture


class ExportTests(unittest.TestCase):
    def test_plan_has_five_areas_explicit_costs_and_budget_verdict(self):
        result=plan_for_cli({},Extraction(claims=fixture()))
        session={'result':asdict(result),'runs':[{'number':1,'status':'completed','calls':[]}]}
        output=render_plan(session)
        for area in ['VENUE','SCHEDULE','FOOD','JUDGING','BUDGET']:
            self.assertIn(area,output)
        self.assertEqual(output.count('Cost:'),3)
        self.assertIn('Engaged count: 2',output)
        self.assertIn('Total: 377',output)
        self.assertIn('Fits: Yes',output)
        self.assertNotIn('MODEL CALL',output)

    def test_trace_has_one_summary_line_per_attempt_and_honest_total(self):
        calls=[{'number':1,'model':'fixture-model','area':'reading','input':[],
                'total_tokens':None,'error':'provider failure'},
               {'number':2,'model':'fixture-model','area':'reading','input':[{'draft_extraction':{}}],
                'total_tokens':7}]
        session={'result':None,'runs':[{'number':1,'status':'completed','calls':calls}]}
        output=render_trace(session)
        summary=output.split('INPUT EVIDENCE')[0]
        self.assertEqual(summary.count('\nCall '),2)
        self.assertIn('Call 1 | Model: fixture-model | Purpose: Reading messages | Tokens: unknown | FAILED',summary)
        self.assertIn('Call 2 | Model: fixture-model | Purpose: Reviewing extracted facts | Tokens: 7',summary)
        self.assertIn('Total tokens: unknown; reported subtotal: 7',output)
