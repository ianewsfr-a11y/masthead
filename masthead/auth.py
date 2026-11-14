"""Sign-in for server mode: password hash, sessions in memory, and a limit on attempts.

One user per instance. The password is never stored, logged or returned: only
a salted scrypt hash, read from MASTHEAD_PASSWORD_HASH or from auth.json in
MastHead's home folder. Sessions live in memory, so restarting the server signs
the user out, and every session ends when the password changes.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from collections import deque
from pathlib import Path
from typing import Callable

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 1024  # longer input is refused before any hashing
ENV_HASH = "MASTHEAD_PASSWORD_HASH"
AUTH_FILE = "auth.json"
SESSION_TTL_SECONDS = 7 * 24 * 3600

# scrypt cost: about 64 MB and a fraction of a second per check.
_N, _R, _P = 2**16, 8, 1
_MAXMEM = 128 * 1024 * 1024


class PasswordError(ValueError):
    """A password that cannot be accepted."""


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def hash_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordError(f"Use at least {MIN_PASSWORD_LENGTH} characters.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise PasswordError(f"Use at most {MAX_PASSWORD_LENGTH} characters.")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, maxmem=_MAXMEM, dklen=32)
    return f"scrypt${_N}${_R}${_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, encoded: str | None) -> bool:
    try:
        scheme, n, r, p, salt, expected = (encoded or "").split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"), salt=base64.b64decode(salt),
            n=int(n), r=int(r), p=int(p), maxmem=_MAXMEM, dklen=32,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, base64.b64decode(expected))


class CredentialSource:
    """Where the password hash comes from. The environment wins over the file."""

    def __init__(self, home: Path, environ: dict[str, str] | None = None) -> None:
        self.path = Path(home) / AUTH_FILE
        self._environ = environ

    def _env(self) -> dict[str, str]:
        return os.environ if self._environ is None else self._environ  # type: ignore[return-value]

    @property
    def from_environment(self) -> bool:
        return bool(self._env().get(ENV_HASH))

    def current(self) -> str | None:
        if self.from_environment:
            return self._env()[ENV_HASH].strip()
        try:
            value = json.loads(self.path.read_text(encoding="utf-8")).get("password")
        except (OSError, ValueError, AttributeError):
            return None
        return value if isinstance(value, str) and value.startswith("scrypt$") else None

    def save(self, encoded: str) -> None:
        if self.from_environment:
            raise PasswordError(f"The password comes from {ENV_HASH}; change it there.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.unlink(missing_ok=True)
        # Created with owner-only rights from the start: the hash is never readable by others.
        descriptor = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"password": encoded}) + "\n")
        tmp.replace(self.path)


class SessionStore:
    """Sessions in memory. Tokens are kept hashed; each one is tied to the password it was opened with."""

    def __init__(self, ttl_seconds: int = SESSION_TTL_SECONDS, clock: Callable[[], float] = time.time) -> None:
        self.ttl = ttl_seconds
        self._clock = clock
        self._sessions: dict[str, tuple[float, str]] = {}

    @staticmethod
    def _key(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _tag(credential: str) -> str:
        return hashlib.sha256(credential.encode("utf-8")).hexdigest()

    def create(self, credential: str) -> str:
        now = self._clock()
        self._sessions = {key: value for key, value in self._sessions.items() if value[0] > now}
        token = secrets.token_urlsafe(32)
        self._sessions[self._key(token)] = (self._clock() + self.ttl, self._tag(credential))
        return token

    def check(self, token: str | None, credential: str | None) -> bool:
        if not token or not credential:
            return False
        found = self._sessions.get(self._key(token))
        if found is None:
            return False
        expires, tag = found
        if not hmac.compare_digest(tag, self._tag(credential)):
            self.revoke_all()  # the password changed: every session ends
            return False
        if self._clock() >= expires:
            self._sessions.pop(self._key(token), None)
            return False
        return True

    def revoke(self, token: str | None) -> None:
        if token:
            self._sessions.pop(self._key(token), None)

    def revoke_all(self) -> None:
        self._sessions.clear()


class LoginLimiter:
    """Sign-in attempts per address and overall, over a sliding window.

    An attempt counts as a failure from the moment it starts and is cleared if
    it succeeds, so parallel attempts cannot all pass before the first result.
    An address that signed in successfully in the last 30 days is not held by
    the overall limit, so strangers failing elsewhere cannot lock the owner out.
    """

    KNOWN_SECONDS = 30 * 24 * 3600

    def __init__(
        self,
        per_address: int = 5,
        overall: int = 50,
        window_seconds: int = 15 * 60,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.per_address = per_address
        self.overall = overall
        self.window = window_seconds
        self._clock = clock
        self._failures: deque[tuple[float, str]] = deque()
        self._known: dict[str, float] = {}

    def _prune(self) -> float:
        now = self._clock()
        while self._failures and self._failures[0][0] <= now - self.window:
            self._failures.popleft()
        return now

    def retry_after(self, address: str) -> int:
        """Seconds to wait before this address may try again; 0 when it may try now."""
        now = self._prune()
        mine = [at for at, who in self._failures if who == address]
        waits = []
        if len(mine) >= self.per_address:
            waits.append(mine[-self.per_address] + self.window - now)
        known = self._known.get(address, float("-inf")) > now - self.KNOWN_SECONDS
        if len(self._failures) >= self.overall and not known:
            waits.append(self._failures[-self.overall][0] + self.window - now)
        return max(1, int(max(waits)) + 1) if waits else 0

    def failure(self, address: str) -> None:
        self._prune()
        self._failures.append((self._clock(), address))

    def success(self, address: str) -> None:
        self._failures = deque(item for item in self._failures if item[1] != address)
        self._known[address] = self._clock()
