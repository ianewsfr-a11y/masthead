"""Shared test setup."""

from __future__ import annotations

import ssl

import pytest

_ORIGINAL_SSL_CONTEXT = ssl.SSLContext


@pytest.fixture(autouse=True)
def _restore_ssl():
    """Every command calls tls.use_system_trust(), which changes ssl for the whole
    process. Undo it after each test so no test depends on the order they run in."""
    yield
    if ssl.SSLContext is not _ORIGINAL_SSL_CONTEXT:
        import truststore

        truststore.extract_from_ssl()
