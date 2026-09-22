from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from pcr_governance_app.domain.time import utc_now


class AuditEventType(StrEnum):
    PCR_CREATED = "pcr_created"
    REVISION_CREATED = "revision_created"
    PCR_SUBMITTED = "pcr_submitted"
    PCR_RESUBMITTED = "pcr_resubmitted"
    CHANGES_REQUESTED = "changes_requested"
    PCR_REJECTED = "pcr_rejected"
    PCR_WITHDRAWN = "pcr_withdrawn"
    PCR_APPROVED = "pcr_approved"
    PCR_EFFECTIVE = "pcr_effective"
    PCR_SUPERSEDED = "pcr_superseded"
    APPROVAL_WORKFLOW_CREATED = "approval_workflow_created"
    APPROVAL_DECISION_RECORDED = "approval_decision_recorded"
    APPROVAL_STAGE_COMPLETED = "approval_stage_completed"


AuditValue = str | int | float | bool | None


class AuditEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    pcr_id: UUID
    revision_id: UUID | None = None
    event_type: AuditEventType
    actor: str = Field(min_length=1)
    occurred_at: datetime = Field(default_factory=utc_now)
    details: dict[str, AuditValue] = Field(default_factory=dict)
