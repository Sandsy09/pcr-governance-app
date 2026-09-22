from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from pcr_governance_app.domain.audit import AuditEvent
from pcr_governance_app.persistence.mappers import (
    audit_event_record_to_domain,
    audit_event_to_record,
)
from pcr_governance_app.persistence.models import AuditEventRecord


class SqlAlchemyAuditEventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, event: AuditEvent) -> None:
        self._session.add(audit_event_to_record(event))
        self._session.flush()

    def list_for_pcr(self, pcr_id: UUID) -> list[AuditEvent]:
        statement = (
            select(AuditEventRecord)
            .where(AuditEventRecord.pcr_id == pcr_id)
            .order_by(AuditEventRecord.occurred_at, AuditEventRecord.id)
        )
        records = self._session.scalars(statement).all()
        return [audit_event_record_to_domain(record) for record in records]
