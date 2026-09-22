from uuid import UUID

from .approval import (
    ApprovalActionResult,
    ApprovalDecision,
    ApprovalDecisionType,
    ApprovalPrincipal,
    ApprovalRequirement,
    ApprovalRoute,
    ApprovalStage,
    ApprovalStageMode,
    ApprovalWorkflow,
    ApprovalWorkflowStatus,
)
from .enums import PCRStatus
from .errors import (
    ApprovalAuthorisationError,
    ApprovalRouteError,
    ApprovalWorkflowStateError,
    DuplicateApprovalDecisionError,
)
from .pcr import PCR
from .time import utc_now


class ApprovalEngine:
    @staticmethod
    def create_workflow(*, pcr: PCR, route: ApprovalRoute, actor: str) -> ApprovalWorkflow:
        if pcr.status != PCRStatus.IN_REVIEW:
            raise ApprovalWorkflowStateError(
                "Approval workflows can only be created for PCRs that are in review."
            )

        revision = pcr.current_revision
        if revision is None:
            raise ApprovalWorkflowStateError(
                "A PCR must have a revision before an approval workflow can be created."
            )

        if not route.active:
            raise ApprovalRouteError(f"Approval route '{route.route_code}' is inactive.")

        return ApprovalWorkflow(
            pcr_id=pcr.id,
            revision_id=revision.id,
            route_id=route.id,
            route_code=route.route_code,
            route_version=route.version,
            stages=route.ordered_stages,
            created_by=actor,
        )

    @classmethod
    def current_stage(cls, workflow: ApprovalWorkflow) -> ApprovalStage | None:
        if workflow.status != ApprovalWorkflowStatus.ACTIVE:
            return None

        for stage in workflow.stages:
            if not cls.is_stage_satisfied(workflow, stage):
                return stage

        return None

    @classmethod
    def is_requirement_satisfied(
        cls,
        workflow: ApprovalWorkflow,
        requirement: ApprovalRequirement,
    ) -> bool:
        actors = {
            decision.actor
            for decision in workflow.decisions
            if (
                decision.decision_type == ApprovalDecisionType.APPROVE
                and decision.requirement_id == requirement.id
            )
        }
        return len(actors) >= requirement.min_approvals

    @classmethod
    def is_stage_satisfied(
        cls,
        workflow: ApprovalWorkflow,
        stage: ApprovalStage,
    ) -> bool:
        satisfied = [
            cls.is_requirement_satisfied(workflow, requirement)
            for requirement in stage.requirements
        ]

        match stage.mode:
            case ApprovalStageMode.ANY:
                return any(satisfied)
            case ApprovalStageMode.ALL:
                return all(satisfied)

        return False

    @classmethod
    def approve(
        cls,
        *,
        workflow: ApprovalWorkflow,
        principal: ApprovalPrincipal,
        requirement_id: UUID,
        comment: str | None = None,
    ) -> ApprovalActionResult:
        cls._ensure_active(workflow)
        stage = cls._require_current_stage(workflow)
        requirement = cls._find_requirement(
            stage=stage,
            requirement_id=requirement_id,
        )

        if not requirement.selector.matches(principal):
            raise ApprovalAuthorisationError(
                "The current user does not satisfy this approval requirement."
            )

        if cls.is_requirement_satisfied(workflow, requirement):
            raise ApprovalWorkflowStateError(
                "This approval requirement has already been satisfied."
            )

        cls._ensure_actor_can_decide(
            workflow=workflow,
            stage=stage,
            principal=principal,
        )

        decision = ApprovalDecision(
            workflow_id=workflow.id,
            stage_id=stage.id,
            requirement_id=requirement.id,
            decision_type=ApprovalDecisionType.APPROVE,
            actor=principal.user_id,
            comment=comment,
        )

        updated = workflow.model_copy(update={"decisions": (*workflow.decisions, decision)})

        stage_completed = cls.is_stage_satisfied(updated, stage)
        workflow_completed = stage_completed and cls.current_stage(updated) is None

        if workflow_completed:
            updated = updated.model_copy(
                update={
                    "status": ApprovalWorkflowStatus.APPROVED,
                    "completed_at": utc_now(),
                }
            )

        return ApprovalActionResult(
            workflow=updated,
            decision=decision,
            completed_stage_id=stage.id if stage_completed else None,
        )

    @classmethod
    def request_changes(
        cls,
        *,
        workflow: ApprovalWorkflow,
        principal: ApprovalPrincipal,
        reason: str,
    ) -> ApprovalActionResult:
        return cls._terminal_decision(
            workflow=workflow,
            principal=principal,
            decision_type=ApprovalDecisionType.REQUEST_CHANGES,
            resulting_status=ApprovalWorkflowStatus.CHANGES_REQUIRED,
            reason=reason,
        )

    @classmethod
    def reject(
        cls,
        *,
        workflow: ApprovalWorkflow,
        principal: ApprovalPrincipal,
        reason: str,
    ) -> ApprovalActionResult:
        return cls._terminal_decision(
            workflow=workflow,
            principal=principal,
            decision_type=ApprovalDecisionType.REJECT,
            resulting_status=ApprovalWorkflowStatus.REJECTED,
            reason=reason,
        )

    @staticmethod
    def cancel(workflow: ApprovalWorkflow) -> ApprovalWorkflow:
        if workflow.status != ApprovalWorkflowStatus.ACTIVE:
            raise ApprovalWorkflowStateError("Only active approval workflows can be cancelled.")

        return workflow.model_copy(
            update={
                "status": ApprovalWorkflowStatus.CANCELLED,
                "completed_at": utc_now(),
            }
        )

    @classmethod
    def _terminal_decision(
        cls,
        *,
        workflow: ApprovalWorkflow,
        principal: ApprovalPrincipal,
        decision_type: ApprovalDecisionType,
        resulting_status: ApprovalWorkflowStatus,
        reason: str,
    ) -> ApprovalActionResult:
        cls._ensure_active(workflow)
        cleaned_reason = reason.strip()

        if not cleaned_reason:
            raise ApprovalWorkflowStateError("A reason is required.")

        stage = cls._require_current_stage(workflow)
        if not any(requirement.selector.matches(principal) for requirement in stage.requirements):
            raise ApprovalAuthorisationError(
                "The current user is not an authorised approver for this stage."
            )

        cls._ensure_actor_can_decide(
            workflow=workflow,
            stage=stage,
            principal=principal,
        )

        decision = ApprovalDecision(
            workflow_id=workflow.id,
            stage_id=stage.id,
            decision_type=decision_type,
            actor=principal.user_id,
            comment=cleaned_reason,
        )

        updated = workflow.model_copy(
            update={
                "decisions": (*workflow.decisions, decision),
                "status": resulting_status,
                "completed_at": utc_now(),
            }
        )

        return ApprovalActionResult(workflow=updated, decision=decision)

    @staticmethod
    def _ensure_active(workflow: ApprovalWorkflow) -> None:
        if workflow.status != ApprovalWorkflowStatus.ACTIVE:
            raise ApprovalWorkflowStateError("The approval workflow is no longer active.")

    @classmethod
    def _require_current_stage(cls, workflow: ApprovalWorkflow) -> ApprovalStage:
        stage = cls.current_stage(workflow)
        if stage is None:
            raise ApprovalWorkflowStateError("No approval stage is awaiting action.")
        return stage

    @staticmethod
    def _find_requirement(*, stage: ApprovalStage, requirement_id: UUID) -> ApprovalRequirement:
        for requirement in stage.requirements:
            if requirement.id == requirement_id:
                return requirement

        raise ApprovalAuthorisationError(
            "The requested approval requirement does not belong to the current stage."
        )

    @staticmethod
    def _ensure_actor_can_decide(
        *,
        workflow: ApprovalWorkflow,
        stage: ApprovalStage,
        principal: ApprovalPrincipal,
    ) -> None:
        if stage.allow_same_approver_multiple_requirements:
            return

        already_decided = any(
            decision.actor == principal.user_id and decision.stage_id == stage.id
            for decision in workflow.decisions
        )

        if already_decided:
            raise DuplicateApprovalDecisionError(
                "An approver may only make one decision within this approval stage."
            )
