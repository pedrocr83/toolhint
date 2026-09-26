"""MCP stdio server exposing one `route` tool backed by a warm Laya engine."""
from __future__ import annotations

import json
import logging
import os
import threading
from collections import OrderedDict
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from . import __version__, catalog
from .dataset import previous_prompt
from .decisions import DEFAULT_LOG, DecisionLog
from .engine import (
    PLURAL,
    SHORT_PROMPT_CHARS,
    Engine,
    EngineConfig,
    format_hint,
    prompt_view,
)
from .items import Item, Ranking, RouteContext

log = logging.getLogger("toolhint.server")
INSTRUCTIONS = ("If a user request arrives without a [toolhint] line in context, you may call `route` "
                "with the request text to get ranked skill/connector/tool candidates. Treat them as advisory.")
ROUTE_DESCRIPTION = ("Rank the skills, connectors and tools most relevant to a user request. "
                     "Returns one advisory line, or an empty string when nothing stands out.")
WARMUP_PROMPT = "warm up the router model"
MAX_SESSIONS = 64


class RouterService:
    """Holds the engine, loads it off the request path, and never raises from route()."""

    def __init__(self, engine_factory: Callable[[], Engine],
                 discover: Callable[[RouteContext], list[Item]] = catalog.discover,
                 decisions: DecisionLog | None = None) -> None:
        self._factory = engine_factory
        self._discover = discover
        self._decisions = decisions or DecisionLog(None)
        self._engine: Engine | None = None
        self._hinted: OrderedDict[str, set[str]] = OrderedDict()
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

    def route(self, ctx: RouteContext, dedupe: bool = False) -> str:
        engine = self._engine
        if engine is None:
            return ""
        try:
            items = self._discover(ctx)
            short = len(prompt_view(ctx.prompt)) < SHORT_PROMPT_CHARS  # the length the engine checks
            ranking = engine.rank(ctx.prompt, items, previous_prompt(ctx.transcript_path, ctx.prompt) if short else "")
            hint = format_hint(self._unseen(ctx.session_id, ranking) if dedupe else ranking)
        except Exception:
            log.exception("route failed")
            return ""
        try:
            self._decisions.write(ctx, ranking, len(items))
        except Exception:
            log.exception("decision log write failed; the hint still goes out")
        return hint

    def forget(self, session_id: str) -> None:
        """Compaction dropped the earlier hints from context, so let them show again."""
        self._hinted.pop(session_id, None)

    def _unseen(self, session_id: str, ranking: Ranking) -> Ranking:
        """The ranking minus items this session was already hinted; remembers the rest."""
        if not session_id:
            return ranking
        seen = self._hinted.setdefault(session_id, set())
        self._hinted.move_to_end(session_id)
        if len(self._hinted) > MAX_SESSIONS:
            self._hinted.popitem(last=False)
        fresh = replace(ranking, **{field: [c for c in getattr(ranking, field) if c.id not in seen]
                                    for field in PLURAL.values()})
        seen.update(c.id for c in fresh.skills + fresh.connectors + fresh.tools)
        return fresh


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

    server = MCPServer("toolhint", instructions=INSTRUCTIONS, version=__version__, lifespan=lifespan)

    @server.tool(name="route", description=ROUTE_DESCRIPTION)
    def route(prompt: str, cwd: str = "", transcript_path: str = "", session_id: str = "",
              format: str = "text", event: str = "", dedupe: bool = False) -> str:
        # the plugin hook passes "format": "hook" and "dedupe": true; an older hooks.json (no compaction
        # reset) sends no dedupe, so its sessions keep getting repeats rather than losing hints for good
        if event == "compact":  # SessionStart(compact): earlier hints are gone from the context
            service.forget(session_id)
            return ""
        hint = service.route(RouteContext(prompt, cwd, transcript_path, session_id), dedupe)
        return hook_output(hint) if format == "hook" else hint

    return server


def default_engine(env: Mapping[str, str] = os.environ) -> Engine:
    from .scorer import LayaScorer

    model = env.get("TOOLHINT_MODEL", "typed-decisions")
    scorer = LayaScorer(model=model, device=env.get("TOOLHINT_DEVICE") or None)
    return Engine(scorer, EngineConfig.from_env(env))


def decision_log(env: Mapping[str, str] = os.environ) -> DecisionLog:
    raw = env.get("TOOLHINT_LOG", "")
    if raw.lower() in ("0", "off", "false"):
        return DecisionLog(None)
    return DecisionLog(Path(raw) if raw else DEFAULT_LOG)


def serve() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    build_server(RouterService(default_engine, decisions=decision_log())).run()
