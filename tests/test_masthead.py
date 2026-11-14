"""End-to-end checks that need no network and no model.

The demo run goes through Horizon's real selection (score filter, duplicate
merging, group limits, maximum), with a stand-in answering only the
duplicate-merging question.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from masthead import journal as jn
from masthead.demo import seed_demo_run
from masthead.domains import create_from_template, get_domain
from masthead.server import create_app
from masthead.service import MastHeadService

HEADERS = {"host": "127.0.0.1:8765"}


@pytest.fixture()
def domain(tmp_path, monkeypatch):
    monkeypatch.setenv("MASTHEAD_HOME", str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return create_from_template("flight-sim")


@pytest.fixture()
async def run_id(domain):
    return await seed_demo_run(domain)


@pytest.fixture()
def client(domain):
    # The context manager keeps one event loop alive, as the real server does,
    # so a background run survives between two requests.
    with TestClient(create_app(), headers=HEADERS) as test_client:
        yield test_client


async def test_demo_run_funnel_and_reasons(domain, run_id):
    service = MastHeadService(domain)
    meta = service.get_run_meta(run_id)["meta"]
    assert meta["raw_count_before_merge"] == 50
    assert meta["raw_count"] == 48

    journal = service.journal(run_id)
    assert journal["funnel"] == {"scored": 48, "passing": 12, "after_merge": 7, "kept": 6}
    assert journal["counts"][jn.BELOW] == 36
    assert journal["counts"][jn.MERGED] == 5
    assert journal["counts"][jn.CAPPED] == 1

    # Horizon's own stage file agrees with the journal.
    kept = [item["id"] for item in service.run_store.load_items(run_id, "filtered")]
    assert kept == [d["id"] for d in journal["decisions"] if d["outcome"] == jn.KEPT]

    merged = [d for d in journal["decisions"] if d["outcome"] == jn.MERGED]
    assert all(d["merged_into"]["id"] in kept for d in merged)
    assert all(d["score"] <= next(k["score"] for k in journal["decisions"] if k["id"] == d["merged_into"]["id"])
               for d in merged)

    capped = next(d for d in journal["decisions"] if d["outcome"] == jn.CAPPED)
    assert capped["cap"] == "group_limit"
    assert capped["category"] == "community-news"


async def test_replay_changes_nothing_on_disk_and_calls_no_model(domain, run_id):
    def no_model(_config):
        raise AssertionError("replay must not create a model client")

    service = MastHeadService(domain, client_factory=no_model)
    run_dir = service.run_store.run_dir(run_id)
    before = {path.name: path.read_bytes() for path in run_dir.iterdir()}

    same = service.replay(run_id, 6.5)
    assert same["funnel"] == {"scored": 48, "passing": 12, "after_merge": 7, "kept": 6}
    assert same["unchecked_count"] == 0

    stricter = service.replay(run_id, 7.5)
    assert stricter["funnel"]["passing"] == 3
    assert stricter["funnel"]["kept"] == 2  # two of the three are the same story

    looser = service.replay(run_id, 6.0)
    assert looser["funnel"]["passing"] == 17
    assert looser["unchecked_count"] == 5
    assert looser["funnel"]["kept"] == 6  # still limited by the maximum

    assert before == {path.name: path.read_bytes() for path in run_dir.iterdir()}


async def test_foreign_run_gets_an_honest_partial_journal(domain, run_id):
    service = MastHeadService(domain)
    (service.run_store.run_dir(run_id) / "masthead_decisions.json").unlink()
    journal = service.journal(run_id)
    assert journal["merge_recorded"] is False
    assert journal["counts"][jn.KEPT] == 6
    assert journal["counts"][jn.UNEXPLAINED] == 6
    assert journal["counts"][jn.MERGED] == 0


def test_default_sources_are_visible_and_toggle(client, domain):
    overview = client.get("/api/domains/flight-sim").json()
    kinds = {row["key"]: row for row in overview["sources"]}
    assert kinds["hackernews"]["enabled"] is False and kinds["telegram"]["enabled"] is False
    assert overview["missing_env"] == ["ANTHROPIC_API_KEY"]
    assert overview["settings"]["ai"]["api_key_present"] is False

    # Remove the explicit switch: Horizon turns Hacker News back on by itself, and MastHead says so.
    raw = domain.raw_config()
    del raw["sources"]["hackernews"]
    domain.write_raw_config(raw)
    row = next(r for r in client.get("/api/domains/flight-sim").json()["sources"] if r["key"] == "hackernews")
    assert row["enabled"] is True and row["implicit"] is True

    after = client.post("/api/domains/flight-sim/sources", json={"key": "hackernews", "enabled": False}).json()
    row = next(r for r in after["sources"] if r["key"] == "hackernews")
    assert row["enabled"] is False and row["implicit"] is False
    assert domain.config_path.with_suffix(".json.bak").exists()

    after = client.post("/api/domains/flight-sim/sources", json={"key": "rss:1", "enabled": False}).json()
    assert next(r for r in after["sources"] if r["key"] == "rss:1")["enabled"] is False


def test_settings_are_validated_by_horizon(client, domain):
    ok = client.post("/api/domains/flight-sim/settings", json={"threshold": 7, "max_items": 8, "time_window_hours": 48})
    assert ok.status_code == 200
    settings = ok.json()["settings"]
    assert settings["profiles"][0]["threshold"] == 7 and settings["max_items"] == 8 and settings["time_window_hours"] == 48
    bad = client.post("/api/domains/flight-sim/settings", json={"threshold": 12})
    assert bad.status_code == 400
    assert json.loads(domain.config_path.read_text())["processing"]["profile_settings"]["flightsim-news"]["threshold"] == 7


async def test_api_run_detail_replay_and_briefing(client, run_id):
    runs = client.get("/api/domains/flight-sim/runs").json()["runs"]
    assert runs[0]["run_id"] == run_id and runs[0]["number"] == 1 and runs[0]["demo"] is True

    detail = client.get(f"/api/domains/flight-sim/runs/{run_id}").json()
    assert detail["journal"]["funnel"]["kept"] == 6 and detail["languages"] == ["en"]

    replay = client.post(f"/api/domains/flight-sim/runs/{run_id}/replay", json={"threshold": 9}).json()
    assert replay["funnel"]["kept"] == 0 and replay["preview"] is True

    briefing = client.get(f"/api/domains/flight-sim/runs/{run_id}/briefing", params={"language": "en"}).json()
    assert "Aurora Works" in briefing["summary"]


def test_requests_from_elsewhere_are_refused(domain):
    app = create_app()
    assert TestClient(app, headers={"host": "evil.example"}).get("/api/domains").status_code == 403
    cross = TestClient(app, headers={**HEADERS, "origin": "https://evil.example"})
    assert cross.post("/api/domains/flight-sim/runs", json={}).status_code == 403
    form = TestClient(app, headers=HEADERS)
    assert form.post("/api/domains/flight-sim/runs", data={"until": "full"}).status_code == 415


def test_collect_only_run_without_network_reports_failed_sources(client):
    """Stopping after collection needs no AI key. Here the feeds cannot be reached, which must be reported."""
    import time

    job = client.post("/api/domains/flight-sim/runs", json={"until": "collect"})
    assert job.status_code == 202
    job_id = job.json()["id"]
    for _ in range(600):
        state = client.get(f"/api/jobs/{job_id}").json()
        if state["status"] != "running":
            break
        time.sleep(0.1)
    assert [s["status"] for s in state["stages"]][1:] == ["skipped"] * 4
    run = client.get(f"/api/domains/flight-sim/runs/{state['run_id']}").json()
    report = run["meta"]["fetch_report"]
    assert report["attempted"] >= 1
    if report["status"] == "failure":  # no network: the run must say so, not claim success
        assert state["status"] == "failed" and "Every source failed" in state["error"]
        assert run["meta"]["masthead"]["status"] == "failed"
        assert all(source.get("error") or source.get("failures") for source in report["sources"])
    else:
        assert state["status"] == "done"
