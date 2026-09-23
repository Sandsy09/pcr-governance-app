import pytest

from pcr_governance_app.application.revision_service import PCRRevisionService
from pcr_governance_app.domain.approval import (
    ApprovalPrincipal,
    ApprovalRequirement,
    ApprovalRoute,
    ApprovalSelector,
    ApprovalSelectorType,
    ApprovalStage,
    ApprovalStageMode,
    ApprovalWorkflowStatus,
)
from pcr_governance_app.domain.approval_engine import ApprovalEngine
from pcr_governance_app.domain.enums import ChangeType, PCRStatus
from pcr_governance_app.domain.errors import (
    ApprovalAuthorisationError,
    ApprovalWorkflowStateError,
    DuplicateApprovalDecisionError,
)
from pcr_governance_app.domain.pcr import PCR, PCRContent
from pcr_governance_app.domain.transitions import PCRStateMachine


def make_content() -> PCRContent:
    return PCRContent(
        title="Update affordability rules",
        description="Change affordability policy.",
        change_type=ChangeType.POLICY_CHANGE,
        rationale="Policy requires updating.",
        current_policy="Current wording.",
        proposed_policy="Proposed wording.",
        impact_summary="Underwriting impact.",
    )


def make_review_pcr() -> PCR:
    pcr = PCR(
        pcr_code="PCR-2026-0001",
        policy_code="CP-001",
        created_by="author@example.com",
    )
    pcr = PCRRevisionService.create_revision(
        pcr=pcr,
        content=make_content(),
        actor="author@example.com",
    )
    return PCRStateMachine.transition(pcr, PCRStatus.IN_REVIEW)


def role_requirement(name: str, role: str, min_approvals: int = 1) -> ApprovalRequirement:
    return ApprovalRequirement(
        name=name,
        selector=ApprovalSelector(
            selector_type=ApprovalSelectorType.ROLE,
            value=role,
        ),
        min_approvals=min_approvals,
    )


def department_requirement(name: str, department: str) -> ApprovalRequirement:
    return ApprovalRequirement(
        name=name,
        selector=ApprovalSelector(
            selector_type=ApprovalSelectorType.DEPARTMENT,
            value=department,
        ),
    )


def make_route(*stages: ApprovalStage, version: int = 1) -> ApprovalRoute:
    return ApprovalRoute(
        route_code="POLICY-STANDARD",
        version=version,
        name="Standard policy change",
        stages=tuple(stages),
        created_by="admin@example.com",
    )


def test_any_stage_requires_one_matching_approval() -> None:
    senior = role_requirement("Senior Credit Risk Manager", "Senior Manager")
    head = role_requirement("Head of Credit Risk", "Head of Credit Risk")
    stage = ApprovalStage(
        name="Credit Risk",
        sequence=10,
        mode=ApprovalStageMode.ANY,
        requirements=(senior, head),
    )
    workflow = ApprovalEngine.create_workflow(
        pcr=make_review_pcr(),
        route=make_route(stage),
        actor="author@example.com",
    )

    result = ApprovalEngine.approve(
        workflow=workflow,
        principal=ApprovalPrincipal(
            user_id="head@example.com",
            roles=frozenset({"Head of Credit Risk"}),
        ),
        requirement_id=head.id,
    )

    assert result.workflow.status == ApprovalWorkflowStatus.APPROVED
    assert result.completed_stage_id == stage.id


def test_all_stage_requires_every_requirement() -> None:
    compliance = department_requirement("Compliance", "Compliance")
    operations = department_requirement("Operations", "Operations")
    stage = ApprovalStage(
        name="Business Approval",
        sequence=10,
        mode=ApprovalStageMode.ALL,
        requirements=(compliance, operations),
    )
    workflow = ApprovalEngine.create_workflow(
        pcr=make_review_pcr(),
        route=make_route(stage),
        actor="author@example.com",
    )

    first = ApprovalEngine.approve(
        workflow=workflow,
        principal=ApprovalPrincipal(
            user_id="compliance@example.com",
            departments=frozenset({"Compliance"}),
        ),
        requirement_id=compliance.id,
    )

    assert first.workflow.status == ApprovalWorkflowStatus.ACTIVE
    assert first.completed_stage_id is None

    second = ApprovalEngine.approve(
        workflow=first.workflow,
        principal=ApprovalPrincipal(
            user_id="operations@example.com",
            departments=frozenset({"Operations"}),
        ),
        requirement_id=operations.id,
    )

    assert second.workflow.status == ApprovalWorkflowStatus.APPROVED
    assert second.completed_stage_id == stage.id


