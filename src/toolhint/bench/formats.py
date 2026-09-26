"""Graders for file outputs, standard library only: .xlsx cells (formulas and their computed values) and HTML pages.

ElementTree never fetches external entities, and expat >= 2.4.1 caps entity expansion, which covers the
agent-written workbooks this reads."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from html.parser import HTMLParser
from itertools import pairwise
from pathlib import Path

MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
SHEET = re.compile(r"xl/worksheets/[^/]+\.xml")
FLAGS = re.IGNORECASE | re.MULTILINE


def xlsx_cells(path: Path) -> list[dict]:
    """Every cell of every sheet: its formula (None when typed in) and its stored value (None when never computed)."""
    try:
        with zipfile.ZipFile(path) as book:
            names = book.namelist()
            shared = []
            if "xl/sharedStrings.xml" in names:
                shared = ["".join(t.text or "" for t in si.iter(f"{MAIN}t"))
                          for si in ET.fromstring(book.read("xl/sharedStrings.xml")).iter(f"{MAIN}si")]
            cells = []
            for name in sorted(n for n in names if SHEET.fullmatch(n)):
                for c in ET.fromstring(book.read(name)).iter(f"{MAIN}c"):
                    cells.append(_cell(Path(name).stem, c, shared))
            return cells
    except (OSError, zipfile.BadZipFile, ET.ParseError, KeyError, IndexError, ValueError):
        return []


def _cell(sheet: str, c: ET.Element, shared: list[str]) -> dict:
    formula, stored, kind = c.find(f"{MAIN}f"), c.find(f"{MAIN}v"), c.get("t", "n")
    raw = stored.text if stored is not None else None
    if kind == "inlineStr":
        value: float | str | None = "".join(t.text or "" for t in c.iter(f"{MAIN}t"))
    elif raw is None:
        value = None
    elif kind == "s":
        value = shared[int(raw)]
    elif kind == "n":
        value = float(raw)
    else:  # str, b, e
        value = raw
    return {"sheet": sheet, "ref": c.get("r"), "value": value, "error": kind == "e",
            # a shared formula's follower cells carry an empty <f>, which is still a formula
            "formula": (formula.text or "(shared)") if formula is not None else None}


def xlsx_checklist(cells: list[dict], checks: list[dict]) -> dict:
    formulas = [c for c in cells if c["formula"] is not None]
    numbers = [c for c in cells if isinstance(c["value"], float)]
    texts = " ".join(c["value"] for c in cells if isinstance(c["value"], str) and not c["error"])
    results = {}
    for check in checks:
        if "min_formulas" in check:
            ok = len(formulas) >= check["min_formulas"]
        elif "cached_ratio" in check:
            ok = bool(formulas) and sum(c["value"] is not None for c in formulas) / len(formulas) >= check["cached_ratio"]
        elif "no_errors" in check:
            ok = bool(cells) and not any(c["error"] for c in cells)
        elif "number" in check:
            pool = [c for c in numbers if c["formula"] is not None] if check.get("formula") else numbers
            ok = any(low <= c["value"] <= high for c in pool for low, high in check["number"])
        else:
            ok = all(re.search(pattern, texts, FLAGS) for pattern in check["text"])
        results[check["id"]] = ok
    return {"passed": sum(results.values()), "total": len(results), "checks": results}


def render_cells(cells: list[dict]) -> str:
    """The workbook as text for the judge: one line per non-empty cell."""
    def shown(value: float | str | None) -> str:
        if isinstance(value, float):
            return str(int(value)) if value.is_integer() else f"{value:.6g}"
        return "(not computed)" if value is None else str(value)
    return "\n".join(f"{c['sheet']}!{c['ref']}: " + (f"={c['formula']} → {shown(c['value'])}" if c["formula"] is not None
                                                     else shown(c["value"]))
                     for c in cells if c["formula"] is not None or c["value"] not in (None, ""))


class _Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict]] = []
        self.headings: list[tuple[int, str]] = []
        self.css: list[str] = []
        self.title = ""
        self._open: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        self.tags.append((tag, values))
        self.css.append(values.get("style", ""))
        if tag in ("style", "title") or re.fullmatch(r"h[1-6]", tag):
            self._open = tag
            if tag[0] == "h":
                self.headings.append((int(tag[1]), ""))

    def handle_endtag(self, tag: str) -> None:
        if tag == self._open:
            self._open = None

    def handle_data(self, data: str) -> None:
        if self._open == "style":
            self.css.append(data)
        elif self._open == "title":
            self.title += data
        elif self._open and self.headings:
            level, text = self.headings[-1]
            self.headings[-1] = (level, text + data)


FONT_CDN = re.compile(r"^https://(fonts\.googleapis\.com|fonts\.bunny\.net|use\.typekit\.net)/")
GENERIC_FONTS = {"inter", "roboto", "arial", "helvetica", "helvetica neue", "system-ui", "-apple-system",
                 "blinkmacsystemfont", "segoe ui", "sans-serif", "serif", "monospace", "ui-sans-serif", "open sans",
                 "lato", "montserrat", "poppins", "inherit", "ui-monospace", "ui-serif", "ui-rounded"}


def html_checklist(text: str, checks: list[dict]) -> dict:
    page = _Page()
    page.feed(text)
    css = "\n".join(page.css)
    tags = [tag for tag, _ in page.tags]
    attrs = {tag: values for tag, values in reversed(page.tags)}  # first occurrence wins
    levels = [level for level, _ in page.headings]
    labels = " ".join([text for _, text in page.headings] +
                      [f"{v.get('id', '')} {v.get('class', '')} {v.get('aria-label', '')}" for _, v in page.tags])
    # font stacks in font-family declarations, and in custom properties that end in a generic family
    stacks = re.findall(r"font-family\s*:\s*([^;}]+)", css, FLAGS) + re.findall(
        r"--[\w-]+\s*:\s*([^;}]*\b(?:serif|sans-serif|monospace|cursive))\s*[;}]", css, FLAGS)
    fonts = [stack.split(",")[0].strip().strip("'\"").lower() for stack in stacks]
    moving = re.search(r"transition|animation|@keyframes", css, FLAGS)
    rules = {
        # the page's own CSS must be inline; a web-font stylesheet is an asset, not the page's CSS
        "inline_css": "style" in tags and not any(t == "link" and "stylesheet" in v.get("rel", "").lower()
                                                  and not FONT_CDN.search(v.get("href", "")) for t, v in page.tags),
        "html_lang": bool(attrs.get("html", {}).get("lang", "").strip()),
        "viewport_meta": any(t == "meta" and v.get("name", "").lower() == "viewport"
                             and "width=device-width" in v.get("content", "").replace(" ", "") for t, v in page.tags),
        "title": bool(page.title.strip()),
        "one_h1": levels.count(1) == 1,
        "heading_order": bool(levels) and levels[0] == 1 and all(b <= a + 1 for a, b in pairwise(levels)),
        "main_landmark": "main" in tags,
        "required_sections": all(re.search(p, labels, FLAGS) for p in ("feature", "pric|plan", r"faq|frequently|question")),
        "responsive_css": bool(re.search(r"@media[^{]*width|clamp\(|auto-fit|auto-fill", css, FLAGS)),
        "focus_styles": ":focus" in css,
        "reduced_motion": not moving or "prefers-reduced-motion" in css,
        "img_alt": all("alt" in v for t, v in page.tags if t == "img"),
        "faq_disclosure": ("details" in tags and "summary" in tags) or any("aria-expanded" in v for _, v in page.tags),
        "distinctive_font": any(font and font not in GENERIC_FONTS and not font.startswith("var(") for font in fonts),
    }
    results = {check["id"]: rules[check["rule"]] for check in checks}
    return {"passed": sum(results.values()), "total": len(results), "checks": results}
