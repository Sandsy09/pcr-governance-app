from collections.abc import Mapping

from .enums import PCRStatus
from .errors import InvalidPCRTransitionError, MissingPCRRevisionError
from .pcr import PCR

ALLOWED_TRANSITIONS: Mapping[PCRStatus, frozenset[PCRStatus]] = {
    PCRStatus.DRAFT: frozenset({PCRStatus.IN_REVIEW, PCRStatus.WITHDRAWN}),
    PCRStatus.IN_REVIEW: frozenset(
        {
            PCRStatus.CHANGES_REQUIRED,
            PCRStatus.REJECTED,
            PCRStatus.APPROVED,
            PCRStatus.WITHDRAWN,
        }
    ),
    PCRStatus.CHANGES_REQUIRED: frozenset({PCRStatus.DRAFT, PCRStatus.WITHDRAWN}),
    PCRStatus.REJECTED: frozenset(),
    PCRStatus.APPROVED: frozenset({PCRStatus.EFFECTIVE}),
    PCRStatus.EFFECTIVE: frozenset({PCRStatus.SUPERSEDED}),
    PCRStatus.SUPERSEDED: frozenset(),
    PCRStatus.WITHDRAWN: frozenset(),
}


class PCRStateMachine:
    @staticmethod
    def allowed_targets(current_status: PCRStatus) -> frozenset[PCRStatus]:
        return ALLOWED_TRANSITIONS[current_status]

    @classmethod
    def can_transition(cls, pcr: PCR, target_status: PCRStatus) -> bool:
        return target_status in cls.allowed_targets(pcr.status)

    @classmethod
    def transition(cls, pcr: PCR, target_status: PCRStatus) -> PCR:
        if not cls.can_transition(pcr, target_status):
            raise InvalidPCRTransitionError(
                f"PCR '{pcr.pcr_code}' cannot transition from '{pcr.status}' to '{target_status}'."
            )

        cls._validate_transition(pcr=pcr, target_status=target_status)
        return pcr.model_copy(update={"status": target_status})

    @staticmethod
    def _validate_transition(*, pcr: PCR, target_status: PCRStatus) -> None:
        if target_status == PCRStatus.IN_REVIEW and pcr.current_revision is None:
            raise MissingPCRRevisionError(
                f"PCR '{pcr.pcr_code}' cannot be submitted for review without a revision."
            )
