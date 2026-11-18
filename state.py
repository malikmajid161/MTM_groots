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


def trusted_date(record):
    if record.get("message_date_trusted") is not True:
        return None
    try:
        date = datetime.fromisoformat(record["message_date"])
        return date if date.utcoffset() is not None else None
    except (KeyError, TypeError, ValueError):
        return None


def apply_update(state, extraction):
    """Apply compact normalized fixtures with externally verified source context.

    The fixture adapter expects trusted_scopes and trusted message dates to
    come from the input envelope supplied by the caller.
    """
    state = State() if state is None else state
    active = {normalize_claim(record).identity: record for record in state.active}
    sources = dict(state.sources)
    history = list(state.history)
    decisions = []
    affected = set()
    blocking = []
    for source, message in extraction.get("sources", {}).items():
        if source in sources and sources[source] != message:
            raise ValueError(f"Source ID already belongs to different evidence: {source}")
        sources[source] = message

    seen_before = tuple(state.history)
    for record in extraction.get("claims", ()):
        claim = normalize_claim(record)
        source = claim.source or "(missing source)"
        if record in seen_before or record in history:
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
        if claim.kind in {"directive", "reported_action"}:
            scopes = extraction.get("trusted_scopes", {}).get(source)
            if not scopes:
                outcome, reason = "unresolved", "Authority could not be verified"
            elif claim.area not in scopes:
                outcome, reason = "rejected", f"Verified scopes {sorted(scopes)} exclude {claim.area}"
            else:
                outcome, reason = "unresolved", "Binding actions require constraint and authorization review"
            decisions.append(Decision(source, outcome, reason))
            if claim.kind == "reported_action":
                blocking.append(f"{source}: reported action requires fulfillment review")
            continue
        if claim.reason:
            decisions.append(Decision(source, "unresolved", claim.reason))
            blocking.append(f"{source}: {claim.reason}")
            continue

        previous = active.get(claim.identity)
        if previous is not None:
            older, newer = trusted_date(record), trusted_date(previous)
            if older is not None and newer is not None and older < newer:
                if record.get("corrects") == previous["src"]:
                    reason = f"Retrospective correction needs review ({older.isoformat()} < {newer.isoformat()})"
                    decisions.append(Decision(source, "unresolved", reason))
                    blocking.append(f"{source}: {reason}")
                    continue
                reason = f"Stale update {older.isoformat()} < {newer.isoformat()} from {previous['src']}"
                decisions.append(Decision(source, "superseded", reason))
                continue
            decisions.append(Decision(previous["src"], "superseded", f"Replaced by {source}"))
        active[claim.identity] = dict(record)
        decisions.append(Decision(source, "accepted", "Recorded factual claim"))
        affected.update(DEPENDENCIES[claim.area])

    for source in extraction.get("irrelevant", ()):
        decisions.append(Decision(source, "ignored", "Irrelevant message"))
    for source in extraction.get("ambiguous", ()):
        decisions.append(Decision(source, "unresolved", "Extraction reported ambiguous content"))
        blocking.append(f"{source}: ambiguous content")
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
    )
    return UpdateResult(updated, tuple(decisions), tuple(sorted(affected)))
