"""Checks the chapter parameter of the German pages of SMA-Trendfolge and HFEA.

Wave strategie-parameter-text, section acceptance. Checked is: the chapter
parameter verbatim like appendix A and B, the sources from appendix C in the list
sources, the card form of the :::parameter cards, the order of the card keys, the
absence of the removed sentences, exit 0 of check_frontmatter.py, the run of the
named neighbours test_examples and test_faq_inhalt, this module docstring itself
and the card form in the schema. Appendices A and B are the contract data and
are checked themselves.

The tests are red as long as the chapters still carry the old state: old card
form without lead paragraphs, wrong order of the card keys, the removed
sentences still there, the sources from appendix C missing, the schema without
card form.

Contract (test author, 2026-10-12): the chapter reaches from the line
``## parameter`` to before ``## herleitung``; on a page in the V5 schema
(chapter ``## rule``, waves struktur-v5-inhalt for SMA and struktur-v5-hfea
for HFEA) it reaches from
``## parameters`` to before ``## implementation``. Normalized is like in
test_faq_inhalt: the lines of a paragraph joined with one space, paragraphs with
one blank line. A card is a ``:::parameter key=...`` up to the closing ``:::``;
its paragraphs begin after the opener. A lead paragraph begins with
``**<word>:** ``; the cost paragraph is the one paragraph with
``**Was es kostet:** `` or ``**Was es spart:** ``, a direction paragraph every
other lead paragraph.
"""

from __future__ import annotations

import re
import subprocess
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SMA = ROOT / "content" / "strategies" / "sma-trend.de.md"
HFEA = ROOT / "content" / "strategies" / "hfea.de.md"
SCHEMA = ROOT / "docs" / "frontmatter-schema.md"

PREFACE = re.compile(r"^\*\*[^*]+:\*\* ")
COST_BEGINNINGS = ("**Was es kostet:** ", "**Was es spart:** ")
HEADING = re.compile(r"^#{1,4} .*$")

PAGES = (("sma-trend.de.md", SMA), ("hfea.de.md", HFEA))

SMA_KEYS = [
    "window",
    "enter_buffer_pct",
    "exit_buffer_pct",
    "confirmation_days",
    "signal_series",
    "price_basis",
    "currency_basis",
    "execution_lag_days",
]
HFEA_KEYS = [
    "weight.slot_equity",
    "rebalance_period",
    "rebalance_trigger",
    "band.slot_equity",
    "cashflow_policy",
]

NEW_SOURCES_SMA = [
    {
        "title": "Symmetrischer und getrennter Puffer um den 190-Tage-Durchschnitt, S&P 500 ab 1885",
        "author": "Tystros (r/gehebelteETFs)",
        "year": 2025,
        "url": "https://www.reddit.com/comments/1huohxz/_/m6il18n",
        "kind": "forum",
        "lang": "de",
        "license": "unknown",
        "may_reproduce": False,
        "role": "source",
        "supports": ["parameter"],
    },
    {
        "title": "Getrennte Puffer für Kauf und Verkauf aus dem Backtest",
        "author": "deep0r (r/gehebelteETFs)",
        "year": 2025,
        "url": "https://www.reddit.com/comments/1huohxz/_/m5noufn",
        "kind": "forum",
        "lang": "de",
        "license": "unknown",
        "may_reproduce": False,
        "role": "source",
        "supports": ["parameter"],
    },
    {
        "title": "Signalwährung und Fensterlänge: Wechselkursschwankung verkürzt das Fenster",
        "author": "ChemicalStats (r/LETFs)",
        "year": 2026,
        "url": "https://www.reddit.com/comments/1rp9618/_/o9ncnct",
        "kind": "forum",
        "lang": "en",
        "license": "unknown",
        "may_reproduce": False,
        "role": "source",
        "supports": ["parameter"],
    },
]
ADDED_SOURCES_SMA = [
    "Eine kleine Reise in gehebelte Welten (Vectis Mundi), Teile I und II",
    "Leverage for the Long Run, Volltext der Dow-Award-Einreichung",
    "ChemStats Archiv: Strahlende Bullen, düstere Bären, Principia Amumbo, Teil V",
]

