"""MCP stdio server exposing one `route` tool backed by a warm Laya engine."""
from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from . import __version__, catalog
from .decisions import DEFAULT_LOG, DecisionLog
from .engine import Engine, EngineConfig, format_hint
from .items import Item, RouteContext

log = logging.getLogger("laya_router.server")
INSTRUCTIONS = ("If a user request arrives without a [laya-router] line in context, you may call `route` "
                "with the request text to get ranked skill/connector/tool candidates. Treat them as advisory.")
ROUTE_DESCRIPTION = ("Rank the skills, connectors and tools most relevant to a user request. "
                     "Returns one advisory line, or an empty string when nothing stands out.")
WARMUP_PROMPT = "warm up the router model"


class RouterService:
    """Holds the engine, loads it off the request path, and never raises from route()."""

    def __init__(self, engine_factory: Callable[[], Engine],
                 discover: Callable[[RouteContext], list[Item]] = catalog.discover,
                 decisions: DecisionLog | None = None) -> None:
        self._factory = engine_factory
        self._discover = discover
        self._decisions = decisions or DecisionLog(None)
        self._engine: Engine | None = None
        self._started = False
        self.ready = threading.Event()

    def load(self) -> None:
        try:
            self._engine = self._factory()
            # The first forward pass pays CUDA warm-up (~1.4 s); spend it here, not inside the 5 s hook budget.
            self._engine.scores(WARMUP_PROMPT, self._discover(RouteContext(WARMUP_PROMPT)))
        except Exception:
            log.exception("engine load or warm-up failed; routing stays silent without an engine")
        finally:
            self.ready.set()

    def start(self) -> None:
        if self._started or self.ready.is_set():
            return
        self._started = True
        threading.Thread(target=self.load, name="laya-load", daemon=True).start()

    def route(self, ctx: RouteContext) -> str:
        engine = self._engine
        if engine is None:
            return ""
        try:
            items = self._discover(ctx)
            ranking = engine.rank(ctx.prompt, items)
            hint = format_hint(ranking)
        except Exception:
            log.exception("route failed")
            return ""
        try:
            self._decisions.write(ctx, ranking, len(items))
        except Exception:
            log.exception("decision log write failed; the hint still goes out")
        return hint


def hook_output(hint: str) -> str:
    """UserPromptSubmit hook JSON; an mcp_tool hook's plain-text result never reaches the model."""
    if not hint:
        return ""
    return json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": hint}},
                      ensure_ascii=False)


def build_server(service: RouterService) -> MCPServer:
    @asynccontextmanager
    async def lifespan(_server: MCPServer) -> AsyncIterator[dict]:
        service.start()  # stdio_server already points fd 1 at stderr, so stray model prints miss the wire
        yield {}

    server = MCPServer("laya-router", instructions=INSTRUCTIONS, version=__version__, lifespan=lifespan)

    @server.tool(name="route", description=ROUTE_DESCRIPTION)
    def route(prompt: str, cwd: str = "", transcript_path: str = "", session_id: str = "",
              format: str = "text") -> str:  # the plugin hook passes a literal "format": "hook"
        hint = service.route(RouteContext(prompt, cwd, transcript_path, session_id))
        return hook_output(hint) if format == "hook" else hint

    return server


def default_engine(env: Mapping[str, str] = os.environ) -> Engine:
    from .scorer import LayaScorer

    model = env.get("LAYA_ROUTER_MODEL", "typed-decisions")
    scorer = LayaScorer(model=model, device=env.get("LAYA_ROUTER_DEVICE") or None)
    return Engine(scorer, EngineConfig.from_env(env))


def decision_log(env: Mapping[str, str] = os.environ) -> DecisionLog:
    raw = env.get("LAYA_ROUTER_LOG", "")
    if raw.lower() in ("0", "off", "false"):
        return DecisionLog(None)
    return DecisionLog(Path(raw) if raw else DEFAULT_LOG)


def serve() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    build_server(RouterService(default_engine, decisions=decision_log())).run()
