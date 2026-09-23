from collections.abc import Iterator
from pathlib import Path

import pytest
from django.test import Client
from sqlalchemy import create_engine, select

from pcr_governance_app.persistence.base import Base
from pcr_governance_app.persistence.models import PCRRecord
from pcr_governance_app.web.services import clear_services_cache


@pytest.fixture
def database_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    database_path = tmp_path / "django-ui.db"
    url = f"sqlite+pysqlite:///{database_path}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    engine.dispose()

    clear_services_cache()
    monkeypatch.setenv("PCR_DATABASE_URL", url)
    monkeypatch.setenv("PCR_DEFAULT_ACTOR", "user@example.com")
    yield url
    clear_services_cache()


@pytest.fixture
def client() -> Client:
    return Client(HTTP_HOST="localhost")


def valid_pcr_form() -> dict[str, str]:
    return {
        "pcr_code": "PCR-2026-0001",
        "policy_code": "CP-001",
        "supersedes_pcr_id": "",
        "title": "Update affordability rules",
        "description": "Change affordability policy.",
        "change_type": "policy_change",
        "rationale": "Policy requires updating.",
        "current_policy": "Current wording.",
        "proposed_policy": "Proposed wording.",
        "affected_policy_sections": "4.2\n4.3",
        "impact_summary": "Underwriting impact.",
        "technical_change_details": "",
        "implementation_date": "2026-10-01",
    }


def test_register_page_renders_empty_state(
    database_url: str,
    client: Client,
) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert b"PCR Register" in response.content
    assert b"No PCRs have been created yet" in response.content


def test_create_page_persists_pcr_and_redirects_to_detail(
    database_url: str,
    client: Client,
) -> None:
    response = client.post("/pcrs/new/", valid_pcr_form())

    assert response.status_code == 302
    assert response.headers["Location"].startswith("/pcrs/")

    engine = create_engine(database_url)
    with engine.connect() as connection:
        pcr_codes = connection.scalars(select(PCRRecord.pcr_code)).all()
    engine.dispose()

    assert pcr_codes == ["PCR-2026-0001"]

    detail = client.get(response.headers["Location"], follow=True)
    assert detail.status_code == 200
    assert b"PCR-2026-0001 was created successfully" in detail.content
    assert b"Update affordability rules" in detail.content
    assert b"Revision history" in detail.content
    assert b"Audit trail" in detail.content
    assert b"There is no active approval workflow" in detail.content


def test_create_page_requires_current_actor(
    database_url: str,
    client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PCR_DEFAULT_ACTOR", "")
    response = client.post("/pcrs/new/", valid_pcr_form())

    assert response.status_code == 200
    assert b"A current user is required to create a PCR" in response.content


def test_register_search_and_status_filters(
    database_url: str,
    client: Client,
) -> None:
    client.post("/pcrs/new/", valid_pcr_form())

    matching = client.get(
        "/",
        {"filtered": "1", "search": "affordability", "status": "draft"},
    )
    assert matching.status_code == 200
    assert b"PCR-2026-0001" in matching.content

    excluded = client.get(
        "/",
        {"filtered": "1", "search": "affordability", "status": "approved"},
    )
    assert excluded.status_code == 200
    assert b"No PCRs match the selected filters" in excluded.content


def test_actor_can_be_changed_for_the_session(
    database_url: str,
    client: Client,
) -> None:
    response = client.post(
        "/development-actor/",
        {"current_actor": "reviewer@example.com", "next": "/pcrs/new/"},
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/pcrs/new/"

    create_response = client.post("/pcrs/new/", valid_pcr_form())
    assert create_response.status_code == 302

    engine = create_engine(database_url)
    with engine.connect() as connection:
        created_by = connection.scalar(select(PCRRecord.created_by))
    engine.dispose()
    assert created_by == "reviewer@example.com"


def test_missing_database_configuration_returns_service_unavailable(
    client: Client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_services_cache()
    monkeypatch.delenv("PCR_DATABASE_URL", raising=False)

    response = client.get("/")

    assert response.status_code == 503
    assert b"PCR_DATABASE_URL is not configured" in response.content
