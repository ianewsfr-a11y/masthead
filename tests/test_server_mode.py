"""Server mode: sign-in, session, cross-site protection, and refusal to start without a password.

Local mode is covered by the other test files and must keep passing unchanged.
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from masthead import cli
from masthead.auth import (
    CredentialSource,
    LoginLimiter,
    PasswordError,
    SessionStore,
    hash_password,
    verify_password,
)
from masthead.domains import create_from_template
from masthead.server import ServerConfigError, ServerSettings, create_app

HOST = "masthead.example.org"
ORIGIN = f"https://{HOST}"
PASSWORD = "correct horse battery staple"


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MASTHEAD_HOME", str(tmp_path))
    monkeypatch.delenv("MASTHEAD_PASSWORD_HASH", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    create_from_template("flight-sim")
    return tmp_path


@pytest.fixture()
def credentials(home):
    source = CredentialSource(home)
    source.save(hash_password(PASSWORD))
    return source


@pytest.fixture()
def app(credentials):
    return create_app(server=ServerSettings(public_host=HOST, credentials=credentials))


def browser(app, **headers):
    return TestClient(app, base_url=f"https://{HOST}", headers={"origin": ORIGIN, **headers})


def sign_in(client, password=PASSWORD):
    return client.post("/api/login", json={"password": password})


# -- passwords -----------------------------------------------------------------


def test_password_is_stored_as_a_salted_scrypt_hash():
    first, second = hash_password(PASSWORD), hash_password(PASSWORD)
    assert first.startswith("scrypt$") and first != second  # salted
    assert PASSWORD not in first
    assert verify_password(PASSWORD, first)
    assert not verify_password(PASSWORD + "x", first)
    assert not verify_password(PASSWORD, "not-a-hash")
    with pytest.raises(PasswordError):
        hash_password("short")


def test_set_password_command_writes_only_the_hash(home, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(PASSWORD + "\n"))
    assert cli.main(["set-password", "--stdin"]) == 0
    stored = (home / "auth.json").read_text(encoding="utf-8")
    assert PASSWORD not in stored and "scrypt$" in stored
    assert verify_password(PASSWORD, CredentialSource(home).current())


def test_set_password_refuses_when_the_hash_comes_from_the_environment(home, monkeypatch, capsys):
    monkeypatch.setenv("MASTHEAD_PASSWORD_HASH", hash_password(PASSWORD))
    monkeypatch.setattr("sys.stdin", io.StringIO("another long password\n"))
    assert cli.main(["set-password", "--stdin"]) == 2
    assert "MASTHEAD_PASSWORD_HASH" in capsys.readouterr().err


def test_environment_hash_takes_precedence(home, monkeypatch):
    source = CredentialSource(home)
    source.save(hash_password("password from the file"))
    monkeypatch.setenv("MASTHEAD_PASSWORD_HASH", hash_password(PASSWORD))
    assert verify_password(PASSWORD, source.current())


# -- refusing to start ---------------------------------------------------------


def test_server_mode_refuses_to_start_without_a_password(home, monkeypatch, capsys):
    monkeypatch.setenv("MASTHEAD_PUBLIC_HOST", HOST)
    monkeypatch.setattr("uvicorn.run", lambda *a, **k: pytest.fail("must not start"))
    assert cli.main(["serve", "--server", "--host", "0.0.0.0", "--no-browser"]) == 2
    assert "password" in capsys.readouterr().err.lower()
    with pytest.raises(ServerConfigError):
        create_app(server=ServerSettings(public_host=HOST, credentials=CredentialSource(home)))


def test_server_mode_refuses_to_start_without_a_public_host(credentials, monkeypatch, capsys):
    monkeypatch.delenv("MASTHEAD_PUBLIC_HOST", raising=False)
    monkeypatch.setattr("uvicorn.run", lambda *a, **k: pytest.fail("must not start"))
    assert cli.main(["serve", "--server", "--host", "0.0.0.0", "--no-browser"]) == 2
    assert "MASTHEAD_PUBLIC_HOST" in capsys.readouterr().err


def test_listening_beyond_loopback_requires_server_mode(credentials, monkeypatch, capsys):
    monkeypatch.setattr("uvicorn.run", lambda *a, **k: pytest.fail("must not start"))
    assert cli.main(["serve", "--host", "0.0.0.0", "--no-browser"]) == 2
    assert "--server" in capsys.readouterr().err


def test_server_mode_starts_with_a_password(credentials, monkeypatch):
    started = {}
    monkeypatch.setenv("MASTHEAD_PUBLIC_HOST", HOST)
    monkeypatch.setattr("uvicorn.run", lambda app, **kwargs: started.update(kwargs))
    assert cli.main(["serve", "--server", "--host", "0.0.0.0", "--no-browser"]) == 0
    assert started["host"] == "0.0.0.0" and started["proxy_headers"] is True


# -- signing in ----------------------------------------------------------------


def test_everything_but_health_and_sign_in_needs_a_session(app):
    client = browser(app)
    assert client.get("/api/domains").status_code == 401
    page = client.get("/", follow_redirects=False)
    assert page.status_code == 303 and page.headers["location"] == "/login"
    assert client.get("/static/app.js", follow_redirects=False).status_code == 303
    assert client.get("/login").status_code == 200
    assert client.get("/static/login.js").status_code == 200
    health = client.get("/healthz")
    assert health.status_code == 200 and health.json() == {"status": "ok"}
    assert client.get("/api/session").json() == {"mode": "server", "signed_in": False}


def test_sign_in_sets_a_strict_session_cookie(app):
    client = browser(app)
    wrong = sign_in(client, "wrong password, long enough")
    assert wrong.status_code == 401 and "set-cookie" not in wrong.headers

    ok = sign_in(client)
    assert ok.status_code == 200
    cookie = ok.headers["set-cookie"]
    assert cookie.startswith("__Host-masthead=")
    for flag in ("HttpOnly", "Secure", "SameSite=Strict", "Path=/"):
        assert flag.lower() in cookie.lower()
    assert "Domain=" not in cookie
    assert client.get("/api/domains").status_code == 200
    assert client.get("/api/session").json() == {"mode": "server", "signed_in": True}


def test_sign_out_ends_the_session(app):
    client = browser(app)
    sign_in(client)
    token = client.cookies.get("__Host-masthead")
    out = client.post("/api/logout", json={})
    assert out.status_code == 200 and "max-age=0" in out.headers["set-cookie"].lower()
    assert client.get("/api/domains").status_code == 401
    replay = browser(app)
    replay.cookies.set("__Host-masthead", token, domain=HOST)
    assert replay.get("/api/domains").status_code == 401


def test_changing_the_password_closes_every_session(app, credentials):
    first, second = browser(app), browser(app)
    sign_in(first)
    sign_in(second)
    credentials.save(hash_password("a brand new long password"))
    assert first.get("/api/domains").status_code == 401
    assert second.get("/api/domains").status_code == 401
    assert sign_in(first).status_code == 401
    assert sign_in(first, "a brand new long password").status_code == 200


def test_sessions_expire():
    now = [1000.0]
    store = SessionStore(ttl_seconds=60, clock=lambda: now[0])
    token = store.create("credential")
    assert store.check(token, "credential")
    now[0] += 61
    assert not store.check(token, "credential")
    assert not store.check("forged", "credential")


# -- cross-site requests and hosts ----------------------------------------------


def test_cross_site_and_foreign_host_requests_are_refused(app):
    client = browser(app)
    sign_in(client)
    change = {"max_items": 5}
    assert client.post("/api/domains/flight-sim/settings", json=change,
                       headers={"origin": "https://evil.example"}).status_code == 403
    no_origin = TestClient(app, base_url=f"https://{HOST}")
    no_origin.cookies = client.cookies
    assert no_origin.post("/api/domains/flight-sim/settings", json=change).status_code == 403
    assert client.post("/api/domains/flight-sim/settings", data={"max_items": "5"}).status_code == 415
    assert client.post("/api/domains/flight-sim/settings", json=change).status_code == 200

    other_host = TestClient(app, base_url="https://evil.example", headers={"origin": "https://evil.example"})
    assert other_host.get("/api/domains").status_code == 403
    assert other_host.get("/login").status_code == 403


def test_sign_in_from_another_site_is_refused(app):
    assert browser(app, origin="https://evil.example").post(
        "/api/login", json={"password": PASSWORD}).status_code == 403


# -- rate limit -----------------------------------------------------------------


def test_sign_in_attempts_are_limited(app):
    client = browser(app)
    for _ in range(5):
        assert sign_in(client, "wrong password, long enough").status_code == 401
    blocked = sign_in(client)  # even the right password waits
    assert blocked.status_code == 429 and int(blocked.headers["retry-after"]) > 0


def test_limiter_counts_per_address_and_overall():
    now = [0.0]
    limiter = LoginLimiter(per_address=2, overall=3, window_seconds=60, clock=lambda: now[0])
    limiter.failure("a")
    limiter.failure("a")
    assert limiter.retry_after("a") > 0 and limiter.retry_after("b") == 0
    limiter.failure("b")
    assert limiter.retry_after("c") > 0  # too many failures overall
    now[0] += 61
    assert limiter.retry_after("a") == 0 and limiter.retry_after("c") == 0


# -- secrets stay out of logs and responses --------------------------------------


def test_no_password_or_session_token_in_logs(app, capfd):
    client = browser(app)
    sign_in(client, "wrong password, long enough")
    sign_in(client)
    token = client.cookies.get("__Host-masthead")
    client.get("/api/domains")
    out, err = capfd.readouterr()
    for secret in (PASSWORD, "wrong password, long enough", token):
        assert secret not in out and secret not in err


async def test_no_article_text_in_logs(app, capfd):
    from masthead.demo import seed_demo_run
    from masthead.domains import get_domain

    run_id = await seed_demo_run(get_domain("flight-sim"))  # Horizon's real selection and briefing
    client = browser(app)
    sign_in(client)
    detail = client.get(f"/api/domains/flight-sim/runs/{run_id}").json()
    client.get(f"/api/domains/flight-sim/runs/{run_id}/briefing", params={"language": "en"})
    titles = [d["title"] for d in detail["journal"]["decisions"]]
    out, err = capfd.readouterr()
    assert titles and not any(title in out or title in err for title in titles)
    assert "Invented story" not in out + err


# -- local mode is unchanged ----------------------------------------------------


def test_local_mode_has_no_sign_in(home):
    client = TestClient(create_app(), headers={"host": "127.0.0.1:8765"})
    assert client.get("/api/domains").status_code == 200
    assert client.get("/api/session").json() == {"mode": "local", "signed_in": True}
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/login").status_code == 404
