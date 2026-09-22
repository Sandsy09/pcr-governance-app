from dataclasses import dataclass
from functools import lru_cache
from os import environ

from sqlalchemy import Engine

from pcr_governance_app.application.pcr_service import PCRApplicationService
from pcr_governance_app.application.query_service import PCRQueryService
from pcr_governance_app.persistence.session import (
    create_database_engine,
    create_session_factory,
)
from pcr_governance_app.persistence.unit_of_work import SqlAlchemyUnitOfWork


class AppConfigurationError(RuntimeError):
    """Raised when required application configuration is missing."""


@dataclass(frozen=True)
class AppServices:
    pcr_commands: PCRApplicationService
    pcr_queries: PCRQueryService
    _engine: Engine

    def close(self) -> None:
        self._engine.dispose()


def get_database_url() -> str:
    database_url = environ.get("PCR_DATABASE_URL", "").strip()
    if not database_url:
        raise AppConfigurationError(
            "PCR_DATABASE_URL is not configured. Set it before starting the app."
        )
    return database_url


def get_default_actor() -> str:
    return environ.get("PCR_DEFAULT_ACTOR", "").strip()


def build_services(database_url: str) -> AppServices:
    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)

    def uow_factory() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    return AppServices(
        pcr_commands=PCRApplicationService(uow_factory),
        pcr_queries=PCRQueryService(uow_factory),
        _engine=engine,
    )


@lru_cache(maxsize=1)
def get_services() -> AppServices:
    return build_services(get_database_url())


def clear_services_cache() -> None:
    if get_services.cache_info().currsize:
        get_services().close()
    get_services.cache_clear()
