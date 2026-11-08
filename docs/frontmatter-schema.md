# Frontmatter and page schema

Every file under `content/strategies/` starts with a YAML frontmatter block,
delimited by `---` on the first line and another `---` line after it.
Everything after that is the Markdown text.

Since wave S1 the schema describes not only the frontmatter, but also the
**structure** of the page: fixed chapter anchors and six kinds of containers.
The reason is the division of labour: the text lives here, the numbers and the
interaction come from the definition and are rendered by the website. For that
to fit, the website must be able to rely on the structure.

Everything is checked by `scripts/check_frontmatter.py`; the check is the
binding version of this document.

## One file type

Per strategy and language there is exactly one file: the **core page**. The
file name is `<slug>.<lang>.md`, `lang` is `de` or `en`.

Until wave S9 there were also **region files** (`hfea.eu.de.md`,
`hfea.us.en.md`) that carried what one region changes. Since S10 they are
dissolved: their content lives in the `region` chapter of the core page,
bracketed by `:::market` blocks. The reason is translation. A region file had
to exist per market and language, which is why the US layer never had a German
version; a market block, in contrast, is translated like any other paragraph
and only shown or hidden in the frontend.

German is the source language. A missing English mirror is a **warning**; a
missing German version is an **error**.

## Fields of the core page

| Field | Type | Required | Meaning |
|---|---|---|---|
| `slug` | String | yes | Identifier of the content unit. Must match the file name and be the same in both language files. Characters: `a-z`, `0-9`, `-`. |
| `status` | `draft` \| `published` | yes | `draft` is not served by the website. |
| `origin` | Object | yes | Origin of the strategy for the origin tile: `author`, `year`, `url`. |
| `definition_ids` | Map region to list of strings | yes | The strategy definitions (presets) this page explains. |
| `sources` | List of objects | yes | Sources, see below. May be empty, but must exist. |
| `related` | List of strings | no | Slugs of related content units. |
| `purpose` | String | no | One sentence for the overview page: what the strategy is meant for. Per language version. |
| `building_blocks` | List of strings | no | Building blocks of the strategy for the overview page, from fixed vocabulary. The same in both language versions. |
| `short_summary` | String | no | "Key points" box of the page: three to five sentences, 80 to 600 characters, no dashes, no percent figures, no words of the purpose block list. Per language version. |
| `factsheet` | List of objects | no | Fact sheet of the page: 3 to 9 rows with `label` and `value` (non-empty text) and optional `ref` (a chapter anchor of the same page). Per language version. |
| `last_reviewed` | Date `YYYY-MM-DD` | yes | When the content was last reviewed on the merits. |
| `reviewed_by` | String | yes | Who reviewed it (name or handle). |

There is no title in the frontmatter: it is the first `#` heading of the
document.

### `purpose` and `building_blocks`

The overview page `/strategies` shows one sentence per strategy saying what it
is meant for, and its building blocks as chips (wave strategie-felder, GO Andre
2026-09-26).

```yaml
purpose: "Stay invested with leverage, but sit out long crashes where possible."
building_blocks:
  - aktien
  - cash
```

<!-- The code span shows the exact spelling of the block list; MD038 flags the spaces for a reason. -->
<!-- markdownlint-disable MD038 -->

- `purpose`: 20 to 110 characters, ends with a period, without a dash and
  without a number with percent. Blocked because it would sound like advice, a
  forecast or a promise: in `*.de.md` the words `solltest`, `prognose`,
  `optimal`, `beste`, `garantiert`, `sicher` (as whole words) and everything
  starting with `empfehl` or `erwartet`; in `*.en.md` `recommend`, `should`,
  `expected`, `best`, `optimal`, `guarantee`, `safe` (as whole words). Upper
  and lower case do not count.
- `building_blocks`: 1 to 4 distinct keys from `aktien`,
  `lange-staatsanleihen`, `staatsanleihen`, `gold`, `cash`; the order is the
  display order. The list is written as a block list (one line `  - aktien`
  each), because the frontend's frontmatter parser only reads block lists.
  German and English version name the same building blocks; the frontend
  translates the label.

