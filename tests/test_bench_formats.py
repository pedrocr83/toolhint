import zipfile

from toolhint.bench.formats import (
    html_checklist,
    render_cells,
    xlsx_cells,
    xlsx_checklist,
)

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def workbook(path, cells, strings=()):
    """A minimal .xlsx: one sheet of raw <c> elements plus optional shared strings."""
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml", f'<workbook xmlns="{MAIN}"/>')
        z.writestr("xl/worksheets/sheet1.xml",
                   f'<worksheet xmlns="{MAIN}"><sheetData><row r="1">{"".join(cells)}</row></sheetData></worksheet>')
        if strings:
            z.writestr("xl/sharedStrings.xml",
                       f'<sst xmlns="{MAIN}">{"".join(f"<si><t>{s}</t></si>" for s in strings)}</sst>')
    return path


def test_xlsx_cells_reads_strings_numbers_formulas_and_errors(tmp_path):
    path = workbook(tmp_path / "w.xlsx", ['<c r="A1" t="s"><v>0</v></c>', '<c r="B1"><v>214000</v></c>',
                                          '<c r="C1"><f>B1*3</f><v>642000</v></c>', '<c r="D1"><f>B1/0</f></c>',
                                          '<c r="E1" t="e"><f>1/0</f><v>#DIV/0!</v></c>'], ["RouteLoom"])
    cells = {c["ref"]: c for c in xlsx_cells(path)}
    assert cells["A1"]["value"] == "RouteLoom" and cells["B1"]["value"] == 214000.0 and cells["B1"]["formula"] is None
    assert (cells["C1"]["formula"], cells["C1"]["value"]) == ("B1*3", 642000.0)
    assert cells["D1"]["value"] is None and cells["E1"]["error"]
    assert "sheet1!C1: =B1*3 → 642000" in render_cells(list(cells.values()))


def test_xlsx_checklist_needs_computed_formulas_for_formula_checks(tmp_path):
    checks = [{"id": "formulas", "min_formulas": 2}, {"id": "cached", "cached_ratio": 1.0},
              {"id": "errors", "no_errors": True}, {"id": "total", "number": [[641999.5, 642000.5]], "formula": True},
              {"id": "labels", "text": ["routeloom"]}]
    typed = workbook(tmp_path / "typed.xlsx", ['<c r="A1"><v>642000</v></c>', '<c r="B1"><v>1</v></c>'])
    uncached = workbook(tmp_path / "uncached.xlsx", ['<c r="A1"><f>B1*3</f></c>', '<c r="B1"><f>C1</f></c>'])
    good = workbook(tmp_path / "good.xlsx", ['<c r="A1" t="s"><v>0</v></c>', '<c r="B1"><f>C1*3</f><v>642000</v></c>',
                                             '<c r="C1"><f>214000</f><v>214000</v></c>'], ["RouteLoom"])
    assert xlsx_checklist(xlsx_cells(typed), checks)["checks"] == {
        "formulas": False, "cached": False, "errors": True, "total": False, "labels": False}
    assert xlsx_checklist(xlsx_cells(uncached), checks)["checks"]["cached"] is False
    assert xlsx_checklist(xlsx_cells(good), checks)["passed"] == 5


def test_an_unreadable_workbook_has_no_cells(tmp_path):
    (tmp_path / "bad.xlsx").write_text("not a zip")
    assert xlsx_cells(tmp_path / "bad.xlsx") == [] and xlsx_cells(tmp_path / "missing.xlsx") == []


RULES = ["inline_css", "html_lang", "viewport_meta", "title", "one_h1", "heading_order", "main_landmark",
         "required_sections", "responsive_css", "focus_styles", "reduced_motion", "img_alt", "faq_disclosure",
         "distinctive_font"]
GOOD = """<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width, initial-scale=1">
<title>RouteLoom</title><style>:root{font-family:"Iowan Old Style",Georgia,serif}
a:focus-visible{outline:3px solid}.card{transition:transform .2s}
@media (max-width:600px){.grid{grid-template-columns:1fr}}
@media (prefers-reduced-motion:reduce){*{transition:none}}</style></head>
<body><header><nav><a href="#pricing">Pricing</a></nav></header><main><section><h1>Routes that learn</h1>
<img src="data:," alt=""></section><section id="features"><h2>Features</h2><h3>Waves</h3></section>
<section id="pricing"><h2>Pricing</h2></section><section id="faq"><h2>FAQ</h2>
<details><summary>Does it work offline?</summary><p>Yes.</p></details></section></main></body></html>"""


def test_html_checklist_passes_a_good_page_and_flags_each_rule():
    checks = [{"id": rule, "rule": rule} for rule in RULES]
    assert html_checklist(GOOD, checks)["passed"] == len(RULES)
    bad = ("<html><head><link rel=stylesheet href=x.css><style>body{font-family:Inter,sans-serif;"
           "transition:all 1s}</style></head><body><h1>A</h1><h1>B</h1><h4>C</h4><img src=x.png></body></html>")
    failed = {rule for rule, ok in html_checklist(bad, checks)["checks"].items() if not ok}
    assert failed == set(RULES)


def test_a_web_font_stylesheet_does_not_count_against_inline_css():
    fonts = GOOD.replace("<title>", '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces"><title>')
    assert html_checklist(fonts, [{"id": "inline_css", "rule": "inline_css"}])["passed"] == 1


def test_fonts_declared_through_custom_properties_count_and_system_stacks_do_not():
    rule = [{"id": "font", "rule": "distinctive_font"}]
    tokens = "<style>:root{--display:'Fraunces',Georgia,serif}h1{font-family:var(--display)}</style>"
    system = "<style>code{font-family:ui-monospace,monospace}body{font-family:system-ui,sans-serif}</style>"
    assert html_checklist(tokens, rule)["passed"] == 1 and html_checklist(system, rule)["passed"] == 0
