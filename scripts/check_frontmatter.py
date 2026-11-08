#!/usr/bin/env python3
"""Prüft Frontmatter und Aufbau aller Content-Dateien gegen das Schema.

Das Schema ist in `docs/frontmatter-schema.md` beschrieben; dieses Skript ist
die verbindliche Fassung davon. Geprüft werden:

* Pflichtfelder, Typen und die geschlossenen Wertelisten für `kind` und
  `license`, dazu `origin` und `supports` je Quelle,
* die Quellenliste, in der einzig `url` fehlen darf, wenn ein Dokument keine
  öffentlich abrufbare Adresse hat, dazu `role`: eine Quelle mit `source` belegt
  mindestens ein Kapitel, eine mit `further_reading` steht mit ihrer Adresse als
  Link im Kapitel `weiterlesen`,
* jeder Eintrag in `definition_ids` gegen die committete Kopie der Preset-Slugs
  (`registry/strategy_preset_slugs.json`, erzeugt von
  `scripts/sync_preset_slugs.py`); ein Slug, der dort nicht steht, ist ein
  Fehler,
* der Aufbau: jede Seite trägt die Kapitelanker als H2 in fester Reihenfolge, und
  kein Kapitel steht ganz in `:::layer`-Kästen: Das Frontend zeigt einen Kasten
  zugeklappt, ein Kapitel nur aus Kästen wäre für die Leserin leer,
* die Container `:::layer`, `:::parameter`, `:::faq`, `:::example` und
  `:::chart` samt ihren Angaben, und die Paarigkeit der `$$`-Formelblöcke,
* der Container `:::market` samt seinen Marktcodes gegen `registry/markets.json`:
  er darf die anderen fünf umschließen, nie umgekehrt und nie sich selbst; beide
  Sprachfassungen führen je Kapitel dieselben Markt-Blöcke in derselben
  Reihenfolge, und kein Kapitel darf für eine Region des Registers leer sein,
* die Kategorien im Kapitel `faq`: eine H3 außerhalb der Container eröffnet
  dort eine Gruppe, und dann müssen alle Fragen in einer Gruppe stehen; der
  Mindestwert von zwei Fragen gilt je Markt aus dem Register, nicht über die
  Summe,
* der Ton der Ebene Verstehen gegen eine kleine Wortliste (Warnung, kein
  Fehler),
* die Vollständigkeit der Sprachfassungen. Eine fehlende englische Datei ist
  eine Warnung, eine fehlende deutsche ein Fehler.

Abhängigkeiten: Standardbibliothek + PyYAML.

Aufruf:
    python scripts/check_frontmatter.py [--content-dir content/strategies]
                                        [--registry registry/strategy_preset_slugs.json]
                                        [--parameter-keys registry/strategy_parameter_keys.json]
                                        [--markets registry/markets.json]

Exit-Code 0, wenn alles passt; 1 bei mindestens einem Fehler. Warnungen ändern
den Exit-Code nicht.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_CONTENT_DIR = Path("content/strategies")
DEFAULT_REGISTRY = REPO_ROOT / "registry" / "strategy_preset_slugs.json"
DEFAULT_PARAMETER_KEYS = REPO_ROOT / "registry" / "strategy_parameter_keys.json"
DEFAULT_MARKETS = REPO_ROOT / "registry" / "markets.json"

LANGUAGES = ("de", "en")

# Seit S10 gibt es nur noch Kernseiten: Was eine Region ändert, steht dort in
# `:::market`-Blöcken und nicht mehr in eigenen Dateien.
FILENAME_PATTERN = re.compile(r"^(?P<slug>[a-z0-9-]+)\.(?P<lang>de|en)\.md$")
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
REGION_PATTERN = re.compile(r"^[a-z]{2}$")
SOURCE_LANG_PATTERN = re.compile(r"^[a-z]{2}$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
URL_PATTERN = re.compile(r"^https?://\S+$")
ISIN_PATTERN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}\d$")

STATUS_VALUES = ("draft", "published")

# Kapitel als H2 mit festem Anker, Reihenfolge bindend (Vertrag, Plan v2 §10).
CORE_ANCHORS = (
    # Seit S11 trägt `regel` auch den Regel-Chart: Ein eigenes Kapitel `chart`
    # daneben zeigte dieselbe Figur ein zweites Mal und erklärte ihre Bedienung.
    "regel",
    "rueckschau",
    "parameter",
    "herleitung",
    "beispiele",
    "dabeibleiben",
    "fehler",
    "abwaegung",
    "region",
    # Seit S9 die Community-Geschichte der Strategie; mit S10 heißt sie
    # `geschichte` statt `herkunft`, näher an der Gliederung von Wikipedia.
    "geschichte",
    # Seit S10: die Einwände gegen die Strategie selbst. Anwenderfehler bleiben
    # im Kapitel `fehler`.
    "kritik",
    "faq",
    # Seit S10 getrennt nach der Logik von Wikipedia: `quellen` sind die
    # Einzelnachweise, `weiterlesen` die Reihen, Wikis, Videos und Blogs, auf die
    # die Seite zum Weiterlesen zeigt.
    "weiterlesen",
    "quellen",
)

FURTHER_READING_ANCHOR = "weiterlesen"

# Struktur V5 (Andre 2026-10-24): englische Kapitelanker, geordnet nach den vier
# Bereichen Lernen, Anwenden, Verstehen, Nachschlagen. `weiterlesen` entfällt,
# `recompute` ist das eigene Kapitel zum Nachrechnen. Für den Übergang gilt je
# Seite eines der beiden Schemata: eine Seite mit `## rule` folgt V5, jede
# andere den alten Ankern. Sobald alle Seiten umgestellt sind, fällt das alte
# Schema weg.
V5_ANCHORS = (
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
    "math",
    "recompute",
    "faq",
    "sources",
)
V5_MARKER_ANCHOR = "rule"

# Ebene 1 (Verstehen) steht außerhalb der Container, die beiden tieferen Ebenen
# stehen in `:::layer`.
LAYER_NAMES = ("compute", "sources")
CONTAINER_NAMES = ("layer", "parameter", "faq", "example", "chart")
LAYER_CONTAINER = "layer"

# Der Markt-Container (Vertrag S10). Er ist der einzige, der andere Container
# umschließen darf: `:::market de,eu` … `:::` blendet ein, was nur für bestimmte
# Märkte gilt, und alles außerhalb gilt für alle Märkte. Er steht deshalb nicht
# in CONTAINER_NAMES, sondern hat seine eigenen Regeln.
MARKET_CONTAINER = "market"
MARKET_CODES_PATTERN = re.compile(r"^[a-z]{2}(?:,[a-z]{2})*$")

# FAQ-Kategorien (Vertrag S7): Im Kapitel `faq` eröffnet eine H3 außerhalb der
# Container eine Gruppe; alle folgenden `:::faq` bis zur nächsten H3 gehören
# dazu. In allen anderen Kapiteln bleibt eine Top-Level-H3, was sie war: kein
# Anker, keine Gruppe, keine Prüfung.
FAQ_ANCHOR = "faq"
MIN_QUESTIONS_PER_GROUP = 2
# Seit dem Faktencheck-Nachtrag tragen alle Gruppen genug Fragen; der
# Mindestwert ist damit ein Fehler und keine Warnung mehr.
GROUP_MINIMUM_IS_ERROR = True

# Chart-Container: der Text liefert Einleitung und Lesehilfe, die Zahlen kommen
# aus dem Backend. Typliste und Klassen sind fest (Vertrag, Plan v2 §12).
CHART_TYPES = (
    "main",
    # `main` trägt den Regel-Chart, seit S11 im Kapitel `regel`; der Vergleich
    # Strategie gegen Halten steht als eigener Typ im Kapitel `rueckschau`,
    # damit das Frontend die beiden nicht am selben Typ auseinanderhalten muss.
    "backtest",
    # Seit S11 trägt `distribution` im Kapitel `rueckschau`, was `rolling` dort
    # tat: nicht mehr eine Kurve je Startmonat, sondern die Verteilung der
    # jährlichen Rendite über rollierende Zeiträume. `rolling` steht weiter im
    # Vertrag, wird aber von keiner Seite mehr benutzt.
    "distribution",
    # `longterm` (Welle strategie-backtest-langzeit-text) steht im Kapitel
    # `rueckschau` hinter der Verteilung: dieselbe Regel auf dem Index über
    # mehrere Jahrzehnte, nachgebaut mit angenommenen Kosten, unabhängig vom
    # Produkt; Zahlen und Kennzeichnung kommen aus dem Backend.
    "longterm",
    "rolling",
    "panorama",
    "heatmap",
    "whipsaw",
    "correlation",
    "premium",
    "drift",
    "regime",
    "volatility-drag",
    "crossing",
    "currency-panorama",
)
# `backtest` und `pulse` sind die V5-Namen von `rueckschau` und `puls`.
CHART_CLASSES = ("rueckschau", "puls", "schema", "backtest", "pulse")
CHART_METRICS = ("excess_return", "drawdown", "signals")
CHART_TYPES_NEEDING_PARAMETER = ("panorama", "currency-panorama")

# Wörter, die in der Ebene Verstehen nichts zu suchen haben: Empfehlung,
# Bewertung, oder eine Zahl, die wir nicht belegen können. Warnung, kein Fehler.
DISCOURAGED_WORDS = (
    "solltest",
    "empfohlen",
    "Empfehlung",
    "Definition",
    "Trefferquote",
    "Wahrscheinlichkeit",
    "ehrlich",
    "lohnt sich",
    "you should",
    "recommend",
    "hit rate",
    "probabilit",
    "honest",
    "worth it",
)

HEADING2_PATTERN = re.compile(r"^##\s+(?P<anchor>.+?)\s*$")
HEADING3_PATTERN = re.compile(r"^###\s+(?P<title>\S.*?)\s*$")
CONTAINER_OPEN_PATTERN = re.compile(r"^:::(?P<name>[a-z]+)(?:\s+(?P<args>.*?))?\s*$")
CONTAINER_CLOSE_PATTERN = re.compile(r"^:::\s*$")
ATTRIBUTE_PATTERN = re.compile(r"(?P<key>[a-z_]+)=(?P<value>\S+)")
WORD_PATTERNS = tuple(
    (word, re.compile(r"(?<![\w])" + re.escape(word), re.IGNORECASE)) for word in DISCOURAGED_WORDS
)
FORMULA_FENCE = "$$"

SOURCE_KINDS = (
    "paper",
    "book",
    "article",
    "blog",
    "forum",
    "dataset",
    "documentation",
    "regulation",
    "video",
    "other",
)

SOURCE_LICENSES = (
    "cc0-1.0",
    "cc-by-4.0",
    "cc-by-sa-4.0",
    "cc-by-nd-4.0",
    "cc-by-nc-4.0",
    "public-domain",
    "proprietary",
    "all-rights-reserved",
    "unknown",
)

# Bei diesen Lizenzen darf nichts übernommen werden; Verlinken und Zusammenfassen
# im eigenen Wortlaut bleibt erlaubt.
RESTRICTED_LICENSES = ("proprietary", "all-rights-reserved", "unknown")

SOURCE_FIELDS = (
    "title",
    "author",
    "year",
    "url",
    "kind",
    "lang",
    "license",
    "may_reproduce",
    "role",
    "supports",
    # Seit strategie-quellen-maerkte (Andre 2026-11-01): Marktcodes wie bei
    # `:::market`, für Quellen, die nur für bestimmte Märkte gelten (Recht).
    "market",
)

# Wozu die Seite eine Quelle führt (Vertrag S10): `source` ist ein
# Einzelnachweis und gehört ins Kapitel `quellen`, `further_reading` ist ein
# Ort zum Weiterlesen und muss im Kapitel `weiterlesen` verlinkt sein.
SOURCE_ROLES = ("source", "further_reading")

# `url` ist der einzige Eintrag, der fehlen darf: Manche Emittentendokumente
# haben keine öffentlich abrufbare Adresse. Dann benennen Titel und Autor den
# Emittenten und die Dokumentart, und die Kachel bleibt ohne Link.
SOURCE_REQUIRED = tuple(field for field in SOURCE_FIELDS if field not in ("url", "market"))
# Rechtsquellen gelten für einen Markt; ohne `market` eine Warnung (Übergang, Andre 2026-11-01).
SOURCE_KIND_NEEDS_MARKET = "regulation"

ORIGIN_FIELDS = ("author", "year", "url")

CORE_REQUIRED = ("slug", "status", "origin", "definition_ids", "sources", "last_reviewed", "reviewed_by")
CORE_OPTIONAL = ("related", "purpose", "building_blocks", "short_summary", "factsheet")

# "Das Wichtigste in Kürze" und Steckbrief je Strategie (strategie-kurz-inhalt, Andre 2026-11-01).
SHORT_SUMMARY_MIN_LENGTH = 80
SHORT_SUMMARY_MAX_LENGTH = 600
SHORT_SUMMARY_SENTENCES = (3, 5)
FACTSHEET_ROWS = (3, 9)
FACTSHEET_FIELDS = ("label", "value", "ref")
FACTSHEET_REQUIRED = ("label", "value")

# Übersichtsseite /strategies (Welle strategie-felder, GO Andre 2026-09-26): ein
# Satz, wofür die Strategie gedacht ist, und ihre Bausteine als feste Schlüssel.
PURPOSE_MIN_LENGTH = 20
PURPOSE_MAX_LENGTH = 110
PURPOSE_DASHES = ("\u2013", "\u2014")
PURPOSE_PERCENT_PATTERN = re.compile(r"\d\s*%")
# Wörter, die nach Empfehlung, Prognose oder Versprechen klingen (Compliance-Katalog
# K3/K4). Einträge in PREFIXES treffen als Wortanfang, alle übrigen nur als ganzes Wort.
PURPOSE_BANNED_WORDS = {
    "de": ("solltest", "prognose", "optimal", "beste", "garantiert", "sicher"),
    "en": ("recommend", "should", "expected", "best", "optimal", "guarantee", "safe"),
}
PURPOSE_BANNED_PREFIXES = {"de": ("empfehl", "erwartet"), "en": ()}
BUILDING_BLOCKS = ("aktien", "lange-staatsanleihen", "staatsanleihen", "gold", "cash")
BUILDING_BLOCKS_MAX = 4

# Präfix aus der Zeit vor dem Registry-Export. Seit die Slug-Liste vorliegt, ist
# ein solcher Wert keine offene Baustelle mehr, sondern ein Fehler.
PLACEHOLDER_PREFIX = "PLACEHOLDER__"


class RegistryError(Exception):
    """Eine der beiden Registry-Kopien fehlt oder ist unbrauchbar."""


class SlugRegistry:
    """Die zulässigen Preset-Slugs je Region, aus der committeten Kopie."""

    def __init__(self, by_region: dict[str, Sequence[str]], *, source_commit: str, path: Path | None = None) -> None:
        self.by_region = {region: tuple(slugs) for region, slugs in by_region.items()}
        self.source_commit = source_commit
        self.path = path
        self._region_of = {slug: region for region, slugs in self.by_region.items() for slug in slugs}

    @classmethod
    def load(cls, path: Path) -> SlugRegistry:
        """Liest die Kopie; jeder Defekt ist ein RegistryError."""
        data = _load_json(path, "Slug-Liste")

        slugs = data.get("slugs")
        if not isinstance(slugs, dict) or not slugs:
            raise RegistryError("Slug-Liste braucht ein nicht-leeres Objekt 'slugs' (Region -> Liste)")
        by_region: dict[str, Sequence[str]] = {}
        for region, entries in slugs.items():
            if not isinstance(entries, list) or not all(isinstance(item, str) and item for item in entries):
                raise RegistryError(f"slugs['{region}'] muss eine Liste nicht-leerer Strings sein")
            by_region[region] = entries

        source = data.get("source")
        commit = source.get("commit") if isinstance(source, dict) else None
        if not isinstance(commit, str) or not commit:
            raise RegistryError("Slug-Liste braucht den Quell-Commit unter source.commit")

        return cls(by_region, source_commit=commit, path=path)

    def region_of(self, slug: str) -> str | None:
        """Die Region, unter der ein Slug geführt wird, sonst None."""
        return self._region_of.get(slug)

    def describe(self) -> str:
        where = self.path.name if self.path is not None else "Slug-Liste"
        return f"{where}, Quell-Commit {self.source_commit[:12]}"


class ParameterKeys:
    """Die zulässigen Schlüssel für `:::parameter`-Karten."""

    def __init__(self, keys: Sequence[str], *, path: Path | None = None) -> None:
        self.keys = tuple(keys)
        self.path = path
        self._known = set(keys)

    @classmethod
    def load(cls, path: Path) -> ParameterKeys:
        data = _load_json(path, "Deskriptor-Liste")
        keys = data.get("keys")
        if not isinstance(keys, list) or not keys:
            raise RegistryError("Deskriptor-Liste braucht eine nicht-leere Liste 'keys'")
        if not all(isinstance(key, str) and key for key in keys):
            raise RegistryError("'keys' muss eine Liste nicht-leerer Strings sein")
        return cls(keys, path=path)

    def knows(self, key: str) -> bool:
        return key in self._known

    def describe(self) -> str:
        return self.path.name if self.path is not None else "Deskriptor-Liste"


class MarketRegistry:
    """Die Märkte, auf die sich ein `:::market`-Container berufen darf.

    Zwei Ebenen: Regionen (`eu`, `us`) sind die Ebene, auf der das Backend seine
    Presets führt; Länder (`de`, `at`, `fr`) liegen darunter. Ein Block für eine
    Region sieht auch eine Leserin, deren Land unter dieser Region steht; ein
    Block für ein Land nur diese.
    """

    def __init__(
        self,
        regions: Sequence[tuple[str, Sequence[str]]],
        *,
        fallback_countries: dict[str, str] | None = None,
        path: Path | None = None,
    ) -> None:
        self.regions = tuple(code for code, _ in regions)
        self.countries = {code: tuple(countries) for code, countries in regions}
        self.fallback_countries = dict(fallback_countries or {})
        self.path = path
        self._region_of = {
            country: region for region, countries in self.countries.items() for country in countries
        }

    @classmethod
    def load(cls, path: Path) -> MarketRegistry:
        """Liest das Register; jeder Defekt ist ein RegistryError."""
        data = _load_json(path, "Marktregister")

        entries = data.get("regions")
        if not isinstance(entries, list) or not entries:
            raise RegistryError("Marktregister braucht eine nicht-leere Liste 'regions'")

        regions: list[tuple[str, Sequence[str]]] = []
        fallback_countries: dict[str, str] = {}
        seen: dict[str, str] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                raise RegistryError("jeder Eintrag in 'regions' muss ein Objekt sein")
            code = entry.get("code")
            if not isinstance(code, str) or not REGION_PATTERN.match(code):
                raise RegistryError(f"'{code}' ist kein Regionscode (zwei Kleinbuchstaben)")
            if code in seen:
                raise RegistryError(f"'{code}' steht zweimal im Marktregister")
            seen[code] = "Region"

            countries = entry.get("countries", [])
            if not isinstance(countries, list) or not all(
                isinstance(item, str) and REGION_PATTERN.match(item) for item in countries
            ):
                raise RegistryError(f"regions['{code}'].countries muss eine Liste von Ländercodes sein")
            for country in countries:
                if country in seen:
                    raise RegistryError(f"'{country}' steht zweimal im Marktregister")
                seen[country] = "Land"

            fallback = entry.get("fallback_country")
            if fallback is not None:
                if fallback not in countries:
                    raise RegistryError(
                        f"regions['{code}'].fallback_country='{fallback}' steht nicht unter dieser Region"
                    )
                fallback_countries[code] = fallback

            unknown = [key for key in entry if key not in ("code", "countries", "fallback_country")]
            if unknown:
                raise RegistryError(f"regions['{code}']: unbekannte Felder: {', '.join(sorted(unknown))}")

            regions.append((code, countries))

        return cls(regions, fallback_countries=fallback_countries, path=path)

    @property
    def codes(self) -> tuple[str, ...]:
        """Alle zulässigen Marktcodes, Regionen und Länder."""
        return self.regions + tuple(self._region_of)

    def knows(self, code: str) -> bool:
        return code in self.regions or code in self._region_of

    def is_region(self, code: str) -> bool:
        return code in self.regions

    def region_of(self, code: str) -> str | None:
        """Die Region eines Codes: bei einer Region sie selbst, bei einem Land seine."""
        if code in self.regions:
            return code
        return self._region_of.get(code)

    def reaches(self, codes: Sequence[str], market: str) -> bool:
        """Sieht eine Leserin im Markt `market` einen Block mit diesen Codes?

        Ein Block für eine Region erreicht auch ihre Länder. Umgekehrt erreicht ein
        Block für ein Land eine Leserin, deren Land nicht erkannt wurde, nur dann,
        wenn es das `fallback_country` ihrer Region ist: Genau so liest das
        Frontend sie in der Übergangszeit.
        """
        if market in codes:
            return True
        if market in self.regions:
            fallback = self.fallback_countries.get(market)
            return fallback is not None and fallback in codes
        region = self._region_of.get(market)
        return region is not None and region in codes

    def is_live(self, market: str) -> bool:
        """Erreicht das Frontend diesen Markt heute schon als eigenen Markt?

        Regionen ja, und das `fallback_country` einer Region auch, weil eine
        Leserin ohne erkanntes Land als dieses Land gelesen wird. Die übrigen
        Länder bekommen erst mit der Feinteilung eigene Leser.
        """
        return market in self.regions or market in self.fallback_countries.values()

    def describe(self) -> str:
        where = self.path.name if self.path is not None else "Marktregister"
        return f"{where}, Codes: {', '.join(sorted(self.codes))}"


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RegistryError(f"{label} nicht lesbar ({exc.strerror})") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RegistryError(f"{label} ist kein gültiges JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise RegistryError(f"{label} muss ein JSON-Objekt sein")
    return data


class Report:
    """Sammelt Fehler und Warnungen mit Dateibezug."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, location: str, message: str) -> None:
        self.errors.append(f"{location}: {message}")

    def warn(self, location: str, message: str) -> None:
        self.warnings.append(f"{location}: {message}")


