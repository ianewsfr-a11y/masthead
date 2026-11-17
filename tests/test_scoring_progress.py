"""While Horizon scores, MastHead shows each story Horizon has finished, as it goes."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pytest

from masthead.service import MastHeadService
from support import create_from_template


@pytest.fixture()
def domain(tmp_path, monkeypatch):
    monkeypatch.setenv("MASTHEAD_HOME", str(tmp_path))
    return create_from_template("flight-sim")


def _story(index: int, title: str) -> dict[str, Any]:
    return {
        "id": f"rss:test:{index}",
        "source_type": "rss",
        "title": title,
        "url": f"https://example.com/story-{index}",
        "content": "A story. " * 20,
        "published_at": datetime.now(timezone.utc).isoformat(),
        "metadata": {"feed_name": "Test Feed"},
        "profile": "flightsim-news",  # named by the source, so no classification call
    }


class _Model:
    """Stands in for the model: scores every story, and cannot answer about one of them."""

    def __init__(self, seen: list[dict[str, Any]], progress: dict[str, Any]):
        self.seen = seen
        self.progress = progress

    async def complete(self, system: str, user: str, *args: Any, **kwargs: Any) -> str:
        # What the interface would show at the moment Horizon asks about the next story.
        self.seen.append({"done": self.progress["done"], "total": self.progress["total"]})
        if "Broken story" in user:
            return "not json"
        return json.dumps({"score": 7.5, "reason": "A concrete release.", "summary": "Summary.", "tags": []})


async def test_each_story_is_shown_once_horizon_has_scored_it(domain):
    seen: list[dict[str, Any]] = []
    service = MastHeadService(domain, client_factory=lambda _config: _Model(seen, service.scoring.state))
    run_id = service.run_store.create_run("progress-test")
    stories = [_story(1, "First story"), _story(2, "Broken story"), _story(3, "Third story")]
    service.run_store.save_items(run_id, "raw", stories)

    result = await service.score_items(run_id=run_id, horizon_path=service.workspace)

    assert result["scored"] == 3
    state = service.scoring.state
    assert (state["total"], state["done"], state["failed"]) == (3, 3, 1)
    assert state["seconds"] >= 0
    # The count went up one story at a time while Horizon was still working.
    assert [step["done"] for step in seen if step["total"]][0] == 0
    assert max(step["done"] for step in seen) == 2
    first, broken, third = state["items"]
    assert first == {
        "id": "rss:test:1", "title": "First story", "url": "https://example.com/story-1",
        "source": "Test Feed", "profile": "flightsim-news", "score": 7.5,
        "reason": "A concrete release.", "failed": False,
    }
    assert broken["failed"] is True and broken["score"] is None
    assert third["score"] == 7.5
    # What was shown matches what Horizon saved for the run.
    saved = {item["id"]: item["processing"]["analysis"]["score"] for item in service.run_store.load_items(run_id, "scored")}
    assert saved == {"rss:test:1": 7.5, "rss:test:2": None, "rss:test:3": 7.5}


def test_a_running_job_carries_the_scoring_progress(domain, monkeypatch):
    """The job returned by the API holds the same live dict, on the Score stage."""
    import asyncio

    from masthead.runner import RunManager

    service = MastHeadService(domain)
    service.scoring.start(4)

    async def fetch_items(**_kwargs):
        return {"run_id": "r1", "raw_before_merge": 4, "fetched": 4, "fetch_report": {"status": "success"}}

    async def score_items(**_kwargs):
        job = next(iter(manager.jobs.values()))
        assert job["stages"][1]["progress"] is service.scoring.state
        return {"scored": 4}

    monkeypatch.setattr(service, "fetch_items", fetch_items)
    monkeypatch.setattr(service, "score_items", score_items)
    monkeypatch.setattr(service.run_store, "update_meta", lambda *_a, **_k: None)

    class _Env:
        def apply(self, _domain):
            pass

        def clear(self):
            pass

    manager = RunManager(env=_Env())

    async def go():
        job = manager.start(service, hours=24, until="score")
        await manager._task
        return job

    job = asyncio.run(go())
    assert job["status"] == "done", job["error"]
    assert job["stages"][1]["progress"]["total"] == 4
