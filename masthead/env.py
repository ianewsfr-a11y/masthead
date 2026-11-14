"""The keys and settings a domain's run sees, kept apart from the other domains.

Horizon loads a workspace's .env into the process environment and never
removes it, so in one long-lived process the first domain's key would serve
every other domain. MastHead loads a domain's values only while one of its
runs goes, and removes them afterwards.

Order, strongest first:
1. the environment MastHead was started with (for example a Windows variable),
   never changed and never removed;
2. the domain's own .env file;
3. the keys entered in MastHead's interface (keys.env), shared by every domain.
"""

from __future__ import annotations

import os
from collections.abc import Callable, MutableMapping
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

from . import keys


def domain_values(domain: Any) -> dict[str, str]:
    """The non-empty values written in the domain's .env file."""
    path = Path(domain.path) / ".env"
    if not path.is_file():
        return {}
    return {name: value for name, value in dotenv_values(path).items() if value}


class DomainEnvironment:
    """Applies one domain's values at a time on top of the starting environment."""

    def __init__(
        self,
        environ: MutableMapping[str, str] | None = None,
        shared: Callable[[], dict[str, str]] = keys.read_shared,
    ) -> None:
        self._environ = os.environ if environ is None else environ
        # An empty variable counts as unset, so it does not hide the domain's value.
        self._base = {name: value for name, value in self._environ.items() if value}
        self._shared = shared
        self._applied: set[str] = set()

    def values_for(self, domain: Any) -> dict[str, str]:
        return {**self._shared(), **domain_values(domain)}

    def source(self, domain: Any, name: str | None) -> str | None:
        """Where a variable comes from for this domain: environment, domain, shared, or None.
        The value is never returned."""
        if not name:
            return None
        if self._base.get(name):
            return "environment"
        if name in domain_values(domain):
            return "domain"
        if name in self._shared():
            return "shared"
        return None

    def global_source(self, name: str | None) -> str | None:
        """The same, for no domain in particular (the AI keys panel)."""
        if not name:
            return None
        if self._base.get(name):
            return "environment"
        return "shared" if name in self._shared() else None

    def is_available(self, domain: Any, name: str | None) -> bool:
        return self.source(domain, name) is not None

    def clear(self) -> None:
        """Remove the values applied for the last domain; the starting environment stays."""
        for name in self._applied:
            if name not in self._base:
                self._environ.pop(name, None)
        self._applied = set()

    def apply(self, domain: Any) -> None:
        self.clear()
        for name, value in self.values_for(domain).items():
            if name not in self._base:
                self._environ[name] = value
                self._applied.add(name)
