from collections.abc import Callable
from types import TracebackType
from typing import Protocol, Self

from pcr_governance_app.persistence.repositories import (
    ApprovalRouteRepository,
    ApprovalWorkflowRepository,
    AuditEventRepository,
    PCRRepository,
)


class UnitOfWork(Protocol):
    pcrs: PCRRepository
    audits: AuditEventRepository
    approval_routes: ApprovalRouteRepository
    approval_workflows: ApprovalWorkflowRepository

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


UnitOfWorkFactory = Callable[[], UnitOfWork]
