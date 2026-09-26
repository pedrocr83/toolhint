import json
import threading

import pytest
from fakes import FakeScorer
from mcp import Client

from toolhint.decisions import DecisionLog
from toolhint.engine import NONE_ID, Engine
from toolhint.items import Item, Ranking, RouteContext
from toolhint.server import INSTRUCTIONS, RouterService, build_server, decision_log

ITEMS = [Item("skill", "debugging", "debug failing tests", "debug failing tests"),
         Item("skill", "slides", "make slides", "make slides")]
PROMPT = {"prompt": "please debug the failing test", "session_id": "s1"}
HINT = "[toolhint] advisory, ignore if irrelevant — skills: debugging (0.90)"


def text_of(result) -> str:
    return "".join(getattr(block, "text", "") for block in result.content)


def service(factory, log_path=None) -> RouterService:
    return RouterService(factory, discover=lambda ctx: ITEMS, decisions=DecisionLog(log_path))


@pytest.mark.anyio
async def test_route_tool_returns_hint_and_logs(tmp_path):
    svc = service(lambda: Engine(FakeScorer({"skill": {"debugging": 0.9}})), tmp_path / "d.jsonl")
    svc.load()
    async with Client(build_server(svc)) as client:
        result = await client.call_tool("route", PROMPT)
    assert text_of(result) == HINT
    record = json.loads((tmp_path / "d.jsonl").read_text().splitlines()[0])
    assert record["session"] == "s1" and record["skills"][0]["id"] == "debugging"


@pytest.mark.anyio
async def test_route_hook_format_wraps_hint_for_user_prompt_submit():
    svc = service(lambda: Engine(FakeScorer({"skill": {"debugging": 0.9}})))
    svc.load()
    async with Client(build_server(svc)) as client:
        result = await client.call_tool("route", {**PROMPT, "format": "hook"})
    assert json.loads(text_of(result)) == {
        "hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": HINT}}


@pytest.mark.anyio
async def test_route_hook_format_is_empty_without_hint():
    svc = service(lambda: Engine(FakeScorer({"skill": {NONE_ID: 0.9}})))
    svc.load()
    async with Client(build_server(svc)) as client:
        assert text_of(await client.call_tool("route", {**PROMPT, "format": "hook"})) == ""


@pytest.mark.anyio
async def test_route_is_empty_while_model_loads():
    gate = threading.Event()

    def slow_factory():
        gate.wait(5)
        return Engine(FakeScorer())

    async with Client(build_server(service(slow_factory))) as client:
        result = await client.call_tool("route", PROMPT)
    gate.set()
    assert text_of(result) == ""


@pytest.mark.anyio
async def test_failed_load_and_route_errors_stay_silent():
    def broken():
        raise RuntimeError("no checkpoint")

    svc = service(broken)
    svc.load()
    assert svc.ready.is_set()
    async with Client(build_server(svc)) as client:
        assert text_of(await client.call_tool("route", PROMPT)) == ""
    failing = RouterService(lambda: Engine(FakeScorer()), discover=lambda ctx: 1 / 0)
    failing.load()
    assert failing.route(RouteContext("please debug the failing test")) == ""


def test_load_warms_the_model_before_the_first_prompt():
    scorer = FakeScorer()
    RouterService(lambda: Engine(scorer), discover=lambda ctx: ITEMS).load()
    assert len(scorer.choose_calls) == 1


def test_an_unwritable_decision_log_keeps_the_hint(tmp_path):
    svc = RouterService(lambda: Engine(FakeScorer({"skill": {"debugging": 0.9}})), discover=lambda ctx: ITEMS,
                        decisions=DecisionLog(tmp_path))  # a directory, so every append fails
    svc.load()
    assert svc.route(RouteContext("please debug the failing test")) == HINT


def test_decision_log_rotates_and_can_be_disabled(tmp_path):
    path = tmp_path / "d.jsonl"
    log = DecisionLog(path, max_bytes=10)
    log.write(RouteContext("x" * 50), Ranking(), 0)
    log.write(RouteContext("x" * 50), Ranking(), 0)
    assert (tmp_path / "d.jsonl.1").exists() and len(path.read_text().splitlines()) == 1
    DecisionLog(None).write(RouteContext("x"), Ranking(), 0)
    assert decision_log({"TOOLHINT_LOG": "off"}).path is None
    assert decision_log({"TOOLHINT_LOG": str(path)}).path == path


def test_instructions_fit_the_2kb_cap():
    assert len(INSTRUCTIONS) < 300 and "route" in INSTRUCTIONS


def test_short_prompts_get_the_earlier_prompt_from_the_transcript(tmp_path):
    transcript = tmp_path / "s.jsonl"
    transcript.write_text(json.dumps({"type": "user", "message": {"content": "refactor the auth module"}}) + "\n")
    scorer = FakeScorer()
    svc = RouterService(lambda: Engine(scorer), discover=lambda ctx: ITEMS)
    svc.load()
    svc.route(RouteContext("and the unit tests?", transcript_path=str(transcript)))
    assert scorer.choose_calls[-1][0]["earlier request"] == "refactor the auth module"
