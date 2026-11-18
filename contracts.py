"""Shared extractor, planner, and reporting contracts."""

from dataclasses import dataclass, field
from time import monotonic
from typing import Literal, Protocol, TypedDict

Area = Literal["reading", "venue", "schedule", "food", "judging", "budget"]


@dataclass(frozen=True)
class InputBatch:
    source_id: str
    path: str
    text: str


class Claim(TypedDict, total=False):
    src: str
    area: str
    et: str
    id: str
    k: str
    v: object
    op: str
    u: str
    kind: str
    actor: str
    modality: str
    family: str
    raw_key: str
    raw_text: str
    currency: str
    price_scope: str
    message_date: str
    effective_period: dict
    correction_target: dict


class Constraint(TypedDict):
    src: str
    modality: str
    family: str
    # Family-specific operands and references, validated by the planner.
    payload: dict


@dataclass
class Extraction:
    claims: list[Claim] = field(default_factory=list)
    constraints: list[Constraint] = field(default_factory=list)
    ambiguities: list[dict] = field(default_factory=list)
    irrelevant_ids: list[str] = field(default_factory=list)


@dataclass
class UpdateResult:
    ledger: dict
    plan: dict
    status: Literal["VALID", "INFEASIBLE", "UNVERIFIED"]
    last_valid: dict | None = None
    decisions: list[dict] = field(default_factory=list)
    affected_areas: list[str] = field(default_factory=list)


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class RunBudget:
    deadline: float
    max_attempts: int | None
    attempts: int = 0

    def remaining(self) -> float:
        return max(0.0, self.deadline - monotonic())

    def reserve_attempt(self) -> int:
        if not self.remaining():
            raise BudgetExceeded("Model deadline reached")
        if self.max_attempts is not None and self.attempts >= self.max_attempts:
            raise BudgetExceeded("Model attempt limit reached")
        self.attempts += 1
        return self.attempts


@dataclass(frozen=True)
class ModelCall:
    model: str
    area: Area
    input: object
    output: object = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    elapsed_seconds: float | None = None
    error: str | None = None


class Recorder(Protocol):
    def __call__(self, call: ModelCall) -> None: ...


class Extractor(Protocol):
    def __call__(
        self, batch: InputBatch, context: dict, budget: RunBudget, recorder: Recorder
    ) -> Extraction: ...


class Planner(Protocol):
    def __call__(self, state: dict, extraction: Extraction) -> UpdateResult: ...