<!-- markdownlint-enable MD038 -->

### `origin`

```yaml
origin:
  author: "HEDGEFUNDIE (Bogleheads-Forum)"
  year: 2019
  url: "https://www.bogleheads.org/forum/viewtopic.php?t=272007"
```

`year` is a year between 1900 and 2100, `url` starts with `http://` or
`https://`. The tile on the overview page takes author and year from here, not
from the backend.

## Structure of the page

### Chapters as H2 with fixed anchors

The core page carries exactly these fourteen H2 headings, in this order:

```markdown
## regel
## rueckschau
## parameter
## herleitung
## beispiele
## dabeibleiben
## fehler
## abwaegung
## region
## geschichte
## kritik
## faq
## weiterlesen
## quellen
```

This list and everything in this section that names its anchors is the old
scheme. It holds for pages without a chapter `rule` and lapses once HFEA is
converted; the SMA page already follows the new scheme in the section
"Struktur V5 (Übergang)" further below.

`rueckschau` carries the backtest (the frontend labels the chapter that way);
`dabeibleiben` covers what happens between the signals. Both came with wave
S6c.

`geschichte` tells the community history of the strategy in stations and came
with wave S9 under the anchor `herkunft`; since S10 the anchor is `geschichte`,
closer to Wikipedia's outline. Every station may carry an H3, because outside
`faq` a top-level H3 means nothing to the checker.

`kritik` came with S10 and carries the objections against the **strategy
itself**: overfitting, missing costs in other people's backtests, a regime that
does not have to return. User errors stay in `fehler`; the dividing line is
whether the objection also stands against a flawless execution. Every station
names the objection, the page's counterposition in one sentence, and the link.

`weiterlesen` and `quellen` have shared the work since S10, again along
Wikipedia's logic. `quellen` are the **single references**: what the page
relies on, with the chapter the source backs. `weiterlesen` are the **places
where it goes on**: series, wikis, videos, blogs and forums, each entry with
one sentence on what can be found there. The frontend labels the chapters
"Further reading" and "Sources".

`region` carries the content of the former region files since S10 and is called
"Implementation and taxes" in the frontend. It is structured with three H3s
(products, implementation, taxes), and its paragraphs live in `:::market`
blocks: general European product and implementation paragraphs under `eu`,
German tax law under `de`, US paragraphs under `us`. What holds for all markets,
for example the note that the classification is no tax advice, stands outside
the blocks.

`regel` also carries the rule chart since S11. Until then it stood in its own
chapter `chart` beside it, which described the same figure a second time and
explained how to use it; both are gone. The block `:::chart type=main` stands
in the chapter after the first paragraph, and a sentence behind it says why
this figure shows no returns.

Two chart types separate the two tasks: `type=main` is the rule chart in the
chapter `regel`, `type=backtest` the comparison of strategy against holding in
the chapter `rueckschau`. Two containers with the same `type` on one page would
not be unambiguous for the parser, hence the separate type.

The heading is the anchor, not the displayed title: the chapter names are the
same for all strategies and come from the translation file in the frontend.
Chapter 12 (try it yourself) is pure frontend business and has no anchor.

### The introduction before the first anchor

The text between the H1 and `## regel` is the **introduction**; the frontend
shows it below the title, together with the origin tile. The checker neither
requires nor forbids it: everything before the first H2 counts as body text.

Since S9 its task is fixed, since S9b its tone as well. Three short sections:
the rule itself, why someone uses it, what the page does with it. The rule
stands with a real product and a real number, not as a generic term.

Three patterns stay out:

- **No addressing the reader.** The introduction describes the rule, it
  addresses nobody yet; the direct address starts in the chapter `regel`.
- **No "people do this".** The reason belongs to the matter, not to an unnamed
  crowd.
