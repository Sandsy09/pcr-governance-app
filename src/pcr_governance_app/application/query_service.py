from uuid import UUID

from pcr_governance_app.application.errors import PCRNotFoundError
from pcr_governance_app.application.unit_of_work import UnitOfWorkFactory
from pcr_governance_app.domain.approval import ApprovalWorkflow
from pcr_governance_app.domain.audit import AuditEvent
from pcr_governance_app.domain.pcr import PCR


class PCRQueryService:
    """Read-only application service for PCR screens and reporting."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def list_pcrs(self) -> list[PCR]:
        with self._uow_factory() as uow:
            return uow.pcrs.list_all()

    def get_pcr(self, pcr_id: UUID) -> PCR:
        with self._uow_factory() as uow:
            pcr = uow.pcrs.get(pcr_id)
            if pcr is None:
                raise PCRNotFoundError(pcr_id)
            return pcr

    def list_audit_events(self, pcr_id: UUID) -> list[AuditEvent]:
        with self._uow_factory() as uow:
            if uow.pcrs.get(pcr_id) is None:
                raise PCRNotFoundError(pcr_id)
            return uow.audits.list_for_pcr(pcr_id)

    def get_active_approval_workflow(
        self,
        pcr_id: UUID,
    ) -> ApprovalWorkflow | None:
        with self._uow_factory() as uow:
            if uow.pcrs.get(pcr_id) is None:
                raise PCRNotFoundError(pcr_id)
            return uow.approval_workflows.get_active_for_pcr(pcr_id)
