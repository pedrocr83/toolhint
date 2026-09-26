"""Reference solution for the coding-app task; it exists to prove the hidden tests are passable."""
import argparse
import datetime
import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

DATA = Path("expenses.json")


class InputError(Exception):
    pass


def load() -> list[dict]:
    return json.loads(DATA.read_text()) if DATA.exists() else []


def save(expenses: list[dict]) -> None:
    DATA.write_text(json.dumps(expenses, indent=2))


def amount(text: str) -> Decimal:
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise InputError(f"invalid amount: {text}") from None
    if not value.is_finite() or value <= 0 or value.as_tuple().exponent < -2:
        raise InputError(f"amount must be positive with at most 2 decimals: {text}")
    return value


def date(text: str) -> str:
    try:
        return datetime.date.fromisoformat(text).isoformat()
    except ValueError:
        raise InputError(f"invalid date: {text}") from None


def selected(expenses: list[dict], category: str | None, month: str | None) -> list[dict]:
    rows = [e for e in expenses if (not category or e["category"] == category.lower())
            and (not month or e["date"].startswith(month + "-"))]
    return sorted(rows, key=lambda e: (e["date"], e["id"]))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="expenses.py")
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("add")
    add.add_argument("amount")
    add.add_argument("category")
    add.add_argument("--date", default=datetime.datetime.now().astimezone().date().isoformat())
    add.add_argument("--note", default="")
    for name in ("list", "summary"):
        sub = commands.add_parser(name)
        sub.add_argument("--month")
        if name == "list":
            sub.add_argument("--category")
    delete = commands.add_parser("delete")
    delete.add_argument("id")
    args = parser.parse_args(argv)
    expenses = load()
    try:
        if args.command == "add":
            new_id = max((e["id"] for e in expenses), default=0) + 1
            expenses.append({"id": new_id, "date": date(args.date), "category": args.category.lower(),
                             "amount": str(amount(args.amount)), "note": args.note})
            save(expenses)
            print(f"Added #{new_id}")
        elif args.command == "list":
            for e in selected(expenses, args.category, args.month):
                print(f"{e['id']} {e['date']} {e['category']} {Decimal(e['amount']):.2f} {e['note']}".rstrip())
        elif args.command == "summary":
            totals: dict[str, Decimal] = {}
            for e in selected(expenses, None, args.month):
                totals[e["category"]] = totals.get(e["category"], Decimal(0)) + Decimal(e["amount"])
            for category in sorted(totals):
                print(f"{category}: {totals[category]:.2f}")
            print(f"TOTAL: {sum(totals.values(), Decimal(0)):.2f}")
        else:
            if not args.id.isdigit() or not any(e["id"] == int(args.id) for e in expenses):
                raise InputError(f"no expense with id {args.id}")
            save([e for e in expenses if e["id"] != int(args.id)])
            print(f"Deleted #{args.id}")
    except InputError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
