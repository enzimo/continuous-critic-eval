"""The versioned reporting contract, shared by HTTP, MCP, CLI, and exports."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Identifier = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")]
Text = Annotated[str, StringConstraints(min_length=1, max_length=16000)]
Short = Annotated[str, StringConstraints(min_length=1, max_length=240)]
Severity = Literal["blocking", "should_fix", "consider"]
Confidence = Literal["verified", "likely", "possible"]
Category = Literal[
    "intent",
    "correctness",
    "evidence",
    "security",
    "privacy",
    "operations",
    "maintainability",
    "performance",
    "other",
]
Verdict = Literal["AGREE", "DISAGREE_EVIDENCE", "DISAGREE_CONCERN"]
ReviewType = Literal["pull_request", "code", "architecture", "troubleshooting"]
Dataset = Literal["production", "benchmark", "demo"]
MAX_BATCH_BYTES = 2_000_000
MAX_BATCH_EVENTS = 250


def now() -> str:
    return datetime.now(UTC).isoformat()


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Critic(Model):
    name: Short
    role: Short
    specialty: Short | None = None
    prompt: Text
    provider: Short | None = None
    model: Short | None = None
    settings: dict[str, str | int | float | bool] = Field(default_factory=dict, max_length=30)

    @model_validator(mode="after")
    def specialty_is_not_a_duty(self):
        if self.specialty is not None:
            value = " ".join(self.specialty.replace("_", " ").split()).casefold()
            if not value or value in {
                "lead",
                "critic",
                "independent critic",
                "reviewer",
                "coordinator",
                "challenger",
            }:
                raise ValueError(
                    "Specialty must describe what is checked, such as Security, Bug hunting, "
                    "or General review. Record responsibilities in invocation phase."
                )
        return self


class KnownIssue(Model):
    id: Identifier
    title: Short
    severity: Severity
    evidence: Text


class Case(Model):
    id: Identifier
    title: Short
    target: Short
    target_revision: Short
    instructions: Text
    known_issues: list[KnownIssue] = Field(default_factory=list, max_length=100)


class Variant(Model):
    id: Identifier
    name: Short
    critic_ids: list[Identifier] = Field(min_length=1, max_length=20)


class Experiment(Model):
    name: Short
    hypothesis: Text
    skill_revision: Short
    review_type: ReviewType = "code"
    input_mode: Literal["filesystem", "snapshot"] = "filesystem"
    primary_metric: Literal["known_defect_recall", "valid_issues", "false_alarms", "cost_usd"]
    variants: list[Variant] = Field(min_length=2, max_length=24)
    cases: list[Case] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_members(self):
        for values in (self.variants, self.cases):
            if len({v.id for v in values}) != len(values):
                raise ValueError("Case and variant IDs must be unique")
        for variant in self.variants:
            if len(set(variant.critic_ids)) != len(variant.critic_ids):
                raise ValueError("A variant cannot contain a critic twice")
        for case in self.cases:
            if len({i.id for i in case.known_issues}) != len(case.known_issues):
                raise ValueError("Known issue IDs must be unique within a case")
        return self


class RunStarted(Model):
    type: Literal["run_started"]
    project: Short
    title: Short
    review_type: ReviewType
    target: Short
    target_revision: Short
    skill_revision: Short
    client: Short
    dataset: Dataset = "production"
    complexity: Literal["small", "medium", "high"] = "medium"
    expected_critic_ids: list[Identifier] = Field(default_factory=list, max_length=30)
    experiment_id: Identifier | None = None
    variant_id: Identifier | None = None
    case_id: Identifier | None = None
    trial: int = Field(default=1, ge=1, le=10000)

    @model_validator(mode="after")
    def experiment_fields(self):
        fields = [self.experiment_id, self.variant_id, self.case_id]
        if any(fields) and not all(fields):
            raise ValueError("experiment_id, variant_id and case_id must be supplied together")
        if len(set(self.expected_critic_ids)) != len(self.expected_critic_ids):
            raise ValueError("expected_critic_ids cannot contain duplicates")
        return self


class InvocationStarted(Model):
    type: Literal["invocation_started"]
    invocation_id: Identifier
    critic_id: Identifier
    phase: Literal["independent", "critique", "lead"]
    round: int = Field(default=0, ge=0, le=5)
    context: Literal["independent", "shared"]
    provider: Short | None = None
    model: Short | None = None
    scope: Text

    @model_validator(mode="after")
    def coherent_phase(self):
        if self.phase == "independent" and (self.round != 0 or self.context != "independent"):
            raise ValueError("Independent discovery is round 0 with independent context")
        if self.phase == "critique" and self.round < 1:
            raise ValueError("Critique rounds start at 1")
        return self


class Usage(Model):
    source: Literal["runtime", "provider", "operator"]
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cache_read_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    cost_basis: Literal["billed", "provider_estimate", "price_estimate"] | None = None

    @model_validator(mode="after")
    def cost_provenance(self):
        if (self.cost_usd is None) != (self.cost_basis is None):
            raise ValueError("A cost measurement needs both cost_usd and cost_basis")
        return self


class InvocationFinished(Model):
    type: Literal["invocation_finished"]
    invocation_id: Identifier
    status: Literal["completed", "failed", "cancelled"]
    usage: Usage | None = None
    resolved_model: Short | None = None
    error: Text | None = None


class FindingRecorded(Model):
    type: Literal["finding_recorded"]
    finding_id: Identifier
    version: int = Field(default=1, ge=1, le=1000)
    issue_id: Identifier
    invocation_id: Identifier
    title: Short
    severity: Severity
    confidence: Confidence
    category: Category
    location: Text
    trigger: Text
    impact: Text
    evidence: Text


class VerdictRecorded(Model):
    type: Literal["verdict_recorded"]
    invocation_id: Identifier
    finding_id: Identifier
    finding_version: int = Field(ge=1)
    verdict: Verdict
    rationale: Text
    evidence: str = Field(default="", max_length=16000)

    @model_validator(mode="after")
    def evidence_required(self):
        if self.verdict == "DISAGREE_EVIDENCE" and not self.evidence.strip():
            raise ValueError("DISAGREE_EVIDENCE must cite contradicting evidence")
        return self


class DecisionRecorded(Model):
    type: Literal["decision_recorded"]
    finding_id: Identifier
    finding_version: int = Field(ge=1)
    revision: int = Field(default=1, ge=1)
    state: Literal["supported", "withdrawn", "unresolved"]
    rationale: Text
    evidence: str = Field(default="", max_length=16000)


class IssuesMerged(Model):
    type: Literal["issues_merged"]
    source_issue_id: Identifier
    target_issue_id: Identifier
    reason: Text


class RunFinished(Model):
    type: Literal["run_finished"]
    status: Literal["completed", "failed", "cancelled"]
    reason: Text


class IssueJudged(Model):
    type: Literal["issue_judged"]
    issue_id: Identifier
    revision: int = Field(default=1, ge=1)
    validity: Literal["valid", "invalid", "unknown"]
    severity: Severity | None = None
    method: Literal["human", "reproduction", "benchmark"]
    assessor: Short
    rationale: Text
    evidence: Text
    known_issue_id: Identifier | None = None


class ChallengeJudged(Model):
    type: Literal["challenge_judged"]
    verdict_event_id: Identifier
    revision: int = Field(default=1, ge=1)
    result: Literal["upheld", "rejected", "unknown"]
    effect: Literal["removed_invalid_claim", "rescued_valid_claim", "improved_evidence", "none"]
    assessor: Short
    evidence: Text


class OutcomeRecorded(Model):
    type: Literal["outcome_recorded"]
    issue_id: Identifier
    revision: int = Field(default=1, ge=1)
    state: Literal["fixed", "deferred", "reopened"]
    rationale: Text
    reference: Text


class RunEvaluated(Model):
    type: Literal["run_evaluated"]
    assessor: Short
    evidence: Text


class RunInvalidated(Model):
    type: Literal["run_invalidated"]
    reason: Text


Payload = Annotated[
    RunStarted
    | InvocationStarted
    | InvocationFinished
    | FindingRecorded
    | VerdictRecorded
    | DecisionRecorded
    | IssuesMerged
    | RunFinished
    | IssueJudged
    | ChallengeJudged
    | OutcomeRecorded
    | RunEvaluated
    | RunInvalidated,
    Field(discriminator="type"),
]


class Event(Model):
    schema_version: Literal[1] = 1
    event_id: Identifier
    run_id: Identifier
    occurred_at: datetime
    data: Payload

    @model_validator(mode="after")
    def timezone_required(self):
        if self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at needs an explicit timezone")
        self.occurred_at = self.occurred_at.astimezone(UTC)
        return self


class Batch(Model):
    events: list[Event] = Field(min_length=1, max_length=MAX_BATCH_EVENTS)


OPERATOR_EVENTS = {
    "issue_judged",
    "challenge_judged",
    "outcome_recorded",
    "run_evaluated",
    "run_invalidated",
}
