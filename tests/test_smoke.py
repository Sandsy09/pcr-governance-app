"""Smoke tests for pcr_governance_app."""

from pcr_governance_app import __version__


def test_version_is_available() -> None:
    assert __version__
