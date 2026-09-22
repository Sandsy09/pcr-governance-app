from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from pcr_governance_app.domain.approval import ApprovalRoute, ApprovalWorkflow
from pcr_governance_app.persistence.errors import PCRPersistenceConflictError
from pcr_governance_app.persistence.mappers import (
    approval_decision_record_to_domain,
    approval_decision_to_record,
    approval_route_record_to_domain,
    approval_route_to_record,
    approval_workflow_record_to_domain,
    approval_workflow_to_record,
    to_database_datetime,
)
from pcr_governance_app.persistence.models import (
    ApprovalRouteRecord,
    ApprovalStageRecord,
    ApprovalWorkflowRecord,
)


class SqlAlchemyApprovalRouteRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, route: ApprovalRoute) -> None:
        self._session.add(approval_route_to_record(route))
        self._session.flush()

    def get(self, route_id: UUID) -> ApprovalRoute | None:
        record = self._get_record(route_id)
        if record is None:
            return None
        return approval_route_record_to_domain(record)

    def get_active_by_code(self, route_code: str) -> ApprovalRoute | None:
        statement = (
            select(ApprovalRouteRecord)
            .options(
                selectinload(ApprovalRouteRecord.stages).selectinload(
                    ApprovalStageRecord.requirements
                )
            )
            .where(
                ApprovalRouteRecord.route_code == route_code,
                ApprovalRouteRecord.active.is_(True),
            )
            .order_by(ApprovalRouteRecord.version.desc())
        )
        record = self._session.scalars(statement).first()
        if record is None:
            return None
        return approval_route_record_to_domain(record)

    def list_active(self) -> list[ApprovalRoute]:
        statement = (
            select(ApprovalRouteRecord)
            .options(
                selectinload(ApprovalRouteRecord.stages).selectinload(
                    ApprovalStageRecord.requirements
                )
            )
            .where(ApprovalRouteRecord.active.is_(True))
            .order_by(
                ApprovalRouteRecord.route_code,
                ApprovalRouteRecord.version.desc(),
            )
        )
        records = self._session.scalars(statement).all()
        return [approval_route_record_to_domain(record) for record in records]

    def _get_record(self, route_id: UUID) -> ApprovalRouteRecord | None:
        statement = (
            select(ApprovalRouteRecord)
            .options(
                selectinload(ApprovalRouteRecord.stages).selectinload(
                    ApprovalStageRecord.requirements
                )
            )
            .where(ApprovalRouteRecord.id == route_id)
        )
        return self._session.scalar(statement)


class SqlAlchemyApprovalWorkflowRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, workflow: ApprovalWorkflow) -> None:
        self._session.add(approval_workflow_to_record(workflow))
        self._session.flush()

    def get(self, workflow_id: UUID) -> ApprovalWorkflow | None:
        record = self._get_record(workflow_id)
        if record is None:
            return None
        return approval_workflow_record_to_domain(record)

    def get_active_for_pcr(self, pcr_id: UUID) -> ApprovalWorkflow | None:
        statement = self._base_statement().where(
            ApprovalWorkflowRecord.pcr_id == pcr_id,
            ApprovalWorkflowRecord.status == "active",
        )
        record = self._session.scalars(statement).first()
        if record is None:
            return None
        return approval_workflow_record_to_domain(record)

    def save(self, workflow: ApprovalWorkflow) -> None:
        record = self._get_record(workflow.id)
        if record is None:
            raise PCRPersistenceConflictError(f"Approval workflow '{workflow.id}' does not exist.")

        self._ensure_identity_unchanged(stored=record, supplied=workflow)
        self._synchronise_decisions(stored=record, supplied=workflow)

        record.status = workflow.status.value
        record.completed_at = (
            to_database_datetime(workflow.completed_at)
            if workflow.completed_at is not None
            else None
        )
        self._session.flush()

    def _get_record(self, workflow_id: UUID) -> ApprovalWorkflowRecord | None:
        statement = self._base_statement().where(ApprovalWorkflowRecord.id == workflow_id)
        return self._session.scalar(statement)

    @staticmethod
    def _base_statement() -> Select[tuple[ApprovalWorkflowRecord]]:
        return select(ApprovalWorkflowRecord).options(
            selectinload(ApprovalWorkflowRecord.decisions),
            selectinload(ApprovalWorkflowRecord.route)
            .selectinload(ApprovalRouteRecord.stages)
            .selectinload(ApprovalStageRecord.requirements),
        )

    @staticmethod
    def _ensure_identity_unchanged(
        *,
        stored: ApprovalWorkflowRecord,
        supplied: ApprovalWorkflow,
    ) -> None:
        stored_identity = (
            stored.pcr_id,
            stored.revision_id,
            stored.route_id,
            stored.route_code,
            stored.route_version,
            stored.created_by,
        )
        supplied_identity = (
            supplied.pcr_id,
            supplied.revision_id,
            supplied.route_id,
            supplied.route_code,
            supplied.route_version,
            supplied.created_by,
        )
        if stored_identity != supplied_identity:
            raise PCRPersistenceConflictError(
                "Approval workflow identity fields cannot be modified after creation."
            )

    @staticmethod
    def _synchronise_decisions(
        *,
        stored: ApprovalWorkflowRecord,
        supplied: ApprovalWorkflow,
    ) -> None:
        stored_by_id = {decision.id: decision for decision in stored.decisions}
        supplied_ids = {decision.id for decision in supplied.decisions}

        if set(stored_by_id) - supplied_ids:
            raise PCRPersistenceConflictError("Existing approval decisions cannot be removed.")

        for decision in supplied.decisions:
            stored_decision = stored_by_id.get(decision.id)
            if stored_decision is None:
                stored.decisions.append(approval_decision_to_record(decision))
                continue

            if approval_decision_record_to_domain(stored_decision) != decision:
                raise PCRPersistenceConflictError("Persisted approval decisions are immutable.")
