import pytest

from pcr_governance_app.application.revision_service import PCRRevisionService
from pcr_governance_app.domain.enums import ChangeType, PCRStatus
from pcr_governance_app.domain.errors import PCRImmutableError
from pcr_governance_app.domain.pcr import PCR, PCRContent
from pcr_governance_app.domain.transitions import PCRStateMachine


@pytest.fixture
def content() -> PCRContent:
    return PCRContent(
        title="Update affordability rules",
        description="Change affordability policy.",
        change_type=ChangeType.POLICY_CHANGE,
        rationale="Policy requires updating.",
        current_policy="Current wording.",
        proposed_policy="Proposed wording.",
        impact_summary="Underwriting impact.",
    )


@pytest.fixture
def pcr() -> PCR:
    return PCR(
        pcr_code="PCR-2026-0001",
        policy_code="CP-001",
        created_by="user@example.com",
    )


def test_first_revision_is_revision_one(pcr: PCR, content: PCRContent) -> None:
    updated = PCRRevisionService.create_revision(
        pcr=pcr,
        content=content,
        actor="user@example.com",
    )

    assert updated.current_revision is not None
    assert updated.current_revision.revision_number == 1


def test_revision_creation_does_not_modify_original_pcr(pcr: PCR, content: PCRContent) -> None:
    updated = PCRRevisionService.create_revision(
        pcr=pcr,
        content=content,
        actor="user@example.com",
    )

    assert pcr.revisions == ()
    assert len(updated.revisions) == 1


def test_revision_numbers_increment(pcr: PCR, content: PCRContent) -> None:
    first = PCRRevisionService.create_revision(
        pcr=pcr,
        content=content,
        actor="user@example.com",
    )
    second = PCRRevisionService.create_revision(
        pcr=first,
        content=content,
        actor="user@example.com",
    )

    assert len(second.revisions) == 2
    assert second.revisions[0].revision_number == 1
    assert second.revisions[1].revision_number == 2


def test_pcr_under_review_cannot_be_edited(pcr: PCR, content: PCRContent) -> None:
    updated = PCRRevisionService.create_revision(
        pcr=pcr,
        content=content,
        actor="user@example.com",
    )
    submitted = PCRStateMachine.transition(updated, PCRStatus.IN_REVIEW)

    with pytest.raises(PCRImmutableError):
        PCRRevisionService.create_revision(
            pcr=submitted,
            content=content,
            actor="user@example.com",
        )


def test_changes_required_pcr_can_be_revised(pcr: PCR, content: PCRContent) -> None:
    updated = PCRRevisionService.create_revision(
        pcr=pcr,
        content=content,
        actor="user@example.com",
    )
    submitted = PCRStateMachine.transition(updated, PCRStatus.IN_REVIEW)
    changes_required = PCRStateMachine.transition(submitted, PCRStatus.CHANGES_REQUIRED)
    revised = PCRRevisionService.create_revision(
        pcr=changes_required,
        content=content,
        actor="user@example.com",
    )

    assert len(revised.revisions) == 2
    assert revised.current_revision is not None
    assert revised.current_revision.revision_number == 2
