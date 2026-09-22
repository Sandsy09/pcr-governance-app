from datetime import date, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import ChangeType, CommunicationTarget, PCRStatus
from .time import utc_now


class PCRContent(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str = Field(min_length=5, max_length=200)
    description: str = Field(min_length=1)

    change_type: ChangeType

    rationale: str = Field(min_length=1)
    current_policy: str = Field(min_length=1)
    proposed_policy: str = Field(min_length=1)

    affected_policy_sections: tuple[str, ...] = ()

    impact_summary: str = Field(min_length=1)

    technical_change_required: bool = False
    technical_change_details: str | None = None

    communication_targets: frozenset[CommunicationTarget] = frozenset()

    implementation_date: date | None = None

    @model_validator(mode="after")
    def validate_technical_change(self) -> "PCRContent":
        if self.technical_change_required and not self.technical_change_details:
            raise ValueError(
                "Technical change details are required when a technical change is necessary."
            )

        return self


class PCRRevision(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    revision_number: int = Field(ge=1)
    content: PCRContent
    created_by: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=utc_now)


class PCR(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    pcr_code: str = Field(min_length=1)
    policy_code: str = Field(min_length=1, max_length=50)
    status: PCRStatus = PCRStatus.DRAFT
    supersedes_pcr_id: UUID | None = None
    created_by: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=utc_now)
    revisions: tuple[PCRRevision, ...] = ()

    @property
    def current_revision(self) -> PCRRevision | None:
        if not self.revisions:
            return None

        return max(self.revisions, key=lambda revision: revision.revision_number)
