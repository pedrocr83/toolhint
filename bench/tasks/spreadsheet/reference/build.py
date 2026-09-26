"""Rebuild the reference comparison.xlsx without openpyxl: write a flat ODS with formulas, let LibreOffice
convert it (which also computes and stores every formula's value). Run: python3 build.py"""
import subprocess
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
ROWS = [
    ["Item", "RouteLoom", "Pathwise", "Source"],
    ["Annual subscription (EUR)", 214000, 176000, "03-vendor-quotes.md"],
    ["One-time integration (EUR)", 38000, 95000, "03-vendor-quotes.md"],
    ["Contract years", 3, 3, "03-vendor-quotes.md"],
    ["Three-year cost (EUR)", "=[.B2]*[.B4]+[.B3]", "=[.C2]*[.C4]+[.C3]", "subscription x years + one-time"],
    ["Pathwise minus RouteLoom over three years (EUR)", "", "=[.C5]-[.B5]", "negative: Pathwise is cheaper"],
    ["Estimated annual labour saving (EUR)", 312000, 312000, "01-pilot-report.md, extrapolated from the RouteLoom pilot"],
    ["Net annual saving (EUR)", "=[.B7]-[.B2]", "=[.C7]-[.C2]", "saving - subscription"],
    ["Payback on one-time cost (months)", "=[.B3]/[.B8]*12", "=[.C3]/[.C8]*12", "CFO limit: 18 months (05-steering-minutes.md)"],
]


def cell(value) -> str:
    if isinstance(value, (int, float)):
        return f'<table:table-cell office:value-type="float" office:value="{value}"/>'
    if isinstance(value, str) and value.startswith("="):
        return f'<table:table-cell table:formula="of:{escape(value)}" office:value-type="float"/>'
    return f'<table:table-cell office:value-type="string"><text:p>{escape(value)}</text:p></table:table-cell>'


def main() -> None:
    rows = "".join(f"<table:table-row>{''.join(cell(v) for v in row)}</table:table-row>" for row in ROWS)
    fods = ('<?xml version="1.0" encoding="UTF-8"?>'
            '<office:document xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
            'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
            'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
            'xmlns:of="urn:oasis:names:tc:opendocument:xmlns:of:1.2" office:version="1.2" '
            'office:mimetype="application/vnd.oasis.opendocument.spreadsheet"><office:body><office:spreadsheet>'
            f'<table:table table:name="Comparison">{rows}</table:table></office:spreadsheet></office:body>'
            '</office:document>')
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "comparison.fods"
        source.write_text(fods, encoding="utf-8")
        subprocess.run(["soffice", f"-env:UserInstallation=file://{tmp}/profile", "--headless", "--convert-to", "xlsx",
                        "--outdir", str(HERE), str(source)], check=True, capture_output=True)


if __name__ == "__main__":
    main()
