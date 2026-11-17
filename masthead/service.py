"""MastHead's service: Horizon's staged pipeline, plus the decision journal.

MastHead does not copy Horizon's engine. It subclasses the service Horizon ships
for assistants (src/mcp/service.py) and adds four things:

- every call is bound to one domain (its own config, profiles, data and runs);
- the model's answer to the duplicate-merging question is recorded, so the
  journal can say which story each duplicate merged into;
- a replay that recomputes the selection with another minimum score without
  calling the model and without touching the run's files;
- while Horizon scores, each story it has finished (the count its own progress
  bar shows in a terminal), so the interface can show the scoring as it goes.
"""

from __future__ import annotations

import time
from functools import cached_property
from pathlib import Path
from typing import Any, Callable

from rich.console import Console

from src.ai.analyzer import ContentAnalyzer
from src.ai.errors import AIProviderUnavailableError
from src.ai.prompting.deduplication import TOPIC_DEDUP_SYSTEM
from src.ai.utils import parse_json_response
from src.mcp.errors import HorizonMcpError
from src.mcp.horizon_adapter import (
    apply_source_filter,
    dicts_to_items,
    load_config,
    make_storage,
    resolve_config_path,
    resolve_horizon_path,
)
from src.mcp.service import HorizonPipelineService, PipelineContext
from src.models import ContentItem
from src.orchestrator import HorizonOrchestrator

from . import journal as jn
from .domains import Domain

JOURNAL_FILE = "masthead_decisions.json"


