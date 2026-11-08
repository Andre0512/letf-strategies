# All numbers are invented; they only show the calculation and say nothing about a market, a product or the future.

Sample package for the check: simple chain, falsified reference output. The
reference output deviates on one day. Call: `python3 recompute.py input.csv`.
Code and data are under LICENSE-CODE.

## Columns

| Column | Meaning | Unit |
|---|---|---|
| date | day of the row | date |
| daily_return | daily return of the day | ratio |
| price | price of the chain | base 100 |
| price_saved | saved price | base 100 |
| direction | direction of the reconstruction | word |

## Steps

1. Read the input: reads input.csv.
2. Compute the chain: sets the real price and computes the chain.
3. Write the output: writes the reference output as CSV to standard output.

The file with the target values is the reference output. Legal: see LICENSE-CODE.
