import pytest
from tests.fakes import FakeUnitOfWork, make_uow_factory

from pcr_governance_app.application.errors import (
    ApprovalRouteNotFoundError,
    PCRCodeAlreadyExistsError,
)
from pcr_governance_app.application.pcr_service import PCRApplicationService
from pcr_governance_app.domain.approval import (
    ApprovalRequirement,
    ApprovalRoute,
    ApprovalSelector,
    ApprovalSelectorType,
    ApprovalStage,
    ApprovalStageMode,
    ApprovalWorkflowStatus,
)
from pcr_governance_app.domain.audit import AuditEventType
from pcr_governance_app.domain.enums import ChangeType, PCRStatus
from pcr_governance_app.domain.errors import PCRImmutableError
from pcr_governance_app.domain.pcr import PCRContent


@pytest.fixture
def content() -> PCRContent:
    return PCRContent(
        title="Update affordability rules",
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
                name="Credit Risk Approval",
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
        ),
    )


@pytest.fixture
def uow(route: ApprovalRoute) -> FakeUnitOfWork:
    unit = FakeUnitOfWork()
    unit.approval_routes.add(route)
    return unit


@pytest.fixture
def service(uow: FakeUnitOfWork) -> PCRApplicationService:
    return PCRApplicationService(uow_factory=make_uow_factory(uow))


def test_create_pcr_creates_initial_revision(
    service: PCRApplicationService,
    uow: FakeUnitOfWork,
    content: PCRContent,
) -> None:
    pcr = service.create_pcr(
        pcr_code="PCR-2026-0001",
        policy_code="CP-001",
        content=content,
        actor="user@example.com",
    )
    stored = uow.pcrs.get(pcr.id)

    assert stored is not None
    assert stored.status == PCRStatus.DRAFT
    assert len(stored.revisions) == 1
    assert uow.committed


def test_create_pcr_records_audit_events(
    service: PCRApplicationService,
    uow: FakeUnitOfWork,
    content: PCRContent,
) -> None:
    pcr = service.create_pcr(
        pcr_code="PCR-2026-0001",
        policy_code="CP-001",
        content=content,
        actor="user@example.com",
    )
    events = uow.audits.list_for_pcr(pcr.id)

    assert [event.event_type for event in events] == [
        AuditEventType.PCR_CREATED,
        AuditEventType.REVISION_CREATED,
    ]


def test_save_revision_appends_revision_and_audit(
    service: PCRApplicationService,
    uow: FakeUnitOfWork,
    content: PCRContent,
) -> None:
    pcr = service.create_pcr(
        pcr_code="PCR-2026-0001",
        policy_code="CP-001",
        content=content,
        actor="user@example.com",
    )
    revised_content = content.model_copy(update={"proposed_policy": "Updated wording."})
    updated = service.save_revision(
        pcr_id=pcr.id,
        content=revised_content,
        actor="user@example.com",
    )

    assert len(updated.revisions) == 2
    assert updated.current_revision is not None
    assert updated.current_revision.revision_number == 2
    assert uow.audits.items[-1].event_type == AuditEventType.REVISION_CREATED


def test_submit_for_review_creates_approval_workflow(
    service: PCRApplicationService,
    uow: FakeUnitOfWork,
    content: PCRContent,
) -> None:
    pcr = service.create_pcr(
        pcr_code="PCR-2026-0001",
        policy_code="CP-001",
        content=content,
        actor="user@example.com",
    )
    submitted = service.submit_for_review(
        pcr_id=pcr.id,
        route_code="POLICY-STANDARD",
        actor="user@example.com",
    )

    workflow = uow.approval_workflows.get_active_for_pcr(pcr.id)

    assert submitted.status == PCRStatus.IN_REVIEW
    assert workflow is not None
    assert submitted.current_revision is not None
    assert workflow.status == ApprovalWorkflowStatus.ACTIVE
    assert workflow.revision_id == submitted.current_revision.id
    assert workflow.route_code == "POLICY-STANDARD"
    assert [event.event_type for event in uow.audits.items[-2:]] == [
        AuditEventType.PCR_SUBMITTED,
        AuditEventType.APPROVAL_WORKFLOW_CREATED,
    ]


