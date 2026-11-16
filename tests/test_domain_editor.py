"""The domain editor: one screen to create and to change a domain.

Subject and languages, sources switched on or off in one save, sources added by
pasting lines, and editorial rules that never overwrite hand-written profiles.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from masthead.domains import get_domain, import_domain
from support import FIXTURES_DIR as TEMPLATES_DIR, create_from_template
from masthead.new_domain import parse_source_line
from masthead.server import create_app

HEADERS = {"host": "127.0.0.1:8765"}


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    create_from_template("flight-sim")
    return tmp_path


@pytest.fixture()
def client(home):
    with TestClient(create_app(), headers=HEADERS) as test_client:
        yield test_client


# -- subject --------------------------------------------------------------------


def test_the_subject_and_languages_of_a_domain_can_be_changed(client):
    response = client.post("/api/domains/flight-sim/subject",
                           json={"name": "Flight sim news", "description": "For pilots.", "languages": ["en", "fr"]})
    assert response.status_code == 200, response.text
    domain = get_domain("flight-sim")
    assert domain.name == "Flight sim news" and domain.meta()["description"] == "For pilots."
    assert domain.raw_config()["ai"]["languages"] == ["en", "fr"]
    assert client.post("/api/domains/flight-sim/subject",
                       json={"name": "", "languages": ["en"]}).status_code == 400
    assert client.post("/api/domains/flight-sim/subject",
                       json={"name": "X", "languages": ["english please"]}).status_code == 400
    assert domain.raw_config()["ai"]["languages"] == ["en", "fr"]


# -- sources ----------------------------------------------------------------------


def test_several_sources_are_switched_in_one_save(client):
    response = client.post("/api/domains/flight-sim/sources-enabled", json={"changes": [
        {"key": "rss:0", "enabled": False}, {"key": "rss:1", "enabled": False}, {"key": "hackernews", "enabled": False}]})
    assert response.status_code == 200, response.text
    raw = get_domain("flight-sim").raw_config()["sources"]
    assert [entry["enabled"] for entry in raw["rss"][:2]] == [False, False]
    bad = client.post("/api/domains/flight-sim/sources-enabled",
                      json={"changes": [{"key": "rss:0", "enabled": True}, {"key": "rss:99", "enabled": False}]})
    assert bad.status_code == 400
    assert get_domain("flight-sim").raw_config()["sources"]["rss"][0]["enabled"] is False  # nothing half-applied


@pytest.mark.parametrize("line, kind, fields", [
    ("https://fselite.net/feed/", "rss", {"name": "fselite.net", "url": "https://fselite.net/feed/"}),
    ("FSElite | https://fselite.net/feed/", "rss", {"name": "FSElite", "url": "https://fselite.net/feed/"}),
    ("https://github.com/flybywiresim/aircraft", "github_repo", {"owner": "flybywiresim", "repo": "aircraft"}),
    ("github.com/flybywiresim/aircraft/releases", "github_repo", {"owner": "flybywiresim", "repo": "aircraft"}),
    ("https://github.com/torvalds", "github_user", {"username": "torvalds"}),
    ("r/flightsim", "reddit_subreddit", {"subreddit": "flightsim"}),
    ("https://www.reddit.com/r/flightsim/", "reddit_subreddit", {"subreddit": "flightsim"}),
    ("https://t.me/s/boatnews", "telegram", {"channel": "boatnews"}),
    ("t.me/boatnews", "telegram", {"channel": "boatnews"}),
])
def test_a_pasted_line_says_what_kind_of_source_it_is(line, kind, fields):
    assert parse_source_line(line) == {"line": line, "kind": kind, "fields": fields, "error": None}


@pytest.mark.parametrize("line", ["flight sim news", "ftp://example.org/feed", "https://github.com/"])
def test_a_line_that_is_not_a_source_says_so(line):
    parsed = parse_source_line(line)
    assert parsed["kind"] is None and parsed["error"]


def test_pasted_text_is_split_into_lines(client):
    text = "https://fselite.net/feed/\n\n  r/flightsim  \nnot a source\n"
    lines = client.post("/api/domains/flight-sim/source-parse", json={"text": text}).json()["lines"]
    assert [line["kind"] for line in lines] == ["rss", "reddit_subreddit", None]
    too_many = "\n".join(f"https://example.org/{n}" for n in range(60))
    assert client.post("/api/domains/flight-sim/source-parse", json={"text": too_many}).status_code == 400


# -- rules -------------------------------------------------------------------------


@pytest.fixture()
def imported(home, tmp_path):
    """A domain brought from Horizon with hand-written profile files, like the owner's virtual-flight."""
    source = tmp_path / "horizon-setup"
    shutil.copytree(TEMPLATES_DIR / "flight-sim" / "profiles", source / "profiles")
    (source / "profiles" / "flightsim-news" / "match.md").write_text("Hand-written rules.\n", encoding="utf-8")
    config = json.loads((TEMPLATES_DIR / "flight-sim" / "data" / "config.json").read_text(encoding="utf-8"))
    (source / "config.json").write_text(json.dumps(config), encoding="utf-8")
    return import_domain("imported", "Imported", source / "config.json", source / "profiles")


