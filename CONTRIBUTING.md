# Contributing

Thanks for reading along and writing along. This repo is deliberately kept
small: Markdown files with frontmatter, one check script, nothing else.

## The two kinds of files

Per strategy there are exactly two files in `content/strategies/`:

- `<slug>.de.md`: the **source**. Content work happens here.
- `<slug>.en.md`: the **English mirror**. It is pulled along after content
  changes to the source, ideally in the same pull request.

Both files must exist; the check script aborts otherwise. Pure language fixes in
one of the two files need no change in the other; only content changes do.

## The most important rule

**No parameter values, ticker key figures or formulas in the text that the
website renders.**

SMA lengths, buffers, band widths, target weights, TER, fund volume, ISINs,
returns, drawdowns: all of that comes from the strategy definitions and the
market data of LETF.io and is rendered on the page around the text. If it also
stands in the text, it goes stale there, and then the page contradicts itself.

Explain the **mechanics** instead: why a buffer exists, what it does against
false signals, when it hurts. Historical classification with year and source
("in 2008 the index fell by ...", documented) is fine; it is a quote and not a
rendered live value.

## Sources

Every source belongs in the `sources` frontmatter, with license and the note
whether it may be reproduced (`may_reproduce`). Foreign texts, tables and
graphics are not taken over without this note; the repo licenses do not cover
them, see [NOTICE](NOTICE). The schema and a complete example
stand in [docs/frontmatter-schema.md](docs/frontmatter-schema.md).

## Suggestions and errors

A **normal issue** is enough, in any language; German and English are
guaranteed to be read. There is no form obligation and no template pressure.
Helpful is: what stands there, what is wrong about it, how do you know it
(link). Pull requests are welcome, but not a must; a well documented error
report is worth more than a hasty PR.

## Before submitting

```bash
pip install pyyaml
python scripts/check_frontmatter.py
```

That checks required fields, types, license values and the de/en pair. The same
check runs in the CI.

## Extension path

For translation automation, glossary, section markers and a fine-grained item
structure there is a documented extension path; until then it deliberately stays
with the two kinds of files above.
