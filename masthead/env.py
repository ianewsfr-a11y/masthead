"""Each domain's .env file, kept apart from the other domains.

Horizon loads a workspace's .env into the process environment and never
removes it, so in one long-lived process the first domain's key would serve
every other domain. MastHead loads a domain's values only when a run of that
domain starts, and removes the previous domain's values first.

The environment the server was started with always wins over a domain's file,
as in Horizon, and is never removed.
"""

from __future__ import annotations

import os
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any

from dotenv import dotenv_values


def domain_values(domain: Any) -> dict[str, str]:
    """The non-empty values written in the domain's .env file."""
    path = Path(domain.path) / ".env"
    if not path.is_file():
        return {}
    return {name: value for name, value in dotenv_values(path).items() if value}


class DomainEnvironment:
    """Applies one domain's .env at a time on top of the server's own environment."""

    def __init__(self, environ: MutableMapping[str, str] | None = None) -> None:
        self._environ = os.environ if environ is None else environ
        self._base = dict(self._environ)
        self._applied: set[str] = set()

    def is_available(self, domain: Any, name: str | None) -> bool:
        """Whether a variable will be set when this domain runs. The value is never returned."""
        if not name:
            return False
        return bool(self._base.get(name)) or name in domain_values(domain)

    def apply(self, domain: Any) -> None:
        for name in self._applied:
            if name not in self._base:
                self._environ.pop(name, None)
        self._applied = set()
        for name, value in domain_values(domain).items():
            if name not in self._base:
                self._environ[name] = value
                self._applied.add(name)
