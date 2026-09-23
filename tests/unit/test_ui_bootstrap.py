import pytest

from pcr_governance_app.web.services import (
    AppConfigurationError,
    get_database_url,
    get_default_actor,
)


def test_database_url_is_read_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PCR_DATABASE_URL", "sqlite+pysqlite:///test.db")

    assert get_database_url() == "sqlite+pysqlite:///test.db"


def test_missing_database_url_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PCR_DATABASE_URL", raising=False)

    with pytest.raises(AppConfigurationError):
        get_database_url()


def test_default_actor_is_optional_and_trimmed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PCR_DEFAULT_ACTOR", " user@example.com ")
    assert get_default_actor() == "user@example.com"

    monkeypatch.delenv("PCR_DEFAULT_ACTOR")
    assert get_default_actor() == ""
