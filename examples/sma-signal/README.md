# All numbers are invented; they only show the calculation and say nothing about a market, a product or the future.

This package shows trend following with moving average and buffer, computed day
by day: which line applies, whether the money is in the market, and which value
curve follows. Call: `python3 recompute.py input.csv`. The output goes as CSV to
standard output; the file with the target values is the reference output
(`output.csv`). Code and data are under LICENSE-CODE.

## Columns

### Input (input.csv)

| Column | Meaning | Unit | Time basis |
|---|---|---|---|
| date | day of the row | date | trading days of the index |
| index | closing price of the index | points, first day 100 | trading days |
| product_price | closing price of the product; empty in lead rows and on days without product price | base 100 at the first day with product price | trading days |
| money_rate_percent_year | last known money-market rate in the currency of the product; empty as long as none is known | percent per year | trading days |
| window_trading_days | length of the window; once per package, in the first row | trading days | trading days |
| buffer_percent | buffer around the average, equal for both directions; once per package | percent of the average | no time |
| trading_cost_percent | trading cost per trade; once per package | percent of the value | per trade |

### Output (output.csv)

| Column | Meaning | Unit | Time basis |
|---|---|---|---|
| date | day of the row | date | trading days of the index |
| index_rounded | round(index, 2), for display only | points | trading days |
| sma | average of the latest index levels over the window, unrounded | points | trading days |
| line | average with buffer, by the line state of the previous day, unrounded | points | trading days |
| line_rounded | round(line, 2), for display only | points | trading days |
| above_line | index is at least line, both unrounded | ja/nein | trading days |
| line_state | `aufwaermen`, `drin` or `draussen` at the closing price, led unrounded; sets the edge of the line for the next day | word | trading days |
| invested | money in the product at the closing price | ja/nein | trading days |
| signal | `start`, `einstieg`, `ausstieg` or empty | word | trading days |
| money_interest_day | daily rate of the money market credited on that day, otherwise 0 | ratio | trading days |
| trading_cost | cost of the trade on the execution day | value points, base 100 | per trade |
| trade_count | entries and exits up to and including this row; `start` does not count | count | trading days |
| value_strategy | value of the strategy | base 100 at the first day with product price | trading days |
| value_hold | 100 times product price divided by the first product price | base 100 at the first day with product price | trading days |

Lead rows carry only `index` in the input and count into the window; in the
output all columns except `date` and `index_rounded` stay empty there.

## Calculation

The example spans several years: 1300 trading days from 1923-02-05, the window
210 instead of a mini window of 5, computed with the formula
`index[t] = index[t - 1] * (1 + r(t))` and `r(t) = 0.00025 + 0.01*sin(t/23)*cos(t/7)`,
and three set days that replace only the index. The site takes 50 to 500 trading
days in steps of 5, the buffer from 0 to 5 % in steps of 0.5, and the trading
cost from 0 to 1 % in steps of 0.05.

The set days with date, value and purpose:

| Date | Value | Purpose |
|---|---|---|
| 1923-11-23 | 100.4 | start decision above the line |
| 1925-11-06 | 111.34 | exit with eight box rows |
| 1927-11-07 | 126.116 | tie with exit |

The average runs over the whole index series, including the lead rows. The
window counts rows of the index calendar; product prices apply only on trading
days of the index.

One comparison decides line state and money. The line state picks the edge of
the line for the next day: in state `drin` the value `sma * (1 - b)` applies, in
state `draussen` the value `sma * (1 + b)`, on the first day with a full line
`sma` applies without buffer. It changes with unrounded values: `drin` stays as
long as the index reaches the line at least, `draussen` stays as long as it is
below. If the index is unrounded just below the line but equal when rounded, it
counts as below.

Shown are `index_rounded` and `line_rounded`; rounding is only for display.

The first day with product price and full line is the start decision (`start`):
the index is at least on the line (unrounded), the money goes into the market at
the closing price, without signal and without trading cost; otherwise it waits
in the money market for the first entry. The first signal comes at the earliest
on the next price day.

A signal forms at the closing price and is executed at the same closing price.
Every entry and every exit multiplies the value with `(1 - c)`; the trading costs
add up with the number of trades.

Out of the market the money carries per row with product price the daily rate
`(1 + r/100)^(1/252) - 1`, also over a weekend. `r` is the last known rate in
the currency of the product, never below 0; if none is known yet, the fallback
2.5 % per year applies. On the first day with product price there is no
interest; the warm-up days from the second price day and the day the warm-up
ends accrue interest. On the entry day the money still carries interest, on the
exit day no more, because it was still in the market that day.

On an index day without product price there is no interest and no decision, the
cash level of the previous day stays; a warm-up end or a crossing of the line
takes effect only on the next price day. The value columns stay empty on such
days.

The standard curve of the site stands at 100 on the first day with product
price, hold is `100 * P_t / P_first` including the warm-up days. "Your version"
on the site normalizes strategy, hold and own curve at the warm-up end; to
compare, one divides the columns `value_strategy` and `value_hold` by their
value on that day.

The site also allows an offset of one trading day: then trading happens at the
closing price of the next row, and the trading costs fall on that execution day.
On entry the money then carries interest on the signal day and on the execution
day; the package computes without offset, like all defaults of the site.

The chart of the site compresses long periods for display into weekly values;
the computation runs day by day, and the package shows every trading day.

The package knows one buffer for both directions, one confirmation day and the
comparison `>=`; separate buffers for entry and exit and several confirmation
days the backtest of the site does not compute.

## Steps

1. Read the input: reads input.csv and the three package values from the first row.
2. Compute the average: averages the latest index levels over the window.
3. Track the line and the line state: sets the edge by the state of the previous day and compares index and line unrounded.
4. Decide the cash position: start decision on the first day with product
   price and full line, then entry and exit by the comparison on unrounded
   values.
5. Compute the value: product return in the market, money-market interest
   out of the market, trading cost per trade, hold as price ratio.
6. Write the output: writes the reference output as CSV to stdout.

## What is not part of the calculation

The package does not compute tax or the Vorabpauschale.

Before the launch of a product, the leverage model (`../leverage-model/`) stands
behind the product prices. For products in a currency other than the index, the
reconstruction there multiplies additionally with (1 + exchange rate return),
unlevered; the package `leverage-model` does not show this step yet.

With the same product prices, the same signal days, the same money-market
rates (without a known rate 2.5 %) and the same trading costs, the site
computes the same value curve; the site compares the signal at the unrounded
raw level of the index, which it does not show; the package demonstrates the
same rule on its invented series. Before the launch, the leverage model
stands behind it.

This invented example needs no license notice for a market data source.
For data one obtains oneself, its terms of use apply.