NEW_SOURCES_HFEA = [
    {
        "title": "Rebalance Timing Luck: The Difference between Hired and Fired",
        "author": "Corey Hoffstein, Justin Sibears, Nathan Faber (Newfound Research)",
        "year": 2019,
        "url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3319045",
        "kind": "paper",
        "lang": "en",
        "license": "all-rights-reserved",
        "may_reproduce": False,
        "role": "source",
        "supports": ["parameter"],
    },
]
ADDED_SOURCES_HFEA = ["Risikoparität als Herkunft der Aufteilung 40/60 im Ursprungsthread"]

# The removed sentences deliberately do not stand as a whole in this file.
FORBIDDEN_HFEA = (
    "fünf" + "fach",
    "Je weiter die Quote " + "von der Mitte weg",
    "beides zusammen bringt " + "vor allem mehr Handel",
)
FORBIDDEN_SMA = (
    "oft um " + "Wochen",
    "dreht später als " + "ein enger",
    "auf dem S&P 500 " + "fällt sie",
)

APPENDIX_A = """\
## parameters

Deine Fassung besteht aus wenigen Werten. Jeder verschiebt dieselbe Abwägung:
früher reagieren und öfter wechseln, oder später reagieren und seltener
wechseln. Hier steht, was jeder Wert tut, in welche Richtung er wirkt und was er
kostet. Die Zahlen selbst kommen aus deiner Fassung und stehen an jeder Karte.

Drei Werte entscheiden, **wann** ein Signal kommt: Fenster, Puffer und
Bestätigungstage. Drei weitere legen fest, **auf welcher Reihe** es entsteht:
Signalindex, Preisbasis und Signalwährung. Einer sagt, **wann gehandelt** wird.

:::parameter key=window
Das Fenster ist die Anzahl der Schlusskurse, aus denen der Durchschnitt
gebildet wird. Gezählt werden Handelstage, nicht Kalendertage.

**Länger:** Die Linie wird träger. Weniger Signale, dafür ein späterer
Ausstieg, wenn es wirklich abwärts geht, und ein späterer Wiedereinstieg.

**Kürzer:** Die Linie folgt dem Kurs enger. Du bist früher draußen und früher
wieder drin, wechselst aber öfter umsonst.

**Was es kostet:** Jeder Wechsel zahlt die Handelsspanne und, in einem
steuerpflichtigen Depot, Steuer auf realisierte Gewinne. Ein kürzeres Fenster
erzeugt mehr Wechsel pro Jahr und damit mehr von beidem.

Wer verschiedene Fenster nachrechnet, findet keinen einzelnen besten Wert,
sondern eine breite Zone mit ähnlichen Ergebnissen. Welche, hängt am Index und
am Zeitraum; das Panorama unten zeigt sie für dein Produkt.
:::

:::parameter key=enter_buffer_pct
Der Puffer legt ein Band um die Linie. Gekauft wird erst, wenn der Schlusskurs
die Linie um diesen Abstand erreicht oder überschreitet; verkauft wird erst,
wenn er sie um denselben Abstand unterschreitet. Der Abstand ist relativ zur
Linie, in Prozent.

**Größer:** Weniger Hin und Her dicht an der Linie. Dafür kommst du nach einem
Tief später zurück und verpasst einen Teil der Erholung.

**Kleiner:** Du bist früher wieder dabei und zahlst mehr Fehlwechsel, wenn der
Kurs um die Linie pendelt.

**Was es kostet:** Ohne Puffer mehr Spannen und Steuerereignisse, mit großem
Puffer ein Stück verpasster Bewegung auf beiden Seiten.

Die Rückrechnung auf dieser Seite setzt Einstieg und Ausstieg gleich; deshalb
gibt es dafür nur ein Panorama.
:::

:::parameter key=exit_buffer_pct
Der Ausstiegspuffer ist dieselbe Schwelle für die andere Richtung: Der
Schlusskurs muss die Linie um diesen Abstand unterschreiten, bevor verkauft
wird.

**Größer:** Du bleibst länger investiert, nimmst mehr vom Rückgang mit und
steigst seltener umsonst aus.

**Kleiner:** Du bist früher draußen und öfter umsonst.

**Was es kostet:** Jeder Fehlausstieg ist ein voller Umschlag: Spanne beim
Verkauf, Spanne beim Rückkauf und ein Steuerereignis dazwischen.

Dein Tracker kann beide Puffer getrennt führen. Die Presets und die
Rückrechnung dieser Seite setzen sie gleich. Getrennte Werte je Richtung werden
meist an der Vergangenheit ausgesucht und tragen damit dasselbe Risiko der
Überanpassung wie ein ausgesuchtes Fenster (Kapitel Kritik).
:::

:::parameter key=confirmation_days
Die Bestätigungstage verlangen, dass der neue Zustand an mehreren
Handelstagen hintereinander gilt, bevor er zählt. Ein Tag heißt: sofort.

**Mehr:** Ruhigere Signale, späteres Handeln.

**Weniger:** Schnelleres Handeln, mehr Fehlsignale.

**Was es kostet:** Dieselbe Währung wie beim Puffer, nur über die Zeit statt
über den Abstand: Wechsel und Spannen auf der einen Seite, verpasste Bewegung
auf der anderen.

Die Presets rechnen mit einem Tag. Dein Tracker kann mehr führen; die
Rückrechnung dieser Seite kennt noch keinen anderen Wert.
:::

:::parameter key=signal_series
Der Signalindex ist die Reihe, an der die Linie gezogen wird. Auf dieser Seite
ist das immer der ungehebelte Index deines Produkts, nie das gehebelte Produkt
selbst.

**Warum der Index:** Das gehebelte Produkt schwankt stärker und verliert in
Seitwärtsphasen Wert. Seine Linie würde öfter und an anderen Tagen kreuzen,
ohne dass der Markt etwas anderes getan hätte.

**Andere Reihe:** Sie kreuzt an anderen Tagen, auch wenn dein Produkt sich nicht
anders bewegt hat.

**Was es kostet:** Keine Gebühren, aber Signal und Bestand hängen weniger eng
zusammen.

Eine andere Reihe rechnet die Seite nicht.
:::

:::parameter key=price_basis
Die Preisbasis sagt, welche Variante des Index gerechnet wird. Die Seite
rechnet auf der Reihe mit wieder angelegten Erträgen: in Europa netto, also
nach Quellensteuer, in den USA brutto.

**Mit Erträgen:** Die Reihe mit wieder angelegten Erträgen wächst schneller als
der reine Kursindex und kreuzt die Linie deshalb an anderen Tagen.

**Netto statt brutto:** Die Nettoreihe wächst etwas langsamer als die
Bruttoreihe und kreuzt wieder anders.

**Was es kostet:** Keine Gebühren, aber andere Signaltage und damit andere
Ergebnisse.

Eine fremde Rückrechnung ist nur dann vergleichbar, wenn sie dieselbe Basis
benutzt; der Backtest dieser Seite nennt seine.
:::

:::parameter key=currency_basis
Die Signalwährung sagt, in welcher Währung die Signalreihe gerechnet wird:
Euro oder Dollar, sofern es den Index in beiden Währungen gibt.

**In Euro:** Die Reihe eines US-Markts enthält die Bewegung des Dollarkurses.
Die Linie verschiebt sich mit der Währung, auch wenn der Markt stillsteht.

**In Dollar:** Bei einem US-Markt bleibt der Wechselkurs aus dem Signal
heraus.

**Was es kostet:** Keine Gebühren, aber die Signaltage können sich
verschieben.

Deshalb lassen sich Fensterlängen nicht ohne Weiteres von einer Währung auf die
andere übertragen.
:::

:::parameter key=execution_lag_days
Die Ausführungsverzögerung sagt, wie viele Handelstage zwischen Signal und
Handel liegen.

**Null:** Die Rechnung unterstellt, dass du zum Schlusskurs des Signaltags
handelst. So rechnen die Presets dieser Seite.

**Ein Tag:** Du handelst am folgenden Handelstag, wie es in der Praxis meist
geschieht.

**Was es kostet:** Keine Gebühren, sondern Genauigkeit. Bei einem
europäischen Produkt auf einen US-Index schließt die Börse, an der du handelst,
vor dem Index. Mit null rechnet die Seite deshalb mit einem Kurs, der schon
feststand, bevor das Signal da war.
:::

**Was sonst noch mitrechnet.** Die Zeit außerhalb des Marktes verzinst der
Backtest mit dem Geldmarktsatz der Produktwährung. Steuer zieht er nur ab, wenn
du sie einschaltest; Handelsspannen zieht er nicht ab (Kapitel Backtest).

:::layer sources
**Was die Quellen belegen.** Dass sich statt eines Werts eine Zone brauchbarer
Fensterlängen findet, rechnen mehrere Auswertungen der Szene nach:
[Vectis Mundi](https://redd.it/1n6je6h) für den MSCI World und seine Regionen,
zusammengefasst in [Teil 5 der Wissenssammlung](https://redd.it/1qliqzn), dazu
der Kanal Notgroschen. Die Zone hängt an Index, Preisbasis und Währung: Auf dem
Preisindex landet eine Auswertung bei 275 Handelstagen, auf dem Index mit
wieder angelegten Nettoerträgen bei 255
([Klarstellung](https://www.reddit.com/comments/1o21g35/_/njep35a)); in
Dollar gerechnet liegen die robusten Fenster bei rund 280 bis 310 Tagen, in Euro
bei rund 190 bis 215 ([Principia Amumbo, Teil V](https://redd.it/1tw1in2)).

Dass ein Puffer auf dem S&P 500 die Zahl der Wechsel deutlich senkt, zeigt eine
[öffentliche Rückrechnung ab 1885](https://www.reddit.com/comments/1huohxz/_/m6il18n);
getrennte Werte je Richtung schneiden dort nur wenig besser ab als ein gemeinsamer
Wert. Dass zwischen dem Schluss eines US-Index und dem Handel in Europa eine Nacht
liegt, steht in derselben Wissenssammlung und in der Klarstellung oben.

**Was keine Quelle belegt.** Wie stark getrennte Puffer auf dem MSCI World wirken,
ist öffentlich nicht nachgerechnet. Keine der Arbeiten zeigt, dass eine Zone oder
ein Puffer in Zukunft so arbeitet; alle rechnen auf derselben Marktgeschichte.

**Offene Fragen.** Ob Bestätigungstage einen Vorteil gegenüber einem Puffer
bringen, ist kaum untersucht. Ebenso, wie weit sich Fensterlängen zwischen
Signalreihen übertragen lassen.

**Was LETF.io zeigt und was nicht.** Die Werte deiner Fassung kommen aus ihrer
Regelkarte; eine Suche nach dem besten Wert bieten wir nicht an.
:::
"""

