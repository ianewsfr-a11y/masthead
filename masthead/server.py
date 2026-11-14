"""The local HTTP server: a JSON API over MastHeadService, and the static interface.

It listens on the loopback address only. Requests that do not come from the
local interface itself are refused, so a web page open in the same browser
cannot start a run or read a briefing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.mcp.errors import HorizonMcpError

from . import __version__
from . import config_view
from .domains import DomainError, get_domain, list_domains
from .env import DomainEnvironment
from .runner import RunManager, failed_source_count
from . import new_domain_api
from .service import MastHeadService

STATIC = Path(__file__).resolve().parent / "static"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]"}


def _host_only(value: str) -> str:
    value = value.strip().lower()
    if value.startswith("["):
        return value.split("]")[0] + "]"
    return value.split(":")[0]


def create_app(client_factory=None) -> FastAPI:
    app = FastAPI(title="MastHead", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
    env = DomainEnvironment()
    manager = RunManager(env=env)
    app.state.manager = manager

    def service_for(domain_id: str) -> MastHeadService:
        return MastHeadService(get_domain(domain_id), client_factory=client_factory)

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        if _host_only(request.headers.get("host", "")) not in LOCAL_HOSTS:
            return JSONResponse({"error": "MastHead only answers on this computer."}, status_code=403)
        origin = request.headers.get("origin")
        if origin and _host_only(origin.split("://", 1)[-1]) not in LOCAL_HOSTS:
            return JSONResponse({"error": "Cross-site requests are refused."}, status_code=403)
        if request.method not in ("GET", "HEAD") and "application/json" not in request.headers.get("content-type", ""):
            return JSONResponse({"error": "Requests that change something must be JSON."}, status_code=415)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
        )
        return response

    @app.exception_handler(DomainError)
    async def domain_error(_: Request, exc: DomainError):
        return JSONResponse({"error": str(exc)}, status_code=404 if "does not exist" in str(exc) else 400)

    @app.exception_handler(HorizonMcpError)
    async def horizon_error(_: Request, exc: HorizonMcpError):
        missing = exc.code.endswith("NOT_FOUND")
        detail = exc.details.get("error") if isinstance(exc.details, dict) else None
        return JSONResponse(
            {"error": exc.message + (f" {detail}" if detail else ""), "code": exc.code},
            status_code=404 if missing else 400,
        )

    @app.exception_handler(ValueError)
    async def value_error(_: Request, exc: ValueError):
        return JSONResponse({"error": str(exc)}, status_code=400)

    new_domain_api.install(app, manager)

    # -- domains -----------------------------------------------------------

    @app.get("/api/domains")
    async def domains() -> dict[str, Any]:
        items = []
        for domain in list_domains():
            meta = domain.meta()
            entry: dict[str, Any] = {"id": domain.id, "name": domain.name, "description": meta.get("description"),
                                     "draft": meta.get("draft") is True}
            try:
                service = MastHeadService(domain, client_factory=client_factory)
                ctx = service.context()
                rows = config_view.sources_view(domain, ctx.config)
                runs = service.numbered_runs()
                entry.update({
                    "sources_enabled": sum(1 for row in rows if row["enabled"]),
                    "languages": list(ctx.config.ai.languages),
                    "model": ctx.config.ai.model,
                    "runs": len(runs),
                    "last_run": runs[0]["updated_at"] if runs else None,
                })
            except (HorizonMcpError, DomainError, ValueError) as exc:
                entry["problem"] = getattr(exc, "message", None) or str(exc)
            items.append(entry)
        return {"version": __version__, "domains": items}

    @app.get("/api/domains/{domain_id}")
    async def domain_overview(domain_id: str) -> dict[str, Any]:
        domain = get_domain(domain_id)
        service = MastHeadService(domain, client_factory=client_factory)
        check = await service.validate_config(horizon_path=service.workspace)
        ctx = service.context()
        # Horizon checks the process environment; the domain's own .env counts too.
        missing = [name for name in check["missing_env"] if not env.is_available(domain, name)]
        warnings = [
            text for text in check["warnings"]
            if not (text.startswith("GITHUB_TOKEN ") and env.is_available(domain, "GITHUB_TOKEN"))
        ]
        key_available = env.is_available(domain, ctx.config.ai.api_key_env)
        # While another domain's run goes, its key is in the process and Horizon would count it here.
        needs_key = ctx.config.ai.provider.value not in ("ollama", "openai-chatgpt")
        if needs_key and not key_available and ctx.config.ai.api_key_env not in missing:
            missing.insert(0, ctx.config.ai.api_key_env)
        return {
            "id": domain.id,
            "draft": domain.meta().get("draft") is True,
            "name": domain.name,
            "description": domain.meta().get("description"),
            "folder": str(domain.path),
            "sources": config_view.sources_view(domain, ctx.config),
            "settings": config_view.settings_view(domain, service, key_available),
            "missing_env": missing,
            "warnings": warnings,
        }

    @app.post("/api/domains/{domain_id}/sources")
    async def toggle_source(domain_id: str, body: dict[str, Any]) -> dict[str, Any]:
        domain = get_domain(domain_id)
        config_view.set_source_enabled(domain, str(body.get("key", "")), bool(body.get("enabled")))
        return await domain_overview(domain_id)

    @app.post("/api/domains/{domain_id}/settings")
    async def save_settings(domain_id: str, body: dict[str, Any]) -> dict[str, Any]:
        config_view.update_settings(get_domain(domain_id), body)
        return await domain_overview(domain_id)

    # -- runs --------------------------------------------------------------

    def run_entry(run: dict[str, Any]) -> dict[str, Any]:
        meta = run.get("meta", {})
        own = meta.get("masthead") or {}
        sources_failed = failed_source_count(meta.get("fetch_report") or {})
        status = own.get("status") or ("done" if meta.get("summary_generated_at") else "partial")
        if status == "done" and sources_failed:
            status = "incomplete"  # finished, but without everything it should have read
        return {
            "run_id": run["run_id"],
            "number": run.get("number"),
            "created_at": run.get("created_at"),
            "updated_at": run.get("updated_at"),
            "stages": run.get("stages"),
            "collected": meta.get("raw_count_before_merge"),
            "scored": meta.get("scored_count"),
            "kept": meta.get("filtered_count"),
            "status": status,
            "sources_failed": sources_failed,
            "until": own.get("until"),
            "error": own.get("error"),
            "demo": bool(meta.get("masthead_demo")),
            "input_tokens": own.get("input_tokens"),
            "output_tokens": own.get("output_tokens"),
        }

    @app.get("/api/domains/{domain_id}/runs")
    async def runs(domain_id: str) -> dict[str, Any]:
        service = service_for(domain_id)
        active = manager.active()
        return {
            "runs": [run_entry(run) for run in service.numbered_runs()],
            "active_job": active if active and active["domain"] == domain_id else None,
            "busy": active is not None,
        }

    @app.post("/api/domains/{domain_id}/runs")
    async def start_run(domain_id: str, body: dict[str, Any]) -> JSONResponse:
        service = service_for(domain_id)
        ctx = service.context()
        hours = body.get("hours") or ctx.config.collection.time_window_hours
        if not isinstance(hours, int) or isinstance(hours, bool) or hours <= 0:
            raise ValueError("The time window must be a positive number of hours.")
        try:
            job = manager.start(service, hours=hours, until=str(body.get("until") or "full"))
        except RuntimeError as exc:
            return JSONResponse({"error": str(exc)}, status_code=409)
        return JSONResponse(job, status_code=202)

    @app.get("/api/jobs/{job_id}")
    async def job(job_id: str) -> JSONResponse:
        found = manager.jobs.get(job_id)
        if found is None:
            return JSONResponse({"error": "Unknown job."}, status_code=404)
        return JSONResponse(found)

    @app.post("/api/jobs/{job_id}/cancel")
    async def cancel(job_id: str) -> dict[str, Any]:
        return {"cancelled": manager.cancel(job_id)}

    @app.get("/api/domains/{domain_id}/runs/{run_id}")
    async def run_detail(domain_id: str, run_id: str) -> dict[str, Any]:
        service = service_for(domain_id)
        meta = service.get_run_meta(run_id)["meta"]
        stages = {stage: service.run_store.has_stage(run_id, stage) for stage in ("raw", "scored", "filtered", "enriched")}
        journal = service.journal(run_id)
        collected: list[dict[str, Any]] = []
        if journal is None and stages["raw"]:
            from .journal import score_of, source_label
            stage = "scored" if stages["scored"] else "raw"
            for item in service.run_store.load_items(run_id, stage)[:300]:
                collected.append({
                    "id": item["id"], "title": item.get("title"), "url": item.get("url"),
                    "source": source_label(item), "published_at": item.get("published_at"),
                    "score": score_of(item),
                })
        ctx = service.context()
        return {
            "run_id": run_id,
            "number": service.run_number(run_id),
            "meta": meta,
            "stages": stages,
            "journal": journal,
            "collected": collected,
            "languages": service.summary_languages(run_id),
            "pricing": service.domain.meta().get("pricing"),
            "max_items": ctx.config.digest.max_items,
            "demo": bool(meta.get("masthead_demo")),
        }

    @app.post("/api/domains/{domain_id}/runs/{run_id}/replay")
    async def replay(domain_id: str, run_id: str, body: dict[str, Any]) -> dict[str, Any]:
        threshold = body.get("threshold")
        if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
            raise ValueError("Give a minimum score between 0 and 10.")
        return service_for(domain_id).replay(run_id, float(threshold))

    @app.get("/api/domains/{domain_id}/runs/{run_id}/briefing")
    async def briefing(domain_id: str, run_id: str, language: str) -> dict[str, Any]:
        return service_for(domain_id).get_run_summary(run_id, language)

    # -- interface -----------------------------------------------------------

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
