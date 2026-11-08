"""Reference for recomputing: the price of a leveraged product before its launch."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

OUTPUT_COLUMNS = (
    "date",
    "factor_gross",
    "factor_ter",
    "factor_financing",
    "factor_hedge",
    "factor_lending",
    "factor_dividend",
    "factor_withholding",
    "factor_base",
    "share_year_ter",
    "share_year_financing",
    "daily_return",
    "price",
    "price_saved",
    "direction",
)

FACTOR_NAMES = (
    "factor_gross",
    "factor_ter",
    "factor_financing",
    "factor_hedge",
    "factor_lending",
    "factor_dividend",
    "factor_withholding",
    "factor_base",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Leverage model: price before the launch")
    parser.add_argument("input", type=Path)
    args = parser.parse_args()

    # Step 1: Read the input
    with args.input.open(newline="", encoding="utf-8") as handle:
        days = list(csv.DictReader(handle))

    def yes(text: str) -> bool:
        return text.strip().lower() in {"wahr", "ja", "true", "1", "yes", "y"}

    # Step 2: Compute the ladder factors
    computed: list[dict[str, object]] = []
    for row in days:
        leverage = float(row["leverage"])
        ter = float(row["ter_percent_year"]) / 100.0
        markup = float(row["markup_bps_year"]) / 10000.0
        hedge = float(row["hedge_bps_year"]) / 10000.0
        lending = float(row["lending_bps_year"]) / 10000.0
        dividend = float(row["dividend_percent_year"]) / 100.0
        withholding = float(row["withholding_bps_year"]) / 10000.0
        ter_base = float(row["ter_base_percent_year"]) / 100.0
        in_ter = yes(row["financing_in_ter"])
        rate = float(row["rate_percent"]) / 100.0
        calendar_days = int(row["calendar_days"])
        index_return = float(row["index_return"])
        share_year_ter = calendar_days / 365.0
        share_year_financing = calendar_days / 360.0
        factor_gross = 1.0 + leverage * index_return
        factor_ter = 1.0 - ter * share_year_ter
        if in_ter or leverage <= 1.0:
            factor_financing = 1.0
        else:
            factor_financing = (
                1.0 - (leverage - 1.0) * (rate + markup) * calendar_days / 360.0
            )
        factor_hedge = 1.0 - hedge * share_year_ter
        factor_lending = 1.0 + lending * share_year_ter
        factor_dividend = 1.0 + dividend * leverage * share_year_ter
        factor_withholding = 1.0 + withholding * leverage * share_year_ter
        factor_base = 1.0 - ter_base * leverage * share_year_ter
        computed.append(
            {
                "date": row["date"],
                "factor_gross": factor_gross,
                "factor_ter": factor_ter,
                "factor_financing": factor_financing,
                "factor_hedge": factor_hedge,
                "factor_lending": factor_lending,
                "factor_dividend": factor_dividend,
                "factor_withholding": factor_withholding,
                "factor_base": factor_base,
                "share_year_ter": share_year_ter,
                "share_year_financing": share_year_financing,
                "real_price": row["real_price"],
            }
        )

    # Step 3: Form the daily return
    for entry in computed:
        product = 1.0
        for name in FACTOR_NAMES:
            product *= float(entry[name])
        entry["daily_return"] = product - 1.0

    # Step 4: Rebuild the chain
    anchor = next(
        i for i, entry in enumerate(computed) if entry["real_price"] != ""
    )
    for i, entry in enumerate(computed):
        if entry["real_price"] != "":
            entry["price"] = float(entry["real_price"])
            entry["direction"] = "echt"
        elif i > anchor:
            entry["price"] = float(computed[i - 1]["price"]) * (
                1.0 + float(entry["daily_return"])
            )
            entry["direction"] = "vorwaerts"
        else:
            entry["direction"] = "rueckwaerts"
    for i in range(anchor - 1, -1, -1):
        computed[i]["price"] = float(computed[i + 1]["price"]) / (
            1.0 + float(computed[i + 1]["daily_return"])
        )
    for entry in computed:
        entry["price_saved"] = round(float(entry["price"]), 6)

    # Step 5: Write the output
    writer = csv.DictWriter(sys.stdout, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for entry in computed:
        writer.writerow(
            {
                "date": entry["date"],
                "factor_gross": repr(entry["factor_gross"]),
                "factor_ter": repr(entry["factor_ter"]),
                "factor_financing": repr(entry["factor_financing"]),
                "factor_hedge": repr(entry["factor_hedge"]),
                "factor_lending": repr(entry["factor_lending"]),
                "factor_dividend": repr(entry["factor_dividend"]),
                "factor_withholding": repr(entry["factor_withholding"]),
                "factor_base": repr(entry["factor_base"]),
                "share_year_ter": repr(entry["share_year_ter"]),
                "share_year_financing": repr(entry["share_year_financing"]),
                "daily_return": repr(entry["daily_return"]),
                "price": repr(entry["price"]),
                "price_saved": repr(entry["price_saved"]),
                "direction": entry["direction"],
            }
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
