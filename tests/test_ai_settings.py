"""Choosing the AI of a domain, and AI keys entered in the interface.

A key is saved once per provider, shared by every domain that uses that
provider. A domain's own .env overrides it; the environment MastHead was
started with overrides both. A key is never returned, never logged.
"""

from __future__ import annotations

import os
import stat

import pytest
from fastapi.testclient import TestClient

from masthead.domains import create_from_template, get_domain
from masthead.env import DomainEnvironment
from masthead.keys import keys_path
from masthead.server import create_app

HEADERS = {"host": "127.0.0.1:8765"}
SECRET = "sk-test-0123456789abcdef"


@pytest.fixture()
def home(tmp_path, monkeypatch):
    for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    create_from_template("flight-sim")
    return tmp_path


@pytest.fixture()
def client(home):
    with TestClient(create_app(), headers=HEADERS) as test_client:
        yield test_client


def save_key(client, name, value=SECRET):
    return client.post("/api/ai/keys", json={"name": name, "value": value})


# -- providers -------------------------------------------------------------------


def test_providers_come_from_horizon(client):
    from src.models import AI_PROVIDER_DEFAULTS, AIProvider

    providers = {p["id"]: p for p in client.get("/api/ai").json()["providers"]}
    assert "openai-chatgpt" not in providers  # signs in through Horizon's own command, not a key
    anthropic = providers["anthropic"]
    assert anthropic["key_env"] == "ANTHROPIC_API_KEY" and anthropic["needs_key"] is True
    assert anthropic["example_model"] == AI_PROVIDER_DEFAULTS[AIProvider.ANTHROPIC]["model"]
    assert providers["ollama"]["needs_key"] is False and providers["ollama"]["base_url"].startswith("http://localhost")
    assert providers["azure"]["extra_env"] == ["AZURE_OPENAI_ENDPOINT"]
    assert all(p["key_present"] is False for p in providers.values() if p["needs_key"])


# -- keys ------------------------------------------------------------------------


def test_a_saved_key_is_shared_by_domains_and_never_returned(client, home):
    response = save_key(client, "ANTHROPIC_API_KEY")
    assert response.status_code == 200 and SECRET not in response.text

    status = {p["id"]: p for p in client.get("/api/ai").json()["providers"]}["anthropic"]
    assert status["key_present"] is True and status["key_source"] == "shared"

    overview = client.get("/api/domains/flight-sim")
    assert overview.json()["settings"]["ai"]["api_key_present"] is True
    assert overview.json()["settings"]["ai"]["key_source"] == "shared"
    assert overview.json()["missing_env"] == []
    for text in (overview.text, client.get("/api/domains").text, client.get("/api/ai").text):
        assert SECRET not in text

    assert SECRET in keys_path().read_text(encoding="utf-8")
    assert not (get_domain("flight-sim").path / ".env").exists()  # nothing written in the domain
    assert "ANTHROPIC_API_KEY" not in os.environ  # loaded only while a run goes


@pytest.mark.skipif(os.name != "posix", reason="file modes are POSIX")
def test_the_keys_file_is_readable_by_its_owner_only(client):
    save_key(client, "ANTHROPIC_API_KEY")
    assert stat.S_IMODE(keys_path().stat().st_mode) == 0o600


def test_a_domain_env_overrides_the_shared_key_and_the_environment_overrides_both(client, home, monkeypatch):
    save_key(client, "ANTHROPIC_API_KEY")
    domain = get_domain("flight-sim")
    (domain.path / ".env").write_text("ANTHROPIC_API_KEY=domain-own-key\n", encoding="utf-8")
    assert client.get("/api/domains/flight-sim").json()["settings"]["ai"]["key_source"] == "domain"

    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-windows")
    with TestClient(create_app(), headers=HEADERS) as fresh:
        assert fresh.get("/api/domains/flight-sim").json()["settings"]["ai"]["key_source"] == "environment"
        provider = {p["id"]: p for p in fresh.get("/api/ai").json()["providers"]}["anthropic"]
        assert provider["key_source"] == "environment"


def test_a_run_gets_the_shared_key_then_it_is_removed(client, home):
    save_key(client, "ANTHROPIC_API_KEY")
    environ: dict[str, str] = {}
    env = DomainEnvironment(environ)
    domain = get_domain("flight-sim")
    env.apply(domain)
    assert environ["ANTHROPIC_API_KEY"] == SECRET
    (domain.path / ".env").write_text("ANTHROPIC_API_KEY=domain-own-key\n", encoding="utf-8")
    env.apply(domain)
    assert environ["ANTHROPIC_API_KEY"] == "domain-own-key"
    env.clear()
    assert environ == {}


def test_a_key_can_be_replaced_and_deleted(client):
    save_key(client, "ANTHROPIC_API_KEY")
    save_key(client, "ANTHROPIC_API_KEY", "sk-test-replaced")
    assert "sk-test-replaced" in keys_path().read_text(encoding="utf-8")
    assert SECRET not in keys_path().read_text(encoding="utf-8")
    save_key(client, "OPENAI_API_KEY", "sk-other")
    assert client.post("/api/ai/keys/delete", json={"name": "ANTHROPIC_API_KEY"}).status_code == 200
    status = {p["id"]: p for p in client.get("/api/ai").json()["providers"]}
    assert status["anthropic"]["key_present"] is False and status["openai"]["key_present"] is True


