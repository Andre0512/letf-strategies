"""Tests for scripts/check_frontmatter.py (standard library, unittest)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_frontmatter as cf  # noqa: E402

# Slug list for the test cases, deliberately smaller than the real copy.
TEST_SLUGS = {
    "eu": ["HFEA__55_45__QUARTERLY__BANDS5__XS2595672036", "SMA__MSCI_USA__NETR__200__B0__FR0010755611"],
    "us": ["SMA__SPX__GRTR__200__B0__US74347X8645"],
}
TEST_COMMIT = "0" * 40

KNOWN_EU_SLUG = TEST_SLUGS["eu"][1]
KNOWN_US_SLUG = TEST_SLUGS["us"][0]
KNOWN_EU_ISIN = "FR0010755611"
KNOWN_US_ISIN = "US74347X8645"

TEST_PARAMETER_KEYS = ("window", "enter_buffer_pct", "weight.slot_equity")

# Market register for the test cases, built the same way as the committed copy.
TEST_MARKETS = (("eu", ("at", "de", "fr")), ("us", ()))

VALID_SOURCE = """
  - title: "A Quantitative Approach to Tactical Asset Allocation"
    author: "Meb Faber"
    year: 2007
    url: "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=962461"
    kind: paper
    lang: en
    license: all-rights-reserved
    may_reproduce: false
    role: source
    supports:
      - regel
      - herleitung
""".strip("\n")

# A source for further reading; its address must stand in the `weiterlesen` chapter.
FURTHER_READING_URL = "https://example.org/reihe"
FURTHER_READING_SOURCE = f"""
  - title: "Eine lange Reihe zum Weiterlesen"
    author: "Jemand (Forum)"
    year: 2026
    url: "{FURTHER_READING_URL}"
    kind: forum
    lang: de
    license: unknown
    may_reproduce: false
    role: further_reading
    supports:
      - weiterlesen
""".strip("\n")

FURTHER_READING_CHAPTER = f"Ein Satz dazu: [die Reihe]({FURTHER_READING_URL})."

VALID_ORIGIN = """
origin:
  author: "HEDGEFUNDIE"
  year: 2019
  url: "https://www.bogleheads.org/forum/viewtopic.php?t=272007"
""".strip("\n")


def body(anchors: tuple[str, ...] = cf.CORE_ANCHORS, extra: str = "") -> str:
    """Builds a text body with the required chapter anchors."""
    parts = ["# Titel", "", "Text."]
    for anchor in anchors:
        parts += ["", f"## {anchor}", "", "Text."]
    if extra:
        parts += ["", extra]
    return "\n".join(parts) + "\n"


def chapter_body(**chapters: str) -> str:
    """Like `body`, but single chapters get their own text."""
    parts = ["# Titel", "", "Text."]
    for anchor in cf.CORE_ANCHORS:
        parts += ["", f"## {anchor}", "", chapters.get(anchor, "Text.")]
    return "\n".join(parts) + "\n"


def question(title: str) -> str:
    """A question as a `:::faq` container."""
    return f":::faq\n### {title}\n\nAntwort in einem Satz.\n:::"


def faq_block(*parts: str) -> str:
    return "\n\n".join(parts)


def grouped_faq(*, first_lead: str = "", second_title: str = "Im Alltag") -> str:
    """Two categories with two questions each, optionally one sentence under the first."""
    first: list[str] = ["### Einstieg"]
    if first_lead:
        first.append(first_lead)
    first += [question("Was heißt gehebelt?"), question("Mit wie wenig Geld geht das?")]
    second = [
        f"### {second_title}",
        question("Muss ich jeden Tag nachsehen?"),
        question("Was mache ich bei einem verpassten Signal?"),
    ]
    return faq_block(*first, *second)


def document(
    *,
    slug: str = "hfea",
    status: str = "published",
    origin: str = VALID_ORIGIN,
    definition_ids: str = f"  eu:\n    - {KNOWN_EU_SLUG}",
    sources: str = VALID_SOURCE,
    extra: str = "",
    text: str | None = None,
) -> str:
    return (
        "---\n"
        f"slug: {slug}\n"
        f"status: {status}\n"
        f"{origin}\n"
        "definition_ids:\n"
        f"{definition_ids}\n"
        "sources:\n"
        f"{sources}\n"
        "last_reviewed: 2026-08-30\n"
        "reviewed_by: andre\n"
        f"{extra}"
        "---\n\n" + (body() if text is None else text)
    )


class CheckerTestCase(unittest.TestCase):
    """Shared scaffold: content directory in the temp folder, registry in memory."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.content_dir = Path(self._tmp.name) / "strategies"
        self.content_dir.mkdir()
        self.registry = cf.SlugRegistry(
            TEST_SLUGS, source_commit=TEST_COMMIT, path=Path("registry/strategy_preset_slugs.json")
        )
        self.parameter_keys = cf.ParameterKeys(
            TEST_PARAMETER_KEYS, path=Path("registry/strategy_parameter_keys.json")
        )
        self.markets = cf.MarketRegistry(
            TEST_MARKETS, fallback_countries={"eu": "de"}, path=Path("registry/markets.json")
        )

    def write(self, name: str, content: str) -> None:
        (self.content_dir / name).write_text(content, encoding="utf-8")

    def write_pair(self, slug: str = "hfea", **kwargs: str) -> None:
        for language in ("de", "en"):
            self.write(f"{slug}.{language}.md", document(slug=slug, **kwargs))

    def run_check(self) -> cf.Report:
        return cf.run(
            self.content_dir,
            registry=self.registry,
            parameter_keys=self.parameter_keys,
            markets=self.markets,
        )

    def assertError(self, needle: str, report: cf.Report) -> None:
        self.assertTrue(
            any(needle in error for error in report.errors),
            f"'{needle}' not found in {report.errors}",
        )


