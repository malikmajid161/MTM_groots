import unittest

from plan import normalize_claim
from state import apply_update


def claim(area, entity, name, key, value, **metadata):
    return {"src": "initial", "area": area, "et": entity, "id": name,
            "k": key, "v": value, **metadata}


def fixture():
    def event(key, value, **metadata):
        return claim("general", "event", "event", key, value, **metadata)

    def judging(key, value):
        return claim("judging", "activity", "reviews", key, value)

    def price(area, entity, name, value, scope="fixed"):
        return claim(area, entity, name, "unit_price", value, scope=scope, currency="PKR")

    return [
        event("student_count", 21), event("team_size", 7), event("staff_count", 2),
        event("judge_count", 2), event("budget_cap", "1000", currency="PKR"),
        judging("start_time", "2026-12-01T10:00:00+05:00"),
        judging("end_time", "2026-12-01T10:33:00+05:00"),
        judging("duration_minutes", 33), judging("minutes_per_team", 11),
        judging("judge_team_cap", 2),
        claim("judging", "judge", "m", "engagement_rule", "required"),
        claim("judging", "judge", "n", "engagement_rule", "optional"),
        price("judging", "judge", "m", 17), price("judging", "judge", "n", 19),
        claim("venue", "venue_option", "hall", "capacity", 26),
        price("venue", "venue_option", "hall", 55),
        claim("food", "vendor_item", "meal", "quantity", 27),
        price("food", "vendor_item", "meal", 9, "per_item"),
        claim("budget", "expense", "existing", "committed_cost", 43, currency="PKR"),
    ]


class PlannerTests(unittest.TestCase):
    def test_five_areas_and_independent_totals(self):
        plan = apply_update(None, {"claims": fixture()}).state.plan
        self.assertEqual(plan.status, "VALID", plan.issues)
        self.assertEqual(set(plan.areas), {"venue", "schedule", "food", "judging", "budget"})
        self.assertEqual(plan.areas["venue"]["people"], 25)
        self.assertEqual(plan.areas["food"]["quantity"], 27)
        self.assertEqual(plan.areas["budget"]["total"], "377")
        slots = plan.areas["judging"]["assignments"]
        self.assertEqual([row["judge"] for row in slots], ["m", "m", "n"])
        self.assertEqual(slots[0]["end"], slots[1]["start"])
        self.assertEqual(slots[-1]["end"], plan.areas["schedule"]["end"])

    def test_invalid_amount_and_engagement_need_review(self):
        self.assertTrue(normalize_claim(claim("budget", "expense", "x", "committed_cost",
                                              "NaN", currency="PKR")).reason)
        self.assertTrue(normalize_claim(claim("judging", "judge", "m", "engagement_rule",
                                              "confirmed")).reason)

    def test_capacity_and_meals_are_hard_bounds(self):
        initial = apply_update(None, {"claims": fixture()}).state
        for area, entity, name, key in (("venue", "venue_option", "hall", "capacity"),
                                        ("food", "vendor_item", "meal", "quantity")):
            with self.subTest(area=area):
                new = claim(area, entity, name, key, 24, src="update")
                state = apply_update(initial, {"claims": [new]}).state
                self.assertEqual(state.plan.status, "INFEASIBLE", state.plan.issues)
                self.assertIn(new, state.active)
                self.assertEqual(state.last_valid, initial.plan)

    def test_venue_feature_and_late_judge(self):
        records = fixture() + [
            claim("venue", "event", "event", "required_feature", "Ramp"),
            claim("venue", "venue_option", "hall", "required_feature", ["ramp"]),
            claim("judging", "judge", "n", "availability_window", {
                "start": "2026-12-01T10:22:00+05:00",
                "end": "2026-12-01T10:33:00+05:00",
            }),
        ]
        result = apply_update(None, {"claims": records}).state.plan
        self.assertEqual(result.status, "VALID", result.issues)
        slots = result.areas["judging"]["assignments"]
        self.assertEqual(slots[-1]["judge"], "n")
        self.assertEqual(slots[-1]["start"], "2026-12-01T10:22:00+05:00")
        records.pop(-2)
        unknown = apply_update(None, {"claims": records}).state.plan
        self.assertEqual(unknown.status, "UNVERIFIED")
        self.assertTrue(any("required venue features are unverified" in issue for issue in unknown.issues))

    def test_required_features_distinguish_unknown_from_absence(self):
        base = fixture() + [claim("general", "event", "event", "required_feature", ["lift"])]
        result = apply_update(None, {"claims": base}).state
        self.assertEqual(result.plan.status, "UNVERIFIED")
        for features, expected in [([], "INFEASIBLE"), (["lift"], "VALID")]:
            with self.subTest(features=features):
                options = base + [claim("venue", "venue_option", "hall", "required_feature", features)]
                self.assertEqual(apply_update(None, {"claims": options}).state.plan.status, expected)

    def test_required_meal_is_retained_when_cheaper_meal_exists(self):
        base = fixture() + [
            claim("food", "vendor_item", "meal", "engagement_rule", "required"),
            claim("food", "vendor_item", "alternative", "engagement_rule", "optional"),
            claim("food", "vendor_item", "alternative", "quantity", 25),
            claim("food", "vendor_item", "alternative", "unit_price", 1,
                  price_basis="per_item", currency="PKR"),
        ]
        plan = apply_update(None, {"claims": base}).state.plan
        self.assertEqual(plan.status, "VALID", plan.issues)
        self.assertEqual(plan.areas["food"]["item"], "meal")
