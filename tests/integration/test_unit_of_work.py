from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from pcr_governance_app.application.revision_service import PCRRevisionService
from pcr_governance_app.domain.audit import AuditEvent, AuditEventType
from pcr_governance_app.domain.enums import ChangeType
from pcr_governance_app.domain.pcr import PCR, PCRContent
from pcr_governance_app.persistence.base import Base
from pcr_governance_app.persistence.models import AuditEventRecord, PCRRecord
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


def test_pcr_and_audit_are_committed_together(session_factory: sessionmaker[Session]) -> None:
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
        created_by="user@example.com",
    )
    pcr = PCRRevisionService.create_revision(
        pcr=pcr,
        content=content,
        actor="user@example.com",
    )
    revision = pcr.current_revision
    assert revision is not None

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.pcrs.add(pcr)
        uow.audits.add(
            AuditEvent(
                pcr_id=pcr.id,
                revision_id=revision.id,
                event_type=AuditEventType.PCR_CREATED,
                actor="user@example.com",
            )
        )
        uow.commit()

    with session_factory() as session:
        pcr_count = len(session.scalars(select(PCRRecord)).all())
        audit_count = len(session.scalars(select(AuditEventRecord)).all())

    assert pcr_count == 1
    assert audit_count == 1


def test_exception_rolls_back_entire_unit_of_work(
    session_factory: sessionmaker[Session],
) -> None:
    pcr = PCR(
        pcr_code="PCR-2026-0001",
        policy_code="CP-001",
        created_by="user@example.com",
    )

    with pytest.raises(RuntimeError), SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.pcrs.add(pcr)
        uow.audits.add(
            AuditEvent(
                pcr_id=pcr.id,
                event_type=AuditEventType.PCR_CREATED,
                actor="user@example.com",
            )
        )
        raise RuntimeError("Simulated application failure.")

    with session_factory() as session:
        pcr_records = session.scalars(select(PCRRecord)).all()
        audit_records = session.scalars(select(AuditEventRecord)).all()

    assert pcr_records == []
    assert audit_records == []
