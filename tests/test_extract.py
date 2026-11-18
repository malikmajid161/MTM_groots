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

    def test_real_client_requests_generic_schema_without_replacing_explicit_format(self):
        payloads=[]
        def transport(endpoint,key,payload,timeout):
            payloads.append(payload)
            return {'choices':[{'message':{'content':json.dumps({'claims':[self.claim],'irrelevant':[],'ambiguous':[]})}}]}
        client=ModelClient('https://example.invalid','mock','s',transport=transport)
        extract(self.batch,{},RunBudget(),TraceRecorder(),client)
        schema=payloads[-1]['response_format']['json_schema']['schema']
        self.assertIn('currency',schema['properties']['claims']['items']['required'])
        self.assertFalse(payloads[-1]['stream'])
        client=ModelClient('https://example.invalid','mock','s',transport=transport,request_options={'response_format':{'type':'json_object'}})
        extract(self.batch,{},RunBudget(),TraceRecorder(),client)
        self.assertEqual(payloads[-1]['response_format'],{'type':'json_object'})

    def test_committed_cost_is_total_without_invented_unit_price_basis(self):
        c=dict(self.claim,k='committed_cost',et='expense',area='budget')
        c.pop('price_basis')
        self.assertEqual(self.normalized(c)['status'],'PENDING_VALIDATION')
        c['k']='unit_price'
        self.assertEqual(self.normalized(c)['status'],'UNKNOWN')

    def test_short_wire_sources_round_trip_to_full_local_ids(self):
        payloads=[]
        batch=dict(self.batch,messages={'very-long-original-source-one':self.batch['text'],'very-long-original-source-two':'Thanks'})
        def transport(endpoint,key,payload,timeout):
            payloads.append(json.loads(payload['messages'][-1]['content']))
            c=dict(self.claim,src='s1')
            return {'choices':[{'message':{'content':json.dumps({'claims':[c],'irrelevant':['s2'],'ambiguous':[]})}}]}
        result=extract(batch,{},RunBudget(),TraceRecorder(),ModelClient('https://example.invalid','mock','s',transport=transport))
        self.assertEqual(set(payloads[0]['messages']),{'s1','s2'})
        self.assertEqual(result['claims'][0]['src'],'very-long-original-source-one')
        self.assertEqual(result['irrelevant'],['very-long-original-source-two'])
        self.assertFalse(result['ambiguous'])

    def test_strict_metadata_cannot_replace_source_or_core_values(self):
        result=normalize({'claims':[dict(self.claim,metadata_json='{"src":"forged"}')],'irrelevant':[],'ambiguous':[]},self.batch)
        self.assertFalse(result['claims'])
        self.assertTrue(result['ambiguous'])

    def test_empty_optional_metadata_means_no_metadata(self):
        c=dict(self.claim,metadata_json='')
        self.assertEqual(self.normalized(c)['status'],'PENDING_VALIDATION')

    def test_schema_aliases_do_not_leak_between_reused_client_calls(self):
        sent=[]
        def transport(endpoint,key,payload,timeout):
            sent.append(payload['response_format']['json_schema']['schema']['properties']['claims']['items']['properties']['src']['enum'])
            return {'choices':[{'message':{'content':json.dumps({'claims':[],'irrelevant':['s1'],'ambiguous':[]})}}]}
        client=ModelClient('https://example.invalid','mock','s',transport=transport)
        extract(self.batch,{},RunBudget(),TraceRecorder(),client)
        multi=dict(self.batch,messages={'one':'Hello','two':'Thanks'})
        extract(multi,{},RunBudget(),TraceRecorder(),client)
        self.assertEqual(sent,[['s1'],['s1','s2']])
        self.assertNotIn('response_format',client.request_options)

    def test_context_references_compact_and_metadata_references_restored(self):
        context={'active_claims':[dict(self.claim,src='prior-source-hash',claim_id='prior-claim-hash')]}
        def transport(endpoint,key,payload,timeout):
            wire=json.loads(payload['messages'][-1]['content'])
            previous=wire['context']['active_claims'][0]
            self.assertNotEqual(previous['src'],'prior-source-hash')
            self.assertNotEqual(previous['claim_id'],'prior-claim-hash')
            c=dict(self.claim,src='s1',metadata_json=json.dumps({'correction_target':{'src':previous['src']},'supersedes':[previous['claim_id']]}))
            return {'choices':[{'message':{'content':json.dumps({'claims':[c],'irrelevant':[],'ambiguous':[]})}}]}
        result=extract(self.batch,context,RunBudget(),TraceRecorder(),ModelClient('https://example.invalid','mock','s',transport=transport))
        c=result['claims'][0]
        self.assertEqual(c['correction_target']['src'],'prior-source-hash')
        self.assertEqual(c['supersedes'],['prior-claim-hash'])
        self.assertEqual(context['active_claims'][0]['src'],'prior-source-hash')

    def test_scalar_correction_alias_restores_active_claim_id(self):
        context={'active_claims':[dict(self.claim,src='prior-source',claim_id='prior-claim')]}
        def transport(endpoint,key,payload,timeout):
            previous=json.loads(payload['messages'][-1]['content'])['context']['active_claims'][0]
            c=dict(self.claim,src='s1',metadata_json=json.dumps({'correction_target':previous['claim_id']}))
            return {'choices':[{'message':{'content':json.dumps({'claims':[c],'irrelevant':[],'ambiguous':[]})}}]}
        result=extract(self.batch,context,RunBudget(),TraceRecorder(),ModelClient('https://example.invalid','mock','s',transport=transport))
        self.assertEqual(result['claims'][0]['correction_target'],'prior-claim')

    def test_schema_forbids_add_assignment_operator(self):
        from extract import strict_extraction_schema
        operators=strict_extraction_schema()['properties']['claims']['items']['properties']['op']['enum']
        self.assertIn('=',operators)
        self.assertNotIn('+=',operators)
        self.assertEqual(self.normalized(dict(self.claim,op='+='))['status'],'UNKNOWN')

    def test_optional_review_is_recorded_and_replaces_draft(self):
        from unittest.mock import patch
        seen = []
        def transport(endpoint, key, payload, timeout):
            seen.append(payload)
            value = 941 if len(seen) == 1 else 940
            row = dict(self.claim, src='s1', v=value)
            return {'choices':[{'message':{'content':json.dumps({'claims':[row], 'irrelevant':[], 'ambiguous':[]})}}],
                    'usage':{'total_tokens':17}}
        budget, trace = RunBudget(), TraceRecorder()
        client = ModelClient('https://example.invalid', 'mock', 'secret', transport=transport)
        with patch.dict('os.environ', {'MODEL_VERIFY_EXTRACTION':'1'}):
            result = extract(self.batch, {}, budget, trace, client)
        self.assertEqual(result['claims'][0]['v'], 940)
        self.assertEqual(len(seen), 2)
        self.assertIn('draft_extraction', json.loads(seen[1]['messages'][1]['content']))
        self.assertEqual(budget.attempts, 2)
        self.assertEqual(len(trace.records), 2)
