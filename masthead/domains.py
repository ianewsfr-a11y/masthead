"""Domains: one Horizon workspace (config, profiles, data, runs) per subject."""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DOMAIN_ID_RE = re.compile(r"^[a-z][a-z0-9-]{0,40}$")


class DomainError(Exception):
    """A problem with a domain that the user can fix."""


def home_dir() -> Path:
    """Where MastHead keeps its domains. Nothing is stored anywhere else."""
    return Path(os.environ.get("MASTHEAD_HOME", "~/.masthead")).expanduser().resolve()


@dataclass
class Domain:
    id: str
    path: Path

    @property
    def config_path(self) -> Path:
        return self.path / "data" / "config.json"

    @property
    def runs_root(self) -> Path:
        return self.path / "data" / "mcp-runs"

    @property
    def meta_path(self) -> Path:
        return self.path / "domain.json"

    def meta(self) -> dict[str, Any]:
        try:
            value = json.loads(self.meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            value = {}
        return value if isinstance(value, dict) else {}

    @property
    def name(self) -> str:
        return str(self.meta().get("name") or self.id)

    def raw_config(self) -> dict[str, Any]:
        """The config file as written, with ${ENV} placeholders left untouched."""
        try:
            value = json.loads(self.config_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise DomainError(f"Domain '{self.id}' has no data/config.json.") from exc
        except ValueError as exc:
            raise DomainError(f"data/config.json of '{self.id}' is not valid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise DomainError(f"data/config.json of '{self.id}' must be a JSON object.")
        return value

    def write_raw_config(self, raw: dict[str, Any]) -> None:
        """Validate with Horizon's own model, back up, then write."""
        from src.models import Config
        from src.storage.manager import _expand_env_vars

        try:
            Config.model_validate(_expand_env_vars(json.loads(json.dumps(raw))))
        except Exception as exc:  # pydantic's message is the useful part
            raise DomainError(f"Horizon rejected this configuration: {exc}") from exc
        if self.config_path.exists():
            shutil.copy2(self.config_path, self.config_path.with_suffix(".json.bak"))
        tmp = self.config_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.config_path)


def _check_id(domain_id: str) -> str:
    if not DOMAIN_ID_RE.fullmatch(domain_id or ""):
        raise DomainError("A domain id uses lowercase letters, digits and dashes, starting with a letter.")
    return domain_id


def domains_dir() -> Path:
    path = home_dir() / "domains"
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_domains() -> list[Domain]:
    return [
        Domain(id=child.name, path=child)
        for child in sorted(domains_dir().iterdir())
        if child.is_dir() and DOMAIN_ID_RE.fullmatch(child.name) and (child / "data" / "config.json").exists()
    ]


def get_domain(domain_id: str) -> Domain:
    path = domains_dir() / _check_id(domain_id)
    if not (path / "data" / "config.json").exists():
        raise DomainError(f"Domain '{domain_id}' does not exist.")
    return Domain(id=domain_id, path=path)


def import_domain(domain_id: str, name: str, config: Path, profiles: Path | None = None) -> Domain:
    """Create a domain from an existing Horizon config file and profiles folder."""
    config = Path(config).expanduser().resolve()
    if not config.is_file():
        raise DomainError(f"Config file not found: {config}")
    target = domains_dir() / _check_id(domain_id)
    if target.exists():
        raise DomainError(f"Domain '{domain_id}' already exists.")
    (target / "data").mkdir(parents=True)
    try:
        shutil.copy2(config, target / "data" / "config.json")
        if profiles is not None:
            profiles = Path(profiles).expanduser().resolve()
            if not profiles.is_dir():
                raise DomainError(f"Profiles folder not found: {profiles}")
            shutil.copytree(profiles, target / "profiles")
        (target / "domain.json").write_text(
            json.dumps({"name": name or domain_id, "description": f"Imported from {config}"}, indent=2) + "\n",
            encoding="utf-8",
        )
        domain = Domain(id=domain_id, path=target)
        # A relative profiles_dir must resolve inside the domain.
        raw = domain.raw_config()
        processing = raw.setdefault("processing", {})
        if profiles is not None:
            processing["profiles_dir"] = "profiles"
        domain.write_raw_config(raw)
        return domain
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        raise

