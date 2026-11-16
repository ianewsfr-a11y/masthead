"""HTTP routes for New domain and the domain editor. The logic lives in new_domain.py and horizon_setup.py."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from . import config_view, horizon_setup, new_domain, preset_lists
from .domains import get_domain
from .runner import RunManager


def _item(body: dict[str, Any]) -> dict[str, Any]:
    """A source in the wizard's format, from {"type", "config"} or the older {"kind", fields...}."""
    if "type" in body:
        return {"type": body.get("type"), "config": body.get("config") or {}}
    return {"type": body.get("kind"), "config": {k: v for k, v in body.items() if k != "kind"}}


def install(app: FastAPI, manager: RunManager) -> None:
    @app.exception_handler(new_domain.DraftError)
    async def draft_error(_: Request, exc: new_domain.DraftError):
        return JSONResponse({"error": str(exc)}, status_code=409)

    @app.exception_handler(new_domain.ProfileError)
    async def profile_error(_: Request, exc: new_domain.ProfileError):
        return JSONResponse({"error": str(exc)}, status_code=400)

    def not_running(domain_id: str | None = None) -> JSONResponse | None:
        active = manager.active()
        if active and (domain_id is None or active["domain"] == domain_id):
            return JSONResponse({"error": "A run is in progress. Wait until it ends."}, status_code=409)
        return None

    # -- the setup, before the domain exists ------------------------------------------

    @app.post("/api/setup/parse")
    async def setup_parse(body: dict[str, Any]) -> dict[str, Any]:
        return {"lines": new_domain.parse_sources(body.get("text"))}

    @app.post("/api/setup/test")
    async def setup_test(body: dict[str, Any]) -> dict[str, Any]:
        return await horizon_setup.test(_item(body))

    @app.post("/api/setup/presets")
    async def setup_presets(body: dict[str, Any]) -> dict[str, Any]:
        return preset_lists.matches(body.get("interests"))

    @app.post("/api/domains/{domain_id}/source-presets")
    async def source_presets(domain_id: str, body: dict[str, Any]) -> dict[str, Any]:
        get_domain(domain_id)
        return preset_lists.matches(body.get("interests"))

    @app.post("/api/domains/{domain_id}/preset-share")
    async def preset_share(domain_id: str, body: dict[str, Any]):
        try:
            return preset_lists.share(get_domain(domain_id), body)
        except FileExistsError as exc:
            return JSONResponse({"error": f"A list with this id already exists: {exc}. Replace it, or choose another id.",
                                 "code": "PRESET_EXISTS"}, status_code=409)

    @app.post("/api/setup/suggest")
    async def setup_suggest(body: dict[str, Any]):
        busy = not_running()  # the shared keys must not meet a domain's run
        if busy:
            return busy
        ai = horizon_setup.ai_config(body.get("ai") or {})
        env = manager.env
        if ai.provider.value != "ollama" and not env.global_source(ai.api_key_env):
            return JSONResponse({"error": f"Suggestions use the model: enter the {ai.api_key_env} key first."},
                                status_code=400)
        existing = [{"type": item.get("type"), "description": str(item.get("config"))}
                    for item in body.get("existing") or [] if isinstance(item, dict)]
        return await new_domain.suggest(ai, body.get("interests"), existing, env.apply_shared, env.clear)

    @app.post("/api/new-domain")
    async def create(body: dict[str, Any]) -> JSONResponse:
        domain = new_domain.create_draft(body)
        return JSONResponse({"id": domain.id}, status_code=201)

    # -- an existing domain ------------------------------------------------------------

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

    @app.post("/api/domains/{domain_id}/source-test")
    async def test_source(domain_id: str, body: dict[str, Any]) -> dict[str, Any]:
        get_domain(domain_id)
        return await horizon_setup.test(_item(body))

    @app.post("/api/domains/{domain_id}/source-add")
    async def add_source(domain_id: str, body: dict[str, Any]) -> dict[str, Any]:
        new_domain.add_source(get_domain(domain_id), _item(body))
        return {"added": True}

    @app.post("/api/domains/{domain_id}/source-suggest")
    async def suggest(domain_id: str, body: dict[str, Any]):
        busy = not_running()  # this domain's key must not meet another domain's run
        if busy:
            return busy
        domain = get_domain(domain_id)
        ai, existing = new_domain.domain_suggest_args(domain, manager.env)
        return await new_domain.suggest(ai, body.get("interests"), existing,
                                        lambda: manager.env.apply(domain), manager.env.clear)

    @app.get("/api/domains/{domain_id}/profiles")
    async def profiles(domain_id: str) -> dict[str, Any]:
        return new_domain.profiles_state(get_domain(domain_id))

    @app.post("/api/domains/{domain_id}/profiles/customize")
    async def customize(domain_id: str) -> dict[str, Any]:
        return new_domain.customize_profiles(get_domain(domain_id))

    @app.post("/api/domains/{domain_id}/profile-file")
    async def save_profile_file(domain_id: str, body: dict[str, Any]) -> dict[str, Any]:
        return new_domain.save_profile_file(get_domain(domain_id), body.get("profile"), body.get("file"), body.get("text"))

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
