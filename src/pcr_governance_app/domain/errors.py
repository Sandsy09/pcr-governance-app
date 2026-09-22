class PCRDomainError(Exception):
    """Base exception for PCR domain rule violations."""


class InvalidPCRTransitionError(PCRDomainError):
    """Raised when a PCR status transition is not permitted."""


class PCRImmutableError(PCRDomainError):
    """Raised when an attempt is made to modify an immutable PCR."""


class MissingPCRRevisionError(PCRDomainError):
    """Raised when an operation requires a PCR revision but none exists."""


class InvalidRevisionError(PCRDomainError):
    """Raised when PCR revision rules are violated."""


class ApprovalDomainError(PCRDomainError):
    """Base approval domain error."""


class ApprovalRouteError(ApprovalDomainError):
    """Raised for invalid approval-route behaviour."""


class ApprovalWorkflowStateError(ApprovalDomainError):
    """Raised when workflow state prevents an action."""


class ApprovalAuthorisationError(ApprovalDomainError):
    """Raised when an actor cannot perform an approval."""


class DuplicateApprovalDecisionError(ApprovalDomainError):
    """Raised when an approver acts twice in one stage."""
