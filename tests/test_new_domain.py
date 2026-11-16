"""New domain through Horizon's own setup: the configuration is what Horizon's wizard
writes (build_config, save_config), sources are tested with Horizon's collector and
added as Horizon builds them, suggestions come from Horizon, and the editorial rules
are Horizon's built-in profiles until the user customizes them.

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
from src.models import AI_PROVIDER_DEFAULTS, AIConfig, AIProvider
from src.setup.wizard import build_config
from support import create_from_template
from masthead.server import create_app

HEADERS = {"host": "127.0.0.1:8765"}
SETUP = {"id": "boating", "name": "Boating", "description": "Sailing and motor boats.",
         "provider": "anthropic", "model": "claude-test", "languages": ["en", "fr"],
         "sources": [{"type": "rss", "config": {"name": "FSElite", "url": "https://fselite.net/feed/"}}]}


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
    return tmp_path


@pytest.fixture()
def client(home):
    app = create_app()
    with TestClient(app, headers=HEADERS) as test_client:
        test_client.app_state = app.state
        yield test_client


@pytest.fixture()
def draft(client):
    response = client.post("/api/new-domain", json=SETUP)
    assert response.status_code == 201, response.text
    return get_domain("boating")


def horizon_setup_of(answers: dict, items: list) -> dict:
    """What Horizon's own wizard writes for these answers: configure_ai's AIConfig, build_config, save_config."""
    ai = AIConfig(provider=AIProvider(answers["provider"]), model=answers["model"],
                  api_key_env=AI_PROVIDER_DEFAULTS[AIProvider(answers["provider"])]["api_key_env"],
                  temperature=0.3, max_tokens=8192, languages=answers["languages"])
    return build_config(ai, items).model_dump(mode="json")


# -- creating a domain: Horizon's setup ---------------------------------------------


def test_the_configuration_is_the_one_horizons_setup_writes(client, draft):
    meta = json.loads(draft.meta_path.read_text(encoding="utf-8"))
    assert meta == {"name": "Boating", "description": "Sailing and motor boats.", "draft": True}
    written = json.loads(draft.config_path.read_text(encoding="utf-8"))
    assert written == horizon_setup_of(SETUP, SETUP["sources"])
    assert written["sources"]["rss"][0]["profile"] is None  # Horizon's model chooses the profile
    assert written["sources"]["hackernews"]["enabled"] is False  # a source was chosen
    assert not (draft.path / "profiles").exists()  # Horizon's built-in profiles

    overview = client.get("/api/domains/boating").json()
    assert overview["draft"] is True and overview["rules_missing"] is False
    assert overview["missing_env"] == ["ANTHROPIC_API_KEY"]
    assert {p["id"] for p in overview["settings"]["profiles"]} == {"tech-news", "tech-blog", "finance-news", "ai-creator"}


def test_without_any_source_horizon_switches_hacker_news_on(client):
    answers = {**SETUP, "id": "plain", "sources": []}
    assert client.post("/api/new-domain", json=answers).status_code == 201
    written = json.loads(get_domain("plain").config_path.read_text(encoding="utf-8"))
    assert written == horizon_setup_of(answers, [])
    assert written["sources"]["hackernews"]["enabled"] is True  # Horizon's own fallback


def test_nothing_is_pre_filled_so_every_answer_is_needed(client):
    for missing in ("provider", "model", "languages"):
        body = {**SETUP, "id": f"no-{missing}", missing: "" if missing != "languages" else []}
        response = client.post("/api/new-domain", json=body)
        assert response.status_code == 400, missing
    assert client.post("/api/new-domain", json={**SETUP, "id": "chat", "provider": "openai-chatgpt"}).status_code == 400


def test_a_draft_id_must_be_new_and_well_formed(client, draft):
    assert client.post("/api/new-domain", json=SETUP).status_code == 400
    assert client.post("/api/new-domain", json={**SETUP, "id": "Bad Id"}).status_code == 400
    assert client.post("/api/new-domain", json={**SETUP, "id": "x2", "sources": [{"type": "website"}]}).status_code == 400


def test_drafts_are_listed_as_drafts(client, draft):
    listing = {d["id"]: d for d in client.get("/api/domains").json()["domains"]}
    assert listing["boating"]["draft"] is True


# -- sources --------------------------------------------------------------------------


def test_a_source_is_tested_with_horizons_collector_and_nothing_is_kept(client, draft, feeds):
    before = draft.config_path.read_bytes()
    runs_before = list(draft.runs_root.glob("*")) if draft.runs_root.exists() else []

    fresh = client.post("/api/setup/test", json={"type": "rss", "config": {"name": "Fresh", "url": f"{feeds}/fresh.xml"}}).json()
    assert fresh["status"] == "ok" and fresh["items"] == 2  # the 200-hour-old story is outside 7 days
    assert fresh["latest"] and fresh["titles"][0].startswith("Story")
    stale = client.post("/api/domains/boating/source-test",
                        json={"type": "rss", "config": {"name": "Stale", "url": f"{feeds}/stale.xml"}}).json()
    assert stale["status"] == "empty" and stale["items"] == 0
    broken = client.post("/api/setup/test", json={"type": "rss", "config": {"name": "Broken", "url": f"{feeds}/missing.xml"}}).json()
    assert broken["status"] == "failed" and "500" in broken["error"]

    assert draft.config_path.read_bytes() == before
    assert (list(draft.runs_root.glob("*")) if draft.runs_root.exists() else []) == runs_before


def test_a_source_added_later_gets_the_entry_horizon_builds(client, draft, monkeypatch):
    monkeypatch.setenv("SAIL_FEED", "https://example.org/sail.xml")
    raw = draft.raw_config()
    raw["sources"]["rss"][0]["url"] = "${SAIL_FEED}"  # a placeholder written by hand must survive
    draft.config_path.write_text(json.dumps(raw), encoding="utf-8")

    added = [
        {"type": "rss", "config": {"name": "Sail News", "url": "https://example.org/feed"}},
        {"type": "github_repo", "config": {"owner": "example", "repo": "boat-tools"}},
        {"type": "reddit_subreddit", "config": {"subreddit": "sailing"}},
        {"type": "telegram", "config": {"channel": "boatnews"}},
    ]
    for item in added:
        response = client.post("/api/domains/boating/source-add", json=item)
        assert response.status_code == 200, response.text
    sources = draft.raw_config()["sources"]
    expected = horizon_setup_of(SETUP, added)["sources"]
    assert sources["rss"][0]["url"] == "${SAIL_FEED}"
    assert sources["rss"][1] == expected["rss"][0]
    assert sources["github"][0] == expected["github"][0]
    assert sources["reddit"]["subreddits"] == expected["reddit"]["subreddits"] and sources["reddit"]["enabled"] is True
    assert sources["telegram"]["channels"] == expected["telegram"]["channels"] and sources["telegram"]["enabled"] is True

    again = client.post("/api/domains/boating/source-add", json={"type": "rss", "config": {"name": "Again", "url": "https://example.org/feed"}})
    assert again.status_code == 400
    bad = client.post("/api/domains/boating/source-add", json={"type": "rss", "config": {"name": "x", "url": "not a url"}})
    assert bad.status_code == 400


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
            {"type": "reddit_user", "config": {"username": "sailor"}},
            {"type": "something_else", "config": {}},
        ]

    monkeypatch.setattr("masthead.new_domain.get_ai_recommendations", fake_recommendations)
    result = client.post("/api/domains/boating/source-suggest", json={"interests": "sailing races"}).json()

    assert [s["type"] for s in result["suggestions"]] == ["rss", "reddit_user"]
    assert result["suggestions"][0]["config"] == {"name": "Sail Mag", "url": "https://example.org/sail.xml", "category": "press"}
    assert result["suggestions"][0]["reason"] == "Covers races"
    assert result["input_tokens"] == 321 and result["output_tokens"] == 123
    assert seen["interests"] == "sailing races" and seen["key"] == "not-a-real-key"
    assert any("FSElite" in (s.get("description") or "") for s in seen["existing"])
    import os

    assert "ANTHROPIC_API_KEY" not in os.environ  # removed once the call is over


def test_setup_suggestions_use_the_shared_key_before_the_domain_exists(client, monkeypatch):
    seen = {}

    async def fake_recommendations(ai_config, interests, existing_sources):
        import os

        seen.update(key=os.environ.get("ANTHROPIC_API_KEY"), provider=ai_config.provider.value)
        return [{"type": "telegram", "config": {"channel": "@boats"}}]

    monkeypatch.setattr("masthead.new_domain.get_ai_recommendations", fake_recommendations)
    ai = {key: SETUP[key] for key in ("provider", "model", "languages")}
    refused = client.post("/api/setup/suggest", json={"ai": ai, "interests": "boats"})
    assert refused.status_code == 400 and "ANTHROPIC_API_KEY" in refused.json()["error"]

    assert client.post("/api/ai/keys", json={"name": "ANTHROPIC_API_KEY", "value": "sk-ant-not-real-0000"}).status_code == 200
    result = client.post("/api/setup/suggest", json={"ai": ai, "interests": "boats"}).json()
    assert result["suggestions"] == [{"type": "telegram", "config": {"channel": "boats"}, "description": None, "reason": None}]
    assert seen == {"key": "sk-ant-not-real-0000", "provider": "anthropic"}
    import os

    assert "ANTHROPIC_API_KEY" not in os.environ


def test_suggestions_need_a_key(client, draft):
    response = client.post("/api/domains/boating/source-suggest", json={"interests": "sailing"})
    assert response.status_code == 400 and "ANTHROPIC_API_KEY" in response.json()["error"]


# -- editorial rules: Horizon's profiles ----------------------------------------------


def test_a_new_domain_uses_horizons_built_in_profiles_read_only(client, draft):
    state = client.get("/api/domains/boating/profiles").json()
    assert state["builtin"] is True
    assert {p["id"] for p in state["profiles"]} == {"tech-news", "tech-blog", "finance-news", "ai-creator"}
    assert all(set(p["files"]) == {"match.md", "analysis.md", "enrichment.md"} for p in state["profiles"])
    refused = client.post("/api/domains/boating/profile-file",
                          json={"profile": "tech-news", "file": "match.md", "text": "x"})
    assert refused.status_code == 400 and not (draft.path / "profiles").exists()


def test_customized_profiles_are_copies_edited_as_text_and_checked_by_horizon(client, draft):
    from src.processing.profiles import BUILTIN_PROFILES_DIR

    state = client.post("/api/domains/boating/profiles/customize", json={}).json()
    assert state["builtin"] is False
    copied = draft.path / "profiles" / "tech-news" / "match.md"
    assert copied.read_text(encoding="utf-8") == (BUILTIN_PROFILES_DIR / "tech-news" / "match.md").read_text(encoding="utf-8")
    assert client.post("/api/domains/boating/profiles/customize", json={}).status_code == 409  # never over existing files

    saved = client.post("/api/domains/boating/profile-file",
                        json={"profile": "tech-news", "file": "match.md", "text": "Boating news only.\n"})
    assert saved.status_code == 200 and copied.read_text(encoding="utf-8") == "Boating news only.\n"
    assert client.post("/api/domains/boating/profile-file",
                       json={"profile": "../escape", "file": "match.md", "text": "x"}).status_code == 400
    assert client.post("/api/domains/boating/profile-file",
                       json={"profile": "tech-news", "file": "profile.json", "text": "{}"}).status_code == 400


# -- trial run, then create or discard -----------------------------------------------


def test_a_trial_stops_before_writing(client, draft, feeds):
    raw = draft.raw_config()
    raw["sources"]["rss"][0]["url"] = f"{feeds}/fresh.xml"
    draft.write_raw_config(raw)
    job = client.post("/api/domains/boating/runs", json={"until": "select"})
    assert job.status_code == 202, job.text
    assert [s["status"] for s in job.json()["stages"]][3:] == ["skipped", "skipped"]  # write, briefing


def test_create_needs_a_source_on_then_clears_the_draft_flag(client, draft):
    raw = draft.raw_config()
    raw["sources"]["rss"][0]["enabled"] = False
    draft.write_raw_config(raw)
    assert client.post("/api/domains/boating/publish", json={}).status_code == 400
    raw["sources"]["rss"][0]["enabled"] = True
    draft.write_raw_config(raw)
    assert client.post("/api/domains/boating/publish", json={}).status_code == 200
    assert client.get("/api/domains/boating").json()["draft"] is False
    assert client.post("/api/domains/boating/discard", json={}).status_code == 409  # no longer a draft


def test_discard_deletes_only_a_draft(client, draft):
    create_from_template("flight-sim")
    assert client.post("/api/domains/flight-sim/discard", json={}).status_code == 409
    assert client.post("/api/domains/boating/discard", json={}).status_code == 200
    assert not draft.path.exists()
