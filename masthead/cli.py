"""Command line: start the console, import an existing Horizon setup, list domains."""

from __future__ import annotations

import argparse
import sys
import threading
import webbrowser
from pathlib import Path

from . import __version__, tls
from .domains import DomainError, home_dir, import_domain, list_domains


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    from .server import create_app

    url = f"http://127.0.0.1:{args.port}/"
    print(f"MastHead {__version__} for Horizon")
    print(f"  Domains folder: {home_dir() / 'domains'}")
    print(f"  Open {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    # Loopback only: the console is never reachable from another machine.
    uvicorn.run(create_app(), host="127.0.0.1", port=args.port, log_level="warning")
    return 0


def _import(args: argparse.Namespace) -> int:
    domain = import_domain(
        args.id, args.name or args.id, Path(args.config), Path(args.profiles) if args.profiles else None
    )
    print(f"Domain '{domain.id}' created in {domain.path}")
    print("Enter your AI key in MastHead (Domains, AI keys), or put it in a .env file in that folder.")
    return 0


def _list(_: argparse.Namespace) -> int:
    for domain in list_domains():
        print(f"{domain.id}\t{domain.name}\t{domain.path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="masthead", description="MastHead for Horizon: a local console.")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="start the console (default)")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--no-browser", action="store_true")
    serve.set_defaults(func=_serve)

    imp = sub.add_parser("import", help="create a domain from an existing Horizon config")
    imp.add_argument("--id", required=True, help="short id, for example boating")
    imp.add_argument("--name", help="display name")
    imp.add_argument("--config", required=True, help="path to Horizon's config.json")
    imp.add_argument("--profiles", help="path to the profiles folder, if you have custom profiles")
    imp.set_defaults(func=_import)

    lst = sub.add_parser("domains", help="list domains")
    lst.set_defaults(func=_list)

    args = parser.parse_args(argv)
    tls.use_system_trust()
    if args.command is None:
        args = parser.parse_args(["serve", *(argv or [])])
    try:
        return args.func(args)
    except DomainError as exc:
        print(f"masthead: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
