from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from pcr_governance_app.application.revision_service import PCRRevisionService
from pcr_governance_app.domain.enums import ChangeType, PCRStatus
from pcr_governance_app.domain.pcr import PCR, PCRContent
from pcr_governance_app.domain.transitions import PCRStateMachine
from pcr_governance_app.persistence.base import Base
from pcr_governance_app.persistence.errors import ImmutableRevisionPersistenceError
from pcr_governance_app.persistence.sqlalchemy_repository import SqlAlchemyPCRRepository


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as db_session:
        yield db_session

    engine.dispose()


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
def pcr() -> PCR:
    return PCR(
        pcr_code="PCR-2026-0001",
        policy_code="CP-001",
        created_by="user@example.com",
    )


def test_add_and_retrieve_pcr(session: Session, pcr: PCR, content: PCRContent) -> None:
    pcr = PCRRevisionService.create_revision(
        pcr=pcr,
        content=content,
        actor="user@example.com",
    )
    repository = SqlAlchemyPCRRepository(session)
    repository.add(pcr)
    retrieved = repository.get(pcr.id)

    assert retrieved is not None
    assert retrieved.id == pcr.id
    assert retrieved.pcr_code == pcr.pcr_code
    assert retrieved.policy_code == "CP-001"
    assert len(retrieved.revisions) == 1


def test_new_revision_is_appended(session: Session, pcr: PCR, content: PCRContent) -> None:
    repository = SqlAlchemyPCRRepository(session)
    pcr = PCRRevisionService.create_revision(
        pcr=pcr,
        content=content,
        actor="user@example.com",
    )
    repository.add(pcr)
    pcr = PCRRevisionService.create_revision(
        pcr=pcr,
        content=content,
        actor="user@example.com",
    )
    repository.save(pcr)
    retrieved = repository.get(pcr.id)

    assert retrieved is not None
    assert len(retrieved.revisions) == 2
    assert [revision.revision_number for revision in retrieved.revisions] == [1, 2]


def test_status_change_is_persisted(session: Session, pcr: PCR, content: PCRContent) -> None:
    repository = SqlAlchemyPCRRepository(session)
    pcr = PCRRevisionService.create_revision(
        pcr=pcr,
        content=content,
        actor="user@example.com",
    )
    repository.add(pcr)
    pcr = PCRStateMachine.transition(pcr, PCRStatus.IN_REVIEW)
    repository.save(pcr)
    retrieved = repository.get(pcr.id)

    assert retrieved is not None
    assert retrieved.status == PCRStatus.IN_REVIEW


def test_existing_revision_cannot_be_changed(
    session: Session, pcr: PCR, content: PCRContent
) -> None:
    repository = SqlAlchemyPCRRepository(session)
    pcr = PCRRevisionService.create_revision(
        pcr=pcr,
        content=content,
        actor="user@example.com",
    )
    repository.add(pcr)
    original_revision = pcr.revisions[0]
    changed_content = original_revision.content.model_copy(
        update={"proposed_policy": "Tampered policy text."}
    )
    changed_revision = original_revision.model_copy(update={"content": changed_content})
    tampered_pcr = pcr.model_copy(update={"revisions": (changed_revision,)})

    with pytest.raises(ImmutableRevisionPersistenceError):
        repository.save(tampered_pcr)
