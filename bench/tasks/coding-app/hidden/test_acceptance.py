"""Hidden acceptance tests for the coding-app task. The harness runs them against a finished workspace
(BENCH_WORKSPACE); the agent never sees this file."""
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

WORKSPACE = Path(os.environ["BENCH_WORKSPACE"])
SUMMARY_LINE = re.compile(r"^\s*([^:]+?)\s*:\s*(-?\d+(?:\.\d+)?)\s*$")


@pytest.fixture
def app(tmp_path):
    root = tmp_path / "app"
    shutil.copytree(WORKSPACE, root, ignore=shutil.ignore_patterns(".git", "expenses.json", "__pycache__"))

    def run(*args):
        return subprocess.run([sys.executable, "expenses.py", *args], cwd=root, capture_output=True, text=True,
                              timeout=30, check=False)

    run.root = root
    return run


def listed(app, *args):
    result = app("list", *args)
    assert result.returncode == 0, result.stderr
    rows = []
    for line in result.stdout.splitlines():
        tokens = line.split()
        if tokens:
            rows.append((tokens[0].lstrip("#"), tokens[1], tokens[2], tokens[3], " ".join(tokens[4:])))
    return rows


def summary(app, *args):
    result = app("summary", *args)
    assert result.returncode == 0, result.stderr
    return [(m.group(1).lower(), m.group(2)) for m in map(SUMMARY_LINE.match, result.stdout.splitlines()) if m]


def seed(app):
    assert app("add", "12.50", "Food", "--date", "2026-09-05", "--note", "team lunch").returncode == 0
    assert app("add", "3", "transport", "--date", "2026-08-30").returncode == 0
    assert app("add", "4.25", "FOOD", "--date", "2026-09-01").returncode == 0


def test_add_prints_increasing_ids(app):
    assert app("add", "12.50", "food", "--date", "2026-09-01").stdout.strip() == "Added #1"
    assert app("add", "3", "transport", "--date", "2026-09-02").stdout.strip() == "Added #2"


def test_list_is_oldest_first_with_lowercase_categories_and_two_decimals(app):
    seed(app)
    assert listed(app) == [("2", "2026-08-30", "transport", "3.00", ""),
                           ("3", "2026-09-01", "food", "4.25", ""),
                           ("1", "2026-09-05", "food", "12.50", "team lunch")]


def test_list_filters_by_category_ignoring_case(app):
    seed(app)
    assert [row[0] for row in listed(app, "--category", "Food")] == ["3", "1"]


def test_list_filters_by_month(app):
    seed(app)
    assert [row[0] for row in listed(app, "--month", "2026-08")] == ["2"]


def test_summary_totals_each_category_then_the_total(app):
    seed(app)
    assert summary(app) == [("food", "16.75"), ("transport", "3.00"), ("total", "19.75")]


def test_summary_filters_by_month(app):
    seed(app)
    assert summary(app, "--month", "2026-09") == [("food", "16.75"), ("total", "16.75")]


def test_delete_removes_the_expense(app):
    seed(app)
    assert app("delete", "1").stdout.strip() == "Deleted #1"
    assert [row[0] for row in listed(app)] == ["2", "3"]


@pytest.mark.parametrize("amount", ["abc", "-5", "0", "1.234"])
def test_invalid_amounts_are_rejected(app, amount):
    result = app("add", amount, "food", "--date", "2026-09-01")
    assert result.returncode == 1 and result.stderr.strip()
    assert listed(app) == []


def test_invalid_dates_are_rejected(app):
    result = app("add", "5", "food", "--date", "2026-13-40")
    assert result.returncode == 1 and result.stderr.strip()


def test_deleting_an_unknown_id_is_an_error(app):
    seed(app)
    result = app("delete", "99")
    assert result.returncode == 1 and result.stderr.strip()


def test_data_is_kept_in_expenses_json(app):
    seed(app)
    json.loads((app.root / "expenses.json").read_text())
    assert len(listed(app)) == 3


def test_date_defaults_to_today(app):
    app("add", "7", "books")
    assert listed(app)[0][1] == datetime.datetime.now().astimezone().date().isoformat()
