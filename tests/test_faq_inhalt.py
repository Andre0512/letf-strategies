"""Checks the chapter faq of the German pages of SMA-Trendfolge and HFEA.

Wave strategie-faq-inhalt, section acceptance. The tests are red as long as the
chapters still carry the old state: 36 and 28 questions, no short answer as its
own first paragraph, "weiter oben" and the sentences that the technical review
corrected.

Contract (test author, 2026-10-09): The chapter runs from the line ``## faq``
to before ``## weiterlesen`` (in the V5 schema, page with ``## rule``, to
before ``## sources``; wave struktur-v5-inhalt). A category is an H3 outside a ``:::faq``; its
intro is the first paragraph after it. The answer is everything in the
container after the question; its first paragraph (lines up to the blank line,
joined with spaces) is the short answer.

Wave strategie-faq-inhalt-en (test author, 2026-10-13): The English pages are
checked pairwise against the German ones. Pairing is by position: category n
with category n, question m of a category with question m. Per question the
``:::market`` wrapper, URLs and internal anchors match.

Wave hfea-faq-zahlen (test author, 2026-10-18): The answers on drawdowns, on
the long backtests and on 2022 carry the numbers from quant as of 2009-06-25.
Acceptance 1 and 2 are checked by HfeaNumbersTest; acceptance 3 is covered by
FrontmatterCheckTest, NoDashTest and FullRunTest. Because the wave replaces
exactly these three answers, the checksum of appendix B leaves them out via
``without_faq``, and the sentences "beginnt derzeit im Juli 2021" and "Stand 8. Oktober 2026"
drop out of CorrectionsTest.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
import unittest
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SMA = ROOT / "content" / "strategies" / "sma-trend.de.md"
HFEA = ROOT / "content" / "strategies" / "hfea.de.md"
SMA_EN = ROOT / "content" / "strategies" / "sma-trend.en.md"
HFEA_EN = ROOT / "content" / "strategies" / "hfea.en.md"
SCHEMA = ROOT / "docs" / "frontmatter-schema.md"

ALLOWED_ANCHORS = frozenset(
    {"regel", "beispiele", "rueckschau", "parameter", "dabeibleiben", "region", "abwaegung", "fehler", "kritik"}
    # Wave struktur-v5-inhalt: the V5 anchors of SMA, additive because HFEA keeps the old ones.
    | {
        "rule",
        "examples",
        "backtest",
        "parameters",
        "implementation",
        "staying-invested",
        "mistakes",
        "history",
        "tradeoffs",
        "criticism",
    }
)
TAX_NOTE = "Stand der Steuerangaben: November 2026; keine Steuerberatung."
# Wave strategie-compliance-release: only the "Stand" of the tax note switched from Oktober 2026 to November 2026.
HASH_APPENDIX_A = "9e91697a20092dd8ed13433d626111fa24c52b65ddfec24d86d2839ff8c7c7eb"
HASH_APPENDIX_B = "0bd5b36322096360d3d3d753742532e9b6cbbdf5c396497282ac1c0b2eea63ab"
REFERENCE_START = "Mehr dazu im Kapitel ["
REFERENCE = re.compile(r"^Mehr dazu im Kapitel \[[^\]]+\]\(#([a-z-]+)\)\.$")
LINK_ANCHOR = re.compile(r"\]\(#([^)\s]+)\)")

TAX_NOTE_EN = "Tax information as of November 2026; not tax advice."
REFERENCE_DE = re.compile(r"^Mehr dazu im Kapitel \[([^\]]+)\]\(#([a-z-]+)\)\.$")
REFERENCE_EN_START = "More in the chapter ["
CHAPTER_EN = {
    "Die Regel": "The Rule",
    "Beispiele": "Examples",
    "Backtest": "Backtest",
    "Parameter": "Parameters",
    "Dabeibleiben": "Staying the Course",
    "Umsetzung und Steuern": "Implementation and Taxes",
    "Hintergrund": "Background",
}
URL = re.compile(r"https?://[^\s)\]>]+")
# U+2013 and U+2014 via chr, so that the test file itself carries no dash.
DASHES = (chr(0x2013), chr(0x2014))

# Abbreviations after whose period no sentence ends.
ABBREVIATIONS = frozenset({"abs", "art", "nr", "z", "b", "d", "h", "u", "a", "ca", "rev", "rul", "s", "vgl", "bzw"})
# English abbreviations, checked against the text before the last period.
ABBREVIATIONS_EN = re.compile(r"(?:\b(?:vs|e\.g|i\.e|U\.S|approx|Rev|Rul|No))$", re.IGNORECASE)

EXPECTED_SMA: list[tuple[str, list[str]]] = [
    (
        "Einstieg und erste Schritte",
        [
            "Was ist die 200-Tage-Linie, und wie lautet die Regel?",
            "Was heißt gehebelt, und warum zählt der tägliche Hebel?",
            "Mit wie wenig Geld geht das?",
            "Der Index steht weit über der 200-Tage-Linie: sofort einsteigen oder warten?",
            "Was ist, wenn ich schon investiert bin?",
        ],
    ),
    (
        "Sparplan und Zuflüsse",
        [
            "Was passiert mit meinem Sparplan, wenn die Regel verkauft hat?",
            "Was mache ich mit neuem Geld, wenn ich schon investiert bin?",
            "Wo liegt das Geld, solange ich draußen bin?",
        ],
    ),
    (
        "Im Alltag",
        [
            "Muss ich wirklich jeden Tag nachsehen?",
            "Handle ich am Abend des Signals oder am nächsten Handelstag?",
            "Was mache ich, wenn ich ein Signal verpasst habe?",
            "Wann zählt das Signal: Schlusskurs, Kurs im Tagesverlauf oder Futures?",
            "Wie bekomme ich eine Meldung, wenn ein Signal entsteht?",
            "Warum bekomme ich von meinem Broker Verlustmeldungen?",
            "Kann ich die 200-Tage-Linie mit einer Stop-Loss-Order automatisieren?",
            "Wer handelt für mich, wenn ich es nicht kann?",
        ],
    ),
    (
        "Produkte und Hebel",
        [
            "Welcher Index gibt das Signal, etwa bei einem MSCI World 2x?",
            "Ich halte zwei Hebelprodukte, etwa World und Nasdaq-100. Ein Signal oder zwei?",
            "2x oder 3x: ist mehr Hebel besser, wenn der Filter mich schützt?",
            "Trägt der Filter noch, wenn mein Gesamthebel niedrig ist?",
            "Funktioniert die 200-Tage-Linie auch mit einem ETF ohne Hebel?",
            "Warum weicht mein Produkt von Index mal Hebel ab?",
            "Wird bei einem Euro-Produkt auf einen US-Index die Währung mitgehebelt?",
            "Kann ich unter der Linie short gehen?",
            "Kann ich beim Kaufsignal zusätzlich mit Kredit einsteigen?",
            "Was passiert, wenn das Produkt geschlossen wird?",
        ],
    ),
    (
        "Parameter und Rechnung",
        [
            "Warum weicht eure 200-Tage-Linie von TradingView oder meinem Broker ab?",
            "Warum 200 Tage, und warum zeigt ihr Bereiche statt einer besten Zahl?",
            "Was bringt ein Puffer um die Linie, etwa 3 Prozent?",
            "Wie rechne ich eine fremde Fensterzahl in Handelstage um?",
            "SMA oder EMA: kann ich einen exponentiellen Durchschnitt nehmen?",
            "Warum rechnet ihr auf dem Index und nicht auf dem Kurs meines Produkts?",
            "Was macht der Wechselkurs mit dem Signal?",
        ],
    ),
    (
        "Rückrechnung und Risiko",
        [
            "Wie tief können die Rückgänge (Drawdowns) trotz Filter werden?",
            "Wie oft gibt es Fehlsignale, und was kosten sie?",
            "Kann ein gehebeltes Produkt auf null fallen?",
            "Funktioniert die 200-Tage-Linie noch, oder ist das Overfitting?",
            "Wie verlässlich sind die Rückrechnungen auf dieser Seite?",
            "Schlägt die Trendfolge Buy and Hold, und womit vergleiche ich sie?",
            "Wie lange muss ich durchhalten, bevor ich über die Regel urteilen kann?",
        ],
    ),
    (
        "Steuern",
        [
            "Was kostet mich das an Steuern?",
            "Was passiert mit Verlusten aus Fehlsignalen, und was ist mit dem Pauschbetrag?",
            "Zählt die Vorabpauschale auch gegen die Trendfolge?",
            "Kann ich das über ein Wikifolio oder ein Zertifikat laufen lassen?",
            "Was macht die Wash-Sale-Regel mit der Trendfolge?",
        ],
    ),
]

EXPECTED_HFEA: list[tuple[str, list[str]]] = [
    (
        "Einstieg und erste Schritte",
        [
            "Was ist HFEA (Hedgefundie's Excellent Adventure)?",
            "Was heißt gehebelt?",
            "Mit wie wenig Geld geht das?",
            "Muss ich auf einen guten Einstiegszeitpunkt warten?",
            "Was ist, wenn ich schon investiert bin?",
        ],
    ),
    (
        "Rebalancing und Alltag",
        [
            "Wie oft muss ich handeln?",
            "Rebalancing: warum quartalsweise und nicht monatlich oder nach Band?",
            "Was mache ich, wenn ich einen Termin verpasst habe?",
            "Kann ich in HFEA einen Sparplan laufen lassen?",
        ],
    ),
    (
        "Aufteilung und Anleihebein",
        [
            "55/45 oder 40/60: welche Aufteilung von UPRO und TMF ist richtig?",
            "Warum rechnet die Seite nur eine Fassung?",
            "Kann ich Gold oder Cash statt Anleihen als zweites Bein nehmen?",
            "Was passiert, wenn Aktien und Anleihen gleichzeitig fallen?",
            "Ist HFEA nach 2022 tot? Was der Absturz von TMF bedeutet",
            "Was machen hohe Zinsen mit HFEA?",
            "Wie stark reagiert TMF auf steigende Zinsen?",
            "Was hat HFEA mit Risk Parity zu tun?",
            "Kann ich HFEA mit der 200-Tage-Linie (SMA 200) kombinieren?",
        ],
    ),
    (
        "Produkte und Hebel",
        [
            "Warum TMF und nicht einfach 100 Prozent UPRO?",
            "Geht HFEA auch ohne Hebel?",
            "HFEA mit dem Nasdaq-100 (TQQQ) statt dem S&P 500?",
            "Was ist mit dem Emittentenrisiko des gehebelten Anleihe-ETP?",
            "Was passiert, wenn ein Produkt geschlossen wird?",
        ],
    ),
    (
        "Rückrechnung und Risiko",
        [
            "Wie tief können die Rückgänge (Drawdowns) von HFEA werden?",
            "Wie verlässlich sind die langen Rückrechnungen, die man online findet?",
            "Hat HFEA den S&P 500 geschlagen, und womit vergleiche ich?",
            "Wie lange muss ein Zeitraum sein, bevor er etwas über die Regel sagt?",
        ],
    ),
    (
        "Steuern und Region",
        [
            "Was kostet mich das an Steuern?",
            "Wie viel Steuer kostet das Zurückschichten grob?",
            "Kann ich das über ein Wikifolio oder ein Zertifikat laufen lassen?",
            "HFEA in Deutschland: kann ich UPRO und TMF kaufen, und was gibt es stattdessen?",
            "Was ist mit dem Währungsrisiko?",
        ],
    ),
]


@dataclass
class Question:
    title: str | None
    h3_count: int
    paragraphs: list[str]  # paragraphs of the answer, lines joined with spaces


@dataclass
class Category:
    title: str
    intro: str = ""
    questions: list[Question] = field(default_factory=list)


def chapter_end(lines: list[str]) -> str:
    """Upper bound of the chapter faq: ``sources`` in the V5 schema (chapter ``## rule``), else ``weiterlesen``."""
    return "sources" if "## rule" in lines else "weiterlesen"


def chapter(text: str, name: str = "faq", end: str | None = None) -> str:
    lines = text.splitlines()
    if end is None:
        end = chapter_end(lines)
    start = lines.index(f"## {name}")
    stop = lines.index(f"## {end}")
    return "\n".join(lines[start:stop])


def paragraphs(lines: list[str]) -> list[str]:
    result: list[str] = []
    current: list[str] = []
    for line in lines:
        if line.strip():
            current.append(line.strip())
        elif current:
            result.append(" ".join(current))
            current = []
    if current:
        result.append(" ".join(current))
    return result


def normalize(text: str) -> str:
    """Paragraphs joined, connected with a blank line (acceptance 1)."""
    return "\n\n".join(paragraphs(text.splitlines()))


def has_number(text: str, number: str) -> bool:
    """``number`` stands as its own number in the text, without decimals (acceptance: whole percent)."""
    return re.search(rf"(?<![\d,.]){re.escape(number)}(?![\d,.]\d)", text) is not None


def near(text: str, word: str, number: str, distance: int = 40) -> bool:
    """Word and number in the same sentence at most ``distance`` characters apart, in both directions.

    ``word`` is a pattern such as ``r"(?:Mischung|55/45)"``; the number counts as a
    whole number as in ``has_number``.
    """
    number_pattern = rf"(?<![\d,.]){re.escape(number)}(?![\d,.]\d)"
    if re.search(word + rf"[^.!?]{{0,{distance}}}" + number_pattern, text):
        return True
    return re.search(number_pattern + rf"[^.!?]{{0,{distance}}}" + word, text) is not None


def decline(text: str, number: str, loss: str) -> bool:
    """Value ``number`` as a decline: the same sentence carries ``loss`` (for example ``minus``)."""
    return near(text, loss, number, distance=100)


def parse_faq(faq: str) -> list[Category]:
    """Categories with intro and questions; :::market wrappers are skipped."""
    categories: list[Category] = []
    lines = faq.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("### "):
            category = Category(line[4:].strip())
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            intro: list[str] = []
            while j < len(lines) and lines[j].strip() and not lines[j].startswith(":::"):
                intro.append(lines[j].strip())
                j += 1
            category.intro = " ".join(intro)
            categories.append(category)
            i = j
            continue
        if line.strip() == ":::faq":
            content: list[str] = []
            i += 1
            while i < len(lines) and lines[i].strip() != ":::":
                content.append(lines[i])
                i += 1
            h3 = [z for z in content if z.startswith("### ")]
            title = h3[0][4:].strip() if h3 else None
            rest = content[content.index(h3[0]) + 1 :] if h3 else content
            question = Question(title, len(h3), paragraphs(rest))
            if not categories:
                categories.append(Category("(ohne Kategorie)"))
            categories[-1].questions.append(question)
        i += 1
    return categories


def without_faq(text: str, titles: tuple[str, ...]) -> str:
    """Chapter in which the :::faq containers for ``titles`` carry only question and mark.

    Wave hfea-faq-zahlen: the wave defines the wording of these answers anew;
    the rest of the chapter stays verbatim (WordingTest).
    """
    lines = text.splitlines()
    result: list[str] = []
    i = 0
    while i < len(lines):
        if lines[i].strip() == ":::faq":
            end = i + 1
            while end < len(lines) and lines[end].strip() != ":::":
                end += 1
            h3 = [z for z in lines[i + 1 : end] if z.startswith("### ")]
            if h3 and h3[0][4:].strip() in titles:
                result.extend([":::faq", "", h3[0], "", "<wortlaut neu>", "", ":::", ""])
                i = end + 1
                continue
        result.append(lines[i])
        i += 1
    return "\n".join(result)


def count_sentences(text: str, language: str = "de") -> int:
    """Counts sentences: a sentence ends on . ? ! before whitespace and a capital letter or at the end.

    ``language="en"`` knows the English abbreviations instead of the German ones
    (``vs.``, ``e.g.``, ``i.e.``, ``U.S.``, ``approx.``).
    """
    count = 0
    start = r"[A-Z\"“'(\[]" if language == "en" else r"[A-ZÄÖÜ\"„(\[]"
    for match in re.finditer(rf"[.!?](?=\s+{start}|\s*$)", text):
        before = text[: match.start()]
        word = re.search(r"([\wÄÖÜäöüß]+)$", before)
        if match.group() == "." and word:
            token = word.group(1)
            if language == "en":
                abbreviation = ABBREVIATIONS_EN.search(before) is not None
            else:
                abbreviation = token.lower() in ABBREVIATIONS
            # Ordinal such as "8. Oktober"; "S&P 500." on the other hand ends a sentence.
            if abbreviation or (language == "de" and token.isdigit() and len(token) <= 2):
                if match.end() < len(text.rstrip()):
                    continue
        count += 1
    return count


def markets_per_question(faq: str) -> list[str | None]:
    """Per ``:::faq`` of the chapter the code of the surrounding ``:::market`` wrapper (None without wrapper)."""
    codes: list[str | None] = []
    open_codes: list[str] = []
    in_question = False
    for line in faq.splitlines():
        s = line.strip()
        if in_question:
            if s == ":::":
                in_question = False
            continue
        if s == ":::faq":
            in_question = True
            codes.append(" / ".join(open_codes) or None)
        elif s.startswith(":::market"):
            open_codes.append(s[len(":::market") :].strip())
        elif s == ":::" and open_codes:
            open_codes.pop()
    return codes


def urls(text: str) -> list[str]:
    return sorted(u.rstrip(".,;:") for u in URL.findall(text))


def anchors(text: str) -> list[str]:
    return sorted(LINK_ANCHOR.findall(text))


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


PAGES = (("sma-trend.de.md", SMA), ("hfea.de.md", HFEA))
PAGES_EN = (("sma-trend.en.md", SMA_EN), ("hfea.en.md", HFEA_EN))
# (name, German file, English file, total questions, title of the German tax category)
PAIRS = (
    ("sma-trend", SMA, SMA_EN, 45, "Steuern"),
    ("hfea", HFEA, HFEA_EN, 32, "Steuern und Region"),
)


def answer(path: Path, title: str) -> list[str]:
    """Paragraphs of the answer to question ``title``; the question must be in the chapter faq."""
    for category in parse_faq(chapter(read(path))):
        for question in category.questions:
            if question.title == title:
                return question.paragraphs
    raise AssertionError(f"question missing in chapter faq: {title}")


class HelpersTest(unittest.TestCase):
    """The sentence count does not split at abbreviations and ordinals."""

    def test_sentences(self) -> None:
        self.assertEqual(count_sentences("Zwei. Jede Fassung gehört zu einem Produkt."), 2)
        self.assertEqual(count_sentences("Nach § 43a Abs. 3 EStG gilt das. Stand 8. Oktober 2026."), 2)
        self.assertEqual(count_sentences("Ein Satz, mit 1.000 Euro."), 1)
        self.assertEqual(count_sentences("Eins. Zwei! Drei?"), 3)
        self.assertEqual(count_sentences("Nicht der S&P 500. Eine fremde Reihe. Und noch einer."), 3)

    def test_sentences_english(self) -> None:
        """Wave strategie-faq-inhalt-en: English abbreviations do not end a sentence."""
        text = "Approx. US$ 5 in the U.S. Treasury market, e.g. Nasdaq-100, i.e. S&P 500 vs. MSCI World. Done."
        self.assertEqual(count_sentences(text, "en"), 2)
        self.assertEqual(count_sentences("See Rev. Rul. 2008-5 for details. It applies.", "en"), 2)
        self.assertEqual(count_sentences("One. Two! Three?", "en"), 3)
        self.assertEqual(count_sentences("Not the S&P 500. Another series.", "en"), 2)

    def test_markets_per_question(self) -> None:
        faq = "\n".join(
            [":::faq", "### A", "x", ":::", ":::market eu", ":::faq", "### B", "y", ":::", ":::", ":::faq", ":::"]
        )
        self.assertEqual(markets_per_question(faq), [None, "eu", None])


class StructureTest(unittest.TestCase):
    """Every :::faq has exactly one question; short answer and chapter reference."""

    def test_each_question_has_exactly_one_h3(self) -> None:
        for name, path in PAGES:
            for category in parse_faq(chapter(read(path))):
                for question in category.questions:
                    with self.subTest(page=name, question=question.title):
                        self.assertEqual(question.h3_count, 1)

    def test_short_answer(self) -> None:
        for name, path in PAGES:
            for category in parse_faq(chapter(read(path))):
                for question in category.questions:
                    with self.subTest(page=name, question=question.title):
                        self.assertTrue(question.paragraphs, "answer without paragraph")
                        short = question.paragraphs[0]
                        self.assertLessEqual(len(short), 320, short)
                        self.assertLessEqual(count_sentences(short), 2, short)
                        self.assertRegex(short, r"[.?!]$")
                        self.assertNotIn("LETF.io", short)

    def test_short_answer_is_own_paragraph(self) -> None:
        """At least one further paragraph follows the short answer (long answer or reference)."""
        for name, path in PAGES:
            for category in parse_faq(chapter(read(path))):
                for question in category.questions:
                    with self.subTest(page=name, question=question.title):
                        self.assertGreaterEqual(len(question.paragraphs), 2)

    def test_chapter_reference(self) -> None:
        for name, path in PAGES:
            with_reference = 0
            questions = 0
            for category in parse_faq(chapter(read(path))):
                for question in category.questions:
                    questions += 1
                    last = question.paragraphs[-1] if question.paragraphs else ""
                    if not last.startswith(REFERENCE_START):
                        continue
                    with_reference += 1
                    with self.subTest(page=name, question=question.title):
                        match = REFERENCE.match(last)
                        self.assertIsNotNone(match, last)
                        assert match is not None
                        self.assertIn(match.group(1), ALLOWED_ANCHORS)
            with self.subTest(page=name, check="almost every answer"):
                self.assertGreaterEqual(with_reference, questions - 2)

    def test_internal_links_only_to_chapters(self) -> None:
        for name, path in PAGES:
            for anchor in LINK_ANCHOR.findall(chapter(read(path))):
                with self.subTest(page=name, anchor=anchor):
                    self.assertIn(anchor, ALLOWED_ANCHORS)

    def test_no_see_above(self) -> None:
        for name, path in PAGES:
            with self.subTest(page=name):
                self.assertNotIn("weiter oben", chapter(read(path)))


class QuestionListTest(unittest.TestCase):
    """Categories and questions in the order of appendices A and B."""

    def check(self, path: Path, expected: list[tuple[str, list[str]]], count: int, first: str) -> None:
        categories = parse_faq(chapter(read(path)))
        titles = [q.title for c in categories for q in c.questions]
        self.assertEqual(len(titles), count)
        self.assertEqual(titles[0], first)
        self.assertEqual([(c.title, [q.title for q in c.questions]) for c in categories], expected)

    def test_sma(self) -> None:
        self.check(SMA, EXPECTED_SMA, 45, "Was ist die 200-Tage-Linie, und wie lautet die Regel?")

    def test_hfea(self) -> None:
        self.check(HFEA, EXPECTED_HFEA, 32, "Was ist HFEA (Hedgefundie's Excellent Adventure)?")


class WordingTest(unittest.TestCase):
    """Chapter faq verbatim appendix A or B plus the five evidence items (SHA-256 of the normalized chapter).

    HASH_APPENDIX_A and HASH_APPENDIX_B carry the state after acceptance 1 to 5 of the
    wave strategie-faq-namen (appendix A or B of the previous wave, only the five
    spots of acceptance changed). The chapter is compared after
    joining the line breaks; every other line must stay the same.

    Wave hfea-faq-zahlen: for HFEA the comparison excludes the three answers
    of the acceptance spots (drawdowns, long backtests, 2022), whose wording the
    wave defines anew; everything else stays verbatim.
    """

    def test_sma(self) -> None:
        # Wave struktur-v5-inhalt: the link targets moved to the V5 anchors; they are mapped
        # back to the old anchors before hashing, so the lock protects the wording as strictly as before.
        text = normalize(old_link_targets(chapter(read(SMA))))
        self.assertEqual(hashlib.sha256(text.encode("utf-8")).hexdigest(), HASH_APPENDIX_A)

    def test_hfea(self) -> None:
        # Wave struktur-v5-hfea: same mapping as for SMA; HASH_APPENDIX_B stays unchanged.
        text = old_link_targets(chapter(read(HFEA)))
        text = normalize(without_faq(text, tuple(NUMBERS_DE.values())))
        self.assertEqual(hashlib.sha256(text.encode("utf-8")).hexdigest(), HASH_APPENDIX_B)


OLD_ANCHOR = {
    "rule": "regel",
    "backtest": "rueckschau",
    "parameters": "parameter",
    "math": "herleitung",
    "examples": "beispiele",
    "staying-invested": "dabeibleiben",
    "mistakes": "fehler",
    "tradeoffs": "abwaegung",
    "implementation": "region",
    "history": "geschichte",
    "criticism": "kritik",
    "sources": "quellen",
}


def old_link_targets(text: str) -> str:
    """Maps the V5 link targets ``](#rule)`` back to the old anchors ``](#regel)``."""
    return re.sub(
        r"\]\(#([a-z-]+)\)",
        lambda match: f"](#{OLD_ANCHOR.get(match.group(1), match.group(1))})",
        text,
    )


class CorrectionsTest(unittest.TestCase):
    """BAU-3: old sentences are gone, the corrected ones are there."""

    def test_sma(self) -> None:
        faq = chapter(read(SMA))
        self.assertNotIn("denselben Schwankungsschaden", re.sub(r"\s+", " ", faq))
        for sentence in (
            "Short-Produkt trägt einen größeren Schwankungsschaden als ein Long-Produkt",
            "innerhalb von 30 Tagen vor oder nach",
            "Rev. Rul. 2008-5",
            "nur an, wenn der Basiszins positiv",
            "(§ 19 Abs. 1 InvStG)",
            "gegenüber dem L-fachen des Marktes",
            "Oktober 2000 bis Oktober 2026",
        ):
            with self.subTest(sentence=sentence):
                self.assertIn(sentence, re.sub(r"\s+", " ", faq))

    def test_hfea(self) -> None:
        faq = chapter(read(HFEA))
        for old in ("fünffach gehebelt", "nur so weit, wie es sie gibt", "steht in der Regelkarte"):
            with self.subTest(old=old):
                self.assertNotIn(old, re.sub(r"\s+", " ", faq))
        # "beginnt derzeit im Juli 2021" and "Stand 8. Oktober 2026" are replaced by
        # the wave hfea-faq-zahlen at exactly these spots; the numbers themselves,
        # including those of 2022, are checked by HfeaNumbersTest.
        for sentence in ("TMF verlor rund 73 Prozent",):
            with self.subTest(sentence=sentence):
                self.assertIn(sentence, re.sub(r"\s+", " ", faq))


class EvidenceTest(unittest.TestCase):
    """Wave strategie-faq-namen: five evidence items stand again with name and link in the text.

    Acceptance of the spec, sentences 1 to 5. Comparison is after joining the
    line breaks of a paragraph (``answer`` returns the paragraphs that way).
    """

    def test_sma_clarification(self) -> None:
        """Sentence 1: the sentence ends with the clarification on reddit.com."""
        text = " ".join(answer(SMA, "Warum weicht eure 200-Tage-Linie von TradingView oder meinem Broker ab?"))
        ending = "ist der häufigste Fall ([Klarstellung dazu](https://www.reddit.com/comments/1o21g35/_/njep35a))."
        self.assertIn(ending, text)

    def test_hfea_rebalancing_sources(self) -> None:
        """Sentence 2: the brackets name modern_football and Allocate Smartly."""
        text = " ".join(answer(HFEA, "Rebalancing: warum quartalsweise und nicht monatlich oder nach Band?"))
        brackets = (
            "([modern_football](https://redd.it/ttg5ok), "
            "[Allocate Smartly](https://allocatesmartly.com/alternate-trading-days-important-analytical-tool/))"
        )
        self.assertIn(brackets, text)

    def test_hfea_gold_cash_part6(self) -> None:
        """Sentence 3: the sentence reads with the evidence item ZahlGraf, part 6."""
        text = " ".join(answer(HFEA, "Kann ich Gold oder Cash statt Anleihen als zweites Bein nehmen?"))
        sentence = (
            "Beides ergibt eine andere Fassung, und beides ist öffentlich nachgerechnet worden "
            "([ZahlGraf, Teil 6](https://redd.it/srkunv))."
        )
        self.assertIn(sentence, text)

    def test_hfea_sma200_part9(self) -> None:
        """Sentence 4: the paragraph after the short answer refers to part 9 of the series by ZahlGraf."""
        paragraphs = answer(HFEA, "Kann ich HFEA mit der 200-Tage-Linie (SMA 200) kombinieren?")
        expected = (
            "Das ist eine eigene Fassung, und es gibt sie: [Teil 9 der Reihe von ZahlGraf](https://redd.it/t82roi) "
            "rechnet die Kombination durch und kommt dabei auf ein niedrigeres Risiko als bei HFEA allein."
        )
        self.assertEqual(paragraphs[1], expected)

    def test_hfea_nasdaq_part7(self) -> None:
        """Sentence 5: the paragraph after the short answer refers to part 7 of the series by ZahlGraf."""
        paragraphs = answer(HFEA, "HFEA mit dem Nasdaq-100 (TQQQ) statt dem S&P 500?")
        expected = (
            "Eine eigene Fassung, öffentlich nachgerechnet in [Teil 7 der Reihe von ZahlGraf](https://redd.it/sx4xxw). "
            "Dort steht der Nasdaq-100 allerdings nicht anstelle des breiten Index, "
            "sondern als Beimischung im wachstumsorientierten Teil."
        )
        self.assertEqual(paragraphs[1], expected)


class ComplianceTest(unittest.TestCase):
    """Acceptance 6: only the scene word stays forbidden, short answers without link and names."""

    def test_no_names_and_no_reddit(self) -> None:
        """Only Szene stays forbidden in the chapter faq; names and Reddit links are evidence (acceptance 6)."""
        for name, path in PAGES:
            faq = chapter(read(path))
            for word in ("Szene",):
                with self.subTest(page=name, word=word):
                    self.assertNotIn(word, faq)

    def test_short_answer_without_link_and_names(self) -> None:
        """Acceptance 6 (wave strategie-faq-namen): short answers carry no link and no name."""
        for name, path in PAGES:
            for category in parse_faq(chapter(read(path))):
                for question in category.questions:
                    with self.subTest(page=name, question=question.title):
                        short = question.paragraphs[0]
                        self.assertNotIn("](", short)
                        self.assertNotRegex(short, r"https?://")
                        self.assertNotIn("ZahlGraf", short)
                        self.assertNotIn("modern_football", short)

    def test_tax_notice(self) -> None:
        for name, path, category_title in (("sma", SMA, "Steuern"), ("hfea", HFEA, "Steuern und Region")):
            with self.subTest(page=name):
                categories = {c.title: c for c in parse_faq(chapter(read(path)))}
                self.assertIn(category_title, categories)
                self.assertTrue(categories[category_title].intro.endswith(TAX_NOTE))


class TestSchema(unittest.TestCase):
    """docs/frontmatter-schema.md describes the convention for the container :::faq."""

    def test_convention(self) -> None:
        text = read(SCHEMA)
        flat = re.sub(r"\s+", " ", text)
        self.assertIn("short answer", flat)
        self.assertIn("Mehr dazu im Kapitel [<Kapitel>](#<anker>).", flat)
        self.assertRegex(flat, r"short answer[^.]*first paragraph|first paragraph[^.]*short answer")
        self.assertRegex(flat, r"at most two sentences")

    def test_no_dash(self) -> None:
        text = read(SCHEMA)
        for dash in ("\u2013", "\u2014"):
            with self.subTest(dash=repr(dash)):
                self.assertNotIn(dash, text)


class FrontmatterCheckTest(unittest.TestCase):
    """check_frontmatter.py ends with exit 0; warnings only of the expected kinds."""

    def test_exit_and_warnings(self) -> None:
        run = subprocess.run(
            [sys.executable, "scripts/check_frontmatter.py"], cwd=ROOT, capture_output=True, text=True
        )
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        ranges = {}
        for name, path in PAGES + PAGES_EN:
            lines = read(path).splitlines()
            ranges[name] = (lines.index("## faq") + 1, lines.index(f"## {chapter_end(lines)}") + 1)
        for line in run.stdout.splitlines():
            if not line.startswith("WARNUNG"):
                continue
            if re.search(r"Kategorie \d+ .* führt \d+ Fragen, die deutsche", line) or "Markt" in line:
                continue
            # Other warnings (for example word hits) are only allowed outside the chapter faq;
            # the remaining chapters do not change in this wave.
            for name, (start, end) in ranges.items():
                match = re.search(re.escape(name) + r":(\d+)", line)
                if match is None:
                    continue
                with self.subTest(line=line):
                    self.assertFalse(start <= int(match.group(1)) < end, line)

    def test_no_category_warning(self) -> None:
        """Wave strategie-faq-inhalt-en: the categories of both languages count the same; market warnings only at/fr."""
        run = subprocess.run(
            [sys.executable, "scripts/check_frontmatter.py"], cwd=ROOT, capture_output=True, text=True
        )
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        for line in run.stdout.splitlines():
            if not line.startswith("WARNUNG"):
                continue
            with self.subTest(line=line):
                self.assertNotRegex(line, r"Kategorie \d+ .* führt \d+ Fragen, die deutsche")
                self.assertNotIn("FAQ-Kategorien der Sprachfassungen zählen verschieden", line)
                match = re.search(r"erreicht den Markt '([a-z]+)'", line)
                if match is not None:
                    self.assertIn(match.group(1), {"at", "fr"}, line)


class EnglishQuestionsTest(unittest.TestCase):
    """Wave strategie-faq-inhalt-en: categories, questions and market wrappers as in the German."""

    def test_question_count(self) -> None:
        for name, de, en, count, _ in PAIRS:
            categories_de = parse_faq(chapter(read(de)))
            categories_en = parse_faq(chapter(read(en)))
            with self.subTest(page=name, check="total"):
                self.assertEqual(sum(len(c.questions) for c in categories_en), count)
                self.assertEqual(chapter(read(en)).count(":::faq"), count)
                self.assertEqual(chapter(read(de)).count(":::faq"), count)
            with self.subTest(page=name, check="per category"):
                self.assertEqual(
                    [len(c.questions) for c in categories_en], [len(c.questions) for c in categories_de]
                )

    def test_each_question_has_exactly_one_h3(self) -> None:
        for name, path in PAGES_EN:
            for category in parse_faq(chapter(read(path))):
                for question in category.questions:
                    with self.subTest(page=name, question=question.title):
                        self.assertEqual(question.h3_count, 1)

    def test_markets_per_question(self) -> None:
        for name, de, en, _, _ in PAIRS:
            with self.subTest(page=name):
                self.assertEqual(markets_per_question(chapter(read(en))), markets_per_question(chapter(read(de))))


def paired_questions(de: Path, en: Path) -> list[tuple[Question, Question]]:
    """Questions of both languages paired by position; AssertionError when the counts differ."""
    categories_de = parse_faq(chapter(read(de)))
    categories_en = parse_faq(chapter(read(en)))
    counts_de = [len(c.questions) for c in categories_de]
    counts_en = [len(c.questions) for c in categories_en]
    if counts_de != counts_en:
        raise AssertionError(f"questions per category: German {counts_de}, English {counts_en}")
    return [
        (question_de, question_en)
        for category_de, category_en in zip(categories_de, categories_en)
        for question_de, question_en in zip(category_de.questions, category_en.questions)
    ]


class EnglishLinksTest(unittest.TestCase):
    """Per question exactly the URLs and internal anchors of the German answer."""

    def test_urls_and_anchors(self) -> None:
        for name, de, en, _, _ in PAIRS:
            for question_de, question_en in paired_questions(de, en):
                text_de = " ".join(question_de.paragraphs)
                text_en = " ".join(question_en.paragraphs)
                with self.subTest(page=name, question=question_de.title, check="urls"):
                    self.assertEqual(urls(text_en), urls(text_de), question_en.title)
                with self.subTest(page=name, question=question_de.title, check="anchors"):
                    self.assertEqual(anchors(text_en), anchors(text_de), question_en.title)


class EnglishShortAnswerTest(unittest.TestCase):
    """BAU-2: the first paragraph is the short answer; the more line becomes More in the chapter."""

    def test_short_answer(self) -> None:
        for name, path in PAGES_EN:
            for category in parse_faq(chapter(read(path))):
                for question in category.questions:
                    with self.subTest(page=name, question=question.title):
                        self.assertGreaterEqual(len(question.paragraphs), 2, "short answer without its own paragraph")
                        short = question.paragraphs[0]
                        self.assertLessEqual(len(short), 360, short)
                        self.assertLessEqual(count_sentences(short, "en"), 2, short)
                        self.assertRegex(short, r"[.?!]$")

    def test_chapter_reference(self) -> None:
        for name, de, en, _, _ in PAIRS:
            for question_de, question_en in paired_questions(de, en):
                last_de = question_de.paragraphs[-1] if question_de.paragraphs else ""
                last_en = question_en.paragraphs[-1] if question_en.paragraphs else ""
                match = REFERENCE_DE.match(last_de)
                with self.subTest(page=name, question=question_de.title):
                    if match is None:
                        self.assertFalse(last_en.startswith(REFERENCE_EN_START), last_en)
                        continue
                    self.assertIn(match.group(1), CHAPTER_EN)
                    expected = f"More in the chapter [{CHAPTER_EN[match.group(1)]}](#{match.group(2)})."
                    self.assertEqual(last_en, expected)

    def test_references_present(self) -> None:
        """Cross-check: the German page ends with the reference almost everywhere, the English one as often."""
        for name, de, en, _, _ in PAIRS:
            pairs = paired_questions(de, en)
            count_de = sum(
                1 for question_de, _ in pairs
                if question_de.paragraphs and REFERENCE_DE.match(question_de.paragraphs[-1])
            )
            count_en = sum(
                1 for _, question_en in pairs
                if question_en.paragraphs and question_en.paragraphs[-1].startswith(REFERENCE_EN_START)
            )
            with self.subTest(page=name):
                self.assertGreaterEqual(count_de, len(pairs) - 2)
                self.assertEqual(count_en, count_de)


class EnglishCorrectionsTest(unittest.TestCase):
    """Old sentences and German remnants are gone; the tax notice stands at the end of the intro."""

    def test_old_sentences_gone(self) -> None:
        for name, path in PAGES_EN:
            faq = re.sub(r"\s+", " ", chapter(read(path)))
            for old in ("Mehr dazu", "five times leveraged", "carries the same volatility drag"):
                with self.subTest(page=name, old=old):
                    self.assertNotIn(old, faq)

    def test_tax_notice(self) -> None:
        for name, de, en, _, tax_de in PAIRS:
            titles_de = [c.title for c in parse_faq(chapter(read(de)))]
            categories_en = parse_faq(chapter(read(en)))
            with self.subTest(page=name):
                self.assertIn(tax_de, titles_de)
                position = titles_de.index(tax_de)
                self.assertGreater(len(categories_en), position)
                self.assertTrue(
                    categories_en[position].intro.endswith(TAX_NOTE_EN),
                    categories_en[position].intro,
                )


class EnglishComplianceTest(unittest.TestCase):
    """Like ComplianceTest, for en with "scene" instead of "Szene"."""

    def test_no_scene(self) -> None:
        for name, path in PAGES_EN:
            with self.subTest(page=name):
                self.assertNotRegex(chapter(read(path)), r"(?i)\bscenes?\b")

    def test_short_answer_without_link_and_names(self) -> None:
        for name, path in PAGES_EN:
            for category in parse_faq(chapter(read(path))):
                for question in category.questions:
                    with self.subTest(page=name, question=question.title):
                        self.assertTrue(question.paragraphs, "answer without paragraph")
                        short = question.paragraphs[0]
                        self.assertNotIn("](", short)
                        self.assertNotRegex(short, r"https?://")
                        for word in ("ZahlGraf", "modern_football", "LETF.io"):
                            self.assertNotIn(word, short)


class NoDashTest(unittest.TestCase):
    """No characters U+2013 and U+2014 in the lines that the wave adds.

    Wave hfea-faq-zahlen: the changed lines of the German pages are checked
    as well (acceptance sentence 3).
    """

    def test_changed_lines(self) -> None:
        try:
            base = subprocess.run(
                ["git", "merge-base", "HEAD", "main"], cwd=ROOT, capture_output=True, text=True, check=True
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            self.skipTest("no git or no branch main")
        paths = [p.relative_to(ROOT).as_posix() for _, p in PAGES + PAGES_EN] + ["tests/test_faq_inhalt.py"]
        diff = subprocess.run(
            ["git", "diff", "--unified=0", base, "--", *paths],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        for line in diff.splitlines():
            if not line.startswith("+") or line.startswith("+++"):
                continue
            for dash in DASHES:
                with self.subTest(line=line[:80], dash=repr(dash)):
                    self.assertNotIn(dash, line)

    def test_faq_chapter_english(self) -> None:
        for name, path in PAGES_EN:
            faq = chapter(read(path))
            for dash in DASHES:
                with self.subTest(page=name, dash=repr(dash)):
                    self.assertNotIn(dash, faq)


# Wave hfea-faq-zahlen: the spots of the finding, per key the question of both languages.
NUMBERS_DE = {
    "drawdown": "Wie tief können die Rückgänge (Drawdowns) von HFEA werden?",
    "laengst": "Wie verlässlich sind die langen Rückrechnungen, die man online findet?",
    "jahr2022": "Ist HFEA nach 2022 tot? Was der Absturz von TMF bedeutet",
}
NUMBERS_EN = {
    "drawdown": "How deep can the declines (drawdowns) of HFEA get?",
    "laengst": "How reliable are the long backtests found online?",
    "jahr2022": "Is HFEA dead after 2022? What the crash of TMF means",
}
NUMBER_PAGES = (
    ("hfea.de.md", HFEA, NUMBERS_DE, "de"),
    ("hfea.en.md", HFEA_EN, NUMBERS_EN, "en"),
)
LOSS_DE = r"(?:minus|verlor|verloren|Verlust|sank|fiel|endete|rückläufig)"
LOSS_EN = r"(?:minus|lost|fell|ended|declin|down)"


class HfeaNumbersTest(unittest.TestCase):
    """Wave hfea-faq-zahlen: start 2009-06-25 and the numbers of quant at the spots of the finding.

    Acceptance sentence 1: "Juli 2021", "July 2021" and "erst ab dann vorliegen" no
    longer occur in either file. Acceptance sentence 2: the values 2009-06-25
    (first real UPRO price, TMF from 2009-04-16), 71, 2023-10-27 (high 2021-12-27),
    minus 73, minus 57, minus 64 stand in the three answers of the finding, as
    whole percent and with their assignment (low, high, TMF, UPRO, mix);
    no square placeholder bracket remains.
    """

    def test_old_state_gone(self) -> None:
        """Sentence 1: the spots on the window from July 2021 are gone without replacement."""
        for name, path, _, _ in NUMBER_PAGES:
            text = re.sub(r"\s+", " ", read(path))
            for old in ("Juli 2021", "July 2021", "erst ab dann vorliegen"):
                with self.subTest(page=name, old=old):
                    self.assertFalse(old in text, f"{old} still stands in {name}")

    def test_start_and_decline(self) -> None:
        """Sentence 2 (finding on drawdowns and long backtests): start, 71, low and high."""
        for name, path, titles, language in NUMBER_PAGES:
            drawdown_text = " ".join(answer(path, titles["drawdown"]))
            long_text = " ".join(answer(path, titles["laengst"]))
            if language == "de":
                trough, peak, loss = r"(?:Tief|Tiefststand)", r"(?:Hoch|Höchststand)", LOSS_DE
            else:
                trough, peak, loss = r"(?:trough|low)", r"(?:high|peak)", LOSS_EN
            for number in ("71", "64", "2023-10-27", "2021-12-27"):
                with self.subTest(page=name, question="drawdown", value=number):
                    self.assertTrue(has_number(drawdown_text, number), f"{number} missing in {name}")
            with self.subTest(page=name, assignment="2022"):
                self.assertTrue(decline(drawdown_text, "64", loss), f"minus 64 missing in {name}")
            with self.subTest(page=name, assignment="low"):
                self.assertTrue(near(drawdown_text, trough, "2023-10-27"), f"low 2023-10-27 missing in {name}")
            with self.subTest(page=name, assignment="high"):
                self.assertTrue(near(drawdown_text, peak, "2021-12-27"), f"high 2021-12-27 missing in {name}")
            for number in ("2009-06-25", "2009-04-16"):
                with self.subTest(page=name, question="laengst", value=number):
                    self.assertTrue(has_number(long_text, number), f"{number} missing in {name}")
            with self.subTest(page=name, assignment="UPRO"):
                self.assertTrue(near(long_text, r"UPRO", "2009-06-25"), f"UPRO 2009-06-25 missing in {name}")
            with self.subTest(page=name, assignment="TMF"):
                self.assertTrue(near(long_text, r"TMF", "2009-04-16"), f"TMF 2009-04-16 missing in {name}")

    def test_values_2022(self) -> None:
        """Sentence 2 (finding on 2022): TMF minus 73, UPRO minus 57, mix minus 64."""
        for name, path, titles, language in NUMBER_PAGES:
            text = " ".join(answer(path, titles["jahr2022"]))
            mix = r"(?:Mischung|55/45)" if language == "de" else r"(?:mix|55/45)"
            loss = LOSS_DE if language == "de" else LOSS_EN
            for word, number in (("TMF", "73"), ("UPRO", "57"), (mix, "64")):
                with self.subTest(page=name, value=number):
                    self.assertTrue(near(text, word, number), f"{number} missing in {name}")
                    self.assertTrue(decline(text, number, loss), f"minus {number} missing in {name}")

    def test_no_placeholder_brackets(self) -> None:
        """Sentence 2: no square placeholder bracket remains at the spots of the finding."""
        placeholder = re.compile(r"\[[^\]]*\](?!\()")
        for name, path, titles, _ in NUMBER_PAGES:
            for spot in ("drawdown", "laengst", "jahr2022"):
                text = " ".join(answer(path, titles[spot]))
                match = placeholder.search(text)
                with self.subTest(page=name, spot=spot):
                    self.assertIsNone(match, f"placeholder {match} in {name}")


class TestStructureV5Hfea(unittest.TestCase):
    """Wave struktur-v5-hfea: hfea.de.md and hfea.en.md follow the V5 scheme like sma-trend."""

    V5_ORDER = [
        "rule", "examples", "backtest", "parameters", "implementation",
        "staying-invested", "mistakes", "history", "tradeoffs", "criticism",
        "math", "recompute", "faq", "sources",
    ]
    OLD_ANCHORS = set(OLD_ANCHOR.values()) | {"weiterlesen"}
    PACKAGE = (
        "https://github.com/Andre0512/letf-strategies/blob/main/"
        "examples/rebalancing/README.md"
    )
    MAUERSTRASSENWETTEN = "https://www.reddit.com/r/mauerstrassenwetten/"
    DROPPED = (
        "https://www.optimizedportfolio.com/hedgefundie-adventure/",
        "https://www.reddit.com/r/LETFs/",
    )

    @staticmethod
    def _h2(text: str) -> list[str]:
        return re.findall(r"(?m)^##[ \t]+(\S.*?)[ \t]*$", text)

    @staticmethod
    def _section(text: str, name: str) -> str:
        match = re.search(rf"(?ms)^##[ \t]+{re.escape(name)}[ \t]*$(.*?)(?=^##[ \t]|\Z)", text)
        return match.group(1) if match else ""

    @staticmethod
    def _sources(text: str) -> list[dict]:
        import yaml

        front = text.split("\n---", 1)[0].lstrip("-\n")
        return yaml.safe_load(front).get("sources") or []

    def test_h2_order_is_v5(self) -> None:
        for page in (HFEA, HFEA_EN):
            with self.subTest(page=page.name):
                self.assertEqual(self._h2(read(page)), self.V5_ORDER)

    def test_no_weiterlesen_one_recompute(self) -> None:
        for page in (HFEA, HFEA_EN):
            headings = self._h2(read(page))
            with self.subTest(page=page.name):
                self.assertEqual(headings.count("weiterlesen"), 0)
                self.assertEqual(headings.count("recompute"), 1)

    def test_recompute_intro_and_subsections(self) -> None:
        for page in (HFEA, HFEA_EN):
            body = self._section(read(page), "recompute")
            with self.subTest(page=page.name):
                first = re.search(r"(?m)^(###[ \t]|:::layer)", body)
                intro = body[: first.start()] if first else body
                self.assertGreaterEqual(len(intro.split()), 10, "intro before the first H3")
                h3 = re.findall(r"(?m)^###[ \t]+(\S.*?)[ \t]*$", body)
                # Wave strategie-nachrechnen-code: the nine H3, intro without
                # the quote box for agents.
                self.assertEqual(h3, self.RECOMPUTE_H3[page.name])
                self.assertIsNone(re.search(r"(?m)^>", intro), "quote in the intro")
                self.assertIsNone(re.search(r"(?i)agent", intro), "agent in the intro")

    RECOMPUTE_H3 = {
        "hfea.de.md": [
            "Was im Repository liegt", "Lokal ausführen",
            "Die Rechnung in Kurzform", "Die Parameter", "Datenregeln",
            "Die Spalten", "Warum zwei Pakete", "Warum erfundene Daten",
            "Was die Seite genauso rechnet",
        ],
        "hfea.en.md": [
            "What the repository holds", "Run it locally",
            "The calculation in short", "The parameters", "Data rules",
            "The columns", "Why two packages", "Why invented data",
            "What the page computes the same way",
        ],
    }
    DAY_BY_DAY = {"hfea.de.md": "Tag für Tag gerechnet", "hfea.en.md": "Day by day"}

    def _day_by_day(self, page) -> str:
        math = self._section(read(page), "math")
        parts = re.split(r"(?m)^###[ \t]+(\S.*?)[ \t]*$", math)
        if len(parts) < 3 or parts[-2] != self.DAY_BY_DAY[page.name]:
            return ""
        return parts[-1]

    def test_recompute_block_content(self) -> None:
        for page in (HFEA, HFEA_EN):
            body = self._section(read(page), "recompute")
            with self.subTest(page=page.name):
                self.assertIn(self.PACKAGE, body)
                self.assertGreaterEqual(len(re.findall(r"(?m)^\|.*\|[ \t]*$", body)), 9)
                for mark in ("$$", "\\frac", "\\begin", "\\lvert"):
                    self.assertNotIn(mark, body, f"formula {mark} in recompute")
                # Wave strategie-nachrechnen-code: pseudocode as a text block.
                self.assertRegex(body, r"(?m)^```text[ \t]*$", "no text block in recompute")
                days = self._day_by_day(page)
                self.assertTrue(days, "the last H3 of math is not day by day")
                self.assertIn(r"n_e = \frac{100\, w_e}{P_e(0)}", days)
                self.assertIn(r"\lvert w_e(t) - w_e \rvert \ge b", days)

    def test_math_keeps_derivation_without_compute_block(self) -> None:
        for page in (HFEA, HFEA_EN):
            body = self._section(read(page), "math")
            with self.subTest(page=page.name):
                self.assertIn(r"w_e(t) = \frac{w_e R_e}{w_e R_e + w_b R_b}", body)
                self.assertIn(r"w_i^{*}", body)
                self.assertNotIn(self.PACKAGE, body)
                self.assertNotIn("examples/", body)
                self.assertFalse(self._day_by_day(page).lstrip().startswith("**"))
        self.assertNotIn("Zum Nachrechnen", self._section(read(HFEA), "math"))

    def test_no_further_reading_forum_is_history_source(self) -> None:
        for page in (HFEA, HFEA_EN):
            sources = self._sources(read(page))
            urls = [source.get("url") for source in sources]
            with self.subTest(page=page.name):
                self.assertEqual(
                    [s.get("url") for s in sources if s.get("role") == "further_reading"], []
                )
                self.assertEqual(urls.count(self.MAUERSTRASSENWETTEN), 1)
                forum = next(s for s in sources if s.get("url") == self.MAUERSTRASSENWETTEN)
                self.assertEqual(forum.get("role"), "source")
                self.assertEqual(forum.get("supports"), ["history"])
                for url in self.DROPPED:
                    self.assertNotIn(url, urls)

    def test_supports_name_only_v5_anchors(self) -> None:
        for page in (HFEA, HFEA_EN):
            for source in self._sources(read(page)):
                with self.subTest(page=page.name, url=source.get("url")):
                    stale = set(source.get("supports") or []) & self.OLD_ANCHORS
                    self.assertEqual(stale, set())

    def test_chart_classes(self) -> None:
        for page in (HFEA, HFEA_EN):
            text = read(page)
            classes = re.findall(r"(?m)^:::chart\b[^\n]*\bclass=(\S+)", text)
            longterm = re.findall(
                r"(?m)^:::chart\b(?=[^\n]*\btype=longterm\b)(?=[^\n]*\bclass=backtest\b)", text
            )
            with self.subTest(page=page.name):
                self.assertEqual(classes.count("rueckschau"), 0)
                self.assertEqual(classes.count("puls"), 0)
                self.assertEqual(classes.count("backtest"), 2)
                self.assertEqual(classes.count("pulse"), 1)
                self.assertEqual(len(longterm), 1)


class FullRunTest(unittest.TestCase):
    """python3 -m unittest discover -s tests is green, including test_examples."""

    def test_example_packages_and_word_list(self) -> None:
        """test_examples checks the example packages and the word list outside the boxes."""
        run = subprocess.run(
            [sys.executable, "-m", "unittest", "tests.test_examples"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)


if __name__ == "__main__":
    unittest.main()