def test_submit_for_review_requires_active_route(
    content: PCRContent,
) -> None:
    uow = FakeUnitOfWork()
    service = PCRApplicationService(uow_factory=make_uow_factory(uow))
    pcr = service.create_pcr(
        pcr_code="PCR-2026-0001",
        policy_code="CP-001",
        content=content,
        actor="user@example.com",
    )

    with pytest.raises(ApprovalRouteNotFoundError):
        service.submit_for_review(
            pcr_id=pcr.id,
            route_code="MISSING-ROUTE",
            actor="user@example.com",
        )


def test_resubmission_creates_new_workflow_for_latest_revision(
    service: PCRApplicationService,
    uow: FakeUnitOfWork,
    content: PCRContent,
) -> None:
    pcr = service.create_pcr(
        pcr_code="PCR-2026-0001",
        policy_code="CP-001",
        content=content,
        actor="user@example.com",
    )
    submitted = service.submit_for_review(
        pcr_id=pcr.id,
        route_code="POLICY-STANDARD",
        actor="user@example.com",
    )
    first_workflow = uow.approval_workflows.get_active_for_pcr(pcr.id)
    assert first_workflow is not None

    changed = submitted.model_copy(update={"status": PCRStatus.CHANGES_REQUIRED})
    uow.pcrs.save(changed)
    uow.approval_workflows.save(
        first_workflow.model_copy(update={"status": ApprovalWorkflowStatus.CHANGES_REQUIRED})
    )

    revised_content = content.model_copy(
        update={"impact_summary": "Expanded customer and underwriting impact."}
    )
    revised = service.save_revision(
        pcr_id=pcr.id,
        content=revised_content,
        actor="user@example.com",
    )
    resubmitted = service.submit_for_review(
        pcr_id=pcr.id,
        route_code="POLICY-STANDARD",
        actor="user@example.com",
    )

    workflows = list(uow.approval_workflows.items.values())
    assert resubmitted.status == PCRStatus.IN_REVIEW
    assert len(workflows) == 2
    assert submitted.current_revision is not None
    assert revised.current_revision is not None
    assert workflows[0].revision_id == submitted.current_revision.id
    assert workflows[0].status == ApprovalWorkflowStatus.CHANGES_REQUIRED
    assert workflows[1].revision_id == revised.current_revision.id
    assert uow.audits.items[-2].event_type == AuditEventType.PCR_RESUBMITTED


def test_pcr_cannot_be_edited_in_review(
    service: PCRApplicationService,
    content: PCRContent,
) -> None:
    pcr = service.create_pcr(
        pcr_code="PCR-2026-0001",
        policy_code="CP-001",
        content=content,
        actor="user@example.com",
    )
    service.submit_for_review(
        pcr_id=pcr.id,
        route_code="POLICY-STANDARD",
        actor="user@example.com",
    )

    with pytest.raises(PCRImmutableError):
        service.save_revision(
            pcr_id=pcr.id,
            content=content,
            actor="user@example.com",
        )


def test_withdraw_pcr_is_audited(
    service: PCRApplicationService,
    uow: FakeUnitOfWork,
    content: PCRContent,
) -> None:
    pcr = service.create_pcr(
        pcr_code="PCR-2026-0001",
        policy_code="CP-001",
        content=content,
        actor="user@example.com",
    )
    withdrawn = service.withdraw_pcr(
        pcr_id=pcr.id,
        actor="user@example.com",
        reason="Change no longer required.",
    )

    assert withdrawn.status == PCRStatus.WITHDRAWN
    assert uow.audits.items[-1].event_type == AuditEventType.PCR_WITHDRAWN


def test_duplicate_pcr_code_is_rejected(
    service: PCRApplicationService,
    content: PCRContent,
) -> None:
    service.create_pcr(
        pcr_code="PCR-2026-0001",
        policy_code="CP-001",
        content=content,
        actor="user@example.com",
    )

    with pytest.raises(PCRCodeAlreadyExistsError):
        service.create_pcr(
            pcr_code="PCR-2026-0001",
            policy_code="CP-001",
            content=content,
            actor="user@example.com",
        )
