"""Each domain's .env stays with that domain: no key leaks from one domain to another."""

from __future__ import annotations

import os
from types import SimpleNamespace

from fastapi.testclient import TestClient

from masthead.domains import create_from_template
from masthead.env import DomainEnvironment
from masthead.runner import RunManager
from masthead.server import create_app

HEADERS = {"host": "127.0.0.1:8765"}


def _domain(path, env_text=None):
    path.mkdir(parents=True, exist_ok=True)
    if env_text is not None:
        (path / ".env").write_text(env_text, encoding="utf-8")
    return SimpleNamespace(id=path.name, path=path)


def test_switching_domain_removes_the_previous_domains_values(tmp_path):
    environ: dict[str, str] = {}
    env = DomainEnvironment(environ)
    alpha = _domain(tmp_path / "alpha", "ANTHROPIC_API_KEY=alpha-value\nEXTRA=1\n")
    beta = _domain(tmp_path / "beta")

    env.apply(alpha)
    assert environ == {"ANTHROPIC_API_KEY": "alpha-value", "EXTRA": "1"}
    env.apply(beta)
    assert environ == {}


def test_the_servers_own_environment_wins_and_is_never_removed(tmp_path):
    environ = {"ANTHROPIC_API_KEY": "from-server"}
    env = DomainEnvironment(environ)
    alpha = _domain(tmp_path / "alpha", "ANTHROPIC_API_KEY=alpha-value\n")
    env.apply(alpha)
    env.apply(_domain(tmp_path / "beta"))
    assert environ == {"ANTHROPIC_API_KEY": "from-server"}
    assert env.is_available(alpha, "ANTHROPIC_API_KEY")


def test_an_empty_variable_does_not_hide_the_domains_value(tmp_path):
    environ = {"ANTHROPIC_API_KEY": ""}  # e.g. "set ANTHROPIC_API_KEY=" left in a shell
    env = DomainEnvironment(environ)
    alpha = _domain(tmp_path / "alpha", "ANTHROPIC_API_KEY=alpha-value\n")
    env.apply(alpha)
    assert environ["ANTHROPIC_API_KEY"] == "alpha-value"
    env.apply(_domain(tmp_path / "beta"))
    assert not environ.get("ANTHROPIC_API_KEY")


def test_a_key_edited_in_the_file_is_taken_at_the_next_run(tmp_path):
    environ: dict[str, str] = {}
    env = DomainEnvironment(environ)
    alpha = _domain(tmp_path / "alpha", "ANTHROPIC_API_KEY=old\n")
    env.apply(alpha)
    (alpha.path / ".env").write_text("ANTHROPIC_API_KEY=new\n", encoding="utf-8")
    env.apply(alpha)
    assert environ["ANTHROPIC_API_KEY"] == "new"


def test_overview_reports_each_domains_own_key_and_leaks_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("MASTHEAD_HOME", str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with_key = create_from_template("flight-sim")
    (with_key.path / ".env").write_text("ANTHROPIC_API_KEY=not-a-real-key\n", encoding="utf-8")
    create_from_template("other")

    with TestClient(create_app(), headers=HEADERS) as client:
        first = client.get("/api/domains/flight-sim").json()
        second = client.get("/api/domains/other").json()
        listing = client.get("/api/domains").json()

    assert first["settings"]["ai"]["api_key_present"] is True and first["missing_env"] == []
    assert second["settings"]["ai"]["api_key_present"] is False
    assert second["missing_env"] == ["ANTHROPIC_API_KEY"]
    assert "not-a-real-key" not in str(listing) + str(first) + str(second)
    assert "ANTHROPIC_API_KEY" not in os.environ  # reading a domain does not load its key


def test_clear_removes_the_applied_values_only(tmp_path):
    environ = {"KEEP": "server"}
    env = DomainEnvironment(environ)
    env.apply(_domain(tmp_path / "alpha", "ANTHROPIC_API_KEY=alpha-value\nKEEP=domain\n"))
    env.clear()
    assert environ == {"KEEP": "server"}


async def test_a_finished_run_leaves_no_domain_value_in_the_environment(tmp_path):
    environ: dict[str, str] = {}
    env = DomainEnvironment(environ)
    alpha = _domain(tmp_path / "alpha", "ANTHROPIC_API_KEY=alpha-value\n")

    class Service:
        domain = alpha
        workspace = "unused"

        async def fetch_items(self, **_):
            assert environ.get("ANTHROPIC_API_KEY") == "alpha-value"  # set while the run goes
            raise RuntimeError("stop here")

        def context(self):
            raise RuntimeError("not needed")

    manager = RunManager(env=env)
    manager.start(Service(), hours=24, until="collect")
    await manager._task
    assert "ANTHROPIC_API_KEY" not in environ


def test_a_domain_without_key_says_so_while_another_domains_key_is_applied(tmp_path, monkeypatch):
    monkeypatch.setenv("MASTHEAD_HOME", str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with_key = create_from_template("flight-sim")
    (with_key.path / ".env").write_text("ANTHROPIC_API_KEY=not-a-real-key\n", encoding="utf-8")
    create_from_template("other")

    app = create_app()
    with TestClient(app, headers=HEADERS) as client:
        app.state.manager.env.apply(with_key)  # as during a run of flight-sim
        try:
            other = client.get("/api/domains/other").json()
        finally:
            app.state.manager.env.clear()
    assert other["missing_env"] == ["ANTHROPIC_API_KEY"]
    assert other["settings"]["ai"]["api_key_present"] is False


async def test_a_run_loads_its_own_domains_values_first(tmp_path):
    applied = []
    env = SimpleNamespace(apply=lambda domain: applied.append(domain.id), clear=lambda: None)

    class Service:
        domain = SimpleNamespace(id="alpha")
        workspace = "unused"

        async def fetch_items(self, **_):
            raise RuntimeError("stop here")

        def context(self):
            raise RuntimeError("not needed")

    manager = RunManager(env=env)
    job = manager.start(Service(), hours=24, until="collect")
    await manager._task
    assert applied == ["alpha"] and job["status"] == "failed"
