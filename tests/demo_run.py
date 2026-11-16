"""A demo run made of invented stories.

It lets someone explore the run inspector without an AI key. The stories and
scores are invented and every title starts with "[Demo]". The selection itself
is real: it goes through Horizon's own filtering, merging and limits, with a
stand-in for the model that only answers the duplicate-merging question.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from src.ai.prompting.deduplication import TOPIC_DEDUP_SYSTEM
from src.mcp.horizon_adapter import dicts_to_items, items_to_dicts

from masthead.domains import Domain
from masthead.service import MastHeadService

# (score, source, category, title, duplicate group or None)
_PASSING = [
    (8.0, "Demo Feed A", "community-news", "Aurora Works ships the first big patch for its narrow-body airliner", "patch"),
    (7.5, "Demo Feed B", "community-news", "Aurora Works narrow-body: version 3.1 is out with new engine model", "patch"),
    (7.0, "Demo Feed C", "official", "Aurora Works publishes the 3.1 changelog for its airliner", "patch"),
    (7.0, "Demo Feed A", "community-news", "Patch day for the Aurora Works airliner: what changed", "patch"),
    (7.5, "Demo Feed B", "community-news", "Lantern Studio releases a high-altitude reconnaissance jet", None),
    (7.0, "Demo Feed A", "community-news", "Harbor Sims confirms its wide-body twin enters open beta", "beta"),
    (7.0, "Demo Feed B", "community-news", "Open beta date set for the Harbor Sims wide-body twin", "beta"),
    (6.5, "Demo Feed C", "official", "Harbor Sims details the beta programme for its twin-aisle jet", "beta"),
    (7.0, "Demo Feed B", "community-news", "Tidewater Scenery rebuilds a major Asian hub airport", None),
    (7.0, "Demo Feed A", "community-news", "Lantern Studio brings its double-decker to consoles", None),
    (6.5, "Demo Feed C", "official", "Quarry Lab previews a regional turboprop with a release window", None),
    (7.0, "Demo Feed C", "official", "Simulator update 4 arrives next week with a new weather engine", None),
]
_KINDS = ["screenshots", "a teaser video", "a discount week", "a livery pack", "a minor hotfix", "a dev diary"]
_STUDIOS = ["Aurora Works", "Lantern Studio", "Harbor Sims", "Tidewater Scenery", "Quarry Lab", "Pinewood Avionics"]


class _DemoClient:
    """Stands in for the model. It only knows how to group the demo duplicates."""

    def __init__(self, groups: dict[str, str]):
        self.groups = groups

    async def complete(self, system: str, user: str, *args: Any, **kwargs: Any) -> str:
        if system != TOPIC_DEDUP_SYSTEM:
            raise RuntimeError("The demo run does not call a model.")
        clusters: dict[str, list[int]] = {}
        for match in re.finditer(r"^\[(\d+)\] (.*)$", user, re.MULTILINE):
            group = self.groups.get(match.group(2).strip())
            if group:
                clusters.setdefault(group, []).append(int(match.group(1)))
        return json.dumps({"duplicates": [members for members in clusters.values() if len(members) > 1]})


def _item(index: int, title: str, source: str, category: str, when: datetime, url: str | None = None) -> dict[str, Any]:
    return {
        "id": f"rss:demo:{index:02d}",
        "source_type": "rss",
        "title": f"[Demo] {title}",
        "url": url or f"https://example.com/demo/story-{index:02d}",
        "content": "Invented story used to demonstrate MastHead. " * 4,
        "author": source,
        "published_at": when.isoformat(),
        "metadata": {"feed_name": source, "category": category},
        "profile": None,
    }


async def seed_demo_run(domain: Domain) -> str:
    groups = {f"[Demo] {title}": group for _, _, _, title, group in _PASSING if group}
    service = MastHeadService(domain, client_factory=lambda _config: _DemoClient(groups))
    ctx = service.context()
    profile = ctx.config.processing.default_profile
    now = datetime.now(timezone.utc)

    raw: list[dict[str, Any]] = []
    scores: dict[str, tuple[float, str]] = {}
    for index, (score, source, category, title, _group) in enumerate(_PASSING):
        raw.append(_item(index, title, source, category, now - timedelta(hours=index + 1)))
        scores[raw[-1]["id"]] = (score, "Invented reason: a concrete release or a dated announcement.")
    for offset in range(36):
        index = len(_PASSING) + offset
        studio, kind = _STUDIOS[offset % len(_STUDIOS)], _KINDS[(offset // len(_STUDIOS)) % len(_KINDS)]
        source = ["Demo Feed A", "Demo Feed B", "Demo Feed C"][offset % 3]
        category = "official" if source == "Demo Feed C" else "community-news"
        raw.append(_item(index, f"{studio} shares {kind} ({offset + 1})", source, category, now - timedelta(hours=offset % 23 + 1)))
        score = [6.0, 5.5, 5.0, 4.5, 4.0, 3.5, 3.0, 2.0][offset % 8]
        scores[raw[-1]["id"]] = (score, "Invented reason: little new information for a pilot.")
    # Two links collected twice, as happens when two feeds carry the same article.
    for index in (0, 4):
        copy = dict(raw[index], id=f"rss:demo:dup{index:02d}", author="Demo Feed C",
                    metadata={"feed_name": "Demo Feed C", "category": "official"})
        raw.append(copy)

    run_id = service.run_store.create_run("demo-" + now.strftime("%Y%m%dT%H%M%SZ"))
    orchestrator = service._orchestrator(ctx)
    merged = items_to_dicts(orchestrator.merge_cross_source_duplicates(dicts_to_items(raw)))
    service.run_store.save_items(run_id, "raw", merged)

    scored = []
    for item in merged:
        score, reason = scores[item["id"]] if item["id"] in scores else scores[item["id"].replace("dup", "")]
        item["processing"] = {
            "classification": {"profile": profile, "method": "source_override"},
            "analysis": {
                "score": score,
                "reason": reason,
                "summary": "Invented summary for the demonstration.",
                "tags": ["demo", "flight-simulation"],
            },
            "artifacts": {},
        }
        scored.append(item)
    service.run_store.save_items(run_id, "scored", scored)
    service.run_store.update_meta(run_id, {
        "horizon_path": str(domain.path),
        "config_path": str(domain.config_path),
        "hours": 24,
        "since": (now - timedelta(hours=24)).isoformat(),
        "raw_count_before_merge": len(raw),
        "raw_count": len(merged),
        "scored_count": len(scored),
        "masthead_demo": True,
    })

    await service.filter_items(run_id=run_id)
    for language in ctx.config.ai.languages:
        await service.generate_summary(run_id=run_id, language=language, source_stage="filtered",
                                       horizon_path=service.workspace)
    service.run_store.update_meta(run_id, {
        "masthead_demo": True,
        "masthead": {"status": "done", "until": "full", "error": None,
                     "note": "Demo run: invented stories, no model call, no cost.",
                     "model": None, "provider": None, "stages": [],
                     "input_tokens": 0, "output_tokens": 0, "seconds": 0},
    })
    return run_id
