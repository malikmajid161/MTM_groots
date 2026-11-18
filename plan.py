"""Normalize compact claim keys for the first planner slice."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation

AREAS = frozenset(("venue", "schedule", "food", "judging", "budget", "general"))
ENTITY_TYPES = frozenset((
    "venue_option", "vendor_item", "judge", "staff", "expense", "event", "activity"
))
COUNT_KEYS = frozenset((
    "student_count", "team_size", "staff_count", "judge_count", "capacity",
    "quantity", "duration_minutes", "judge_team_cap", "minutes_per_team"
))
PRICE_KEYS = frozenset(("unit_price", "budget_cap", "committed_cost"))
KEYS = COUNT_KEYS | PRICE_KEYS | {
    "start_time", "end_time", "availability_window", "required_feature", "engagement_rule"
}
KINDS = frozenset(("fact", "directive", "proposal", "warning", "reported_action"))


@dataclass(frozen=True)
class Claim:
    source: str
    area: str
    entity_type: str
    entity_id: str
    key: str
    value: object
    scope: str = ""
    currency: str = ""
    kind: str = "fact"
    reason: str = ""
    unit: str = ""

    @property
    def identity(self):
        return self.area, self.entity_type, self.entity_id, self.key, self.scope


def normalize_claim(record):
    """Keep unsupported or incomplete records visible with a reason."""
    source = record.get("src")
    area = record.get("area")
    entity_type = record.get("et")
    entity_id = record.get("id")
    key = record.get("k")
    value = record.get("v")
    scope = record.get("scope", "")
    currency = record.get("currency", "")
    kind = record.get("kind", "fact")
    unit = record.get("u", "")
    reason = ""
    if not all(isinstance(item, str) for item in (
        source, area, entity_type, entity_id, key, scope, currency, kind, unit
    )):
        reason = "missing or invalid claim metadata"
    elif not source or not entity_id or area not in AREAS or entity_type not in ENTITY_TYPES:
        reason = "missing source or unsupported entity or area"
    elif key not in KEYS or kind not in KINDS:
        reason = "unsupported claim key or kind"
    elif record.get("op", "=") != "=":
        reason = "operator requires a constraint evaluator"
    elif key in COUNT_KEYS:
        if type(value) is not int or value < 0:
            reason = "expected a nonnegative integer"
        elif key in {"team_size", "duration_minutes", "minutes_per_team"} and value == 0:
            reason = "expected a positive integer"
    elif key in PRICE_KEYS:
        if key == "unit_price" and scope not in {"fixed", "per_item", "per_person"}:
            reason = "price scope is missing or unsupported"
        if not currency:
            reason = "currency is required"
        try:
            amount = Decimal(str(value))
            if not amount.is_finite() or amount < 0:
                raise InvalidOperation
        except InvalidOperation:
            reason = "expected a finite nonnegative amount"
    elif key == "engagement_rule" and value not in ("required", "optional"):
        reason = "engagement must be required or optional"
    elif key in {"start_time", "end_time"}:
        try:
            stamp = datetime.fromisoformat(value)
            if stamp.utcoffset() is None:
                raise ValueError
        except (TypeError, ValueError):
            reason = "expected an ISO datetime with an explicit offset"
    elif key in {"availability_window", "required_feature"}:
        reason = "claim needs a supported availability or feature evaluator"
    return Claim(source, area, entity_type, entity_id, key, value, scope, currency, kind, reason, unit)

@dataclass(frozen=True)
class Plan:
    status: str
    areas: dict
    issues: tuple = ()


def build_plan(claims):
    """Build a candidate for one event and one explicitly timed judging activity."""
    from datetime import timedelta
    from itertools import combinations

    claims = tuple(claims)
    areas = {area: {} for area in ("venue", "schedule", "food", "judging", "budget")}
    issues = [f"{claim.source}: {claim.reason}" for claim in claims if claim.reason]
    groups = {}
    used = set()

    for claim in claims:
        if claim.reason:
            continue
        key = (claim.entity_type, claim.entity_id)
        group = groups.setdefault(key, {})
        if claim.key in group:
            issues.append(f"{claim.source}: multiple scopes for {claim.key} on {claim.entity_id}")
        group[claim.key] = claim

    def select(entity_type):
        return [(entity_id, group) for (kind, entity_id), group in groups.items()
                if kind == entity_type]

    def read(group, key, default=None):
        claim = group.get(key)
        if claim is None:
            return default
        used.add(claim.identity)
        return claim.value

    def cost(group, key, quantities):
        value = read(group, key)
        if value is None:
            return None
        claim = group[key]
        multiplier = quantities.get(claim.scope if key == "unit_price" else "")
        if multiplier is None:
            return None
        return claim.currency, Decimal(str(value)) * multiplier

    events = select("event")
    activities = [(entity_id, group) for entity_id, group in select("activity")
                  if any(claim.area == "judging" for claim in group.values())]
    if len(events) != 1 or len(activities) != 1:
        return Plan("UNVERIFIED", areas, tuple(issues + [
            "One event and one explicitly timed judging activity are required by this planner."
        ]))
    _, event = events[0]
    activity_id, activity = activities[0]
    students = read(event, "student_count")
    team_size = read(event, "team_size")
    staff = read(event, "staff_count")
    available = read(event, "judge_count")
    start = read(activity, "start_time")
    end = read(activity, "end_time")
    duration = read(activity, "duration_minutes")
    team_minutes = read(activity, "minutes_per_team")
    judge_cap = read(activity, "judge_team_cap")
    budget = cost(event, "budget_cap", {"": 1})
    if None in (students, team_size, staff, available, start, end, team_minutes, judge_cap, budget):
        return Plan("UNVERIFIED", areas, tuple(issues + [
            "Missing headcount, judging window, throughput or budget data."
        ]))

    start, end = datetime.fromisoformat(start), datetime.fromisoformat(end)
    areas["schedule"] = {"activity": activity_id, "start": start.isoformat(), "end": end.isoformat()}
    teams = (students + team_size - 1) // team_size
    elapsed = end - start
    slots = elapsed // timedelta(minutes=team_minutes)
    if elapsed <= timedelta(0) or (duration is not None and elapsed != timedelta(minutes=duration)):
        return Plan("INFEASIBLE", areas, tuple(issues + ["Judging times contradict the required duration."]))
    if teams > slots:
        issues.append(f"{teams} teams need more than {slots} sequential judging slots")
    judges = select("judge")
    if len(judges) != available:
        issues.append(f"{available} judges reported, {len(judges)} identified")
    required = set()
    judge_prices = {}
    for judge_id, group in judges:
        rule = read(group, "engagement_rule")
        if rule is None:
            issues.append(f"{judge_id}: engagement terms are missing")
        if rule == "required":
            required.add(judge_id)
        judge_prices[judge_id] = cost(group, "unit_price", {
            "fixed": 1, "per_person": 1, "per_item": 1
        })
    currency, limit = budget
    committed = [cost(group, "committed_cost", {"": 1}) for _, group in select("expense")]
    if any(item is None for item in committed):
        issues.append("An expense is missing its committed cost")

    venues, meals = select("venue_option"), select("vendor_item")
    if not venues or not meals:
        issues.append("Venue and meal options are required")
    venue_capacities = {name: read(group, "capacity") for name, group in venues}
    meal_quantities = {name: read(group, "quantity") for name, group in meals}
    for name, value in (*venue_capacities.items(), *meal_quantities.items()):
        if value is None:
            issues.append(f"{name}: a capacity or meal quantity is missing")

    optional = sorted(set(judge_prices) - required)
    assignments_possible = teams <= slots and (teams == 0 or judge_cap > 0)
    if judge_cap:
        minimum = (teams + judge_cap - 1) // judge_cap
    else:
        minimum = 0
    best = None
    for size in range(max(0, minimum - len(required)), len(optional) + 1):
        if not assignments_possible:
            break
        for extra in combinations(optional, size):
            engaged = sorted(required.union(extra))
            people = students + staff + len(engaged)
            for venue_id, venue in venues:
                venue_price = cost(venue, "unit_price", {"fixed": 1, "per_person": people})
                capacity = venue_capacities[venue_id]
                for meal_id, meal in meals:
                    quantity = meal_quantities[meal_id]
                    if quantity is None:
                        continue
                    meal_price = cost(meal, "unit_price", {
                        "fixed": 1, "per_item": quantity, "per_person": quantity
                    })
                    prices = [venue_price, meal_price, *committed,
                              *(judge_prices[judge] for judge in engaged)]
                    if any(item is None or item[0] != currency for item in prices):
                        issues.append(f"{venue_id}/{meal_id}: missing price or mismatched currency")
                        continue
                    if capacity is None or min(capacity, quantity) < people:
                        continue
                    total = sum((amount for _, amount in prices), Decimal(0))
                    rank = (len(engaged), total, venue_id, meal_id, engaged)
                    if total <= limit and (best is None or rank < best):
                        best = rank

    issues.extend(f"{claim.source}: unsupported placement of {claim.key}"
                  for claim in claims if not claim.reason and claim.identity not in used)
    areas["judging"] = {"teams": teams, "available": available}
    areas["budget"] = {"currency": currency, "cap": str(limit)}
    if best is None:
        issues.append("No candidate satisfies the supported headcount, judging and budget checks.")
        return Plan("UNVERIFIED" if len(issues) > 1 else "INFEASIBLE", areas, tuple(dict.fromkeys(issues)))

    _, total, venue_id, meal_id, engaged = best
    assignments = []
    for index in range(teams):
        slot_start = start + timedelta(minutes=index * team_minutes)
        assignments.append({
            "team": index + 1, "judge": engaged[index // judge_cap],
            "start": slot_start.isoformat(),
            "end": (slot_start + timedelta(minutes=team_minutes)).isoformat(),
        })
    people = students + staff + len(engaged)
    areas["venue"] = {"option": venue_id, "people": people, "capacity": venue_capacities[venue_id]}
    areas["food"] = {"item": meal_id, "quantity": meal_quantities[meal_id], "required": people}
    areas["judging"].update(engaged=engaged, assignments=assignments)
    areas["budget"]["total"] = str(total)
    return Plan("UNVERIFIED" if issues else "VALID", areas, tuple(dict.fromkeys(issues)))
