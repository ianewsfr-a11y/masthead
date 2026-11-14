"""Check HTTPS certificates against the operating system's store.

Python ships its own list of authorities (certifi). An antivirus that inspects
HTTPS, or a company proxy, re-signs every connection with a root it installs in
the system store only, so Horizon's calls to feeds and to the model fail with
CERTIFICATE_VERIFY_FAILED while the browser works. Using the system store, as
the browser and pip do, fixes that without turning verification off.
"""

from __future__ import annotations

import ssl


def use_system_trust() -> None:
    """Make every TLS connection in this process verify against the system store."""
    import truststore

    if ssl.SSLContext is not truststore.SSLContext:
        truststore.inject_into_ssl()
