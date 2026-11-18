"""Apply normalized updates and retain source decisions and the last valid plan."""

from dataclasses import dataclass, replace
from datetime import datetime

from plan import Plan, build_plan, normalize_claim


@dataclass(frozen=True)
class Decision:
    source: str
    outcome: str
    reason: str


@dataclass(frozen=True)
class State:
    active: tuple = ()
    sources: tuple = ()
    history: tuple = ()
    decisions: tuple = ()
    plan: Plan | None = None
    last_valid: Plan | None = None
    review_issues: tuple = ()
    message_dates: tuple = ()
    constraints: tuple = ()
    review_records: tuple = ()


@dataclass(frozen=True)
class UpdateResult:
    state: State
    decisions: tuple
    affected_areas: tuple


DEPENDENCIES = {
    "general": {"venue", "schedule", "food", "judging", "budget"},
    "venue": {"venue", "budget"},
    "schedule": {"schedule", "judging", "budget"},
    "food": {"food", "budget"},
    "judging": {"judging", "schedule", "venue", "food", "budget"},
    "budget": {"venue", "food", "judging", "budget"},
}


def parse_message_date(value):
    try:
        date = datetime.fromisoformat(value)
        return date
    except (TypeError, ValueError):
        return None


def apply_update(state, extraction):
    """Apply compact normalized claims with externally verified source context.

    The planner expects trusted_scopes and trusted_message_dates to
    come from the input envelope supplied by the caller.
    """
    state = State() if state is None else state
    active = {normalize_claim(record).identity: record for record in state.active}
    sources = dict(state.sources)
    dates = dict(state.message_dates)
    for source, raw_date in extraction.get("trusted_message_dates", {}).items():
        date = parse_message_date(raw_date)
        if date is not None:
            dates.setdefault(source, date.isoformat())
    history = list(state.history)
    decisions = []
    affected = set()
    blocking = []
    pending = list(state.review_records)
    resolved_issues = set()
    constraints = list(state.constraints)
    claims = []
    incoming_constraints = list(extraction.get("constraints", ()))
    for record in extraction.get("claims", ()):
        if (record.get("k") in (None, "other") and isinstance(record.get("payload"), dict)
                and record.get("status") != "UNKNOWN" and record.get("kind", "fact") == "fact"):
            incoming_constraints.append(record)
        else:
            claims.append(record)
    new_constraints = []
    for constraint in incoming_constraints:
        source = constraint.get("src") or "(missing source)"
        if constraint.get("kind", "fact") != "fact":
            decisions.append(Decision(source, "unresolved", "Constraint amendments require verified authority"))
            blocking.append(f"{source}: constraint authority could not be verified")
            continue
        target = constraint.get("correction_target")
        if isinstance(target, dict):
            target = target.get("claim_id")
        previous = next((item for item in constraints if target and item.get("claim_id") == target), None)
        if target and previous is None:
            decisions.append(Decision(source, "unresolved", "Constraint correction target does not match"))
            blocking.append(f"{source}: constraint correction target does not match")
            continue
        if previous is not None:
            older, newer = parse_message_date(dates.get(source)), parse_message_date(dates.get(previous.get("src")))
            if older is not None and newer is not None and (older.utcoffset() is None) == (newer.utcoffset() is None) and older < newer:
                decisions.append(Decision(source, "unresolved", "Retrospective constraint correction needs review"))
                blocking.append(f"{source}: retrospective constraint correction needs review")
                continue
            constraints.remove(previous)
            decisions.append(Decision(previous.get("src", "unknown"), "superseded", f"Replaced by {source}"))
        if constraint not in constraints:
            constraints.append(dict(constraint))
            new_constraints.append(constraint)
    if new_constraints:
        affected.update(DEPENDENCIES["general"])
    for source, message in extraction.get("sources", {}).items():
        if source in sources and sources[source] != message:
            raise ValueError(f"Source ID already belongs to different evidence: {source}")
        sources[source] = message

    for record in claims:
        claim = normalize_claim(record)
        source = claim.source or "(missing source)"
        if record in history:
            decisions.append(Decision(source, "ignored", "Duplicate claim"))
            continue
        history.append(dict(record))
        if claim.kind == "proposal":
            decisions.append(Decision(source, "ignored", "Non-binding proposal"))
            continue
        if claim.kind == "warning":
            if claim.area == "food" and claim.key == "quantity" and not claim.reason:
                baseline = state.plan or build_plan((normalize_claim(item) for item in active.values()), constraints)
                food = baseline.areas.get("food", {})
                required, ordered = food.get("required"), food.get("quantity")
                if required is not None and ordered is not None and claim.value < required <= ordered:
                    decisions.append(Decision(source, "ignored",
                        f"Warning assessed: {claim.value} meals would be insufficient; plan retains {ordered} meals for {required} attendees"))
                    continue
            decisions.append(Decision(source, "unresolved", "Warning requires assessment"))
            blocking.append(f"{source}: warning requires assessment")
            continue
        if claim.kind == "reported_action":
            reason = "A reported action does not authorize an amendment"
            previous = active.get(claim.identity) if not claim.reason else None
            unit = claim.unit or (previous or {}).get("u") or "items"
            if previous is not None and claim.key == "quantity":
                reason += f"; reported {claim.value} {unit}, approved {previous['v']} {unit}"
            if (
                not claim.reason and claim.area == "food" and claim.entity_type == "vendor_item"
                and claim.key == "quantity" and not claim.scope
                and unit.strip().casefold() in {"meal", "meals", "box", "boxes", "meal box",
                                              "meal boxes", "item", "items", "serving", "servings"}
                and state.plan is not None and state.plan.status == "VALID"
            ):
                food = state.plan.areas["food"]
                required = food.get("required")
                if food.get("item") == claim.entity_id and required is not None and claim.value < required:
                    if previous is None:
                        reason += f"; reported {claim.value} {unit}, planned {food['quantity']} meals"
                    reason += f"; required {required} meals, shortfall {required - claim.value} meals"
            reason += "; supplier fulfillment requires confirmation"
            decisions.append(Decision(source, "rejected", reason))
            continue
        if claim.kind == "directive":
            scopes = extraction.get("trusted_scopes", {}).get(source)
            if not scopes:
                if claim.area == "food" and claim.key == "quantity" and not claim.reason:
                    baseline = state.plan or build_plan((normalize_claim(item) for item in active.values()), constraints)
                    required = baseline.areas.get("food", {}).get("required")
                    if required is not None and claim.value < required:
                        decisions.append(Decision(source, "rejected",
                            f"Authority could not be verified; requested {claim.value} meals < required {required} meals"))
                        continue
                decisions.append(Decision(source, "unresolved", "Authority could not be verified"))
                continue
            if claim.area not in scopes:
                reason = f"Verified scopes {sorted(scopes)} exclude {claim.area}"
                decisions.append(Decision(source, "rejected", reason))
                continue
        if claim.reason:
            decisions.append(Decision(source, "unresolved", claim.reason))
            issue = f"{source}: {claim.reason}"
            blocking.append(issue)
            pending.append({"record": dict(record), "issue": issue})
            continue

        previous = active.get(claim.identity)
        target = record.get("correction_target", record.get("corrects"))
        if isinstance(target, dict):
            target = target.get("claim_id") or target
        review_match = next((item for item in pending
                             if target and target == item["record"].get("claim_id")), None)
        matches = review_match is not None or target is not None and previous is not None and (
            target == previous.get("claim_id") or
            ("corrects" in record and target == previous["src"])
        )
        if previous is not None:
            older = parse_message_date(dates.get(source))
            newer = parse_message_date(dates.get(previous["src"]))
            if older is not None and newer is not None and (older.utcoffset() is None) == (newer.utcoffset() is None) and older < newer:
                if matches:
                    reason = f"Retrospective correction needs review ({older.isoformat()} < {newer.isoformat()})"
                    decisions.append(Decision(source, "unresolved", reason))
                    blocking.append(f"{source}: {reason}")
                    continue
                reason = f"Stale update {older.isoformat()} < {newer.isoformat()} from {previous['src']}"
                decisions.append(Decision(source, "superseded", reason))
                continue
        if target is not None and not matches:
            reason = "Correction target does not match the active claim"
            decisions.append(Decision(source, "unresolved", reason))
            blocking.append(f"{source}: {reason}")
            continue
        if claim.kind == "directive":
            candidate = active.copy()
            candidate[claim.identity] = record
            proposed = build_plan((normalize_claim(item) for item in candidate.values()), constraints)
            if state.review_issues or blocking or proposed.status != "VALID":
                outcome = "rejected" if proposed.status == "INFEASIBLE" else "unresolved"
                evidence = " / ".join(proposed.issues) or "Existing claims require review"
                if claim.area == "food" and claim.key == "quantity" and state.plan is not None:
                    required = state.plan.areas["food"].get("required")
                    if required is not None and claim.value < required:
                        unit = claim.unit or "items"
                        evidence += f" Requested {claim.value} {unit}; current plan requires {required} {unit}."
                decisions.append(Decision(source, outcome, f"Amendment could not be applied. {evidence}"))
                continue
        if previous is not None:
            decisions.append(Decision(previous["src"], "superseded", f"Replaced by {source}"))
        if review_match is not None:
            pending.remove(review_match)
            resolved_issues.add(review_match["issue"])
            decisions.append(Decision(review_match["record"].get("src", "unknown"), "superseded",
                                      f"Review resolved by explicit correction {source}"))
        active[claim.identity] = dict(record)
        reason = "Applied verified directive" if claim.kind == "directive" else "Recorded factual claim"
        decisions.append(Decision(source, "accepted", reason))
        affected.update(DEPENDENCIES[claim.area])

    for source in extraction.get("irrelevant", ()):
        decisions.append(Decision(source, "ignored", "Irrelevant message"))
    for source in extraction.get("ambiguous", ()):
        if isinstance(source, dict):
            source = source.get("src") or "(missing source)"
        decisions.append(Decision(source, "unresolved", "Extraction reported ambiguous content"))
        blocking.append(f"{source}: ambiguous content")
    if blocking:
        affected.update(DEPENDENCIES["general"])
    plan = state.plan
    if affected or plan is None:
        plan = build_plan((normalize_claim(record) for record in active.values()), constraints)
    for constraint in new_constraints:
        source = constraint.get("src") or "(missing source)"
        family = constraint.get("family") or "unknown"
        outcome = "unresolved" if plan.status == "UNVERIFIED" and constraint.get("modality") != "soft" else "accepted"
        decisions.append(Decision(source, outcome, f"Recorded {family} constraint. Plan status: {plan.status}"))
    # Preserve unresolved facts on later runs until the review seam can resolve them.
    unresolved = tuple(issue for issue in dict.fromkeys((*state.review_issues, *blocking))
                       if issue not in resolved_issues)
    if unresolved:
        plan = replace(plan, status="UNVERIFIED", issues=tuple(dict.fromkeys((*plan.issues, *unresolved))))
    updated = State(
        active=tuple(active.values()), sources=tuple(sources.items()), history=tuple(history),
        decisions=(*state.decisions, *decisions), plan=plan,
        last_valid=plan if plan.status == "VALID" else state.last_valid, review_issues=unresolved,
        message_dates=tuple(dates.items()),
        constraints=tuple(constraints), review_records=tuple(pending),
    )
    return UpdateResult(updated, tuple(decisions), tuple(sorted(affected)))
