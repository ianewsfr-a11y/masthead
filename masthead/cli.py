"""Command line: start the console, import an existing Horizon setup, add demo data."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
import threading
import webbrowser
from pathlib import Path

from . import __version__, tls
from .auth import PasswordError
from .domains import DomainError, ensure_starter_domain, get_domain, home_dir, import_domain, list_domains


LOOPBACK = {"127.0.0.1", "localhost", "::1"}


class StartError(Exception):
    """MastHead must not start with these options."""


def _server_settings(args: argparse.Namespace):
    from .auth import CredentialSource
    from .server import ServerSettings

    public_host = (args.public_host or os.environ.get("MASTHEAD_PUBLIC_HOST") or "").strip()
    if not public_host:
        raise StartError("Server mode needs the public host name: set MASTHEAD_PUBLIC_HOST or use --public-host.")
    port_text = str(args.public_port or os.environ.get("MASTHEAD_PUBLIC_PORT") or "443").strip()
    if not port_text.isdigit() or not 0 < int(port_text) < 65536:
        raise StartError("The public port must be a number from 1 to 65535.")
    credentials = CredentialSource(home_dir())
    if credentials.current() is None:
        raise StartError(
            "Server mode needs a password. Run 'masthead set-password' first, or set MASTHEAD_PASSWORD_HASH."
        )
    return ServerSettings(public_host=public_host, credentials=credentials, public_port=int(port_text))


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    from .server import create_app

    server_mode = args.server or os.environ.get("MASTHEAD_SERVER") == "1"
    if not server_mode and args.host not in LOOPBACK:
        raise StartError("Listening beyond this computer needs server mode, with sign-in: add --server.")
    settings = _server_settings(args) if server_mode else None

    ensure_starter_domain()
    print(f"MastHead {__version__} for Horizon")
    print(f"  Domains folder: {home_dir() / 'domains'}")
    if settings:
        print(f"  Server mode for {settings.origin}/ (listening on {args.host}:{args.port})")
        proxies = args.trusted_proxies or os.environ.get("MASTHEAD_TRUSTED_PROXIES") or "127.0.0.1"
        # Client addresses (used to limit sign-in attempts) are taken from the proxy only.
        uvicorn.run(create_app(server=settings), host=args.host, port=args.port, log_level="warning",
                    proxy_headers=True, forwarded_allow_ips=proxies, server_header=False)
        return 0
    url = f"http://127.0.0.1:{args.port}/"
    print(f"  Open {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    # Loopback only: the console is never reachable from another machine.
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="warning")
    return 0


def _read_password(args: argparse.Namespace) -> str:
    if args.stdin:
        return sys.stdin.readline().rstrip("\r\n")
    first = getpass.getpass("New password: ")
    if getpass.getpass("Same password again: ") != first:
        raise StartError("The two passwords differ.")
    return first


def _set_password(args: argparse.Namespace) -> int:
    from .auth import CredentialSource, hash_password

    credentials = CredentialSource(home_dir())
    if credentials.from_environment:
        raise StartError("The password comes from MASTHEAD_PASSWORD_HASH; change it there.")
    credentials.save(hash_password(_read_password(args)))
    print(f"Password saved (hash only) in {credentials.path}. Every open session is now closed.")
    return 0


def _hash_password(args: argparse.Namespace) -> int:
    from .auth import hash_password

    print(hash_password(_read_password(args)))
    return 0


def _import(args: argparse.Namespace) -> int:
    domain = import_domain(
        args.id, args.name or args.id, Path(args.config), Path(args.profiles) if args.profiles else None
    )
    print(f"Domain '{domain.id}' created in {domain.path}")
    print("Put your AI key in a .env file in that folder, or export it before starting MastHead.")
    return 0


def _demo(args: argparse.Namespace) -> int:
    from .demo import seed_demo_run

    ensure_starter_domain()
    domain = get_domain(args.domain)
    run_id = asyncio.run(seed_demo_run(domain))
    print(f"Demo run '{run_id}' added to domain '{domain.id}'. It is made of invented stories and is labelled as such.")
    return 0


def _list(_: argparse.Namespace) -> int:
    ensure_starter_domain()
    for domain in list_domains():
        print(f"{domain.id}\t{domain.name}\t{domain.path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="masthead", description="MastHead for Horizon: a local console.")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="start the console (default)")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--host", default="127.0.0.1", help="address to listen on (anything but loopback needs --server)")
    serve.add_argument("--server", action="store_true", help="server mode: sign-in required, behind an HTTPS proxy")
    serve.add_argument("--public-host", help="host name users type, e.g. masthead.example.com (or MASTHEAD_PUBLIC_HOST)")
    serve.add_argument("--public-port", help="HTTPS port users type, when not 443 (or MASTHEAD_PUBLIC_PORT)")
    serve.add_argument("--trusted-proxies", help="proxy addresses or networks allowed to give the client address")
    serve.add_argument("--no-browser", action="store_true")
    serve.set_defaults(func=_serve)

    setpw = sub.add_parser("set-password", help="set the server mode password (stored as a hash)")
    setpw.add_argument("--stdin", action="store_true", help="read the password from standard input")
    setpw.set_defaults(func=_set_password)

    hashpw = sub.add_parser("hash-password", help="print a hash for MASTHEAD_PASSWORD_HASH")
    hashpw.add_argument("--stdin", action="store_true", help="read the password from standard input")
    hashpw.set_defaults(func=_hash_password)

    imp = sub.add_parser("import", help="create a domain from an existing Horizon config")
    imp.add_argument("--id", required=True, help="short id, for example flight-sim")
    imp.add_argument("--name", help="display name")
    imp.add_argument("--config", required=True, help="path to Horizon's config.json")
    imp.add_argument("--profiles", help="path to the profiles folder, if you have custom profiles")
    imp.set_defaults(func=_import)

    demo = sub.add_parser("demo", help="add a run made of invented stories, to explore the interface without an AI key")
    demo.add_argument("--domain", default="flight-sim")
    demo.set_defaults(func=_demo)

    lst = sub.add_parser("domains", help="list domains")
    lst.set_defaults(func=_list)

    args = parser.parse_args(argv)
    tls.use_system_trust()
    if args.command is None:
        args = parser.parse_args(["serve", *(argv or [])])
    try:
        return args.func(args)
    except (DomainError, StartError, PasswordError) as exc:
        print(f"masthead: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
