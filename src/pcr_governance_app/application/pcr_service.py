from uuid import UUID

from pcr_governance_app.application.errors import (
    ApprovalRouteNotFoundError,
    MissingReasonError,
    PCRCodeAlreadyExistsError,
    PCRNotFoundError,
)
from pcr_governance_app.application.revision_service import PCRRevisionService
from pcr_governance_app.application.unit_of_work import UnitOfWork, UnitOfWorkFactory
from pcr_governance_app.domain.approval_engine import ApprovalEngine
from pcr_governance_app.domain.audit import AuditEvent, AuditEventType
from pcr_governance_app.domain.enums import PCRStatus
from pcr_governance_app.domain.pcr import PCR, PCRContent, PCRRevision
from pcr_governance_app.domain.transitions import PCRStateMachine


class PCRApplicationService:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def create_pcr(
        self,
        *,
        pcr_code: str,
        policy_code: str,
        content: PCRContent,
        actor: str,
        supersedes_pcr_id: UUID | None = None,
    ) -> PCR:
        pcr = PCR(
            pcr_code=pcr_code,
            policy_code=policy_code,
            supersedes_pcr_id=supersedes_pcr_id,
            created_by=actor,
        )
        pcr = PCRRevisionService.create_revision(
            pcr=pcr,
            content=content,
            actor=actor,
        )
        revision = self._require_current_revision(pcr)

        with self._uow_factory() as uow:
            if uow.pcrs.get_by_code(pcr_code) is not None:
                raise PCRCodeAlreadyExistsError(pcr_code)

            uow.pcrs.add(pcr)
            uow.audits.add(
                AuditEvent(
                    pcr_id=pcr.id,
                    revision_id=revision.id,
                    event_type=AuditEventType.PCR_CREATED,
                    actor=actor,
                    details={
                        "pcr_code": pcr.pcr_code,
                        "policy_code": pcr.policy_code,
                    },
                )
            )
            uow.audits.add(
                AuditEvent(
                    pcr_id=pcr.id,
                    revision_id=revision.id,
                    event_type=AuditEventType.REVISION_CREATED,
                    actor=actor,
                    details={"revision_number": revision.revision_number},
                )
            )
            uow.commit()

        return pcr

    def save_revision(
        self,
        *,
        pcr_id: UUID,
        content: PCRContent,
        actor: str,
    ) -> PCR:
        with self._uow_factory() as uow:
            pcr = self._get_pcr(uow=uow, pcr_id=pcr_id)
            updated = PCRRevisionService.create_revision(
                pcr=pcr,
                content=content,
                actor=actor,
            )
            revision = self._require_current_revision(updated)
            uow.pcrs.save(updated)
            uow.audits.add(
                AuditEvent(
                    pcr_id=updated.id,
                    revision_id=revision.id,
                    event_type=AuditEventType.REVISION_CREATED,
                    actor=actor,
                    details={"revision_number": revision.revision_number},
                )
            )
            uow.commit()

        return updated

    def submit_for_review(
        self,
        *,
        pcr_id: UUID,
        route_code: str,
        actor: str,
    ) -> PCR:
        with self._uow_factory() as uow:
            pcr = self._get_pcr(uow=uow, pcr_id=pcr_id)
            original_status = pcr.status

            if original_status == PCRStatus.CHANGES_REQUIRED:
                pcr = PCRStateMachine.transition(pcr, PCRStatus.DRAFT)

            updated = PCRStateMachine.transition(pcr, PCRStatus.IN_REVIEW)
            revision = self._require_current_revision(updated)

            route = uow.approval_routes.get_active_by_code(route_code)
            if route is None:
                raise ApprovalRouteNotFoundError(route_code)

            workflow = ApprovalEngine.create_workflow(
                pcr=updated,
                route=route,
                actor=actor,
            )

            event_type = (
                AuditEventType.PCR_RESUBMITTED
                if original_status == PCRStatus.CHANGES_REQUIRED
                else AuditEventType.PCR_SUBMITTED
            )

            uow.pcrs.save(updated)
            uow.approval_workflows.add(workflow)

            uow.audits.add(
                AuditEvent(
                    pcr_id=updated.id,
                    revision_id=revision.id,
                    event_type=event_type,
                    actor=actor,
                    details={
                        "revision_number": revision.revision_number,
                        "from_status": original_status.value,
                        "to_status": updated.status.value,
                    },
                )
            )
            uow.audits.add(
                AuditEvent(
                    pcr_id=updated.id,
                    revision_id=revision.id,
                    event_type=AuditEventType.APPROVAL_WORKFLOW_CREATED,
                    actor=actor,
                    details={
                        "workflow_id": str(workflow.id),
                        "route_code": route.route_code,
                        "route_version": route.version,
                    },
                )
            )
            uow.commit()

        return updated

    def withdraw_pcr(
        self,
        *,
        pcr_id: UUID,
        actor: str,
        reason: str,
    ) -> PCR:
        reason = self._validate_reason(reason)

        with self._uow_factory() as uow:
            pcr = self._get_pcr(uow=uow, pcr_id=pcr_id)
            updated = PCRStateMachine.transition(pcr, PCRStatus.WITHDRAWN)
            revision = updated.current_revision
            uow.pcrs.save(updated)
            uow.audits.add(
                AuditEvent(
                    pcr_id=updated.id,
                    revision_id=revision.id if revision is not None else None,
                    event_type=AuditEventType.PCR_WITHDRAWN,
                    actor=actor,
                    details={
                        "reason": reason,
                        "from_status": pcr.status.value,
                        "to_status": updated.status.value,
                    },
                )
            )
            uow.commit()

        return updated

    @staticmethod
    def _get_pcr(*, uow: UnitOfWork, pcr_id: UUID) -> PCR:
        pcr = uow.pcrs.get(pcr_id)
        if pcr is None:
            raise PCRNotFoundError(pcr_id)
        return pcr

    @staticmethod
    def _require_current_revision(pcr: PCR) -> PCRRevision:
        revision = pcr.current_revision
        if revision is None:
            raise RuntimeError("PCR operation unexpectedly has no current revision.")
        return revision

    @staticmethod
    def _validate_reason(reason: str) -> str:
        cleaned = reason.strip()
        if not cleaned:
            raise MissingReasonError("A reason is required for this governance action.")
        return cleaned
