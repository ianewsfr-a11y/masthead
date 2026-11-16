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

from masthead.domains import get_domain
from support import create_from_template
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


OFF = {"hackernews": {"enabled": False}, "reddit": {"enabled": False}, "telegram": {"enabled": False}}


def test_a_draft_is_a_valid_horizon_domain_with_nothing_read_by_default(client, draft):
    meta = json.loads(draft.meta_path.read_text(encoding="utf-8"))
    assert meta["draft"] is True and meta["name"] == "Boating"
    raw = draft.raw_config()
    starter = get_domain("flight-sim").raw_config()
    # Only what the user chose: the copied AI with their languages, the profile id, and the three
    # sources Horizon reads by default switched off. No threshold, no maximum, no default values.
    assert raw == {"ai": {**starter["ai"], "languages": ["en", "fr"]},
                   "processing": {"default_profile": "boating"}, "sources": OFF}
    assert not (draft.path / ".env").exists()  # the key is never copied
    assert not (draft.path / "profiles").exists()  # nothing written before the rules are saved

    overview = client.get("/api/domains/boating").json()
    assert overview["draft"] is True and overview["rules_missing"] is True
    assert overview["sources"] and all(not row["enabled"] for row in overview["sources"])
    assert {row["kind"] for row in overview["sources"]} == {"hackernews", "reddit", "telegram"}  # shown, off
    assert not any(row["implicit"] for row in overview["sources"])
    assert overview["missing_env"] == ["ANTHROPIC_API_KEY"]
    assert overview["settings"]["profiles"] == []


def test_a_draft_without_a_copy_holds_only_what_was_typed(client):
    response = client.post("/api/new-domain", json={"id": "plain", "name": "Plain", "languages": ["en"],
                                                    "provider": "anthropic", "model": "claude-test"})
    assert response.status_code == 201, response.text
    assert get_domain("plain").raw_config() == {
        "ai": {"provider": "anthropic", "model": "claude-test", "api_key_env": "ANTHROPIC_API_KEY"},
        "processing": {"default_profile": "plain"},
        "sources": OFF,
    }
    assert client.post("/api/new-domain", json={"id": "noai", "name": "No AI", "languages": ["en"]}).status_code == 400


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
    # What identifies each source and the domain's profile; Horizon's defaults for everything else.
    assert raw["rss"] == [{"name": "Sail News", "url": "https://example.org/feed", "profile": "boating"}]
    assert raw["github"] == [{"type": "repo_releases", "owner": "example", "repo": "boat-tools", "profile": "boating"}]
    assert raw["reddit"] == {"enabled": True, "subreddits": [{"subreddit": "sailing", "profile": "boating"}]}
    assert raw["telegram"] == {"enabled": True, "channels": [{"channel": "boatnews", "profile": "boating"}]}
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


RULES = {"goal": "Score news for sailors.", "summary": "Lead with what changed.",
         "tiers": ["Major news.", "", "", "", "Noise."]}


def test_the_form_starts_empty_and_writes_only_what_was_typed(client, draft):
    from src.processing.profiles import ProfileRegistry

    form = client.get("/api/domains/boating/profile-form").json()
    assert form["exists"] is False and form["files"] == {}
    assert all(value in ("", False, None) for key, value in form["fields"].items() if key != "tiers")
    assert form["fields"]["tiers"] == [""] * 5
    assert not {"belongs", "typical", "excluded"} & set(form["fields"])  # match.md is not in the form

    saved = client.post("/api/domains/boating/profile-form", json={"fields": RULES})
    assert saved.status_code == 200, saved.text
    files = saved.json()["files"]
    assert files["analysis.md"] == "Score news for sailors.\n\n- 9-10: Major news.\n- 0-2: Noise.\n"
    assert files["enrichment.md"] == "- `summary`: Lead with what changed.\n"
    assert files["match.md"] == ""  # Horizon requires the file; it can stay empty
    definition = json.loads(files["profile.json"])
    assert definition == {"id": "boating", "name": "Boating", "match": "match.md", "analysis": "analysis.md",
                          "enrichment": {"prompt": "enrichment.md", "blocks": [{"id": "summary", "primary": True}]}}
    loaded = ProfileRegistry.load(draft.path / "profiles", "boating").get("boating")
    assert loaded.definition.content.analysis_max_chars == 1000  # Horizon's own default, not written

    more = {**RULES, "analysis_max_chars": 6000, "background": True, "web_search": False, "profile_name": "Sailing"}
    files = client.post("/api/domains/boating/profile-form", json={"fields": more}).json()["files"]
    definition = json.loads(files["profile.json"])
    assert definition["content"] == {"analysis_max_chars": 6000} and definition["name"] == "Sailing"
    assert {"id": "background", "tools": ["history_search"]} in definition["enrichment"]["blocks"]
    assert "Use three to five" not in files["analysis.md"] and "web_search" not in files["enrichment.md"]


def test_the_profile_text_can_be_edited_directly(client, draft):
    text = "# Boating profile\n\nOnly sailing news.\n"
    before = client.post("/api/domains/boating/profile-file", json={"file": "match.md", "text": text})
    assert before.status_code == 400  # Horizon needs profile.json first: save the form once
    client.post("/api/domains/boating/profile-form", json={"fields": RULES})
    assert client.post("/api/domains/boating/profile-file", json={"file": "match.md", "text": text}).status_code == 200
    assert (draft.path / "profiles" / "boating" / "match.md").read_text(encoding="utf-8") == text
    assert client.post("/api/domains/boating/profile-file",
                       json={"file": "../domain.json", "text": "x"}).status_code == 400
    assert client.post("/api/domains/boating/profile-file", json={"file": "match.md", "text": ""}).status_code == 200


def test_invalid_form_values_are_refused(client, draft):
    assert client.post("/api/domains/boating/profile-form",
                       json={"fields": {**RULES, "analysis_max_chars": 100}}).status_code == 400
    assert client.post("/api/domains/boating/profile-form",
                       json={"fields": {**RULES, "tiers": ["one"]}}).status_code == 400
    assert client.post("/api/domains/boating/profile-form",
                       json={"fields": {**RULES, "background": "yes"}}).status_code == 400


# -- step 4: trial run, then create or discard -------------------------------------


def test_a_trial_stops_before_writing(client, draft, feeds):
    client.post("/api/domains/boating/source-add", json={"kind": "rss", "name": "Fresh", "url": f"{feeds}/fresh.xml"})
    early = client.post("/api/domains/boating/runs", json={"until": "collect"})
    assert early.status_code == 409 and "editorial rules" in early.json()["error"]
    client.post("/api/domains/boating/profile-form", json={"fields": RULES})
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
