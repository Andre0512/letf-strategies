# Example packages for recomputing

All numbers are invented; they only show the calculation and say nothing about
a market, a product or the future.

Each package is a directory with exactly four files:

| File | Content |
|---|---|
| `input.csv` | invented input |
| `recompute.py` | reference version of the recipe, standard library only |
| `output.csv` | reference output with all intermediate steps |
| `README.md` | recipe in numbered steps, call, columns with unit |

Call: `python3 P/recompute.py P/input.csv` writes the reference output as CSV
to standard output. To compare it line by line:

```bash
python3 P/recompute.py P/input.csv > result.csv
diff result.csv P/output.csv
```

If `diff` prints nothing, every line matches.

The package `examples/sma-signal/` recomputes trend following with moving
average and buffer day by day: line, money position, trading costs,
money-market interest and value curve (`line`, `invested`, `trading_cost`,
`money_interest_day`, `value_strategy`, `value_hold`).

The package `examples/rebalancing/` recomputes rebalancing two products to a
fixed target weight day by day: unit counts, equity share, deadline, band and
value curve (`stock_shares`, `bond_shares`, `quote_stock_percent`, `deadline`,
`band_breached`, `value_strategy`, `value_hold`), in one run by date and one
run by date and band.

The package `examples/leverage-model/` recomputes the price of a leveraged
product before its launch day by day, with the daily reset of the leverage.

The recipes describe what goes into the calculation and what comes out. They
name no data sources and contain no real market, index or product data.
Legal: see LICENSE-CODE.
