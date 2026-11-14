"""New domain: draft, sources tested with Horizon's collector, Horizon's suggestions,
editorial rules written to Horizon's profile files, then create or discard.

No model call: the suggestion function is replaced. Source tests read a feed
served on this computer.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from masthead.domains import create_from_template, get_domain
from masthead.server import create_app

HEADERS = {"host": "127.0.0.1:8765"}
STEP1 = {"id": "boating", "name": "Boating", "description": "Sailing and motor boats.",
         "languages": ["en", "fr"], "copy_from": "flight-sim"}


def _rss(hours_ago: list[int]) -> bytes:
    now = datetime.now(timezone.utc)
    items = "".join(
        f"<item><title>Story {n}</title><link>https://example.org/{n}</link>"
        f"<pubDate>{format_datetime(now - timedelta(hours=h))}</pubDate>"
        f"<description>Text of story {n}.</description></item>"
        for n, h in enumerate(hours_ago)
    )
    return (f'<?xml version="1.0"?><rss version="2.0"><channel><title>Test feed</title>'
            f"<link>https://example.org/</link><description>t</description>{items}</channel></rss>").encode()


class _Feeds(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        bodies = {"/fresh.xml": _rss([1, 30, 200]), "/stale.xml": _rss([400])}
        body = bodies.get(self.path)
        if body is None:
            self.send_response(500)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("content-type", "application/rss+xml")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture()
def feeds():
    server = HTTPServer(("127.0.0.1", 0), _Feeds)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MASTHEAD_HOME", str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    starter = create_from_template("flight-sim")
    (starter.path / ".env").write_text("ANTHROPIC_API_KEY=not-a-real-key\n", encoding="utf-8")
    return tmp_path


@pytest.fixture()
def client(home):
    app = create_app()
    with TestClient(app, headers=HEADERS) as test_client:
        test_client.app_state = app.state
        yield test_client


@pytest.fixture()
def draft(client):
    response = client.post("/api/new-domain", json=STEP1)
    assert response.status_code == 201, response.text
    return get_domain("boating")


# -- step 1: subject -----------------------------------------------------------


def test_a_draft_is_a_valid_horizon_domain_with_nothing_read_by_default(client, draft):
    meta = json.loads(draft.meta_path.read_text(encoding="utf-8"))
    assert meta["draft"] is True and meta["name"] == "Boating"
    raw = draft.raw_config()
    starter = get_domain("flight-sim").raw_config()
    assert raw["ai"]["model"] == starter["ai"]["model"] and raw["ai"]["languages"] == ["en", "fr"]
    assert raw["ai"]["api_key_env"] == starter["ai"]["api_key_env"]
    assert not (draft.path / ".env").exists()  # the key is never copied

    overview = client.get("/api/domains/boating").json()
    assert overview["draft"] is True
    assert overview["sources"] == [] or all(not row["enabled"] for row in overview["sources"])
    assert not any(row["implicit"] for row in overview["sources"])  # Hacker News, Reddit, Telegram off
    assert overview["missing_env"] == ["ANTHROPIC_API_KEY"]
    profile = overview["settings"]["profiles"][0]
    assert profile["id"] == "boating" and profile["analysis_max_chars"] == 4000


def test_a_draft_id_must_be_new_and_well_formed(client, draft):
    assert client.post("/api/new-domain", json=STEP1).status_code == 400
    assert client.post("/api/new-domain", json={**STEP1, "id": "Bad Id"}).status_code == 400
    assert client.post("/api/new-domain", json={**STEP1, "id": "x2", "languages": []}).status_code == 400
    assert client.post("/api/new-domain", json={**STEP1, "id": "x3", "copy_from": "nope"}).status_code == 404


def test_drafts_are_listed_as_drafts(client, draft):
    listing = {d["id"]: d for d in client.get("/api/domains").json()["domains"]}
    assert listing["boating"]["draft"] is True and listing["flight-sim"]["draft"] is False


# -- step 2: sources -------------------------------------------------------------


def test_a_source_is_tested_with_horizons_collector_and_nothing_is_kept(client, draft, feeds):
    before = draft.config_path.read_bytes()
    runs_before = list(draft.runs_root.glob("*")) if draft.runs_root.exists() else []

    fresh = client.post("/api/domains/boating/source-test",
                        json={"kind": "rss", "name": "Fresh", "url": f"{feeds}/fresh.xml"}).json()
    assert fresh["status"] == "ok" and fresh["items"] == 2  # the 200-hour-old story is outside 7 days
    assert fresh["latest"] and fresh["titles"][0].startswith("Story")

    stale = client.post("/api/domains/boating/source-test",
                        json={"kind": "rss", "name": "Stale", "url": f"{feeds}/stale.xml"}).json()
    assert stale["status"] == "empty" and stale["items"] == 0

    broken = client.post("/api/domains/boating/source-test",
                         json={"kind": "rss", "name": "Broken", "url": f"{feeds}/missing.xml"}).json()
    assert broken["status"] == "failed" and "500" in broken["error"]

    assert draft.config_path.read_bytes() == before
    assert (list(draft.runs_root.glob("*")) if draft.runs_root.exists() else []) == runs_before


def test_sources_of_each_kind_are_added_to_the_config(client, draft):
    for body in (
        {"kind": "rss", "name": "Sail News", "url": "https://example.org/feed"},
        {"kind": "github_repo", "owner": "example", "repo": "boat-tools"},
        {"kind": "reddit_subreddit", "subreddit": "sailing"},
        {"kind": "telegram", "channel": "boatnews"},
    ):
        response = client.post("/api/domains/boating/source-add", json=body)
        assert response.status_code == 200, response.text
    raw = draft.raw_config()["sources"]
    assert raw["rss"][0]["url"] == "https://example.org/feed" and raw["rss"][0]["profile"] == "boating"
    assert raw["github"][0] == {**raw["github"][0], "type": "repo_releases", "owner": "example", "repo": "boat-tools"}
    assert raw["reddit"]["enabled"] is True and raw["reddit"]["subreddits"][0]["subreddit"] == "sailing"
    assert raw["telegram"]["enabled"] is True and raw["telegram"]["channels"][0]["channel"] == "boatnews"
    assert raw["hackernews"]["enabled"] is False

    again = client.post("/api/domains/boating/source-add",
                        json={"kind": "rss", "name": "Again", "url": "https://example.org/feed"})
    assert again.status_code == 400
    bad = client.post("/api/domains/boating/source-add", json={"kind": "rss", "name": "x", "url": "not a url"})
    assert bad.status_code == 400
    assert client.post("/api/domains/boating/source-add", json={"kind": "website", "url": "https://x"}).status_code == 400


def test_suggestions_come_from_horizons_function_with_measured_tokens(client, draft, monkeypatch):
    from src.ai import tokens

    (draft.path / ".env").write_text("ANTHROPIC_API_KEY=not-a-real-key\n", encoding="utf-8")
    seen = {}

    async def fake_recommendations(ai_config, interests, existing_sources):
        import os

        seen.update(interests=interests, existing=existing_sources, key=os.environ.get("ANTHROPIC_API_KEY"),
                    model=ai_config.model)
        tokens.record_usage("anthropic", input_tokens=321, output_tokens=123)
        return [
            {"type": "rss", "description": "A sailing magazine", "reason": "Covers races",
             "config": {"name": "Sail Mag", "url": "https://example.org/sail.xml", "category": "press"}},
            {"type": "reddit_subreddit", "description": "Sailing forum", "config": {"subreddit": "sailing"}},
            {"type": "something_else", "config": {}},
        ]

    monkeypatch.setattr("masthead.new_domain.get_ai_recommendations", fake_recommendations)
    client.post("/api/domains/boating/source-add", json={"kind": "rss", "name": "Have", "url": "https://example.org/have"})
    result = client.post("/api/domains/boating/source-suggest", json={"interests": "sailing races"}).json()

    assert [s["kind"] for s in result["suggestions"]] == ["rss", "reddit_subreddit"]
    assert result["suggestions"][0]["fields"] == {"name": "Sail Mag", "url": "https://example.org/sail.xml"}
    assert result["suggestions"][0]["reason"] == "Covers races"
    assert result["input_tokens"] == 321 and result["output_tokens"] == 123
    assert seen["interests"] == "sailing races" and seen["key"] == "not-a-real-key"
    assert any("example.org/have" in (s.get("description") or "") for s in seen["existing"])
    import os

    assert "ANTHROPIC_API_KEY" not in os.environ  # removed once the call is over


def test_suggestions_need_the_drafts_own_key(client, draft):
    response = client.post("/api/domains/boating/source-suggest", json={"interests": "sailing"})
    assert response.status_code == 400 and "ANTHROPIC_API_KEY" in response.json()["error"]


# -- step 3: editorial rules ------------------------------------------------------


def test_the_form_writes_profile_files_that_horizon_loads(client, draft):
    from src.processing.profiles import ProfileRegistry

    form = client.get("/api/domains/boating/profile-form").json()
    assert form["fields"]["belongs"] and len(form["fields"]["tiers"]) == 5

    fields = {**form["fields"], "belongs": "News about sailing and motor boats.",
              "excluded": "Boat sales listings.", "web_search": False, "community": False,
              "analysis_max_chars": 6000}
    saved = client.post("/api/domains/boating/profile-form", json={"fields": fields})
    assert saved.status_code == 200, saved.text
    files = saved.json()["files"]
    assert "News about sailing and motor boats." in files["match.md"]
    assert "Boat sales listings." in files["match.md"]
    assert "9-10" in files["analysis.md"]

    registry = ProfileRegistry.load(draft.path / "profiles", "boating")
    loaded = registry.get("boating")
    assert loaded.definition.content.analysis_max_chars == 6000
    tools = {block.id: block.tools for block in loaded.definition.enrichment.blocks}
    assert "web_search" not in sum(tools.values(), []) and "community_discussion" not in tools
    assert client.get("/api/domains/boating/profile-form").json()["fields"]["excluded"] == "Boat sales listings."


def test_the_profile_text_can_be_edited_directly(client, draft):
    text = "# Boating profile\n\nOnly sailing news.\n"
    assert client.post("/api/domains/boating/profile-file", json={"file": "match.md", "text": text}).status_code == 200
    assert (draft.path / "profiles" / "boating" / "match.md").read_text(encoding="utf-8") == text
    assert client.post("/api/domains/boating/profile-file",
                       json={"file": "../domain.json", "text": "x"}).status_code == 400
    assert client.post("/api/domains/boating/profile-file", json={"file": "match.md", "text": "  "}).status_code == 400


def test_invalid_form_values_are_refused(client, draft):
    fields = client.get("/api/domains/boating/profile-form").json()["fields"]
    assert client.post("/api/domains/boating/profile-form",
                       json={"fields": {**fields, "analysis_max_chars": 100}}).status_code == 400
    assert client.post("/api/domains/boating/profile-form",
                       json={"fields": {**fields, "belongs": ""}}).status_code == 400


# -- step 4: trial run, then create or discard -------------------------------------


def test_a_trial_stops_before_writing(client, draft, feeds):
    client.post("/api/domains/boating/source-add", json={"kind": "rss", "name": "Fresh", "url": f"{feeds}/fresh.xml"})
    job = client.post("/api/domains/boating/runs", json={"until": "select"})
    assert job.status_code == 202
    assert [s["status"] for s in job.json()["stages"]][3:] == ["skipped", "skipped"]  # write, briefing


def test_create_needs_a_source_then_clears_the_draft_flag(client, draft, feeds):
    assert client.post("/api/domains/boating/publish", json={}).status_code == 400
    client.post("/api/domains/boating/source-add", json={"kind": "rss", "name": "Fresh", "url": f"{feeds}/fresh.xml"})
    assert client.post("/api/domains/boating/publish", json={}).status_code == 200
    assert client.get("/api/domains/boating").json()["draft"] is False
    assert client.post("/api/domains/boating/discard", json={}).status_code == 409  # no longer a draft


def test_discard_deletes_only_a_draft(client, draft):
    assert client.post("/api/domains/flight-sim/discard", json={}).status_code == 409
    assert client.post("/api/domains/boating/discard", json={}).status_code == 200
    assert not draft.path.exists()
    assert client.get("/api/domains/boating").status_code == 404
