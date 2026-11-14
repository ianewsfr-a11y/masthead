"""Who may talk to the server: the loopback guard in local mode, sign-in in server mode."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response

from .auth import CredentialSource, LoginLimiter, SessionStore, verify_password

STATIC = Path(__file__).resolve().parent / "static"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]"}
COOKIE = "__Host-masthead"  # the __Host- prefix forces Secure, Path=/ and no Domain
# Reachable without a session: the sign-in page and what it needs, and the health check.
PUBLIC_PATHS = {"/healthz", "/login", "/api/login", "/api/session", "/static/login.js", "/static/app.css"}


class ServerConfigError(Exception):
    """Server mode cannot start with this configuration."""


@dataclass(frozen=True)
class ServerSettings:
    public_host: str
    credentials: CredentialSource

    @property
    def hostname(self) -> str:
        return host_only(self.public_host)


def host_only(value: str) -> str:
    value = value.strip().lower()
    if value.startswith("["):
        return value.split("]")[0] + "]"
    return value.split(":")[0]


def _refuse(message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


def _changes_something(request: Request) -> bool:
    return request.method not in ("GET", "HEAD")


def _not_json(request: Request) -> bool:
    return _changes_something(request) and "application/json" not in request.headers.get("content-type", "")


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


class ServerGuard:
    """Server mode: the configured host name, same-site requests only, and a session."""

    def __init__(self, settings: ServerSettings) -> None:
        if settings.credentials.current() is None:
            raise ServerConfigError(
                "Server mode needs a password. Run 'masthead set-password', or set MASTHEAD_PASSWORD_HASH."
            )
        self.settings = settings
        self.sessions = SessionStore()
        self.limiter = LoginLimiter()

    def signed_in(self, request: Request) -> bool:
        return self.sessions.check(request.cookies.get(COOKIE), self.settings.credentials.current())

    def refusal(self, request: Request) -> Response | None:
        path = request.url.path
        if path == "/healthz":
            return None
        if host_only(request.headers.get("host", "")) != self.settings.hostname:
            return _refuse("Unknown host.", 403)
        origin = request.headers.get("origin")
        if origin:
            parts = urlsplit(origin)
            if parts.scheme != "https" or (parts.hostname or "") != self.settings.hostname:
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
            if not isinstance(password, str) or not password:
                return _refuse("Type the password.", 400)
            credential = credentials.current()
            if credential is None:
                return _refuse("No password is set on this server.", 503)
            # scrypt takes a fraction of a second: keep the event loop free meanwhile.
            if not await asyncio.to_thread(verify_password, password, credential):
                limiter.failure(address)
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