class FrontmatterTestCase(CheckerTestCase):
    # --- Positive case ---

    def test_valid_pair_passes(self) -> None:
        self.write_pair()
        report = self.run_check()
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])

    def test_main_returns_zero_for_valid_pair(self) -> None:
        self.write_pair()
        self.assertEqual(cf.main(["--content-dir", str(self.content_dir)]), 0)

    # --- Structure of the frontmatter ---

    def test_missing_frontmatter_is_error(self) -> None:
        self.write("hfea.de.md", "# Ohne Frontmatter\n")
        self.write("hfea.en.md", document())
        self.assertError("kein YAML-Frontmatter", self.run_check())

    def test_broken_yaml_is_error(self) -> None:
        self.write("hfea.de.md", "---\nslug: [unclosed\n---\n")
        self.write("hfea.en.md", document())
        self.assertError("kein gültiges YAML", self.run_check())

    def test_missing_required_field_is_error(self) -> None:
        self.write("hfea.de.md", document().replace("reviewed_by: andre\n", ""))
        self.write("hfea.en.md", document())
        self.assertError("reviewed_by", self.run_check())

    def test_unknown_field_is_error(self) -> None:
        self.write_pair(extra="titel: Handgeschrieben\n")
        self.assertError("unbekannte Felder", self.run_check())

    def test_slug_must_match_filename(self) -> None:
        self.write("hfea.de.md", document(slug="sma-trend"))
        self.write("hfea.en.md", document())
        self.assertError("passt nicht zum Dateinamen", self.run_check())

    def test_invalid_status_is_error(self) -> None:
        self.write_pair(status="fertig")
        self.assertError("status='fertig'", self.run_check())

    def test_invalid_date_is_error(self) -> None:
        self.write("hfea.de.md", document().replace("last_reviewed: 2026-08-30", "last_reviewed: 30.08.2026"))
        self.write("hfea.en.md", document())
        self.assertError("last_reviewed", self.run_check())

    # --- origin ---

    def test_missing_origin_is_error(self) -> None:
        self.write_pair(origin="related:\n  - sma-trend")
        self.assertError("origin", self.run_check())

    def test_origin_without_year_is_error(self) -> None:
        self.write_pair(origin='origin:\n  author: "HEDGEFUNDIE"\n  url: "https://example.org/x"')
        self.assertError("origin: Pflichtfelder fehlen: year", self.run_check())

    def test_origin_with_bad_year_is_error(self) -> None:
        self.write_pair(origin='origin:\n  author: "X"\n  year: neunzehn\n  url: "https://example.org/x"')
        self.assertError("origin.year", self.run_check())

    def test_origin_with_bad_url_is_error(self) -> None:
        self.write_pair(origin='origin:\n  author: "X"\n  year: 2019\n  url: "ftp://example.org/x"')
        self.assertError("origin.url", self.run_check())

    # --- de/en pairs ---

    def test_missing_mirror_is_warning_not_error(self) -> None:
        self.write("hfea.de.md", document())
        report = self.run_check()
        self.assertEqual(report.errors, [])
        self.assertTrue(any("hfea.en.md" in warning for warning in report.warnings))

    def test_missing_german_source_is_error(self) -> None:
        self.write("hfea.en.md", document())
        self.assertError("hfea.de.md", self.run_check())

    def test_unexpected_filename_is_error(self) -> None:
        self.write_pair()
        self.write("hfea.fr.md", document())
        self.assertError("Dateiname muss", self.run_check())

    def test_region_filename_is_error_since_s10(self) -> None:
        """Region files are resolved; their content stands in `:::market` blocks."""
        self.write_pair()
        self.write("hfea.eu.de.md", document())
        self.assertError("Dateiname muss '<slug>.<lang>.md' lauten", self.run_check())

    # --- definition_ids ---

    def test_definition_ids_must_be_map(self) -> None:
        self.write_pair(definition_ids=f"  - {KNOWN_EU_SLUG}")
        self.assertError("definition_ids", self.run_check())

    def test_bad_region_key_is_error(self) -> None:
        self.write_pair(definition_ids=f"  europa:\n    - {KNOWN_EU_SLUG}")
        self.assertError("Regionscode", self.run_check())

    def test_placeholder_is_error(self) -> None:
        self.write_pair(status="draft", definition_ids="  eu:\n    - PLACEHOLDER__HFEA__EU")
        self.assertError("Platzhalter", self.run_check())

    def test_unknown_slug_is_error(self) -> None:
        self.write_pair(definition_ids="  eu:\n    - SMA__SPX__NETR__200__B0__XX0000000000")
        self.assertError("steht nicht in der Slug-Liste", self.run_check())

    def test_slug_without_isin_is_error(self) -> None:
        """The canonical_strategy_id without an ISIN is not a slug."""
        self.write_pair(definition_ids="  eu:\n    - SMA__MSCI_USA__NETR__200__B0")
        self.assertError("steht nicht in der Slug-Liste", self.run_check())

    def test_slug_under_wrong_region_is_error(self) -> None:
        self.write_pair(definition_ids=f"  eu:\n    - {KNOWN_US_SLUG}")
        self.assertError("unter Region 'us' geführt", self.run_check())

    def test_error_names_source_commit(self) -> None:
        self.write_pair(definition_ids="  eu:\n    - SMA__SPX__NETR__200__B0__XX0000000000")
        report = self.run_check()
        self.assertTrue(any(TEST_COMMIT[:12] in error for error in report.errors))

    # --- sources ---

    def test_source_missing_field_is_error(self) -> None:
        without_license = "\n".join(line for line in VALID_SOURCE.splitlines() if "license:" not in line)
        self.write_pair(sources=without_license)
        self.assertError("Pflichtfelder fehlen", self.run_check())

    def test_source_without_url_passes(self) -> None:
        """An issuer document without a publicly retrievable address (S7 review)."""
        without_url = "\n".join(line for line in VALID_SOURCE.splitlines() if "url:" not in line)
        self.write_pair(sources=without_url)
        report = self.run_check()
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])

    def test_source_without_title_is_still_an_error(self) -> None:
        without_title = "\n".join(
            line for line in VALID_SOURCE.splitlines() if "title:" not in line
        ).replace("    author:", "  - author:", 1)
        self.write_pair(sources=without_title)
        self.assertError("Pflichtfelder fehlen: title", self.run_check())

    def test_source_with_bad_year_is_error(self) -> None:
        self.write_pair(sources=VALID_SOURCE.replace("year: 2007", "year: zweitausendsieben"))
        self.assertError(".year", self.run_check())

    def test_source_without_supports_is_error(self) -> None:
        without_supports = VALID_SOURCE.split("    supports:")[0].rstrip("\n")
        self.write_pair(sources=without_supports)
        self.assertError("supports", self.run_check())

    def test_supports_with_unknown_anchor_is_error(self) -> None:
        self.write_pair(sources=VALID_SOURCE.replace("      - herleitung", "      - anhang"))
        self.assertError("keine Kapitelanker", self.run_check())

    def test_unknown_license_is_error(self) -> None:
        self.write_pair(sources=VALID_SOURCE.replace("all-rights-reserved", "gemeinfrei"))
        self.assertError("license='gemeinfrei'", self.run_check())

    def test_unknown_kind_is_error(self) -> None:
        self.write_pair(sources=VALID_SOURCE.replace("kind: paper", "kind: tweet"))
        self.assertError("kind='tweet'", self.run_check())

    def test_forum_kind_is_allowed(self) -> None:
        self.write_pair(sources=VALID_SOURCE.replace("kind: paper", "kind: forum"))
        self.assertEqual(self.run_check().errors, [])

    def test_restricted_license_forbids_reproduction(self) -> None:
        self.write_pair(sources=VALID_SOURCE.replace("may_reproduce: false", "may_reproduce: true"))
        self.assertError("erlaubt keine Reproduktion", self.run_check())

    def test_permissive_license_allows_reproduction(self) -> None:
        permissive = VALID_SOURCE.replace("all-rights-reserved", "cc-by-4.0").replace(
            "may_reproduce: false", "may_reproduce: true"
        )
        self.write_pair(sources=permissive)
        self.assertEqual(self.run_check().errors, [])

    def test_bad_url_is_error(self) -> None:
        self.write_pair(sources=VALID_SOURCE.replace("https://papers.ssrn.com", "ftp://papers.ssrn.com"))
        self.assertError(".url", self.run_check())

    # --- role and the `weiterlesen` chapter (contract S10) ---

    def test_source_without_role_is_error(self) -> None:
        without_role = VALID_SOURCE.replace("    role: source\n", "")
        self.write_pair(sources=without_role)
        self.assertError("Pflichtfelder fehlen: role", self.run_check())

    def test_unknown_role_is_error(self) -> None:
        self.write_pair(sources=VALID_SOURCE.replace("role: source", "role: literatur"))
        self.assertError("role='literatur'", self.run_check())

    def test_linked_further_reading_source_passes(self) -> None:
        self.write_pair(
            sources=VALID_SOURCE + "\n" + FURTHER_READING_SOURCE,
            text=chapter_body(weiterlesen=FURTHER_READING_CHAPTER),
        )
        report = self.run_check()
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])

    def test_further_reading_source_without_a_link_is_error(self) -> None:
        self.write_pair(sources=VALID_SOURCE + "\n" + FURTHER_READING_SOURCE)
        self.assertError("steht aber nicht als Link im Kapitel 'weiterlesen'", self.run_check())

    def test_a_link_in_another_chapter_does_not_count(self) -> None:
        self.write_pair(
            sources=VALID_SOURCE + "\n" + FURTHER_READING_SOURCE,
            text=chapter_body(quellen=FURTHER_READING_CHAPTER),
        )
        self.assertError("steht aber nicht als Link im Kapitel 'weiterlesen'", self.run_check())

    def test_further_reading_source_needs_a_url(self) -> None:
        without_url = "\n".join(
            line for line in FURTHER_READING_SOURCE.splitlines() if "url:" not in line
        )
        self.write_pair(
            sources=VALID_SOURCE + "\n" + without_url,
            text=chapter_body(weiterlesen=FURTHER_READING_CHAPTER),
        )
        self.assertError("braucht eine url", self.run_check())

    def test_source_role_needs_a_supported_chapter(self) -> None:
        empty_supports = VALID_SOURCE.replace("      - regel\n      - herleitung", "      []")
        self.write_pair(sources=empty_supports)
        self.assertError("role='source' belegt mindestens ein Kapitel", self.run_check())

    # --- Directory ---

    def test_missing_directory_is_error(self) -> None:
        report = cf.run(
            self.content_dir / "gibtsnicht", registry=self.registry, parameter_keys=self.parameter_keys
        )
        self.assertError("existiert nicht", report)

    def test_empty_directory_is_error(self) -> None:
        self.assertError("keine Content-Dateien", self.run_check())