def test_two_approvals_can_be_required_for_role() -> None:
    managers = role_requirement(
        "Two underwriting managers",
        "Underwriting Manager",
        min_approvals=2,
    )
    stage = ApprovalStage(
        name="Underwriting",
        sequence=10,
        mode=ApprovalStageMode.ALL,
        requirements=(managers,),
    )
    workflow = ApprovalEngine.create_workflow(
        pcr=make_review_pcr(),
        route=make_route(stage),
        actor="author@example.com",
    )

    first = ApprovalEngine.approve(
        workflow=workflow,
        principal=ApprovalPrincipal(
            user_id="manager.one@example.com",
            roles=frozenset({"Underwriting Manager"}),
        ),
        requirement_id=managers.id,
    )
    assert first.workflow.status == ApprovalWorkflowStatus.ACTIVE

    second = ApprovalEngine.approve(
        workflow=first.workflow,
        principal=ApprovalPrincipal(
            user_id="manager.two@example.com",
            roles=frozenset({"Underwriting Manager"}),
        ),
        requirement_id=managers.id,
    )
    assert second.workflow.status == ApprovalWorkflowStatus.APPROVED


def test_unauthorised_user_cannot_approve() -> None:
    compliance = department_requirement("Compliance", "Compliance")
    stage = ApprovalStage(
        name="Compliance",
        sequence=10,
        mode=ApprovalStageMode.ALL,
        requirements=(compliance,),
    )
    workflow = ApprovalEngine.create_workflow(
        pcr=make_review_pcr(),
        route=make_route(stage),
        actor="author@example.com",
    )

    with pytest.raises(ApprovalAuthorisationError):
        ApprovalEngine.approve(
            workflow=workflow,
            principal=ApprovalPrincipal(
                user_id="sales@example.com",
                departments=frozenset({"Sales"}),
            ),
            requirement_id=compliance.id,
        )


def test_actor_cannot_approve_twice_in_stage() -> None:
    first_req = role_requirement("Manager A", "Manager")
    second_req = department_requirement("Credit Risk", "Credit Risk")
    stage = ApprovalStage(
        name="Combined",
        sequence=10,
        mode=ApprovalStageMode.ALL,
        requirements=(first_req, second_req),
    )
    workflow = ApprovalEngine.create_workflow(
        pcr=make_review_pcr(),
        route=make_route(stage),
        actor="author@example.com",
    )
    principal = ApprovalPrincipal(
        user_id="dual@example.com",
        roles=frozenset({"Manager"}),
        departments=frozenset({"Credit Risk"}),
    )
    first = ApprovalEngine.approve(
        workflow=workflow,
        principal=principal,
        requirement_id=first_req.id,
    )

    with pytest.raises(DuplicateApprovalDecisionError):
        ApprovalEngine.approve(
            workflow=first.workflow,
            principal=principal,
            requirement_id=second_req.id,
        )


def test_actor_cannot_satisfy_two_all_requirements_by_default() -> None:
    manager = role_requirement("Manager", "Manager")
    compliance = department_requirement("Compliance", "Compliance")
    stage = ApprovalStage(
        name="Dual requirement",
        sequence=10,
        mode=ApprovalStageMode.ALL,
        requirements=(manager, compliance),
    )
    workflow = ApprovalEngine.create_workflow(
        pcr=make_review_pcr(),
        route=make_route(stage),
        actor="author@example.com",
    )
    principal = ApprovalPrincipal(
        user_id="dual@example.com",
        roles=frozenset({"Manager"}),
        departments=frozenset({"Compliance"}),
    )

    first = ApprovalEngine.approve(
        workflow=workflow,
        principal=principal,
        requirement_id=manager.id,
    )

    assert first.workflow.status == ApprovalWorkflowStatus.ACTIVE
    with pytest.raises(DuplicateApprovalDecisionError):
        ApprovalEngine.approve(
            workflow=first.workflow,
            principal=principal,
            requirement_id=compliance.id,
        )


def test_stage_advances_when_complete() -> None:
    risk = role_requirement("Risk", "Risk Approver")
    compliance = department_requirement("Compliance", "Compliance")
    stage_one = ApprovalStage(
        name="Risk",
        sequence=10,
        mode=ApprovalStageMode.ALL,
        requirements=(risk,),
    )
    stage_two = ApprovalStage(
        name="Compliance",
        sequence=20,
        mode=ApprovalStageMode.ALL,
        requirements=(compliance,),
    )
    workflow = ApprovalEngine.create_workflow(
        pcr=make_review_pcr(),
        route=make_route(stage_one, stage_two),
        actor="author@example.com",
    )

    result = ApprovalEngine.approve(
        workflow=workflow,
        principal=ApprovalPrincipal(
            user_id="risk@example.com",
            roles=frozenset({"Risk Approver"}),
        ),
        requirement_id=risk.id,
    )

    assert result.workflow.status == ApprovalWorkflowStatus.ACTIVE
    assert result.completed_stage_id == stage_one.id
    assert ApprovalEngine.current_stage(result.workflow) == stage_two