APPENDIX_B = """\
## parameters

Diese Strategie hat wenige Stellschrauben. Eine legt die Aufteilung fest, drei
bestimmen, wann zurückgeschichtet wird, und eine regelt neues Geld. Hier steht,
was jede tut, in welche Richtung sie wirkt und was sie kostet. Die Zahlen selbst
kommen aus deiner Fassung und stehen an jeder Karte.

:::parameter key=weight.slot_equity
Die Aktienquote legt fest, welcher Anteil deines Strategiebetrags dem
Aktienbaustein folgt. Der Rest geht in den Anleihebaustein; beide ergeben
zusammen den ganzen Betrag, deshalb genügt eine Zahl.

**Höher:** Das Ergebnis wird aktienähnlicher, mit größeren Ausschlägen nach
oben und unten.

**Niedriger:** Mehr Gewicht auf der Anleiheseite und damit mehr Abhängigkeit
davon, dass Anleihen sich gegen Aktien bewegen.

**Was es kostet:** Wie weit die Gewichte zwischen zwei Terminen
auseinanderlaufen, hängt an der Quote: bei halb und halb am meisten, zu den
Rändern hin weniger. Eine Quote nahe der Mitte bewegt beim Zurückschichten also
etwas mehr Geld als eine weit außen; der Unterschied ist klein.
:::

:::parameter key=rebalance_period
Der Rhythmus sagt, in welchem Abstand die Termine liegen, an denen
zurückgeschichtet wird, von monatlich bis jährlich.

**Länger:** Weniger Handel, dafür laufen die Gewichte zwischen den Terminen
weiter von der Vorgabe weg.

**Kürzer:** Die Aufteilung bleibt näher an der Vorgabe, gehandelt wird öfter.

**Was es kostet:** Jeder Termin sind zwei Orders, also zweimal Spanne, und in
einem steuerpflichtigen Depot ein Steuerereignis auf der Seite, die verkauft
wird.

Welcher Kalendertag den Termin trägt, lässt sich kaum planen. Rückrechnungen
streuen mit dem Termin, ohne ein Muster, das sich vorab nutzen ließe.
:::

:::parameter key=rebalance_trigger
Der Auslöser sagt, was das Zurückschichten in Gang setzt. Es gibt drei
Möglichkeiten: nur der Termin, nur das Band, oder Termin und Band zusammen.

**Nur Termin:** An jedem Termin wird auf die Zielgewichte zurückgesetzt, egal
wie weit sie abgewichen sind.

**Nur Band:** Zurückgeschichtet wird an dem Tag, an dem ein Gewicht sein Band
verlässt, egal wann der letzte Termin war.

**Termin und Band:** Erst muss die Frist seit dem letzten Zurückschichten
abgelaufen sein, dann wird gewartet, bis ein Gewicht sein Band verlässt. Ohne
Bandbruch passiert nichts.

**Was es kostet:** Termin und Band zusammen handeln seltener als jedes für
sich, also mit weniger Spannen und Steuerereignissen. Der Preis: Eine
Abweichung innerhalb des Bands bleibt stehen.
:::

:::parameter key=band.slot_equity
Das Band ist die Abweichung vom Zielgewicht, die ohne Handlung zulässig ist,
in Prozentpunkten. Bei zwei Bausteinen weichen beide um denselben Betrag ab,
deshalb genügt eine Zahl. Das Band gilt nur, wenn der Auslöser ein Band
enthält.

**Breiter:** Seltener handeln, dafür läuft die Aufteilung weiter von der
Vorgabe weg.

**Enger:** Die Aufteilung bleibt genauer, gehandelt wird öfter.

**Was es kostet:** Spannen und Steuerereignisse gegen Genauigkeit.

Zusammen mit einem Termin kann das Band einen Termin nur ausfallen lassen,
nie einen zusätzlichen auslösen: Ein enges Band auf einem kurzen Rhythmus
handelt fast wie ein reiner Terminplan, ein breites lässt viele Termine aus.
Ein Bandbruch zählt am Schlusskurs desselben Tages, ohne Bestätigungstage.
:::

:::parameter key=cashflow_policy
Die Zuflussregel sagt, wohin neues Geld geht, das du einzahlst: nach den
Zielgewichten aufgeteilt, in einem festen Verhältnis, oder zuerst in den
Baustein, der gerade untergewichtet ist.

**Zuerst untergewichtet:** Der Zufluss schiebt die Aufteilung zurück zur
Vorgabe, ohne dass etwas verkauft wird.

**Nach Zielgewichten:** Der Fehlbetrag bleibt stehen; die Abweichung wird nur
verdünnt und dem nächsten Termin überlassen.

**Was es spart:** Was ein Zufluss ausgleicht, muss kein Verkauf ausgleichen,
und ein Verkauf ist in einem steuerpflichtigen Depot ein Steuerereignis. Je
größer das Depot im Verhältnis zur Rate, desto weniger reicht ein Zufluss, und
der Termin übernimmt wieder.

Die Regel gilt für deinen Tracker. Der Backtest dieser Seite rechnet ohne
Einzahlungen.
:::

:::layer sources
**Was die Quellen belegen.** Gewichte und Quartalsrhythmus stammen aus dem
[Ursprungsthread](https://www.bogleheads.org/forum/viewtopic.php?t=272007) und
sind dort am Ergebnis der eigenen Rückrechnung begründet. Dass der Termin des
Zurückschichtens streut, rechnet [modern_football](https://redd.it/ttg5ok) für
diese Strategie nach; dass sich daraus kein Termin vorab ablesen lässt, ist als
Rebalance Timing Luck
[allgemein beschrieben](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3319045).

**Was keine Quelle belegt.** Dass engere Bänder und kürzere Rhythmen genauer
an der Vorgabe bleiben und dafür öfter handeln, dass Termin und Band zusammen
seltener handeln als jedes allein und dass Zuflüsse in den untergewichteten
Baustein Verkäufe ersparen, folgt aus der Regel selbst; dass die Drift bei halb
und halb am größten ist, folgt aus der Rechnung. Für gehebelte Bausteine ist
keine dieser Aussagen eigens nachgerechnet, und keine Quelle findet einen
Rhythmus oder ein Band, das allen anderen überlegen ist.

**Offene Fragen.** Wie stark die Streuung über den Termin in einer Phase
steigender Zinsen ausfällt, ist offen.
:::

**Das Anleihebein** ist keine Zahl, sondern eine Produktwahl, und es verändert
die Strategie stärker als jede Einstellung. Die Seite rechnet die klassische
Fassung mit TMF, einem dreifach gehebelten Produkt auf US-Staatsanleihen mit
mehr als 20 Jahren Restlaufzeit, Ausschüttungen wieder angelegt. Welche
Bausteine es in Europa gibt, steht im Kapitel Umsetzung und Steuern.

**Was der Backtest nicht abzieht.** Spannen, Steuer und Einzahlungen rechnet
die Rückrechnung dieser Seite nicht; beide Bausteine laufen mit wieder
angelegten Ausschüttungen in Dollar.
"""


