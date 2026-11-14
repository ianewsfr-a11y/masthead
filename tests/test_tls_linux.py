"""The certificate store fix, on Linux, the way a server meets it.

A root that exists only in the operating system's store (as with a company
proxy that inspects HTTPS) must be trusted once masthead.tls.use_system_trust()
ran, and refused before. Verification itself stays on.

Runs in the container test image (docker build --target test), which runs as
root so the test can add a root to the system store and remove it after.
"""

from __future__ import annotations

import datetime
import ipaddress
import os
import shutil
import ssl
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    not (sys.platform.startswith("linux") and os.environ.get("MASTHEAD_SYSTEM_CA_TEST") == "1"),
    reason="needs Linux and the right to change the system store: runs in the container test image",
)

SYSTEM_CA = Path("/usr/local/share/ca-certificates/masthead-test-root.crt")


def _certificates(folder: Path) -> tuple[Path, Path, Path]:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    now = datetime.datetime.now(datetime.timezone.utc)
    root_key = ec.generate_private_key(ec.SECP256R1())
    root_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "MastHead test root (inspecting proxy)")])
    root = (
        x509.CertificateBuilder().subject_name(root_name).issuer_name(root_name)
        .public_key(root_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5)).not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True,
                                     content_commitment=False, key_encipherment=False, data_encipherment=False,
                                     key_agreement=False, encipher_only=False, decipher_only=False), critical=True)
        .sign(root_key, hashes.SHA256())
    )
    leaf_key = ec.generate_private_key(ec.SECP256R1())
    leaf = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")]))
        .issuer_name(root_name).public_key(leaf_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5)).not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost"),
                                                    x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
        .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(root_key, hashes.SHA256())
    )
    pem = serialization.Encoding.PEM
    root_path, leaf_path, key_path = folder / "root.crt", folder / "leaf.crt", folder / "leaf.key"
    root_path.write_bytes(root.public_bytes(pem))
    leaf_path.write_bytes(leaf.public_bytes(pem))
    key_path.write_bytes(leaf_key.private_bytes(pem, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    return root_path, leaf_path, key_path


class _Hello(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 (http.server naming)
        self.send_response(200)
        self.send_header("content-length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


@pytest.fixture()
def https_server(tmp_path):
    root, leaf, key = _certificates(tmp_path)
    shutil.copy(root, SYSTEM_CA)
    subprocess.run(["update-ca-certificates"], check=True, capture_output=True)
    httpd = HTTPServer(("127.0.0.1", 0), _Hello)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)  # built before truststore is injected
    context.load_cert_chain(leaf, key)
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"https://localhost:{httpd.server_address[1]}/"
    httpd.shutdown()
    SYSTEM_CA.unlink(missing_ok=True)
    subprocess.run(["update-ca-certificates", "--fresh"], check=True, capture_output=True)


def test_a_root_known_only_to_the_system_store_is_trusted_after_the_fix(https_server):
    import httpx
    import truststore

    from masthead import tls

    assert ssl.SSLContext.__module__ == "ssl", "start from Python's own ssl, before the fix"
    original = ssl.SSLContext
    try:
        with pytest.raises(httpx.ConnectError, match="CERTIFICATE_VERIFY_FAILED"):
            httpx.get(https_server, timeout=10)  # certifi does not know the root
        tls.use_system_trust()
        response = httpx.get(https_server, timeout=10)
        assert response.status_code == 200 and response.text == "ok"
        assert ssl.create_default_context().verify_mode == ssl.CERT_REQUIRED
    finally:
        if ssl.SSLContext is not original:
            truststore.extract_from_ssl()