class _RecordingOrchestrator(HorizonOrchestrator):
    """Horizon's orchestrator, with the duplicate-merging answers written down."""

    def __init__(self, *args: Any, recorder: list, client_factory: Callable | None = None,
                 progress: "ScoringProgress | None" = None, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._recorder = recorder
        self._client_factory = client_factory
        self._progress = progress

    async def analyze_items(self, items: list[ContentItem]) -> list[ContentItem]:  # type: ignore[override]
        """Horizon's analyze_items (src/orchestrator.py), with an analyzer that reports each story."""
        if self._progress is None:
            return await super().analyze_items(items)
        self.console.print(f"{self.icons['ai']} Analyzing content with AI...")
        self._progress.start(len(items))
        analyzer = _ObservedAnalyzer(
            self.ai_client, self.profiles, console=self.console,
            concurrency=self.config.ai.analysis_concurrency,
            throttle_sec=self.config.ai.throttle_sec,
            progress=self._progress,
        )
        return await analyzer.analyze_batch(items)

    @cached_property
    def ai_client(self):  # type: ignore[override]
        if self._client_factory is not None:
            client = self._client_factory(self.config.ai)
        else:
            client = HorizonOrchestrator.ai_client.func(self)
        original = client.complete
        recorder = self._recorder

        async def complete(system: str, user: str, *args: Any, **kwargs: Any) -> str:
            response = await original(system, user, *args, **kwargs)
            if system == TOPIC_DEDUP_SYSTEM:
                recorder.append((user, parse_json_response(response)))
            return response

        client.complete = complete  # type: ignore[method-assign]
        return client


class ScoringProgress:
    """What Horizon's analyzer has finished so far: the count its own progress bar shows in a
    terminal, and each story's profile, score and reason as soon as Horizon sets them.

    `state` is one plain dict updated in place, so a job can carry it as it is.
    """

    def __init__(self) -> None:
        self.state: dict[str, Any] = {"total": 0, "done": 0, "failed": 0, "seconds": 0.0, "items": []}
        self._started = time.monotonic()

    def start(self, total: int) -> None:
        self.state.update(total=total, done=0, failed=0, seconds=0.0, items=[])
        self._started = time.monotonic()

    def finished(self, item: ContentItem, failed: bool) -> None:
        processing = item.processing
        analysis = processing.analysis if processing else None
        classification = processing.classification if processing else None
        failed = failed or analysis is None or analysis.score is None
        self.state["items"].append({
            "id": item.id,
            "title": item.title,
            "url": str(item.url),
            "source": jn.source_label(item.model_dump(mode="json")),
            "profile": classification.profile if classification else None,
            "score": None if failed else analysis.score,
            "reason": analysis.reason if analysis else None,
            "failed": failed,
        })
        self.state["done"] += 1
        self.state["failed"] += failed
        self.state["seconds"] = round(time.monotonic() - self._started, 1)


class _ObservedAnalyzer(ContentAnalyzer):
    """Horizon's analyzer, telling MastHead about each story once Horizon has finished it."""

    def __init__(self, *args: Any, progress: ScoringProgress, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._progress = progress

    async def _analyze_item(self, item: ContentItem) -> None:
        try:
            await super()._analyze_item(item)  # Horizon's own retries happen inside
        except AIProviderUnavailableError:
            raise
        except Exception:
            # Horizon then records "Analysis failed" for this story and carries on.
            self._progress.finished(item, failed=True)
            raise
        self._progress.finished(item, failed=False)


class MastHeadService(HorizonPipelineService):
    """Horizon's pipeline service bound to one domain."""

    def __init__(self, domain: Domain, client_factory: Callable | None = None, console: Console | None = None):
        super().__init__(runs_root=domain.runs_root, console=console or Console(stderr=True))
        self.domain = domain
        self.workspace = str(domain.path)
        self._client_factory = client_factory
        self._dedup_calls: list[tuple[str, Any]] = []
        self.scoring = ScoringProgress()

    # -- Horizon hooks ---------------------------------------------------

    def _orchestrator(self, ctx: PipelineContext) -> HorizonOrchestrator:
        return _RecordingOrchestrator(
            ctx.config,
            make_storage(ctx.config_path),
            console=self.console,
            profiles=self._profiles(ctx),
            recorder=self._dedup_calls,
            client_factory=self._client_factory,
            progress=self.scoring,
        )

    def _build_context(  # type: ignore[override]
        self,
        horizon_path: str | None,
        config_path: str | None,
        sources: list[str] | None,
    ) -> tuple[PipelineContext, list[str], list[str]]:
        """Horizon's context, without loading the domain's .env into the process.

        MastHead loads a domain's .env only when one of its runs starts
        (see env.DomainEnvironment), so a key never serves another domain.
        """
        resolved_horizon = resolve_horizon_path(horizon_path)
        resolved_config = resolve_config_path(resolved_horizon, config_path)
        config, selected, unknown = apply_source_filter(load_config(resolved_config), sources)
        return PipelineContext(horizon_path=resolved_horizon, config_path=resolved_config, config=config), selected, unknown

    def context(self) -> PipelineContext:
        return self._build_context(horizon_path=self.workspace, config_path=None, sources=None)[0]

    def profile_name(self, profile_id: str) -> str:
        """The name Horizon shows for a profile, or its id when the profiles cannot be read."""
        try:
            return self._profiles(self.context()).get(profile_id).definition.name
        except ValueError:
            return profile_id

    def rules_missing(self) -> str | None:
        """Why Horizon cannot load this domain's profiles yet (a new draft has none), or None."""
        try:
            self._profiles(self.context())
        except ValueError as exc:
            return str(exc)
        return None

    async def filter_items(  # type: ignore[override]
        self,
        run_id: str,
        threshold: float | None = None,
        source_stage: str = "scored",
        topic_dedup: bool = True,
        horizon_path: str | None = None,
        config_path: str | None = None,
    ) -> dict[str, Any]:
        """Horizon's selection, followed by the journal of every decision."""
        self._dedup_calls.clear()
        result = await super().filter_items(
            run_id=run_id,
            threshold=threshold,
            source_stage=source_stage,
            topic_dedup=topic_dedup,
            horizon_path=horizon_path or self.workspace,
            config_path=config_path,
        )
        scored = self.run_store.load_items(run_id, source_stage)
        kept_ids = [item["id"] for item in self.run_store.load_items(run_id, "filtered")]
        ctx = self.context()
        thresholds = self._thresholds(ctx)
        default_profile = ctx.config.processing.default_profile
        passing = [
            item for item in scored
            if jn.passes(item, jn.effective_threshold(jn.profile_of(item, default_profile), thresholds, threshold))
        ]
        clusters = jn.duplicate_clusters(passing, list(self._dedup_calls))
        merged = jn.merge_map(scored, clusters, kept_ids)
        eligible = [item for item in passing if item["id"] not in merged]
        within_groups = set(self._select(ctx, eligible, drop_max=True))
        journal = jn.build_journal(
            scored,
            kept_ids,
            thresholds=thresholds,
            default_profile=default_profile,
            override=threshold,
            clusters=clusters,
            merge_recorded=topic_dedup,
            survives_group_caps=within_groups.__contains__,
            max_items=ctx.config.digest.max_items,
        )
        self.run_store.write_json(run_id, JOURNAL_FILE, journal)
        result["journal"] = {"funnel": journal["funnel"], "counts": journal["counts"]}
        return result

    # -- MastHead additions ----------------------------------------------

    @staticmethod
    def _thresholds(ctx: PipelineContext) -> dict[str, float | None]:
        return {
            profile_id: settings.threshold
            for profile_id, settings in ctx.config.processing.profile_settings.items()
        }

    def _select(
        self,
        ctx: PipelineContext,
        eligible: list[dict[str, Any]],
        *,
        drop_max: bool = False,
        max_items: int | None = None,
    ) -> list[str]:
        """Apply Horizon's group limits and maximum to already merged items. No model call."""
        config = ctx.config.model_copy(deep=True)
        if drop_max:
            config.digest.max_items = None
        elif max_items is not None:
            config.digest.max_items = max_items
        orchestrator = HorizonOrchestrator(
            config, make_storage(ctx.config_path), console=self.console, profiles=self._profiles(ctx)
        )
        ordered = sorted(eligible, key=lambda item: -(jn.score_of(item) if jn.score_of(item) is not None else -1.0))
        balanced = orchestrator.apply_balanced_digest(dicts_to_items(ordered), log=False)
        return [item.id for item in balanced.items]

    def stored_journal(self, run_id: str) -> dict[str, Any] | None:
        try:
            return self.run_store.read_json(run_id, JOURNAL_FILE)
        except FileNotFoundError:
            return None

    def journal(self, run_id: str) -> dict[str, Any] | None:
        """The stored journal, or a partial one for runs made outside MastHead."""
        stored = self.stored_journal(run_id)
        if stored is not None and self.run_store.has_stage(run_id, "filtered"):
            return stored
        if not (self.run_store.has_stage(run_id, "scored") and self.run_store.has_stage(run_id, "filtered")):
            return None
        ctx = self.context()
        meta = self.run_store.load_meta(run_id)
        return jn.build_journal(
            self.run_store.load_items(run_id, "scored"),
            [item["id"] for item in self.run_store.load_items(run_id, "filtered")],
            thresholds=self._thresholds(ctx),
            default_profile=ctx.config.processing.default_profile,
            override=meta.get("filter_threshold_override"),
            merge_recorded=False,
        )

    def replay(self, run_id: str, threshold: float, max_items: int | None = None) -> dict[str, Any]:
        """What the run would have kept with another minimum score.

        No model call and nothing written. Duplicates found during the run are
        reused; stories that only pass at the new score were never compared with
        the others, and are flagged as such.
        """
        if not 0 <= threshold <= 10:
            raise HorizonMcpError(code="HZ_INVALID_INPUT", message="The minimum score must be between 0 and 10.")
        try:
            scored = self.run_store.load_items(run_id, "scored")
        except FileNotFoundError as exc:
            raise HorizonMcpError(code="HZ_STAGE_NOT_FOUND", message="This run has no scores to replay.") from exc
        ctx = self.context()
        thresholds = self._thresholds(ctx)
        default_profile = ctx.config.processing.default_profile
        stored = self.stored_journal(run_id)
        recorded = bool(stored and stored.get("merge_recorded"))

        passing = [item for item in scored if jn.passes(item, threshold)]
        passing_ids = {item["id"] for item in passing}
        clusters = [
            [member for member in members if member in passing_ids]
            for members in (stored.get("clusters") if stored else None) or []
        ]
        if recorded:
            compared = {
                decision["id"] for decision in stored["decisions"]
                if decision["outcome"] not in (jn.BELOW, jn.UNSCORED)
            }
            unchecked = passing_ids - compared
        else:
            unchecked = set(passing_ids)

        merged = jn.merge_map(scored, clusters)
        eligible = [item for item in passing if item["id"] not in merged]
        kept_ids = self._select(ctx, eligible, max_items=max_items)
        within_groups = set(self._select(ctx, eligible, drop_max=True))
        effective_max = max_items if max_items is not None else ctx.config.digest.max_items
        result = jn.build_journal(
            scored,
            kept_ids,
            thresholds=thresholds,
            default_profile=default_profile,
            override=threshold,
            clusters=clusters,
            merge_recorded=True,
            survives_group_caps=within_groups.__contains__,
            max_items=effective_max,
            unchecked_ids=unchecked,
        )
        result["preview"] = True
        result["unchecked_count"] = len(unchecked)
        return result

    def summary_languages(self, run_id: str) -> list[str]:
        run_dir = self.run_store.run_dir(run_id)
        return sorted(path.stem.removeprefix("summary-") for path in run_dir.glob("summary-*.md"))

    def numbered_runs(self) -> list[dict[str, Any]]:
        """Runs, newest first, each with a stable number in order of creation."""
        runs = self.list_runs(limit=500)["items"]
        by_creation = sorted(runs, key=lambda run: run.get("created_at") or "")
        number = {run["run_id"]: index for index, run in enumerate(by_creation, start=1)}
        for run in runs:
            run["number"] = number[run["run_id"]]
        return runs

    def run_number(self, run_id: str) -> int | None:
        for run in self.numbered_runs():
            if run["run_id"] == run_id:
                return run["number"]
        return None


def runs_root_of(domain: Domain) -> Path:
    return domain.runs_root
