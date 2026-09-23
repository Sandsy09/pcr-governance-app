from types import TracebackType
from typing import Self, cast
from uuid import UUID

from pcr_governance_app.application.unit_of_work import UnitOfWork, UnitOfWorkFactory
from pcr_governance_app.domain.approval import ApprovalRoute, ApprovalWorkflow
from pcr_governance_app.domain.audit import AuditEvent
from pcr_governance_app.domain.pcr import PCR


class FakePCRRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, PCR] = {}

    def add(self, pcr: PCR) -> None:
        self.items[pcr.id] = pcr

    def get(self, pcr_id: UUID) -> PCR | None:
        return self.items.get(pcr_id)

    def get_by_code(self, pcr_code: str) -> PCR | None:
        return next(
            (pcr for pcr in self.items.values() if pcr.pcr_code == pcr_code),
            None,
        )

    def list_all(self) -> list[PCR]:
        return list(self.items.values())

    def save(self, pcr: PCR) -> None:
        self.items[pcr.id] = pcr


class FakeAuditEventRepository:
    def __init__(self) -> None:
        self.items: list[AuditEvent] = []

    def add(self, event: AuditEvent) -> None:
        self.items.append(event)

    def list_for_pcr(self, pcr_id: UUID) -> list[AuditEvent]:
        return [event for event in self.items if event.pcr_id == pcr_id]


class FakeApprovalRouteRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, ApprovalRoute] = {}

    def add(self, route: ApprovalRoute) -> None:
        self.items[route.id] = route

    def get(self, route_id: UUID) -> ApprovalRoute | None:
        return self.items.get(route_id)

    def get_active_by_code(self, route_code: str) -> ApprovalRoute | None:
        matching = [
            route
            for route in self.items.values()
            if route.route_code == route_code and route.active
        ]
        if not matching:
            return None
        return max(matching, key=lambda route: route.version)

    def list_active(self) -> list[ApprovalRoute]:
        return [route for route in self.items.values() if route.active]


class FakeApprovalWorkflowRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, ApprovalWorkflow] = {}

    def add(self, workflow: ApprovalWorkflow) -> None:
        self.items[workflow.id] = workflow

    def get(self, workflow_id: UUID) -> ApprovalWorkflow | None:
        return self.items.get(workflow_id)

    def get_active_for_pcr(self, pcr_id: UUID) -> ApprovalWorkflow | None:
        return next(
            (
                workflow
                for workflow in self.items.values()
                if workflow.pcr_id == pcr_id and workflow.status.value == "active"
            ),
            None,
        )

    def save(self, workflow: ApprovalWorkflow) -> None:
        self.items[workflow.id] = workflow


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.pcrs = FakePCRRepository()
        self.audits = FakeAuditEventRepository()
        self.approval_routes = FakeApprovalRouteRepository()
        self.approval_workflows = FakeApprovalWorkflowRepository()
        self.committed = False
        self.rolled_back = False

    def __enter__(self) -> Self:
        self.committed = False
        self.rolled_back = False
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc_type is not None or not self.committed:
            self.rollback()

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


def make_uow_factory(uow: FakeUnitOfWork) -> UnitOfWorkFactory:
    # Repository attrs are concretely typed for `.items` access, so the cast below
    # papers over the resulting invariance mismatch against the UnitOfWork protocol.
    def factory() -> UnitOfWork:
        return cast(UnitOfWork, uow)

    return factory