@dataclass
class Card:
    key: str
    paragraphs: list[str]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def chapter(text: str, name: str | None = None, end: str | None = None) -> str:
    lines = text.splitlines()
    v5 = "## rule" in lines
    if name is None:
        name = "parameters" if v5 else "parameter"
    if end is None:
        end = "implementation" if v5 else "herleitung"
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


def cards(boxes: str) -> list[Card]:
    """The :::parameter cards of a chapter with their paragraphs."""
    result: list[Card] = []
    lines = boxes.splitlines()
    i = 0
    while i < len(lines):
        if lines[i].startswith(":::parameter key="):
            key = lines[i].split("=", 1)[1].strip()
            content: list[str] = []
            i += 1
            while i < len(lines) and lines[i].strip() != ":::":
                content.append(lines[i])
                i += 1
            result.append(Card(key, paragraphs(content)))
        i += 1
    return result


def is_cost(paragraph: str) -> bool:
    return paragraph.startswith(COST_BEGINNINGS)


def has_lead(paragraph: str) -> bool:
    return PREFACE.match(paragraph) is not None


def form_errors(card: Card) -> list[str]:
    """Violations of the card form from acceptance 3, as short messages."""
    problems: list[str] = []
    leads = [n for n, a in enumerate(card.paragraphs) if has_lead(a)]
    if not leads:
        return ["no paragraph with a lead"]
    if leads[0] < 1:
        problems.append("no paragraph without a lead before the first lead")
    direction = [a for a in card.paragraphs if has_lead(a) and not is_cost(a)]
    if len(direction) < 2:
        problems.append(f"only {len(direction)} paragraphs with a direction lead")
    costs = [a for a in card.paragraphs if is_cost(a)]
    if len(costs) != 1:
        problems.append(f"{len(costs)} paragraphs with a cost lead")
    return problems


