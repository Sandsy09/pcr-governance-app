from enum import StrEnum


class PCRStatus(StrEnum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    CHANGES_REQUIRED = "changes_required"
    REJECTED = "rejected"
    APPROVED = "approved"
    EFFECTIVE = "effective"
    SUPERSEDED = "superseded"
    WITHDRAWN = "withdrawn"


class ChangeType(StrEnum):
    POLICY_CHANGE = "policy_change"
    POLICY_CLARIFICATION = "policy_clarification"
    PROCESS_CHANGE = "process_change"
    TECHNICAL_CHANGE = "technical_change"


class CommunicationTarget(StrEnum):
    SALES = "sales"
    UNDERWRITING = "underwriting"
    OPERATIONS = "operations"
    TECHNOLOGY = "technology"