class AnchorTestCase(CheckerTestCase):
    def test_missing_anchor_is_error(self) -> None:
        without_faq = tuple(anchor for anchor in cf.CORE_ANCHORS if anchor != "faq")
        self.write_pair(text=body(without_faq))
        self.assertError("Kapitelanker fehlen: faq", self.run_check())

    def test_unknown_heading_is_error(self) -> None:
        self.write_pair(text=body() + "\n## anhang\n\nText.\n")
        self.assertError("unbekannte H2-Überschriften: anhang", self.run_check())

    def test_history_and_critique_stand_before_faq(self) -> None:
        """Since S10: `geschichte` instead of `herkunft`, then `kritik`, then the FAQ."""
        self.assertEqual(
            cf.CORE_ANCHORS.index("geschichte") + 1,
            cf.CORE_ANCHORS.index("kritik"),
        )
        self.assertEqual(
            cf.CORE_ANCHORS.index("kritik") + 1,
            cf.CORE_ANCHORS.index("faq"),
        )
        self.assertNotIn("herkunft", cf.CORE_ANCHORS)

    def test_missing_history_is_error(self) -> None:
        without_history = tuple(anchor for anchor in cf.CORE_ANCHORS if anchor != "geschichte")
        self.write_pair(text=body(without_history))
        self.assertError("Kapitelanker fehlen: geschichte", self.run_check())

    def test_further_reading_stands_before_sources(self) -> None:
        """Separate since S10: the places for further reading, then the individual references."""
        self.assertEqual(
            cf.CORE_ANCHORS.index("weiterlesen") + 1,
            cf.CORE_ANCHORS.index("quellen"),
        )
        self.assertEqual(cf.CORE_ANCHORS[-1], "quellen")

    def test_missing_further_reading_is_error(self) -> None:
        without_further_reading = tuple(anchor for anchor in cf.CORE_ANCHORS if anchor != "weiterlesen")
        self.write_pair(text=body(without_further_reading))
        self.assertError("Kapitelanker fehlen: weiterlesen", self.run_check())

    def test_missing_critique_is_error(self) -> None:
        without_critique = tuple(anchor for anchor in cf.CORE_ANCHORS if anchor != "kritik")
        self.write_pair(text=body(without_critique))
        self.assertError("Kapitelanker fehlen: kritik", self.run_check())

    def test_heading3_outside_faq_is_no_group(self) -> None:
        """The stations in `geschichte` and `kritik` carry H3 without being a group."""
        stations = "### 2016: Das Paper\n\nText.\n\n### 2022: Die Reihe\n\nText."
        self.write_pair(text=chapter_body(geschichte=stations, kritik=stations))
        self.assertEqual(self.run_check().errors, [])

    def test_wrong_order_is_error(self) -> None:
        swapped = (cf.CORE_ANCHORS[1], cf.CORE_ANCHORS[0]) + cf.CORE_ANCHORS[2:]
        self.write_pair(text=body(swapped))
        self.assertError("falschen Reihenfolge", self.run_check())

    def test_headings_inside_containers_are_ignored(self) -> None:
        extra = ":::layer sources\n\n## regel\n\nText.\n\n:::"
        self.write_pair(text=body(extra=extra))
        self.assertEqual(self.run_check().errors, [])


class LayerOnlyChapterTestCase(CheckerTestCase):
    """No chapter may stand entirely in `:::layer` boxes (S11 addendum)."""

    BOX = ":::layer compute\n\n$$\nx = 1\n$$\n\n:::"

    def test_a_chapter_only_in_boxes_is_error(self) -> None:
        self.write_pair(text=chapter_body(herleitung=self.BOX))
        self.assertError("das Kapitel 'herleitung' steht ganz in ':::layer'-Kästen", self.run_check())

    def test_several_boxes_are_no_better_than_one(self) -> None:
        self.write_pair(text=chapter_body(herleitung=f"{self.BOX}\n\n{self.BOX}"))
        self.assertError("steht ganz in ':::layer'-Kästen", self.run_check())

    def test_text_beside_the_box_passes(self) -> None:
        self.write_pair(text=chapter_body(herleitung=f"Die Formel selbst.\n\n{self.BOX}"))
        self.assertEqual(self.run_check().errors, [])

    def test_another_container_beside_the_box_passes(self) -> None:
        chart = ":::chart type=main class=puls\n\nWas die Kurven bedeuten.\n\n:::"
        self.write_pair(text=chapter_body(herleitung=f"{self.BOX}\n\n{chart}"))
        self.assertEqual(self.run_check().errors, [])

    def test_a_market_block_is_transparent(self) -> None:
        """A market block hides nothing: its text counts as visible."""
        wrapped = market("eu", "Für Europa gilt das so.") + "\n\n" + market("us", "Und so in den USA.")
        self.write_pair(text=chapter_body(herleitung=f"{self.BOX}\n\n{wrapped}"))
        self.assertEqual(self.run_check().errors, [])

    def test_a_box_inside_a_market_block_is_still_only_a_box(self) -> None:
        self.write_pair(text=chapter_body(herleitung=market("eu", self.BOX) + "\n\n" + market("us", self.BOX)))
        self.assertError("steht ganz in ':::layer'-Kästen", self.run_check())


