from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from pcr_governance_app.application.revision_service import PCRRevisionService
from pcr_governance_app.domain.approval import (
    ApprovalPrincipal,
    ApprovalRequirement,
    ApprovalRoute,
    ApprovalSelector,
    ApprovalSelectorType,
    ApprovalStage,
    ApprovalStageMode,
)
from pcr_governance_app.domain.approval_engine import ApprovalEngine
from pcr_governance_app.domain.enums import ChangeType, PCRStatus
from pcr_governance_app.domain.pcr import PCR, PCRContent
from pcr_governance_app.domain.transitions import PCRStateMachine
from pcr_governance_app.persistence.base import Base
from pcr_governance_app.persistence.sqlalchemy_approval_repository import (
    SqlAlchemyApprovalRouteRepository,
    SqlAlchemyApprovalWorkflowRepository,
)
from pcr_governance_app.persistence.sqlalchemy_repository import SqlAlchemyPCRRepository


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    with factory() as db_session:
        yield db_session

    engine.dispose()


def make_route(*, version: int = 1) -> ApprovalRoute:
    return ApprovalRoute(
        route_code="POLICY-STANDARD",
        version=version,
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


def make_review_pcr() -> PCR:
    content = PCRContent(
        title="Update affordability rules",
        description="Change affordability policy.",
        change_type=ChangeType.POLICY_CHANGE,
        rationale="Policy requires updating.",
        current_policy="Current wording.",
        proposed_policy="Proposed wording.",
        impact_summary="Underwriting impact.",
    )
    pcr = PCR(
        pcr_code="PCR-2026-0001",
        policy_code="CP-001",
        created_by="author@example.com",
    )
    pcr = PCRRevisionService.create_revision(
        pcr=pcr,
        content=content,
        actor="author@example.com",
    )
    return PCRStateMachine.transition(pcr, PCRStatus.IN_REVIEW)


def test_approval_route_round_trip(session: Session) -> None:
    repository = SqlAlchemyApprovalRouteRepository(session)
    route = make_route()

    repository.add(route)
    retrieved = repository.get(route.id)

    assert retrieved == route


def test_get_active_by_code_returns_highest_version(session: Session) -> None:
    repository = SqlAlchemyApprovalRouteRepository(session)
    repository.add(make_route(version=1))
    route_v2 = make_route(version=2)
    repository.add(route_v2)

    retrieved = repository.get_active_by_code("POLICY-STANDARD")

    assert retrieved is not None
    assert retrieved.id == route_v2.id
    assert retrieved.version == 2


def test_approval_workflow_round_trip_and_decision_append(session: Session) -> None:
    route_repository = SqlAlchemyApprovalRouteRepository(session)
    workflow_repository = SqlAlchemyApprovalWorkflowRepository(session)
    pcr_repository = SqlAlchemyPCRRepository(session)

    route = make_route()
    pcr = make_review_pcr()
    route_repository.add(route)
    pcr_repository.add(pcr)

    workflow = ApprovalEngine.create_workflow(
        pcr=pcr,
        route=route,
        actor="author@example.com",
    )
    workflow_repository.add(workflow)

    retrieved = workflow_repository.get(workflow.id)
    assert retrieved is not None
    assert pcr.current_revision is not None
    assert retrieved.id == workflow.id
    assert retrieved.revision_id == pcr.current_revision.id
    assert retrieved.stages == route.ordered_stages

    requirement = retrieved.stages[0].requirements[0]
    result = ApprovalEngine.approve(
        workflow=retrieved,
        principal=ApprovalPrincipal(
            user_id="manager@example.com",
            roles=frozenset({"Credit Risk Manager"}),
        ),
        requirement_id=requirement.id,
    )
    workflow_repository.save(result.workflow)

    updated = workflow_repository.get(workflow.id)
    assert updated is not None
    assert updated.status == result.workflow.status
    assert updated.decisions == result.workflow.decisions
