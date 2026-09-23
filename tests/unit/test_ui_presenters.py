from datetime import date

from pcr_governance_app.application.revision_service import PCRRevisionService
from pcr_governance_app.domain.approval import (
    ApprovalPrincipal,
    ApprovalRequirement,
    ApprovalRoute,
    ApprovalSelector,
    ApprovalSelectorType,
    ApprovalStage,
    ApprovalStageMode,
)
from pcr_governance_app.domain.approval_engine import ApprovalEngine
from pcr_governance_app.domain.audit import AuditEvent, AuditEventType
from pcr_governance_app.domain.enums import ChangeType, CommunicationTarget, PCRStatus
from pcr_governance_app.domain.pcr import PCR, PCRContent
from pcr_governance_app.domain.transitions import PCRStateMachine
from pcr_governance_app.web.presenters import (
    approval_stage_rows,
    audit_event_rows,
    pcr_display_name,
    pcr_register_rows,
)


def make_pcr() -> PCR:
    pcr = PCR(
        pcr_code="PCR-2026-0001",
        policy_code="CP-001",
        created_by="user@example.com",
    )
    content = PCRContent(
        title="Update affordability rules",
        description="Change affordability policy.",
        change_type=ChangeType.POLICY_CHANGE,
        rationale="Policy requires updating.",
        current_policy="Current wording.",
        proposed_policy="Proposed wording.",
        affected_policy_sections=("4.2",),
        impact_summary="Underwriting impact.",
        communication_targets=frozenset({CommunicationTarget.UNDERWRITING}),
        implementation_date=date(2026, 10, 1),
    )
    return PCRRevisionService.create_revision(
        pcr=pcr,
        content=content,
        actor="user@example.com",
    )


def test_register_rows_include_current_revision_summary() -> None:
    pcr = make_pcr()

    rows = pcr_register_rows([pcr])

    assert rows[0]["PCR"] == "PCR-2026-0001"
    assert rows[0]["Policy"] == "CP-001"
    assert rows[0]["Title"] == "Update affordability rules"
    assert rows[0]["Status"] == "Draft"
    assert rows[0]["Revision"] == 1
    assert rows[0]["Implementation date"] == "2026-10-01"


def test_audit_rows_present_event_details() -> None:
    pcr = make_pcr()
    assert pcr.current_revision is not None
    event = AuditEvent(
        pcr_id=pcr.id,
        revision_id=pcr.current_revision.id,
        event_type=AuditEventType.PCR_CREATED,
        actor="user@example.com",
        details={"policy_code": "CP-001"},
    )

    rows = audit_event_rows([event])

    assert rows[0]["Event"] == "Pcr Created"
    assert rows[0]["Actor"] == "user@example.com"
    assert '"policy_code": "CP-001"' in rows[0]["Details"]


def test_approval_stage_rows_identify_current_and_completed_stages() -> None:
    pcr = PCRStateMachine.transition(make_pcr(), PCRStatus.IN_REVIEW)
    requirement_one = ApprovalRequirement(
        name="Credit Risk Manager",
        selector=ApprovalSelector(
            selector_type=ApprovalSelectorType.ROLE,
            value="Credit Risk Manager",
        ),
    )
    requirement_two = ApprovalRequirement(
        name="Compliance",
        selector=ApprovalSelector(
            selector_type=ApprovalSelectorType.DEPARTMENT,
            value="Compliance",
        ),
    )
    route = ApprovalRoute(
        route_code="POLICY-STANDARD",
        version=1,
        name="Standard policy route",
        created_by="admin@example.com",
        stages=(
            ApprovalStage(
                name="Credit Risk",
                sequence=10,
                mode=ApprovalStageMode.ALL,
                requirements=(requirement_one,),
            ),
            ApprovalStage(
                name="Compliance",
                sequence=20,
                mode=ApprovalStageMode.ALL,
                requirements=(requirement_two,),
            ),
        ),
    )
    workflow = ApprovalEngine.create_workflow(
        pcr=pcr,
        route=route,
        actor="user@example.com",
    )

    before = approval_stage_rows(workflow)
    assert before[0]["Status"] == "Current"
    assert before[1]["Status"] == "Pending"

    result = ApprovalEngine.approve(
        workflow=workflow,
        principal=ApprovalPrincipal(
            user_id="manager@example.com",
            roles=frozenset({"Credit Risk Manager"}),
        ),
        requirement_id=requirement_one.id,
    )

    after = approval_stage_rows(result.workflow)
    assert after[0]["Status"] == "Complete"
    assert after[1]["Status"] == "Current"


def test_pcr_display_name_uses_business_code_and_title() -> None:
    pcr = make_pcr()

    assert pcr_display_name(pcr) == ("PCR-2026-0001 — Update affordability rules")
