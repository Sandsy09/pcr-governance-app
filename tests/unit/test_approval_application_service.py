import pytest
from tests.fakes import FakeUnitOfWork, make_uow_factory

from pcr_governance_app.application.approval_service import ApprovalApplicationService
from pcr_governance_app.application.pcr_service import PCRApplicationService
from pcr_governance_app.domain.approval import (
    ApprovalPrincipal,
    ApprovalRequirement,
    ApprovalRoute,
    ApprovalSelector,
    ApprovalSelectorType,
    ApprovalStage,
    ApprovalStageMode,
    ApprovalWorkflow,
    ApprovalWorkflowStatus,
)
from pcr_governance_app.domain.audit import AuditEventType
from pcr_governance_app.domain.enums import ChangeType, PCRStatus
from pcr_governance_app.domain.pcr import PCR, PCRContent


@pytest.fixture
def content() -> PCRContent:
    return PCRContent(
        title="Update affordability r_appules",
        description="Change affordability policy.",
        change_type=ChangeType.POLICY_CHANGE,
        rationale="Policy requires updating.",
        current_policy="Current wording.",
        proposed_policy="Proposed wording.",
        impact_summary="Underwriting impact.",
    )


@pytest.fixture
def route() -> ApprovalRoute:
    return ApprovalRoute(
        route_code="POLICY-STANDARD",
        version=1,
        name="Standard policy change",
        created_by="admin@example.com",
        stages=(
            ApprovalStage(
                name="Credit Risk",
                sequence=10,
                mode=ApprovalStageMode.ANY,
                requirements=(
                    ApprovalRequirement(
                        name="Credit Risk Manager",
                        selector=ApprovalSelector(
                            selector_type=ApprovalSelectorType.ROLE,
                            value="Credit Risk Manager",
                        ),
                    ),
                ),
            ),
            ApprovalStage(
                name="Compliance",
                sequence=20,
                mode=ApprovalStageMode.ANY,
                requirements=(
                    ApprovalRequirement(
                        name="Compliance",
                        selector=ApprovalSelector(
                            selector_type=ApprovalSelectorType.DEPARTMENT,
                            value="Compliance",
                        ),
                    ),
                ),
            ),
        ),
    )


@pytest.fixture
def uow(route: ApprovalRoute) -> FakeUnitOfWork:
    unit = FakeUnitOfWork()
    unit.approval_routes.add(route)
    return unit


def submit_pcr(
    *,
    uow: FakeUnitOfWork,
    content: PCRContent,
) -> tuple[PCR, ApprovalWorkflow]:
    pcr_service = PCRApplicationService(uow_factory=make_uow_factory(uow))
    pcr = pcr_service.create_pcr(
        pcr_code="PCR-2026-0001",
        policy_code="CP-001",
        content=content,
        actor="author@example.com",
    )
    pcr_service.submit_for_review(
        pcr_id=pcr.id,
        route_code="POLICY-STANDARD",
        actor="author@example.com",
    )
    workflow = uow.approval_workflows.get_active_for_pcr(pcr.id)
    assert workflow is not None
    return pcr, workflow


def test_first_stage_approval_keeps_pcr_in_review(
    uow: FakeUnitOfWork,
    content: PCRContent,
) -> None:
    pcr, workflow = submit_pcr(uow=uow, content=content)
    service = ApprovalApplicationService(uow_factory=make_uow_factory(uow))
    first_requirement = workflow.stages[0].requirements[0]

    result = service.approve(
        workflow_id=workflow.id,
        principal=ApprovalPrincipal(
            user_id="manager@example.com",
            roles=frozenset({"Credit Risk Manager"}),
        ),
        requirement_id=first_requirement.id,
    )

    stored_pcr = uow.pcrs.get(pcr.id)
    assert stored_pcr is not None
    assert stored_pcr.status == PCRStatus.IN_REVIEW
    assert result.workflow.status == ApprovalWorkflowStatus.ACTIVE
    audit_events = uow.audits.list_for_pcr(pcr.id)
    assert audit_events[-2].event_type == AuditEventType.APPROVAL_DECISION_RECORDED
    assert audit_events[-1].event_type == AuditEventType.APPROVAL_STAGE_COMPLETED


def test_final_approval_marks_workflow_and_pcr_approved(
    uow: FakeUnitOfWork,
    content: PCRContent,
) -> None:
    pcr, workflow = submit_pcr(uow=uow, content=content)
    service = ApprovalApplicationService(uow_factory=make_uow_factory(uow))

    first = service.approve(
        workflow_id=workflow.id,
        principal=ApprovalPrincipal(
            user_id="manager@example.com",
            roles=frozenset({"Credit Risk Manager"}),
        ),
        requirement_id=workflow.stages[0].requirements[0].id,
    )

    result = service.approve(
        workflow_id=workflow.id,
        principal=ApprovalPrincipal(
            user_id="compliance@example.com",
            departments=frozenset({"Compliance"}),
        ),
        requirement_id=first.workflow.stages[1].requirements[0].id,
    )

    stored_pcr = uow.pcrs.get(pcr.id)
    stored_workflow = uow.approval_workflows.get(workflow.id)

    assert stored_pcr is not None
    assert stored_pcr.status == PCRStatus.APPROVED
    assert stored_workflow is not None
    assert stored_workflow.status == ApprovalWorkflowStatus.APPROVED
    assert result.workflow.status == ApprovalWorkflowStatus.APPROVED
    assert uow.audits.list_for_pcr(pcr.id)[-1].event_type == AuditEventType.PCR_APPROVED


def test_request_changes_moves_workflow_and_pcr_to_changes_required(
    uow: FakeUnitOfWork,
    content: PCRContent,
) -> None:
    pcr, workflow = submit_pcr(uow=uow, content=content)
    service = ApprovalApplicationService(uow_factory=make_uow_factory(uow))

    result = service.request_changes(
        workflow_id=workflow.id,
        principal=ApprovalPrincipal(
            user_id="manager@example.com",
            roles=frozenset({"Credit Risk Manager"}),
        ),
        reason="Clarify the customer impact.",
    )

    stored_pcr = uow.pcrs.get(pcr.id)
    assert stored_pcr is not None
    assert stored_pcr.status == PCRStatus.CHANGES_REQUIRED
    assert result.workflow.status == ApprovalWorkflowStatus.CHANGES_REQUIRED
    assert [event.event_type for event in uow.audits.list_for_pcr(pcr.id)[-2:]] == [
        AuditEventType.APPROVAL_DECISION_RECORDED,
        AuditEventType.CHANGES_REQUESTED,
    ]


def test_reject_moves_workflow_and_pcr_to_rejected(
    uow: FakeUnitOfWork,
    content: PCRContent,
) -> None:
    pcr, workflow = submit_pcr(uow=uow, content=content)
    service = ApprovalApplicationService(uow_factory=make_uow_factory(uow))

    result = service.reject(
        workflow_id=workflow.id,
        principal=ApprovalPrincipal(
            user_id="manager@example.com",
            roles=frozenset({"Credit Risk Manager"}),
        ),
        reason="Governance requirements not met.",
    )

    stored_pcr = uow.pcrs.get(pcr.id)
    assert stored_pcr is not None
    assert stored_pcr.status == PCRStatus.REJECTED
    assert result.workflow.status == ApprovalWorkflowStatus.REJECTED
    assert [event.event_type for event in uow.audits.list_for_pcr(pcr.id)[-2:]] == [
        AuditEventType.APPROVAL_DECISION_RECORDED,
        AuditEventType.PCR_REJECTED,
    ]
