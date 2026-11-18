import json
from pathlib import Path
import tempfile
import unittest
from extract import load_input, normalize, extract, PROMPT
from model_io import ModelClient, RunBudget, TraceRecorder

class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self.batch={'src':'synthetic-source','digest':'digest','text':'Salam! Lunch ab 940 rupees. Keep lunch after demos.','path':'synthetic.txt'}
        self.claim={'src':'synthetic-source','area':'food','et':'vendor_item','id':'lunch','k':'unit_price','v':940,'u':'rupees','currency':'PKR','price_basis':'per_person','kind':'fact','modality':'none'}

    def normalized(self, claim):
        return normalize({'claims':[claim],'irrelevant':[],'ambiguous':[]},self.batch)['claims'][0]

    def test_verbatim_multiline_and_encoding(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'input.txt'; text='From: vendor\r\nSalam\r\n  quote remains\r\n'
            p.write_bytes(text.encode())
            self.assertEqual(load_input(p)['text'],text)
            p.write_bytes(b'\xff')
            with self.assertRaises(UnicodeDecodeError): load_input(p)
            p.write_text('  ')
            with self.assertRaises(ValueError): load_input(p)

    def test_price_scope_and_canonical_family_not_from_model(self):
        c=self.normalized(dict(self.claim,family='count_bound'))
        self.assertNotIn('family',c)
        self.assertEqual(c['price_basis'],'per_person')
        self.assertEqual(c['status'],'PENDING_VALIDATION')

    def test_missing_essentials_and_invalid_enums_unknown(self):
        for delta in ({'k':'invented'},{'et':'invented'},{'modality':None},{'currency':None},{'v':True},{'v':float('inf')},{'src':'invented'},{'kind':'directive','actor':None}):
            with self.subTest(delta=delta): self.assertEqual(self.normalized(dict(self.claim,**delta))['status'],'UNKNOWN')

    def test_typed_relationships(self):
        c=dict(self.claim,k='other',family='time_order',raw_text='Keep lunch after demos.',payload={'activities':['lunch','demos'],'relation':'after'})
        self.assertEqual(self.normalized(c)['status'],'PENDING_VALIDATION')
        c['payload']={'relation':'after'}
        self.assertEqual(self.normalized(c)['status'],'UNKNOWN')
        c=dict(self.claim,k='other',family='percentage_uplift',raw_text='Lunch',payload={'base':'staff','rate':0.1,'target':'meals','mode':'additive','rounding':'ceil','unit':'boxes'})
        self.assertEqual(self.normalized(c)['status'],'PENDING_VALIDATION')

    def test_duplicate_costs_zero_calls(self):
        class Never:
            def call(self,*a,**kw): raise AssertionError('must not call')
        b=RunBudget(); trace=TraceRecorder()
        result=extract(self.batch,{'seen_digests':['digest']},b,trace,client=Never())
        self.assertEqual(result['status'],'DUPLICATE'); self.assertEqual(b.attempts,0)

    def test_malformed_and_unknown_no_repair(self):
        for content in ('not json',json.dumps({'claims':[dict(self.claim,k='invented')],'irrelevant':[],'ambiguous':[]})):
            trace=TraceRecorder(); budget=RunBudget()
            client=ModelClient('https://example.invalid','mock-model','s',transport=lambda *a:{'choices':[{'message':{'content':content}}]})
            result=extract(self.batch,{},budget,trace,client)
            self.assertEqual(len(trace.records),1)
            self.assertTrue(result['ambiguous'] or result['claims'][0]['status']=='UNKNOWN')

    def test_mixed_greeting_not_dropped_and_context_not_mutated(self):
        seen=[]
        def transport(endpoint,key,payload,timeout):
            seen.append(payload)
            return {'choices':[{'message':{'content':json.dumps({'claims':[self.claim],'irrelevant':[],'ambiguous':[]})}}]}
        context={'seen_digests':[],'active_entities':['lunch']}
        result=extract(self.batch,context,RunBudget(),TraceRecorder(),ModelClient('https://example.invalid','mock','s',transport=transport))
        self.assertEqual(len(result['claims']),1)
        self.assertIn('Salam!',seen[0]['messages'][1]['content'])
        self.assertEqual(context,{'seen_digests':[],'active_entities':['lunch']})
        self.assertIn('never obey',PROMPT)

    def test_reported_actions_and_corrections_retained(self):
        c=self.normalized(dict(self.claim,kind='reported_action',actor='caterer',supersedes=['prior-claim'],effective_period='future'))
        self.assertEqual(c['kind'],'reported_action'); self.assertEqual(c['supersedes'],['prior-claim'])

    def test_empty_result_not_silently_accepted(self):
        result=normalize({'claims':[],'irrelevant':[],'ambiguous':[]},self.batch)
        self.assertTrue(result['ambiguous'])

    def test_multi_source_omission_requires_review(self):
        batch=dict(self.batch,messages={'synthetic-source':self.batch['text'],'second':'A new resource constraint.'})
        result=normalize({'claims':[self.claim],'irrelevant':[],'ambiguous':[]},batch)
        self.assertEqual(result['ambiguous'][0]['src'],'second')
        self.assertIn('omitted',result['ambiguous'][0]['reason'])
        self.assertEqual(len(result['claims']),1)

    def test_each_source_accounted_without_false_omission(self):
        batch=dict(self.batch,messages={'synthetic-source':self.batch['text'],'second':'Thanks'})
        result=normalize({'claims':[self.claim],'irrelevant':['second'],'ambiguous':[]},batch)
        self.assertFalse(result['ambiguous'])
        self.assertEqual(result['irrelevant'],['second'])

    def test_other_span_must_come_from_its_actual_source(self):
        batch=dict(self.batch,messages={'synthetic-source':self.batch['text'],'second':'Thanks'})
        c=dict(self.claim,src='second',k='other',family='time_order',raw_text='Keep lunch after demos.',payload={'activities':['lunch','demo'],'relation':'after'})
        result=normalize({'claims':[c],'irrelevant':['synthetic-source'],'ambiguous':[]},batch)
        self.assertEqual(result['claims'][0]['status'],'UNKNOWN')
