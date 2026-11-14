"""Fixes found during the first real run. One test per fix; no network and no model."""

from __future__ import annotations

import ssl

import pytest

from masthead import cli, tls
from masthead.runner import collect_detail


@pytest.fixture()
def restore_ssl():
    original = ssl.SSLContext
    yield
    if ssl.SSLContext is not original:
        import truststore

        truststore.extract_from_ssl()


def test_certificates_are_checked_against_the_system_store(restore_ssl):
    """An antivirus or a company proxy that inspects HTTPS installs its root in the
    operating system's store, not in certifi. Verification must stay on, against
    the store the browser uses."""
    import truststore

    tls.use_system_trust()
    tls.use_system_trust()  # calling twice is harmless
    assert ssl.SSLContext is truststore.SSLContext
    context = ssl.create_default_context()
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname is True


def test_every_command_uses_the_system_store(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setenv("MASTHEAD_HOME", str(tmp_path))
    monkeypatch.setattr(tls, "use_system_trust", lambda: calls.append(True))
    assert cli.main(["domains"]) == 0
    assert calls == [True]


def test_collect_detail_counts_feeds_not_source_groups():
    """Horizon reports all RSS feeds as one source. Nine failed feeds out of ten
    sources must not read as '1 of 2 sources failed'."""
    failures = {f"Feed {n}": "ConnectError: certificate verify failed" for n in range(9)}
    fetched = {
        "raw_before_merge": 15,
        "fetched": 15,
        "fetch_report": {
            "status": "partial_failure", "attempted": 2, "failed": 1,
            "sources": [
                {"source": "RSS Feeds", "status": "failure", "item_count": 0, "failures": failures},
                {"source": "Google News", "status": "success", "item_count": 15},
            ],
        },
    }
    assert collect_detail(fetched, enabled_sources=10) == (
        "15 collected, 15 after removing repeated links, 9 of 10 sources failed"
    )


def test_collect_detail_partial_group_and_clean_run():
    fetched = {
        "raw_before_merge": 40, "fetched": 38,
        "fetch_report": {"status": "partial_failure", "sources": [
            {"source": "RSS Feeds", "status": "partial_failure", "item_count": 30, "failures": {"A": "timeout"}},
            {"source": "GitHub", "status": "failure", "item_count": 0, "error": "rate limited"},
        ]},
    }
    assert collect_detail(fetched, enabled_sources=6).endswith("2 of 6 sources failed")
    clean = {"raw_before_merge": 5, "fetched": 5, "fetch_report": {"status": "success", "sources": []}}
    assert collect_detail(clean, enabled_sources=3) == "5 collected, 5 after removing repeated links"
