"""Value types shared by catalog, engine and server."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Kind = Literal["skill", "connector", "tool"]
KINDS: tuple[Kind, ...] = ("skill", "connector", "tool")
Harness = Literal["claude-code", "cowork"]
COWORK_MARKER = "/local-agent-mode-sessions/"


@dataclass(frozen=True)
class Item:
    """One routable thing, named exactly as the harness knows it."""

    kind: Kind
    id: str
    label: str
    text: str
    connector: str | None = None
    source: str = ""


@dataclass(frozen=True)
class RouteContext:
    """What the hook (or the model) tells us about the current turn."""

    prompt: str
    cwd: str = ""
    transcript_path: str = ""
    session_id: str = ""

    @property
    def harness(self) -> Harness:
        return "cowork" if COWORK_MARKER in self.transcript_path else "claude-code"


@dataclass(frozen=True)
class Candidate:
    id: str
    label: str
    p: float
    connector: str | None = None


@dataclass
class Ranking:
    skills: list[Candidate] = field(default_factory=list)
    connectors: list[Candidate] = field(default_factory=list)
    tools: list[Candidate] = field(default_factory=list)
    latency_ms: float = 0.0
    model: str = ""
    device: str = ""

    def is_empty(self) -> bool:
        return not (self.skills or self.connectors or self.tools)
