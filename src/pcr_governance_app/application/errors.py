from uuid import UUID


class PCRApplicationError(Exception):
    """Base application orchestration error."""


class PCRNotFoundError(PCRApplicationError):
    def __init__(self, pcr_id: UUID) -> None:
        super().__init__(f"PCR '{pcr_id}' was not found.")


class PCRCodeAlreadyExistsError(PCRApplicationError):
    def __init__(self, pcr_code: str) -> None:
        super().__init__(f"PCR code '{pcr_code}' already exists.")


class MissingReasonError(PCRApplicationError):
    """Raised when a governance action requires a reason."""


class ApprovalRouteNotFoundError(PCRApplicationError):
    def __init__(self, route_code: str) -> None:
        super().__init__(f"No active approval route exists for '{route_code}'.")


class ApprovalWorkflowNotFoundError(PCRApplicationError):
    def __init__(self, workflow_id: UUID) -> None:
        super().__init__(f"Approval workflow '{workflow_id}' was not found.")
