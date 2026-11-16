"""Helpers shared by the tests: a ready-made domain to copy, outside the product."""

from __future__ import annotations

import shutil
from pathlib import Path

from masthead.domains import Domain, DomainError, _check_id, domains_dir

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def create_from_template(domain_id: str, template: str = "flight-sim") -> Domain:
    """A domain copied from tests/fixtures (the former starter domain)."""
    source = FIXTURES_DIR / template
    target = domains_dir() / _check_id(domain_id)
    if target.exists():
        raise DomainError(f"Domain '{domain_id}' already exists.")
    shutil.copytree(source, target)
    return Domain(id=domain_id, path=target)
