"""Generic regressions for failures exposed by external judge-style packs."""
import unittest
from main import source_dates
from state import apply_update
from test_plan import claim, fixture


class BundleRegressions(unittest.TestCase):
    def test_local_clock_activity_window_is_not_its_duration(self):
        rows = []
        for row in fixture():
            row = dict(row)
            if row['k'] == 'start_time': row['v'] = '10:00'
            if row['k'] == 'end_time': row['v'] = '10:33'
            rows.append(row)
        rows += [claim('schedule', 'event', 'event', 'start_time', '09:00'),
                 claim('schedule', 'event', 'event', 'end_time', '10:33'),
                 claim('schedule', 'activity', 'networking', 'duration_minutes', 13),
                 claim('schedule', 'activity', 'networking', 'availability_window',
                       {'start':'09:05', 'end':'09:45'})]
        plan = apply_update(None, {'claims':rows}).state.plan
        self.assertEqual(plan.status, 'VALID', plan.issues)
        self.assertEqual(plan.areas['schedule']['activities']['networking'],
                         {'start':'09:05', 'end':'09:18'})
        self.assertEqual(plan.areas['schedule']['time_basis'], 'local')

    def test_dietary_portions_replace_regular_meals_and_delivery_counts_once(self):
        rows = [row for row in fixture() if row['k'] != 'quantity']
        rows += [claim('food','event','event','delivery_cost',7,currency='PKR'),
                 claim('food','vendor_item','dietary','unit_price',12,
                       price_basis='per_item',currency='PKR'),
                 claim('food','vendor_item','dietary','meal_fraction',0.17)]
        plan = apply_update(None, {'claims':rows}).state.plan
        self.assertEqual(plan.status, 'VALID', plan.issues)
        self.assertEqual(plan.areas['food']['items'], {'dietary':5, 'meal':20})
        self.assertEqual(plan.areas['food']['quantity'],25)
        self.assertEqual(plan.areas['budget']['total'],'381')
        self.assertEqual(plan.areas['budget']['breakdown']['food'],'247')

    def test_preferred_tier_used_when_affordable_fallback_when_needed(self):
        rows = fixture() + [claim('food','vendor_item','meal','preference_rank',0),
                            claim('food','vendor_item','fallback','preference_rank',1),
                            claim('food','vendor_item','fallback','unit_price',1,
                                  price_basis='per_item',currency='PKR')]
        initial = apply_update(None, {'claims':rows}).state
        self.assertEqual(initial.plan.status,'VALID',initial.plan.issues)
        self.assertEqual(initial.plan.areas['food']['item'],'meal')
        updated = apply_update(initial, {'claims':[
            claim('budget','event','event','budget_cap',200,src='cap',currency='PKR')]}).state
        self.assertEqual(updated.plan.status,'VALID',updated.plan.issues)
        self.assertEqual(updated.plan.areas['food']['item'],'fallback')

    def test_inline_local_dates_supersede_older_fact(self):
        dates = source_dates({'initial':'From: Finance | Date: 2026-11-18 08:00\nLatest facts',
                              'old':'From: Finance | Date: 2026-11-17 12:00\nOld facts'})
        self.assertEqual(len(dates),2)
        initial = apply_update(None, {'claims':fixture(), 'trusted_message_dates':dates}).state
        older = claim('budget','expense','existing','committed_cost',1,src='old',currency='PKR')
        result = apply_update(initial, {'claims':[older], 'trusted_message_dates':dates})
        self.assertEqual(result.decisions[0].outcome,'superseded')
        self.assertEqual(result.state.plan.areas['budget']['total'],'377')

    def test_judge_pool_throughput_reconciled_without_guessing(self):
        rows = fixture()
        for row in rows:
            if row['k'] in {'judge_team_cap','minutes_per_team'}:
                row.update(et='judge',id='m')
        plan = apply_update(None, {'claims':rows}).state.plan
        self.assertEqual(plan.status,'VALID',plan.issues)
        self.assertEqual(plan.areas['budget']['total'],'377')

    def test_unknown_authority_is_not_granted_for_feasible_directive(self):
        initial = apply_update(None, {'claims':fixture()}).state
        change = claim('food','vendor_item','meal','quantity',26,
                       src='stranger',kind='directive')
        result = apply_update(initial, {'claims':[change]})
        self.assertEqual(result.decisions[0].outcome,'unresolved')
        self.assertEqual(result.state.plan,initial.plan)
        self.assertEqual(result.state.active,initial.active)

    def test_numeric_shortage_warning_is_assessed_without_changing_order(self):
        initial = apply_update(None, {'claims':fixture()}).state
        warning = claim('food','vendor_item','meal','quantity',12,src='warning',kind='warning')
        result = apply_update(initial, {'claims':[warning]})
        self.assertEqual(result.state.plan,initial.plan)
        self.assertEqual(result.state.review_issues,())
        self.assertIn('27 meals for 25 attendees',result.decisions[0].reason)

    def test_review_flags_dangling_activities_and_temporal_resource_ids(self):
        from extract import extraction_findings
        findings = extraction_findings({'claims':[
            {'et':'expense','id':'bill','k':'committed_cost','v':3},
            {'et':'expense','id':'bill_old','k':'committed_cost','v':2},
            {'et':'other','id':'order','family':'time_order',
             'payload':{'activities':['briefing','reviews'],'relation':'before'}},
        ]})
        self.assertTrue(any(item['issue']=='dangling activity reference' for item in findings))
        self.assertTrue(any(item['issue']=='possible duplicate temporal resource identity' for item in findings))

    def test_numbered_headers_and_partial_dates_preserve_message_order(self):
        from contracts import InputBatch
        from main import message_sources
        body='#1 | From: Office | Date: 9 Nov\nNew price\n\n#2 | From: Office | Date: 2 Nov\nOld price\n'
        sources=message_sources(InputBatch('pack','messages.txt',body))
        self.assertEqual(len(sources),2)
        self.assertEqual(source_dates(sources),{'pack:1':'--11-09','pack:2':'--11-02'})
        initial=apply_update(None,{'claims':fixture(),'trusted_message_dates':{'initial':'--11-09'}}).state
        old=claim('budget','expense','existing','committed_cost',1,src='old',currency='PKR')
        result=apply_update(initial,{'claims':[old],'trusted_message_dates':{'old':'--11-02'}})
        self.assertEqual(result.decisions[0].outcome,'superseded')

    def test_service_charge_unavailable_venue_and_explicit_area_costs(self):
        rows=fixture()+[
            claim('food','event','event','service_charge_rate',0.1),
            claim('venue','venue_option','cheaper','capacity',40),
            claim('venue','venue_option','cheaper','unit_price',1,price_basis='fixed',currency='PKR'),
            claim('venue','venue_option','cheaper','engagement_rule','unavailable'),
        ]
        plan=apply_update(None,{'claims':rows}).state.plan
        self.assertEqual(plan.status,'VALID',plan.issues)
        self.assertEqual(plan.areas['venue']['option'],'hall')
        self.assertEqual(plan.areas['food']['cost'],'267.3')
        self.assertEqual(plan.areas['judging']['cost'],'36')
        self.assertEqual(plan.areas['venue']['cost'],'55')
        self.assertEqual(plan.areas['budget']['total'],'401.3')
        self.assertTrue(plan.areas['budget']['fits'])

    def test_ground_floor_ramp_matches_step_free_requirement(self):
        rows=fixture()+[
            claim('venue','event','event','required_feature',['step-free access']),
            claim('venue','venue_option','hall','required_feature',['ground-floor ramp access']),
        ]
        plan=apply_update(None,{'claims':rows}).state.plan
        self.assertEqual(plan.status,'VALID',plan.issues)
        from plan import feature_set
        self.assertNotIn('step free access',feature_set(['ramp access']))

    def test_uncommitted_meal_quotes_are_options_without_invented_rules(self):
        rows=[r for r in fixture() if r['k']!='quantity']+[
            claim('food','vendor_item','alternative','unit_price',8,price_basis='per_item',currency='PKR')]
        plan=apply_update(None,{'claims':rows}).state.plan
        self.assertEqual(plan.status,'VALID',plan.issues)
        self.assertEqual(plan.areas['food']['item'],'alternative')
        self.assertEqual(plan.areas['budget']['total'],'334')
