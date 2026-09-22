from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pcr_governance_app.domain.time import utc_now


class ApprovalSelectorType(StrEnum):
    USER = "user"
    ROLE = "role"
    DEPARTMENT = "department"


class ApprovalStageMode(StrEnum):
    ANY = "any"
    ALL = "all"


class ApprovalDecisionType(StrEnum):
    APPROVE = "approve"
    REQUEST_CHANGES = "request_changes"
    REJECT = "reject"


class ApprovalWorkflowStatus(StrEnum):
    ACTIVE = "active"
    APPROVED = "approved"
    CHANGES_REQUIRED = "changes_required"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class ApprovalPrincipal(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: str = Field(min_length=1)
    roles: frozenset[str] = frozenset()
    departments: frozenset[str] = frozenset()


class ApprovalSelector(BaseModel):
    model_config = ConfigDict(frozen=True)

    selector_type: ApprovalSelectorType
    value: str = Field(min_length=1)

    def matches(self, principal: ApprovalPrincipal) -> bool:
        match self.selector_type:
            case ApprovalSelectorType.USER:
                return principal.user_id == self.value
            case ApprovalSelectorType.ROLE:
                return self.value in principal.roles
            case ApprovalSelectorType.DEPARTMENT:
                return self.value in principal.departments

        return False


class ApprovalRequirement(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1)
    selector: ApprovalSelector
    min_approvals: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def validate_user_requirement(self) -> "ApprovalRequirement":
        if self.selector.selector_type == ApprovalSelectorType.USER and self.min_approvals != 1:
            raise ValueError(
                "A specific-user approval requirement must require exactly one approval."
            )

        return self


class ApprovalStage(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    mode: ApprovalStageMode
    requirements: tuple[ApprovalRequirement, ...]
    allow_same_approver_multiple_requirements: bool = False

    @model_validator(mode="after")
    def validate_requirements(self) -> "ApprovalStage":
        if not self.requirements:
            raise ValueError("An approval stage must contain at least one requirement.")

        requirement_ids = {requirement.id for requirement in self.requirements}
        if len(requirement_ids) != len(self.requirements):
            raise ValueError("Approval requirement IDs must be unique within a stage.")

        return self


class ApprovalRoute(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    route_code: str = Field(min_length=1, max_length=100)
    version: int = Field(ge=1)
    name: str = Field(min_length=1)
    stages: tuple[ApprovalStage, ...]
    active: bool = True
    created_by: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_stages(self) -> "ApprovalRoute":
        if not self.stages:
            raise ValueError("An approval route must contain at least one stage.")

        sequences = [stage.sequence for stage in self.stages]
        if len(set(sequences)) != len(sequences):
            raise ValueError("Approval stage sequence values must be unique.")

        stage_ids = {stage.id for stage in self.stages}
        if len(stage_ids) != len(self.stages):
            raise ValueError("Approval stage IDs must be unique.")

        return self

    @property
    def ordered_stages(self) -> tuple[ApprovalStage, ...]:
        return tuple(sorted(self.stages, key=lambda stage: stage.sequence))


class ApprovalDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    workflow_id: UUID
    stage_id: UUID
    requirement_id: UUID | None = None
    decision_type: ApprovalDecisionType
    actor: str = Field(min_length=1)
    comment: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class ApprovalWorkflow(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    pcr_id: UUID
    revision_id: UUID
    route_id: UUID
    route_code: str
    route_version: int
    stages: tuple[ApprovalStage, ...]
    status: ApprovalWorkflowStatus = ApprovalWorkflowStatus.ACTIVE
    decisions: tuple[ApprovalDecision, ...] = ()
    created_by: str
    created_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None


class ApprovalActionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    workflow: ApprovalWorkflow
    decision: ApprovalDecision
    completed_stage_id: UUID | None = None
