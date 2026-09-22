from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from pcr_governance_app.domain.pcr import PCR, PCRRevision
from pcr_governance_app.persistence.errors import (
    ImmutableRevisionPersistenceError,
    PCRNotFoundError,
    PCRPersistenceConflictError,
)
from pcr_governance_app.persistence.mappers import (
    pcr_record_to_domain,
    pcr_to_record,
    revision_record_to_domain,
    revision_to_record,
)
from pcr_governance_app.persistence.models import PCRRecord, PCRRevisionRecord


class SqlAlchemyPCRRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, pcr: PCR) -> None:
        self._session.add(pcr_to_record(pcr))
        self._session.flush()

    def get(self, pcr_id: UUID) -> PCR | None:
        record = self._get_record(pcr_id)
        return None if record is None else pcr_record_to_domain(record)

    def get_by_code(self, pcr_code: str) -> PCR | None:
        statement = (
            select(PCRRecord)
            .options(selectinload(PCRRecord.revisions))
            .where(PCRRecord.pcr_code == pcr_code)
        )
        record = self._session.scalar(statement)
        return None if record is None else pcr_record_to_domain(record)

    def list_all(self) -> list[PCR]:
        statement = (
            select(PCRRecord)
            .options(selectinload(PCRRecord.revisions))
            .order_by(PCRRecord.created_at.desc())
        )
        records = self._session.scalars(statement).all()
        return [pcr_record_to_domain(record) for record in records]

    def save(self, pcr: PCR) -> None:
        record = self._get_record(pcr.id)
        if record is None:
            raise PCRNotFoundError(pcr.id)

        self._ensure_identity_unchanged(stored=record, supplied=pcr)
        self._synchronise_revisions(stored=record, supplied=pcr)
        record.status = pcr.status.value
        self._session.flush()

    def _get_record(self, pcr_id: UUID) -> PCRRecord | None:
        statement = (
            select(PCRRecord)
            .options(selectinload(PCRRecord.revisions))
            .where(PCRRecord.id == pcr_id)
        )
        return self._session.scalar(statement)

    @staticmethod
    def _ensure_identity_unchanged(*, stored: PCRRecord, supplied: PCR) -> None:
        stored_identity = (
            stored.pcr_code,
            stored.policy_code,
            stored.supersedes_pcr_id,
            stored.created_by,
        )
        supplied_identity = (
            supplied.pcr_code,
            supplied.policy_code,
            supplied.supersedes_pcr_id,
            supplied.created_by,
        )

        if stored_identity != supplied_identity:
            raise PCRPersistenceConflictError(
                "PCR identity fields cannot be modified after creation."
            )

    def _synchronise_revisions(self, *, stored: PCRRecord, supplied: PCR) -> None:
        stored_by_id = {revision.id: revision for revision in stored.revisions}
        supplied_ids = {revision.id for revision in supplied.revisions}
        removed_ids = set(stored_by_id) - supplied_ids

        if removed_ids:
            raise ImmutableRevisionPersistenceError("Existing PCR revisions cannot be removed.")

        for revision in supplied.revisions:
            stored_revision = stored_by_id.get(revision.id)
            if stored_revision is None:
                stored.revisions.append(revision_to_record(pcr_id=supplied.id, revision=revision))
                continue

            self._ensure_revision_unchanged(
                stored=stored_revision,
                supplied=revision,
            )

    @staticmethod
    def _ensure_revision_unchanged(*, stored: PCRRevisionRecord, supplied: PCRRevision) -> None:
        stored_domain = revision_record_to_domain(stored)
        if (
            stored_domain.revision_number != supplied.revision_number
            or stored_domain.content != supplied.content
            or stored_domain.created_by != supplied.created_by
        ):
            raise ImmutableRevisionPersistenceError("Persisted PCR revisions are immutable.")