class ContainerTestCase(CheckerTestCase):
    def valid_containers(self) -> str:
        return (
            ":::layer compute\n\nText.\n\n:::\n\n"
            ":::parameter key=window\n\nText.\n\n:::\n\n"
            ":::faq\n\n### Frage?\n\nAntwort.\n\n:::\n\n"
            f":::example from=2020-02-19 to=2020-04-30 isin={KNOWN_EU_ISIN}\n\nText.\n\n:::"
        )

    def test_valid_containers_pass(self) -> None:
        self.write_pair(text=body(extra=self.valid_containers()))
        self.assertEqual(self.run_check().errors, [])

    def test_unknown_container_is_error(self) -> None:
        self.write_pair(text=body(extra=":::kasten\n\nText.\n\n:::"))
        self.assertError("unbekannter Container", self.run_check())

    def test_unclosed_container_is_error(self) -> None:
        self.write_pair(text=body(extra=":::layer compute\n\nText.\n"))
        self.assertError("wird nicht durch", self.run_check())

    def test_stray_close_is_error(self) -> None:
        self.write_pair(text=body(extra="Text.\n\n:::\n"))
        self.assertError("ohne offenen Container", self.run_check())

    def test_nested_container_is_error(self) -> None:
        nested = ":::layer compute\n\n:::parameter key=window\n\nText.\n\n:::\n\n:::"
        self.write_pair(text=body(extra=nested))
        self.assertError("darf andere Container umschließen", self.run_check())

    def test_empty_container_is_error(self) -> None:
        self.write_pair(text=body(extra=":::layer compute\n\n:::"))
        self.assertError("ist leer", self.run_check())

    def test_unknown_layer_is_error(self) -> None:
        self.write_pair(text=body(extra=":::layer verstehen\n\nText.\n\n:::"))
        self.assertError(":::layer braucht eine Ebene", self.run_check())

    def test_parameter_without_key_is_error(self) -> None:
        self.write_pair(text=body(extra=":::parameter\n\nText.\n\n:::"))
        self.assertError("braucht key=", self.run_check())

    def test_unknown_parameter_key_is_error(self) -> None:
        self.write_pair(text=body(extra=":::parameter key=zauberzahl\n\nText.\n\n:::"))
        self.assertError("steht nicht in der Deskriptor-Liste", self.run_check())

    def test_faq_without_question_is_error(self) -> None:
        self.write_pair(text=body(extra=":::faq\n\nAntwort ohne Frage.\n\n:::"))
        self.assertError("Frage als H3", self.run_check())

    def test_faq_with_arguments_is_error(self) -> None:
        self.write_pair(text=body(extra=":::faq key=window\n\n### Frage?\n\nText.\n\n:::"))
        self.assertError("nimmt keine Angaben", self.run_check())

    def test_example_missing_attribute_is_error(self) -> None:
        self.write_pair(text=body(extra=":::example from=2020-02-19 to=2020-04-30\n\nText.\n\n:::"))
        self.assertError("Angaben fehlen: isin", self.run_check())

    def test_example_with_bad_date_is_error(self) -> None:
        self.write_pair(
            text=body(extra=f":::example from=19.02.2020 to=2020-04-30 isin={KNOWN_EU_ISIN}\n\nText.\n\n:::")
        )
        self.assertError("ist kein Datum", self.run_check())

    def test_example_with_reversed_range_is_error(self) -> None:
        self.write_pair(
            text=body(extra=f":::example from=2020-04-30 to=2020-02-19 isin={KNOWN_EU_ISIN}\n\nText.\n\n:::")
        )
        self.assertError("from muss vor to liegen", self.run_check())

    def test_example_with_foreign_isin_is_error(self) -> None:
        self.write_pair(
            text=body(extra=f":::example from=2020-02-19 to=2020-04-30 isin={KNOWN_US_ISIN}\n\nText.\n\n:::")
        )
        self.assertError("kommt in den definition_ids dieser Datei nicht vor", self.run_check())

    # --- Formulas ---

    def test_balanced_formula_passes(self) -> None:
        self.write_pair(text=body(extra=":::layer compute\n\n$$\nx = y\n$$\n\n:::"))
        self.assertEqual(self.run_check().errors, [])

    def test_unbalanced_formula_is_error(self) -> None:
        self.write_pair(text=body(extra=":::layer compute\n\n$$\nx = y\n\n:::"))
        self.assertError("unpaariger Formelblock", self.run_check())

    def test_empty_formula_is_error(self) -> None:
        self.write_pair(text=body(extra=":::layer compute\n\n$$\n$$\n\n:::"))
        self.assertError("leerer Formelblock", self.run_check())


class ChartContainerTestCase(CheckerTestCase):
    def test_valid_charts_pass(self) -> None:
        charts = (
            ":::chart type=main class=puls\n\nLesehilfe.\n\n:::\n\n"
            ":::chart type=backtest class=rueckschau\n\nLesehilfe.\n\n:::\n\n"
            ":::chart type=distribution class=rueckschau\n\nLesehilfe.\n\n:::\n\n"
            ":::chart type=panorama class=rueckschau parameter=window metric=signals\n\nLesehilfe.\n\n:::\n\n"
            ":::chart type=heatmap class=rueckschau layer=compute\n\nLesehilfe.\n\n:::"
        )
        self.write_pair(text=body(extra=charts))
        self.assertEqual(self.run_check().errors, [])

    def test_v5_page_with_english_anchors_passes(self) -> None:
        sources = VALID_SOURCE.replace("- regel", "- rule").replace("- herleitung", "- math")
        charts = ":::chart type=main class=pulse\n\nLesehilfe.\n\n:::\n\n:::chart type=backtest class=backtest\n\nLesehilfe.\n\n:::"
        self.write_pair(sources=sources, text=body(cf.V5_ANCHORS, extra=charts))
        report = self.run_check()
        self.assertEqual(report.errors, [])

    def test_v5_page_checks_the_v5_order(self) -> None:
        swapped = ("examples", "rule") + cf.V5_ANCHORS[2:]
        sources = VALID_SOURCE.replace("- regel", "- rule").replace("- herleitung", "- math")
        self.write_pair(sources=sources, text=body(swapped))
        self.assertError("falschen Reihenfolge", self.run_check())

    def test_v5_page_rejects_old_anchor_in_supports(self) -> None:
        self.write_pair(text=body(cf.V5_ANCHORS))
        self.assertError("keine Kapitelanker: regel, herleitung", self.run_check())

    def test_v5_page_rejects_further_reading(self) -> None:
        sources = VALID_SOURCE.replace("- regel", "- rule").replace("- herleitung", "- math")
        reading = FURTHER_READING_SOURCE.replace("- weiterlesen", "- sources")
        self.write_pair(sources=sources + "\n" + reading, text=body(cf.V5_ANCHORS))
        self.assertError("gibt es in Struktur V5 nicht mehr", self.run_check())

    def test_page_mixing_both_schemes_is_error(self) -> None:
        mixed = ("rule",) + cf.CORE_ANCHORS[1:]
        self.write_pair(text=body(mixed))
        self.assertError("Kapitelanker fehlen", self.run_check())

    def test_source_market_passes(self) -> None:
        sources = VALID_SOURCE.replace("    role: source", "    role: source\n    market: de")
        self.write_pair(sources=sources)
        self.assertEqual(self.run_check().errors, [])

    def test_unknown_source_market_is_error(self) -> None:
        sources = VALID_SOURCE.replace("    role: source", "    role: source\n    market: xx")
        self.write_pair(sources=sources)
        self.assertError("market: 'xx' steht nicht im Marktregister", self.run_check())

    def test_regulation_without_market_warns(self) -> None:
        sources = VALID_SOURCE.replace("kind: paper", "kind: regulation")
        self.write_pair(sources=sources)
        report = self.run_check()
        self.assertEqual(report.errors, [])
        self.assertTrue(any("Rechtsquelle ohne market" in warning for warning in report.warnings))

    def test_short_summary_and_factsheet_pass(self) -> None:
        extra = (
            "short_summary: >-\n"
            "  Die Regel vergleicht jeden Tag einen Index mit seinem Durchschnitt. Liegt er darueber, bist du"
            " investiert. Liegt er darunter, wartest du ab.\n"
            "factsheet:\n"
            "  - label: Signalindex\n    value: MSCI ACWI\n"
            "  - label: Linie\n    value: Durchschnitt der letzten 200 Schlusskurse\n"
            "  - label: Steuern\n    value: siehe Umsetzung\n    ref: region\n"
        )
        self.write_pair(extra=extra)
        self.assertEqual(self.run_check().errors, [])

    def test_short_summary_needs_sentences(self) -> None:
        self.write_pair(extra="short_summary: Nur ein einziger Satz, der zwar lang genug ist, aber eben nur einer bleibt.\n")
        self.assertError("short_summary braucht 3 bis 5 Sätze", self.run_check())

    def test_factsheet_ref_must_be_anchor(self) -> None:
        extra = (
            "factsheet:\n"
            "  - label: A\n    value: a\n  - label: B\n    value: b\n"
            "  - label: C\n    value: c\n    ref: nirgends\n"
        )
        self.write_pair(extra=extra)
        self.assertError("ref 'nirgends' ist kein Kapitelanker", self.run_check())

    def test_longterm_chart_passes(self) -> None:
        chart = ":::chart type=longterm class=rueckschau\n\nLesehilfe.\n\n:::"
        self.write_pair(text=body(extra=chart))
        self.assertEqual(self.run_check().errors, [])

    def test_chart_without_type_is_error(self) -> None:
        self.write_pair(text=body(extra=":::chart class=puls\n\nText.\n\n:::"))
        self.assertError("braucht type=", self.run_check())

    def test_unknown_chart_type_is_error(self) -> None:
        self.write_pair(text=body(extra=":::chart type=kerzen class=puls\n\nText.\n\n:::"))
        self.assertError("type='kerzen'", self.run_check())

    def test_chart_without_class_is_error(self) -> None:
        self.write_pair(text=body(extra=":::chart type=main\n\nText.\n\n:::"))
        self.assertError("braucht class=", self.run_check())

    def test_unknown_chart_class_is_error(self) -> None:
        self.write_pair(text=body(extra=":::chart type=main class=tracker\n\nText.\n\n:::"))
        self.assertError("class='tracker'", self.run_check())

    def test_panorama_without_parameter_is_error(self) -> None:
        self.write_pair(text=body(extra=":::chart type=panorama class=rueckschau\n\nText.\n\n:::"))
        self.assertError("braucht parameter=", self.run_check())

    def test_currency_panorama_without_parameter_is_error(self) -> None:
        self.write_pair(text=body(extra=":::chart type=currency-panorama class=rueckschau\n\nText.\n\n:::"))
        self.assertError("braucht parameter=", self.run_check())

    def test_unknown_chart_parameter_is_error(self) -> None:
        self.write_pair(
            text=body(extra=":::chart type=panorama class=rueckschau parameter=zauberzahl\n\nText.\n\n:::")
        )
        self.assertError("steht nicht in der Deskriptor-Liste", self.run_check())

    def test_unknown_chart_metric_is_error(self) -> None:
        self.write_pair(
            text=body(extra=":::chart type=main class=puls metric=sharpe\n\nText.\n\n:::")
        )
        self.assertError("metric='sharpe'", self.run_check())

    def test_chart_layer_takes_only_compute(self) -> None:
        self.write_pair(text=body(extra=":::chart type=main class=puls layer=sources\n\nText.\n\n:::"))
        self.assertError("layer nimmt nur", self.run_check())

    def test_unknown_chart_attribute_is_error(self) -> None:
        self.write_pair(text=body(extra=":::chart type=main class=puls hoehe=400\n\nText.\n\n:::"))
        self.assertError("unbekannte Angaben", self.run_check())

    def test_empty_chart_is_error(self) -> None:
        self.write_pair(text=body(extra=":::chart type=main class=puls\n\n:::"))
        self.assertError("ist leer", self.run_check())


