# All numbers are invented; they only show the calculation and say nothing about a market, a product or the future.

This package shows the rebalancing of two products, a stock side and a bond
side, onto a fixed target weight, computed day by day: share counts, stock
quote, deadline, rebalancing and value curve. Call: `python3 recompute.py
input.csv`. The output goes as CSV to standard output; the file with the target
values is the reference output (`output.csv`). Code and data are under
LICENSE-CODE.

The package contains two runs with their own calendar: run 1 with the rule
`termin`, run 2 with the rule `termin_und_band`. Both are explained separately
and are not compared with each other.

## Columns

Input and output lie in the long format: every row carries its run and the
values of the run, which are equal in every row within a run.

### Input (input.csv)

| Column | Meaning | Unit | Time basis |
|---|---|---|---|
| run | number of the run | number | per run |
| rule | `termin` or `termin_und_band` | word | per run |
| stock_weight_percent | target weight of the stock side; the bond side carries the rest | percent | per run |
| period_months | distance of the deadlines | months | per run |
| band_percentage_points | width of the band around the target weight; empty in a run without band | percentage points | per run |
| date | day of the row; only days on which both products have a price | date | trading days |
| stock_price | closing price of the stock side | price | trading days |
| bond_price | closing price of the bond side | price | trading days |

### Output (output.csv)

The output repeats the columns of the input and appends these:

| Column | Meaning | Unit | Time basis |
|---|---|---|---|
| stock_shares | share count of the stock side after the trading of the day | shares per 100 starting value | trading days |
| bond_shares | share count of the bond side after the trading of the day | shares per 100 starting value | trading days |
| quote_before_percent | stock quote from the share counts of the previous day to the prices of the day; basis of the band check; on the first day the target weight | percent | trading days |
| quote_stock_percent | stock quote after the rebalancing, otherwise equal to `quote_before_percent` | percent | trading days |
| deadline | deadline that applies after the trading of the day | date | calendar |
| band_breached | the distance of `quote_before_percent` to the target weight reaches the band; without band always `nein` | `ja`/`nein` | trading days |
| rebalanced | rebalanced onto the target weight on this day | `ja`/`nein` | trading days |
| value_strategy | value of the strategy, share counts times prices | base 100 on the first day of the run | trading days |
| value_hold | value when one buys with the starting weights and never rebalances | base 100 on the first day of the run | trading days |

## Calculation

The computation runs only on days on which both products have a price. The
first of these days is the anchor: there the share counts
`g * 100 / stock_price` and `(1 - g) * 100 / bond_price` are bought with the
value 100, `g` is the target weight as a share. On the anchor day only buying
happens: if the anchor day falls on a scheduled date, no rebalancing happens on
it.

Between two rebalancings the share counts stay fixed; the value is on every day
share count times price, counted together on both sides. The stock quote drifts
in the direction of the side that has risen more strongly.

The deadline counts from the first common day, not from the beginning of a
shown period. If the deadline falls on a day without a price, the rebalancing
happens on the next trading day. The rebalancing happens at the close of the
day to the closing prices of this day, without offset. The value before and
after the rebalancing is equal; afterwards the stock side again holds precisely
the target weight.

Rule `termin`: the dates stand fixed in the calendar. The scheduled date is the
1st of every month whose distance to January is a multiple of the period; with
three months that is the 1st of January, April, July and October. The first
deadline is the first scheduled date after the anchor day, every further one the
next scheduled date after the executed one. The rebalancing happens on the
first day that lies on or after the scheduled date; a rebalancing day after the
scheduled date does not shift the following dates. In the example the scheduled
date 1927-01-01 in run 1 falls on a Saturday, the rebalancing happens on
Monday, 1927-01-03, and the next deadline is 1927-04-01.

With quarterly rebalancing, the rule uses the first trading day of each quarter
(in general: the first trading day of each scheduled month). This is a
convention, not a recommendation.

Rule `termin_und_band`: the first deadline is anchor day plus period, every
further one counts from the actual rebalancing day plus period. If the day is
missing in the target month, its last day counts; after such a capping the next
deadline counts from the capped day, the last day of the month does not come
back. In the example run 2 rebalances on 1927-01-31, the deadline falls on
1927-02-28, and after the rebalancing on this day the next deadline is
1927-03-28.

After the deadline has expired, `termin_und_band` rebalances on the first day
on which `|quote_before_percent - 100 * g| >= band_percentage_points` holds; a
band only just reached counts. As long as the band is not breached, no
rebalancing happens, and the deadline stays. The backtest of the site computes
this rule not today; the package shows it in the second run.

The holding buys on the anchor with the starting weights and never rebalances:
`value_hold = 100 * (g * stock_price / stock_price_0 + (1 - g) * bond_price / bond_price_0)`,
with the prices of the anchor day as `stock_price_0` and `bond_price_0`.

The example takes a target weight of 60 %, in run 1 a period of three months
and in run 2 one of one month, so that several deadlines fit into few rows. The
input lists not every trading day, but in run 1 the first trading day on or
after each scheduled date and the days around the Saturday, in run 2 the days
around the deadlines and the rebalancings; the missing days change nothing in
the shown values, because the share counts between two rebalancings stay fixed
and every rebalancing day stands in the input. The site computes with periods
of 1, 3, 6 or 12 months and a stock share of 30 to 80 % in steps of 5.

The site stores the value on 4 decimal places and shows 0.01; the package
writes the values rounded on 12 decimal places.

## Steps

1. Read the input: reads input.csv and divides the rows by `run` into runs.
2. Set the anchor: buys on the first day of the run with the value 100 the share counts after the target weight and sets
   the first deadline, with `termin` on the first scheduled date after the anchor day, with `termin_und_band` on anchor
   day plus period.
3. Compute the quote before the rebalancing: values the share counts of the previous day to the prices of the day and
   computes from it value and stock quote.
4. Check deadline and band: determines whether the deadline is reached and whether the distance of the quote to the
   target weight reaches the band; from this follows by the rule of the run whether the rebalancing happens.
5. Rebalance: sets the share counts to the value of the day onto the target weight and the new deadline, with `termin`
   on the next scheduled date after the executed one, with `termin_und_band` on the rebalancing day plus period.
6. Compute the value and the holding: stock quote after the rebalancing and value of the holding with the starting
   weights.
7. Write the output: writes the reference output as CSV to stdout.

## What is not part of the calculation

The package computes no tax and no trading costs.

With the same closing prices of both products, adjusted for splits and distributions, on days on which both have a
price, and from the first common day, the site computes the same value curve. Raw closing prices deviate from every
distribution day onwards.

Not part of the calculation in the package are the state of the data, the
choice between NAV and closing price, the adjustments that LETF.io itself makes
on the prices, and the outlier check. For data that one obtains oneself, its
terms of use apply.