@pytest.mark.parametrize("name, value", [
    ("PATH", SECRET),                         # not a provider's key
    ("ANTHROPIC_API_KEY", ""),
    ("ANTHROPIC_API_KEY", "two words"),
    ("ANTHROPIC_API_KEY", "line\nANOTHER=1"),
    ("ANTHROPIC_API_KEY", "quote'inside"),
    ("ANTHROPIC_API_KEY", "x" * 2000),
])
def test_bad_names_and_values_are_refused(client, name, value):
    response = save_key(client, name, value)
    assert response.status_code == 400
    assert value not in response.text or not value
    assert not keys_path().exists()


def test_keys_never_reach_the_logs(client, capfd):
    save_key(client, "ANTHROPIC_API_KEY")
    save_key(client, "ANTHROPIC_API_KEY", "bad value with spaces")
    client.get("/api/domains/flight-sim")
    out, err = capfd.readouterr()
    assert SECRET not in out + err and "bad value with spaces" not in out + err


def test_a_request_from_another_site_cannot_save_a_key(home):
    other = TestClient(create_app(), headers={**HEADERS, "origin": "https://evil.example"})
    assert other.post("/api/ai/keys", json={"name": "ANTHROPIC_API_KEY", "value": SECRET}).status_code == 403
    assert not keys_path().exists()


# -- choosing the AI of a domain ----------------------------------------------------


def test_choosing_a_provider_and_model_writes_horizons_config(client, home):
    before = get_domain("flight-sim").raw_config()["ai"]
    response = client.post("/api/domains/flight-sim/model", json={"provider": "openai", "model": "gpt-test"})
    assert response.status_code == 200, response.text
    ai = get_domain("flight-sim").raw_config()["ai"]
    assert ai["provider"] == "openai" and ai["model"] == "gpt-test" and ai["api_key_env"] == "OPENAI_API_KEY"
    assert ai["languages"] == before["languages"] and ai["temperature"] == before["temperature"]
    assert response.json()["missing_env"] == ["OPENAI_API_KEY"]

    local = client.post("/api/domains/flight-sim/model", json={"provider": "ollama", "model": "llama-test"}).json()
    ai = get_domain("flight-sim").raw_config()["ai"]
    assert ai["provider"] == "ollama" and ai["base_url"].startswith("http://localhost")
    assert local["missing_env"] == [] and local["settings"]["ai"]["api_key_present"] is True

    custom = client.post("/api/domains/flight-sim/model",
                         json={"provider": "ollama", "model": "llama-test", "base_url": "http://192.168.1.20:11434/v1"})
    assert custom.status_code == 200
    assert get_domain("flight-sim").raw_config()["ai"]["base_url"] == "http://192.168.1.20:11434/v1"

    client.post("/api/domains/flight-sim/model", json={"provider": "anthropic", "model": "claude-test"})
    ai = get_domain("flight-sim").raw_config()["ai"]
    assert ai["provider"] == "anthropic" and "base_url" not in ai and ai["api_key_env"] == "ANTHROPIC_API_KEY"


def test_azure_needs_its_api_version_and_endpoint_variable(client):
    client.post("/api/domains/flight-sim/model", json={"provider": "azure", "model": "my-deployment"})
    ai = get_domain("flight-sim").raw_config()["ai"]
    assert ai["azure_endpoint_env"] == "AZURE_OPENAI_ENDPOINT" and ai["api_version"]


@pytest.mark.parametrize("body", [
    {"provider": "openai-chatgpt", "model": "x"},
    {"provider": "nope", "model": "x"},
    {"provider": "openai", "model": ""},
    {"provider": "openai", "model": "x" * 300},
    {"provider": "ollama", "model": "x", "base_url": "not a url"},
])
def test_invalid_choices_are_refused(client, body):
    before = get_domain("flight-sim").config_path.read_bytes()
    assert client.post("/api/domains/flight-sim/model", json=body).status_code == 400
    assert get_domain("flight-sim").config_path.read_bytes() == before


def test_an_empty_model_is_refused_with_horizons_example(client):
    from src.models import AI_PROVIDER_DEFAULTS, AIProvider

    response = client.post("/api/domains/flight-sim/model", json={"provider": "gemini", "model": ""})
    assert response.status_code == 400
    message = response.json()["error"]
    assert "Google Gemini" in message and AI_PROVIDER_DEFAULTS[AIProvider.GEMINI]["model"] in message


def test_a_new_domain_can_use_another_provider(client):
    response = client.post("/api/new-domain", json={
        "id": "boating", "name": "Boating", "languages": ["en"], "copy_from": "flight-sim",
        "provider": "deepseek", "model": "deepseek-test"})
    assert response.status_code == 201, response.text
    ai = get_domain("boating").raw_config()["ai"]
    assert ai["provider"] == "deepseek" and ai["model"] == "deepseek-test" and ai["api_key_env"] == "DEEPSEEK_API_KEY"