- **No list of nouns.** What the page does stands in verbs ("shows the rule in
  the chart, recomputes it, explains every parameter"), not as a list of
  chapter names.

On top of that **no definitions** and none of the words that are only explained
further down: fund, bond, index series, signal currency, version. "Leveraged
ETF" is enough.

### Body text and two boxes

The **body text** outside the containers carries the page: short sentences,
direct address, one thought per paragraph, every technical term explained at
its first occurrence. What goes deeper stands in one of the two containers:

```markdown
:::layer compute
What goes beyond the core statement of the chapter: limits of an
approximation, a catalogue of biases.
:::

:::layer sources
What the source backs, what it does not back, what LETF.io cannot do.
:::
```

The containers are still called `compute` and `sources`, and the content does
not change because of that. What changed is how the frontend shows them: there
is no global switch above the page anymore that flips between understanding,
recomputing and sources. Instead `:::layer compute` stands as the box **For
recomputation** and `:::layer sources` as the box **Sources for this chapter**
at its place in the chapter.

For the text that means: a box must be readable at its place without anyone
having switched anything before, and the body text must not depend on a box.

**No chapter may consist entirely of boxes** (S11 addendum, the checker turns
that red). The frontend shows a box collapsed; a chapter made only of boxes
would be a heading with a closed box below it for the reader. The box is the
deep dive, not the content. For the check counts every non-empty line outside
the containers and every container that is not a `:::layer`; `:::market` is
transparent here, because it selects the market and hides nothing.

This concerns `herleitung` in particular: **the formulas and their explanation
are the content of this chapter and stand in the body text**, not in the box.
Into a box there belongs only what goes beyond the core formula: for example
the two limits of the approximation for volatility drag at `sma-trend`, or the
question what the rebalancing premium is measured against at `hfea`.

### Containers

Six kinds, all opened with `:::` and closed with a line `:::`.
**The five content containers do not nest**, so that the assignment stays
unambiguous; a parameter card stands beside a box, not inside it. The only
exception is `:::market`, which may enclose them, see below.

| Container | Attributes | Purpose |
|---|---|---|
| `:::layer compute` \| `:::layer sources` | name of the box | The two boxes, see above |
| `:::parameter key=window` | `key` from the descriptor list | Text of a parameter card; numbers come from `/v3` |
| `:::faq` | none | One question; the question itself is an H3 in the container. Groups see below |
| `:::example from=2020-02-19 to=2020-04-30 isin=FR0014010HV4` | period and product | Example episode; the website computes and draws, the text tells |
| `:::chart type=main class=puls` | see below | A chart; the text provides introduction and reading aid |
| `:::market de,eu` | market codes from the market registry | What holds only for certain markets, see below |

The allowed `key` values stand in `registry/strategy_parameter_keys.json`. The
list is taken provisionally from the contract in the plan and will be replaced
as soon as the backend exports the `parameter_descriptors`.

The ISIN of an example must appear in the `definition_ids` of the same file.
`from` must lie before `to`.

### The container `:::parameter`

Every parameter card has the same form, so that the frontend can build
comparison boxes from it and show the cost paragraph as a line of its own. The
paragraphs of the card follow in four steps:

<!-- The code spans show the exact prefixes with their trailing space; MD038 flags them for a reason. -->
<!-- markdownlint-disable MD038 -->

1. Paragraphs without a prefix say what the value is and in which unit it is
   meant. A paragraph with a prefix never stands before them.
2. Two or three paragraphs with a bold prefix `**<Richtung>:** ` say where the
   value acts: `**Länger:** ` and `**Kürzer:** `, `**Größer:** ` and
   `**Kleiner:** `, `**Mehr:** ` and `**Weniger:** `, `**Höher:** ` and
   `**Niedriger:** `, `**Breiter:** ` and `**Enger:** `, or named options like
   `**Nur Termin:** `. Three are allowed when the value has more than two
   directions.
3. Exactly one paragraph starts with `**Was es kostet:** ` or `**Was es spart:** `.
   It stands for itself, and the card never has both prefixes.
4. Optionally paragraphs without a prefix follow as hints: limits of the
   effect, what the tracker can do, references to other chapters.

<!-- markdownlint-enable MD038 -->

### The container `:::faq`

The answer starts with the **short answer** as its first paragraph: at most
two sentences that end in `.`, `?` or `!`. After that the long answer follows
in further paragraphs. Almost every answer closes with the closing line
`Mehr dazu im Kapitel [<Kapitel>](#<anker>).`; `<Kapitel>` names the target
chapter and `<anker>` its anchor. Chapter references in the body text of the
faq stand in the same link form; the phrase "further up" does not appear in
the chapter `faq`.

### The container `:::market`

Part of every strategy page does not hold everywhere: products, trading hours
and tax law differ per market. Since wave S10 this part no longer stands in
files of its own, but in the body text of the core page, bracketed by a market
container:

```markdown
## region

The rule is the same everywhere. Different are the products and the taxes.

:::market eu
For the invested side there are leveraged funds and exchange-traded notes in
Europe.
:::

:::market de
On realised gains flat-rate withholding tax falls due in Germany.
:::

:::market us
Both roles are available as exchange-traded funds.
:::
```

The codes stand **comma-separated without spaces**, two lower-case letters
each; their order does not count, `:::market de,eu` and `:::market eu,de` are
the same. **Everything outside a market block holds for all markets.** Every
block is translated like any other paragraph: both language versions carry the
same blocks, including the ones that are not shown in their market at all.

#### The market registry

The allowed codes stand in `registry/markets.json`. It knows two levels:

| Level | Codes | Meaning |
|---|---|---|
| Region | `eu`, `us` | The level on which the backend keeps its presets (`definition_ids`) |
| Country | `de`, `at`, `fr` (under `eu`) | What a single country changes, above all tax law |

A block for a **region** is also seen by a reader whose country stands under
this region: `:::market eu` therefore also reaches someone with country `de`.
A block for a **country** reaches only this country.

Since S11 Germany, Austria and France stand under `eu`. A code for "other EU"
does not exist and shall not exist: that is the region `eu` without a
recognised country, and how the frontend labels this case is frontend
business. In the text `:::market eu` therefore still means "holds in Europe",
not "holds for everyone except the named countries".

For the transition period the frontend treats a reader in the region `eu`
**without a recognised country as `de`** (`fallback_country` in the registry).
That is why German tax law may already carry `de` today, although Austria and
France share the same region: the fine split is coming, the codes do not have
to be touched again for it.

#### The rules

1. `:::market` may enclose the other five containers (`:::faq`,
   `:::parameter`, `:::example`, `:::chart`, `:::layer`), **never the other way
   around**. A market block therefore always stands on the top level of a
   chapter.
2. `:::market` inside `:::market` is forbidden. Whoever means two markets
   writes two codes.
3. Every code must stand in the registry; a duplicated code in the same
   attribute is an error.
4. German and English version carry **per chapter the same market blocks in
   the same order with the same codes**. Otherwise the same reader would see a
   different text per language.
5. **No chapter may be empty for one market.** Either the chapter has
   something outside all market blocks, or there is a block for **every
   region** of the registry. A country code does not count for this: a chapter
   carrying only `de` would stay empty for a reader in Austria as soon as the
   frontend keeps the countries apart.
6. An empty market block and an unclosed one are errors, like for any other
   container.

For the word list and the two boxes a market block changes nothing: it selects
the market, not the level. A `:::layer compute` inside a market block stays the
box for recomputation, and a word from the word list inside a market block is
warned about like in the remaining body text.

### Categories in the chapter `faq`

The faq chapter may order its questions into groups, so that the reader can
jump by purpose instead of scrolling. A group opens with an **H3 on top
level**, so outside a `:::faq`:

```markdown
## faq

### Einstieg und erste Schritte

Optionally one sentence on what holds this group together.

:::faq
### Was heißt gehebelt?

Answer.
:::

:::faq
### Mit wie wenig Geld geht das?

Answer.
:::

### Im Alltag

:::faq
### Muss ich jeden Tag nachsehen?

Answer.
:::
```

All `:::faq` up to the next top-level H3 belong to the group above. Seven
rules hold:

1. Groups are an offer: a faq chapter without a single H3 stays valid.
2. **Either all questions grouped or none.** As soon as an H3 stands there, no
   `:::faq` may stand before it.
3. Between the groups stands **no body text**; at most one sentence directly
   below the H3 is allowed, before the first question. From the first question
   of the group on, body text on top level is an error.
4. Every group carries at least **two** questions, and **per market** at that:
   counted are the unconditional questions plus the market blocks that reach
   this market. Two questions of which one carries `de` and one `us` count two
   in the sum and still show only one to each reader; which is why since the
   S10 review the checker counts per code of the market registry and not the
   sum. Two exceptions: if the **H3 itself** already stands in a market block,
   the group does not appear in other markets at all and is not checked there;
   and for countries that the frontend does not yet read as a market of their
   own (all except the `fallback_country` of a region), a shortfall is only a
   **warning** until the fine split comes. The minimum started in S7 as a
   warning, because two groups were still waiting for their questions; since
   the fact-check addendum `GROUP_MINIMUM_IS_ERROR` is set to `True` in the
   check script.
5. The titles of one file must **differ**: the frontend builds the jump mark
   from the title.
6. German and English version carry **the same number of groups in the same
   order**; group *i* in German belongs to group *i* in English. The titles
   themselves are translated and are not compared. If a group carries a
   different number of questions per language, that is a warning.
7. `:::market` is **transparent** for the groups: a market block may stand
   inside a group and enclose single `:::faq`, or enclose a whole group
   including its H3. For the minimum count unconditional and market questions
   together, but per market separately, see rule 4.

The anchor of a group is `faq-<slug>`, where `<slug>` is built from the title
(lower-cased, spaces to hyphens). `### Einstieg
und erste Schritte` thus becomes `#faq-einstieg-und-erste-schritte`. The slug
is built in the frontend; the repo only guarantees that the titles inside one
file are unique. A registry of the anchors does not exist: `registry/` keeps
preset slugs and descriptor keys, no headings.

Only the chapter `faq` knows this meaning. In all other chapters a top-level
H3 stays what it has been: an ordinary subheading, no anchor and no group.

### Chart containers

A `:::chart` block tells the website which chart to draw at this place. The
body is **not** a result, but introduction and reading aid: what stands on the
axes, what the line, the band or the zone mean. All numbers come from the
backend.

| Attribute | Required | Values |
|---|---|---|
| `type` | yes | `main`, `backtest`, `distribution`, `longterm`, `rolling`, `panorama`, `heatmap`, `whipsaw`, `correlation`, `premium`, `drift`, `regime`, `volatility-drag`, `crossing`, `currency-panorama` |
| `class` | yes | `rueckschau` (long history, derived quantities), `puls` (the last few years, rule chart without return figures), `schema` (schematic drawing without data) |
| `parameter` | for `panorama` and `currency-panorama` | one key from the descriptor list |
| `metric` | no | `excess_return`, `drawdown`, `signals` |
| `layer` | no | only `compute`, for charts in the box for recomputation |

For `currency-panorama`, `parameter` names the quantity that runs along the
x-axis, not the split: swept is the window length, and the signal currency is
what separates the two lines from each other.

`distribution` came with S11 and stands in the chapter `rueckschau` behind the
community backtests: the distribution of the annual return over rolling
periods of ten, twenty or thirty years, strategy against holding. It replaces
`rolling` there, which drew a curve of its own for every start month and thus
showed a precision that overlapping windows cannot deliver. `rolling` stays in
the contract, but no page uses it anymore.

`longterm` stands in the chapter `rueckschau` behind the distribution and
shows the same rule on the index across several decades, rule against holding,
with a switchable leverage. The curves are rebuilt with assumed costs and
independent of the chosen product; the marking as a computation of our own
comes from the backend.

The two classes separate the two tasks of the charts and are labelled in the
frontend as well: the **review** computes on the long history and shows only
derived quantities; it carries the backtest. The **pulse** shows the last few
years and serves the chapter `regel`, which makes the rule visible: index and
line, phases and signal days, **without return figures**. The reason for the
missing numbers stands as one sentence in the chapter itself.

### Formulas

Formulas stand as KaTeX blocks between two lines `$$`:

```markdown
$$
\mathrm{SMA}_n(t) = \frac{1}{n} \sum_{i=0}^{n-1} P(t-i)
$$
```

The blocks must be paired and not empty. In the chapter `herleitung` they
stand in the body text since the S11 addendum, so that they are visible
without expanding anything; in all other chapters they belong into the
container `compute`.

## Word list for the body text

The checker warns when one of these words stands outside the two boxes:
`solltest`, `empfohlen`, `Empfehlung`, `Definition`, `Trefferquote`,
`Wahrscheinlichkeit`, `ehrlich`, `lohnt sich`, and their English
counterparts. `Definition` here stands for the backend term: in the body text
it is called version or preset. The reason is not language policing, but the
division of roles: the page describes what a value has done in the past, and
does not judge what someone should do. Numbers like hit rates we do not
publish, because we cannot back them up.

In `:::layer compute` and in charts with `layer=compute` the same words are
allowed: there it stands why they do not exist.

It is a **warning**, not an error; the exit code stays 0.

## Glossary

Three words that must mean the same on every page:

| Word | Meaning |
|---|---|
| **Preset** | a well-known, popular, proven starting version. A starting point, not a suggestion and not a default; every value can be changed freely in the stepper. |
| **Version** | the configuration someone follows. On the page "Your version", in the chart next to the standard version and holding. |
| **Holding** | the reference without a rule: the same product held throughout. |

**Definition** is the backend's term (the stored rule with its document). In
the body text of the pages it does not stand anymore; there it is called
version or preset.

## `definition_ids`

The values are IDs from the preset registry of LETF.io, not freely invented
names. The slug format comes from wave A2:

- **SMA presets**: `{canonical_strategy_id}__{ISIN}`, that is
  `SMA__{INDEX}__{LEVEL}__{LENGTH}__B{PUFFER_BPS}__{ISIN}`. Example:
  `SMA__MSCI_WORLD__NETR__255__B0__FR0014010HV4`. The bare
  `canonical_strategy_id` without ISIN is **not** the slug.
- **HFEA presets**: `HFEA__55_45__QUARTERLY__{ISIN}`. The ISIN is the one of
  the bond leg. There is one preset, the classic US version; a pair made of
  other building blocks is a version of its own.

### Check against the slug list

In the repo under `registry/strategy_preset_slugs.json` lies a committed copy
of the allowed slugs per region, produced by `scripts/sync_preset_slugs.py`
from the committed export of the registry. A slug that does not stand there is
an **error**, independent of `status`. A slug that stands there under another
region is one as well. The former prefix `PLACEHOLDER__` is thereby an error
even in drafts.

When the presets in the source repo change, the copy is regenerated and
committed first, then the affected `definition_ids` are adjusted:

```bash
python scripts/sync_preset_slugs.py --export ../finance_api/strategy_presets.json
```

Why a map across regions: the same strategy is implemented in Europe and the
US with different products. With the SMA presets the ID is **product
specific**: two ETFs on the same index with the same parameters yield two
entries, because the ISIN is part of the slug. That is intentional and no
duplicate.

## `sources`

Every entry is an object with exactly these fields; all are required except
`url`:

| Field | Type | Meaning |
|---|---|---|
| `title` | String | Title of the source. |
| `author` | String | Author, institution or handle. |
| `year` | Year | Year of publication; for continuously maintained pages the year of the state that is linked to. |
| `url` | String | `http://` or `https://`. The only field that **may be missing**, see below. |
| `kind` | Enum | Kind of the source, see the list. |
| `lang` | String | Language of the source, two lower-case letters (ISO 639-1). |
| `license` | Enum | License of the source, see the list. |
| `may_reproduce` | Boolean | May text parts, tables or graphics be taken over from it? |
| `role` | `source` \| `further_reading` | Single reference or place for further reading, see below. |
| `supports` | List of chapter anchors | Which chapters this source backs. |
| `market` | Market codes, optional | Comma-separated codes like `:::market` (`de`, `de,at`); the source applies only to these markets. Legal sources (`kind: regulation`) without `market` give a warning. |

**`kind`**: `paper`, `book`, `article`, `blog`, `forum`, `dataset`,
`documentation`, `regulation`, `video`, `other`. Public Reddit series are
`forum`.

**`license`**: `cc0-1.0`, `cc-by-4.0`, `cc-by-sa-4.0`, `cc-by-nd-4.0`,
`cc-by-nc-4.0`, `public-domain`, `proprietary`, `all-rights-reserved`,
`unknown`.

### `role`: single reference or further reading

Since wave S10 every source says what the page leads it for:

- **`source`** is a **single reference**. The page relies on it, and `supports`
  names at least one chapter that the source backs. The frontend shows it in
  the chapter `quellen`.
- **`further_reading`** is a **place for further reading**: a series, a wiki, a
  channel, a blog, a forum. It needs a `url`, and this `url` must appear as a
  link in the chapter `weiterlesen`, with the sentence beside it on what can
  be found there. `supports` then lists `weiterlesen`.

The checker tests both directions: a source with `role: source` without a
chapter in `supports` is an error, and a source with `role: further_reading`
whose address does not stand as a link in the chapter `weiterlesen` likewise.
A tile for further reading without a sentence beside it would else be a
reference into nowhere.

The rule does not hold the other way round: the chapter `weiterlesen` may also
link a source with `role: source`. The origin thread of a strategy is a single
reference and at the same time worth reading as a whole.

### A source without `url`

`url` may be missing as the only field. The case is narrow: a document that
exists, but that has no publicly retrievable address, for example an issuer
factsheet behind a lock. Then `title` and `author` name the **issuer and the
kind of document** so precisely that the reader finds it at the provider, and
the source tile stays without link.

Inventing an address or entering an unverified one is the alternative that
this field is meant to prevent. Whoever has a retrievable address enters it.

A rule the script enforces: with `proprietary`, `all-rights-reserved` and
`unknown`, `may_reproduce: false` must hold. Linking and summarising in one's
own words stays allowed then, taking over does not.

`supports` contains anchors from the chapter list of the core page. From them
the website builds the source tile with the addition which chapter the source
backs.

## Complete example (shortened core page)

```markdown
---
slug: sma-trend
status: draft
origin:
  author: "Michael A. Gayed, Charles Bilello"
  year: 2016
  url: "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2741701"
definition_ids:
  eu:
    - SMA__MSCI_WORLD__NETR__255__B0__FR0014010HV4
sources:
  - title: "Leverage for the Long Run"
    author: "Michael A. Gayed, Charles Bilello"
    year: 2016
    url: "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2741701"
    kind: paper
    lang: en
    license: all-rights-reserved
    may_reproduce: false
    role: source
    supports:
      - herleitung
      - quellen
  - title: "ZahlGrafs Exzellente Abenteuer"
    author: "ZahlGraf (r/mauerstrassenwetten)"
    year: 2022
    url: "https://redd.it/s71qds"
    kind: forum
    lang: de
    license: unknown
    may_reproduce: false
    role: further_reading
    supports:
      - weiterlesen
related:
  - hfea
last_reviewed: 2026-09-04
reviewed_by: s1-entwurf
---

# Die SMA-Trendfolge

One sentence on what the strategy does.

## regel

Body text of the chapter.

:::chart type=main class=puls
What the curves mean.
:::

## parameter

:::parameter key=window
What the window does and why there is a range instead of a single value.
:::

## herleitung

The moving average is the mean of the last $n$ closing prices:

$$
\mathrm{SMA}_n(t) = \frac{1}{n} \sum_{i=0}^{n-1} P(t-i)
$$

:::layer compute
What goes beyond the formula, for example the limits of an approximation.
:::

## beispiele

:::example from=2020-02-19 to=2020-04-30 isin=FR0014010HV4
What the rule did, what it cost, what holding would have done.
:::

## fehler

...

## abwaegung

...

## region

### Steuern

:::market de
What German tax law makes of this rule.
:::

:::market us
What a US brokerage account changes about it.
:::

## geschichte

### 2016: Das Paper

What the station contributed, in three to six sentences.

## kritik

### The window is selected on the past

The objection, the page's counterposition in one sentence, the link.

## faq

:::faq
### Muss ich jeden Tag nachsehen?

Answer in three to six sentences.
:::

## weiterlesen

:::market eu
- **ZahlGrafs Exzellente Abenteuer** rechnet die Regel für Europa nach:
  [Teil 1](https://redd.it/s71qds).
:::

## quellen

:::layer sources
What the source backs and what it does not.
:::
```

## Struktur V5 (Übergang)

Since wave struktur-v5-inhalt two page schemes live side by side. The SMA page
follows V5, HFEA still the old one. The old section above stays valid until
HFEA is converted; then it lapses and this section is the only one.

### The marker: `## rule` decides

The checker picks the scheme per page. A page with an H2 `## rule` follows V5,
every other page the old anchors. There is no mixing: a V5 page carries only V5
anchors, in chapters as well as in `supports`.

### The fourteen anchors and their areas

A V5 page carries exactly these fourteen H2 headings, in this order:

```markdown
## rule
## examples
## backtest
## parameters
## implementation
## staying-invested
## mistakes
## history
## tradeoffs
## criticism
## math
## recompute
## faq
## sources
```

The frontend groups them into four areas:

| Area | Anchors |
|---|---|
| Lernen | `rule`, `examples`, `backtest` |
| Anwenden | `parameters`, `implementation`, `staying-invested` |
| Verstehen | `history`, `tradeoffs`, `criticism`, `math` |
| Nachschlagen | `recompute`, `faq`, `sources` |

The old anchors map one to one: `regel` to `rule`, `beispiele` to `examples`,
`rueckschau` to `backtest`, `parameter` to `parameters`, `region` to
`implementation`, `dabeibleiben` to `staying-invested`, `fehler` to
`mistakes`, `geschichte` to `history`, `abwaegung` to `tradeoffs`, `kritik` to
`criticism`, `herleitung` to `math`, `faq` stays `faq`, `quellen` to
`sources`. `weiterlesen` has no successor.

`recompute` is new. It takes the last `:::layer compute` box that used to stand
at the end of `herleitung`, behind an introduction and the H3s Eingabe,
Rechenweg, Ausgabe and Für Agenten (in English Input, Calculation, Output and
For agents). The link to the recomputation package stands there; `math` keeps
the formulas and the derivation and links no package.

### Chart classes

`CHART_CLASSES` now holds `rueckschau`, `puls`, `schema`, `backtest` and
`pulse`. On a V5 page the long history carries `class=backtest`, the rule
chart of the last few years `class=pulse`; `rueckschau` and `puls` stay for
pages in the old scheme until HFEA is converted. `schema` is unchanged.

### No `further_reading` in V5

V5 has no chapter `weiterlesen`, and `role: further_reading` on a V5 page is an
error. Every source is a single reference with `role: source` and names in
`supports` at least one V5 anchor. Forums and series that used to stand in
`weiterlesen` become sources of the chapter they back, for the community
history usually `history`.

### Frontmatter example in V5

```markdown
---
slug: sma-trend
status: draft
origin:
  author: "Michael A. Gayed, Charles Bilello"
  year: 2016
  url: "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2741701"
definition_ids:
  eu:
    - SMA__MSCI_WORLD__NETR__255__B0__FR0014010HV4
sources:
  - title: "Leverage for the Long Run"
    author: "Michael A. Gayed, Charles Bilello"
    year: 2016
    url: "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2741701"
    kind: paper
    lang: en
    license: all-rights-reserved
    may_reproduce: false
    role: source
    supports:
      - math
      - sources
  - title: "ZahlGrafs Exzellente Abenteuer"
    author: "ZahlGraf (r/mauerstrassenwetten)"
    year: 2022
    url: "https://redd.it/s71qds"
    kind: forum
    lang: de
    license: unknown
    may_reproduce: false
    role: source
    supports:
      - implementation
      - history
related:
  - hfea
last_reviewed: 2026-09-04
reviewed_by: s1-entwurf
---
```

## What does not belong into the frontmatter and not into the body text

No parameter values (SMA length, buffer, bands, weights), no product key
figures, no computed results. All of that hangs on the definition that
`definition_ids` points to, and is rendered by the website. The frontmatter
refers to the definition, it does not copy it.
