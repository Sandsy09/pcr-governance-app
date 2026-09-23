from datetime import date
from uuid import UUID

from pcr_governance_app.domain.enums import ChangeType, CommunicationTarget
from pcr_governance_app.domain.pcr import PCR
from pcr_governance_app.web.forms import CreatePCRForm


def valid_form_data() -> dict[str, object]:
    return {
        "pcr_code": "PCR-2026-0001",
        "policy_code": "CP-001",
        "supersedes_pcr_id": "",
        "title": "Update affordability rules",
        "description": "Change affordability policy.",
        "change_type": ChangeType.POLICY_CHANGE.value,
        "rationale": "Policy requires updating.",
        "current_policy": "Current wording.",
        "proposed_policy": "Proposed wording.",
        "affected_policy_sections": "4.2\n\n4.3 ",
        "impact_summary": "Underwriting impact.",
        "technical_change_required": "",
        "technical_change_details": "",
        "communication_targets": [
            CommunicationTarget.UNDERWRITING.value,
            CommunicationTarget.OPERATIONS.value,
        ],
        "implementation_date": "2026-10-01",
    }


def test_valid_form_builds_domain_content() -> None:
    form = CreatePCRForm(valid_form_data())

    assert form.is_valid(), form.errors
    content = form.to_content()

    assert content.change_type == ChangeType.POLICY_CHANGE
    assert content.affected_policy_sections == ("4.2", "4.3")
    assert content.communication_targets == frozenset(
        {
            CommunicationTarget.UNDERWRITING,
            CommunicationTarget.OPERATIONS,
        }
    )
    assert content.implementation_date == date(2026, 10, 1)


def test_technical_change_requires_details() -> None:
    data = valid_form_data()
    data["technical_change_required"] = "on"
    form = CreatePCRForm(data)

    assert not form.is_valid()
    assert "technical_change_details" in form.errors


def test_supersedes_choice_is_limited_to_existing_pcrs() -> None:
    existing = PCR(
        pcr_code="PCR-2025-0001",
        policy_code="CP-001",
        created_by="user@example.com",
    )
    data = valid_form_data()
    data["supersedes_pcr_id"] = str(existing.id)
    form = CreatePCRForm(data, existing_pcrs=[existing])

    assert form.is_valid(), form.errors
    assert form.supersedes_id() == UUID(str(existing.id))
