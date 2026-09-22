from typing import Any

from django.http import HttpRequest

from pcr_governance_app.web.services import get_default_actor


def current_actor(request: HttpRequest) -> str:
    return str(request.session.get("current_actor", get_default_actor())).strip()


def actor_context(request: HttpRequest) -> dict[str, Any]:
    return {"current_actor": current_actor(request)}
