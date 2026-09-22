from collections.abc import Iterable
from typing import Any, cast
from uuid import UUID

from django import forms

from pcr_governance_app.domain.enums import ChangeType, CommunicationTarget
from pcr_governance_app.domain.pcr import PCR, PCRContent
from pcr_governance_app.web.presenters import label, pcr_display_name


def _enum_choices(
    values: Iterable[ChangeType | CommunicationTarget],
) -> list[tuple[str, str]]:
    return [(value.value, label(value.value)) for value in values]


class ActorForm(forms.Form):
    current_actor = forms.CharField(
        label="Current user",
        required=False,
        max_length=320,
    )
    next = forms.CharField(required=False, widget=forms.HiddenInput)


class CreatePCRForm(forms.Form):
    pcr_code = forms.CharField(
        label="PCR code",
        max_length=100,
        widget=forms.TextInput(attrs={"placeholder": "PCR-2026-0001"}),
    )
    policy_code = forms.CharField(
        label="Policy code",
        max_length=50,
        widget=forms.TextInput(attrs={"placeholder": "CP-001"}),
    )
    supersedes_pcr_id = forms.ChoiceField(
        label="Supersedes PCR",
        required=False,
    )
    title = forms.CharField(min_length=5, max_length=200)
    description = forms.CharField(widget=forms.Textarea)
    change_type = forms.ChoiceField(choices=_enum_choices(ChangeType))
    rationale = forms.CharField(widget=forms.Textarea)
    current_policy = forms.CharField(widget=forms.Textarea)
    proposed_policy = forms.CharField(widget=forms.Textarea)
    affected_policy_sections = forms.CharField(
        required=False,
        help_text="Enter one policy section per line.",
        widget=forms.Textarea,
    )
    impact_summary = forms.CharField(widget=forms.Textarea)
    technical_change_required = forms.BooleanField(required=False)
    technical_change_details = forms.CharField(
        required=False,
        help_text="Required when a technical change is necessary.",
        widget=forms.Textarea,
    )
    communication_targets = forms.MultipleChoiceField(
        choices=_enum_choices(CommunicationTarget),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    implementation_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    def __init__(
        self,
        *args: Any,
        existing_pcrs: Iterable[PCR] = (),
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        supersedes_field = cast(forms.ChoiceField, self.fields["supersedes_pcr_id"])
        supersedes_field.choices = [
            ("", "None"),
            *((str(pcr.id), pcr_display_name(pcr)) for pcr in existing_pcrs),
        ]

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean() or {}
        if (
            cleaned_data.get("technical_change_required")
            and not str(cleaned_data.get("technical_change_details", "")).strip()
        ):
            self.add_error(
                "technical_change_details",
                "Technical change details are required when a technical change is necessary.",
            )
        return cleaned_data

    def to_content(self) -> PCRContent:
        if not self.is_valid():
            raise ValueError("Cannot build PCR content from an invalid form.")

        return PCRContent(
            title=str(self.cleaned_data["title"]).strip(),
            description=str(self.cleaned_data["description"]).strip(),
            change_type=ChangeType(str(self.cleaned_data["change_type"])),
            rationale=str(self.cleaned_data["rationale"]).strip(),
            current_policy=str(self.cleaned_data["current_policy"]).strip(),
            proposed_policy=str(self.cleaned_data["proposed_policy"]).strip(),
            affected_policy_sections=tuple(
                line.strip()
                for line in str(self.cleaned_data.get("affected_policy_sections", "")).splitlines()
                if line.strip()
            ),
            impact_summary=str(self.cleaned_data["impact_summary"]).strip(),
            technical_change_required=bool(self.cleaned_data.get("technical_change_required")),
            technical_change_details=(
                str(self.cleaned_data.get("technical_change_details", "")).strip() or None
            ),
            communication_targets=frozenset(
                CommunicationTarget(value)
                for value in self.cleaned_data.get("communication_targets", [])
            ),
            implementation_date=self.cleaned_data.get("implementation_date"),
        )

    def supersedes_id(self) -> UUID | None:
        value = str(self.cleaned_data.get("supersedes_pcr_id", "")).strip()
        return UUID(value) if value else None
