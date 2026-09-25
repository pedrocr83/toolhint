from collections.abc import Callable
from pathlib import Path

import pytest


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def skill_md(name: str, description: str) -> str:
    return f"---\nname: {name}\ndescription: {description}\n---\n# {name}\n"


@pytest.fixture
def write_skill() -> Callable[..., Path]:
    def write(root: Path, name: str, body: str | None = None) -> Path:
        path = root / name / "SKILL.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body if body is not None else skill_md(name, f"{name} skill."), encoding="utf-8")
        return path

    return write


@pytest.fixture(autouse=True)
def _fresh_catalog_cache():
    from laya_router import catalog

    catalog.clear_cache()
    yield
