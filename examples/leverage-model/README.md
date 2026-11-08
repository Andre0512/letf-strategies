# All numbers are invented; they only show the calculation and say nothing about a market, a product or the future.

This package shows the price of a leveraged product before its launch, computed
day by day. Call: `python3 recompute.py input.csv`. The output goes as CSV to
standard output; the file with the target values is the reference output
(`output.csv`). Code and data are under LICENSE-CODE.

## Columns

### Input (input.csv)

| Column | Meaning | Unit | Time basis |
|---|---|---|---|
| date | day of the row | date | trading days |
| index_return | index return of the day | ratio | trading days |
| rate_percent | interest rate of the index currency | percent per year | calendar days |
| calendar_days | calendar days to the previous day | calendar days | calendar days |
| real_price | real price, otherwise empty | base 100 | trading days |
| leverage | leverage of the product | ratio | no time |
| ter_percent_year | running costs of the product | percent per year | calendar days |
| markup_bps_year | markup on the interest | basis points per year | calendar days |
| hedge_bps_year | hedging costs | basis points per year | calendar days |
| lending_bps_year | income from securities lending | basis points per year | calendar days |
| dividend_percent_year | dividend yield | percent per year | calendar days |
| withholding_bps_year | withholding-tax advantage | basis points per year | calendar days |
| ter_base_percent_year | running costs of the underlying | percent per year | calendar days |
| financing_in_ter | financing included in the TER; per product; in the package only in the first row as a check `wahr` | `wahr`/`nein` | trading days |

### Output (output.csv)

| Column | Meaning | Unit | Time basis |
|---|---|---|---|
| date | day of the row | date | trading days |
| factor_gross | gross factor: 1 + leverage × index return | ratio | trading days |
| factor_ter | factor of the running costs of the product | ratio | calendar days |
| factor_financing | financing factor | ratio | calendar days |
| factor_hedge | hedging-cost factor | ratio | calendar days |
| factor_lending | lending-income factor | ratio | calendar days |
| factor_dividend | dividend factor with leverage | ratio | calendar days |
| factor_withholding | withholding-tax-advantage factor with leverage | ratio | calendar days |
| factor_base | factor of the running costs of the underlying with leverage | ratio | calendar days |
| share_year_ter | calendar days/365 | ratio | calendar days |
| share_year_financing | calendar days/360 | ratio | calendar days |
| daily_return | product of the factors minus 1 | ratio | trading days |
| price | unrounded price chain | base 100 | trading days |
| price_saved | round(price, 6), how the website stores it | base 100 | trading days |
| direction | direction of the reconstruction | word | trading days |

## Calculation

The calculation runs day by day (daily reset) and is multiplied, never as an
annual formula "index return times leverage". There is no currency conversion.

Whether the financing is already in the index series is a separate setting; in
the reconstruction it never is, so the ladder subtracts it.

If the product has financing in the TER or a leverage of at most 1, the
financing factor is 1. The example shows this in the first row with
`financing_in_ter = wahr`; its daily return does not enter any price.

The interest is the rate of the index currency (or an interest curve fixed per
product) at the later day of the interval, without carry-forward; if it is
missing, the reconstruction ends there going backward, and going forward no
price is created until the next real price.

A daily swap rate in basis points per trading day replaces, where present, the
financing (even when included in the TER) and is deducted once per interval,
independent of the calendar days; in the example it is not set.

The ladder of the website has one stage of collateral interest after the
financing; in the reconstruction it is always 1 and therefore not part of the
package.

Limits: the reconstruction holds only for leverage above 1 up to 3; a daily
return of at most -100 % or a price outside 0 to 999.999.999.999 ends the
reconstruction backward or leaves the day without a price forward.

On the website, TER, dividend yield and withholding-tax advantage can change
from day to day (if a day is missing in the earnings series, 0 applies); the
package keeps them constant.

LETF.io sets the markup on the interest per product from the quiet stretches of
the last 252 trading days of real prices adjusted for splits and payouts; the
value determined this way applies to the whole reconstructed time.

The withholding-tax advantage is a calculated quantity, invented for the
example, without tax significance for any country.

The product sizes lie in every daily row, fixed per product; the website knows
them once per product. For `financing_in_ter`: per product; in the package only
in the first row as a check `wahr`. The first row shows the case of a product
with financing in the TER; its daily return does not enter any price.

## Steps

1. Read the input: reads input.csv and the product sizes.
2. Compute the ladder factors: sets up the eight factors of the ladder.
3. Form the daily return: multiplies all eight factors.
4. Rebuild the chain: backward from the first real price, then forward.
5. Write the output: writes the reference output as CSV to stdout.

## What is not part of the calculation

The calibrated values, the state of the data, LETF.io's own split adjustments
and the choice between NAV and closing price as the first real price are not
part of the calculation in the package.

With the same inputs, including the cost sizes, the website computes the same
numbers. Whoever estimates the cost sizes themselves only comes close to the
website; for data one obtains oneself, its terms of use apply.

From the launch of a product, real prices stand behind it; whoever starts there
and normalizes to that starting point does not need the cost sizes and arrives
exactly at the website's values with the same real prices.
