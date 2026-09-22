from uuid import UUID

from pcr_governance_app.domain.approval import (
    ApprovalActionResult,
    ApprovalPrincipal,
    ApprovalWorkflow,
    ApprovalWorkflowStatus,
)
from pcr_governance_app.domain.approval_engine import ApprovalEngine
from pcr_governance_app.domain.audit import AuditEvent, AuditEventType
from pcr_governance_app.domain.enums import PCRStatus
from pcr_governance_app.domain.pcr import PCR
from pcr_governance_app.domain.transitions import PCRStateMachine

from .errors import ApprovalWorkflowNotFoundError, PCRNotFoundError
from .unit_of_work import UnitOfWork, UnitOfWorkFactory


class ApprovalApplicationService:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def approve(
        self,
        *,
        workflow_id: UUID,
        principal: ApprovalPrincipal,
        requirement_id: UUID,
        comment: str | None = None,
    ) -> ApprovalActionResult:
        with self._uow_factory() as uow:
            workflow = self._get_workflow(uow=uow, workflow_id=workflow_id)
            pcr = self._get_pcr(uow=uow, pcr_id=workflow.pcr_id)

            result = ApprovalEngine.approve(
                workflow=workflow,
                principal=principal,
                requirement_id=requirement_id,
                comment=comment,
            )

            uow.approval_workflows.save(result.workflow)
            self._record_decision_audit(
                uow=uow,
                pcr=pcr,
                workflow=workflow,
                result=result,
                actor=principal.user_id,
                decision="approve",
                requirement_id=requirement_id,
            )

            if result.completed_stage_id is not None:
                uow.audits.add(
                    AuditEvent(
                        pcr_id=pcr.id,
                        revision_id=workflow.revision_id,
                        event_type=AuditEventType.APPROVAL_STAGE_COMPLETED,
                        actor=principal.user_id,
                        details={
                            "stage_id": str(result.completed_stage_id),
                        },
                    )
                )

            if result.workflow.status == ApprovalWorkflowStatus.APPROVED:
                approved_pcr = PCRStateMachine.transition(
                    pcr,
                    PCRStatus.APPROVED,
                )
                uow.pcrs.save(approved_pcr)
                uow.audits.add(
                    AuditEvent(
                        pcr_id=pcr.id,
                        revision_id=workflow.revision_id,
                        event_type=AuditEventType.PCR_APPROVED,
                        actor=principal.user_id,
                        details={
                            "workflow_id": str(workflow.id),
                        },
                    )
                )

            uow.commit()

        return result

    def request_changes(
        self,
        *,
        workflow_id: UUID,
        principal: ApprovalPrincipal,
        reason: str,
    ) -> ApprovalActionResult:
        with self._uow_factory() as uow:
            workflow = self._get_workflow(uow=uow, workflow_id=workflow_id)
            pcr = self._get_pcr(uow=uow, pcr_id=workflow.pcr_id)

            result = ApprovalEngine.request_changes(
                workflow=workflow,
                principal=principal,
                reason=reason,
            )
            updated_pcr = PCRStateMachine.transition(
                pcr,
                PCRStatus.CHANGES_REQUIRED,
            )

            uow.approval_workflows.save(result.workflow)
            uow.pcrs.save(updated_pcr)
            self._record_decision_audit(
                uow=uow,
                pcr=pcr,
                workflow=workflow,
                result=result,
                actor=principal.user_id,
                decision="request_changes",
                requirement_id=None,
            )
            uow.audits.add(
                AuditEvent(
                    pcr_id=pcr.id,
                    revision_id=workflow.revision_id,
                    event_type=AuditEventType.CHANGES_REQUESTED,
                    actor=principal.user_id,
                    details={
                        "reason": reason.strip(),
                        "from_status": pcr.status.value,
                        "to_status": updated_pcr.status.value,
                        "workflow_id": str(workflow.id),
                    },
                )
            )
            uow.commit()

        return result

    def reject(
        self,
        *,
        workflow_id: UUID,
        principal: ApprovalPrincipal,
        reason: str,
    ) -> ApprovalActionResult:
        with self._uow_factory() as uow:
            workflow = self._get_workflow(uow=uow, workflow_id=workflow_id)
            pcr = self._get_pcr(uow=uow, pcr_id=workflow.pcr_id)

            result = ApprovalEngine.reject(
                workflow=workflow,
                principal=principal,
                reason=reason,
            )
            updated_pcr = PCRStateMachine.transition(
                pcr,
                PCRStatus.REJECTED,
            )

            uow.approval_workflows.save(result.workflow)
            uow.pcrs.save(updated_pcr)
            self._record_decision_audit(
                uow=uow,
                pcr=pcr,
                workflow=workflow,
                result=result,
                actor=principal.user_id,
                decision="reject",
                requirement_id=None,
            )
            uow.audits.add(
                AuditEvent(
                    pcr_id=pcr.id,
                    revision_id=workflow.revision_id,
                    event_type=AuditEventType.PCR_REJECTED,
                    actor=principal.user_id,
                    details={
                        "reason": reason.strip(),
                        "from_status": pcr.status.value,
                        "to_status": updated_pcr.status.value,
                        "workflow_id": str(workflow.id),
                    },
                )
            )
            uow.commit()

        return result

    @staticmethod
    def _get_workflow(
        *,
        uow: UnitOfWork,
        workflow_id: UUID,
    ) -> ApprovalWorkflow:
        workflow = uow.approval_workflows.get(workflow_id)
        if workflow is None:
            raise ApprovalWorkflowNotFoundError(workflow_id)
        return workflow

    @staticmethod
    def _get_pcr(*, uow: UnitOfWork, pcr_id: UUID) -> PCR:
        pcr = uow.pcrs.get(pcr_id)
        if pcr is None:
            raise PCRNotFoundError(pcr_id)
        return pcr

    @staticmethod
    def _record_decision_audit(
        *,
        uow: UnitOfWork,
        pcr: PCR,
        workflow: ApprovalWorkflow,
        result: ApprovalActionResult,
        actor: str,
        decision: str,
        requirement_id: UUID | None,
    ) -> None:
        details: dict[str, str | int | float | bool | None] = {
            "decision": decision,
            "stage_id": str(result.decision.stage_id),
        }
        if requirement_id is not None:
            details["requirement_id"] = str(requirement_id)

        uow.audits.add(
            AuditEvent(
                pcr_id=pcr.id,
                revision_id=workflow.revision_id,
                event_type=AuditEventType.APPROVAL_DECISION_RECORDED,
                actor=actor,
                details=details,
            )
        )
