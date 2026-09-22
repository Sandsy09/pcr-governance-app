import json
from collections.abc import Iterable
from typing import Any

from pcr_governance_app.domain.approval import ApprovalWorkflow
from pcr_governance_app.domain.approval_engine import ApprovalEngine
from pcr_governance_app.domain.audit import AuditEvent
from pcr_governance_app.domain.pcr import PCR


def label(value: str) -> str:
    return value.replace("_", " ").strip().title()


def pcr_display_name(pcr: PCR) -> str:
    revision = pcr.current_revision
    title = revision.content.title if revision is not None else "No revision"
    return f"{pcr.pcr_code} — {title}"


def pcr_register_rows(pcrs: Iterable[PCR]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for pcr in sorted(pcrs, key=lambda item: item.created_at, reverse=True):
        revision = pcr.current_revision
        rows.append(
            {
                "id": str(pcr.id),
                "PCR": pcr.pcr_code,
                "Policy": pcr.policy_code,
                "Title": revision.content.title if revision else "",
                "Status": label(pcr.status.value),
                "Revision": revision.revision_number if revision else None,
                "Implementation date": (
                    revision.content.implementation_date.isoformat()
                    if revision and revision.content.implementation_date
                    else ""
                ),
                "Created by": pcr.created_by,
                "Created at": pcr.created_at.strftime("%Y-%m-%d %H:%M UTC"),
            }
        )

    return rows


def audit_event_rows(events: Iterable[AuditEvent]) -> list[dict[str, str]]:
    return [
        {
            "When": event.occurred_at.strftime("%Y-%m-%d %H:%M UTC"),
            "Event": label(event.event_type.value),
            "Actor": event.actor,
            "Details": json.dumps(event.details, sort_keys=True),
        }
        for event in sorted(events, key=lambda item: item.occurred_at)
    ]


def approval_stage_rows(workflow: ApprovalWorkflow) -> list[dict[str, str]]:
    current_stage = ApprovalEngine.current_stage(workflow)
    rows: list[dict[str, str]] = []

    for stage in workflow.stages:
        if ApprovalEngine.is_stage_satisfied(workflow, stage):
            stage_status = "Complete"
        elif current_stage is not None and current_stage.id == stage.id:
            stage_status = "Current"
        else:
            stage_status = "Pending"

        requirements = ", ".join(
            f"{requirement.name} ({requirement.min_approvals})"
            for requirement in stage.requirements
        )

        rows.append(
            {
                "Sequence": str(stage.sequence),
                "Stage": stage.name,
                "Mode": stage.mode.value.upper(),
                "Requirements": requirements,
                "Status": stage_status,
            }
        )

    return rows