def test_hand_written_rules_are_shown_as_files_and_never_overwritten_by_the_form(client, imported):
    state = client.get("/api/domains/imported/profile-form").json()
    assert state["managed"] is False and "Hand-written rules." in state["files"]["match.md"]
    analysis = imported.path / "profiles" / "flightsim-news" / "analysis.md"
    before = analysis.read_text(encoding="utf-8")

    refused = client.post("/api/domains/imported/profile-form", json={"fields": state["fields"]})
    assert refused.status_code == 409 and "analysis.md" in refused.json()["files"]
    assert analysis.read_text(encoding="utf-8") == before

    replaced = client.post("/api/domains/imported/profile-form", json={"fields": state["fields"], "replace": True})
    assert replaced.status_code == 200 and replaced.json()["managed"] is True
    match = imported.path / "profiles" / "flightsim-news" / "match.md"
    assert match.read_text(encoding="utf-8") == "Hand-written rules.\n"  # the form never writes match.md


def test_a_file_edited_by_hand_is_never_replaced_by_the_form_without_confirmation(client):
    """Point 2: also in a domain whose rules were written with the form."""
    client.post("/api/new-domain", json={"id": "boating", "name": "Boating", "languages": ["en"],
                                         "provider": "anthropic", "model": "claude-test"})
    fields = {"goal": "Score boating news."}
    first = client.post("/api/domains/boating/profile-form", json={"fields": fields})
    assert first.status_code == 200 and first.json()["managed"] is True
    edited = client.post("/api/domains/boating/profile-file", json={"file": "analysis.md", "text": "My own words.\n"})
    assert edited.json()["changed_by_hand"] == ["analysis.md"] and edited.json()["managed"] is False

    refused = client.post("/api/domains/boating/profile-form", json={"fields": {"goal": "Something else."}})
    assert refused.status_code == 409 and refused.json()["files"] == ["analysis.md"]
    analysis = get_domain("boating").path / "profiles" / "boating" / "analysis.md"
    assert analysis.read_text(encoding="utf-8") == "My own words.\n"

    # A file changed outside MastHead altogether counts too.
    enrichment = analysis.with_name("enrichment.md")
    client.post("/api/domains/boating/profile-form", json={"fields": fields, "replace": True})
    enrichment.write_text("Typed in a text editor.\n", encoding="utf-8")
    again = client.post("/api/domains/boating/profile-form", json={"fields": fields})
    assert again.status_code == 409 and again.json()["files"] == ["enrichment.md"]


# -- settings ------------------------------------------------------------------------


def test_the_minimum_score_changes_only_the_profile_shown(client):
    """Point 1: the other profiles keep their own minimum score."""
    domain = get_domain("flight-sim")
    raw = domain.raw_config()
    raw["processing"]["profile_settings"]["second"] = {"threshold": 3.0, "topic_dedup": False}
    domain.write_raw_config(raw)

    assert client.post("/api/domains/flight-sim/settings", json={"threshold": 8, "profile": "flightsim-news"}).status_code == 200
    settings = get_domain("flight-sim").raw_config()["processing"]["profile_settings"]
    assert settings["flightsim-news"]["threshold"] == 8 and settings["second"] == {"threshold": 3.0, "topic_dedup": False}

    # Without a profile named, the domain's default profile, and only that one.
    client.post("/api/domains/flight-sim/settings", json={"threshold": 7.5})
    settings = get_domain("flight-sim").raw_config()["processing"]["profile_settings"]
    assert settings["flightsim-news"]["threshold"] == 7.5 and settings["second"]["threshold"] == 3.0

    # Empty removes the minimum of that profile only; nothing is written as null.
    client.post("/api/domains/flight-sim/settings", json={"threshold": None, "profile": "flightsim-news"})
    settings = get_domain("flight-sim").raw_config()["processing"]["profile_settings"]
    assert "threshold" not in settings["flightsim-news"] and settings["second"]["threshold"] == 3.0


def test_saving_settings_writes_no_value_horizon_already_uses(client):
    client.post("/api/new-domain", json={"id": "boating", "name": "Boating", "languages": ["en"],
                                         "provider": "anthropic", "model": "claude-test"})
    before = get_domain("boating").raw_config()
    response = client.post("/api/domains/boating/settings",
                           json={"time_window_hours": 24, "threshold": None, "max_items": None})
    assert response.status_code == 200
    assert get_domain("boating").raw_config() == before


# -- first start and commands -------------------------------------------------------


def test_first_start_creates_no_domain(tmp_path, monkeypatch, capsys):
    """Point 8: no starter domain; the interface offers to create or import one."""
    from masthead import cli
    from masthead.domains import list_domains

    monkeypatch.setenv("MASTHEAD_HOME", str(tmp_path / "empty"))
    with TestClient(create_app(), headers=HEADERS) as fresh:
        assert fresh.get("/api/domains").json()["domains"] == []
    assert cli.main(["domains"]) == 0 and capsys.readouterr().out == ""
    assert list_domains() == []


def test_the_demo_command_is_gone():
    """Point 9: the demo is a test helper, not part of the product."""
    from masthead import cli

    with pytest.raises(SystemExit):
        cli.main(["demo"])
