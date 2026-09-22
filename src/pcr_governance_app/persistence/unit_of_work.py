from types import TracebackType
from typing import Self

from sqlalchemy.orm import Session, sessionmaker

from pcr_governance_app.persistence.repositories import (
    ApprovalRouteRepository,
    ApprovalWorkflowRepository,
    AuditEventRepository,
    PCRRepository,
)
from pcr_governance_app.persistence.sqlalchemy_approval_repository import (
    SqlAlchemyApprovalRouteRepository,
    SqlAlchemyApprovalWorkflowRepository,
)
from pcr_governance_app.persistence.sqlalchemy_audit_repository import (
    SqlAlchemyAuditEventRepository,
)
from pcr_governance_app.persistence.sqlalchemy_repository import SqlAlchemyPCRRepository


class SqlAlchemyUnitOfWork:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None
        self._committed = False

    def __enter__(self) -> Self:
        self._session = self._session_factory()
        self._committed = False
        self.pcrs: PCRRepository = SqlAlchemyPCRRepository(self._session)
        self.audits: AuditEventRepository = SqlAlchemyAuditEventRepository(self._session)
        self.approval_routes: ApprovalRouteRepository = SqlAlchemyApprovalRouteRepository(
            self._session
        )
        self.approval_workflows: ApprovalWorkflowRepository = SqlAlchemyApprovalWorkflowRepository(
            self._session
        )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._session is None:
            return

        try:
            if exc_type is not None or not self._committed:
                self._session.rollback()
        finally:
            self._session.close()
            self._session = None

    def commit(self) -> None:
        session = self._require_session()
        session.commit()
        self._committed = True

    def rollback(self) -> None:
        session = self._require_session()
        session.rollback()

    def _require_session(self) -> Session:
        if self._session is None:
            raise RuntimeError("Unit of Work is not active.")
        return self._session
