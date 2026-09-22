from datetime import UTC, datetime
from uuid import UUID

from pcr_governance_app.domain.approval import (
    ApprovalDecision,
    ApprovalDecisionType,
    ApprovalRequirement,
    ApprovalRoute,
    ApprovalSelector,
    ApprovalSelectorType,
    ApprovalStage,
    ApprovalStageMode,
    ApprovalWorkflow,
    ApprovalWorkflowStatus,
)
from pcr_governance_app.domain.audit import AuditEvent, AuditEventType
from pcr_governance_app.domain.enums import ChangeType, CommunicationTarget, PCRStatus
from pcr_governance_app.domain.pcr import PCR, PCRContent, PCRRevision
from pcr_governance_app.persistence.models import (
    ApprovalDecisionRecord,
    ApprovalRequirementRecord,
    ApprovalRouteRecord,
    ApprovalStageRecord,
    ApprovalWorkflowRecord,
    AuditEventRecord,
    PCRRecord,
    PCRRevisionRecord,
)


def to_database_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Domain datetime values must be timezone-aware.")

    return value.astimezone(UTC).replace(tzinfo=None)


def from_database_datetime(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(UTC)

    return value.replace(tzinfo=UTC)


def revision_to_record(*, pcr_id: UUID, revision: PCRRevision) -> PCRRevisionRecord:
    content = revision.content
    return PCRRevisionRecord(
        id=revision.id,
        pcr_id=pcr_id,
        revision_number=revision.revision_number,
        title=content.title,
        description=content.description,
        change_type=content.change_type.value,
        rationale=content.rationale,
        current_policy=content.current_policy,
        proposed_policy=content.proposed_policy,
        affected_policy_sections=list(content.affected_policy_sections),
        impact_summary=content.impact_summary,
        technical_change_required=content.technical_change_required,
        technical_change_details=content.technical_change_details,
        communication_targets=sorted(target.value for target in content.communication_targets),
        implementation_date=content.implementation_date,
        created_by=revision.created_by,
        created_at=to_database_datetime(revision.created_at),
    )


def revision_record_to_domain(record: PCRRevisionRecord) -> PCRRevision:
    return PCRRevision(
        id=record.id,
        revision_number=record.revision_number,
        content=PCRContent(
            title=record.title,
            description=record.description,
            change_type=ChangeType(record.change_type),
            rationale=record.rationale,
            current_policy=record.current_policy,
            proposed_policy=record.proposed_policy,
            affected_policy_sections=tuple(record.affected_policy_sections),
            impact_summary=record.impact_summary,
            technical_change_required=record.technical_change_required,
            technical_change_details=record.technical_change_details,
            communication_targets=frozenset(
                CommunicationTarget(target) for target in record.communication_targets
            ),
            implementation_date=record.implementation_date,
        ),
        created_by=record.created_by,
        created_at=from_database_datetime(record.created_at),
    )


def pcr_to_record(pcr: PCR) -> PCRRecord:
    record = PCRRecord(
        id=pcr.id,
        pcr_code=pcr.pcr_code,
        policy_code=pcr.policy_code,
        status=pcr.status.value,
        supersedes_pcr_id=pcr.supersedes_pcr_id,
        created_by=pcr.created_by,
        created_at=to_database_datetime(pcr.created_at),
    )
    record.revisions = [
        revision_to_record(pcr_id=pcr.id, revision=revision) for revision in pcr.revisions
    ]
    return record


def pcr_record_to_domain(record: PCRRecord) -> PCR:
    return PCR(
        id=record.id,
        pcr_code=record.pcr_code,
        policy_code=record.policy_code,
        status=PCRStatus(record.status),
        supersedes_pcr_id=record.supersedes_pcr_id,
        created_by=record.created_by,
        created_at=from_database_datetime(record.created_at),
        revisions=tuple(revision_record_to_domain(revision) for revision in record.revisions),
    )


def audit_event_to_record(event: AuditEvent) -> AuditEventRecord:
    return AuditEventRecord(
        id=event.id,
        pcr_id=event.pcr_id,
        revision_id=event.revision_id,
        event_type=event.event_type.value,
        actor=event.actor,
        occurred_at=to_database_datetime(event.occurred_at),
        event_data=dict(event.details),
    )


def audit_event_record_to_domain(record: AuditEventRecord) -> AuditEvent:
    return AuditEvent(
        id=record.id,
        pcr_id=record.pcr_id,
        revision_id=record.revision_id,
        event_type=AuditEventType(record.event_type),
        actor=record.actor,
        occurred_at=from_database_datetime(record.occurred_at),
        details=dict(record.event_data),
    )


def approval_requirement_to_record(
    requirement: ApprovalRequirement,
) -> ApprovalRequirementRecord:
    return ApprovalRequirementRecord(
        id=requirement.id,
        name=requirement.name,
        selector_type=requirement.selector.selector_type.value,
        selector_value=requirement.selector.value,
        min_approvals=requirement.min_approvals,
    )


def approval_requirement_record_to_domain(
    record: ApprovalRequirementRecord,
) -> ApprovalRequirement:
    return ApprovalRequirement(
        id=record.id,
        name=record.name,
        selector=ApprovalSelector(
            selector_type=ApprovalSelectorType(record.selector_type),
            value=record.selector_value,
        ),
        min_approvals=record.min_approvals,
    )


def approval_stage_to_record(stage: ApprovalStage) -> ApprovalStageRecord:
    record = ApprovalStageRecord(
        id=stage.id,
        name=stage.name,
        sequence=stage.sequence,
        mode=stage.mode.value,
        allow_same_approver_multiple_requirements=(stage.allow_same_approver_multiple_requirements),
    )
    record.requirements = [
        approval_requirement_to_record(requirement) for requirement in stage.requirements
    ]
    return record


def approval_stage_record_to_domain(record: ApprovalStageRecord) -> ApprovalStage:
    return ApprovalStage(
        id=record.id,
        name=record.name,
        sequence=record.sequence,
        mode=ApprovalStageMode(record.mode),
        requirements=tuple(
            approval_requirement_record_to_domain(requirement)
            for requirement in record.requirements
        ),
        allow_same_approver_multiple_requirements=(
            record.allow_same_approver_multiple_requirements
        ),
    )


def approval_route_to_record(route: ApprovalRoute) -> ApprovalRouteRecord:
    record = ApprovalRouteRecord(
        id=route.id,
        route_code=route.route_code,
        version=route.version,
        name=route.name,
        active=route.active,
        created_by=route.created_by,
        created_at=to_database_datetime(route.created_at),
    )
    record.stages = [approval_stage_to_record(stage) for stage in route.ordered_stages]
    return record


def approval_route_record_to_domain(record: ApprovalRouteRecord) -> ApprovalRoute:
    return ApprovalRoute(
        id=record.id,
        route_code=record.route_code,
        version=record.version,
        name=record.name,
        stages=tuple(
            approval_stage_record_to_domain(stage)
            for stage in sorted(record.stages, key=lambda item: item.sequence)
        ),
        active=record.active,
        created_by=record.created_by,
        created_at=from_database_datetime(record.created_at),
    )


def approval_decision_to_record(
    decision: ApprovalDecision,
) -> ApprovalDecisionRecord:
    return ApprovalDecisionRecord(
        id=decision.id,
        workflow_id=decision.workflow_id,
        stage_id=decision.stage_id,
        requirement_id=decision.requirement_id,
        decision_type=decision.decision_type.value,
        actor=decision.actor,
        comment=decision.comment,
        created_at=to_database_datetime(decision.created_at),
    )


def approval_decision_record_to_domain(
    record: ApprovalDecisionRecord,
) -> ApprovalDecision:
    return ApprovalDecision(
        id=record.id,
        workflow_id=record.workflow_id,
        stage_id=record.stage_id,
        requirement_id=record.requirement_id,
        decision_type=ApprovalDecisionType(record.decision_type),
        actor=record.actor,
        comment=record.comment,
        created_at=from_database_datetime(record.created_at),
    )


def approval_workflow_to_record(
    workflow: ApprovalWorkflow,
) -> ApprovalWorkflowRecord:
    record = ApprovalWorkflowRecord(
        id=workflow.id,
        pcr_id=workflow.pcr_id,
        revision_id=workflow.revision_id,
        route_id=workflow.route_id,
        route_code=workflow.route_code,
        route_version=workflow.route_version,
        status=workflow.status.value,
        created_by=workflow.created_by,
        created_at=to_database_datetime(workflow.created_at),
        completed_at=(
            to_database_datetime(workflow.completed_at)
            if workflow.completed_at is not None
            else None
        ),
    )
    record.decisions = [approval_decision_to_record(decision) for decision in workflow.decisions]
    return record


def approval_workflow_record_to_domain(
    record: ApprovalWorkflowRecord,
) -> ApprovalWorkflow:
    return ApprovalWorkflow(
        id=record.id,
        pcr_id=record.pcr_id,
        revision_id=record.revision_id,
        route_id=record.route_id,
        route_code=record.route_code,
        route_version=record.route_version,
        stages=tuple(
            approval_stage_record_to_domain(stage)
            for stage in sorted(record.route.stages, key=lambda item: item.sequence)
        ),
        status=ApprovalWorkflowStatus(record.status),
        decisions=tuple(
            approval_decision_record_to_domain(decision) for decision in record.decisions
        ),
        created_by=record.created_by,
        created_at=from_database_datetime(record.created_at),
        completed_at=(
            from_database_datetime(record.completed_at) if record.completed_at is not None else None
        ),
    )
