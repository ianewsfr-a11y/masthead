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

from masthead.domains import TEMPLATES_DIR, create_from_template, get_domain, import_domain
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

    refused = client.post("/api/domains/imported/profile-form", json={"fields": state["fields"]})
    assert refused.status_code == 409
    match = imported.path / "profiles" / "flightsim-news" / "match.md"
    assert match.read_text(encoding="utf-8") == "Hand-written rules.\n"

    edited = client.post("/api/domains/imported/profile-file", json={"file": "match.md", "text": "Edited by hand.\n"})
    assert edited.status_code == 200 and match.read_text(encoding="utf-8") == "Edited by hand.\n"

    replaced = client.post("/api/domains/imported/profile-form", json={"fields": state["fields"], "replace": True})
    assert replaced.status_code == 200 and replaced.json()["managed"] is True
    assert "Edited by hand." not in match.read_text(encoding="utf-8")


def test_a_new_domain_rules_are_managed_and_remember_when_saved(client):
    client.post("/api/new-domain", json={"id": "boating", "name": "Boating", "languages": ["en"], "copy_from": "flight-sim"})
    state = client.get("/api/domains/boating/profile-form").json()
    assert state["managed"] is True and state["saved_by_user"] is False
    saved = client.post("/api/domains/boating/profile-form", json={"fields": state["fields"]}).json()
    assert saved["saved_by_user"] is True