def frontmatter(text: str) -> str:
    lines = text.splitlines()
    assert lines[0] == "---", "file does not begin with the frontmatter"
    stop = lines.index("---", 1)
    return "\n".join(lines[1:stop])


def sources(path: Path) -> list[dict[str, object]]:
    data = yaml.safe_load(frontmatter(read(path)))
    assert isinstance(data, dict) and isinstance(data.get("sources"), list), "list sources is missing"
    return data["sources"]


def entry(source_list: list[dict[str, object]], title: str) -> dict[str, object]:
    hits = [q for q in source_list if q.get("title") == title]
    if len(hits) != 1:
        raise AssertionError(f"{len(hits)} entries with the title: {title}")
    return hits[0]


def container_section(text: str, needle: str) -> str | None:
    """Section under the first heading that names ``needle``."""
    lines = text.splitlines()
    for n, line in enumerate(lines):
        if not HEADING.match(line) or needle not in line:
            continue
        end = len(lines)
        for m in range(n + 1, len(lines)):
            if HEADING.match(lines[m]):
                end = m
                break
        return "\n".join(lines[n:end])
    return None


class TestAppendices(unittest.TestCase):
    """The appendices of this file are the contract data and fulfil the form themselves.

    Checks the transcription of appendices A and B: keys, card form, exactly
    one sources block, no removed sentences. Otherwise TestChapterVerbatim
    and the form tests of the files would contradict each other.
    """

    def check(self, chap: str, keys: list[str], forbidden: tuple[str, ...]) -> None:
        self.assertEqual([k.key for k in cards(chap)], keys)
        self.assertEqual(chap.count(":::layer sources"), 1)
        for card in cards(chap):
            with self.subTest(key=card.key):
                self.assertEqual(form_errors(card), [])
        text = re.sub(r"\s+", " ", chap)
        for sentence in forbidden:
            with self.subTest(sentence=sentence):
                self.assertNotIn(sentence, text)

    def test_sma(self) -> None:
        self.check(APPENDIX_A, SMA_KEYS, FORBIDDEN_SMA)

    def test_hfea(self) -> None:
        self.check(APPENDIX_B, HFEA_KEYS, FORBIDDEN_HFEA)


