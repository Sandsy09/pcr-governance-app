from collections.abc import Callable
from functools import wraps
from typing import Any
from uuid import UUID

from django.contrib import messages
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods

from pcr_governance_app.application.errors import (
    PCRApplicationError,
    PCRNotFoundError,
)
from pcr_governance_app.domain.enums import PCRStatus
from pcr_governance_app.web.context_processors import current_actor
from pcr_governance_app.web.forms import ActorForm, CreatePCRForm
from pcr_governance_app.web.presenters import (
    approval_stage_rows,
    audit_event_rows,
    label,
    pcr_register_rows,
)
from pcr_governance_app.web.services import AppConfigurationError, get_services

View = Callable[..., HttpResponse]


def configuration_required(view: View) -> View:
    @wraps(view)
    def wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        try:
            return view(request, *args, **kwargs)
        except AppConfigurationError as exc:
            return render(
                request,
                "web/configuration_error.html",
                {"configuration_error": str(exc)},
                status=503,
            )

    return wrapped


@configuration_required
def pcr_register(request: HttpRequest) -> HttpResponse:
    pcrs = get_services().pcr_queries.list_pcrs()
    search = request.GET.get("search", "").strip()
    filter_submitted = request.GET.get("filtered") == "1"
    requested_statuses = request.GET.getlist("status")
    valid_status_values = {status.value for status in PCRStatus}
    selected_status_values = {value for value in requested_statuses if value in valid_status_values}
    if not filter_submitted:
        selected_status_values = valid_status_values

    filtered = []
    for pcr in pcrs:
        revision = pcr.current_revision
        searchable = " ".join(
            (
                pcr.pcr_code,
                pcr.policy_code,
                revision.content.title if revision else "",
            )
        ).lower()
        if pcr.status.value not in selected_status_values:
            continue
        if search and search.lower() not in searchable:
            continue
        filtered.append(pcr)

    status_options = [
        {
            "value": status.value,
            "label": label(status.value),
            "selected": status.value in selected_status_values,
        }
        for status in PCRStatus
    ]
    return render(
        request,
        "web/pcr_register.html",
        {
            "has_pcrs": bool(pcrs),
            "rows": pcr_register_rows(filtered),
            "search": search,
            "status_options": status_options,
        },
    )


@configuration_required
def create_pcr(request: HttpRequest) -> HttpResponse:
    services = get_services()
    existing_pcrs = services.pcr_queries.list_pcrs()
    form = CreatePCRForm(
        request.POST or None,
        existing_pcrs=existing_pcrs,
    )
    actor = current_actor(request)

    if request.method == "POST":
        if not actor:
            form.add_error(
                None,
                "A current user is required to create a PCR.",
            )
        elif form.is_valid():
            try:
                pcr = services.pcr_commands.create_pcr(
                    pcr_code=str(form.cleaned_data["pcr_code"]).strip(),
                    policy_code=str(form.cleaned_data["policy_code"]).strip(),
                    content=form.to_content(),
                    actor=actor,
                    supersedes_pcr_id=form.supersedes_id(),
                )
            except PCRApplicationError as exc:
                form.add_error(None, str(exc))
            else:
                messages.success(
                    request,
                    f"{pcr.pcr_code} was created successfully.",
                )
                return redirect("pcr-detail", pcr_id=pcr.id)

    return render(
        request,
        "web/create_pcr.html",
        {"form": form, "actor_missing": not actor},
    )


@configuration_required
def pcr_detail(request: HttpRequest, pcr_id: UUID) -> HttpResponse:
    services = get_services()
    try:
        pcr = services.pcr_queries.get_pcr(pcr_id)
        events = services.pcr_queries.list_audit_events(pcr_id)
        workflow = services.pcr_queries.get_active_approval_workflow(pcr_id)
    except PCRNotFoundError as exc:
        raise Http404(str(exc)) from exc

    revision = pcr.current_revision
    if revision is None:
        return render(
            request,
            "web/pcr_detail.html",
            {"pcr": pcr, "revision_missing": True},
            status=500,
        )

    revision_history = sorted(
        pcr.revisions,
        key=lambda item: item.revision_number,
        reverse=True,
    )
    communication_targets = ", ".join(
        label(target.value)
        for target in sorted(
            revision.content.communication_targets,
            key=lambda target: target.value,
        )
    )
    return render(
        request,
        "web/pcr_detail.html",
        {
            "pcr": pcr,
            "revision": revision,
            "revision_history": revision_history,
            "status_label": label(pcr.status.value),
            "change_type_label": label(revision.content.change_type.value),
            "communication_targets": communication_targets or "—",
            "audit_rows": audit_event_rows(events),
            "workflow": workflow,
            "workflow_status_label": (label(workflow.status.value) if workflow else None),
            "approval_rows": (approval_stage_rows(workflow) if workflow else []),
        },
    )


@require_http_methods(["POST"])
def set_actor(request: HttpRequest) -> HttpResponse:
    form = ActorForm(request.POST)
    if form.is_valid():
        request.session["current_actor"] = form.cleaned_data["current_actor"].strip()

    next_url = form.cleaned_data.get("next") if form.is_valid() else None
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect(reverse("pcr-register"))
