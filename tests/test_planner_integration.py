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
