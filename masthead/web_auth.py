"""Who may talk to the server: the loopback guard in local mode, sign-in in server mode."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response

from .auth import MAX_PASSWORD_LENGTH, CredentialSource, LoginLimiter, SessionStore, verify_password

STATIC = Path(__file__).resolve().parent / "static"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]"}
COOKIE = "__Host-masthead"  # the __Host- prefix forces Secure, Path=/ and no Domain
# Reachable without a session: sign-in and sign-out, what the sign-in page needs, and the health check.
PUBLIC_PATHS = {"/healthz", "/login", "/api/login", "/api/logout", "/api/session", "/static/login.js", "/static/app.css"}
# At most this many password checks at once: each one takes about 64 MB and some CPU.
CONCURRENT_CHECKS = 2


class ServerConfigError(Exception):
    """Server mode cannot start with this configuration."""


@dataclass(frozen=True)
class ServerSettings:
    public_host: str
    credentials: CredentialSource
    public_port: int = 443

    @property
    def hostname(self) -> str:
        return host_only(self.public_host)

    @property
    def origin(self) -> str:
        port = "" if self.public_port == 443 else f":{self.public_port}"
        return f"https://{self.hostname}{port}"


def host_only(value: str) -> str:
    value = value.strip().lower()
    if value.startswith("["):
        return value.split("]")[0] + "]"
    return value.split(":")[0]


def _host_and_port(value: str, default_port: int) -> tuple[str, int | None]:
    parts = urlsplit("//" + value.strip().lower())
    try:
        return (parts.hostname or ""), (parts.port or default_port)
    except ValueError:  # a port that is not a number
        return "", None


def _refuse(message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


def _changes_something(request: Request) -> bool:
    return request.method not in ("GET", "HEAD")


def _not_json(request: Request) -> bool:
    media_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    return _changes_something(request) and media_type != "application/json"


def local_refusal(request: Request) -> Response | None:
    """Local mode: only this computer, only the console itself."""
    if host_only(request.headers.get("host", "")) not in LOCAL_HOSTS:
        return _refuse("MastHead only answers on this computer.", 403)
    origin = request.headers.get("origin")
    if origin and host_only(origin.split("://", 1)[-1]) not in LOCAL_HOSTS:
        return _refuse("Cross-site requests are refused.", 403)
    if _not_json(request):
        return _refuse("Requests that change something must be JSON.", 415)
    return None


async def _verify_in_thread(password: str, encoded: str) -> bool:
    # scrypt takes a fraction of a second: keep the event loop free meanwhile.
    return await asyncio.to_thread(verify_password, password, encoded)


class ServerGuard:
    """Server mode: the configured host and port, same-site requests only, and a session."""

    def __init__(self, settings: ServerSettings) -> None:
        if settings.credentials.current() is None:
            raise ServerConfigError(
                "Server mode needs a password. Run 'masthead set-password', or set MASTHEAD_PASSWORD_HASH."
            )
        self.settings = settings
        self.sessions = SessionStore()
        self.limiter = LoginLimiter()
        self.verify: Callable[[str, str], Awaitable[bool]] = _verify_in_thread
        self._checks: asyncio.Semaphore | None = None

    def _semaphore(self) -> asyncio.Semaphore:
        if self._checks is None:
            self._checks = asyncio.Semaphore(CONCURRENT_CHECKS)
        return self._checks

    def busy(self) -> bool:
        return self._semaphore().locked()

    async def check_password(self, password: str, encoded: str) -> bool | None:
        """True or False, or None when too many checks are already running."""
        if self.busy():
            return None
        async with self._semaphore():
            return await self.verify(password, encoded)

    def signed_in(self, request: Request) -> bool:
        return self.sessions.check(request.cookies.get(COOKIE), self.settings.credentials.current())

    def _same_place(self, value: str) -> bool:
        host, port = _host_and_port(value, 443)
        return host == self.settings.hostname and port == self.settings.public_port

    def refusal(self, request: Request) -> Response | None:
        path = request.url.path
        if path == "/healthz":
            return None
        if not self._same_place(request.headers.get("host", "")):
            return _refuse("Unknown host.", 403)
        origin = request.headers.get("origin")
        if origin:
            parts = urlsplit(origin)
            if parts.scheme != "https" or not self._same_place(parts.netloc):
                return _refuse("Cross-site requests are refused.", 403)
        elif _changes_something(request):
            return _refuse("Requests that change something must come from the console.", 403)
        if _not_json(request):
            return _refuse("Requests that change something must be JSON.", 415)
        if path in PUBLIC_PATHS or self.signed_in(request):
            return None
        if path.startswith("/api/"):
            return _refuse("Sign in first.", 401)
        return RedirectResponse("/login", status_code=303)

    def install_routes(self, app: FastAPI) -> None:
        sessions, limiter, credentials = self.sessions, self.limiter, self.settings.credentials

        @app.get("/login")
        async def login_page() -> FileResponse:
            return FileResponse(STATIC / "login.html")

        @app.post("/api/login")
        async def login(request: Request, body: dict[str, Any]) -> JSONResponse:
            address = request.client.host if request.client else "unknown"
            wait = limiter.retry_after(address)
            if wait:
                return JSONResponse({"error": "Too many attempts. Try again later."}, status_code=429,
                                    headers={"Retry-After": str(wait)})
            password = body.get("password")
            if not isinstance(password, str) or not password or len(password) > MAX_PASSWORD_LENGTH:
                return _refuse("Type the password.", 400)
            credential = credentials.current()
            if credential is None:
                return _refuse("No password is set on this server.", 503)
            if self.busy():
                return JSONResponse({"error": "Busy. Try again in a few seconds."}, status_code=429,
                                    headers={"Retry-After": "2"})
            # Counted before the check, so parallel attempts cannot all get through.
            limiter.failure(address)
            if not await self.check_password(password, credential):
                return _refuse("Wrong password.", 401)
            limiter.success(address)
            response = JSONResponse({"signed_in": True})
            response.set_cookie(COOKIE, sessions.create(credential), max_age=sessions.ttl, path="/",
                                secure=True, httponly=True, samesite="strict")
            return response

        @app.post("/api/logout")
        async def logout(request: Request) -> JSONResponse:
            sessions.revoke(request.cookies.get(COOKIE))
            response = JSONResponse({"signed_in": False})
            response.delete_cookie(COOKIE, path="/", secure=True, httponly=True, samesite="strict")
            return response
