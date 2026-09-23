from uuid import uuid4

import pytest
from tests.fakes import FakeUnitOfWork, make_uow_factory

from pcr_governance_app.application.errors import PCRNotFoundError
from pcr_governance_app.application.query_service import PCRQueryService
from pcr_governance_app.application.revision_service import PCRRevisionService
from pcr_governance_app.domain.approval import (
    ApprovalRequirement,
    ApprovalRoute,
    ApprovalSelector,
    ApprovalSelectorType,
    ApprovalStage,
    ApprovalStageMode,
)
from pcr_governance_app.domain.approval_engine import ApprovalEngine
from pcr_governance_app.domain.audit import AuditEvent, AuditEventType
from pcr_governance_app.domain.enums import ChangeType, PCRStatus
from pcr_governance_app.domain.pcr import PCR, PCRContent
from pcr_governance_app.domain.transitions import PCRStateMachine


@pytest.fixture
def uow() -> FakeUnitOfWork:
    return FakeUnitOfWork()


@pytest.fixture
def service(uow: FakeUnitOfWork) -> PCRQueryService:
    return PCRQueryService(make_uow_factory(uow))


def make_pcr() -> PCR:
    pcr = PCR(
        pcr_code="PCR-2026-0001",
        policy_code="CP-001",
        created_by="user@example.com",
    )
    content = PCRContent(
        title="Update affordability rules",
        description="Change affordability policy.",
        change_type=ChangeType.POLICY_CHANGE,
        rationale="Policy requires updating.",
        current_policy="Current wording.",
        proposed_policy="Proposed wording.",
        impact_summary="Underwriting impact.",
    )
    return PCRRevisionService.create_revision(
        pcr=pcr,
        content=content,
        actor="user@example.com",
    )


def test_list_pcrs_returns_repository_values(
    service: PCRQueryService,
    uow: FakeUnitOfWork,
) -> None:
    pcr = make_pcr()
    uow.pcrs.add(pcr)

    assert service.list_pcrs() == [pcr]


def test_get_pcr_returns_requested_pcr(
    service: PCRQueryService,
    uow: FakeUnitOfWork,
) -> None:
    pcr = make_pcr()
    uow.pcrs.add(pcr)

    assert service.get_pcr(pcr.id) == pcr


def test_get_pcr_raises_when_missing(service: PCRQueryService) -> None:
    with pytest.raises(PCRNotFoundError):
        service.get_pcr(uuid4())


def test_list_audit_events_returns_pcr_events(
    service: PCRQueryService,
    uow: FakeUnitOfWork,
) -> None:
    pcr = make_pcr()
    uow.pcrs.add(pcr)
    assert pcr.current_revision is not None
    event = AuditEvent(
        pcr_id=pcr.id,
        revision_id=pcr.current_revision.id,
        event_type=AuditEventType.PCR_CREATED,
        actor="user@example.com",
    )
    uow.audits.add(event)

    assert service.list_audit_events(pcr.id) == [event]


def test_active_workflow_is_returned(
    service: PCRQueryService,
    uow: FakeUnitOfWork,
) -> None:
    pcr = make_pcr()
    pcr = PCRStateMachine.transition(pcr, PCRStatus.IN_REVIEW)
    uow.pcrs.add(pcr)

    route = ApprovalRoute(
        route_code="POLICY-STANDARD",
        version=1,
        name="Standard policy route",
        created_by="admin@example.com",
        stages=(
            ApprovalStage(
                name="Credit Risk",
                sequence=10,
                mode=ApprovalStageMode.ALL,
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
    workflow = ApprovalEngine.create_workflow(
        pcr=pcr,
        route=route,
        actor="user@example.com",
    )
    uow.approval_workflows.add(workflow)

    assert service.get_active_approval_workflow(pcr.id) == workflow


def test_list_audit_events_raises_when_pcr_missing(
    service: PCRQueryService,
) -> None:
    with pytest.raises(PCRNotFoundError):
        service.list_audit_events(uuid4())


def test_active_workflow_raises_when_pcr_missing(
    service: PCRQueryService,
) -> None:
    with pytest.raises(PCRNotFoundError):
        service.get_active_approval_workflow(uuid4())