class TestChapterVerbatim(unittest.TestCase):
    """Acceptance 1: chapter parameter verbatim like appendix A or B (normalized)."""

    def test_sma(self) -> None:
        self.assertEqual(normalize(chapter(read(SMA))), normalize(APPENDIX_A))

    def test_hfea(self) -> None:
        self.assertEqual(normalize(chapter(read(HFEA))), normalize(APPENDIX_B))


class TestSources(unittest.TestCase):
    """Acceptance 2: the entries from appendix C with exactly these fields and values."""

    def test_sma_new_entries(self) -> None:
        listing = sources(SMA)
        for expected in NEW_SOURCES_SMA:
            # sma-trend follows the V5 scheme: the chapter anchor is "parameters".
            expected = {**expected, "supports": ["parameters"]}
            with self.subTest(title=expected["title"]):
                self.assertEqual(entry(listing, str(expected["title"])), expected)

    def test_hfea_new_entries(self) -> None:
        listing = sources(HFEA)
        for expected in NEW_SOURCES_HFEA:
            # hfea follows the V5 scheme (wave struktur-v5-hfea): the chapter anchor is "parameters".
            expected = {**expected, "supports": ["parameters"]}
            with self.subTest(title=expected["title"]):
                self.assertEqual(entry(listing, str(expected["title"])), expected)

    def test_sma_existing_sources_support_parameter(self) -> None:
        listing = sources(SMA)
        for title in ADDED_SOURCES_SMA:
            with self.subTest(title=title):
                # sma-trend follows the V5 scheme: the chapter anchor is "parameters".
                self.assertIn("parameters", entry(listing, title)["supports"])

    def test_hfea_existing_sources_support_parameter(self) -> None:
        listing = sources(HFEA)
        for title in ADDED_SOURCES_HFEA:
            with self.subTest(title=title):
                # hfea follows the V5 scheme (wave struktur-v5-hfea): the chapter anchor is "parameters".
                self.assertIn("parameters", entry(listing, title)["supports"])


