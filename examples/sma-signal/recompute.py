"""Reference for recomputing: trend following with moving average and buffer."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

# Rate in percent per year as long as no money-market rate is known.
DEFAULT_RATE_PERCENT = 2.5

# Trading days per year for the daily money-market rate.
TRADING_DAYS_YEAR = 252

OUTPUT_COLUMNS = (
    "date",
    "index_rounded",
    "sma",
    "line",
    "line_rounded",
    "above_line",
    "line_state",
    "invested",
    "signal",
    "money_interest_day",
    "trading_cost",
    "trade_count",
    "value_strategy",
    "value_hold",
)


def yes_no(value: bool) -> str:
    return "ja" if value else "nein"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Trend following: signal and value curve"
    )
    parser.add_argument("input", type=Path)
    args = parser.parse_args()

    # Step 1: Read the input
    with args.input.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    window = int(rows[0]["window_trading_days"])
    buffer_share = float(rows[0]["buffer_percent"]) / 100.0
    cost_share = float(rows[0]["trading_cost_percent"]) / 100.0
    index = [float(row["index"]) for row in rows]
    price = [
        float(row["product_price"]) if row["product_price"] != "" else None
        for row in rows
    ]
    first = next(i for i, value in enumerate(price) if value is not None)

    # Step 2: Compute the average
    sma: list[float | None] = []
    for i in range(len(rows)):
        if i + 1 < window:
            sma.append(None)
        else:
            sma.append(sum(index[i + 1 - window : i + 1]) / window)

    # Step 3: Track the line and the line state
    line: list[float | None] = []
    above: list[bool | None] = []
    state: list[str] = []
    previous = "aufwaermen"
    for i in range(len(rows)):
        average = sma[i]
        if average is None:
            line.append(None)
            above.append(None)
            state.append("aufwaermen")
            continue
        if previous == "drin":
            edge = average * (1.0 - buffer_share)
        elif previous == "draussen":
            edge = average * (1.0 + buffer_share)
        else:
            edge = average
        line.append(edge)
        above.append(index[i] >= edge)
        previous = "drin" if index[i] >= edge else "draussen"
        state.append(previous)

    # Step 4: Decide the cash position
    invested: list[bool] = []
    signal: list[str] = []
    in_market = False
    decided = False
    for i in range(len(rows)):
        today = ""
        comparison = above[i]
        if price[i] is not None and comparison is not None:
            if not decided:
                decided = True
                in_market = comparison
                today = "start"
            elif comparison and not in_market:
                in_market = True
                today = "einstieg"
            elif not comparison and in_market:
                in_market = False
                today = "ausstieg"
        invested.append(in_market)
        signal.append(today)

    # Step 5: Compute the value
    interest_day: list[float] = []
    cost_day: list[float] = []
    trades: list[int] = []
    value: list[float | None] = []
    hold: list[float | None] = []
    counter = 0
    level = 100.0
    start_price = float(rows[first]["product_price"])
    last_price = start_price
    previous_day_in_market = False
    for i in range(len(rows)):
        interest = 0.0
        deduction = 0.0
        current = price[i]
        if current is None:
            interest_day.append(interest)
            cost_day.append(deduction)
            trades.append(counter)
            value.append(None)
            hold.append(None)
            continue
        if i > first:
            if previous_day_in_market:
                level = level * current / last_price
            else:
                rate_text = rows[i]["money_rate_percent_year"]
                rate = (
                    DEFAULT_RATE_PERCENT if rate_text == "" else float(rate_text)
                )
                rate = max(rate, 0.0)
                interest = (1.0 + rate / 100.0) ** (1.0 / TRADING_DAYS_YEAR) - 1.0
                level = level * (1.0 + interest)
        if signal[i] in ("einstieg", "ausstieg"):
            counter += 1
            deduction = level * cost_share
            level = level * (1.0 - cost_share)
        interest_day.append(interest)
        cost_day.append(deduction)
        trades.append(counter)
        value.append(level)
        hold.append(100.0 * current / start_price)
        last_price = current
        previous_day_in_market = invested[i]

    # Step 6: Write the output
    writer = csv.DictWriter(
        sys.stdout, fieldnames=OUTPUT_COLUMNS, lineterminator="\n"
    )
    writer.writeheader()
    for i, row in enumerate(rows):
        output = {column: "" for column in OUTPUT_COLUMNS}
        output["date"] = row["date"]
        output["index_rounded"] = repr(round(index[i], 2))
        if i >= first:
            edge = line[i]
            average = sma[i]
            comparison = above[i]
            if average is not None and edge is not None:
                output["sma"] = repr(average)
                output["line"] = repr(edge)
                output["line_rounded"] = repr(round(edge, 2))
            if comparison is not None:
                output["above_line"] = yes_no(comparison)
            output["line_state"] = state[i]
            output["invested"] = yes_no(invested[i])
            output["signal"] = signal[i]
            output["money_interest_day"] = repr(interest_day[i])
            output["trading_cost"] = repr(cost_day[i])
            output["trade_count"] = str(trades[i])
            level_i = value[i]
            hold_i = hold[i]
            if level_i is not None and hold_i is not None:
                output["value_strategy"] = repr(level_i)
                output["value_hold"] = repr(hold_i)
        writer.writerow(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
