import pytest

from pcr_governance_app.domain.enums import PCRStatus
from pcr_governance_app.domain.errors import (
    InvalidPCRTransitionError,
    MissingPCRRevisionError,
)
from pcr_governance_app.domain.pcr import PCR
from pcr_governance_app.domain.transitions import PCRStateMachine


@pytest.fixture
def empty_pcr() -> PCR:
    return PCR(
        pcr_code="PCR-2026-0001",
        policy_code="CP-001",
        created_by="user@example.com",
    )


def test_draft_can_be_withdrawn(empty_pcr: PCR) -> None:
    updated = PCRStateMachine.transition(empty_pcr, PCRStatus.WITHDRAWN)
    assert updated.status == PCRStatus.WITHDRAWN


def test_draft_cannot_be_approved_directly(empty_pcr: PCR) -> None:
    with pytest.raises(InvalidPCRTransitionError):
        PCRStateMachine.transition(empty_pcr, PCRStatus.APPROVED)


def test_empty_pcr_cannot_be_submitted(empty_pcr: PCR) -> None:
    with pytest.raises(MissingPCRRevisionError):
        PCRStateMachine.transition(empty_pcr, PCRStatus.IN_REVIEW)


def test_rejected_pcr_is_terminal(empty_pcr: PCR) -> None:
    review_pcr = empty_pcr.model_copy(update={"status": PCRStatus.IN_REVIEW})
    rejected = PCRStateMachine.transition(review_pcr, PCRStatus.REJECTED)

    with pytest.raises(InvalidPCRTransitionError):
        PCRStateMachine.transition(rejected, PCRStatus.DRAFT)


def test_approved_can_become_effective(empty_pcr: PCR) -> None:
    approved = empty_pcr.model_copy(update={"status": PCRStatus.APPROVED})
    effective = PCRStateMachine.transition(approved, PCRStatus.EFFECTIVE)
    assert effective.status == PCRStatus.EFFECTIVE


def test_effective_can_be_superseded(empty_pcr: PCR) -> None:
    effective = empty_pcr.model_copy(update={"status": PCRStatus.EFFECTIVE})
    superseded = PCRStateMachine.transition(effective, PCRStatus.SUPERSEDED)
    assert superseded.status == PCRStatus.SUPERSEDED


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (PCRStatus.DRAFT, PCRStatus.WITHDRAWN),
        (PCRStatus.IN_REVIEW, PCRStatus.CHANGES_REQUIRED),
        (PCRStatus.IN_REVIEW, PCRStatus.REJECTED),
        (PCRStatus.IN_REVIEW, PCRStatus.APPROVED),
        (PCRStatus.IN_REVIEW, PCRStatus.WITHDRAWN),
        (PCRStatus.CHANGES_REQUIRED, PCRStatus.DRAFT),
        (PCRStatus.CHANGES_REQUIRED, PCRStatus.WITHDRAWN),
        (PCRStatus.APPROVED, PCRStatus.EFFECTIVE),
        (PCRStatus.EFFECTIVE, PCRStatus.SUPERSEDED),
    ],
)
def test_valid_transition_pairs(source: PCRStatus, target: PCRStatus) -> None:
    pcr = PCR(
        pcr_code="PCR-2026-0001",
        policy_code="CP-001",
        created_by="user@example.com",
        status=source,
    )
    assert PCRStateMachine.can_transition(pcr, target)
