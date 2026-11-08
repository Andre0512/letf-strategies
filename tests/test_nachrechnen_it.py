"""Wave strategie-nachrechnen-it: new layout of the chapter recompute.

Acceptance (spec section 4) for sma-trend and hfea, de and en:
- nine fixed H3 in recompute (wave strategie-nachrechnen-code), intro without
  a quote box, no agent anywhere, one llms.txt sentence after the file list;
- pseudocode and parameters as text blocks without LaTeX, the version
  sentence with all ranges, four data rules in fixed order;
- every link goes to a file under the Andre0512 blob URL, file list with 8 points;
- one bash block whose last two lines reproduce output.csv with diff;
- column table, two packages, invented data, fixed sentences and the eight-day table;
- formulas leave recompute and stand under a new last H3 of math;
- llms.txt and examples/README.md name examples/leverage-model/ and diff;
- word bans keep applying to the whole chapter recompute.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_examples as te  # noqa: E402

ROOT = te.ROOT
BLOB = "https://github.com/Andre0512/letf-strategies/blob/main/"
LLMS_URL = BLOB + "llms.txt"
REPO_URL = "https://github.com/Andre0512/letf-strategies"

# Wave strategie-nachrechnen-code: nine H3, the quote box for agents is gone.
H3 = {"de": te.RECOMPUTE_H3_DE, "en": te.RECOMPUTE_H3_EN}
# Index of each H3 in the lists above.
FILES_AT, RUN_AT, COLUMNS_AT, PACKAGES_AT, INVENTED_AT, SAME_AT = 0, 1, 5, 6, 7, 8
CALC_AT, PARAMS_AT, RULES_AT = 2, 3, 4
LLMS_SENTENCE = {
    "de": f"Maschinenlesbare Übersicht: [llms.txt]({LLMS_URL}).",
    "en": f"Machine-readable overview: [llms.txt]({LLMS_URL}).",
}
MATH_H3 = {"de": "Tag für Tag gerechnet", "en": "Day by day"}
RESULT_FILE = {"de": "ergebnis.csv", "en": "result.csv"}
COLUMN_HEADERS = {"de": ["Spalte", "Bedeutung"], "en": ["Column", "Meaning"]}
DAILY = {"de": "täglich", "en": "daily"}
LICENSE = {"de": "Lizenz", "en": "licen"}
INVENTED = {"de": "erfunden", "en": "invented"}
REAL_CLOSE = {"de": "echte Schlusskurse", "en": "real closing prices"}
TABLE_SENTENCE = {"de": te.SENTENCE_TABLE_DE, "en": te.SENTENCE_TABLE_EN}

COLUMNS = {
    "sma-trend": [
        "date",
        "index_rounded",
        "sma",
        "line",
        "line_state",
        "invested",
        "signal",
        "money_interest_day",
        "trading_cost",
        "value_strategy",
        "value_hold",
    ],
    "hfea": [
        "run",
        "rule",
        "date",
        "stock_shares",
        "bond_shares",
        "quote_before_percent",
        "deadline",
        "band_breached",
        "value_strategy",
        "value_hold",
    ],
}
PACKAGE = {"sma-trend": "sma-signal", "hfea": "rebalancing"}
LEVERAGE = "leverage-model"

FIXED_SENTENCES = {
    ("sma-trend", "de"): [te.SENTENCE_EXACTNESS_DE],
    ("sma-trend", "en"): [te.SENTENCE_EXACTNESS_EN],
    ("hfea", "de"): [te.SENTENCE_EXACTNESS_HFEA_DE, te.SENTENCE_CALENDAR_DE],
    ("hfea", "en"): [te.SENTENCE_EXACTNESS_HFEA_EN, te.SENTENCE_CALENDAR_EN],
}

FORMULAS = {
    "sma-trend": [
        r"L(t) = \begin{cases}",
        r"W \leftarrow W\,(1 - c)",
        r"z = \bigl(1 + \max(r, 0)/100\bigr)^{1/252} - 1",
    ],
    "hfea": [
        r"n_e = \frac{100\, w_e}{P_e(0)}",
        r"W(t) = n_e\, P_e(t) + n_b\, P_b(t)",
        r"\lvert w_e(t) - w_e \rvert \ge b",
    ],
}

# Eight-day tables as they stand before the wave (body rows, values unchanged).
EIGHT_DAYS = {
    ("sma-trend", "de"): [
        ["1925-11-04", "113.43", "111.91", "ja", "73.88"],
        ["1925-11-05", "113.56", "111.91", "ja", "74.05"],
        ["1925-11-06", "111.34", "111.90", "nein", "74.11"],
        ["1925-11-09", "113.80", "115.30", "nein", "74.12"],
        ["1925-11-10", "113.89", "115.30", "nein", "74.13"],
        ["1925-11-11", "113.94", "115.30", "nein", "74.14"],
        ["1925-11-12", "113.95", "115.30", "nein", "74.15"],
        ["1925-11-13", "113.91", "115.30", "nein", "74.16"],
    ],
    ("hfea", "de"): [
        ["1926-12-24", "111.00", "43.80", "60.33", "116.80"],
        ["1926-12-27", "113.00", "44.20", "60.54", "118.50"],
        ["1926-12-28", "112.50", "43.50", "60.81", "117.44"],
        ["1926-12-29", "111.50", "43.10", "60.82", "116.38"],
        ["1926-12-30", "112.80", "43.40", "60.93", "117.52"],
        ["1926-12-31", "114.00", "43.90", "60.91", "118.81"],
        ["1927-01-03 (umgeschichtet)", "115.00", "44.50", "60.79", "120.08"],
        ["1927-01-04", "115.80", "44.50", "60.17", "120.58"],
    ],
}
EIGHT_DAYS[("sma-trend", "en")] = [
    [c.replace("ja", "yes").replace("nein", "no") for c in row]
    for row in EIGHT_DAYS[("sma-trend", "de")]
]
EIGHT_DAYS[("hfea", "en")] = [
    [c.replace("(umgeschichtet)", "(rebalanced)") for c in row]
    for row in EIGHT_DAYS[("hfea", "de")]
]

PAGES = [(s, lang) for s in ("sma-trend", "hfea") for lang in ("de", "en")]

H3_BLOCK = re.compile(r"(?ms)^###[ \t]+([^\n]*?)[ \t]*\n(.*?)(?=^###[ \t]|\Z)")
LINK = re.compile(r"\[([^\]]*)\]\(([^)\s]+)\)")
DASHES = (chr(0x2013), chr(0x2014))


def _page(strategy: str, language: str) -> str:
    return (ROOT / "content" / "strategies" / f"{strategy}.{language}.md").read_text(
        encoding="utf-8"
    )


def _chapter(strategy: str, language: str, name: str) -> str:
    return te._section(_page(strategy, language), name)


def _h3_blocks(chapter: str) -> list[tuple[str, str]]:
    return [(m.group(1).strip(), m.group(2)) for m in H3_BLOCK.finditer(chapter)]


def _intro(chapter: str) -> str:
    """Text between the H2 line and the first H3."""
    match = re.search(r"(?m)^###[ \t]", chapter)
    return chapter[: match.start()] if match else chapter


def _h3_body(chapter: str, index: int) -> str:
    blocks = _h3_blocks(chapter)
    return blocks[index][1] if len(blocks) > index else ""


def _paragraphs(text: str) -> list[str]:
    return [p for p in re.split(r"\n[ \t]*\n", text) if p.strip()]


def _bash_blocks(text: str) -> list[list[str]]:
    blocks = re.findall(r"(?ms)^```bash[ \t]*\n(.*?)^```[ \t]*$", text)
    return [[line.strip() for line in b.splitlines() if line.strip()] for b in blocks]


def _expected_files(strategy: str) -> list[str]:
    paths: list[str] = []
    for package in (PACKAGE[strategy], LEVERAGE):
        paths += [f"examples/{package}/{name}" for name in te.PACKAGE_FILES]
    return paths


def _list_items(text: str) -> list[str]:
    return [m.group(1) for m in re.finditer(r"(?m)^[-*][ \t]+(.*)$", text)]


def _list_items_full(text: str) -> list[str]:
    """List items with their indented continuation lines, flattened."""
    items = re.findall(r"(?m)^[-*][ \t]+(.*(?:\n[ \t]+\S.*)*)", text)
    return [te._flatten(item).strip() for item in items]


def _output_header(package: str) -> list[str]:
    path = ROOT / "examples" / package / "output.csv"
    return path.read_text(encoding="utf-8").splitlines()[0].split(",")


class _Pages(unittest.TestCase):
    def pages(self) -> list[tuple[str, str, str]]:
        # Kein subTest im Generator: eine Ausnahme im Schleifenkörper landet
        # nicht im with-Block. Die erste rote Seite beendet den Test.
        return [
            (strategy, language, _chapter(strategy, language, "recompute"))
            for strategy, language in PAGES
        ]


class TestRecomputeLayout(_Pages):
    """Acceptance: H3 list, intro without agents, one llms.txt sentence."""

    def test_h3_list_is_exact(self) -> None:
        for _, language, chapter in self.pages():
            titles = [title for title, _ in _h3_blocks(chapter)]
            self.assertEqual(titles, H3[language])

    def test_intro_has_ten_words_without_agent_and_quote(self) -> None:
        for _, _, chapter in self.pages():
            intro = _intro(chapter)
            body = re.sub(r"(?m)^##[ \t].*$", "", intro, count=1)
            self.assertGreaterEqual(len(re.findall(r"\w+", body)), 10, intro)
            self.assertIsNone(re.search(r"(?i)agent", intro), "agent in the intro")
            self.assertIsNone(re.search(r"(?m)^[ \t]*>", intro), "quote in the intro")

    def test_no_quote_in_recompute(self) -> None:
        for _, _, chapter in self.pages():
            self.assertIsNone(re.search(r"(?m)^[ \t]*>", chapter), "quote in recompute")

    def test_no_heading_for_agents(self) -> None:
        for _, _, chapter in self.pages():
            for title in ("Für Agenten", "For agents"):
                self.assertNotIn(title, chapter)

    def test_llms_sentence_once_after_the_file_list(self) -> None:
        for _, language, chapter in self.pages():
            sentence = LLMS_SENTENCE[language]
            self.assertEqual(chapter.count(sentence), 1, sentence)
            body = _h3_body(chapter, FILES_AT)
            self.assertIn(sentence, body, "llms.txt sentence not under the first H3")
            # The file list is one paragraph (items with continuation lines),
            # the sentence is the only paragraph after it.
            paragraphs = _paragraphs(body)
            self.assertGreaterEqual(len(paragraphs), 2, paragraphs)
            self.assertEqual(te._flatten(paragraphs[-1]).strip(), sentence)
            self.assertRegex(paragraphs[-2].lstrip(), r"^[-*][ \t]", "no list before it")

    def test_no_agent_word_in_recompute(self) -> None:
        for _, _, chapter in self.pages():
            self.assertIsNone(re.search(r"(?i)agent", chapter), "agent in recompute")


class TestRecomputeLinks(_Pages):
    """Acceptance: every link goes to an existing file under the blob URL."""

    def test_every_link_is_a_blob_file(self) -> None:
        for _, _, chapter in self.pages():
            targets = [t for _, t in LINK.findall(chapter)]
            self.assertTrue(targets)
            for target in targets:
                self.assertTrue(target.startswith(BLOB), target)
                path = target[len(BLOB) :]
                self.assertTrue((ROOT / path).is_file(), path)

    def test_no_old_org_and_no_folder_links(self) -> None:
        for _, _, chapter in self.pages():
            self.assertNotIn("LETF-io/strategies", chapter)
            self.assertNotIn("/tree/", chapter)

    def test_file_list_under_first_h3(self) -> None:
        for strategy, _, chapter in self.pages():
            items = _list_items(_h3_body(chapter, FILES_AT))
            expected = _expected_files(strategy)
            self.assertEqual(len(items), 8, items)
            for item, path in zip(items, expected):
                self.assertTrue(
                    item.startswith(f"[`{path}`]({BLOB}{path})"),
                    f"{item!r} does not start with the link on {path}",
                )


class TestRunLocally(_Pages):
    """Acceptance: one bash block, lines 3 and 4 reproduce output.csv."""

    def _expected_lines(self, strategy: str, language: str) -> list[str]:
        result = RESULT_FILE[language]
        return [
            f"git clone {REPO_URL}.git",
            f"cd letf-strategies/examples/{PACKAGE[strategy]}",
            f"python3 recompute.py input.csv > {result}",
            f"diff {result} output.csv",
        ]

    def test_one_bash_block_with_four_lines(self) -> None:
        for strategy, language, chapter in self.pages():
            body = _h3_body(chapter, RUN_AT)
            blocks = _bash_blocks(body)
            self.assertEqual(len(blocks), 1, blocks)
            self.assertEqual(blocks[0], self._expected_lines(strategy, language))
            self.assertEqual(len(re.findall(r"(?m)^```", body)), 2, "extra code block")

    def _run_in_copy(self, package: str, lines: list[str]) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / package
            shutil.copytree(ROOT / "examples" / package, target)
            for line in lines:
                done = subprocess.run(
                    line,
                    shell=True,
                    cwd=target,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                self.assertEqual(done.returncode, 0, f"{line}: {done.stdout}{done.stderr}")

    def test_lines_three_and_four_end_with_exit_zero(self) -> None:
        for strategy, language, chapter in self.pages():
            blocks = _bash_blocks(_h3_body(chapter, RUN_AT))
            self.assertEqual(len(blocks), 1)
            self.assertEqual(len(blocks[0]), 4, blocks[0])
            self._run_in_copy(PACKAGE[strategy], blocks[0][2:4])

    def test_same_lines_hold_for_leverage_model(self) -> None:
        for strategy, language, chapter in self.pages():
            blocks = _bash_blocks(_h3_body(chapter, RUN_AT))
            self.assertEqual(len(blocks), 1)
            self.assertIn(f"examples/{LEVERAGE}", _h3_body(chapter, RUN_AT))
            self._run_in_copy(LEVERAGE, blocks[0][2:4])


def _text_blocks(text: str) -> list[str]:
    return re.findall(r"(?ms)^```text[ \t]*\n(.*?)^```[ \t]*$", text)


def _has_number(line: str, number: str) -> bool:
    # 2.5 also matches 2,5 and 2.50; 50 does not match inside 500 or 0.5.
    pattern = re.escape(number).replace(r"\.", "[.,]")
    pattern += "0*" if "." in number else r"(?:[.,]0+)?"
    return re.search(rf"(?<![\d.,]){pattern}(?![\d]|[.,]\d)", line) is not None


def _lines_with(blocks: list[str], words: tuple[str, ...]) -> list[str]:
    return [
        line
        for block in blocks
        for line in block.splitlines()
        if any(w in line.lower() for w in words)
    ]


LATEX_MARKS = ("$", "\\frac", "\\begin", "\\lvert", "\\leftarrow", "\\bigl")
PSEUDO_WORDS = {
    "sma-trend": [
        ("puffer", "buffer"),
        ("schluss", "close"),
        ("kosten", "cost"),
        ("zins", "interest"),
    ],
    "hfea": [("ziel", "target"), ("frist", "deadline")],
}
# Pairs that must appear in this order in the strategy block.
PSEUDO_ORDER = {
    "sma-trend": [(("puffer", "buffer"), ("zins", "interest"))],
    "hfea": [(("ziel", "target"), ("frist", "deadline"))],
}
ADJUSTED = ("bereinigt", "adjusted")
VERSION_SENTENCE = {
    "de": "Deine Fassung kann diese Werte ändern",
    "en": "Your own version can change these values",
}
VERSION_NUMBERS = {
    "sma-trend": ("50", "500", "5", "1"),
    "hfea": ("1", "3", "6", "12", "30", "80"),
}
RULE_KEYWORDS = [
    ("handelskalender", "trading calendar"),
    ("splits",),
    ("nachbau", "reconstruction"),
    ("währung", "currency"),
]
RULE_CONTENT = [
    ("feiertag", "holiday"),
    ("bereinigt", "adjustment", "adjusted"),
    ("auflage", "launch"),
    ("wechselkurs", "exchange rate", "currency"),
]


class TestPseudocode(_Pages):
    """Acceptance: the calculation in short as a text block without LaTeX."""

    def _blocks(self, chapter: str) -> list[str]:
        return _text_blocks(_h3_body(chapter, CALC_AT))

    def _strategy_block(self, strategy: str, chapter: str) -> str:
        # One block for the strategy, at most a second one for the leverage model.
        blocks = self._blocks(chapter)
        self.assertIn(len(blocks), (1, 2), "one strategy block, optionally one more")
        own = [
            b
            for b in blocks
            if all(any(w in b.lower() for w in ws) for ws in PSEUDO_WORDS[strategy])
        ]
        self.assertEqual(len(own), 1, "exactly one block holds the strategy steps")
        return own[0].lower()

    def test_text_block_without_latex(self) -> None:
        for _, _, chapter in self.pages():
            blocks = self._blocks(chapter)
            self.assertTrue(blocks, "no text block under the calculation in short")
            for block in blocks:
                for mark in LATEX_MARKS:
                    self.assertNotIn(mark, block)

    def test_pseudocode_names_the_steps(self) -> None:
        for strategy, _, chapter in self.pages():
            code = self._strategy_block(strategy, chapter)
            self.assertTrue(any(w in code for w in ADJUSTED), "adjusted prices")

    def test_steps_in_order(self) -> None:
        for strategy, _, chapter in self.pages():
            code = self._strategy_block(strategy, chapter)
            for first, then in PSEUDO_ORDER[strategy]:
                start = min(code.index(w) for w in first if w in code)
                later = max(code.rindex(w) for w in then if w in code)
                self.assertLess(start, later, f"{first} not before {then}")

    def test_band_only_with_the_deadline(self) -> None:
        # The band variant is no trigger of its own: every condition line
        # naming the band also names the deadline.
        condition = re.compile(r"\b(wenn|falls|if|when)\b")
        for strategy, _, chapter in self.pages():
            if strategy != "hfea":
                continue
            code = self._strategy_block(strategy, chapter)
            for line in code.splitlines():
                if "band" in line and condition.search(line):
                    self.assertTrue(
                        "frist" in line or "deadline" in line,
                        f"band without the deadline: {line!r}",
                    )


class TestParameters(_Pages):
    """Acceptance: constants in a text block, version sentence after it."""

    def _body(self, chapter: str) -> str:
        return _h3_body(chapter, PARAMS_AT)

    def test_one_text_block_without_latex(self) -> None:
        for _, _, chapter in self.pages():
            blocks = _text_blocks(self._body(chapter))
            self.assertEqual(len(blocks), 1, "exactly one text block under the parameters")
            for block in blocks:
                for mark in LATEX_MARKS:
                    self.assertNotIn(mark, block)

    def _assert_line(self, blocks: list[str], words, numbers, any_of=()) -> None:
        lines = _lines_with(blocks, words)
        self.assertTrue(lines, f"no line with {words}")
        hits = [
            line
            for line in lines
            if all(_has_number(line, n) for n in numbers)
            and (not any_of or any(_has_number(line, n) for n in any_of))
        ]
        self.assertTrue(hits, f"{words}: {numbers} {any_of} missing in {lines}")

    def test_sma_constants(self) -> None:
        for strategy, _, chapter in self.pages():
            if strategy != "sma-trend":
                continue
            blocks = _text_blocks(self._body(chapter))
            self._assert_line(blocks, ("fenster", "window"), ("200", "220", "255"))
            self._assert_line(blocks, ("puffer", "buffer"), ("0",))
            self._assert_line(
                blocks, ("bestaetigung", "bestätigung", "confirmation"), ("1",)
            )
            self._assert_line(
                blocks, ("ersatz", "fallback", "unbekannt", "unknown"), ("2.5",)
            )
            self._assert_line(
                blocks, ("verzögerung", "verzoegerung", "lag", "delay"), ("0",)
            )
            self._assert_line(blocks, ("kosten", "cost"), ("0",))
            code = "\n".join(blocks)
            for rate in ("ESTR", "SOFR", "SONIA"):
                self.assertIn(rate, code)

    def test_hfea_constants(self) -> None:
        for strategy, _, chapter in self.pages():
            if strategy != "hfea":
                continue
            blocks = _text_blocks(self._body(chapter))
            self._assert_line(blocks, ("gewicht", "weight"), ("55", "50"))
            self._assert_line(blocks, ("monat", "month"), ("3",))
            band = _lines_with(blocks, ("band",))
            self.assertTrue(band, "no band line")
            self.assertTrue(
                any(re.search(r"(?i)\b(keins?|keine|none)\b", line) for line in band),
                f"band is not none: {band}",
            )

    def test_version_sentence_after_the_block(self) -> None:
        for strategy, language, chapter in self.pages():
            body = self._body(chapter)
            ends = [m.end() for m in re.finditer(r"(?ms)^```text[ \t]*\n.*?^```[ \t]*$", body)]
            self.assertTrue(ends)
            after = te._flatten(body[ends[-1] :])
            phrase = VERSION_SENTENCE[language]
            self.assertIn(phrase, after, "no version sentence after the block")
            rest = after[after.index(phrase) :]
            for number in VERSION_NUMBERS[strategy]:
                self.assertTrue(_has_number(rest, number), f"range {number} missing")


class TestDataRules(_Pages):
    """Acceptance: four data rules with bold keywords in fixed order."""

    def test_four_rules_in_order(self) -> None:
        for _, _, chapter in self.pages():
            items = _list_items_full(_h3_body(chapter, RULES_AT))
            self.assertEqual(len(items), 4, items)
            for item, keywords, content in zip(items, RULE_KEYWORDS, RULE_CONTENT):
                bold = re.match(r"\*\*(.+?)\*\*", item.strip())
                self.assertIsNotNone(bold, f"no bold keyword at the start: {item!r}")
                self.assertTrue(
                    any(k in bold.group(1).lower() for k in keywords),
                    f"{bold.group(1)!r} not one of {keywords}",
                )
                self.assertTrue(
                    any(c in item.lower() for c in content), f"{content} missing: {item!r}"
                )

    def test_rule_details(self) -> None:
        for strategy, _, chapter in self.pages():
            items = _list_items_full(_h3_body(chapter, RULES_AT))
            self.assertEqual(len(items), 4, items)
            calendar, _, reconstruction, currency = (i.lower() for i in items)
            if strategy == "sma-trend":
                self.assertTrue(_has_number(calendar, "4"), calendar)
            else:
                self.assertTrue(
                    "gemeinsam" in calendar or "common" in calendar,
                    f"next common trading day missing: {calendar!r}",
                )
                self.assertTrue(
                    "echt" in reconstruction or "real" in reconstruction, reconstruction
                )
            self.assertNotIn("recompute.py", currency)

    def test_rules_without_latex(self) -> None:
        for _, _, chapter in self.pages():
            body = _h3_body(chapter, RULES_AT)
            self.assertTrue(body.strip())
            for mark in ("$", "\\frac", "\\begin"):
                self.assertNotIn(mark, body)


class TestColumnsAndParagraphs(_Pages):
    """Acceptance: column table, two packages, invented data."""

    def test_column_table(self) -> None:
        for strategy, language, chapter in self.pages():
            headers, body, _ = te._table(_h3_body(chapter, COLUMNS_AT))
            self.assertEqual(headers, COLUMN_HEADERS[language])
            cells = [row[0] for row in body]
            for cell in cells:
                self.assertRegex(cell, r"^`[a-z_]+`$")
            names = [cell.strip("`") for cell in cells]
            self.assertEqual(len(names), len(set(names)), "duplicate column")
            self.assertEqual(set(names), set(COLUMNS[strategy]))
            header = _output_header(PACKAGE[strategy])
            for name in names:
                self.assertIn(name, header)

    def test_why_two_packages(self) -> None:
        for strategy, language, chapter in self.pages():
            body = _h3_body(chapter, PACKAGES_AT)
            self.assertIn(LEVERAGE, body)
            self.assertIn(PACKAGE[strategy], body)
            self.assertIn(DAILY[language], body)
            if strategy == "hfea":
                self.assertIn(REAL_CLOSE[language], te._flatten(body))

    def test_why_invented_data(self) -> None:
        for _, language, chapter in self.pages():
            body = _h3_body(chapter, INVENTED_AT)
            self.assertIn(LICENSE[language], body)
            self.assertIn(INVENTED[language], body)


class TestSameComputation(_Pages):
    """Acceptance: fixed sentences and the unchanged eight-day table."""

    def test_fixed_sentences_verbatim(self) -> None:
        for strategy, language, chapter in self.pages():
            body = te._flatten(te._without_links(_h3_body(chapter, SAME_AT)))
            for sentence in FIXED_SENTENCES[(strategy, language)]:
                self.assertIn(te._flatten(sentence), body)

    def test_eight_day_table_unchanged(self) -> None:
        for strategy, language, chapter in self.pages():
            body = _h3_body(chapter, SAME_AT)
            headers, rows, index = te._table(body)
            self.assertGreaterEqual(len(rows) + 1, 9)
            self.assertEqual(rows, EIGHT_DAYS[(strategy, language)])
            before = te._flatten("\n".join(body.splitlines()[:index]))
            self.assertIn(TABLE_SENTENCE[language], before)


class TestFormulasInMath(_Pages):
    """Acceptance: no formula in recompute, formulas under the last H3 of math."""

    def test_no_formula_in_recompute(self) -> None:
        for _, _, chapter in self.pages():
            for mark in ("$$", "\\frac", "\\begin", "\\lvert", "\\leftarrow", "\\bigl"):
                self.assertNotIn(mark, chapter)

    def test_last_h3_of_math_holds_the_formulas(self) -> None:
        for strategy, language, _ in self.pages():
            blocks = _h3_blocks(_chapter(strategy, language, "math"))
            self.assertTrue(blocks)
            title, body = blocks[-1]
            self.assertEqual(title, MATH_H3[language])
            for formula in FORMULAS[strategy]:
                self.assertIn(formula, body)

    def test_math_without_box_lead_and_package_links(self) -> None:
        for strategy, language, _ in self.pages():
            math = _chapter(strategy, language, "math")
            self.assertNotIn("Zum Nachrechnen", math)
            for target in te._link_targets(math):
                self.assertNotIn("examples/", target)

    def test_close_once_in_day_by_day(self) -> None:
        # SMA only: the HFEA Rechenweg never named (Close), and BAU-4 moves it unchanged.
        for strategy, language, _ in self.pages():
            if strategy != "sma-trend":
                continue
            blocks = _h3_blocks(_chapter(strategy, language, "math"))
            body = blocks[-1][1] if blocks else ""
            self.assertEqual(body.count("(Close)"), 1)
            if language == "de":
                self.assertIn("Schlusskurs (Close)", body)


class TestWordBans(_Pages):
    """Acceptance: word bans apply to the whole chapter recompute."""

    def test_names_fields_isins(self) -> None:
        # Fassung 3: ESTR, SOFR and SONIA are allowed only in the interest
        # source line of the constants block (fourth H3); every other hit
        # stays forbidden.
        rate_names = {"ESTR", "SOFR", "SONIA"}
        rate_line = re.compile(r"(?mi)^[ \t]*\w*(?:zins|rate)\w*[ \t]*=.*$")
        for strategy, language, chapter in self.pages():
            constants = _h3_body(chapter, 3)
            rest = chapter
            for line in rate_line.findall(constants):
                hits = te._forbidden_hits(line)
                if hits and set(hits) <= rate_names:
                    rest = rest.replace(line, "", 1)
            self.assertEqual(te._forbidden_hits(rest), [], (strategy, language))

    def test_no_promise_words(self) -> None:
        for _, _, chapter in self.pages():
            text = te._without_links(chapter)
            for word in te.WORDS_NO_PROMISE:
                self.assertIsNone(te._word_pattern(word).search(text), word)

    def test_box_words(self) -> None:
        for _, _, chapter in self.pages():
            for word in te.BOX_WORDS:
                self.assertIsNone(
                    re.search(rf"(?<!\w){re.escape(word)}(?!\w)", chapter, re.IGNORECASE),
                    word,
                )

    def test_exact_only_in_the_fixed_sentence(self) -> None:
        for strategy, language, chapter in self.pages():
            rest = te._flatten(te._without_links(chapter))
            for sentence in FIXED_SENTENCES[(strategy, language)]:
                self.assertIn(te._flatten(sentence), rest)
                rest = rest.replace(te._flatten(sentence), "")
            for word in ("exakt", "exact", "dieselben zahlen", "the same numbers"):
                self.assertIsNone(re.search(word, rest, re.IGNORECASE), word)


class TestLlmsAndExamplesReadme(unittest.TestCase):
    """Acceptance: llms.txt and examples/README.md, no long dashes."""

    def test_both_name_leverage_model_and_diff(self) -> None:
        for path in (ROOT / "llms.txt", ROOT / "examples" / "README.md"):
            with self.subTest(file=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertIn("examples/leverage-model/", text)
                self.assertRegex(text, r"(?<![\w-])diff(?![\w-])")

    def test_llms_names_the_public_address(self) -> None:
        text = (ROOT / "llms.txt").read_text(encoding="utf-8")
        self.assertIn(REPO_URL, text)

    def test_no_long_dashes_in_changed_files(self) -> None:
        files = [ROOT / "content" / "strategies" / f"{s}.{lang}.md" for s, lang in PAGES]
        files += [ROOT / "llms.txt", ROOT / "examples" / "README.md"]
        for path in files:
            with self.subTest(file=path.name):
                text = path.read_text(encoding="utf-8")
                for mark in DASHES:
                    self.assertNotIn(mark, text)


if __name__ == "__main__":
    unittest.main()
