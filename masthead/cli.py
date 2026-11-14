"""Command line: start the console, import an existing Horizon setup, add demo data."""

from __future__ import annotations

import argparse
import asyncio
import sys
import threading
import webbrowser
from pathlib import Path

from . import __version__, tls
from .domains import DomainError, ensure_starter_domain, get_domain, home_dir, import_domain, list_domains


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    from .server import create_app

    ensure_starter_domain()
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
    serve.add_argument("--no-browser", action="store_true")
    serve.set_defaults(func=_serve)

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
    except DomainError as exc:
        print(f"masthead: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