class TestCardForm(unittest.TestCase):
    """Acceptance 3: prose first, two direction paragraphs, exactly one cost paragraph."""

    def test_cards(self) -> None:
        for name, path in PAGES:
            for card in cards(chapter(read(path))):
                with self.subTest(page=name, key=card.key):
                    self.assertEqual(form_errors(card), [])

    def test_exactly_one_sources_block(self) -> None:
        for name, path in PAGES:
            with self.subTest(page=name):
                self.assertEqual(chapter(read(path)).count(":::layer sources"), 1)


class TestRemovedSentences(unittest.TestCase):
    """Acceptance 4: the removed sentences no longer stand in the chapters."""

    def test_sma(self) -> None:
        text = re.sub(r"\s+", " ", chapter(read(SMA)))
        for sentence in FORBIDDEN_SMA:
            with self.subTest(sentence=sentence):
                self.assertNotIn(sentence, text)

    def test_hfea(self) -> None:
        text = re.sub(r"\s+", " ", chapter(read(HFEA)))
        for sentence in FORBIDDEN_HFEA:
            with self.subTest(sentence=sentence):
                self.assertNotIn(sentence, text)


class TestCardOrder(unittest.TestCase):
    """Acceptance 5: the card keys in the order of the spec."""

    def check(self, path: Path, expected: list[str]) -> None:
        keys = [k.key for k in cards(chapter(read(path)))]
        self.assertEqual(keys, expected)

    def test_sma(self) -> None:
        self.check(SMA, SMA_KEYS)

    def test_hfea(self) -> None:
        self.check(HFEA, HFEA_KEYS)


