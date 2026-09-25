from fakes import FakeScorer

from laya_router import cli
from laya_router.engine import Engine


def test_catalog_prints_counts(tmp_path, monkeypatch, capsys, write_skill):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    write_skill(tmp_path / ".claude" / "skills", "mine")
    assert cli.main(["catalog"]) == 0
    assert "skill" in capsys.readouterr().out


def test_route_prints_hint(tmp_path, monkeypatch, capsys, write_skill):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    write_skill(tmp_path / ".claude" / "skills", "debugging")
    monkeypatch.setattr("laya_router.server.default_engine",
                        lambda env=None: Engine(FakeScorer({"skill": {"debugging": 0.9}})))
    assert cli.main(["route", "please debug the failing test"]) == 0
    assert capsys.readouterr().out.startswith("[laya-router] advisory")


def test_eval_build_runs_on_empty_home(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert cli.main(["eval", "build", "--out", str(tmp_path / "out")]) == 0
    assert '"labeled": 0' in capsys.readouterr().out
