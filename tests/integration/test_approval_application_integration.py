from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

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
    ApprovalWorkflowStatus,
)
from pcr_governance_app.domain.enums import ChangeType, PCRStatus
from pcr_governance_app.domain.pcr import PCRContent
from pcr_governance_app.persistence.base import Base
from pcr_governance_app.persistence.unit_of_work import SqlAlchemyUnitOfWork


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    engine.dispose()


def test_submit_and_approve_through_sqlalchemy_unit_of_work(
    session_factory: sessionmaker[Session],
) -> None:
    def uow_factory() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    route = ApprovalRoute(
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
        ),
    )

    with uow_factory() as uow:
        uow.approval_routes.add(route)
        uow.commit()

    pcr_service = PCRApplicationService(uow_factory=uow_factory)
    approval_service = ApprovalApplicationService(uow_factory=uow_factory)

    content = PCRContent(
        title="Update affordability rules",
        description="Change affordability policy.",
        change_type=ChangeType.POLICY_CHANGE,
        rationale="Policy requires updating.",
        current_policy="Current wording.",
        proposed_policy="Proposed wording.",
        impact_summary="Underwriting impact.",
    )
    pcr = pcr_service.create_pcr(
        pcr_code="PCR-2026-0001",
        policy_code="CP-001",
        content=content,
        actor="author@example.com",
    )
    submitted = pcr_service.submit_for_review(
        pcr_id=pcr.id,
        route_code="POLICY-STANDARD",
        actor="author@example.com",
    )

    assert submitted.status == PCRStatus.IN_REVIEW

    with uow_factory() as uow:
        workflow = uow.approval_workflows.get_active_for_pcr(pcr.id)
        assert workflow is not None
        requirement = workflow.stages[0].requirements[0]
        workflow_id = workflow.id

    result = approval_service.approve(
        workflow_id=workflow_id,
        principal=ApprovalPrincipal(
            user_id="manager@example.com",
            roles=frozenset({"Credit Risk Manager"}),
        ),
        requirement_id=requirement.id,
    )

    assert result.workflow.status == ApprovalWorkflowStatus.APPROVED

    with uow_factory() as uow:
        stored_pcr = uow.pcrs.get(pcr.id)
        stored_workflow = uow.approval_workflows.get(workflow_id)
        events = uow.audits.list_for_pcr(pcr.id)

    assert stored_pcr is not None
    assert stored_pcr.status == PCRStatus.APPROVED
    assert stored_workflow is not None
    assert stored_workflow.status == ApprovalWorkflowStatus.APPROVED
    assert len(stored_workflow.decisions) == 1
    assert events[-1].event_type.value == "pcr_approved"
