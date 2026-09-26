Build me a small command-line expense tracker in Python. Standard library only, please: no pip installs.

I want to run it from this folder as `python3 expenses.py <command>`, with the data kept in `expenses.json` in the current directory.

Commands:
- `add AMOUNT CATEGORY [--date YYYY-MM-DD] [--note TEXT]`: the amount is a positive number with at most 2 decimals, and the date defaults to today. Print `Added #ID`; IDs start at 1 and go up.
- `list [--category CATEGORY] [--month YYYY-MM]`: one line per expense, oldest first, formatted `ID DATE CATEGORY AMOUNT NOTE`, with the amount shown to 2 decimals.
- `summary [--month YYYY-MM]`: one line per category sorted by name, formatted `CATEGORY: TOTAL`, then a final `TOTAL: TOTAL` line, all to 2 decimals.
- `delete ID`: remove that expense and print `Deleted #ID`.

Categories are case-insensitive, so store them lowercase. Bad input (an invalid amount or date, an unknown ID) should print an error to stderr and exit with code 1.

Please write tests for it too.
