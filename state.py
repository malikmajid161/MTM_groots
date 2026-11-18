"""Apply normalized updates and retain source decisions and the last valid plan."""

from dataclasses import asdict, dataclass, replace
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
        return date if date.utcoffset() is not None else None
    except (TypeError, ValueError):
        return None


def apply_update(state, extraction):
    """Accept the CLI contract or the standalone normalized fixture envelope."""
    if isinstance(extraction, dict):
        return update_state(state, extraction)

    from contracts import UpdateResult as ContractResult

    ledger = state or {}
    previous = State(
        active=tuple(ledger.get("active", ())),
        sources=tuple(ledger.get("sources", ())),
        history=tuple(ledger.get("history", ())),
        review_issues=tuple(ledger.get("review_issues", ())),
        message_dates=tuple(ledger.get("message_dates", ())),
        constraints=tuple(ledger.get("constraints", ())),
        decisions=tuple(Decision(**item) for item in ledger.get("decisions", ())),
        plan=Plan(**ledger["plan"]) if ledger.get("plan") else None,
        last_valid=Plan(**ledger["last_valid"]) if ledger.get("last_valid") else None,
    )
    result = update_state(previous, {
        "claims": extraction.claims,
        "constraints": extraction.constraints,
        "irrelevant": extraction.irrelevant_ids,
        "ambiguous": extraction.ambiguities,
    })
    updated = result.state
    return ContractResult(
        ledger={"revision": ledger.get("revision", 0) + 1, **asdict(updated)},
        plan={**updated.plan.areas, "issues": updated.plan.issues},
        status=updated.plan.status,
        last_valid=asdict(updated.last_valid) if updated.last_valid else None,
        decisions=[asdict(decision) for decision in result.decisions],
        affected_areas=list(result.affected_areas),
    )


def update_state(state, extraction):
    """Apply compact normalized fixtures with externally verified source context.

    The fixture adapter expects trusted_scopes and trusted_message_dates to
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
    for source, message in extraction.get("sources", {}).items():
        if source in sources and sources[source] != message:
            raise ValueError(f"Source ID already belongs to different evidence: {source}")
        sources[source] = message

    for record in extraction.get("claims", ()):
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
            decisions.append(Decision(source, "unresolved", "Warning requires assessment"))
            blocking.append(f"{source}: warning requires assessment")
            continue
        if claim.kind == "reported_action":
            reason = "A reported action does not authorize an amendment"
            previous = active.get(claim.identity) if not claim.reason else None
            if previous is not None and claim.key == "quantity":
                unit = claim.unit or previous.get("u") or "items"
                reason += f"; reported {claim.value} {unit}, approved {previous['v']} {unit}"
            decisions.append(Decision(source, "rejected", reason))
            blocking.append(f"{source}: fulfillment review required. {reason}")
            continue
        if claim.kind == "directive":
            scopes = extraction.get("trusted_scopes", {}).get(source)
            if not scopes:
                decisions.append(Decision(source, "unresolved", "Authority could not be verified"))
                continue
            if claim.area not in scopes:
                reason = f"Verified scopes {sorted(scopes)} exclude {claim.area}"
                decisions.append(Decision(source, "rejected", reason))
                continue
        if claim.reason:
            decisions.append(Decision(source, "unresolved", claim.reason))
            blocking.append(f"{source}: {claim.reason}")
            continue

        previous = active.get(claim.identity)
        target = record.get("correction_target", record.get("corrects"))
        if isinstance(target, dict):
            target = target.get("claim_id") or target
        matches = target is not None and previous is not None and (
            target == previous.get("claim_id") or
            ("corrects" in record and target == previous["src"])
        )
        if target is not None and not matches:
            reason = "Correction target does not match the active claim"
            decisions.append(Decision(source, "unresolved", reason))
            blocking.append(f"{source}: {reason}")
            continue
        if previous is not None:
            older = parse_message_date(dates.get(source))
            newer = parse_message_date(dates.get(previous["src"]))
            if older is not None and newer is not None and older < newer:
                if matches:
                    reason = f"Retrospective correction needs review ({older.isoformat()} < {newer.isoformat()})"
                    decisions.append(Decision(source, "unresolved", reason))
                    blocking.append(f"{source}: {reason}")
                    continue
                reason = f"Stale update {older.isoformat()} < {newer.isoformat()} from {previous['src']}"
                decisions.append(Decision(source, "superseded", reason))
                continue
        if claim.kind == "directive":
            candidate = active.copy()
            candidate[claim.identity] = record
            proposed = build_plan(normalize_claim(item) for item in candidate.values())
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
    for constraint in extraction.get("constraints", ()):
        source = constraint.get("src") or "(missing source)"
        family = constraint.get("family") or "unknown"
        reason = f"Constraint needs evaluation: {family}"
        decisions.append(Decision(source, "unresolved", reason))
        blocking.append(f"{source}: {reason}")
    if blocking:
        affected.update(DEPENDENCIES["general"])
    plan = build_plan(normalize_claim(record) for record in active.values()) if affected or state.plan is None else state.plan
    # Preserve unresolved facts on later runs until the review seam can resolve them.
    unresolved = tuple(dict.fromkeys((*state.review_issues, *blocking)))
    if unresolved:
        plan = replace(plan, status="UNVERIFIED", issues=tuple(dict.fromkeys((*plan.issues, *unresolved))))
    updated = State(
        active=tuple(active.values()), sources=tuple(sources.items()), history=tuple(history),
        decisions=(*state.decisions, *decisions), plan=plan,
        last_valid=plan if plan.status == "VALID" else state.last_valid, review_issues=unresolved,
        message_dates=tuple(dates.items()),
        constraints=(*state.constraints, *extraction.get("constraints", ())),
    )
    return UpdateResult(updated, tuple(decisions), tuple(sorted(affected)))
