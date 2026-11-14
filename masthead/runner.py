"""Run a domain's pipeline stage by stage, in the background, and report progress."""

from __future__ import annotations

import asyncio
import time
import traceback
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from src.ai.tokens import get_usage_snapshot
from src.mcp.errors import HorizonMcpError

from . import config_view
from .env import DomainEnvironment
from .service import MastHeadService

STAGES = [
    ("collect", "Collect", "Read the sources"),
    ("score", "Score", "The model scores each story"),
    ("select", "Select", "Minimum score, duplicates, limits"),
    ("write", "Write", "The model writes each kept story"),
    ("briefing", "Briefing", "Assemble the briefing in each language"),
]
UNTIL = {"collect": 1, "score": 2, "select": 3, "full": 5}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def failed_source_count(report: dict[str, Any]) -> int:
    """Failed sources as the user sees them: each feed counts, not Horizon's source groups."""
    count = 0
    for group in report.get("sources") or []:
        if group.get("failures"):
            count += len(group["failures"])
        elif group.get("status") == "failure":
            count += 1
    return count


def collect_detail(fetched: dict[str, Any], enabled_sources: int) -> str:
    report = fetched.get("fetch_report") or {}
    failed = failed_source_count(report)
    detail = f"{fetched['raw_before_merge']} collected, {fetched['fetched']} after removing repeated links"
    if failed:
        detail += f", {failed} of {max(enabled_sources, failed)} sources failed"
    return detail


