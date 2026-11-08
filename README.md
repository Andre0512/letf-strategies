# letf-strategies

Open explanatory texts on the investment strategies that [LETF.io](https://letf.io)
maps. This repository contains the **text**: what a strategy is, where it comes
from, what speaks for and against it, what mistakes are frequently made and what
sources there are on it.

## Purpose

Whoever follows a strategy shall be able to read up and **recompute** what they
are getting into. That is why the explanatory texts lie open and versioned here
instead of in a database or a CMS:

- Every change to a statement is visible as a commit.
- Every claim carries its source in the frontmatter (`sources`), including the
  license and the note whether it may be quoted or reproduced.
- Whoever finds a mistake can prove and report it without having an account at
  LETF.io.

## Structure

| Path | Content | License |
|---|---|---|
| `content/strategies/<slug>.de.md` | explanatory text, **German source** (leading) | CC BY 4.0 |
| `content/strategies/<slug>.en.md` | English mirror of the same page | CC BY 4.0 |
| `docs/frontmatter-schema.md` | the frontmatter schema with a complete example | CC BY 4.0 |
| `scripts/` | check scripts (for example `check_frontmatter.py`) | MIT |
| `tests/` | tests of the check scripts | MIT |
| `registry/strategy_preset_slugs.json` | generated copy of the allowed preset slugs, check data | MIT |
| `examples/` | example packages for recomputing (code, CSV, README) | MIT |
| `llms.txt` | entry point for AIs into the example packages | MIT |

German is the source language, English the mirror. When the German file changes
in content, the English one is pulled along; see
[CONTRIBUTING.md](CONTRIBUTING.md).

## Relation to the website

The explanation pages on LETF.io consist of **two** parts, and the separation is
strict:

- **From this repo** comes the running text: explanation, origin, weighing,
  typical mistakes, regional and tax classification, sources.
- **From the website** come all numbers: parameters, weights, bands, SMA
  lengths, buffers, products, charts and key figures. They are rendered from the
  strategy definitions (presets) the frontmatter points to via `definition_ids`.

**Parameter values are never typed in here.** Otherwise text and definition
drift apart, and the page claims something else than the tracker computes. A
sentence like "the bands lie at 5 percentage points" does not belong into the
text; the website renders the bandwidth from the definition. The text instead
explains *why* bands exist and what they do.

## Licenses (split)

This repository stands under **two** licenses:

- **Content**: everything under `content/` as well as the documentation under
  `docs/`: [Creative Commons Attribution 4.0 International](LICENSE)
  (CC BY 4.0). Reuse allowed, also commercially, with attribution.
- **Code**: everything under `scripts/`, `tests/`, `registry/` and `examples/`
  as well as `llms.txt` and the CI configuration: [MIT](LICENSE-CODE).

In case of doubt the path decides: `content/` and `docs/` are content,
`scripts/`, `tests/`, `registry/`, `examples/` and `llms.txt` are code.

Both licenses cover only the own texts and code of LETF.io, **not** third party
material: quotes, linked or named sources, third party data and graphics,
trademarks and index names stay with their rights holders, see
[NOTICE](NOTICE). What may be taken over from a source stands per source in the
frontmatter (`license`, `may_reproduce`).

## Checking

```bash
pip install pyyaml
python scripts/check_frontmatter.py        # checks all files under content/
python -m unittest discover -s tests -v    # tests of the check scripts
```

The same two steps run in the CI, together with a Markdown lint.

The check includes the `definition_ids`: they must stand in
`registry/strategy_preset_slugs.json`, the committed copy of the allowed preset
slugs. This copy is not maintained by hand but generated from the registry
export when the presets change:

```bash
python scripts/sync_preset_slugs.py --export ../finance_api/strategy_presets.json
```

This needs the source repo beside it and therefore runs locally, not in the CI.
