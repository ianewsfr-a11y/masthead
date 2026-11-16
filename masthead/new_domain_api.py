"""HTTP routes for the New domain screen. The logic lives in new_domain.py."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from . import config_view, new_domain
from .domains import get_domain
from .profile_form import ProfileFormError
from .runner import RunManager


def install(app: FastAPI, manager: RunManager) -> None:
    @app.exception_handler(new_domain.DraftError)
    async def draft_error(_: Request, exc: new_domain.DraftError):
        return JSONResponse({"error": str(exc)}, status_code=409)

    @app.exception_handler(ProfileFormError)
    async def form_error(_: Request, exc: ProfileFormError):
        return JSONResponse({"error": str(exc)}, status_code=400)

    @app.exception_handler(new_domain.HandWrittenRules)
    async def hand_written(_: Request, exc: new_domain.HandWrittenRules):
        return JSONResponse({"error": str(exc), "code": "HAND_WRITTEN_RULES", "files": exc.files}, status_code=409)

    @app.post("/api/domains/{domain_id}/subject")
    async def subject(domain_id: str, body: dict[str, Any]) -> dict[str, Any]:
        new_domain.update_subject(get_domain(domain_id), body)
        return {"saved": True}

    @app.post("/api/domains/{domain_id}/sources-enabled")
    async def sources_enabled(domain_id: str, body: dict[str, Any]) -> dict[str, Any]:
        config_view.set_sources_enabled(get_domain(domain_id), body.get("changes"))
        return {"saved": True}

    @app.post("/api/domains/{domain_id}/source-parse")
    async def source_parse(domain_id: str, body: dict[str, Any]) -> dict[str, Any]:
        get_domain(domain_id)
        return {"lines": new_domain.parse_sources(body.get("text"))}

    def not_running(domain_id: str | None = None) -> JSONResponse | None:
        active = manager.active()
        if active and (domain_id is None or active["domain"] == domain_id):
            return JSONResponse({"error": "A run is in progress. Wait until it ends."}, status_code=409)
        return None

    @app.post("/api/new-domain")
    async def create(body: dict[str, Any]) -> JSONResponse:
        domain = new_domain.create_draft(body)
        return JSONResponse({"id": domain.id}, status_code=201)

    @app.post("/api/domains/{domain_id}/source-test")
    async def test_source(domain_id: str, body: dict[str, Any]) -> dict[str, Any]:
        return await new_domain.test_source(get_domain(domain_id), str(body.get("kind", "")), body)

    @app.post("/api/domains/{domain_id}/source-add")
    async def add_source(domain_id: str, body: dict[str, Any]) -> dict[str, Any]:
        new_domain.add_source(get_domain(domain_id), str(body.get("kind", "")), body)
        return {"added": True}

    @app.post("/api/domains/{domain_id}/source-suggest")
    async def suggest(domain_id: str, body: dict[str, Any]):
        # The suggestion uses this domain's key, which must not meet another domain's run.
        busy = not_running()
        if busy:
            return busy
        return await new_domain.suggest_sources(get_domain(domain_id), body.get("interests"), manager.env)

    @app.get("/api/domains/{domain_id}/profile-form")
    async def profile_form_state(domain_id: str) -> dict[str, Any]:
        return new_domain.profile_form_state(get_domain(domain_id))

    @app.post("/api/domains/{domain_id}/profile-form")
    async def save_profile_form(domain_id: str, body: dict[str, Any]) -> dict[str, Any]:
        return new_domain.save_profile_form(get_domain(domain_id), body.get("fields"), replace=body.get("replace") is True)

    @app.post("/api/domains/{domain_id}/profile-file")
    async def save_profile_file(domain_id: str, body: dict[str, Any]) -> dict[str, Any]:
        return new_domain.save_profile_file(get_domain(domain_id), body.get("file"), body.get("text"))

    @app.post("/api/domains/{domain_id}/publish")
    async def publish(domain_id: str) -> dict[str, Any]:
        new_domain.publish(get_domain(domain_id))
        return {"draft": False}

    @app.post("/api/domains/{domain_id}/discard")
    async def discard(domain_id: str):
        busy = not_running(domain_id)
        if busy:
            return busy
        new_domain.discard(get_domain(domain_id))
        return {"discarded": True}
