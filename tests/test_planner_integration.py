import json
import unittest
from dataclasses import asdict

from contracts import Extraction
from main import plan_for_cli
from test_plan import claim, fixture


class PlannerIntegrationTests(unittest.TestCase):
    def test_real_planner_state_round_trip_and_rejection(self):
        initial = plan_for_cli({}, Extraction(claims=fixture(), sources={"initial": "pack"}))
        self.assertEqual(initial.status, "VALID")
        saved = json.loads(json.dumps(initial.ledger))
        amendment = claim("food", "vendor_item", "meal", "quantity", 12,
                          src="supplier", kind="reported_action")
        result = plan_for_cli(saved, Extraction(claims=[amendment], sources={"supplier": "update"}))
        self.assertEqual(result.status, "UNVERIFIED")
        self.assertEqual(result.last_valid["status"], "VALID")
        self.assertEqual(result.plan["areas"]["food"]["quantity"], 27)
        self.assertIn("reported 12 items, approved 27 items", result.decisions[0]["reason"])
        json.dumps(asdict(result), allow_nan=False)

    def test_date_header_blocks_stale_cost_update(self):
        initial = plan_for_cli({}, Extraction(claims=fixture(), sources={
            "initial": "From: Finance\nDate: 2026-12-03T10:00:00+05:00\n\nInitial facts"
        }))
        older = claim("budget", "expense", "existing", "committed_cost", 47,
                      src="older", currency="PKR")
        updated = plan_for_cli(initial.ledger, Extraction(claims=[older], sources={
            "older": "From: Finance\nDate: 2026-12-01T10:00:00+05:00\n\nEarlier facts"
        }))
        self.assertEqual(updated.decisions[0]["outcome"], "superseded")
        self.assertEqual(updated.plan["areas"]["budget"]["total"], "377")
