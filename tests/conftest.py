"""Shared test setup."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _private_home(tmp_path, monkeypatch):
    """Every test gets its own MastHead folder, so no test reads the keys or
    domains of the person running the tests."""
    monkeypatch.setenv("MASTHEAD_HOME", str(tmp_path))
