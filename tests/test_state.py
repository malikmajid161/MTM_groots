import json
import contextlib
import io
import tempfile
import unittest
from importlib.util import find_spec
from pathlib import Path

from state import apply_update
from test_plan import claim, fixture


class StateTests(unittest.TestCase):
    def setUp(self):
        self.initial = apply_update(None, {"claims": fixture(), "sources": {"initial": "pack"}}).state

    def test_correction_replaces_committed_cost(self):
        update = claim("budget", "expense", "existing", "committed_cost", 47,
                       src="correction", currency="PKR")
        result = apply_update(self.initial, {"claims": [update], "sources": {"correction": "update"}})
        self.assertEqual(result.state.plan.areas["budget"]["total"], "381")
        self.assertEqual([decision.outcome for decision in result.decisions],
                         ["superseded", "accepted"])
        self.assertEqual(dict(result.state.sources), {"initial": "pack", "correction": "update"})
        self.assertEqual(self.initial.plan.areas["budget"]["total"], "377")

    def test_reported_action_preserves_required_quantity(self):
        record = claim("food", "vendor_item", "meal", "quantity", 12,
                       src="supplier", kind="reported_action")
        result = apply_update(self.initial, {"claims": [record]})
        self.assertEqual(result.decisions[0].outcome, "rejected")
        self.assertIn("reported 12 items, approved 27 items", result.decisions[0].reason)
        self.assertEqual(result.state.plan.areas["food"]["quantity"], 27)
        self.assertEqual(result.state.plan.status, "VALID")
        self.assertEqual(result.state.last_valid.status, "VALID")

    def test_verified_directive_checks_scope_then_rolls_back_shortfall(self):
        record = claim("food", "vendor_item", "meal", "quantity", 12,
                       src="change", kind="directive", actor="organizer", u="meals")
        for scopes, outcome, reason in (
            ({}, "rejected", "Authority could not be verified"),
            ({"change": ["judging"]}, "rejected", "exclude food"),
            ({"change": ["food"]}, "rejected", "Requested 12 meals; current plan requires 25 meals"),
        ):
            with self.subTest(scopes=scopes):
                result = apply_update(self.initial, {"claims": [record], "trusted_scopes": scopes})
                self.assertEqual(result.decisions[0].outcome, outcome)
                self.assertIn(reason, result.decisions[0].reason)
                self.assertEqual(result.state.plan, self.initial.plan)
                self.assertEqual(result.state.active, self.initial.active)

        updated = apply_update(self.initial, {
            "claims": [{**record, "v": 26}], "trusted_scopes": {"change": ["food"]},
        })
        self.assertEqual(updated.state.plan.areas["food"]["quantity"], 26)
        self.assertEqual(updated.decisions[-1].outcome, "accepted")

    def test_trusted_dates_compare_instants_and_flag_retrospective_corrections(self):
        initial = apply_update(None, {
            "claims": fixture(), "trusted_message_dates": {"initial": "2026-11-18T15:00:00+05:00"},
        }).state
        old = claim("venue", "venue_option", "hall", "capacity", 20, src="old")
        date = {"old": "2026-11-18T10:59:00+01:00"}
        result = apply_update(initial, {"claims": [old], "trusted_message_dates": date})
        self.assertEqual(result.decisions[0].outcome, "superseded")
        self.assertIn("10:59:00+01:00 < 2026-11-18T15:00:00+05:00",
                      result.decisions[0].reason)
        self.assertEqual(result.state.plan, initial.plan)
        result = apply_update(initial, {
            "claims": [{**old, "corrects": "initial"}], "trusted_message_dates": date,
        })
        self.assertEqual(result.decisions[0].outcome, "unresolved")
        self.assertEqual(result.state.last_valid, initial.plan)

    def test_unverified_claim_date_does_not_override_caller_context(self):
        initial = apply_update(None, {
            "claims": fixture(), "trusted_message_dates": {"initial": "2026-11-18T15:00:00+05:00"},
        }).state
        record = claim("venue", "venue_option", "hall", "capacity", 20,
                       src="change", message_date="2020-01-01T00:00:00+00:00",
                       message_date_trusted=True)
        result = apply_update(initial, {"claims": [record]})
        self.assertEqual(result.decisions[-1].outcome, "accepted")
        self.assertEqual(result.state.plan.status, "INFEASIBLE")

    @unittest.skipUnless(find_spec("main"), "CLI is on the integration branch")
    def test_shared_contract_json_round_trip_and_unresolved_constraint(self):
        from contracts import Extraction
        from main import plan_for_cli

        initial = plan_for_cli({}, Extraction(claims=fixture()))
        self.assertEqual(initial.status, "VALID")
        ledger = json.loads(json.dumps(initial.ledger))
        constraint = {"src": "update", "modality": "hard", "family": "availability",
                      "payload": {"resource": "m"}}
        result = plan_for_cli(ledger, Extraction(constraints=[constraint]))
        self.assertEqual(result.status, "UNVERIFIED")
        self.assertEqual(result.last_valid["status"], "VALID")
        self.assertEqual(result.ledger["constraints"], (constraint,))
        self.assertEqual(result.decisions[0]["source"], "update")

    @unittest.skipUnless(find_spec("main"), "CLI is on the integration branch")
    def test_cli_persists_accepted_fact_and_separate_last_valid_plan(self):
        from contracts import Extraction
        from main import plan_for_cli, run

        def extract(batch, ledger, budget, record):
            if not ledger:
                return Extraction(claims=fixture())
            return Extraction(claims=[
                claim("venue", "venue_option", "hall", "capacity", 24, src=batch.source_id)
            ])

        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            root = Path(directory)
            file = root / "input.txt"
            runtime = root / "runtime"
            file.write_text("initial", encoding="utf-8")
            self.assertEqual(run(file, runtime, extract, plan_for_cli), 0)
            file.write_text("credible venue capacity reduction", encoding="utf-8")
            self.assertEqual(run(file, runtime, extract, plan_for_cli), 0)
            saved = json.loads((runtime / "session.json").read_text(encoding="utf-8"))["result"]
            self.assertEqual(saved["status"], "INFEASIBLE")
            self.assertEqual(saved["last_valid"]["areas"]["venue"]["capacity"], 26)
            capacity = next(item for item in saved["ledger"]["active"] if item["k"] == "capacity")
            self.assertEqual(capacity["v"], 24)

    def test_explicit_constraint_correction_replaces_only_its_target(self):
        first = {'src': 'limits', 'claim_id': 'limit-1', 'family': 'cost_cap',
                 'modality': 'hard', 'payload': {'cost_refs': ['food'], 'cap': 245, 'currency': 'PKR'}}
        initial = apply_update(self.initial, {'constraints': [first]}).state
        corrected = {**first, 'src': 'correction', 'claim_id': 'limit-2', 'correction_target': 'limit-1',
                     'payload': {**first['payload'], 'cap': 250}}
        updated = apply_update(initial, {'constraints': [corrected]}).state
        self.assertEqual(updated.constraints, (corrected,))
        self.assertEqual(updated.plan.status, 'VALID')
        bad = {**corrected, 'kind': 'directive', 'src': 'stranger', 'correction_target': 'limit-2'}
        result = apply_update(updated, {'constraints': [bad]})
        self.assertEqual(result.state.constraints, (corrected,))
        self.assertEqual(result.decisions[0].outcome, 'unresolved')

    def test_explicit_correction_can_resolve_unknown_record_without_erasing_audit(self):
        unknown = claim('budget', 'expense', 'unknown', 'committed_cost', 'NaN',
                        src='bad', claim_id='bad:1', currency='PKR')
        broken = apply_update(self.initial, {'claims': [unknown]}).state
        self.assertEqual(broken.plan.status, 'UNVERIFIED')
        corrected = {**unknown, 'src': 'fix', 'claim_id': 'fix:1', 'v': 0,
                     'correction_target': 'bad:1'}
        fixed = apply_update(broken, {'claims': [corrected]}).state
        self.assertEqual(fixed.plan.status, 'VALID', fixed.plan.issues)
        self.assertEqual(fixed.review_records, ())
        self.assertIn(unknown, fixed.history)
        self.assertTrue(any('Review resolved' in item.reason for item in fixed.decisions))
