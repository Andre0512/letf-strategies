"""Reference for recomputing: rebalancing two products onto a target weight."""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date, timedelta
from pathlib import Path

INPUT_COLUMNS = (
    "run",
    "rule",
    "stock_weight_percent",
    "period_months",
    "band_percentage_points",
    "date",
    "stock_price",
    "bond_price",
)

OUTPUT_COLUMNS = INPUT_COLUMNS + (
    "stock_shares",
    "bond_shares",
    "quote_before_percent",
    "quote_stock_percent",
    "deadline",
    "band_breached",
    "rebalanced",
    "value_strategy",
    "value_hold",
)


def add_months(day: date, months: int) -> date:
    """Add months; if the day is missing in the target month, its last day counts."""
    year, month = divmod(day.month - 1 + months, 12)
    year += day.year
    month += 1
    first_of_next_month = date(year + month // 12, month % 12 + 1, 1)
    last = (first_of_next_month - timedelta(days=1)).day
    return date(year, month, min(day.day, last))


def next_scheduled_date(day: date, period: int) -> date:
    """First scheduled date strictly after `day`: the 1st of each month m with (m - 1) % period == 0."""
    year, month = day.year, day.month
    while True:
        month += 1
        if month > 12:
            year, month = year + 1, 1
        if (month - 1) % period == 0:
            return date(year, month, 1)


def yes_no(value: bool) -> str:
    return "ja" if value else "nein"


def number(value: float) -> str:
    """Number to 12 decimal places, written as repr."""
    return repr(round(value, 12))


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebalancing: share counts and value curve")
    parser.add_argument("input_file", type=Path)
    args = parser.parse_args()

    # Step 1: Read the input
    with args.input_file.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    runs: dict[str, list[int]] = {}
    for i, row in enumerate(rows):
        runs.setdefault(row["run"], []).append(i)

    result: list[dict[str, str]] = [{} for _ in rows]
    for indices in runs.values():
        first = rows[indices[0]]
        rule = first["rule"]
        target = float(first["stock_weight_percent"]) / 100.0
        period = int(first["period_months"])
        band_text = first["band_percentage_points"]
        band = float(band_text) if band_text != "" else None
        stock_price_0 = float(first["stock_price"])
        bond_price_0 = float(first["bond_price"])
        stock_shares = 0.0
        bond_shares = 0.0
        deadline = date.min
        for n, i in enumerate(indices):
            row = rows[i]
            today = date.fromisoformat(row["date"])
            stock_price = float(row["stock_price"])
            bond_price = float(row["bond_price"])
            breached = False
            rebalanced = False
            if n == 0:
                # Step 2: Set the anchor
                stock_shares = target * 100.0 / stock_price
                bond_shares = (1.0 - target) * 100.0 / bond_price
                if rule == "termin":
                    deadline = next_scheduled_date(today, period)
                else:
                    deadline = add_months(today, period)
                quote_before = 100.0 * target
                value = 100.0
            else:
                # Step 3: Compute the quote before the rebalancing
                value = stock_shares * stock_price + bond_shares * bond_price
                quote_before = 100.0 * stock_shares * stock_price / value

                # Step 4: Check deadline and band
                if band is not None:
                    breached = abs(quote_before - 100.0 * target) >= band
                due = today >= deadline
                if rule == "termin_und_band":
                    rebalanced = due and breached
                else:
                    rebalanced = due

                # Step 5: Rebalance
                if rebalanced:
                    stock_shares = target * value / stock_price
                    bond_shares = (1.0 - target) * value / bond_price
                    if rule == "termin":
                        deadline = next_scheduled_date(deadline, period)
                    else:
                        deadline = add_months(today, period)

            # Step 6: Compute the value and the holding
            quote_after = 100.0 * stock_shares * stock_price / value
            hold = 100.0 * (
                target * (stock_price / stock_price_0)
                + (1.0 - target) * (bond_price / bond_price_0)
            )
            output = {column: row[column] for column in INPUT_COLUMNS}
            output["stock_shares"] = number(stock_shares)
            output["bond_shares"] = number(bond_shares)
            output["quote_before_percent"] = number(quote_before)
            output["quote_stock_percent"] = number(quote_after)
            output["deadline"] = deadline.isoformat()
            output["band_breached"] = yes_no(breached)
            output["rebalanced"] = yes_no(rebalanced)
            output["value_strategy"] = number(value)
            output["value_hold"] = number(hold)
            result[i] = output

    # Step 7: Write the output
    writer = csv.DictWriter(sys.stdout, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for output in result:
        writer.writerow(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