class FaqGroup:
    """Eine Kategorie im Kapitel `faq`: die H3 und was unter ihr steht."""

    def __init__(self, title: str, line: int, market_codes: tuple[str, ...] | None = None) -> None:
        self.title = title
        self.line = line
        # Die Marktcodes des Blocks, in dem die H3 selbst steht: Eine ganz
        # eingeklammerte Kategorie erscheint in anderen Märkten gar nicht.
        self.market_codes = market_codes
        # Je Frage die Marktcodes ihres `:::market`-Blocks, None für unbedingt.
        self.question_markets: list[tuple[str, ...] | None] = []
        # Absatzanfänge des Fließtexts zwischen H3 und erster Frage …
        self.lead: list[int] = []
        # … und ab der ersten Frage, wo keiner mehr stehen darf.
        self.stray: list[int] = []

    @property
    def questions(self) -> int:
        return len(self.question_markets)

    def reachable_questions(self, markets: MarketRegistry, market: str) -> int:
        """Die Fragen dieser Kategorie, die eine Leserin in `market` sieht."""
        return sum(
            1 for codes in self.question_markets if codes is None or markets.reaches(codes, market)
        )


class MarketBlock:
    """Ein `:::market`-Container: sein Kapitel, seine Codes, seine Zeile."""

    def __init__(self, chapter: str | None, codes: Sequence[str], line: int) -> None:
        self.chapter = chapter
        # Sortiert, weil die Reihenfolge der Codes im Vertrag nicht zählt.
        self.codes = tuple(sorted(codes))
        self.line = line

    @property
    def label(self) -> str:
        return ",".join(self.codes)


