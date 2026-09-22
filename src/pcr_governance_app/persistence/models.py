from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Unicode,
    UnicodeText,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pcr_governance_app.persistence.base import Base


class PCRRecord(Base):
    __tablename__ = "pcr"
    __table_args__ = (UniqueConstraint("pcr_code"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    pcr_code: Mapped[str] = mapped_column(Unicode(30), nullable=False)
    policy_code: Mapped[str] = mapped_column(Unicode(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(Unicode(30), nullable=False, index=True)
    supersedes_pcr_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("pcr.id"), nullable=True
    )
    created_by: Mapped[str] = mapped_column(Unicode(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)

    revisions: Mapped[list["PCRRevisionRecord"]] = relationship(
        back_populates="pcr",
        order_by="PCRRevisionRecord.revision_number",
        lazy="selectin",
    )


class PCRRevisionRecord(Base):
    __tablename__ = "pcr_revision"
    __table_args__ = (UniqueConstraint("pcr_id", "revision_number"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    pcr_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("pcr.id"), nullable=False, index=True
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Unicode(200), nullable=False)
    description: Mapped[str] = mapped_column(UnicodeText, nullable=False)
    change_type: Mapped[str] = mapped_column(Unicode(50), nullable=False)
    rationale: Mapped[str] = mapped_column(UnicodeText, nullable=False)
    current_policy: Mapped[str] = mapped_column(UnicodeText, nullable=False)
    proposed_policy: Mapped[str] = mapped_column(UnicodeText, nullable=False)
    affected_policy_sections: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    impact_summary: Mapped[str] = mapped_column(UnicodeText, nullable=False)
    technical_change_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    technical_change_details: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    communication_targets: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    implementation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_by: Mapped[str] = mapped_column(Unicode(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)

    pcr: Mapped[PCRRecord] = relationship(back_populates="revisions")


class AuditEventRecord(Base):
    __tablename__ = "audit_event"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    pcr_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("pcr.id"), nullable=False, index=True
    )
    revision_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("pcr_revision.id"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(Unicode(100), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(Unicode(255), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    event_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class ApprovalRouteRecord(Base):
    __tablename__ = "approval_route"
    __table_args__ = (UniqueConstraint("route_code", "version"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    route_code: Mapped[str] = mapped_column(Unicode(100), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(Unicode(200), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_by: Mapped[str] = mapped_column(Unicode(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)

    stages: Mapped[list["ApprovalStageRecord"]] = relationship(
        back_populates="route",
        order_by="ApprovalStageRecord.sequence",
        lazy="selectin",
    )


class ApprovalStageRecord(Base):
    __tablename__ = "approval_stage"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    route_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("approval_route.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Unicode(200), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    mode: Mapped[str] = mapped_column(Unicode(20), nullable=False)
    allow_same_approver_multiple_requirements: Mapped[bool] = mapped_column(Boolean, nullable=False)

    route: Mapped[ApprovalRouteRecord] = relationship(back_populates="stages")
    requirements: Mapped[list["ApprovalRequirementRecord"]] = relationship(
        back_populates="stage", lazy="selectin"
    )


class ApprovalRequirementRecord(Base):
    __tablename__ = "approval_requirement"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    stage_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("approval_stage.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Unicode(200), nullable=False)
    selector_type: Mapped[str] = mapped_column(Unicode(30), nullable=False)
    selector_value: Mapped[str] = mapped_column(Unicode(255), nullable=False)
    min_approvals: Mapped[int] = mapped_column(Integer, nullable=False)

    stage: Mapped[ApprovalStageRecord] = relationship(back_populates="requirements")


class ApprovalWorkflowRecord(Base):
    __tablename__ = "approval_workflow"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    pcr_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("pcr.id"), nullable=False, index=True
    )
    revision_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("pcr_revision.id"), nullable=False, index=True
    )
    route_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("approval_route.id"), nullable=False
    )
    route_code: Mapped[str] = mapped_column(Unicode(100), nullable=False)
    route_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Unicode(30), nullable=False, index=True)
    created_by: Mapped[str] = mapped_column(Unicode(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)

    route: Mapped[ApprovalRouteRecord] = relationship(lazy="selectin")
    decisions: Mapped[list["ApprovalDecisionRecord"]] = relationship(
        back_populates="workflow",
        order_by="ApprovalDecisionRecord.created_at",
        lazy="selectin",
    )


class ApprovalDecisionRecord(Base):
    __tablename__ = "approval_decision"
    __table_args__ = (UniqueConstraint("workflow_id", "stage_id", "actor"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    workflow_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("approval_workflow.id"),
        nullable=False,
        index=True,
    )
    stage_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("approval_stage.id"), nullable=False
    )
    requirement_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("approval_requirement.id"), nullable=True
    )
    decision_type: Mapped[str] = mapped_column(Unicode(30), nullable=False)
    actor: Mapped[str] = mapped_column(Unicode(255), nullable=False)
    comment: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)

    workflow: Mapped[ApprovalWorkflowRecord] = relationship(back_populates="decisions")
