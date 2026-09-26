A strong solution to the expense-tracker task has these properties. The file `reference/expenses.py` next to this rubric is one such solution (about 90 lines).

- **Interface exactly as specified:** `python3 expenses.py add|list|summary|delete`, data in `expenses.json` in the current directory, `Added #ID` / `Deleted #ID`, list lines `ID DATE CATEGORY AMOUNT NOTE` oldest first, summary lines `category: total` sorted by name and a final `TOTAL:` line, all amounts to 2 decimals.
- **Money handled exactly:** `Decimal` (or integer cents), not floats that print `16.749999`.
- **Validation:** amounts must be positive with at most 2 decimals; dates must be real `YYYY-MM-DD` dates; unknown IDs are errors. Every error goes to stderr with exit code 1, and nothing is written on error.
- **Categories stored lowercase** and matched case-insensitively; `--month` filters on the date prefix.
- **Standard library only;** no dependencies to install.
- **Tests that exercise the real behavior:** the CLI or its core functions, including error cases, using a temporary directory so they don't touch real data. The tests pass.
- **Readable structure:** small functions for parsing, storage and commands; no dead code; clear error messages.

Deduct for: floats in money arithmetic, missing or wrong exit codes, errors printed to stdout, tests that only check happy paths, tests that fail, extra dependencies, or a spec deviation such as unsorted output.
