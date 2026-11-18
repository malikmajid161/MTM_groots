import unittest

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
        self.assertEqual(result.state.plan.status, "UNVERIFIED")
        self.assertEqual(result.state.last_valid.status, "VALID")

    def test_verified_directive_checks_scope_then_rolls_back_shortfall(self):
        record = claim("food", "vendor_item", "meal", "quantity", 12,
                       src="change", kind="directive", actor="organizer", u="meals")
        for scopes, outcome, reason in (
            ({}, "unresolved", "Authority could not be verified"),
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
