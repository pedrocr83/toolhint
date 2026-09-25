"""laya-router command line: serve | route | catalog | warmup | eval."""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import anyio

from . import catalog, server
from .engine import format_hint
from .items import RouteContext


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="laya-router", description="Local Laya routing hints for agent harnesses")
    sub = parser.add_subparsers(required=True)
    sub.add_parser("serve", help="run the MCP stdio server").set_defaults(func=cmd_serve)
    route = sub.add_parser("route", help="rank one prompt and print the hint")
    route.add_argument("prompt")
    route.add_argument("--transcript-path", default="")
    route.set_defaults(func=cmd_route)
    cat = sub.add_parser("catalog", help="count discovered items; --refresh snapshots local MCP tools first")
    cat.add_argument("--refresh", action="store_true")
    cat.add_argument("--transcript-path", default="")
    cat.set_defaults(func=cmd_catalog)
    sub.add_parser("warmup", help="download the model, refresh tools, count catalogs").set_defaults(func=cmd_warmup)
    ev = sub.add_parser("eval", help="build the eval set or run the Phase 0 comparison")
    ev.add_argument("action", choices=["build", "run"])
    ev.add_argument("rest", nargs=argparse.REMAINDER)
    ev.set_defaults(func=cmd_eval)
    return parser


def cmd_serve(_args: argparse.Namespace) -> int:
    server.serve()
    return 0


def cmd_route(args: argparse.Namespace) -> int:
    ctx = RouteContext(args.prompt, cwd=os.getcwd(), transcript_path=args.transcript_path)
    ranking = server.default_engine().rank(ctx.prompt, catalog.discover(ctx))
    print(format_hint(ranking) or "(no hint)")
    print(json.dumps(asdict(ranking), indent=1))
    return 0


def cmd_catalog(args: argparse.Namespace) -> int:
    home, cwd = Path.home(), Path.cwd()
    if args.refresh:
        from . import toolcache

        snapshot = anyio.run(toolcache.refresh, toolcache.configured_servers(home, cwd), home / catalog.TOOL_CACHE)
        print(f"refreshed {len(snapshot['servers'])} MCP servers")
    items = catalog.discover(RouteContext("", cwd=str(cwd), transcript_path=args.transcript_path), home=home)
    for (kind, source), count in sorted(Counter((i.kind, i.source) for i in items).items()):
        print(f"{kind:9} {count:4}  {source}")
    return 0


def cmd_warmup(_args: argparse.Namespace) -> int:
    cmd_catalog(argparse.Namespace(refresh=True, transcript_path=""))
    catalog.clear_cache()
    engine = server.default_engine()
    for harness, items in catalog.harness_catalogs().items():
        print(f"{harness}: {len(items)} items ready for {engine.scorer.model}")
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    if args.action == "build":
        from .dataset import main as build_main

        return build_main(args.rest)
    from .evaluate import main as run_main

    return run_main(args.rest)