class Page:
    """Eine Content-Datei mit ihrem Dateinamen-Bestandteilen."""

    def __init__(self, path: Path, slug: str, language: str) -> None:
        self.path = path
        self.slug = slug
        self.language = language
        # Wird von check_file gefüllt; None heißt "gar nicht erst gelesen".
        self.faq_groups: list[FaqGroup] | None = None
        self.market_blocks: list[MarketBlock] | None = None
        self.building_blocks: list[str] | None = None


def split_document(text: str) -> tuple[str, list[str], int] | None:
    """Zerlegt in Frontmatter, Textzeilen und die Zeilennummer der ersten Textzeile."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "\n".join(lines[1:index]), lines[index + 1 :], index + 2
    return None


def load_frontmatter(raw: str, location: str, report: Report) -> dict[str, Any] | None:
    """Parst den YAML-Block einer Datei."""
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        report.error(location, f"Frontmatter ist kein gültiges YAML: {exc}")
        return None
    if not isinstance(data, dict):
        report.error(location, "Frontmatter muss eine Zuordnung von Feldern sein")
        return None
    return data


def check_origin(location: str, data: dict[str, Any], report: Report) -> None:
    """Prüft die Herkunfts-Kachel."""
    origin = data.get("origin")
    if not isinstance(origin, dict):
        report.error(location, "origin muss ein Objekt mit author, year und url sein")
        return

    missing = [field for field in ORIGIN_FIELDS if field not in origin]
    if missing:
        report.error(location, f"origin: Pflichtfelder fehlen: {', '.join(missing)}")
    unknown = [field for field in origin if field not in ORIGIN_FIELDS]
    if unknown:
        report.error(location, f"origin: unbekannte Felder: {', '.join(sorted(unknown))}")

    author = origin.get("author")
    if "author" in origin and (not isinstance(author, str) or not author.strip()):
        report.error(location, "origin.author muss ein nicht-leerer String sein")

    year = origin.get("year")
    if "year" in origin and (not isinstance(year, int) or isinstance(year, bool) or not 1900 <= year <= 2100):
        report.error(location, "origin.year muss eine Jahreszahl zwischen 1900 und 2100 sein")

    url = origin.get("url")
    if "url" in origin and (not isinstance(url, str) or not URL_PATTERN.match(url)):
        report.error(location, "origin.url muss mit http:// oder https:// beginnen")


def check_definition_ids(
    location: str,
    data: dict[str, Any],
    registry: SlugRegistry,
    report: Report,
) -> None:
    """Prüft die Map Region -> Liste von Preset-IDs gegen die Slug-Liste."""
    definition_ids = data.get("definition_ids")
    if not isinstance(definition_ids, dict) or not definition_ids:
        report.error(location, "definition_ids muss eine nicht-leere Map Region -> Liste sein")
        return

    for region, ids in definition_ids.items():
        if not isinstance(region, str) or not REGION_PATTERN.match(region):
            report.error(location, f"definition_ids: '{region}' ist kein Regionscode (zwei Kleinbuchstaben)")
            continue
        if not isinstance(ids, list) or not all(isinstance(item, str) and item for item in ids):
            report.error(location, f"definition_ids['{region}'] muss eine Liste nicht-leerer Strings sein")
            continue
        for definition_id in ids:
            where = f"definition_ids['{region}']"
            if definition_id.startswith(PLACEHOLDER_PREFIX):
                report.error(
                    location,
                    f"{where}: Platzhalter '{definition_id}' ist nicht mehr zulässig, "
                    f"die Slug-Liste liegt vor ({registry.describe()})",
                )
                continue
            actual_region = registry.region_of(definition_id)
            if actual_region is None:
                report.error(
                    location,
                    f"{where}: '{definition_id}' steht nicht in der Slug-Liste ({registry.describe()})",
                )
            elif actual_region != region:
                report.error(
                    location,
                    f"{where}: '{definition_id}' wird in der Slug-Liste unter Region "
                    f"'{actual_region}' geführt ({registry.describe()})",
                )


def collect_isins(data: dict[str, Any]) -> set[str]:
    """Alle ISINs, die in den definition_ids der Datei vorkommen."""
    isins: set[str] = set()
    definition_ids = data.get("definition_ids")
    if not isinstance(definition_ids, dict):
        return isins
    for ids in definition_ids.values():
        if not isinstance(ids, list):
            continue
        for definition_id in ids:
            if isinstance(definition_id, str) and "__" in definition_id:
                candidate = definition_id.rsplit("__", 1)[-1]
                if ISIN_PATTERN.match(candidate):
                    isins.add(candidate)
    return isins


def check_sources(
    location: str,
    data: dict[str, Any],
    report: Report,
    anchors: Sequence[str] = CORE_ANCHORS,
    markets: "MarketRegistry | None" = None,
) -> None:
    """Prüft die Quellenliste."""
    sources = data.get("sources")
    if not isinstance(sources, list):
        report.error(location, "sources muss eine Liste sein (darf leer sein)")
        return

    for index, source in enumerate(sources):
        where = f"sources[{index}]"
        if not isinstance(source, dict):
            report.error(location, f"{where} muss ein Objekt sein")
            continue

        missing = [field for field in SOURCE_REQUIRED if field not in source]
        if missing:
            report.error(location, f"{where}: Pflichtfelder fehlen: {', '.join(missing)}")
        unknown = [field for field in source if field not in SOURCE_FIELDS]
        if unknown:
            report.error(location, f"{where}: unbekannte Felder: {', '.join(sorted(unknown))}")
        check_source_market(location, where, source, markets, report)

        for field in ("title", "author"):
            value = source.get(field)
            if field in source and (not isinstance(value, str) or not value.strip()):
                report.error(location, f"{where}.{field} muss ein nicht-leerer String sein")

        year = source.get("year")
        if "year" in source and (not isinstance(year, int) or isinstance(year, bool) or not 1900 <= year <= 2100):
            report.error(location, f"{where}.year muss eine Jahreszahl zwischen 1900 und 2100 sein")

        url = source.get("url")
        if "url" in source and (not isinstance(url, str) or not URL_PATTERN.match(url)):
            report.error(location, f"{where}.url muss mit http:// oder https:// beginnen")

        kind = source.get("kind")
        if "kind" in source and kind not in SOURCE_KINDS:
            report.error(location, f"{where}.kind='{kind}' ist keiner von: {', '.join(SOURCE_KINDS)}")

        lang = source.get("lang")
        if "lang" in source and (not isinstance(lang, str) or not SOURCE_LANG_PATTERN.match(lang)):
            report.error(location, f"{where}.lang muss ein zweistelliger Sprachcode sein")

        license_value = source.get("license")
        if "license" in source and license_value not in SOURCE_LICENSES:
            report.error(
                location,
                f"{where}.license='{license_value}' ist keiner von: {', '.join(SOURCE_LICENSES)}",
            )

        may_reproduce = source.get("may_reproduce")
        if "may_reproduce" in source and not isinstance(may_reproduce, bool):
            report.error(location, f"{where}.may_reproduce muss true oder false sein")
        elif license_value in RESTRICTED_LICENSES and may_reproduce is True:
            report.error(
                location,
                f"{where}: license='{license_value}' erlaubt keine Reproduktion, "
                "may_reproduce muss false sein",
            )

        role = source.get("role")
        if "role" in source and role not in SOURCE_ROLES:
            report.error(location, f"{where}.role='{role}' ist keine von: {', '.join(SOURCE_ROLES)}")
        elif role == "further_reading" and anchors is V5_ANCHORS:
            report.error(location, f"{where}: role='further_reading' gibt es in Struktur V5 nicht mehr")
        elif role == "further_reading" and "url" not in source:
            report.error(
                location,
                f"{where}: eine Quelle mit role='further_reading' braucht eine url, "
                f"denn sie muss im Kapitel '{FURTHER_READING_ANCHOR}' verlinkt sein",
            )

        supports = source.get("supports")
        if "supports" in source:
            if not isinstance(supports, list) or not supports:
                message = f"{where}.supports muss eine nicht-leere Liste von Kapitelankern sein"
                if role == "source":
                    message += "; eine Quelle mit role='source' belegt mindestens ein Kapitel"
                report.error(location, message)
            else:
                unknown_anchors = [
                    anchor for anchor in supports if not isinstance(anchor, str) or anchor not in anchors
                ]
                if unknown_anchors:
                    report.error(
                        location,
                        f"{where}.supports: keine Kapitelanker: "
                        f"{', '.join(str(anchor) for anchor in unknown_anchors)}",
                    )


def chapter_lines(lines: Sequence[str], anchor: str) -> list[str]:
    """Die Zeilen eines Kapitels, ohne seine H2 und ohne das folgende Kapitel."""
    collected: list[str] = []
    inside = False
    depth = 0
    for line in lines:
        if CONTAINER_OPEN_PATTERN.match(line):
            depth += 1
        elif CONTAINER_CLOSE_PATTERN.match(line):
            depth = max(0, depth - 1)
        elif depth == 0:
            heading2 = HEADING2_PATTERN.match(line)
            if heading2:
                inside = heading2.group("anchor") == anchor
                continue
        if inside:
            collected.append(line)
    return collected


def check_further_reading(location: str, data: dict[str, Any], lines: Sequence[str], report: Report) -> None:
    """Prüft, dass jede Quelle zum Weiterlesen im Kapitel `weiterlesen` steht.

    Der Grund ist die Arbeitsteilung der beiden Kapitel: `quellen` führt die
    Einzelnachweise, `weiterlesen` die Orte, an denen es weitergeht. Eine Kachel
    zum Weiterlesen, die im Kapitel nicht vorkommt, wäre eine Empfehlung ohne
    Satz dazu.
    """
    sources = data.get("sources")
    if not isinstance(sources, list):
        return

    chapter = "\n".join(chapter_lines(lines, FURTHER_READING_ANCHOR))
    for index, source in enumerate(sources):
        if not isinstance(source, dict) or source.get("role") != "further_reading":
            continue
        url = source.get("url")
        if not isinstance(url, str):
            continue
        if f"]({url})" not in chapter:
            report.error(
                location,
                f"sources[{index}]: '{url}' ist als 'further_reading' geführt, "
                f"steht aber nicht als Link im Kapitel '{FURTHER_READING_ANCHOR}'",
            )


def page_anchor_scheme(lines: Sequence[str]) -> tuple[str, ...]:
    """Das Ankerschema einer Seite: V5, sobald sie ein Kapitel `rule` hat, sonst das alte."""
    for line in lines:
        match = HEADING2_PATTERN.match(line)
        if match and match.group("anchor") == V5_MARKER_ANCHOR:
            return V5_ANCHORS
    return CORE_ANCHORS


def check_anchors(location: str, lines: Sequence[str], offset: int, expected: Sequence[str], report: Report) -> None:
    """Prüft die H2-Kapitelanker auf Vollständigkeit und Reihenfolge."""
    found: list[str] = []
    # Gezählt statt geschaltet, weil `:::market` andere Container umschließen darf.
    depth = 0
    for line in lines:
        if CONTAINER_OPEN_PATTERN.match(line):
            depth += 1
            continue
        if CONTAINER_CLOSE_PATTERN.match(line):
            depth = max(0, depth - 1)
            continue
        if depth:
            continue
        match = HEADING2_PATTERN.match(line)
        if match:
            found.append(match.group("anchor"))

    if tuple(found) == tuple(expected):
        return

    missing = [anchor for anchor in expected if anchor not in found]
    unknown = [anchor for anchor in found if anchor not in expected]
    if missing:
        report.error(location, f"Kapitelanker fehlen: {', '.join(missing)}")
    if unknown:
        report.error(location, f"unbekannte H2-Überschriften: {', '.join(unknown)}")
    if not missing and not unknown:
        report.error(
            location,
            "Kapitelanker stehen in der falschen Reihenfolge: "
            f"{', '.join(found)} statt {', '.join(expected)}",
        )


def parse_attributes(args: str) -> dict[str, str]:
    return {match.group("key"): match.group("value") for match in ATTRIBUTE_PATTERN.finditer(args)}


def check_containers(
    location: str,
    lines: Sequence[str],
    offset: int,
    data: dict[str, Any],
    parameter_keys: ParameterKeys,
    markets: MarketRegistry,
    report: Report,
) -> None:
    """Prüft die Container-Syntax und die Angaben in den Containern.

    Eine Ebene Verschachtelung ist erlaubt, und nur eine: `:::market` darf die
    fünf anderen Container umschließen, keiner von ihnen umgekehrt, und
    `:::market` nicht sich selbst.
    """
    isins = collect_isins(data)
    open_name: str | None = None
    open_line = 0
    body_lines: list[str] = []
    market_line: int | None = None
    market_body: list[str] = []

    def where(index: int) -> str:
        return f"{location}:{offset + index}"

    for index, line in enumerate(lines):
        close = CONTAINER_CLOSE_PATTERN.match(line)
        if close:
            if open_name is not None:
                if open_name == "faq" and not any(HEADING3_PATTERN.match(item) for item in body_lines):
                    report.error(where(open_line), ":::faq braucht die Frage als H3 (### ...)")
                if not any(item.strip() for item in body_lines):
                    report.error(where(open_line), f":::{open_name} ist leer")
                open_name = None
                body_lines = []
                continue
            if market_line is not None:
                if not any(item.strip() for item in market_body):
                    report.error(where(market_line), f":::{MARKET_CONTAINER} ist leer")
                market_line = None
                market_body = []
                continue
            report.error(where(index), "schließendes ':::' ohne offenen Container")
            continue

        opening = CONTAINER_OPEN_PATTERN.match(line)
        if opening:
            name = opening.group("name")
            args = (opening.group("args") or "").strip()
            if open_name is not None:
                report.error(
                    where(index),
                    f"':::{name}' öffnet innerhalb von ':::{open_name}'; nur ':::{MARKET_CONTAINER}' "
                    "darf andere Container umschließen",
                )
                continue
            if name == MARKET_CONTAINER:
                if market_line is not None:
                    report.error(
                        where(index),
                        f"':::{MARKET_CONTAINER}' öffnet innerhalb von ':::{MARKET_CONTAINER}'; "
                        "Markt-Blöcke verschachteln nicht",
                    )
                    continue
                market_line = index
                market_body = []
                check_market_args(where(index), args, markets, report)
                continue
            if name not in CONTAINER_NAMES:
                report.error(where(index), f"unbekannter Container ':::{name}'")
                continue
            open_name = name
            open_line = index
            body_lines = []
            market_body.append(line)
            check_container_args(where(index), name, args, isins, parameter_keys, report)
            continue

        if open_name is not None:
            body_lines.append(line)
            market_body.append(line)
        elif market_line is not None:
            market_body.append(line)

    if open_name is not None:
        report.error(where(open_line), f":::{open_name} wird nicht durch ':::' geschlossen")
    if market_line is not None:
        report.error(where(market_line), f":::{MARKET_CONTAINER} wird nicht durch ':::' geschlossen")


def parse_market_codes(args: str) -> list[str]:
    """Die Marktcodes hinter `:::market`, in der Reihenfolge des Dokuments."""
    return [code for code in args.split(",") if code]


def check_market_args(location: str, args: str, markets: MarketRegistry, report: Report) -> None:
    """Prüft die Marktcodes eines `:::market`-Containers gegen das Register."""
    if not args:
        report.error(
            location,
            f":::{MARKET_CONTAINER} braucht mindestens einen Marktcode ({markets.describe()})",
        )
        return
    if not MARKET_CODES_PATTERN.match(args):
        report.error(
            location,
            f":::{MARKET_CONTAINER} '{args}': die Codes stehen kommagetrennt ohne Leerzeichen, "
            "je zwei Kleinbuchstaben",
        )
        return

    codes = parse_market_codes(args)
    seen: set[str] = set()
    for code in codes:
        if code in seen:
            report.error(location, f":::{MARKET_CONTAINER}: '{code}' steht zweimal in derselben Angabe")
            continue
        seen.add(code)
        if not markets.knows(code):
            report.error(
                location,
                f":::{MARKET_CONTAINER}: '{code}' steht nicht im Marktregister ({markets.describe()})",
            )


def check_container_args(
    location: str,
    name: str,
    args: str,
    isins: set[str],
    parameter_keys: ParameterKeys,
    report: Report,
) -> None:
    """Prüft die Angaben hinter dem Container-Namen."""
    if name == "layer":
        if args not in LAYER_NAMES:
            report.error(location, f":::layer braucht eine Ebene aus: {', '.join(LAYER_NAMES)}")
        return

    if name == "faq":
        if args:
            report.error(location, ":::faq nimmt keine Angaben")
        return

    attributes = parse_attributes(args)

    if name == "parameter":
        key = attributes.get("key")
        if key is None:
            report.error(location, ":::parameter braucht key=<Deskriptor>")
        elif not parameter_keys.knows(key):
            report.error(
                location,
                f":::parameter key='{key}' steht nicht in der Deskriptor-Liste ({parameter_keys.describe()})",
            )
        return

    if name == "chart":
        chart_type = attributes.get("type")
        if chart_type is None:
            report.error(location, ":::chart braucht type=<Charttyp>")
        elif chart_type not in CHART_TYPES:
            report.error(location, f":::chart type='{chart_type}' ist keiner von: {', '.join(CHART_TYPES)}")

        chart_class = attributes.get("class")
        if chart_class is None:
            report.error(location, ":::chart braucht class=<Klasse>")
        elif chart_class not in CHART_CLASSES:
            report.error(location, f":::chart class='{chart_class}' ist keine von: {', '.join(CHART_CLASSES)}")

        parameter = attributes.get("parameter")
        if parameter is not None and not parameter_keys.knows(parameter):
            report.error(
                location,
                f":::chart parameter='{parameter}' steht nicht in der Deskriptor-Liste "
                f"({parameter_keys.describe()})",
            )
        if chart_type in CHART_TYPES_NEEDING_PARAMETER and parameter is None:
            report.error(location, f":::chart type='{chart_type}' braucht parameter=<Deskriptor>")

        metric = attributes.get("metric")
        if metric is not None and metric not in CHART_METRICS:
            report.error(location, f":::chart metric='{metric}' ist keine von: {', '.join(CHART_METRICS)}")

        layer = attributes.get("layer")
        if layer is not None and layer != "compute":
            report.error(location, ":::chart layer nimmt nur den Wert 'compute'")

        unknown = [key for key in attributes if key not in ("type", "class", "parameter", "metric", "layer")]
        if unknown:
            report.error(location, f":::chart: unbekannte Angaben: {', '.join(sorted(unknown))}")
        return

    if name == "example":
        missing = [field for field in ("from", "to", "isin") if field not in attributes]
        if missing:
            report.error(location, f":::example: Angaben fehlen: {', '.join(missing)}")
            return
        for field in ("from", "to"):
            if not DATE_PATTERN.match(attributes[field]):
                report.error(location, f":::example {field}='{attributes[field]}' ist kein Datum YYYY-MM-DD")
                return
        if attributes["from"] >= attributes["to"]:
            report.error(location, ":::example: from muss vor to liegen")
        isin = attributes["isin"]
        if isin not in isins:
            report.error(
                location,
                f":::example isin='{isin}' kommt in den definition_ids dieser Datei nicht vor",
            )


def collect_market_blocks(
    lines: Sequence[str],
) -> tuple[list[MarketBlock], list[tuple[str, int]], dict[str | None, bool]]:
    """Liest die `:::market`-Blöcke, die Kapitel und ihren unbedingten Inhalt.

    Zurück kommen die Blöcke in Dokumentreihenfolge, die Kapitel als Paar aus
    Anker und Zeile, und je Kapitel die Antwort auf die Frage, ob außerhalb aller
    Markt-Blöcke überhaupt etwas steht. Was vor dem ersten H2 steht, läuft unter
    dem Kapitel `None`.
    """
    blocks: list[MarketBlock] = []
    chapters: list[tuple[str, int]] = []
    unconditional: dict[str | None, bool] = {None: False}
    chapter: str | None = None
    open_name: str | None = None
    in_market = False

    for index, line in enumerate(lines):
        if CONTAINER_CLOSE_PATTERN.match(line):
            if open_name is not None:
                open_name = None
            elif in_market:
                in_market = False
            continue

        opening = CONTAINER_OPEN_PATTERN.match(line)
        if opening:
            name = opening.group("name")
            if name == MARKET_CONTAINER and open_name is None and not in_market:
                codes = parse_market_codes((opening.group("args") or "").strip())
                blocks.append(MarketBlock(chapter, codes, index))
                in_market = True
                continue
            if open_name is None:
                open_name = name
                if not in_market:
                    unconditional[chapter] = True
            continue

        if open_name is not None or in_market:
            continue

        heading2 = HEADING2_PATTERN.match(line)
        if heading2:
            chapter = heading2.group("anchor")
            if chapter not in unconditional:
                chapters.append((chapter, index))
                unconditional[chapter] = False
            continue

        if line.strip():
            unconditional[chapter] = True

    return blocks, chapters, unconditional


def check_market_chapters(
    location: str,
    offset: int,
    blocks: Sequence[MarketBlock],
    chapters: Sequence[tuple[str, int]],
    unconditional: dict[str | None, bool],
    markets: MarketRegistry,
    report: Report,
) -> None:
    """Stellt sicher, dass kein Kapitel für eine Region des Registers leer ist.

    Entweder steht im Kapitel etwas außerhalb aller Markt-Blöcke, oder es gibt
    für jede Region einen Block. Ein Ländercode zählt dafür nicht: Ein Kapitel,
    das nur `de` führt, bliebe für eine Leserin in Österreich leer, sobald das
    Frontend die Länder auseinanderhält.
    """
    by_chapter: dict[str | None, list[MarketBlock]] = {}
    for block in blocks:
        by_chapter.setdefault(block.chapter, []).append(block)

    for chapter, line in chapters:
        if unconditional.get(chapter):
            continue
        covered = {
            code for block in by_chapter.get(chapter, []) for code in block.codes if markets.is_region(code)
        }
        missing = [region for region in markets.regions if region not in covered]
        if missing:
            report.error(
                f"{location}:{offset + line}",
                f"das Kapitel '{chapter}' steht ganz in Markt-Blöcken und lässt "
                f"{', '.join(missing)} leer; ein Kapitel braucht unbedingten Inhalt "
                "oder einen Block je Region des Registers",
            )


def collect_visible_chapters(
    lines: Sequence[str],
) -> tuple[list[tuple[str, int]], dict[str | None, bool]]:
    """Je Kapitel die Frage, ob darin etwas außerhalb der `:::layer`-Kästen steht.

    Zurück kommen die Kapitel als Paar aus Anker und Zeile und je Kapitel die
    Antwort. Als sichtbar zählt jede nicht-leere Zeile außerhalb aller Container
    und jeder Container, der kein `:::layer` ist. `:::market` ist dabei
    durchsichtig: Er wählt den Markt, er versteckt nichts vor der Leserin.
    """
    chapters: list[tuple[str, int]] = []
    visible: dict[str | None, bool] = {None: False}
    chapter: str | None = None
    open_name: str | None = None
    in_market = False

    for index, line in enumerate(lines):
        if CONTAINER_CLOSE_PATTERN.match(line):
            if open_name is not None:
                open_name = None
            elif in_market:
                in_market = False
            continue

        opening = CONTAINER_OPEN_PATTERN.match(line)
        if opening:
            name = opening.group("name")
            if name == MARKET_CONTAINER and open_name is None and not in_market:
                in_market = True
                continue
            if open_name is None:
                open_name = name
                if name != LAYER_CONTAINER:
                    visible[chapter] = True
            continue

        if open_name is not None:
            continue

        if not in_market:
            heading2 = HEADING2_PATTERN.match(line)
            if heading2:
                chapter = heading2.group("anchor")
                if chapter not in visible:
                    chapters.append((chapter, index))
                    visible[chapter] = False
                continue

        if line.strip():
            visible[chapter] = True

    return chapters, visible


def check_layer_only_chapters(
    location: str,
    offset: int,
    chapters: Sequence[tuple[str, int]],
    visible: dict[str | None, bool],
    report: Report,
) -> None:
    """Verbietet ein Kapitel, das ganz in `:::layer`-Kästen steht.

    Seit S11 zeigt das Frontend einen Kasten zugeklappt an seiner Stelle im
    Kapitel. Ein Kapitel, das nur aus Kästen besteht, ist damit für die Leserin
    leer: Sie sieht eine Überschrift und darunter einen geschlossenen Kasten.
    Der Kasten ist die Vertiefung, nicht der Inhalt; was das Kapitel sagen will,
    steht außerhalb.
    """
    for chapter, line in chapters:
        if visible.get(chapter):
            continue
        report.error(
            f"{location}:{offset + line}",
            f"das Kapitel '{chapter}' steht ganz in ':::{LAYER_CONTAINER}'-Kästen; "
            "ein Kasten ist die Vertiefung und nicht der Inhalt, das Frontend zeigt "
            "ihn zugeklappt und das Kapitel bliebe leer",
        )


def collect_faq_groups(lines: Sequence[str]) -> tuple[list[FaqGroup], list[int]]:
    """Liest die Kategorien des Kapitels `faq` und die Fragen vor der ersten.

    Zurück kommen die Gruppen in Dokumentreihenfolge und die Zeilen der
    `:::faq`, die vor der ersten Kategorie stehen. Gesammelt wird nur im
    Kapitel `faq`: Eine Top-Level-H3 in einem anderen Kapitel ist keine
    Kategorie und bleibt unbeachtet.

    `:::market` ist dabei durchsichtig: Eine Kategorie darf einen Markt-Block
    enthalten, und ein Markt-Block darf eine ganze Kategorie umschließen. Für
    den Mindestwert zählen unbedingte und Markt-Fragen zusammen.
    """
    groups: list[FaqGroup] = []
    ungrouped: list[int] = []
    in_faq_chapter = False
    open_container: str | None = None
    market_codes: tuple[str, ...] | None = None
    paragraph_open = False

    for index, line in enumerate(lines):
        if open_container is not None:
            if CONTAINER_CLOSE_PATTERN.match(line):
                open_container = None
            continue

        opening = CONTAINER_OPEN_PATTERN.match(line)
        if opening:
            name = opening.group("name")
            paragraph_open = False
            if name == MARKET_CONTAINER and market_codes is None:
                market_codes = tuple(parse_market_codes((opening.group("args") or "").strip()))
                continue
            open_container = name
            if in_faq_chapter and open_container == FAQ_ANCHOR:
                if groups:
                    groups[-1].question_markets.append(market_codes)
                else:
                    ungrouped.append(index)
            continue

        if CONTAINER_CLOSE_PATTERN.match(line):
            market_codes = None
            paragraph_open = False
            continue

        heading2 = HEADING2_PATTERN.match(line)
        if heading2:
            in_faq_chapter = heading2.group("anchor") == FAQ_ANCHOR
            paragraph_open = False
            continue

        if not in_faq_chapter:
            continue

        heading3 = HEADING3_PATTERN.match(line)
        if heading3:
            groups.append(FaqGroup(heading3.group("title"), index, market_codes))
            paragraph_open = False
            continue

        if not line.strip():
            paragraph_open = False
            continue

        if not paragraph_open and groups:
            group = groups[-1]
            (group.stray if group.questions else group.lead).append(index)
        paragraph_open = True

    return groups, ungrouped


def check_group_minimum(
    location: str, group: FaqGroup, markets: MarketRegistry, report: Report
) -> None:
    """Prüft den Mindestwert je Markt, nicht über die Summe.

    Eine Gruppe aus zwei Fragen, von denen eine `de` und eine `us` trägt, zählt in
    der Summe zwei und zeigt jeder Leserin doch nur eine. Geprüft wird deshalb je
    Markt aus dem Register: unbedingte Fragen plus die Blöcke, die diesen Markt
    erreichen. Für Länder, die das Frontend heute noch nicht als eigenen Markt
    liest, ist ein Fehlbetrag nur eine Warnung.

    Übersprungen werden Märkte, in denen die Kategorie gar nicht erscheint: Steht
    schon ihre H3 in einem Markt-Block, gibt es für die anderen Märkte keine
    Kategorie, die zu dünn sein könnte. Steht die H3 dagegen unbedingt da und
    liegen alle ihre Fragen in Markt-Blöcken, ist die leere Kategorie ein Fehler.
    """
    for market in markets.codes:
        if group.market_codes is not None and not markets.reaches(group.market_codes, market):
            continue
        count = group.reachable_questions(markets, market)
        if count >= MIN_QUESTIONS_PER_GROUP:
            continue
        noun = "Frage" if count == 1 else "Fragen"
        message = (
            f"die Kategorie '{group.title}' erreicht den Markt '{market}' mit nur {count} {noun}, "
            f"gefordert sind {MIN_QUESTIONS_PER_GROUP}"
        )
        if not markets.is_live(market):
            report.warn(
                location,
                message + "; solange das Frontend die Länder einer Region nicht auseinanderhält, "
                "ist das nur eine Warnung",
            )
        elif GROUP_MINIMUM_IS_ERROR:
            report.error(location, message)
        else:
            report.warn(location, message)


def check_faq_groups(
    location: str,
    lines: Sequence[str],
    offset: int,
    markets: MarketRegistry,
    report: Report,
) -> list[FaqGroup]:
    """Prüft die Kategorien im Kapitel `faq` und gibt sie zurück.

    Ein Kapitel ohne Kategorie ist in Ordnung: Gruppen sind ein Angebot, kein
    Zwang. Sobald aber eine H3 dasteht, gilt der ganze Vertrag.
    """
    groups, ungrouped = collect_faq_groups(lines)

    def where(index: int) -> str:
        return f"{location}:{offset + index}"

    if not groups:
        return groups

    if ungrouped:
        report.error(
            where(ungrouped[0]),
            "im Kapitel 'faq' steht eine Frage vor der ersten Kategorie; "
            "entweder alle Fragen gruppiert oder keine",
        )

    seen: dict[str, int] = {}
    for group in groups:
        first = seen.get(group.title)
        if first is not None:
            report.error(
                where(group.line),
                f"die Kategorie '{group.title}' steht schon in Zeile {offset + first}; "
                "die Titel einer Datei müssen sich unterscheiden, das Frontend baut die Sprungmarke daraus",
            )
        else:
            seen[group.title] = group.line

        if group.questions == 0:
            report.error(where(group.line), f"die Kategorie '{group.title}' führt keine Frage")
        else:
            check_group_minimum(where(group.line), group, markets, report)

        if len(group.lead) > 1:
            report.error(
                where(group.lead[1]),
                f"unter der Kategorie '{group.title}' steht mehr als ein Absatz; "
                "erlaubt ist ein einleitender Satz direkt unter der H3",
            )
        if group.stray:
            report.error(
                where(group.stray[0]),
                f"Fließtext zwischen den Fragen der Kategorie '{group.title}'; "
                "ein einleitender Satz steht direkt unter der H3 oder gar nicht",
            )

    return groups


def check_wording(location: str, lines: Sequence[str], offset: int, report: Report) -> None:
    """Warnt vor Wörtern, die in der Ebene Verstehen nichts zu suchen haben.

    Die tieferen Ebenen sind ausgenommen: dort darf über Wahrscheinlichkeiten
    und Trefferquoten geredet werden, gerade weil die Seite davon abrät.
    """
    depth_free = True
    for index, line in enumerate(lines):
        opening = CONTAINER_OPEN_PATTERN.match(line)
        if opening:
            name = opening.group("name")
            args = opening.group("args") or ""
            if name == MARKET_CONTAINER:
                # Ein Markt-Block ändert die Ebene nicht, er wählt nur den Markt.
                continue
            depth_free = not (name == "layer" or (name == "chart" and "layer=compute" in args))
            continue
        if CONTAINER_CLOSE_PATTERN.match(line):
            depth_free = True
            continue
        if not depth_free:
            continue
        for word, pattern in WORD_PATTERNS:
            if pattern.search(line):
                report.warn(
                    f"{location}:{offset + index}",
                    f"'{word}' gehört nicht in die Ebene Verstehen",
                )


def check_formulas(location: str, lines: Sequence[str], offset: int, report: Report) -> None:
    """Prüft, dass die `$$`-Formelblöcke paarig und nicht leer sind."""
    fences = [index for index, line in enumerate(lines) if line.strip() == FORMULA_FENCE]
    if len(fences) % 2 == 1:
        report.error(f"{location}:{offset + fences[-1]}", "unpaariger Formelblock '$$'")
        return
    for start, end in zip(fences[0::2], fences[1::2]):
        if not any(lines[index].strip() for index in range(start + 1, end)):
            report.error(f"{location}:{offset + start}", "leerer Formelblock '$$'")


def check_source_market(
    location: str, where: str, source: dict[str, Any], markets: "MarketRegistry | None", report: Report
) -> None:
    """`market` einer Quelle: Marktcodes wie bei `:::market`; Rechtsquellen ohne Markt warnen."""
    if "market" not in source:
        if source.get("kind") == SOURCE_KIND_NEEDS_MARKET:
            report.warn(location, f"{where}: Rechtsquelle ohne market (gilt sonst für alle Märkte)")
        return
    value = source.get("market")
    if not isinstance(value, str) or not MARKET_CODES_PATTERN.match(value):
        report.error(location, f"{where}.market muss Marktcodes wie 'de' oder 'de,at' enthalten")
        return
    if markets is None:
        return
    for code in value.split(","):
        if not markets.knows(code):
            report.error(location, f"{where}.market: '{code}' steht nicht im Marktregister ({markets.describe()})")


def check_wording_rules(location: str, field: str, text: str, language: str, report: Report) -> None:
    """Gedankenstrich, Prozentzahl und die Wörter der Sperrliste, wie bei `purpose`."""
    if any(dash in text for dash in PURPOSE_DASHES):
        report.error(location, f"{field} enthält einen Gedankenstrich")
    if PURPOSE_PERCENT_PATTERN.search(text):
        report.error(location, f"{field} enthält eine Zahl mit Prozent")
    words = re.findall(r"\w+", text.lower())
    for banned in PURPOSE_BANNED_WORDS.get(language, ()):
        if banned in words:
            report.error(location, f"{field} enthält das Wort '{banned}'")
    for prefix in PURPOSE_BANNED_PREFIXES.get(language, ()):
        if any(word.startswith(prefix) for word in words):
            report.error(location, f"{field} enthält ein Wort mit '{prefix}'")


def check_short_summary(location: str, data: dict[str, Any], language: str, report: Report) -> None:
    """Drei bis fünf Sätze für "Das Wichtigste in Kürze"."""
    summary = data.get("short_summary")
    if not isinstance(summary, str):
        report.error(location, "short_summary muss ein Text (String) sein")
        return
    text = " ".join(summary.split())
    if not SHORT_SUMMARY_MIN_LENGTH <= len(text) <= SHORT_SUMMARY_MAX_LENGTH:
        report.error(
            location,
            f"short_summary hat {len(text)} Zeichen, erlaubt sind "
            f"{SHORT_SUMMARY_MIN_LENGTH} bis {SHORT_SUMMARY_MAX_LENGTH}",
        )
    sentences = [part for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
    low, high = SHORT_SUMMARY_SENTENCES
    if not low <= len(sentences) <= high or not text.endswith((".", "!", "?")):
        report.error(location, f"short_summary braucht {low} bis {high} Sätze mit Satzzeichen am Ende")
    check_wording_rules(location, "short_summary", text, language, report)


def check_factsheet(
    location: str, data: dict[str, Any], anchors: Sequence[str], language: str, report: Report
) -> None:
    """Steckbrief: Zeilen mit `label`, `value` und optional `ref` (Kapitelanker der Seite)."""
    rows = data.get("factsheet")
    low, high = FACTSHEET_ROWS
    if not isinstance(rows, list) or not low <= len(rows) <= high:
        report.error(location, f"factsheet muss eine Liste mit {low} bis {high} Zeilen sein")
        return
    for index, row in enumerate(rows):
        where = f"factsheet[{index}]"
        if not isinstance(row, dict):
            report.error(location, f"{where} muss ein Objekt sein")
            continue
        missing = [field for field in FACTSHEET_REQUIRED if field not in row]
        if missing:
            report.error(location, f"{where}: Pflichtfelder fehlen: {', '.join(missing)}")
        unknown = [field for field in row if field not in FACTSHEET_FIELDS]
        if unknown:
            report.error(location, f"{where}: unbekannte Felder: {', '.join(sorted(unknown))}")
        for field in FACTSHEET_REQUIRED:
            value = row.get(field)
            if field in row and (not isinstance(value, str) or not value.strip()):
                report.error(location, f"{where}.{field} muss ein nicht-leerer Text sein")
            elif isinstance(value, str):
                check_wording_rules(location, f"{where}.{field}", value, language, report)
        ref = row.get("ref")
        if "ref" in row and ref not in anchors:
            report.error(location, f"{where}.ref '{ref}' ist kein Kapitelanker der Seite")


def check_purpose(location: str, data: dict[str, Any], language: str, report: Report) -> None:
    """Ein Satz, wofür die Strategie gedacht ist, in der Sprache der Datei."""
    purpose = data.get("purpose")
    if not isinstance(purpose, str):
        report.error(location, "purpose muss ein Satz (String) sein")
        return
    text = purpose.strip()
    if not PURPOSE_MIN_LENGTH <= len(text) <= PURPOSE_MAX_LENGTH:
        report.error(
            location,
            f"purpose hat {len(text)} Zeichen, erlaubt sind {PURPOSE_MIN_LENGTH} bis {PURPOSE_MAX_LENGTH}",
        )
    if not text.endswith("."):
        report.error(location, "purpose muss mit einem Punkt enden")
    if any(dash in text for dash in PURPOSE_DASHES):
        report.error(location, "purpose enthält einen Gedankenstrich")
    if PURPOSE_PERCENT_PATTERN.search(text):
        report.error(location, "purpose enthält eine Zahl mit Prozent")
    words = re.findall(r"\w+", text.lower())
    for banned in PURPOSE_BANNED_WORDS.get(language, ()):
        if banned in words:
            report.error(location, f"purpose enthält das Wort '{banned}'")
    for prefix in PURPOSE_BANNED_PREFIXES.get(language, ()):
        if any(word.startswith(prefix) for word in words):
            report.error(location, f"purpose enthält ein Wort mit '{prefix}'")


def check_building_blocks(location: str, data: dict[str, Any], report: Report) -> list[str] | None:
    """Die Bausteine aus dem festen Vokabular; gibt die gültige Liste zurück."""
    blocks = data.get("building_blocks")
    if not isinstance(blocks, list) or not all(isinstance(item, str) for item in blocks):
        report.error(location, "building_blocks muss eine Liste von Schlüsseln sein")
        return None
    valid = True
    if not 1 <= len(blocks) <= BUILDING_BLOCKS_MAX:
        report.error(location, f"building_blocks führt {len(blocks)} Einträge, erlaubt sind 1 bis {BUILDING_BLOCKS_MAX}")
        valid = False
    for block in blocks:
        if block not in BUILDING_BLOCKS:
            report.error(location, f"unbekannter Baustein {block}; erlaubt: {', '.join(BUILDING_BLOCKS)}")
            valid = False
    if len(set(blocks)) != len(blocks):
        report.error(location, "building_blocks nennt einen Baustein doppelt")
        valid = False
    return list(blocks) if valid else None


def check_file(
    page: Page,
    registry: SlugRegistry,
    parameter_keys: ParameterKeys,
    markets: MarketRegistry,
    report: Report,
) -> None:
    """Prüft eine einzelne Content-Datei."""
    location = page.path.name
    parts = split_document(page.path.read_text(encoding="utf-8"))
    if parts is None:
        report.error(location, "kein YAML-Frontmatter zwischen zwei '---'-Zeilen gefunden")
        return
    raw, lines, offset = parts

    data = load_frontmatter(raw, location, report)
    if data is None:
        return

    missing = [field for field in CORE_REQUIRED if field not in data]
    if missing:
        report.error(location, f"Pflichtfelder fehlen: {', '.join(missing)}")
    unknown = [field for field in data if field not in set(CORE_REQUIRED) | set(CORE_OPTIONAL)]
    if unknown:
        report.error(location, f"unbekannte Felder: {', '.join(sorted(unknown))}")

    slug = data.get("slug")
    if "slug" in data:
        if not isinstance(slug, str) or not SLUG_PATTERN.match(slug):
            report.error(location, "slug muss aus Kleinbuchstaben, Ziffern und Bindestrichen bestehen")
        elif slug != page.slug:
            report.error(location, f"slug '{slug}' passt nicht zum Dateinamen '{page.slug}'")

    status = data.get("status")
    if "status" in data and status not in STATUS_VALUES:
        report.error(location, f"status='{status}' ist keiner von: {', '.join(STATUS_VALUES)}")

    if "origin" in data:
        check_origin(location, data, report)

    if "definition_ids" in data:
        check_definition_ids(location, data, registry, report)

    anchors = page_anchor_scheme(lines)
    if "sources" in data:
        check_sources(location, data, report, anchors, markets)
        if anchors is CORE_ANCHORS:
            check_further_reading(location, data, lines, report)

    related = data.get("related")
    if "related" in data:
        if not isinstance(related, list) or not all(
            isinstance(item, str) and SLUG_PATTERN.match(item) for item in related
        ):
            report.error(location, "related muss eine Liste von Slugs sein")

    if "purpose" in data:
        check_purpose(location, data, page.language, report)

    if "short_summary" in data:
        check_short_summary(location, data, page.language, report)

    if "factsheet" in data:
        check_factsheet(location, data, anchors, page.language, report)

    if "building_blocks" in data:
        page.building_blocks = check_building_blocks(location, data, report)
    else:
        page.building_blocks = []

    last_reviewed = data.get("last_reviewed")
    if "last_reviewed" in data and not DATE_PATTERN.match(str(last_reviewed)):
        report.error(location, "last_reviewed muss ein Datum im Format YYYY-MM-DD sein")

    reviewed_by = data.get("reviewed_by")
    if "reviewed_by" in data and (not isinstance(reviewed_by, str) or not reviewed_by.strip()):
        report.error(location, "reviewed_by muss ein nicht-leerer String sein")

    check_anchors(location, lines, offset, anchors, report)
    check_containers(location, lines, offset, data, parameter_keys, markets, report)
    blocks, chapters, unconditional = collect_market_blocks(lines)
    page.market_blocks = blocks
    check_market_chapters(location, offset, blocks, chapters, unconditional, markets, report)
    check_layer_only_chapters(location, offset, *collect_visible_chapters(lines), report)
    page.faq_groups = check_faq_groups(location, lines, offset, markets, report)
    check_formulas(location, lines, offset, report)
    check_wording(location, lines, offset, report)


def check_groups(pages: Sequence[Page], report: Report) -> None:
    """Stellt sicher, dass zu jeder Seite die nötigen Sprachfassungen vorliegen."""
    by_slug: dict[str, dict[str, Page]] = {}
    for page in pages:
        by_slug.setdefault(page.slug, {})[page.language] = page

    for slug, files in sorted(by_slug.items()):
        present = files[next(iter(files))].path.name
        if "de" not in files:
            report.error(present, f"zu '{slug}' fehlt die deutsche Fassung '{slug}.de.md'")
        if "en" not in files:
            report.warn(present, f"zu '{slug}' fehlt der englische Spiegel '{slug}.en.md'")
        check_faq_group_pair(files.get("de"), files.get("en"), report)
        check_market_pair(files.get("de"), files.get("en"), report)
        check_building_blocks_pair(files.get("de"), files.get("en"), report)


def check_faq_group_pair(german: Page | None, english: Page | None, report: Report) -> None:
    """Vergleicht die FAQ-Kategorien der beiden Sprachfassungen.

    Die Titel selbst sind übersetzt und lassen sich nicht vergleichen; was das
    Paar zusammenhält, ist die Reihenfolge. Prüfbar ist davon die Anzahl der
    Gruppen: Stimmt sie, steht Gruppe *i* deutsch der Gruppe *i* englisch
    gegenüber. Eine unterschiedliche Zahl Fragen je Gruppe ist der übliche
    Nachzieh-Verzug am Spiegel und deshalb nur eine Warnung.
    """
    if german is None or english is None:
        return
    if german.faq_groups is None or english.faq_groups is None:
        return
    if not german.faq_groups and not english.faq_groups:
        return

    location = english.path.name
    if len(german.faq_groups) != len(english.faq_groups):
        report.error(
            location,
            f"die FAQ-Kategorien der Sprachfassungen zählen verschieden: "
            f"deutsch {len(german.faq_groups)}, englisch {len(english.faq_groups)}; "
            "das Paar steht in gleicher Zahl und gleicher Reihenfolge",
        )
        return

    for position, (de_group, en_group) in enumerate(zip(german.faq_groups, english.faq_groups), start=1):
        if de_group.questions != en_group.questions:
            report.warn(
                location,
                f"Kategorie {position} ('{en_group.title}') führt {en_group.questions} Fragen, "
                f"die deutsche ('{de_group.title}') {de_group.questions}",
            )


def check_market_pair(german: Page | None, english: Page | None, report: Report) -> None:
    """Vergleicht die Markt-Blöcke der beiden Sprachfassungen.

    Ein Markt-Block ist keine Übersetzungsfrage: Steht ein Absatz deutsch nur
    für `de`, muss er englisch ebenso nur für `de` stehen, sonst sieht dieselbe
    Leserin je Sprache einen anderen Text. Verglichen wird deshalb je Kapitel die
    Folge der Codes; die Reihenfolge der Codes innerhalb eines Blocks zählt
    nicht.
    """
    if german is None or english is None:
        return
    if german.market_blocks is None or english.market_blocks is None:
        return

    def by_chapter(page: Page) -> dict[str | None, list[str]]:
        grouped: dict[str | None, list[str]] = {}
        for block in page.market_blocks or []:
            grouped.setdefault(block.chapter, []).append(block.label)
        return grouped

    de_blocks = by_chapter(german)
    en_blocks = by_chapter(english)
    location = english.path.name

    chapters = list(de_blocks) + [chapter for chapter in en_blocks if chapter not in de_blocks]
    for chapter in chapters:
        left = de_blocks.get(chapter, [])
        right = en_blocks.get(chapter, [])
        if left == right:
            continue
        report.error(
            location,
            f"das Kapitel '{chapter or 'Einleitung'}' führt verschiedene Markt-Blöcke: "
            f"deutsch [{' | '.join(left) or '–'}], englisch [{' | '.join(right) or '–'}]; "
            "das Paar steht je Kapitel in gleicher Zahl, gleicher Reihenfolge und mit gleichen Codes",
        )


def check_building_blocks_pair(german: Page | None, english: Page | None, report: Report) -> None:
    """Die Bausteine sind keine Übersetzungsfrage: beide Sprachfassungen nennen dieselben."""
    if german is None or english is None:
        return
    if german.building_blocks is None or english.building_blocks is None:
        return
    if german.building_blocks != english.building_blocks:
        report.error(
            english.path.name,
            f"building_blocks weichen ab: deutsch [{', '.join(german.building_blocks) or 'keine'}], "
            f"englisch [{', '.join(english.building_blocks) or 'keine'}]",
        )


def collect_pages(content_dir: Path, report: Report) -> list[Page]:
    pages: list[Page] = []
    for path in sorted(item for item in content_dir.rglob("*.md") if item.is_file()):
        match = FILENAME_PATTERN.match(path.name)
        if match is None:
            report.error(path.name, "Dateiname muss '<slug>.<lang>.md' lauten")
            continue
        pages.append(Page(path, match.group("slug"), match.group("lang")))
    return pages


def run(
    content_dir: Path,
    registry: SlugRegistry | None = None,
    registry_path: Path = DEFAULT_REGISTRY,
    parameter_keys: ParameterKeys | None = None,
    parameter_keys_path: Path = DEFAULT_PARAMETER_KEYS,
    markets: MarketRegistry | None = None,
    markets_path: Path = DEFAULT_MARKETS,
) -> Report:
    report = Report()
    if registry is None:
        try:
            registry = SlugRegistry.load(registry_path)
        except RegistryError as exc:
            report.error(str(registry_path), str(exc))
            return report
    if parameter_keys is None:
        try:
            parameter_keys = ParameterKeys.load(parameter_keys_path)
        except RegistryError as exc:
            report.error(str(parameter_keys_path), str(exc))
            return report
    if markets is None:
        try:
            markets = MarketRegistry.load(markets_path)
        except RegistryError as exc:
            report.error(str(markets_path), str(exc))
            return report

    if not content_dir.is_dir():
        report.error(str(content_dir), "Verzeichnis existiert nicht")
        return report

    pages = collect_pages(content_dir, report)
    if not pages:
        report.error(str(content_dir), "keine Content-Dateien gefunden")
        return report

    for page in pages:
        check_file(page, registry, parameter_keys, markets, report)
    check_groups(pages, report)
    return report


def _print(lines: Iterable[str], prefix: str) -> None:
    for line in lines:
        print(f"{prefix} {line}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prüft Frontmatter und Aufbau der Content-Dateien.")
    parser.add_argument(
        "--content-dir",
        type=Path,
        default=DEFAULT_CONTENT_DIR,
        help=f"Verzeichnis mit den Content-Dateien (Standard: {DEFAULT_CONTENT_DIR})",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=DEFAULT_REGISTRY,
        help=f"Kopie der Preset-Slugs (Standard: {DEFAULT_REGISTRY})",
    )
    parser.add_argument(
        "--parameter-keys",
        type=Path,
        default=DEFAULT_PARAMETER_KEYS,
        help=f"Liste der Deskriptor-Schlüssel (Standard: {DEFAULT_PARAMETER_KEYS})",
    )
    parser.add_argument(
        "--markets",
        type=Path,
        default=DEFAULT_MARKETS,
        help=f"Register der Märkte für ':::market' (Standard: {DEFAULT_MARKETS})",
    )
    args = parser.parse_args(argv)

    report = run(
        args.content_dir,
        registry_path=args.registry,
        parameter_keys_path=args.parameter_keys,
        markets_path=args.markets,
    )
    _print(report.warnings, "WARNUNG")
    _print(report.errors, "FEHLER")

    if report.errors:
        print(f"\n{len(report.errors)} Fehler, {len(report.warnings)} Warnungen.")
        return 1
    print(f"Frontmatter und Aufbau in Ordnung ({len(report.warnings)} Warnungen).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