class WordingTestCase(CheckerTestCase):
    def test_discouraged_word_in_understand_layer_is_warning(self) -> None:
        self.write_pair(text=body(extra="Das lohnt sich für dich."))
        report = self.run_check()
        self.assertEqual(report.errors, [])
        self.assertTrue(any("lohnt sich" in warning for warning in report.warnings))

    def test_same_word_inside_compute_layer_is_silent(self) -> None:
        self.write_pair(text=body(extra=":::layer compute\n\nDas ist keine Wahrscheinlichkeit.\n\n:::"))
        report = self.run_check()
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])

    def test_chart_body_on_the_compute_layer_is_silent(self) -> None:
        self.write_pair(
            text=body(extra=":::chart type=heatmap class=rueckschau layer=compute\n\nKeine Trefferquote.\n\n:::")
        )
        self.assertEqual(self.run_check().warnings, [])

    def test_wording_inside_a_parameter_card_is_warned(self) -> None:
        self.write_pair(text=body(extra=":::parameter key=window\n\nDas steht in der Definition.\n\n:::"))
        report = self.run_check()
        self.assertTrue(any("Definition" in warning for warning in report.warnings))

    def test_wording_inside_a_pulse_chart_is_warned(self) -> None:
        self.write_pair(text=body(extra=":::chart type=main class=puls\n\nEine Empfehlung dazu.\n\n:::"))
        report = self.run_check()
        self.assertTrue(any("Empfehlung" in warning for warning in report.warnings))

    def test_english_wording_is_warned_too(self) -> None:
        self.write_pair(text=body(extra="This is the honest yardstick."))
        report = self.run_check()
        self.assertTrue(any("honest" in warning for warning in report.warnings))


class FaqGroupTestCase(CheckerTestCase):
    """The categories in the `faq` chapter (contract S7)."""

    def assertWarning(self, needle: str, report: cf.Report) -> None:
        self.assertTrue(
            any(needle in warning for warning in report.warnings),
            f"'{needle}' not found in {report.warnings}",
        )

    # --- Positive cases ---

    def test_grouped_faq_passes(self) -> None:
        self.write_pair(text=chapter_body(faq=grouped_faq()))
        report = self.run_check()
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])

    def test_faq_without_categories_still_passes(self) -> None:
        self.write_pair(text=chapter_body(faq=faq_block(question("Was heißt gehebelt?"), question("Und sonst?"))))
        report = self.run_check()
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])

    def test_one_sentence_under_a_category_passes(self) -> None:
        lead = "Diese Fragen kommen vor dem ersten Kauf,\nund sie kommen fast immer."
        self.write_pair(text=chapter_body(faq=grouped_faq(first_lead=lead)))
        report = self.run_check()
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])

    def test_heading_outside_the_faq_chapter_is_no_category(self) -> None:
        self.write_pair(text=chapter_body(regel="### Eine Zwischenüberschrift\n\nText.", faq=grouped_faq()))
        report = self.run_check()
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])

    # --- Negative cases ---

    def test_question_before_the_first_category_is_error(self) -> None:
        self.write_pair(text=chapter_body(faq=faq_block(question("Frage ohne Gruppe?")) + "\n\n" + grouped_faq()))
        self.assertError("vor der ersten Kategorie", self.run_check())

    def test_duplicate_category_title_is_error(self) -> None:
        self.write_pair(text=chapter_body(faq=grouped_faq(second_title="Einstieg")))
        self.assertError("steht schon in Zeile", self.run_check())

    def test_category_without_a_question_is_error(self) -> None:
        self.write_pair(text=chapter_body(faq=grouped_faq() + "\n\n### Steuern"))
        self.assertError("führt keine Frage", self.run_check())

    def test_single_question_category_is_error(self) -> None:
        self.write_pair(text=chapter_body(faq=grouped_faq() + "\n\n### Steuern\n\n" + question("Was kostet das?")))
        self.assertError("erreicht den Markt 'eu' mit nur 1 Frage", self.run_check())

    def test_single_question_category_is_only_a_warning_while_the_switch_is_off(self) -> None:
        """The switch from the first part of S7; it carried the addendum."""
        self.write_pair(text=chapter_body(faq=grouped_faq() + "\n\n### Steuern\n\n" + question("Was kostet das?")))
        with unittest.mock.patch.object(cf, "GROUP_MINIMUM_IS_ERROR", False):
            report = self.run_check()
        self.assertEqual(report.errors, [])
        self.assertWarning("erreicht den Markt 'eu' mit nur 1 Frage", report)

    def test_two_paragraphs_under_a_category_are_error(self) -> None:
        self.write_pair(text=chapter_body(faq=grouped_faq(first_lead="Ein Satz.\n\nUnd noch einer.")))
        self.assertError("mehr als ein Absatz", self.run_check())

    def test_prose_between_two_questions_is_error(self) -> None:
        faq = grouped_faq().replace(
            question("Mit wie wenig Geld geht das?"),
            "Ein Satz zwischen den Fragen.\n\n" + question("Mit wie wenig Geld geht das?"),
        )
        self.write_pair(text=chapter_body(faq=faq))
        self.assertError("Fließtext zwischen den Fragen", self.run_check())

    # --- The language pair ---

    def test_different_number_of_categories_is_error(self) -> None:
        self.write("hfea.de.md", document(text=chapter_body(faq=grouped_faq())))
        self.write(
            "hfea.en.md",
            document(text=chapter_body(faq=grouped_faq() + "\n\n### Taxes\n\n" + question("Erste?") + "\n\n" + question("Zweite?"))),
        )
        self.assertError("zählen verschieden", self.run_check())

    def test_different_number_of_questions_per_category_is_warning(self) -> None:
        self.write("hfea.de.md", document(text=chapter_body(faq=grouped_faq())))
        self.write(
            "hfea.en.md",
            document(text=chapter_body(faq=grouped_faq() + "\n\n" + question("Eine dritte Frage?"))),
        )
        report = self.run_check()
        self.assertEqual(report.errors, [])
        self.assertWarning("die deutsche", report)