class RunManager:
    """One run at a time: token usage is counted process-wide by Horizon."""

    def __init__(self, env: Any = None) -> None:
        self.jobs: dict[str, dict[str, Any]] = {}
        self._task: asyncio.Task | None = None
        self.env = env if env is not None else DomainEnvironment()

    def active(self) -> dict[str, Any] | None:
        for job in self.jobs.values():
            if job["status"] == "running":
                return job
        return None

    def start(self, service: MastHeadService, hours: int, until: str = "full") -> dict[str, Any]:
        if self.active() is not None:
            raise RuntimeError("A run is already in progress.")
        if until not in UNTIL:
            raise ValueError("Unknown stopping point.")
        # Only this domain's .env values are in the environment while it runs.
        self.env.apply(service.domain)
        job = {
            "id": uuid4().hex[:12],
            "domain": service.domain.id,
            "status": "running",
            "until": until,
            "hours": hours,
            "run_id": None,
            "started_at": _now(),
            "finished_at": None,
            "error": None,
            "note": None,
            "stages": [
                {"id": stage_id, "name": name, "hint": hint,
                 "status": "pending" if index < UNTIL[until] else "skipped",
                 "detail": None, "seconds": None, "input_tokens": 0, "output_tokens": 0}
                for index, (stage_id, name, hint) in enumerate(STAGES)
            ],
        }
        self.jobs[job["id"]] = job
        self._task = asyncio.create_task(self._execute(job, service))
        return job

    async def _stage(self, job: dict[str, Any], stage_id: str, action) -> Any:
        stage = next(s for s in job["stages"] if s["id"] == stage_id)
        stage["status"] = "running"
        before = get_usage_snapshot()
        started = time.monotonic()
        try:
            result = await action()
        except BaseException:
            stage["status"] = "failed"
            raise
        finally:
            after = get_usage_snapshot()
            stage["seconds"] = round(time.monotonic() - started, 1)
            stage["input_tokens"] = after.total_input_tokens - before.total_input_tokens
            stage["output_tokens"] = after.total_output_tokens - before.total_output_tokens
        stage["status"] = "done"
        return result

    def _record(self, job: dict[str, Any], service: MastHeadService) -> None:
        """Keep MastHead's own facts about the run next to Horizon's."""
        if not job["run_id"]:
            return
        ctx = service.context()
        service.run_store.update_meta(job["run_id"], {
            "masthead": {
                "status": job["status"],
                "until": job["until"],
                "error": job["error"],
                "note": job["note"],
                "started_at": job["started_at"],
                "finished_at": job["finished_at"],
                "model": ctx.config.ai.model,
                "provider": ctx.config.ai.provider.value,
                "stages": [
                    {key: stage[key] for key in ("id", "status", "detail", "seconds", "input_tokens", "output_tokens")}
                    for stage in job["stages"]
                ],
                "input_tokens": sum(stage["input_tokens"] for stage in job["stages"]),
                "output_tokens": sum(stage["output_tokens"] for stage in job["stages"]),
                "seconds": round(sum(stage["seconds"] or 0 for stage in job["stages"]), 1),
            }
        })

    async def _execute(self, job: dict[str, Any], service: MastHeadService) -> None:
        workspace = service.workspace
        stage_of = {stage["id"]: stage for stage in job["stages"]}

        def stop_here(note: str) -> None:
            job["note"] = note
            for stage in job["stages"]:
                if stage["status"] == "pending":
                    stage["status"] = "skipped"

        try:
            fetched = await self._stage(job, "collect", lambda: service.fetch_items(
                hours=job["hours"], horizon_path=workspace))
            job["run_id"] = fetched["run_id"]
            report = fetched.get("fetch_report") or {}
            enabled = sum(
                1 for row in config_view.sources_view(service.domain, service.context().config) if row["enabled"]
            )
            stage_of["collect"]["detail"] = collect_detail(fetched, enabled)
            if fetched["fetched"] == 0 and report.get("status") == "failure":
                stop_here(None)
                stage_of["collect"]["status"] = "failed"
                raise HorizonMcpError(
                    code="HZ_FETCH_FAILED",
                    message="Every source failed, so nothing was collected. The reason is listed for each source below.",
                )
            elif fetched["fetched"] == 0:
                stop_here("Nothing was published in this time window, so there is nothing to score.")
            elif job["until"] != "collect":
                scored = await self._stage(job, "score", lambda: service.score_items(
                    run_id=job["run_id"], horizon_path=workspace))
                stage_of["score"]["detail"] = f"{scored['scored']} scored"
                if job["until"] != "score":
                    selected = await self._stage(job, "select", lambda: service.filter_items(
                        run_id=job["run_id"], horizon_path=workspace))
                    funnel = selected["journal"]["funnel"]
                    stage_of["select"]["detail"] = (
                        f"{funnel['passing']} at or above the score, "
                        f"{funnel['after_merge']} after merging, {funnel['kept']} kept"
                    )
                    if job["until"] == "full":
                        source_stage = "filtered"
                        if selected["kept"] > 0:
                            written = await self._stage(job, "write", lambda: service.enrich_items(
                                run_id=job["run_id"], horizon_path=workspace))
                            stage_of["write"]["detail"] = (
                                f"{written['enriched']} written"
                                + (f", {written['failed']} failed" if written["failed"] else "")
                            )
                            if written["status"] != "failure":
                                source_stage = "enriched"
                        else:
                            stage_of["write"]["status"] = "skipped"
                            stage_of["write"]["detail"] = "Nothing was kept"

                        async def briefings() -> list[str]:
                            languages = list(service.context().config.ai.languages)
                            for language in languages:
                                await service.generate_summary(
                                    run_id=job["run_id"], language=language, source_stage=source_stage,
                                    horizon_path=workspace, save_to_horizon_data=True)
                            return languages

                        languages = await self._stage(job, "briefing", briefings)
                        stage_of["briefing"]["detail"] = "Languages: " + ", ".join(languages)
            job["status"] = "done"
        except asyncio.CancelledError:
            job["status"] = "cancelled"
            job["error"] = "Stopped."
            raise
        except HorizonMcpError as exc:
            job["status"] = "failed"
            details = exc.details.get("error") if isinstance(exc.details, dict) else None
            job["error"] = f"{exc.message}" + (f" {details}" if details else "")
        except Exception as exc:  # the message goes to the user; the trace to the terminal
            traceback.print_exc()
            job["status"] = "failed"
            job["error"] = str(exc) or exc.__class__.__name__
        finally:
            job["finished_at"] = _now()
            for stage in job["stages"]:
                if stage["status"] in ("pending", "running"):
                    stage["status"] = "skipped" if stage["status"] == "pending" else "failed"
            try:
                self._record(job, service)
            except Exception:
                traceback.print_exc()
            # The domain's .env values are in the process only while its run goes.
            self.env.clear()

    def cancel(self, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if job and job["status"] == "running" and self._task and not self._task.done():
            self._task.cancel()
            return True
        return False
