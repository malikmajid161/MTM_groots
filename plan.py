"""Normalize compact claim keys for the first planner slice."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from itertools import combinations
from operator import eq, ge, gt, le, lt, ne

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
    price_basis: str = ""

    @property
    def identity(self):
        return self.area, self.entity_type, self.entity_id, self.key, self.scope


def feature_set(value):
    names = [value] if isinstance(value, str) else value
    if not isinstance(names, (list, tuple)) or not names:
        return set()
    if any(not isinstance(name, str) or not name.strip() for name in names):
        return set()
    return {name.strip().casefold() for name in names}


def parse_window(value):
    if not isinstance(value, dict):
        return None
    start = datetime.fromisoformat(value.get("start"))
    end = datetime.fromisoformat(value.get("end"))
    if start.utcoffset() is None or end.utcoffset() is None or start >= end:
        return None
    return start, end


def assign_slots(engaged, slots, cap, windows, teams):
    if not any(windows[judge] for judge in engaged):
        return [(index, engaged[index // cap]) for index in range(teams)]
    seats = [(judge, index) for judge in engaged for index in range(min(cap, len(slots)))]
    occupied = {}

    def assign(index, visited):
        start, end = slots[index]
        for seat in seats:
            window = windows[seat[0]]
            if seat in visited or (window and not (window[0] <= start and end <= window[1])):
                continue
            visited.add(seat)
            if seat not in occupied or assign(occupied[seat], visited):
                occupied[seat] = index
                return True
        return False

    for index in range(len(slots)):
        if len(occupied) == teams:
            break
        assign(index, set())
    if len(occupied) != teams:
        return None
    return sorted((index, judge) for (judge, _), index in occupied.items())


def normalize_claim(record):
    """Keep unsupported or incomplete records visible with a reason."""
    source = record.get("src")
    area = record.get("area")
    entity_type = record.get("et")
    entity_id = record.get("id")
    key = record.get("k")
    value = record.get("v")
    scope = record.get("scope", "")
    price_basis = record.get("price_basis", record.get("price_scope", scope))
    currency = record.get("currency", "")
    kind = record.get("kind", "fact")
    unit = record.get("u", "")
    reason = ""
    if not all(isinstance(item, str) for item in (
        source, area, entity_type, entity_id, key, scope, price_basis, currency, kind, unit
    )):
        reason = "missing or invalid claim metadata"
    elif not source or not entity_id or area not in AREAS or entity_type not in ENTITY_TYPES:
        reason = "missing source or unsupported entity or area"
    elif key not in KEYS or kind not in KINDS:
        reason = "unsupported claim key or kind"
    elif record.get("status") == "UNKNOWN":
        reason = record.get("issue") or "extraction marked the claim unknown"
    elif record.get("effective_period"):
        reason = "effective periods require explicit plan-time evaluation"
    elif record.get("op") not in (None, "=", "=="):
        reason = "operator requires a constraint evaluator"
    elif key in COUNT_KEYS:
        if type(value) is not int or value < 0:
            reason = "expected a nonnegative integer"
        elif key in {"team_size", "duration_minutes", "minutes_per_team"} and value == 0:
            reason = "expected a positive integer"
    elif key in PRICE_KEYS:
        if key == "unit_price" and price_basis not in {"fixed", "per_item", "per_person"}:
            reason = "price scope is missing or unsupported"
        if key == "committed_cost" and price_basis not in {"", "fixed"}:
            reason = "committed cost needs a fixed total"
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
    elif key == "required_feature":
        if entity_type not in {"event", "venue_option"} or (not feature_set(value) and value != []):
            reason = "expected venue feature names on an event or venue"
    elif key == "availability_window":
        try:
            if entity_type not in {"judge", "venue_option"} or not parse_window(value):
                raise ValueError
        except (TypeError, ValueError):
            reason = "expected offset-aware judge or venue availability bounds"
    identity_scope = scope if scope not in ("fixed", "per_item", "per_person") else ""
    return Claim(source, area, entity_type, entity_id, key, value, identity_scope, currency, kind,
                 reason, unit, price_basis)

@dataclass(frozen=True)
class Plan:
    status: str
    areas: dict
    issues: tuple = ()


COMPARISONS = {"=": eq, "==": eq, "!=": ne, ">=": ge, ">": gt, "<=": le, "<": lt}
ROUNDING = {"ceil": ROUND_CEILING, "floor": ROUND_FLOOR, "nearest": ROUND_HALF_UP}


def nonnegative_amount(value):
    amount = Decimal(str(value))
    if not amount.is_finite() or amount < 0:
        raise ValueError("Expected a finite nonnegative value")
    return amount


def constraint_check(constraint, counts, costs, currency, intervals):
    """Evaluate only references and units the candidate can prove."""
    family = constraint.get("family")
    try:
        payload = constraint["payload"]
        if family == "count_bound":
            count, unit = counts[payload["target"]]
            bound = payload["bound"]
            if unit == payload["unit"] and type(bound) is int and bound >= 0:
                return COMPARISONS[payload["op"]](count, bound)
        elif family == "cost_cap":
            refs = payload["cost_refs"]
            if (payload["currency"] == currency and isinstance(refs, list) and refs
                    and len(set(refs)) == len(refs)):
                return sum(costs[ref] for ref in refs) <= nonnegative_amount(payload["cap"])
        elif family == "percentage_uplift":
            base, base_unit = counts[payload["base"]]
            target, unit = counts[payload["target"]]
            factor = nonnegative_amount(payload["rate"])
            if payload["mode"] == "increase":
                factor += 1
            elif payload["mode"] != "share":
                return None
            if base_unit == unit == payload["unit"]:
                minimum = (base * factor).to_integral_value(rounding=ROUNDING[payload["rounding"]])
                return target >= minimum
        elif family == "time_order":
            left, right = payload["activities"]
            first, second = intervals[left], intervals[right]
            relation = payload["relation"]
            if set(payload) != {"activities", "relation"}:
                return None
            if relation == "before":
                return first[1] <= second[0]
            if relation == "after":
                return second[1] <= first[0]
            if relation == "non_overlap":
                return first[1] <= second[0] or second[1] <= first[0]
        elif family == "availability":
            if payload["time_basis"] != "absolute":
                return None
            bookings = intervals.get(payload["resource"])
            if bookings is None:
                return None
            windows = [parse_window(window) for window in payload["windows"]]
            if windows and all(windows):
                # The search handles canonical windows. An unplaced typed
                # window cannot prove infeasibility for alternate assignments.
                return True if any(a <= bookings[0] and bookings[1] <= b for a, b in windows) else None
    except (KeyError, TypeError, ValueError, ArithmeticError):
        return None
    return None


def build_plan(claims, constraints=()):
    """Build a candidate for one event and one explicitly timed judging activity."""
    from datetime import timedelta

    claims = tuple(claims)
    areas = {area: {} for area in ("venue", "schedule", "food", "judging", "budget")}
    issues = [f"{claim.source}: {claim.reason}" for claim in claims if claim.reason]
    hard_constraints = [item for item in constraints if item.get("modality") != "soft"]
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
        multiplier = quantities.get(claim.price_basis if key == "unit_price" else "")
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
    intervals = {activity_id: (start, end)}
    for name, group in select("activity"):
        if name == activity_id:
            continue
        begin, finish = read(group, "start_time"), read(group, "end_time")
        length = read(group, "duration_minutes")
        if begin is None or finish is None:
            issues.append(f"{name}: fixed activity requires start and end times")
            continue
        begin, finish = datetime.fromisoformat(begin), datetime.fromisoformat(finish)
        if finish <= begin or (length is not None and finish - begin != timedelta(minutes=length)):
            return Plan("INFEASIBLE", areas, tuple(issues + [f"{name}: activity times contradict duration"]))
        intervals[name] = (begin, finish)
    if len(intervals) > 1:
        areas["schedule"]["activities"] = {
            name: {"start": begin.isoformat(), "end": finish.isoformat()}
            for name, (begin, finish) in intervals.items()
        }
    event_start = min(begin for begin, _ in intervals.values())
    event_end = max(finish for _, finish in intervals.values())
    teams = (students + team_size - 1) // team_size
    if teams > 10_000:
        return Plan("UNVERIFIED", areas, tuple(issues + ["Explicit team assignment limit exceeded."]))
    elapsed = end - start
    slots = elapsed // timedelta(minutes=team_minutes)
    if elapsed <= timedelta(0) or (duration is not None and elapsed != timedelta(minutes=duration)):
        return Plan("INFEASIBLE", areas, tuple(issues + ["Judging times contradict the required duration."]))
    if teams > slots:
        issues.append(f"{teams} teams need more than {slots} supported sequential judging slots")
    judges = select("judge")
    if len(judges) != available:
        issues.append(f"{available} judges reported, {len(judges)} identified")
    required = set()
    judge_prices = {}
    judge_windows = {}
    for judge_id, group in judges:
        rule = read(group, "engagement_rule")
        if rule is None:
            issues.append(f"{judge_id}: engagement terms are missing")
        if rule == "required":
            required.add(judge_id)
        judge_windows[judge_id] = parse_window(read(group, "availability_window"))
        judge_prices[judge_id] = cost(group, "unit_price", {
            "fixed": 1, "per_person": 1, "per_item": 1
        })
    currency, limit = budget
    committed = [cost(group, "committed_cost", {"": 1}) for _, group in select("expense")]
    if any(item is None for item in committed):
        issues.append("An expense is missing its committed cost")
    extras = {}
    expense_ids = {name for name, _ in select("expense")}
    checks = []
    for constraint in hard_constraints:
        if constraint.get("family") != "priced_extra":
            checks.append(constraint)
            continue
        try:
            payload = constraint["payload"]
            item, required_extra, quantity = (payload[key] for key in ("item", "required", "quantity"))
            basis = payload["price_basis"]
            if (not isinstance(item, str) or not item or type(required_extra) is not bool
                    or type(quantity) is not int or quantity < 0 or payload["currency"] != currency
                    or basis not in {"fixed", "per_item", "per_person"}):
                raise ValueError
            if not required_extra:
                continue
            amount = nonnegative_amount(payload["price"]) * (1 if basis == "fixed" else quantity)
            if item in expense_ids or payload.get("available") is not True:
                raise ValueError
            if item in extras and extras[item] != amount:
                raise ValueError
            extras[item] = amount
        except (KeyError, TypeError, ValueError, ArithmeticError):
            issues.append(f"{constraint.get('src')}: priced extra cost or availability is unverified")

    venues, meals = select("venue_option"), select("vendor_item")
    if not venues or not meals:
        issues.append("Venue and meal options are required")
    venue_capacities = {name: read(group, "capacity") for name, group in venues}
    meal_quantities = {name: read(group, "quantity") for name, group in meals}
    for _, option in (*venues, *meals):
        read(option, "unit_price")
    meal_rules = {name: read(group, "engagement_rule") for name, group in meals}
    required_meals = {name for name, rule in meal_rules.items() if rule == "required"}
    if len(required_meals) > 1:
        issues.append("Multiple required meal items need an explicit multi-item plan")
    elif len(meals) > 1 and not required_meals and any(rule is None for rule in meal_rules.values()):
        issues.append("Meal substitution terms are missing")
    for name, value in (*venue_capacities.items(), *meal_quantities.items()):
        if value is None:
            issues.append(f"{name}: a capacity or meal quantity is missing")

    required_features = feature_set(read(event, "required_feature"))
    venue_features = {name: read(group, "required_feature") for name, group in venues}
    venue_windows = {name: parse_window(read(group, "availability_window")) for name, group in venues}
    def usable_price(judge):
        price = judge_prices[judge]
        return price is not None and price[0] == currency

    optional = sorted(
        (judge for judge in set(judge_prices) - required if usable_price(judge)),
        key=lambda judge: (judge_prices[judge][1], judge),
    )
    step = timedelta(minutes=team_minutes)
    if slots > 10_000:
        return Plan("UNVERIFIED", areas, tuple(issues + ["Judging slot search exceeds the supported range."]))
    judging_slots = [(start + i * step, start + (i + 1) * step) for i in range(slots)]
    best_assignments = []
    assignments_possible = teams <= slots and (teams == 0 or judge_cap > 0)
    if judge_cap:
        minimum = (teams + judge_cap - 1) // judge_cap
    else:
        minimum = 0
    needed_optional = max(0, minimum - len(required))
    if any(not usable_price(judge) for judge in required) or (
        needed_optional and len(optional) != len(judges) - len(required)
    ):
        issues.append("A potentially needed judge has missing or incompatible price data")
    best = None
    if not assignments_possible or len(optional) < needed_optional:
        groups_to_try = ()
    elif not any(judge_windows.values()) and not checks:
        groups_to_try = (iter((optional[:needed_optional],)),)
    else:
        groups_to_try = (
            combinations(optional, size) for size in range(needed_optional, len(optional) + 1)
        )
    attempts = 0
    selected_unknown = ()
    failures = set()
    grid_incomplete = False
    for groups_at_size in groups_to_try:
        for extra in groups_at_size:
            attempts += 1
            if attempts > 10_000:
                return Plan("UNVERIFIED", areas, tuple(issues + ["Judge group search limit reached."]))
            engaged = sorted(required.union(extra))
            try:
                assigned = assign_slots(engaged, judging_slots, judge_cap, judge_windows, teams)
            except RecursionError:
                return Plan("UNVERIFIED", areas, tuple(issues + ["Judge matching depth limit reached."]))
            if assigned is None:
                grid_incomplete |= any(judge_windows[judge] for judge in engaged)
                continue
            people = students + staff + len(engaged)
            for venue_id, venue in venues:
                features = venue_features[venue_id]
                if required_features and features is None:
                    issues.append(f"{venue_id}: required venue features are unverified")
                    continue
                if not required_features <= feature_set(features):
                    continue
                window = venue_windows[venue_id]
                if window and not (window[0] <= event_start and event_end <= window[1]):
                    continue
                venue_price = cost(venue, "unit_price", {"fixed": 1, "per_person": people})
                capacity = venue_capacities[venue_id]
                for meal_id, meal in meals:
                    quantity = meal_quantities[meal_id]
                    if quantity is None or (required_meals and required_meals != {meal_id}):
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
                    costs = {
                        "venue": venue_price[1], "food": meal_price[1],
                        "judging": sum(judge_prices[judge][1] for judge in engaged),
                        "committed": sum(amount for _, amount in committed),
                        "extras": sum(extras.values()),
                    }
                    total = sum(costs.values())
                    counts = {
                        "people": (people, "people"), "seats": (capacity, "seats"),
                        "students": (students, "people"), "teams": (teams, "teams"),
                        "judges": (len(engaged), "judges"), "meals": (quantity, "meals"),
                    }
                    bookings = dict(intervals)
                    if venue_id not in intervals:
                        bookings[venue_id] = (event_start, event_end)
                    unknown = []
                    failed = False
                    for constraint in checks:
                        status = constraint_check(constraint, counts, costs, currency, bookings)
                        label = f"{constraint.get('src')}: {constraint.get('family', 'constraint')}"
                        if status is None:
                            unknown.append(f"{label} could not be verified")
                        elif not status:
                            failures.add(f"{label} failed")
                            failed = True
                    if failed:
                        continue
                    rank = (bool(unknown), len(engaged), total, venue_id, meal_id, engaged)
                    if total <= limit and (best is None or rank < best):
                        best = rank
                        best_assignments = assigned
                        selected_unknown = tuple(unknown)
        if best is not None and not selected_unknown:
            break

    issues.extend(f"{claim.source}: unsupported placement of {claim.key}"
                  for claim in claims if not claim.reason and claim.identity not in used)
    areas["judging"] = {"teams": teams, "available": available}
    areas["budget"] = {"currency": currency, "cap": str(limit)}
    if best is None:
        if grid_incomplete:
            issues.append("No assignment on the supported fixed grid for one or more judge groups")
        status = "UNVERIFIED" if issues else "INFEASIBLE"
        issues.extend(sorted(failures))
        issues.append("No candidate satisfies the supported headcount, judging and budget checks.")
        return Plan(status, areas, tuple(dict.fromkeys(issues)))

    _, _, total, venue_id, meal_id, engaged = best
    issues.extend(selected_unknown)
    assignments = []
    for index, (slot, judge) in enumerate(best_assignments):
        slot_start, slot_end = judging_slots[slot]
        assignments.append({
            "team": index + 1, "judge": judge,
            "start": slot_start.isoformat(),
            "end": slot_end.isoformat(),
        })
    people = students + staff + len(engaged)
    areas["venue"] = {"option": venue_id, "people": people, "capacity": venue_capacities[venue_id]}
    areas["food"] = {"item": meal_id, "quantity": meal_quantities[meal_id], "required": people}
    areas["judging"].update(engaged=engaged, assignments=assignments)
    areas["budget"]["total"] = str(total)
    if extras:
        areas["budget"]["extras"] = {item: str(amount) for item, amount in extras.items()}
    return Plan("UNVERIFIED" if issues else "VALID", areas, tuple(dict.fromkeys(issues)))