class TestChecker(unittest.TestCase):
    """Acceptance 6: check_frontmatter.py ends with exit 0, without error lines."""

    def test_exit_without_errors(self) -> None:
        run = subprocess.run(
            [sys.executable, "scripts/check_frontmatter.py"], cwd=ROOT, capture_output=True, text=True
        )
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        errors = [z for z in run.stdout.splitlines() if z.startswith("FEHLER")]
        self.assertEqual(errors, [], run.stdout)


class TestOverallRun(unittest.TestCase):
    """Acceptance 6: test_faq_inhalt and test_examples run green.

    Both named neighbours thus have a test. Both run green as soon as the new
    text stands: the guard
    ``TestAndereKapitelUnveraendert.test_rest_gleich`` in test_faq_inhalt takes
    the chapter parameter and the list sources out of the comparison for that.
    """

    def check(self, module: str) -> None:
        run = subprocess.run(
            [sys.executable, "-m", "unittest", module],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_examples_green(self) -> None:
        self.check("tests.test_examples")

    def test_faq_content_green(self) -> None:
        self.check("tests.test_faq_inhalt")


class TestModuleDocstring(unittest.TestCase):
    """Acceptance 7: the module docstring describes the check, without protocols."""

    def test_describes_the_check(self) -> None:
        doc = sys.modules[__name__].__doc__ or ""
        self.assertIn("chapter parameter", doc)
        self.assertIn("SMA", doc)
        self.assertIn("HFEA", doc)
        self.assertRegex(doc, r"check\w*")

    def test_no_protocols(self) -> None:
        """Working notes and handovers do not stand in the module docstring (acceptance 7)."""
        doc = sys.modules[__name__].__doc__ or ""
        for word in ("Runde", "Disponent", "Übergabe", "tests_review", "VERDICT", "Befund"):
            with self.subTest(word=word):
                self.assertNotIn(word, doc)


class TestSchema(unittest.TestCase):
    """Acceptance 8: the schema describes the card form for the container :::parameter."""

    def test_card_form_described(self) -> None:
        part = container_section(read(SCHEMA), ":::parameter")
        self.assertIsNotNone(part, "no section on the container :::parameter in the schema")
        assert part is not None
        flat = re.sub(r"\s+", " ", part)
        self.assertIn("prefix", flat)
        self.assertIn("Was es kostet", flat)
        self.assertIn("Was es spart", flat)
        self.assertRegex(flat, r"\*\*[^*]+:\*\*")

    def test_no_dash(self) -> None:
        text = read(SCHEMA)
        for dash in ("\u2013", "\u2014"):
            with self.subTest(dash=repr(dash)):
                self.assertNotIn(dash, text)


if __name__ == "__main__":
    unittest.main()