def test_final_stage_marks_workflow_approved() -> None:
    risk = role_requirement("Risk", "Risk Approver")
    stage = ApprovalStage(
        name="Risk",
        sequence=10,
        mode=ApprovalStageMode.ALL,
        requirements=(risk,),
    )
    workflow = ApprovalEngine.create_workflow(
        pcr=make_review_pcr(),
        route=make_route(stage),
        actor="author@example.com",
    )

    result = ApprovalEngine.approve(
        workflow=workflow,
        principal=ApprovalPrincipal(
            user_id="risk@example.com",
            roles=frozenset({"Risk Approver"}),
        ),
        requirement_id=risk.id,
    )

    assert result.workflow.status == ApprovalWorkflowStatus.APPROVED
    assert result.workflow.completed_at is not None
    assert ApprovalEngine.current_stage(result.workflow) is None


def test_request_changes_terminates_workflow() -> None:
    risk = role_requirement("Risk", "Risk Approver")
    stage = ApprovalStage(
        name="Risk",
        sequence=10,
        mode=ApprovalStageMode.ALL,
        requirements=(risk,),
    )
    workflow = ApprovalEngine.create_workflow(
        pcr=make_review_pcr(),
        route=make_route(stage),
        actor="author@example.com",
    )

    result = ApprovalEngine.request_changes(
        workflow=workflow,
        principal=ApprovalPrincipal(
            user_id="risk@example.com",
            roles=frozenset({"Risk Approver"}),
        ),
        reason="Clarify customer impact.",
    )

    assert result.workflow.status == ApprovalWorkflowStatus.CHANGES_REQUIRED
    assert result.workflow.completed_at is not None
    assert result.decision.comment == "Clarify customer impact."


def test_rejection_terminates_workflow() -> None:
    risk = role_requirement("Risk", "Risk Approver")
    stage = ApprovalStage(
        name="Risk",
        sequence=10,
        mode=ApprovalStageMode.ALL,
        requirements=(risk,),
    )
    workflow = ApprovalEngine.create_workflow(
        pcr=make_review_pcr(),
        route=make_route(stage),
        actor="author@example.com",
    )

    result = ApprovalEngine.reject(
        workflow=workflow,
        principal=ApprovalPrincipal(
            user_id="risk@example.com",
            roles=frozenset({"Risk Approver"}),
        ),
        reason="Governance requirements not met.",
    )

    assert result.workflow.status == ApprovalWorkflowStatus.REJECTED
    assert result.workflow.completed_at is not None


def test_completed_workflow_rejects_further_decisions() -> None:
    risk = role_requirement("Risk", "Risk Approver")
    stage = ApprovalStage(
        name="Risk",
        sequence=10,
        mode=ApprovalStageMode.ALL,
        requirements=(risk,),
    )
    workflow = ApprovalEngine.create_workflow(
        pcr=make_review_pcr(),
        route=make_route(stage),
        actor="author@example.com",
    )
    completed = ApprovalEngine.approve(
        workflow=workflow,
        principal=ApprovalPrincipal(
            user_id="risk@example.com",
            roles=frozenset({"Risk Approver"}),
        ),
        requirement_id=risk.id,
    ).workflow

    with pytest.raises(ApprovalWorkflowStateError):
        ApprovalEngine.request_changes(
            workflow=completed,
            principal=ApprovalPrincipal(
                user_id="risk.two@example.com",
                roles=frozenset({"Risk Approver"}),
            ),
            reason="Too late.",
        )


def test_workflow_references_exact_pcr_revision() -> None:
    pcr = make_review_pcr()
    risk = role_requirement("Risk", "Risk Approver")
    stage = ApprovalStage(
        name="Risk",
        sequence=10,
        mode=ApprovalStageMode.ALL,
        requirements=(risk,),
    )
    workflow = ApprovalEngine.create_workflow(
        pcr=pcr,
        route=make_route(stage),
        actor="author@example.com",
    )

    assert pcr.current_revision is not None
    assert workflow.pcr_id == pcr.id
    assert workflow.revision_id == pcr.current_revision.id


def test_new_route_version_does_not_change_existing_workflow() -> None:
    original = role_requirement("Risk", "Risk Approver")
    stage_v1 = ApprovalStage(
        name="Risk",
        sequence=10,
        mode=ApprovalStageMode.ALL,
        requirements=(original,),
    )
    route_v1 = make_route(stage_v1, version=1)
    workflow = ApprovalEngine.create_workflow(
        pcr=make_review_pcr(),
        route=route_v1,
        actor="author@example.com",
    )

    compliance = department_requirement("Compliance", "Compliance")
    stage_v2 = ApprovalStage(
        name="Risk and Compliance",
        sequence=10,
        mode=ApprovalStageMode.ALL,
        requirements=(original, compliance),
    )
    route_v2 = make_route(stage_v2, version=2)

    assert workflow.route_version == 1
    assert workflow.stages == route_v1.ordered_stages
    assert workflow.stages != route_v2.ordered_stages