def market(codes: str, *parts: str) -> str:
    """A `:::market` container around arbitrary content."""
    body_text = "\n\n".join(parts) if parts else "Text für diesen Markt."
    return f":::market {codes}\n\n{body_text}\n\n:::"


class MarketContainerTestCase(CheckerTestCase):
    """The `:::market` container (contract S10)."""

    # --- Positive cases ---

    def test_market_block_passes(self) -> None:
        self.write_pair(text=chapter_body(region="Text.\n\n" + market("de")))
        report = self.run_check()
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])

    def test_several_codes_pass(self) -> None:
        self.write_pair(text=chapter_body(region="Text.\n\n" + market("de,eu")))
        self.assertEqual(self.run_check().errors, [])

    def test_country_and_region_blocks_side_by_side_pass(self) -> None:
        chapter = "Text.\n\n" + market("eu") + "\n\n" + market("de") + "\n\n" + market("us")
        self.write_pair(text=chapter_body(region=chapter))
        self.assertEqual(self.run_check().errors, [])

    def test_market_may_wrap_other_containers(self) -> None:
        wrapped = market(
            "eu",
            ":::parameter key=window\n\nText.\n\n:::",
            ":::chart type=main class=puls\n\nLesehilfe.\n\n:::",
            ":::layer sources\n\nWas die Quelle belegt.\n\n:::",
            f":::example from=2020-02-19 to=2020-04-30 isin={KNOWN_EU_ISIN}\n\nText.\n\n:::",
        )
        self.write_pair(text=chapter_body(region="Text.\n\n" + wrapped))
        self.assertEqual(self.run_check().errors, [])

    def test_chapter_only_in_market_blocks_passes_with_every_region(self) -> None:
        chapter = market("eu") + "\n\n" + market("us")
        self.write_pair(text=chapter_body(region=chapter))
        self.assertEqual(self.run_check().errors, [])

    def test_code_order_inside_a_block_does_not_split_the_pair(self) -> None:
        self.write("hfea.de.md", document(text=chapter_body(region="Text.\n\n" + market("de,eu"))))
        self.write("hfea.en.md", document(text=chapter_body(region="Text.\n\n" + market("eu,de"))))
        self.assertEqual(self.run_check().errors, [])

    def test_market_in_a_faq_group_counts_towards_the_minimum(self) -> None:
        faq = faq_block(
            "### Steuern",
            question("Was kostet mich das an Steuern?"),
            market("eu", question("Zählt die Vorabpauschale mit?")),
            market("us", question("Was macht die Wash-Sale-Regel?")),
        )
        self.write_pair(text=chapter_body(faq=faq))
        report = self.run_check()
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])

    def test_market_may_wrap_a_whole_faq_group(self) -> None:
        group = market(
            "de",
            "### Steuern",
            question("Was kostet mich das an Steuern?"),
            question("Zählt die Vorabpauschale mit?"),
        )
        self.write_pair(text=chapter_body(faq=grouped_faq() + "\n\n" + group))
        report = self.run_check()
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])

    def test_wording_inside_a_market_block_is_still_warned(self) -> None:
        self.write_pair(text=chapter_body(region="Text.\n\n" + market("de", "Das lohnt sich für dich.")))
        report = self.run_check()
        self.assertEqual(report.errors, [])
        self.assertTrue(any("lohnt sich" in warning for warning in report.warnings))

    def test_compute_layer_inside_a_market_block_stays_silent(self) -> None:
        wrapped = market("de", ":::layer compute\n\nDas ist keine Wahrscheinlichkeit.\n\n:::")
        self.write_pair(text=chapter_body(region="Text.\n\n" + wrapped))
        report = self.run_check()
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])

    def test_heading2_after_a_market_block_is_still_an_anchor(self) -> None:
        """The nesting counter must not swallow the chapters."""
        without_faq = tuple(anchor for anchor in cf.CORE_ANCHORS if anchor != "faq")
        self.write_pair(text=body(without_faq, extra=market("eu")))
        self.assertError("Kapitelanker fehlen: faq", self.run_check())

    # --- Negative cases: the attribute ---

    def test_market_without_codes_is_error(self) -> None:
        self.write_pair(text=chapter_body(region="Text.\n\n:::market\n\nText.\n\n:::"))
        self.assertError("braucht mindestens einen Marktcode", self.run_check())

    def test_unknown_code_is_error(self) -> None:
        self.write_pair(text=chapter_body(region="Text.\n\n" + market("jp")))
        self.assertError("'jp' steht nicht im Marktregister", self.run_check())

    def test_space_after_the_comma_is_error(self) -> None:
        self.write_pair(text=chapter_body(region="Text.\n\n:::market de, eu\n\nText.\n\n:::"))
        self.assertError("kommagetrennt ohne Leerzeichen", self.run_check())

    def test_repeated_code_is_error(self) -> None:
        self.write_pair(text=chapter_body(region="Text.\n\n" + market("de,de")))
        self.assertError("steht zweimal in derselben Angabe", self.run_check())

    # --- Negative cases: the nesting ---

    def test_market_inside_market_is_error(self) -> None:
        nested = ":::market eu\n\n" + market("de") + "\n\n:::"
        self.write_pair(text=chapter_body(region="Text.\n\n" + nested))
        self.assertError("Markt-Blöcke verschachteln nicht", self.run_check())

    def test_market_inside_another_container_is_error(self) -> None:
        nested = ":::layer compute\n\n" + market("de") + "\n\n:::"
        self.write_pair(text=chapter_body(region="Text.\n\n" + nested))
        self.assertError("':::market' öffnet innerhalb von ':::layer'", self.run_check())

    def test_unclosed_market_is_error(self) -> None:
        self.write_pair(text=chapter_body(region="Text.\n\n:::market de\n\nText.\n"))
        self.assertError(":::market wird nicht durch", self.run_check())

    def test_empty_market_is_error(self) -> None:
        self.write_pair(text=chapter_body(region="Text.\n\n:::market de\n\n:::"))
        self.assertError(":::market ist leer", self.run_check())

    # --- Negative cases: no chapter empty for a region ---

    def test_chapter_only_for_one_region_is_error(self) -> None:
        self.write_pair(text=chapter_body(region=market("eu")))
        self.assertError("lässt us leer", self.run_check())

    def test_country_code_alone_does_not_cover_its_region(self) -> None:
        chapter = market("de") + "\n\n" + market("us")
        self.write_pair(text=chapter_body(region=chapter))
        self.assertError("lässt eu leer", self.run_check())

    def test_chapter_with_a_container_outside_the_market_blocks_passes(self) -> None:
        chapter = ":::layer sources\n\nWas die Quelle belegt.\n\n:::\n\n" + market("eu")
        self.write_pair(text=chapter_body(region=chapter))
        self.assertEqual(self.run_check().errors, [])

    # --- Negative cases: the language pair ---

    def test_different_codes_in_the_pair_are_error(self) -> None:
        self.write("hfea.de.md", document(text=chapter_body(region="Text.\n\n" + market("de"))))
        self.write("hfea.en.md", document(text=chapter_body(region="Text.\n\n" + market("us"))))
        self.assertError("verschiedene Markt-Blöcke", self.run_check())

    def test_different_order_in_the_pair_is_error(self) -> None:
        german = "Text.\n\n" + market("eu") + "\n\n" + market("us")
        english = "Text.\n\n" + market("us") + "\n\n" + market("eu")
        self.write("hfea.de.md", document(text=chapter_body(region=german)))
        self.write("hfea.en.md", document(text=chapter_body(region=english)))
        self.assertError("verschiedene Markt-Blöcke", self.run_check())

    def test_extra_block_in_the_mirror_is_error(self) -> None:
        german = "Text.\n\n" + market("eu")
        english = "Text.\n\n" + market("eu") + "\n\n" + market("us")
        self.write("hfea.de.md", document(text=chapter_body(region=german)))
        self.write("hfea.en.md", document(text=chapter_body(region=english)))
        self.assertError("verschiedene Markt-Blöcke", self.run_check())

    def test_same_blocks_in_another_chapter_are_error(self) -> None:
        self.write("hfea.de.md", document(text=chapter_body(region="Text.\n\n" + market("de"))))
        self.write("hfea.en.md", document(text=chapter_body(fehler="Text.\n\n" + market("de"))))
        report = self.run_check()
        self.assertError("das Kapitel 'region' führt verschiedene Markt-Blöcke", report)
        self.assertError("das Kapitel 'fehler' führt verschiedene Markt-Blöcke", report)


