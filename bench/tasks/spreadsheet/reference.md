A strong answer is a workbook whose numbers come from formulas that have been computed, so they show in any viewer. `reference/comparison.xlsx` (built by `reference/build.py`) is one such workbook.

- **Inputs from the sources, labelled:** RouteLoom €214,000 a year and €38,000 one-time; Pathwise €176,000 a year and €95,000 one-time; a 3-year term (`03-vendor-quotes.md`); the estimated €312,000 annual labour saving (`01-pilot-report.md`), marked as an estimate extrapolated from the RouteLoom pilot.
- **Formulas, not typed results:**
  - three-year cost = subscription × 3 + one-time: RouteLoom €680,000 and Pathwise €623,000;
  - the difference: Pathwise €57,000 cheaper over three years;
  - net annual saving = saving − subscription: €98,000 and €136,000;
  - payback on the one-time cost = one-time ÷ net annual saving: about 4.7 months for RouteLoom and 8.4 months for Pathwise, against the CFO's 18-month limit (`05-steering-minutes.md`).
- **Formulas computed and saved:** a formula stored without its value shows blank in many viewers and reads as None to scripts. No `#VALUE!`, `#REF!` or `#DIV/0!`.
- **Readable:** labelled rows or columns, units stated, and the sources or assumptions noted in the sheet.
- **Credit context that isn't required:** Pathwise can't be live before peak season (it needs WMS v9 in Q1 2027), and its saving is unproven.

Deduct for: typed-in totals, formulas left uncomputed, formula errors, wrong inputs, a payback that ignores the subscription, or no labels.
