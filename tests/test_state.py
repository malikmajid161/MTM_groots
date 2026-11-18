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
        self.assertEqual(result.decisions[0].outcome, "unresolved")
        self.assertEqual(result.state.plan.areas["food"]["quantity"], 27)
        self.assertEqual(result.state.plan.status, "UNVERIFIED")
        self.assertEqual(result.state.last_valid.status, "VALID")