class FaqMarketMinimumTestCase(CheckerTestCase):
    """The minimum per group counts per market, not over the sum (S10 review)."""

    def assertWarning(self, needle: str, report: cf.Report) -> None:
        self.assertTrue(
            any(needle in warning for warning in report.warnings),
            f"'{needle}' not found in {report.warnings}",
        )

    def test_two_questions_for_different_markets_do_not_add_up(self) -> None:
        faq = grouped_faq() + "\n\n" + faq_block(
            "### Steuern",
            market("de", question("Was kostet mich das an Steuern?")),
            market("us", question("Was macht die Wash-Sale-Regel?")),
        )
        self.write_pair(text=chapter_body(faq=faq))
        report = self.run_check()
        self.assertError("erreicht den Markt 'eu' mit nur 1 Frage", report)
        self.assertError("erreicht den Markt 'us' mit nur 1 Frage", report)

    def test_group_with_only_market_questions_is_empty_for_the_other_market(self) -> None:
        """The H3 stands unconditionally; all questions lie in one market block."""
        faq = grouped_faq() + "\n\n" + faq_block(
            "### Steuern",
            market("de", question("Was kostet mich das?"), question("Und die Vorabpauschale?")),
        )
        self.write_pair(text=chapter_body(faq=faq))
        self.assertError("erreicht den Markt 'us' mit nur 0 Fragen", self.run_check())

    def test_a_wholly_wrapped_group_is_skipped_for_other_markets(self) -> None:
        """If the H3 already stands in the block, there is no category for other markets."""
        wrapped = market(
            "de",
            "### Steuern",
            question("Was kostet mich das?"),
            question("Und die Vorabpauschale?"),
        )
        self.write_pair(text=chapter_body(faq=grouped_faq() + "\n\n" + wrapped))
        report = self.run_check()
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])

    def test_a_country_without_fallback_is_only_a_warning(self) -> None:
        faq = grouped_faq() + "\n\n" + faq_block(
            "### Steuern",
            market("de", question("Was kostet mich das?"), question("Und die Vorabpauschale?")),
            market("us", question("Wash-Sale?"), question("Und die Haltedauer?")),
        )
        self.write_pair(text=chapter_body(faq=faq))
        report = self.run_check()
        self.assertEqual(report.errors, [])
        self.assertWarning("erreicht den Markt 'at' mit nur 0 Fragen", report)
        self.assertWarning("erreicht den Markt 'fr' mit nur 0 Fragen", report)

    def test_a_region_block_reaches_its_countries(self) -> None:
        faq = grouped_faq() + "\n\n" + faq_block(
            "### Steuern",
            question("Was kostet mich das?"),
            market("eu", question("Und die Vorabpauschale?")),
            market("us", question("Wash-Sale?")),
        )
        self.write_pair(text=chapter_body(faq=faq))
        report = self.run_check()
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])

    def test_reaches_follows_the_register(self) -> None:
        markets = self.markets
        self.assertTrue(markets.reaches(("eu",), "de"))
        self.assertTrue(markets.reaches(("eu",), "at"))
        self.assertTrue(markets.reaches(("de",), "de"))
        self.assertFalse(markets.reaches(("de",), "at"))
        self.assertFalse(markets.reaches(("eu",), "us"))
        # A reader in region eu without a recognized country is read as de.
        self.assertTrue(markets.reaches(("de",), "eu"))
        self.assertFalse(markets.reaches(("at",), "eu"))

    def test_is_live_covers_regions_and_their_fallback(self) -> None:
        self.assertTrue(self.markets.is_live("eu"))
        self.assertTrue(self.markets.is_live("us"))
        self.assertTrue(self.markets.is_live("de"))
        self.assertFalse(self.markets.is_live("at"))
        self.assertFalse(self.markets.is_live("fr"))


class MarketRegistryTestCase(CheckerTestCase):
    """The `registry/markets.json` register."""

    def load(self, payload: dict[str, object]) -> cf.MarketRegistry:
        path = Path(self._tmp.name) / "markets.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return cf.MarketRegistry.load(path)

    def test_committed_register_loads(self) -> None:
        markets = cf.MarketRegistry.load(cf.DEFAULT_MARKETS)
        self.assertEqual(markets.regions, ("eu", "us"))
        self.assertIn("de", markets.countries["eu"])
        self.assertEqual(markets.fallback_countries["eu"], "de")

    def test_region_of_a_country_is_its_region(self) -> None:
        markets = cf.MarketRegistry.load(cf.DEFAULT_MARKETS)
        self.assertEqual(markets.region_of("de"), "eu")
        self.assertEqual(markets.region_of("eu"), "eu")
        self.assertIsNone(markets.region_of("jp"))
        self.assertTrue(markets.is_region("eu"))
        self.assertFalse(markets.is_region("de"))

    def test_register_without_regions_is_error(self) -> None:
        with self.assertRaises(cf.RegistryError):
            self.load({"note": "leer"})

    def test_bad_region_code_is_error(self) -> None:
        with self.assertRaises(cf.RegistryError):
            self.load({"regions": [{"code": "europa"}]})

    def test_country_under_two_regions_is_error(self) -> None:
        with self.assertRaises(cf.RegistryError):
            self.load({"regions": [{"code": "eu", "countries": ["de"]}, {"code": "us", "countries": ["de"]}]})

    def test_fallback_outside_the_region_is_error(self) -> None:
        with self.assertRaises(cf.RegistryError):
            self.load({"regions": [{"code": "eu", "countries": ["at"], "fallback_country": "de"}]})

    def test_unknown_field_is_error(self) -> None:
        with self.assertRaises(cf.RegistryError):
            self.load({"regions": [{"code": "eu", "laender": ["de"]}]})

    def test_missing_register_is_error(self) -> None:
        self.write_pair()
        report = cf.run(
            self.content_dir,
            registry=self.registry,
            parameter_keys=self.parameter_keys,
            markets_path=Path(self._tmp.name) / "gibtsnicht.json",
        )
        self.assertError("Marktregister nicht lesbar", report)


class RegistryTestCase(CheckerTestCase):
    def test_missing_registry_is_error(self) -> None:
        self.write_pair()
        report = cf.run(
            self.content_dir,
            registry_path=Path(self._tmp.name) / "gibtsnicht.json",
            parameter_keys=self.parameter_keys,
        )
        self.assertError("nicht lesbar", report)

    def test_broken_registry_is_error(self) -> None:
        path = Path(self._tmp.name) / "kaputt.json"
        path.write_text("{nicht json", encoding="utf-8")
        self.write_pair()
        report = cf.run(self.content_dir, registry_path=path, parameter_keys=self.parameter_keys)
        self.assertError("kein gültiges JSON", report)

    def test_registry_without_slugs_is_error(self) -> None:
        path = Path(self._tmp.name) / "leer.json"
        path.write_text(json.dumps({"source": {"commit": TEST_COMMIT}}), encoding="utf-8")
        self.write_pair()
        report = cf.run(self.content_dir, registry_path=path, parameter_keys=self.parameter_keys)
        self.assertError("'slugs'", report)

    def test_registry_without_source_commit_is_error(self) -> None:
        path = Path(self._tmp.name) / "ohne-commit.json"
        path.write_text(json.dumps({"slugs": TEST_SLUGS}), encoding="utf-8")
        self.write_pair()
        report = cf.run(self.content_dir, registry_path=path, parameter_keys=self.parameter_keys)
        self.assertError("source.commit", report)

    def test_missing_parameter_keys_is_error(self) -> None:
        self.write_pair()
        report = cf.run(
            self.content_dir,
            registry=self.registry,
            parameter_keys_path=Path(self._tmp.name) / "gibtsnicht.json",
        )
        self.assertError("Deskriptor-Liste nicht lesbar", report)

    def test_parameter_keys_without_list_is_error(self) -> None:
        path = Path(self._tmp.name) / "ohne-keys.json"
        path.write_text(json.dumps({"note": "leer"}), encoding="utf-8")
        self.write_pair()
        report = cf.run(self.content_dir, registry=self.registry, parameter_keys_path=path)
        self.assertError("nicht-leere Liste 'keys'", report)

    def test_committed_registries_load(self) -> None:
        registry = cf.SlugRegistry.load(cf.DEFAULT_REGISTRY)
        self.assertEqual(len(registry.source_commit), 40)
        self.assertIn("eu", registry.by_region)
        keys = cf.ParameterKeys.load(cf.DEFAULT_PARAMETER_KEYS)
        self.assertIn("window", keys.keys)


