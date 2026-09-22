from uuid import UUID


class PersistenceError(Exception):
    """Base persistence-layer error."""


class PCRNotFoundError(PersistenceError):
    def __init__(self, pcr_id: UUID) -> None:
        super().__init__(f"PCR '{pcr_id}' does not exist.")


class PCRPersistenceConflictError(PersistenceError):
    """Stored PCR identity conflicts with supplied domain object."""


class ImmutableRevisionPersistenceError(PCRPersistenceConflictError):
    """An existing persisted revision was modified."""
