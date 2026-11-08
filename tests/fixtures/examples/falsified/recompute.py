"""Sample package for the check: simple chain, falsified reference output."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Sample package")
    parser.add_argument("input", type=Path)
    args = parser.parse_args()

    # Step 1: Read the input
    with args.input.open(newline="", encoding="utf-8") as handle:
        days = list(csv.DictReader(handle))

    # Step 2: Compute the chain
    computed: list[dict[str, str]] = []
    price = 0.0
    for row in days:
        daily_return = float(row["index_return"])
        if row["real_price"]:
            price = float(row["real_price"])
            direction = "echt"
        else:
            price = price * (1.0 + daily_return)
            direction = "vorwaerts"
        computed.append(
            {
                "date": row["date"],
                "daily_return": repr(daily_return),
                "price": repr(price),
                "price_saved": repr(round(price, 6)),
                "direction": direction,
            }
        )

    # Step 3: Write the output
    writer = csv.DictWriter(
        sys.stdout,
        fieldnames=["date", "daily_return", "price", "price_saved", "direction"],
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(computed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