class RepositoryContentTestCase(unittest.TestCase):
    def test_repository_content_is_valid(self) -> None:
        repo_content = Path(__file__).resolve().parents[1] / "content" / "strategies"
        report = cf.run(repo_content)
        self.assertEqual(report.errors, [])



class OverviewFieldsTestCase(CheckerTestCase):
    """`purpose` and `building_blocks` for the overview page (wave strategie-felder)."""

    GERMAN_PURPOSE = "Mit Hebel investiert bleiben, lange Abstürze aber möglichst nicht mitmachen."
    ENGLISH_PURPOSE = "Stay invested with leverage, but sit out long crashes where possible."
    BLOCKS = "building_blocks:\n  - aktien\n  - cash\n"

    def write_fields(
        self,
        *,
        german: str | None = None,
        english: str | None = None,
        german_blocks: str | None = None,
        english_blocks: str | None = None,
    ) -> None:
        de_purpose = self.GERMAN_PURPOSE if german is None else german
        en_purpose = self.ENGLISH_PURPOSE if english is None else english
        de_extra = f'purpose: "{de_purpose}"\n' + (self.BLOCKS if german_blocks is None else german_blocks)
        en_extra = f'purpose: "{en_purpose}"\n' + (self.BLOCKS if english_blocks is None else english_blocks)
        self.write("sma-trend.de.md", document(slug="sma-trend", extra=de_extra))
        self.write("sma-trend.en.md", document(slug="sma-trend", extra=en_extra))

    def test_both_fields_are_optional(self) -> None:
        self.write_pair()
        self.assertEqual(self.run_check().errors, [])

    def test_valid_fields_pass(self) -> None:
        self.write_fields()
        report = self.run_check()
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])

    def test_purpose_too_short_is_error(self) -> None:
        self.write_fields(german="Kurz und knapp dabei.")  # 21 characters, valid
        self.assertEqual(self.run_check().errors, [])
        self.write_fields(german="Kurz und knapp dabe.")  # 20 characters, valid
        self.assertEqual(self.run_check().errors, [])
        self.write_fields(german="Kurz und knapp dab.")  # 19 characters
        self.assertError("purpose", self.run_check())

    def test_purpose_too_long_is_error(self) -> None:
        self.write_fields(german="A" * 109 + ".")
        self.assertEqual(self.run_check().errors, [])
        self.write_fields(german="A" * 110 + ".")
        self.assertError("purpose", self.run_check())

    def test_purpose_without_period_is_error(self) -> None:
        self.write_fields(german="Mit Hebel investiert bleiben, lange Abstürze meiden")
        self.assertError("purpose", self.run_check())

    def test_purpose_with_dash_is_error(self) -> None:
        self.write_fields(german="Mit Hebel investiert bleiben \u2013 lange Abstürze meiden.")
        self.assertError("purpose", self.run_check())

    def test_purpose_with_percent_number_is_error(self) -> None:
        self.write_fields(german="Mit Hebel investiert bleiben und 12 % mehr herausholen.")
        self.assertError("purpose", self.run_check())

    def test_purpose_must_be_string(self) -> None:
        self.write("sma-trend.de.md", document(slug="sma-trend", extra="purpose: 42\n" + self.BLOCKS))
        self.write("sma-trend.en.md", document(slug="sma-trend", extra=f'purpose: "{self.ENGLISH_PURPOSE}"\n' + self.BLOCKS))
        self.assertError("purpose", self.run_check())

    def test_german_banned_word_is_error(self) -> None:
        self.write_fields(german="Die beste Wahl für lange Anleger mit ruhigem Blick.")
        self.assertError("beste", self.run_check())

    def test_german_word_prefix_is_error(self) -> None:
        self.write_fields(german="Wir empfehlen das für lange Anleger mit ruhigem Blick.")
        self.assertError("empfehl", self.run_check())

    def test_german_word_inside_other_word_passes(self) -> None:
        self.write_fields(german="Die Regel besteht aus zwei Schritten.")
        self.assertEqual(self.run_check().errors, [])
        self.write_fields(german="Die Regel bleibt auch unsicher einfach.")
        self.assertEqual(self.run_check().errors, [])

    def test_english_banned_word_is_error(self) -> None:
        self.write_fields(english="The safe way to hold leverage for many years.")
        self.assertError("safe", self.run_check())

    def test_english_list_does_not_apply_to_german(self) -> None:
        self.write_fields(german="Ein Portfolio mit Hebel, das auch safe wirken soll.")
        self.assertEqual(self.run_check().errors, [])

    def test_unknown_block_is_error(self) -> None:
        self.write_fields(
            german_blocks="building_blocks:\n  - aktien\n  - bitcoin\n",
            english_blocks="building_blocks:\n  - aktien\n  - bitcoin\n",
        )
        self.assertError("unbekannter Baustein bitcoin", self.run_check())

    def test_duplicate_block_is_error(self) -> None:
        blocks = "building_blocks:\n  - aktien\n  - aktien\n"
        self.write_fields(german_blocks=blocks, english_blocks=blocks)
        self.assertError("building_blocks", self.run_check())

    def test_empty_block_list_is_error(self) -> None:
        blocks = "building_blocks: []\n"
        self.write_fields(german_blocks=blocks, english_blocks=blocks)
        self.assertError("building_blocks", self.run_check())

    def test_five_blocks_are_error(self) -> None:
        blocks = "building_blocks:\n" + "".join(
            f"  - {key}\n" for key in ("aktien", "lange-staatsanleihen", "staatsanleihen", "gold", "cash")
        )
        self.write_fields(german_blocks=blocks, english_blocks=blocks)
        self.assertError("building_blocks", self.run_check())

    def test_four_blocks_pass(self) -> None:
        blocks = "building_blocks:\n" + "".join(
            f"  - {key}\n" for key in ("aktien", "lange-staatsanleihen", "gold", "cash")
        )
        self.write_fields(german_blocks=blocks, english_blocks=blocks)
        self.assertEqual(self.run_check().errors, [])

    def test_blocks_must_be_list_of_strings(self) -> None:
        blocks = "building_blocks: aktien\n"
        self.write_fields(german_blocks=blocks, english_blocks=blocks)
        self.assertError("building_blocks", self.run_check())

    def test_blocks_differ_between_languages_is_error(self) -> None:
        self.write_fields(
            german_blocks="building_blocks:\n  - aktien\n  - lange-staatsanleihen\n",
            english_blocks="building_blocks:\n  - aktien\n  - cash\n",
        )
        self.assertError("building_blocks", self.run_check())

    def test_blocks_missing_in_one_language_is_error(self) -> None:
        self.write_fields(english_blocks="")
        self.assertError("building_blocks", self.run_check())


if __name__ == "__main__":
    unittest.main()
