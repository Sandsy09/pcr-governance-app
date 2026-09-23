from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from pcr_governance_app.domain.audit import AuditEvent, AuditEventType
from pcr_governance_app.domain.pcr import PCR
from pcr_governance_app.persistence.base import Base
from pcr_governance_app.persistence.unit_of_work import SqlAlchemyUnitOfWork


def test_audit_events_are_returned_in_order() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    pcr = PCR(
        pcr_code="PCR-2026-0001",
        policy_code="CP-001",
        created_by="user@example.com",
    )

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.pcrs.add(pcr)
        uow.audits.add(
            AuditEvent(
                pcr_id=pcr.id,
                event_type=AuditEventType.PCR_CREATED,
                actor="user@example.com",
            )
        )
        uow.audits.add(
            AuditEvent(
                pcr_id=pcr.id,
                event_type=AuditEventType.PCR_WITHDRAWN,
                actor="user@example.com",
                details={"reason": "No longer required."},
            )
        )
        uow.commit()

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        events = uow.audits.list_for_pcr(pcr.id)

    assert [event.event_type for event in events] == [
        AuditEventType.PCR_CREATED,
        AuditEventType.PCR_WITHDRAWN,
    ]

    engine.dispose()
