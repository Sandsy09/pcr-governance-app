from pathlib import Path

from sqlalchemy import create_engine

from pcr_governance_app.domain.enums import ChangeType
from pcr_governance_app.domain.pcr import PCRContent
from pcr_governance_app.persistence.base import Base
from pcr_governance_app.web.services import build_services


def test_ui_services_use_shared_persistence_boundary(tmp_path: Path) -> None:
    database_path = tmp_path / "pcr-ui.db"
    database_url = f"sqlite+pysqlite:///{database_path}"

    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    engine.dispose()

    services = build_services(database_url)
    content = PCRContent(
        title="Update affordability rules",
        description="Change affordability policy.",
        change_type=ChangeType.POLICY_CHANGE,
        rationale="Policy requires updating.",
        current_policy="Current wording.",
        proposed_policy="Proposed wording.",
        impact_summary="Underwriting impact.",
    )

    created = services.pcr_commands.create_pcr(
        pcr_code="PCR-2026-0001",
        policy_code="CP-001",
        content=content,
        actor="user@example.com",
    )

    listed = services.pcr_queries.list_pcrs()
    retrieved = services.pcr_queries.get_pcr(created.id)
    events = services.pcr_queries.list_audit_events(created.id)

    assert [pcr.id for pcr in listed] == [created.id]
    assert retrieved == created
    assert len(events) == 2

    services.close()
