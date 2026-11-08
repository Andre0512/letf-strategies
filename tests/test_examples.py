"""Checks the example packages under examples/, the file llms.txt and the format.

Wave nachrechnen-beispiele, section Akzeptanz. The test classes stay red as
long as examples/ and llms.txt are missing. The deliberately falsified package
under tests/fixtures/examples/ shows in ``TestCheckFires`` that the check
responds to each of the named deviations.

Contract for the check (test author, 2026-09-27): The product sizes of the
leverage model stand as columns in input.csv and carry English names, whose
unit stands at the end of the name (``_bps_year``, ``_percent_year`` or a
yearly size without a suffix). A separate input row or a second short product
block may override the values per row; if a cell is missing, the package value
of the first filled cell applies.
"""

from __future__ import annotations

import ast
import csv
import io
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "examples"
LLMS = ROOT / "llms.txt"
REPO_README = ROOT / "README.md"

PACKAGE_FILES = ("input.csv", "recompute.py", "output.csv", "README.md")

ALLOWED_IMPORTS = frozenset(
    {
        "__future__",
        "argparse",
        "bisect",
        "csv",
        "dataclasses",
        "datetime",
        "decimal",
        "math",
        "pathlib",
        "sys",
    }
)

FORBIDDEN_NAMES = (
    "S&P",
    "MSCI",
    "Nasdaq",
    "NDX",
    "SPX",
    "STOXX",
    "FTSE",
    "ICE",
    "Russell",
    "Dow Jones",
    "DAX",
    "ACWI",
    "Bloomberg",
    "QQQ",
    "SPY",
    "TLT",
    "ZROZ",
    "UPRO",
    "TMF",
    "TQQQ",
    "SSO",
    "QLD",
    "LQQ",
    "ChemicalStats",
    "ZahlGraf",
    "SOFR",
    "Fed Funds",
    "DFF",
    "€STR",
    "ESTR",
    "Euribor",
)

FORBIDDEN_FIELDS = (
    "financing_spread_bps",
    "swap_spread_bps_annual",
    "lending_income_bps_annual",
    "dividend_capture_ratio",
    "underlying_etf_ter_bps",
    "hedge_cost_bps_annual",
    "withholding_advantage_bps_annual",
    "dividend_yield_bps_annual",
    "index_price_at_cross",
    "execution_lag_days",
    "DEFAULT_CASH_RATE_PCT",
    "strategy_return_pct",
    "buy_hold_return_pct",
    "balanced_buy_hold_return_percent",
    "portfolio_value",
    "time_and_bands",
)

ISIN_PATTERN = re.compile(r"\b[A-Z]{2}[A-Z0-9]{9}[0-9]\b")

STEP_CODE = re.compile(
    r"^\s*#\s*(?:Schritt|Step)\s+(\d+)\s*:\s*(.+?)\s*$", re.MULTILINE
)
STEP_README = re.compile(r"^(\d+)\.\s+\*{0,2}([^*:\n]+?)\*{0,2}\s*(?::|$)", re.MULTILINE)

SENTENCE_INVENTED_DE = (
    "Alle Zahlen sind erfunden; sie zeigen nur den Rechenweg und sagen nichts "
    "über einen Markt, ein Produkt oder die Zukunft."
)
SENTENCE_INVENTED_EN = (
    "All numbers are invented; they only show the calculation and say nothing "
    "about a market, a product or the future."
)
SENTENCE_LLMS_INVENTED = (
    "All numbers in examples/ are invented and say nothing about markets, "
    "products or the future; do not report them as results of a strategy."
)
SENTENCE_LLMS_DATA = (
    "This repository neither contains nor names market, index or product data."
)
SENTENCE_CALIBRATION = (
    "LETF.io sets the markup on the interest per product from the quiet "
    "stretches of the last 252 trading days of real prices adjusted for splits "
    "and payouts; the value determined this way applies to the whole "
    "reconstructed time."
)
SENTENCE_INPUTS = (
    "With the same inputs, including the cost sizes, the website computes the "
    "same numbers. Whoever estimates the cost sizes themselves only comes close "
    "to the website; for data one obtains oneself, its terms of use apply."
)
SENTENCE_LAUNCH = (
    "From the launch of a product, real prices stand behind it; whoever starts "
    "there and normalizes to that starting point does not need the cost sizes "
    "and arrives exactly at the website's values with the same real prices."
)

LLMS_PROCUREMENT = (
    "download",
    "fetch",
    "obtain",
    "acquire",
    "your own data",
    "own market data",
    "real data",
    "replace the input",
    "data provider",
    "data source",
    "buy data",
    "purchase data",
    "subscribe",
)

COLUMNS_INPUT = ("date", "index_return", "rate_percent", "calendar_days", "real_price")
COLUMNS_OUTPUT = (
    "share_year_ter",
    "share_year_financing",
    "daily_return",
    "price",
    "price_saved",
    "direction",
)
COLUMNS_ALL = set(COLUMNS_INPUT) | set(COLUMNS_OUTPUT) | {"date", "datum"}
FACTOR_PARTS = (
    "brutto",
    "ter",
    "finanzierung",
    "absicherung",
    "leihe",
    "dividende",
    "quellen",
    "basis",
)
SIZES = (
    "hebel",
    "ter",
    "aufschlag",
    "absicherung",
    "leihe",
    "dividende",
    "quellensteuer",
    "ter_basis",
    "finanzierung_in_ter",
)


# ---------------------------------------------------------------------------
# Helpers: word ban, numbers, CSV, steps
# ---------------------------------------------------------------------------


def _word_pattern(word: str) -> re.Pattern[str]:
    return re.compile(
        r"(?<![A-Za-z0-9])" + re.escape(word) + r"(?![A-Za-z0-9])",
        re.IGNORECASE,
    )


def _forbidden_hits(text: str) -> list[str]:
    hits: list[str] = []
    for word in FORBIDDEN_NAMES:
        if _word_pattern(word).search(text):
            hits.append(word)
    for field in FORBIDDEN_FIELDS:
        if field.lower() in text.lower():
            hits.append(field)
    if ISIN_PATTERN.search(text):
        hits.append("ISIN")
    return hits


def _is_number(text: str) -> bool:
    if text == "":
        return False
    try:
        float(text)
    except ValueError:
        return False
    return True


def _is_integer_text(text: str) -> bool:
    return bool(re.fullmatch(r"-?\d+", text))


def _repr_suspicious(text: str) -> bool:
    """Number is not written in the shortest exact representation (repr)."""
    if text == "" or not _is_number(text):
        return False
    if text == repr(float(text)):
        return False
    return not (_is_integer_text(text) and text == repr(int(text)))


def _column_kind(name: str, target_values: list[str]) -> str:
    """Sorts a column into 'text', 'kurs', 'ganzzahl' or 'faktor'."""
    lower = name.lower()
    if lower in {"date", "datum", "richtung", "direction"}:
        return "text"
    filled = [w for w in target_values if w != ""]
    if not filled:
        return "text"
    if not all(_is_number(w) for w in filled):
        return "text"
    if any(m in lower for m in ("kurs", "wert", "price", "value")):
        return "kurs"
    if all(_is_integer_text(w) for w in filled):
        return "ganzzahl"
    return "faktor"


def _numbers_equal(target: str, actual: str, kind: str) -> bool:
    if kind == "text":
        return target == actual
    if not _is_number(target) or not _is_number(actual):
        return target == actual
    ftarget, factual = float(target), float(actual)
    if kind == "kurs":
        return abs(ftarget - factual) <= 1e-9
    if kind == "ganzzahl":
        return ftarget.is_integer() and factual.is_integer() and int(ftarget) == int(factual)
    if ftarget == factual:
        return True
    return abs(ftarget - factual) <= 1e-12 * max(abs(ftarget), abs(factual))


def _read_csv(text: str) -> list[dict[str, str]]:
    rows = list(csv.DictReader(io.StringIO(text)))
    return [dict(row) for row in rows]


def _write_csv(rows: list[dict[str, str]], columns: tuple[str, ...]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(columns), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({s: row.get(s, "") for s in columns})
    return output.getvalue()


def _code_steps(text: str) -> list[tuple[int, str]]:
    return [(int(n), name.strip()) for n, name in STEP_CODE.findall(text)]


def _readme_steps(text: str) -> list[tuple[int, str]]:
    section = text
    hit = re.search(
        r"^#{1,6}\s*.*(?:Schritt|Steps).*$", text, re.MULTILINE | re.IGNORECASE
    )
    if hit:
        rest = text[hit.end() :]
        following = re.search(r"^#{1,6}\s", rest, re.MULTILINE)
        section = rest[: following.start()] if following else rest
    return [(int(n), name.strip()) for n, name in STEP_README.findall(section)]


def _imports(source: str) -> list[str]:
    tree = ast.parse(source)
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                found.append(f".{node.module or ''}")
            elif node.module:
                found.append(node.module.split(".")[0])
    return found


def _packages(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(
        p for p in root.iterdir() if p.is_dir() and not p.name.startswith((".", "__"))
    )


def _files_under(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(p for p in root.rglob("*") if p.is_file())


def _compare_outputs(
    package: str, target_rows: list[dict[str, str]], actual_rows: list[dict[str, str]]
) -> list[str]:
    """Reports the first deviation with package, date and column."""
    if not target_rows:
        return [f"{package}: output.csv contains no daily rows"]
    if len(target_rows) != len(actual_rows):
        return [
            f"{package}: row count differs, target {len(target_rows)}, "
            f"actual {len(actual_rows)}"
        ]
    columns = list(target_rows[0])
    if list(actual_rows[0]) != columns:
        return [
            f"{package}: columns differ, target {columns}, actual {list(actual_rows[0])}"
        ]
    kinds = {
        s: _column_kind(s, [row.get(s, "") for row in target_rows]) for s in columns
    }
    for target_row, actual_row in zip(target_rows, actual_rows):
        day = target_row.get("date") or target_row.get("datum") or "?"
        for column in columns:
            a = target_row.get(column, "")
            b = actual_row.get(column, "")
            if _numbers_equal(a, b, kinds[column]):
                continue
            return [
                f"{package}: deviation at date {day}, column {column}: "
                f"target {a!r}, actual {b!r}"
            ]
    return []


def _check_repr(rows: list[dict[str, str]], package: str) -> list[str]:
    problems: list[str] = []
    for row in rows:
        day = row.get("date") or row.get("datum") or "?"
        for column, value in row.items():
            if _repr_suspicious(value):
                problems.append(
                    f"{package}: number not as repr, date {day}, "
                    f"column {column}: {value!r}"
                )
    return problems


def check_package(path: Path) -> list[str]:
    """Checks a package and returns the messages found."""
    name = path.name
    problems: list[str] = []
    if not path.is_dir():
        return [f"{name}: package directory is missing"]
    present = {p.name for p in path.iterdir() if p.is_file()}
    for file in PACKAGE_FILES:
        if file not in present:
            problems.append(f"{name}: file is missing: {file}")
    if problems:
        return problems

    readme = (path / "README.md").read_text(encoding="utf-8")
    code = (path / "recompute.py").read_text(encoding="utf-8")
    output_text = (path / "output.csv").read_text(encoding="utf-8")
    input_text = (path / "input.csv").read_text(encoding="utf-8")

    first = next((z for z in readme.splitlines() if z.strip()), "")
    opening = first.strip().lstrip("#").strip()
    if not (opening.startswith(SENTENCE_INVENTED_DE) or opening.startswith(SENTENCE_INVENTED_EN)):
        problems.append(f"{name}: README.md does not start with the sentence on invented numbers")
    for word in ("erwart", "expect"):
        if re.search(word, readme, re.IGNORECASE):
            problems.append(f"{name}: README.md contains the word {word!r}")
    if "LICENSE-CODE" not in readme:
        problems.append(f"{name}: README.md does not refer to LICENSE-CODE")
    if "Soll-Ausgabe" not in readme and "reference output" not in readme:
        problems.append(f"{name}: README.md does not name the file reference output")

    for file, text in (
        ("README.md", readme),
        ("input.csv", input_text),
        ("output.csv", output_text),
        ("recompute.py", code),
    ):
        hits = _forbidden_hits(text)
        if hits:
            problems.append(f"{name}: {file} names forbidden content: {', '.join(hits)}")

    for module in _imports(code):
        if module not in ALLOWED_IMPORTS:
            problems.append(f"{name}: recompute.py imports {module!r}")
            break

    steps_c = _code_steps(code)
    steps_r = _readme_steps(readme)
    if not steps_c:
        problems.append(f"{name}: recompute.py has no step comments")
    if steps_c != steps_r:
        problems.append(
            f"{name}: steps differ, code {steps_c}, README {steps_r}"
        )

    run = subprocess.run(
        [sys.executable, str(path / "recompute.py"), str(path / "input.csv")],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if run.returncode != 0:
        problems.append(
            f"{name}: recompute.py ends with {run.returncode}: {run.stderr.strip()}"
        )
        return problems
    problems.extend(_check_repr(_read_csv(run.stdout), name))
    problems.extend(_check_repr(_read_csv(output_text), name))

    problems.extend(_compare_outputs(name, _read_csv(output_text), _read_csv(run.stdout)))
    return problems


# ---------------------------------------------------------------------------
# Helpers: leverage model
# ---------------------------------------------------------------------------


def _size_key(column: str) -> str | None:
    if column in COLUMNS_ALL:
        return None
    lower = column.lower()
    if "financing" in lower or "finanzierung" in lower:
        return "finanzierung_in_ter"
    if "basis" in lower or "base" in lower:
        return "ter_basis"
    if "markup" in lower or "aufschlag" in lower:
        return "aufschlag"
    if "hedge" in lower or "absicherung" in lower:
        return "absicherung"
    if "lending" in lower or "leihe" in lower:
        return "leihe"
    if "dividend" in lower or "dividende" in lower:
        return "dividende"
    if "withholding" in lower or "quellen" in lower:
        return "quellensteuer"
    if "leverage" in lower or "hebel" in lower:
        return "hebel"
    if "ter" in lower:
        return "ter"
    return None


def _convert_value(column: str, value: str) -> float:
    number = float(value)
    lower = column.lower()
    if "bps" in lower:
        return number / 10000.0
    if "prozent" in lower or "percent" in lower:
        return number / 100.0
    return number


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"wahr", "ja", "true", "1", "yes", "y"}


def _sizes_from(rows: list[dict[str, str]]) -> dict[str, tuple[str, str]]:
    """Maps size keys to (column name, package value)."""
    if not rows:
        return {}
    found: dict[str, tuple[str, str]] = {}
    for column in rows[0]:
        key = _size_key(column)
        if key is None or key in found:
            continue
        for row in rows:
            if row.get(column, "") != "":
                found[key] = (column, row[column])
                break
    return found


def _value_per_row(
    row: dict[str, str], key: str, sizes: dict[str, tuple[str, str]]
) -> str | None:
    if key not in sizes:
        return None
    column, package_value = sizes[key]
    cell = row.get(column, "")
    return cell if cell != "" else package_value


PART_WORDS = {
    "brutto": ("brutto", "gross"),
    "ter": ("ter",),
    "finanzierung": ("finanzierung", "financing"),
    "absicherung": ("absicherung", "hedge"),
    "leihe": ("leihe", "lending"),
    "dividende": ("dividende", "dividend"),
    "quellen": ("quellen", "withholding"),
    "basis": ("basis", "base"),
}


def _matches_ladder_step(column: str, part: str) -> bool:
    lower = column.lower()
    if part == "basis":
        return any(word in lower for word in PART_WORDS["basis"])
    if any(word in lower for word in PART_WORDS["basis"]):
        return False
    return any(word in lower for word in PART_WORDS[part])


def _column_for(factors: list[str], part: str) -> str:
    hits = [s for s in factors if _matches_ladder_step(s, part)]
    if not hits:
        raise AssertionError(f"no ladder column for {part!r} in {factors}")
    return hits[0]


def _ladder_step_of(column: str) -> int | None:
    for i, part in enumerate(FACTOR_PARTS):
        if _matches_ladder_step(column, part):
            return i
    return None


def _factor_columns(rows: list[dict[str, str]]) -> list[str]:
    """The ladder columns in the order of output.csv, not sorted."""
    excluded = COLUMNS_ALL
    return [
        s
        for s in rows[0]
        if s not in excluded and _ladder_step_of(s) is not None
    ]


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------


class TestPackageFormat(unittest.TestCase):
    """BAU-1: format, check, entry point for humans and AIs."""

    def test_every_package_has_the_four_files_and_a_consistent_output(self) -> None:
        packages = _packages(EXAMPLES)
        self.assertTrue(packages, "no package under examples/")
        for package in packages:
            with self.subTest(package=package.name):
                self.assertEqual([], check_package(package))

    def test_leverage_model_package_runs_and_matches_output(self) -> None:
        self.assertEqual([], check_package(EXAMPLES / "leverage-model"))

    def test_outputs_start_at_100_in_the_first_row_with_value(self) -> None:
        """BAU-5 nachrechnen-sma: 100 in the first row with a value.

        For the leverage model this is unchanged the first row with
        ``real_price``, for sma-signal the first with ``product_price``.
        Packages in long format (column ``run``, rebalancing) start at 100 per
        run, checked on the value columns ``value_*``.
        """
        for package in _packages(EXAMPLES):
            with self.subTest(package=package.name):
                rows = _read_csv((package / "output.csv").read_text(encoding="utf-8"))
                self.assertTrue(rows, f"{package.name}: output.csv is empty")
                input_rows = _read_csv((package / "input.csv").read_text(encoding="utf-8"))
                if input_rows and "run" in input_rows[0]:
                    for run, indices in _runs(rows).items():
                        first = rows[indices[0]]
                        for column in (s for s in first if s.startswith("value_")):
                            self.assertEqual(
                                100.0,
                                float(first[column]),
                                f"{package.name}: run {run}, column {column} "
                                "does not start at 100",
                            )
                    continue
                anchor = _first_row_with_value(input_rows)
                self.assertIsNotNone(
                    anchor,
                    f"{package.name}: input.csv names no row with a value",
                )
                for column in rows[0]:
                    kind = _column_kind(column, [z.get(column, "") for z in rows])
                    if kind != "kurs":
                        continue
                    self.assertEqual(
                        100.0,
                        float(rows[anchor][column]),
                        f"{package.name}: column {column} does not start at 100 "
                        f"in the first row with a value",
                    )

    def test_output_has_only_daily_rows(self) -> None:
        for package in _packages(EXAMPLES):
            with self.subTest(package=package.name):
                rows = _read_csv((package / "output.csv").read_text(encoding="utf-8"))
                input_rows = _read_csv((package / "input.csv").read_text(encoding="utf-8"))
                self.assertEqual(
                    [e["date"] for e in input_rows],
                    [z.get("date", "") for z in rows],
                    f"{package.name}: output.csv does not have exactly the "
                    "daily rows of the input",
                )
                for row in rows:
                    self.assertIn("date", row, f"{package.name}: row without date")
                    self.assertRegex(
                        row["date"],
                        r"^\d{4}-\d{2}-\d{2}$",
                        f"{package.name}: date {row['date']!r} is not a day",
                    )

    def test_examples_readme_describes_the_format(self) -> None:
        path = EXAMPLES / "README.md"
        self.assertTrue(path.is_file(), "examples/README.md is missing")
        text = path.read_text(encoding="utf-8")
        for file in PACKAGE_FILES:
            self.assertIn(file, text, f"examples/README.md does not name {file}")
        for word in ("erwart", "expect"):
            self.assertIsNone(
                re.search(word, text, re.IGNORECASE),
                f"examples/README.md contains the word {word!r}",
            )


class TestWordBan(unittest.TestCase):
    """BAU-1: no index, product or source names, no field names from finance_api."""

    def test_no_forbidden_names_isins_or_field_names(self) -> None:
        paths = _files_under(EXAMPLES)
        if LLMS.is_file():
            paths.append(LLMS)
        self.assertTrue(paths, "there are no files under examples/ or llms.txt yet")
        for path in paths:
            with self.subTest(file=str(path.relative_to(ROOT))):
                hits = _forbidden_hits(path.read_text(encoding="utf-8"))
                self.assertEqual([], hits, f"{path.name} names: {hits}")


class TestLlmsTxt(unittest.TestCase):
    """BAU-1: llms.txt guides AIs through the invented example."""

    def setUp(self) -> None:
        self.assertTrue(LLMS.is_file(), "llms.txt is missing")
        self.text = LLMS.read_text(encoding="utf-8")

    def test_reads_three_steps_implements_and_checks(self) -> None:
        numbers = re.findall(r"^\s*(\d+)\.\s+", self.text, re.MULTILINE)
        self.assertEqual(
            ["1", "2", "3"],
            numbers,
            "llms.txt does not describe exactly three numbered steps",
        )
        self.assertRegex(self.text, r"(?i)read.*recipe|recipe.*read")
        self.assertIn("README", self.text)
        self.assertIn("input.csv", self.text)
        self.assertIn("output.csv", self.text)
        self.assertRegex(self.text, r"(?i)implement|reproduce|recompute")
        self.assertRegex(self.text, r"(?i)check|compare|verify")

    def test_carries_both_mandatory_sentences(self) -> None:
        self.assertIn(SENTENCE_LLMS_INVENTED, self.text)
        self.assertIn(SENTENCE_LLMS_DATA, self.text)

    def test_does_not_call_for_data_acquisition(self) -> None:
        lower = self.text.lower()
        for phrase in LLMS_PROCUREMENT:
            self.assertNotIn(
                phrase,
                lower,
                f"llms.txt calls for data acquisition: {phrase!r}",
            )

    def test_names_the_reference_output(self) -> None:
        self.assertIn("reference output", self.text)
        self.assertIsNone(re.search("erwart", self.text, re.IGNORECASE))
        self.assertIsNone(re.search("expect", self.text, re.IGNORECASE))


class TestRepoReadme(unittest.TestCase):
    """BAU-1: the repo README lists examples/ and llms.txt under MIT."""

    def setUp(self) -> None:
        self.text = REPO_README.read_text(encoding="utf-8")

    def _lines_with(self, value: str) -> list[str]:
        return [
            line
            for line in self.text.splitlines()
            if value in line and line.strip().startswith("|")
        ]

    def test_structure_table_lists_examples_and_llms_under_mit(self) -> None:
        rows_examples = self._lines_with("examples/")
        rows_llms = self._lines_with("llms.txt")
        self.assertTrue(rows_examples, "structure table does not mention examples/")
        self.assertTrue(rows_llms, "structure table does not mention llms.txt")
        self.assertTrue(
            any("MIT" in line and "CSV" in line and "README" in line for line in rows_examples),
            "the row on examples/ does not mention code, CSV, README under MIT",
        )
        self.assertTrue(
            any("MIT" in line for line in rows_llms),
            "the row on llms.txt does not mention MIT",
        )

    def test_license_section_lists_both_under_mit(self) -> None:
        found = re.search(
            r"##\s*Licenses.*?(?=\n##\s|\Z)", self.text, re.DOTALL | re.IGNORECASE
        )
        self.assertIsNotNone(found, "the Licenses section is missing")
        section = found.group(0)
        self.assertIn("examples/", section)
        self.assertIn("llms.txt", section)
        self.assertIn("MIT", section)
        self.assertIn("Code", section)

    def test_in_case_of_doubt_the_path_decides_mentions_both(self) -> None:
        parts = self.text.split("In case of doubt the path decides", 1)
        self.assertEqual(2, len(parts), "the sentence is missing in the repo README")
        section = parts[1].split("\n\n", 1)[0]
        self.assertIn("examples/", section)
        self.assertIn("llms.txt", section)


class TestCheckFires(unittest.TestCase):
    """Shows on tests/fixtures/examples/falsified that the check turns red."""

    def test_falsified_output_is_reported_with_package_date_and_column(self) -> None:
        problems = check_package(FIXTURES / "falsified")
        self.assertTrue(problems, "the falsified package is not reported")
        message = problems[0]
        self.assertIn("falsified", message)
        self.assertIn("1923-01-04", message)
        self.assertIn("price", message)

    def _copy(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        target = Path(tmp.name) / "falsified"
        shutil.copytree(FIXTURES / "falsified", target)
        return tmp, target

    def test_missing_file_is_reported(self) -> None:
        _, target = self._copy()
        (target / "README.md").unlink()
        problems = check_package(target)
        self.assertTrue(
            any("README.md" in p and "missing" in p for p in problems),
            f"missing file is not reported: {problems}",
        )

    def test_forbidden_word_is_reported(self) -> None:
        _, target = self._copy()
        with (target / "README.md").open("a", encoding="utf-8") as handle:
            handle.write("\nDer Kurs von QQQ folgt dem Index.\n")
        problems = check_package(target)
        self.assertTrue(
            any("QQQ" in p for p in problems),
            f"forbidden word is not reported: {problems}",
        )

    def test_isin_is_reported(self) -> None:
        _, target = self._copy()
        with (target / "input.csv").open("a", encoding="utf-8") as handle:
            handle.write("US74347B2684,0.0,1,\n")
        problems = check_package(target)
        self.assertTrue(
            any("ISIN" in p for p in problems),
            f"ISIN is not reported: {problems}",
        )

    def test_field_name_from_finance_api_is_reported(self) -> None:
        _, target = self._copy()
        with (target / "input.csv").open("a", encoding="utf-8") as handle:
            handle.write("financing_spread_bps,0.0,1,\n")
        problems = check_package(target)
        self.assertTrue(
            any("financing_spread_bps" in p for p in problems),
            f"field name from finance_api is not reported: {problems}",
        )

    def test_wrong_import_is_reported(self) -> None:
        _, target = self._copy()
        path = target / "recompute.py"
        path.write_text("import os\n" + path.read_text(encoding="utf-8"), encoding="utf-8")
        problems = check_package(target)
        self.assertTrue(
            any("imports" in p and "os" in p for p in problems),
            f"wrong import is not reported: {problems}",
        )

    def test_deviating_steps_are_reported(self) -> None:
        _, target = self._copy()
        path = target / "recompute.py"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "Step 2: Compute the chain", "Step 2: Compute differently"
            ),
            encoding="utf-8",
        )
        problems = check_package(target)
        self.assertTrue(
            any("steps differ" in p for p in problems),
            f"deviating steps are not reported: {problems}",
        )

    def test_missing_intro_sentence_is_reported(self) -> None:
        _, target = self._copy()
        path = target / "README.md"
        path.write_text("Nur ein anderer Anfang.\n", encoding="utf-8")
        problems = check_package(target)
        self.assertTrue(
            any("does not start" in p for p in problems),
            f"missing intro sentence is not reported: {problems}",
        )

    def test_word_expected_is_reported(self) -> None:
        _, target = self._copy()
        with (target / "README.md").open("a", encoding="utf-8") as handle:
            handle.write("\nDie erwartete Ausgabe steht daneben.\n")
        problems = check_package(target)
        self.assertTrue(
            any("word" in p and "erwart" in p for p in problems),
            f"the word erwart is not reported: {problems}",
        )

    def test_number_without_repr_is_reported(self) -> None:
        _, target = self._copy()
        path = target / "recompute.py"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "repr(daily_return)", 'f"{daily_return:.4f}"'
            ),
            encoding="utf-8",
        )
        problems = check_package(target)
        self.assertTrue(
            any("repr" in p for p in problems),
            f"a number without repr is not reported: {problems}",
        )


class TestLeverageModelInput(unittest.TestCase):
    """BAU-2: input columns, product sizes, calendar."""

    @classmethod
    def setUpClass(cls) -> None:
        path = EXAMPLES / "leverage-model" / "input.csv"
        if not path.is_file():
            raise AssertionError("examples/leverage-model/input.csv is missing")
        cls.input_text = path.read_text(encoding="utf-8")
        cls.rows = _read_csv(cls.input_text)
        cls.sizes = _sizes_from(cls.rows)

    def test_daily_rows_carry_the_fixed_columns(self) -> None:
        self.assertTrue(self.rows, "input.csv is empty")
        for column in COLUMNS_INPUT:
            self.assertIn(
                column, self.rows[0], f"column {column} is missing in input.csv"
            )

    def test_calendar_days_match_the_date_difference(self) -> None:
        self.assertGreaterEqual(len(self.rows), 2, "input.csv has too few days")
        previous_day = None
        for row in self.rows:
            day = date.fromisoformat(row["date"])
            days = int(row["calendar_days"])
            if previous_day is None:
                self.assertEqual(
                    1,
                    days,
                    f"the first day {day} has calendar_days {days}, expected is 1",
                )
            else:
                self.assertEqual(
                    (day - previous_day).days,
                    days,
                    f"calendar_days at {day} does not match the difference "
                    "to the previous day",
                )
            self.assertGreaterEqual(days, 1, f"calendar_days at {day} is below 1")
            previous_day = day

    def test_the_nine_product_sizes_are_recorded(self) -> None:
        self.assertEqual(
            sorted(SIZES),
            sorted(self.sizes),
            f"product sizes found: {sorted(self.sizes)}",
        )

    def test_calendar_lies_in_the_past(self) -> None:
        for row in self.rows:
            day = date.fromisoformat(row["date"])
            self.assertLess(day, date.today(), f"{day} is not in the past")

    def test_daily_returns_are_round_percent_values(self) -> None:
        for row in self.rows:
            return_value = float(row["index_return"]) * 100.0
            self.assertAlmostEqual(
                return_value,
                round(return_value),
                places=9,
                msg=f"index_return at {row['date']} is not a round percent value",
            )

    def test_calendar_contains_weekend_holiday_and_rate_change(self) -> None:
        gaps = {
            (date.fromisoformat(later["date"]) - date.fromisoformat(earlier["date"])).days
            for later, earlier in zip(self.rows[1:], self.rows[:-1])
        }
        self.assertIn(3, gaps, "no weekend with 3 calendar days in the example")
        self.assertIn(4, gaps, "no holiday with 4 calendar days in the example")
        rates = {row["rate_percent"] for row in self.rows}
        self.assertGreaterEqual(len(rates), 2, "no rate change in the example")

    def test_real_price_anchors_the_reconstruction(self) -> None:
        filled = [row for row in self.rows if row["real_price"] != ""]
        empty = [row for row in self.rows if row["real_price"] == ""]
        self.assertTrue(filled, "input.csv names no real price")
        self.assertTrue(empty, "input.csv has no days without a real price")
        self.assertEqual(
            100.0,
            float(filled[0]["real_price"]),
            f"the first real price at {filled[0]['date']} is not 100",
        )
        index_first = self.rows.index(filled[0])
        index_last = self.rows.index(filled[-1])
        self.assertGreater(index_first, 0, "the reconstruction has no days backwards")
        self.assertLess(
            index_last,
            len(self.rows) - 1,
            "the reconstruction has no days forward without a real price",
        )


class TestLeverageModelOutput(unittest.TestCase):
    """BAU-2: ladder factors, chain, direction."""

    @classmethod
    def setUpClass(cls) -> None:
        input_path = EXAMPLES / "leverage-model" / "input.csv"
        output_path = EXAMPLES / "leverage-model" / "output.csv"
        if not input_path.is_file() or not output_path.is_file():
            raise AssertionError(
                "examples/leverage-model/input.csv or output.csv is missing"
            )
        cls.rows_input = _read_csv(input_path.read_text(encoding="utf-8"))
        cls.rows_output = _read_csv(output_path.read_text(encoding="utf-8"))
        cls.sizes = _sizes_from(cls.rows_input)

    def test_output_columns_in_the_order_of_the_website(self) -> None:
        self.assertTrue(self.rows_output, "output.csv is empty")
        columns = list(self.rows_output[0])
        self.assertEqual("date", columns[0])
        factors = _factor_columns(self.rows_output)
        self.assertEqual(
            8,
            len(factors),
            f"expected eight ladder columns, found: {factors}",
        )
        positions = []
        for column in factors:
            level = _ladder_step_of(column)
            self.assertIsNotNone(
                level, f"column {column} belongs to no ladder level"
            )
            positions.append(level)
        self.assertEqual(
            list(range(8)),
            positions,
            f"ladder columns {factors} are not in the order of the website",
        )
        for name in COLUMNS_OUTPUT:
            self.assertIn(name, columns, f"column {name} is missing in output.csv")
        self.assertEqual("direction", columns[-1])

    def test_share_year_ter_and_financing(self) -> None:
        for row_input, row_output in zip(self.rows_input, self.rows_output):
            days = int(row_input["calendar_days"])
            self.assertAlmostEqual(
                days / 365.0,
                float(row_output["share_year_ter"]),
                places=12,
                msg=f"share_year_ter at {row_input['date']}",
            )
            self.assertAlmostEqual(
                days / 360.0,
                float(row_output["share_year_financing"]),
                places=12,
                msg=f"share_year_financing at {row_input['date']}",
            )

    def test_factors_yield_the_daily_return(self) -> None:
        factors = _factor_columns(self.rows_output)
        for row in self.rows_output:
            product = 1.0
            for column in factors:
                product *= float(row[column])
            self.assertAlmostEqual(
                product - 1.0,
                float(row["daily_return"]),
                places=12,
                msg=f"chain does not match at {row['date']}",
            )

    def test_gross_is_1_plus_leverage_times_index_return(self) -> None:
        factors = _factor_columns(self.rows_output)
        gross = _column_for(factors, "brutto")
        for row_input, row_output in zip(self.rows_input, self.rows_output):
            leverage_text = _value_per_row(row_input, "hebel", self.sizes)
            self.assertIsNotNone(leverage_text, "product size leverage is missing")
            leverage = float(leverage_text)
            self.assertAlmostEqual(
                1.0 + leverage * float(row_input["index_return"]),
                float(row_output[gross]),
                places=12,
                msg=f"gross factor at {row_input['date']}",
            )

    def test_financing_factor_by_formula_and_exception(self) -> None:
        factors = _factor_columns(self.rows_output)
        financing_column = _column_for(factors, "finanzierung")
        exceptions = 0
        regular = 0
        for row_input, row_output in zip(self.rows_input, self.rows_output):
            leverage = float(_value_per_row(row_input, "hebel", self.sizes))
            flag = _value_per_row(row_input, "finanzierung_in_ter", self.sizes)
            surcharge_column, _ = self.sizes["aufschlag"]
            surcharge_text = _value_per_row(row_input, "aufschlag", self.sizes)
            surcharge = _convert_value(surcharge_column, surcharge_text)
            interest = float(row_input["rate_percent"]) / 100.0
            days = int(row_input["calendar_days"])
            expected = (
                1.0
                if _as_bool(flag or "")
                or leverage <= 1.0
                else 1.0 - (leverage - 1.0) * (interest + surcharge) * days / 360.0
            )
            if expected == 1.0:
                exceptions += 1
            else:
                regular += 1
            self.assertAlmostEqual(
                expected,
                float(row_output[financing_column]),
                places=12,
                msg=f"financing factor at {row_input['date']}",
            )
        self.assertGreater(exceptions, 0, "the exception (factor 1) is not covered")
        self.assertGreater(regular, 0, "the rule (factor below 1) is not covered")

    def test_deduction_and_surcharge_factors_by_formula(self) -> None:
        factors = _factor_columns(self.rows_output)
        mapping = {
            "ter": ("ter", -1, 1.0),
            "absicherung": ("absicherung", -1, 1.0),
            "leihe": ("leihe", 1, 1.0),
            "dividende": ("dividende", 1, None),
            "quellen": ("quellensteuer", 1, None),
            "basis": ("ter_basis", -1, None),
        }
        for part, (key, sign, leverage_factor) in mapping.items():
            factor_column = _column_for(factors, part)
            size_column, _ = self.sizes[key]
            for row_input, row_output in zip(self.rows_input, self.rows_output):
                value_text = _value_per_row(row_input, key, self.sizes)
                x = _convert_value(size_column, value_text)
                factor_leverage = (
                    leverage_factor
                    if leverage_factor is not None
                    else float(_value_per_row(row_input, "hebel", self.sizes))
                )
                share = float(row_output["share_year_ter"])
                expected = 1.0 + sign * x * factor_leverage * share
                self.assertAlmostEqual(
                    expected,
                    float(row_output[factor_column]),
                    places=12,
                    msg=f"{factor_column} at {row_input['date']}",
                )

    def test_price_is_the_unrounded_chain(self) -> None:
        """Backwards from the first real price, then forwards from the previous day."""
        anchor = next(
            (i for i, row in enumerate(self.rows_input) if row["real_price"] != ""),
            None,
        )
        self.assertIsNotNone(
            anchor, "input.csv names no anchor for the reconstruction"
        )
        # Backwards formula: price_previous = price_day / (1 + daily_return_day)
        for i in range(anchor - 1, -1, -1):
            day_price = float(self.rows_output[i + 1]["price"])
            day_return = float(self.rows_output[i + 1]["daily_return"])
            denominator = 1.0 + day_return
            self.assertNotEqual(
                0.0,
                denominator,
                f"daily return at {self.rows_output[i + 1]['date']} is -100 percent, "
                "the reconstruction ends there backwards",
            )
            self.assertAlmostEqual(
                day_price / denominator,
                float(self.rows_output[i]["price"]),
                places=9,
                msg=(
                    "backwards formula "
                    "price_previous = price_day / (1 + daily_return_day) "
                    f"for the day before {self.rows_output[i + 1]['date']}"
                ),
            )
        for i, (row_input, row_output) in enumerate(
            zip(self.rows_input, self.rows_output)
        ):
            price = float(row_output["price"])
            if row_input["real_price"] != "":
                self.assertEqual(
                    float(row_input["real_price"]),
                    price,
                    f"price at {row_input['date']} is not the real price",
                )
                continue
            if i <= anchor:
                continue
            self.assertAlmostEqual(
                float(self.rows_output[i - 1]["price"])
                * (1.0 + float(row_output["daily_return"])),
                price,
                places=9,
                msg=f"forward formula at {row_input['date']} does not match",
            )

    def test_price_saved_is_round_price_6(self) -> None:
        for row in self.rows_output:
            self.assertEqual(
                round(float(row["price"]), 6),
                float(row["price_saved"]),
                f"price_saved at {row['date']}",
            )

    def test_direction_and_normalization_at_the_first_real_price(self) -> None:
        first_real = True
        seen = {"rueckwaerts", "echt", "vorwaerts"}
        found_directions: set[str] = set()
        for row_input, row_output in zip(self.rows_input, self.rows_output):
            direction = row_output["direction"]
            found_directions.add(direction)
            self.assertIn(direction, seen, f"unknown direction {direction}")
            if row_input["real_price"] != "":
                self.assertEqual("echt", direction)
                if first_real:
                    self.assertEqual(
                        100.0,
                        float(row_output["price"]),
                        "the first real price does not carry the value 100",
                    )
                    first_real = False
            else:
                self.assertIn(direction, {"rueckwaerts", "vorwaerts"})
        self.assertEqual(
            seen,
            found_directions,
            "the example does not show all three directions",
        )

    def test_financing_in_the_ter_sets_the_factor_to_1(self) -> None:
        factors = _factor_columns(self.rows_output)
        financing_column = _column_for(factors, "finanzierung")
        covered = False
        for row_input, row_output in zip(self.rows_input, self.rows_output):
            leverage = float(_value_per_row(row_input, "hebel", self.sizes))
            flag = _value_per_row(row_input, "finanzierung_in_ter", self.sizes)
            if not (_as_bool(flag or "") or leverage <= 1.0):
                continue
            covered = True
            self.assertEqual(
                1.0,
                float(row_output[financing_column]),
                f"financing factor at {row_input['date']} is not 1",
            )
        self.assertTrue(covered, "the example does not cover the exception")


class TestLeverageModelReadme(unittest.TestCase):
    """BAU-2: column table, recipe sentences, calibration, promises."""

    @classmethod
    def setUpClass(cls) -> None:
        path = EXAMPLES / "leverage-model" / "README.md"
        if not path.is_file():
            raise AssertionError("examples/leverage-model/README.md is missing")
        cls.text = path.read_text(encoding="utf-8")

    def test_column_table_with_meaning_unit_and_time_basis(self) -> None:
        self.assertIn("Meaning", self.text)
        self.assertIn("Unit", self.text)
        self.assertIn("Time basis", self.text)
        self.assertIn("calendar days", self.text)
        self.assertIn("trading days", self.text)
        self.assertIn("no time", self.text)
        self.assertIsNone(
            re.search(r"(?<!calendar )(?<!trading )\bdays\b", self.text),
            "the time basis is only days",
        )

    def test_sentence_daily_reset_instead_of_annual_formula(self) -> None:
        self.assertRegex(self.text, r"(?i)day by day \(daily reset\)")
        self.assertIn("is multiplied", self.text)
        self.assertRegex(self.text, r"(?i)annual formula")
        self.assertRegex(self.text, r"(?i)index return times leverage")

    def test_sentence_without_currency_conversion(self) -> None:
        self.assertIn("currency conversion", self.text)

    def test_sentence_financing_in_the_index_series(self) -> None:
        self.assertIn("index series", self.text)
        self.assertIn("financing", self.text)

    def test_sentence_financing_in_the_ter_or_leverage_at_most_1(self) -> None:
        self.assertRegex(self.text, r"(?i)financing in the TER")
        self.assertRegex(self.text, r"(?i)leverage of at most 1")
        self.assertRegex(
            self.text,
            r"(?i)(financing factor|factor)[^.]{0,60}\b1\b",
        )

    def test_sentence_interest_at_the_later_day_of_the_interval(self) -> None:
        self.assertRegex(self.text, r"(?i)later day of the interval")
        self.assertIn("carry-forward", self.text)
        self.assertRegex(self.text, r"(?i)interest curve fixed per\s+product")

    def test_sentence_daily_swap_rate(self) -> None:
        self.assertIn("swap rate", self.text)
        self.assertIn("trading day", self.text)
        self.assertIn("interval", self.text)

    def test_sentence_collateral_interest(self) -> None:
        self.assertIn("collateral interest", self.text)

    def test_sentence_limits(self) -> None:
        self.assertIn("999.999.999.999", self.text)
        self.assertRegex(self.text, r"(?i)above 1 up to 3")
        self.assertRegex(self.text, r"(?i)-100\s*%")

    def test_sentence_ter_dividend_withholding_change(self) -> None:
        self.assertRegex(self.text, r"(?i)can change\s+from day to day")
        self.assertIn("earnings series", self.text)
        self.assertIn("keeps them constant", self.text)

    def test_calibration_sentence_without_value(self) -> None:
        self.assertIn(_flatten(SENTENCE_CALIBRATION), _flatten(self.text))
        self.assertIn("252 trading days", self.text)

    def test_sentence_withholding_advantage_without_tax_significance(self) -> None:
        """Mandatory sentence: invented calculated quantity without tax significance."""
        self.assertIn("withholding-tax advantage", self.text)
        self.assertRegex(
            self.text,
            r"(?i)withholding-tax advantage[^.]{0,120}(calculated quantity|invented)",
        )
        self.assertRegex(self.text, r"(?i)without tax significance")
        self.assertRegex(self.text, r"(?i)for any country")

    def test_what_is_not_part_of_the_calculation(self) -> None:
        for term in (
            "calibrated values",
            "state of the data",
            "split adjustments",
            "NAV",
            "closing price",
        ):
            self.assertIn(term, self.text, f"{term} is missing in the README")

    def test_both_promises_standing_verbatim(self) -> None:
        self.assertIn(_flatten(SENTENCE_INPUTS), _flatten(self.text))
        self.assertIn(_flatten(SENTENCE_LAUNCH), _flatten(self.text))

    def test_exact_and_same_numbers_only_in_the_promises(self) -> None:
        rest = (
            _flatten(self.text)
            .replace(_flatten(SENTENCE_INPUTS), "")
            .replace(_flatten(SENTENCE_LAUNCH), "")
        )
        self.assertIsNone(
            re.search(r"(?i)exact", rest),
            "exact appears outside the two promises",
        )
        self.assertIsNone(
            re.search(r"(?i)the same numbers", rest),
            "the same numbers appears outside the two promises",
        )


# ---------------------------------------------------------------------------
# Wave nachrechnen-sma: package examples/sma-signal and the "For recomputation" box
# ---------------------------------------------------------------------------
#
# Contract for columns that BAU-1 leaves open (decision of the test author,
# session 1, 2026-09-29):
#   * `money_interest_day` is the daily rate of the money market as a factor
#     (1 + max(r, 0)/100)^(1/252) - 1 on the day it is credited,
#     otherwise 0; in lead rows the cell stays empty.
#   * `trade_count` counts the signals `einstieg` and `ausstieg` cumulatively up
#     to and including the row; `start` does not count.
#   * `above_line` and `invested` are read via _as_bool (wahr, ja, true, 1).
#   * Lead rows carry only `date` and `index_rounded` in the output.
#   * SENTENCE_EXACTNESS_DE and SENTENCE_EXACTNESS_EN are the fixed wording of the spec
#     (in meaning there); the box adopts it verbatim. The Markdown of the
#     link to examples/leverage-model is free, a separate test checks it.

REPLACEMENT_SENTENCE_PERCENT = 2.5

SMA_SIGNAL = "sma-signal"
# Wave strategie-nachrechnen-it: links go to files under the blob URL of the
# public repository, never to folders and never to the old organisation.
BLOB = "https://github.com/Andre0512/letf-strategies/blob/main/"
URL_SMA_SIGNAL = f"{BLOB}examples/sma-signal/README.md"

# Wave strategie-nachrechnen-code: three H3 for pseudocode, parameters and
# data rules between "Lokal ausführen" and "Die Spalten".
RECOMPUTE_H3_DE = [
    "Was im Repository liegt",
    "Lokal ausführen",
    "Die Rechnung in Kurzform",
    "Die Parameter",
    "Datenregeln",
    "Die Spalten",
    "Warum zwei Pakete",
    "Warum erfundene Daten",
    "Was die Seite genauso rechnet",
]
RECOMPUTE_H3_EN = [
    "What the repository holds",
    "Run it locally",
    "The calculation in short",
    "The parameters",
    "Data rules",
    "The columns",
    "Why two packages",
    "Why invented data",
    "What the page computes the same way",
]

BOX_WORDS = (
    "Prognose",
    "erwartet",
    "optimal",
    "beste",
    "empfehlen",
    "solltest",
    "forecast",
    "expected",
    "best",
)

WORDS_NO_PROMISE = (
    "Offenheit",
    "Transparenz",
    "openness",
    "transparency",
    "KI",
    "Intelligenz",
    "intelligence",
    "künstlich",
    "artificial",
)

SENTENCE_EXACTNESS_DE = (
    "Mit denselben Produktkursen, denselben Signaltagen, denselben "
    "Geldmarktsätzen (ohne bekannten Satz 2,5 %) und denselben Umschlagkosten "
    "rechnet die Seite dieselbe Wertkurve; das Signal vergleicht die Seite am "
    "ungerundeten Rohstand des Index, den sie nicht zeigt; das "
    "Paket führt dieselbe Regel an seiner erfundenen Reihe vor. Vor der Auflage "
    "steht das Hebelmodell dahinter."
)

SENTENCE_EXACTNESS_EN = (
    "With the same product prices, the same signal days, the same money-market "
    "rates (without a known rate 2.5 %) and the same trading costs, the site "
    "computes the same value curve; the site compares the signal at the "
    "unrounded raw level of the index, which it does not show; the "
    "package demonstrates the same rule on its invented series. Before the "
    "launch, the leverage model stands behind it."
)

SENTENCE_TABLE_DE = "Alle Zahlen sind erfunden. Werte seit dem Start bei 100."
SENTENCE_TABLE_EN = "All numbers are invented. Values since the start at 100."

HEADERS_DE = ("Datum", "Index", "Linie", "Im Markt (ja/nein)", "Wert der Strategie")
HEADERS_EN = ("Date", "Index", "Line", "In the market (yes/no)", "Strategy value")

TABLE_SMA = (
    "date",
    "index_rounded",
    "line_rounded",
    "invested",
    "value_strategy",
)

PACKAGE_VALUES_SMA = ("window_trading_days", "buffer_percent", "trading_cost_percent")

EMPTY_OUTPUT = (
    "sma",
    "line",
    "line_rounded",
    "above_line",
    "line_state",
    "invested",
    "signal",
    "money_interest_day",
    "trading_cost",
    "trade_count",
    "value_strategy",
    "value_hold",
)

# Word list outside the :::layer boxes, state of main before the wave (counters).
WORDLIST_BASE = {
    "sma-trend.de.md": {"beste": 1},
    "sma-trend.en.md": {"best": 2, "expected": 1},
}

LAYER_BLOCK = re.compile(r"(?ms)^:::layer[^\n]*\n(.*?)^:::[ \t]*$")


def _section(text: str, name: str) -> str:
    hits = re.search(
        rf"(?ms)^##[ \t]+{re.escape(name)}[ \t]*$(.*?)(?=^##[ \t]|\Z)", text
    )
    return hits.group(1) if hits else ""


def _layer_blocks(text: str) -> list[str]:
    return [m.group(1) for m in LAYER_BLOCK.finditer(text)]


RECOMPUTE_SUBSECTION = re.compile(r"(?ms)^###[ \t]+([^\n]*?)[ \t]*\n(.*?)(?=^###[ \t]|\Z)")


DAY_BY_DAY = {"de": "Tag für Tag gerechnet", "en": "Day by day"}


def _recompute_open_block(text: str, title: str) -> tuple[str, str]:
    """(H3 title, body) of the H3 with this title in chapter recompute.

    Wave strategie-nachrechnen-it: the open text Zum Nachrechnen is gone; the
    chapter has six fixed H3, the fixed sentence and the table stand under the
    sixth, the formulas under the last H3 of math.
    """
    for match in RECOMPUTE_SUBSECTION.finditer(_section(text, "recompute")):
        if match.group(1).strip() == title:
            return title, match.group(2)
    return "", ""


def _day_by_day(text: str, language: str) -> str:
    """Body of the last H3 of math, if it is Tag für Tag gerechnet / Day by day."""
    matches = list(RECOMPUTE_SUBSECTION.finditer(_section(text, "math")))
    if matches and matches[-1].group(1).strip() == DAY_BY_DAY[language]:
        return matches[-1].group(2)
    return ""


def _same_computation(text: str, language: str) -> str:
    """Body of the last H3 of recompute (Was die Seite genauso rechnet)."""
    titles = RECOMPUTE_H3_DE if language == "de" else RECOMPUTE_H3_EN
    return _recompute_open_block(text, titles[-1])[1]


def _recompute_box(text: str) -> str:
    # Wave strategie-nachrechnen-it: word bans, names and the fixed sentence
    # apply to the whole chapter recompute.
    return _section(text, "recompute")


def _without_links(text: str) -> str:
    return re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)


def _link_targets(text: str) -> list[str]:
    return re.findall(r"\]\(([^)]+)\)", text)


def _first_row_with_value(input_rows: list[dict[str, str]]) -> int | None:
    for i, row in enumerate(input_rows):
        for column in ("product_price", "real_price"):
            if row.get(column, "") != "":
                return i
    return None


def _package_value(rows: list[dict[str, str]], column: str) -> str:
    for row in rows:
        if row.get(column, "") != "":
            return row[column]
    return ""


def _expected_daily_rate(rate_text: str) -> float:
    rate = REPLACEMENT_SENTENCE_PERCENT if rate_text == "" else max(float(rate_text), 0.0)
    return (1.0 + rate / 100.0) ** (1.0 / 252.0) - 1.0


def _interest(row: dict[str, str]) -> float:
    return float(row.get("money_interest_day") or 0.0)


def _costs(row: dict[str, str]) -> float:
    return float(row.get("trading_cost") or 0.0)


def _table_cells(row: str) -> list[str]:
    return [part.strip() for part in row.strip().strip("|").split("|")]


def _table(text: str) -> tuple[list[str], list[list[str]], int]:
    """First Markdown table as (headers, body rows, index of the header row)."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not line.strip().startswith("|") or i + 1 >= len(lines):
            continue
        separator = lines[i + 1].strip()
        if not (separator.startswith("|") and set(separator) <= set("|-: ")):
            continue
        body: list[list[str]] = []
        for k in lines[i + 2 :]:
            if not k.strip().startswith("|"):
                break
            body.append(_table_cells(k))
        return _table_cells(line), body, i
    return [], [], -1


class TestSmaSignalPackage(unittest.TestCase):
    """Acceptance 1: recompute reproduces output.csv, standard library, steps."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.path = EXAMPLES / SMA_SIGNAL
        if not cls.path.is_dir():
            raise AssertionError("examples/sma-signal is missing")

    def test_recompute_reproduces_output(self) -> None:
        run = subprocess.run(
            [
                sys.executable,
                str(self.path / "recompute.py"),
                str(self.path / "input.csv"),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(0, run.returncode, run.stderr)
        problems = _compare_outputs(
            SMA_SIGNAL,
            _read_csv((self.path / "output.csv").read_text(encoding="utf-8")),
            _read_csv(run.stdout),
        )
        self.assertEqual([], problems)

    def test_imports_standard_library_only(self) -> None:
        code = (self.path / "recompute.py").read_text(encoding="utf-8")
        for module in _imports(code):
            self.assertIn(module, ALLOWED_IMPORTS, f"recompute.py imports {module!r}")

    def test_steps_in_code_and_readme_match(self) -> None:
        code = (self.path / "recompute.py").read_text(encoding="utf-8")
        readme = (self.path / "README.md").read_text(encoding="utf-8")
        steps_code = _code_steps(code)
        self.assertTrue(steps_code, "recompute.py has no step comments")
        self.assertEqual(steps_code, _readme_steps(readme))


class TestSmaSignalEdgeCases(unittest.TestCase):
    """Acceptance 2: every minimum case from BAU-2 proven at its row."""

    @classmethod
    def setUpClass(cls) -> None:
        path = EXAMPLES / SMA_SIGNAL
        if not (path / "input.csv").is_file() or not (path / "output.csv").is_file():
            raise AssertionError(
                "examples/sma-signal/input.csv or output.csv is missing"
            )
        cls.input_rows = _read_csv((path / "input.csv").read_text(encoding="utf-8"))
        cls.output_rows = _read_csv((path / "output.csv").read_text(encoding="utf-8"))
        cls.buffer = float(_package_value(cls.input_rows, "buffer_percent") or "nan")

    def test_lead_rows_without_product_price(self) -> None:
        first = _first_row_with_value(self.input_rows)
        self.assertIsNotNone(first, "input.csv knows no row with a product price")
        self.assertGreater(first, 0, "the example has no lead rows")
        for i in range(first):
            self.assertEqual("", self.input_rows[i].get("product_price", ""))
            for column in EMPTY_OUTPUT:
                self.assertEqual(
                    "",
                    self.output_rows[i].get(column, ""),
                    f"lead row {self.output_rows[i].get('date')} carries {column}",
                )
            self.assertEqual(
                round(float(self.input_rows[i]["index"]), 2),
                float(self.output_rows[i]["index_rounded"]),
                f"index_rounded in lead row {self.input_rows[i]['date']}",
            )

    def test_first_day_without_interest_and_interest_bearing_warmup_days(self) -> None:
        first = _first_row_with_value(self.input_rows)
        self.assertIsNotNone(first, "input.csv knows no row with a product price")
        self.assertEqual(
            0.0,
            _interest(self.output_rows[first]),
            "the first day with a product price carries interest",
        )
        interest_bearing = [
            i
            for i, row in enumerate(self.output_rows)
            if row.get("line_state") == "aufwaermen" and _interest(row) > 0
        ]
        self.assertTrue(
            interest_bearing,
            "the example shows no interest-bearing warm-up days",
        )

    def test_start_decision_without_costs_and_without_trade(self) -> None:
        starts = [
            i
            for i, row in enumerate(self.output_rows)
            if row.get("signal") == "start"
        ]
        self.assertEqual(1, len(starts), "not exactly one start decision in the example")
        i = starts[0]
        self.assertEqual(
            0.0, _costs(self.output_rows[i]), "the start decision costs"
        )
        self.assertEqual(
            0,
            int(float(self.output_rows[i].get("trade_count") or 0)),
            "the start decision counts in trade_count",
        )
        self.assertGreaterEqual(
            float(self.input_rows[i]["index"]),
            float(self.output_rows[i]["sma"]) - 1e-9,
            "the start decision is not above the line",
        )
        self.assertTrue(
            _as_bool(self.output_rows[i].get("invested", "")),
            "the start decision does not put the money into the market",
        )
        self.assertEqual("drin", self.output_rows[i].get("line_state"))
        window = int(float(_package_value(self.input_rows, "window_trading_days")))
        self.assertGreaterEqual(
            i, window - 1, "at the start decision the line is not full"
        )
        first_with_line = min(
            j
            for j, row in enumerate(self.input_rows)
            if row.get("product_price", "") != "" and j >= window - 1
        )
        self.assertEqual(
            first_with_line,
            i,
            "the start decision is not the first day with a product price "
            "and a full line",
        )

    def test_exit_and_later_entry_are_counted(self) -> None:
        exits = [
            i
            for i, row in enumerate(self.output_rows)
            if row.get("signal") == "ausstieg"
        ]
        entries = [
            i
            for i, row in enumerate(self.output_rows)
            if row.get("signal") == "einstieg"
        ]
        self.assertTrue(exits, "the example shows no exit")
        self.assertTrue(entries, "the example shows no later entry")
        self.assertLess(exits[0], entries[0], "the entry does not come after the exit")
        for i in exits + entries:
            self.assertGreater(
                _costs(self.output_rows[i]),
                0.0,
                f"the trade at {self.input_rows[i]['date']} shows no trading costs",
            )
        running = 0
        for input_row, output_row in zip(self.input_rows, self.output_rows):
            if output_row.get("signal") in ("einstieg", "ausstieg"):
                running += 1
            self.assertEqual(
                running,
                int(float(output_row.get("trade_count") or 0)),
                f"trade_count at {input_row['date']} does not count "
                "the trades cumulatively",
            )

    def test_buffer_prevents_the_switch(self) -> None:
        b = self.buffer / 100.0
        hits: list[int] = []
        for i in range(1, len(self.output_rows)):
            row, previous = self.output_rows[i], self.output_rows[i - 1]
            if row.get("sma") == "" or row.get("line") == "":
                continue
            if float(self.input_rows[i]["index"]) < float(row["sma"]) - 1e-9:
                continue
            if _as_bool(row.get("above_line", "")):
                continue
            if abs(float(row["line"]) - float(row["sma"]) * (1.0 + b)) > 1e-9 * max(
                abs(float(row["sma"])), 1.0
            ):
                continue
            hits.append(i)
            self.assertEqual("draussen", row.get("line_state"))
            self.assertEqual(
                "",
                row.get("signal", f"Signal am Puffertag {row.get('date')}"),
            )
            self.assertEqual(
                previous.get("line_state"),
                row.get("line_state"),
                f"switch on the buffer day {row.get('date')}",
            )
            self.assertEqual(
                _as_bool(previous.get("invested", "")),
                _as_bool(row.get("invested", "")),
                f"change of the money state on the buffer day {row.get('date')}",
            )
        self.assertTrue(
            hits,
            "the example shows no day on which the buffer prevents the switch",
        )

    def test_tie_in_the_rounding(self) -> None:
        # Wave nachrechnen-sma-gleichstand: rounded at a tie, unrounded
        # below, thus not above the line.
        index_per_day = {
            row["date"]: row.get("index", "") for row in self.input_rows
        }
        hits: list[str] = []
        for row in self.output_rows:
            if row.get("line", "") == "" or row.get("line_rounded", "") == "":
                continue
            raw = index_per_day.get(row["date"], "")
            if raw == "":
                continue
            if float(row["index_rounded"]) != float(row["line_rounded"]):
                continue
            if not float(raw) < float(row["line"]):
                continue
            self.assertFalse(
                _as_bool(row.get("above_line", "")),
                f"{row['date']}: rounded at a tie, unrounded below, "
                "above_line is nevertheless yes",
            )
            hits.append(row["date"])
        self.assertTrue(
            hits,
            "the example shows no day on which index and line are rounded equal "
            "and the index lies below unrounded",
        )

    def test_negative_rate_yields_zero_money_interest(self) -> None:
        rows = [
            i
            for i, row in enumerate(self.input_rows)
            if row.get("product_price", "") != ""
            and _is_number(row.get("money_rate_percent_year", ""))
            and float(row["money_rate_percent_year"]) < 0
        ]
        self.assertTrue(rows, "the example shows no negative rate")
        for i in rows:
            self.assertEqual(
                0.0,
                _interest(self.output_rows[i]),
                f"the negative rate at {self.input_rows[i]['date']} yields "
                "money_interest_day not equal to 0",
            )

    def test_rate_change(self) -> None:
        rates = {
            row["money_rate_percent_year"]
            for row in self.input_rows
            if row.get("money_rate_percent_year", "") != ""
        }
        self.assertGreaterEqual(len(rates), 2, "the example shows no rate change")

    def test_day_without_rate_uses_the_substitute_value(self) -> None:
        candidates = [
            i
            for i, (input_row, output_row) in enumerate(
                zip(self.input_rows, self.output_rows)
            )
            if input_row.get("product_price", "") != ""
            and input_row.get("money_rate_percent_year", "") == ""
            and _interest(output_row) > 0
        ]
        self.assertTrue(candidates, "no day without a known rate carries interest")
        expected = _expected_daily_rate("")
        for i in candidates:
            self.assertAlmostEqual(
                expected,
                _interest(self.output_rows[i]),
                places=12,
                msg=f"the day without a rate at {self.input_rows[i]['date']} "
                "does not compute with 2.5 %",
            )

    def test_money_interest_day_follows_the_daily_rate(self) -> None:
        for input_row, output_row in zip(self.input_rows, self.output_rows):
            if input_row.get("product_price", "") == "" or _interest(output_row) <= 0:
                continue
            self.assertAlmostEqual(
                _expected_daily_rate(input_row.get("money_rate_percent_year", "")),
                _interest(output_row),
                places=12,
                msg=f"money_interest_day at {input_row['date']} "
                "does not follow the daily rate",
            )


class TestSmaSignalValues(unittest.TestCase):
    """Acceptance 3: normalisation at 100, holding, daily rows only."""

    @classmethod
    def setUpClass(cls) -> None:
        path = EXAMPLES / SMA_SIGNAL
        if not (path / "input.csv").is_file() or not (path / "output.csv").is_file():
            raise AssertionError("examples/sma-signal/input.csv or output.csv is missing")
        cls.input_rows = _read_csv((path / "input.csv").read_text(encoding="utf-8"))
        cls.output_rows = _read_csv((path / "output.csv").read_text(encoding="utf-8"))

    def test_first_row_with_value_at_100_and_index_starts_at_100(self) -> None:
        first = _first_row_with_value(self.input_rows)
        self.assertIsNotNone(first, "input.csv knows no row with a value")
        self.assertEqual(
            100.0,
            float(self.input_rows[first]["product_price"]),
            "product_price in the first row with a value is not 100",
        )
        for column in ("value_strategy", "value_hold"):
            self.assertEqual(
                100.0,
                float(self.output_rows[first][column]),
                f"{column} in the first row with a value is not 100",
            )
        self.assertEqual(
            100.0, float(self.input_rows[0]["index"]), "index does not start at 100"
        )

    def test_value_hold_is_100_times_the_price_ratio(self) -> None:
        first = _first_row_with_value(self.input_rows)
        self.assertIsNotNone(first, "input.csv knows no row with a value")
        first_price = float(self.input_rows[first]["product_price"])
        for input_row, output_row in zip(self.input_rows, self.output_rows):
            if input_row.get("product_price", "") == "":
                continue
            self.assertAlmostEqual(
                100.0 * float(input_row["product_price"]) / first_price,
                float(output_row["value_hold"]),
                places=9,
                msg=f"value_hold at {input_row['date']} is not 100 times the "
                "price ratio",
            )

    def test_daily_rows_only(self) -> None:
        self.assertEqual(
            [input_row["date"] for input_row in self.input_rows],
            [output_row.get("date", "") for output_row in self.output_rows],
            "output.csv does not have exactly the daily rows of the input",
        )
        for input_row, output_row in zip(self.input_rows, self.output_rows):
            self.assertRegex(
                output_row.get("date", ""),
                r"^\d{4}-\d{2}-\d{2}$",
                f"the row for {input_row['date']} carries no daily date",
            )


class TestSmaSignalBox(unittest.TestCase):
    """Acceptance 4 and 5: the 'For recomputation' box (DE and EN) per BAU-4."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.texts: dict[str, str] = {}
        cls.boxes: dict[str, str] = {}
        cls.same: dict[str, str] = {}
        cls.days: dict[str, str] = {}
        for language in ("de", "en"):
            path = ROOT / "content" / "strategies" / f"sma-trend.{language}.md"
            if not path.is_file():
                raise AssertionError(f"{path} is missing")
            text = path.read_text(encoding="utf-8")
            cls.texts[language] = text
            # Wave strategie-nachrechnen-it: "boxes" is the whole chapter
            # recompute, "same" its sixth H3, "days" the last H3 of math.
            cls.boxes[language] = _recompute_box(text)
            cls.same[language] = _same_computation(text, language)
            cls.days[language] = _day_by_day(text, language)

    def _pairs(self) -> list[tuple[str, str]]:
        return list(self.boxes.items())

    def test_box_in_chapter_recompute_not_in_math(self) -> None:
        """Wave strategie-nachrechnen-it: no formula in recompute, the formulas
        stand under the last H3 of math without lead sentence and package link."""
        for language, text in self.texts.items():
            with self.subTest(language=language):
                chapter = self.boxes[language]
                self.assertTrue(chapter, f"no chapter recompute ({language})")
                for token in ("$$", "\\frac", "\\begin"):
                    self.assertNotIn(
                        token, chapter, f"{token!r} still stands in recompute ({language})"
                    )
                math = _section(text, "math")
                self.assertTrue(math, f"no section math ({language})")
                self.assertNotIn(
                    "Zum Nachrechnen", math, f"math carries 'Zum Nachrechnen' ({language})"
                )
                self.assertFalse(
                    [t for t in _link_targets(math) if "examples/" in t],
                    f"math links into examples/ ({language})",
                )
                days = self.days[language]
                self.assertTrue(
                    days.strip(),
                    f"the H3 {DAY_BY_DAY[language]!r} is not the last H3 of math "
                    f"({language})",
                )
                self.assertFalse(
                    days.strip().startswith("**"),
                    f"the formulas in math still start with a bold lead ({language})",
                )

    def test_starts_with_lead_sentence_and_ends_with_link(self) -> None:
        """Flipped: no bold lead any more; the chapter links the package README
        as a file and carries no promise words."""
        for language, chapter in self._pairs():
            with self.subTest(language=language):
                self.assertNotIn(
                    "**Zum Nachrechnen.**",
                    chapter,
                    f"the bold lead still stands in recompute ({language})",
                )
                self.assertIn(
                    URL_SMA_SIGNAL,
                    _link_targets(chapter),
                    f"the chapter does not link the README of examples/sma-signal "
                    f"({language})",
                )
                rest = _without_links(chapter)
                for word in WORDS_NO_PROMISE:
                    self.assertIsNone(
                        _word_pattern(word).search(rest),
                        f"the chapter carries a sentence about {word!r} ({language})",
                    )

    def test_accuracy_sentence_and_link_to_the_leverage_model(self) -> None:
        """The fixed sentence stands verbatim in the sixth H3, without a link in
        it; the chapter links the package leverage-model."""
        for language, sentence in (
            ("de", SENTENCE_EXACTNESS_DE),
            ("en", SENTENCE_EXACTNESS_EN),
        ):
            with self.subTest(language=language):
                self.assertIn(
                    _flatten(sentence),
                    _flatten(self.same[language]),
                    f"the fixed accuracy sentence is missing verbatim in the sixth "
                    f"H3 ({language})",
                )
                self.assertTrue(
                    any(
                        "examples/leverage-model" in target
                        for target in _link_targets(self.boxes[language])
                    ),
                    f"the chapter does not link to examples/leverage-model ({language})",
                )

    def test_exact_and_same_numbers_only_in_the_fixed_sentence(self) -> None:
        readme = ""
        path = EXAMPLES / SMA_SIGNAL / "README.md"
        if path.is_file():
            readme = path.read_text(encoding="utf-8")
        to_check = {
            "kasten-de": _flatten(_without_links(self.boxes["de"])).replace(
                _flatten(SENTENCE_EXACTNESS_DE), ""
            ),
            "kasten-en": _flatten(_without_links(self.boxes["en"])).replace(
                _flatten(SENTENCE_EXACTNESS_EN), ""
            ),
            "readme": _flatten(readme).replace(_flatten(SENTENCE_EXACTNESS_DE), "").replace(
                _flatten(SENTENCE_EXACTNESS_EN), ""
            ),
        }
        for name, rest in to_check.items():
            with self.subTest(text=name):
                for word in ("exakt", "exact", "dieselben zahlen", "the same numbers"):
                    self.assertIsNone(
                        re.search(word, rest, re.IGNORECASE),
                        f"{word!r} stands outside the fixed sentence in {name}",
                    )

    def test_box_against_names_isins_fields_and_words(self) -> None:
        for language, box in self._pairs():
            with self.subTest(language=language):
                self.assertTrue(box.strip(), f"the box is missing ({language})")
                # Spec acceptance, Fassung 3: the names of the money market
                # rates ESTR, SOFR and SONIA are allowed in exactly one place,
                # the interest source line of the constants block (BAU-4).
                rate_names = ("ESTR", "SOFR", "SONIA")
                rate_lines = [
                    line
                    for line in box.splitlines()
                    if all(_word_pattern(name).search(line) for name in rate_names)
                ]
                self.assertEqual(
                    1,
                    len(rate_lines),
                    f"expected exactly one interest source line with {rate_names} ({language})",
                )
                self.assertLessEqual(
                    set(_forbidden_hits(rate_lines[0])),
                    set(rate_names),
                    f"the interest source line names other forbidden things ({language})",
                )
                rest = "\n".join(
                    line for line in box.splitlines() if line not in rate_lines
                )
                self.assertEqual(
                    [],
                    _forbidden_hits(rest),
                    f"the box names forbidden things ({language})",
                )
                for word in BOX_WORDS:
                    # Own word boundary \w: umlauts count as part of the word,
                    # not as a boundary, otherwise a banned word would hit the
                    # required confirmation day (BAU-4).
                    self.assertIsNone(
                        re.compile(
                            r"(?<!\w)" + re.escape(word) + r"(?!\w)", re.IGNORECASE
                        ).search(box),
                        f"the box contains the word {word!r} ({language})",
                    )

    def test_scene_words_once_each_in_parentheses(self) -> None:
        # Wave strategie-nachrechnen-it: applies to "Tag für Tag gerechnet" in math.
        for language, box in self.days.items():
            with self.subTest(language=language):
                self.assertTrue(
                    box.strip(), f"no H3 {DAY_BY_DAY[language]!r} in math ({language})"
                )
                self.assertEqual(
                    1,
                    box.count("(Close)"),
                    f"Close does not appear exactly once in parentheses "
                    f"({language})",
                )
                self.assertEqual(
                    1,
                    box.count("(Cross)"),
                    f"Cross does not appear exactly once in parentheses "
                    f"({language})",
                )
                if language == "de":
                    self.assertIn("Schlusskurs (Close)", box)
                    self.assertIn("Kreuzen (Cross)", box)

    def test_at_most_four_katex_without_sma_formula(self) -> None:
        for language, box in self.days.items():
            with self.subTest(language=language):
                self.assertTrue(
                    box.strip(), f"no H3 {DAY_BY_DAY[language]!r} in math ({language})"
                )
                blocks = re.findall(r"\$\$(.+?)\$\$", box, re.DOTALL)
                self.assertLessEqual(
                    len(blocks),
                    4,
                    f"the box shows more than four KaTeX blocks ({language})",
                )
                self.assertNotIn(
                    "\\sum", box, f"the SMA sum is repeated ({language})"
                )
                self.assertNotIn(
                    "\\frac{1}{n}",
                    box,
                    f"the SMA formula is repeated ({language})",
                )

    def test_sentence_about_what_is_computed(self) -> None:
        for language, words in (
            ("de", ("Bestätigungstag", "Puffer", "allgemeine Form")),
            ("en", ("confirmation", "buffer", "general form")),
        ):
            with self.subTest(language=language):
                box = self.days[language]
                self.assertTrue(
                    box.strip(), f"no H3 {DAY_BY_DAY[language]!r} in math ({language})"
                )
                self.assertTrue(
                    "≥" in box or "\\ge" in box,
                    f"the comparison ≥ is missing ({language})",
                )
                for word in words:
                    self.assertIn(
                        word.lower(),
                        box.lower(),
                        f"{word!r} is missing in the sentence about what is "
                        f"computed ({language})",
                    )

    def test_table_note_and_values_against_output(self) -> None:
        path = EXAMPLES / SMA_SIGNAL / "output.csv"
        self.assertTrue(path.is_file(), "examples/sma-signal/output.csv is missing")
        output_rows = _read_csv(path.read_text(encoding="utf-8"))
        for language, headers, note in (
            ("de", HEADERS_DE, SENTENCE_TABLE_DE),
            ("en", HEADERS_EN, SENTENCE_TABLE_EN),
        ):
            with self.subTest(language=language):
                # Wave strategie-nachrechnen-it: the table stands under the sixth H3.
                box = self.same[language]
                self.assertTrue(box.strip(), f"the sixth H3 is missing ({language})")
                header, body, position = _table(box)
                self.assertEqual(
                    list(headers), header, f"the table headers differ ({language})"
                )
                self.assertEqual(
                    8,
                    len(body),
                    f"the table does not show eight rows ({language})",
                )
                lines = box.splitlines()
                j = position - 1
                while j >= 0 and not lines[j].strip():
                    j -= 1
                self.assertGreaterEqual(
                    j, 0, f"no sentence above the table ({language})"
                )
                self.assertEqual(
                    note,
                    lines[j].strip(),
                    f"the note sentence above the table is missing ({language})",
                )
                dates = [body_row[0] for body_row in body]
                positions = [
                    i
                    for i, output_row in enumerate(output_rows)
                    if output_row.get("date") in dates
                ]
                self.assertEqual(
                    8,
                    len(positions),
                    f"the dates of the table are not in the output ({language})",
                )
                self.assertEqual(
                    list(range(positions[0], positions[0] + 8)),
                    positions,
                    f"the eight rows are not consecutive ({language})",
                )
                for table_row, i in zip(body, positions):
                    output_row = output_rows[i]
                    self.assertEqual(
                        output_row["date"], table_row[0], f"date ({language})"
                    )
                    for column, cell in zip(TABLE_SMA[1:], table_row[1:]):
                        if column == "invested":
                            self.assertEqual(
                                _as_bool(output_row.get("invested", "")),
                                _as_bool(cell),
                                f"In the market on {output_row['date']} "
                                f"({language})",
                            )
                            continue
                        self.assertLessEqual(
                            abs(float(output_row[column]) - float(cell)),
                            0.005 + 1e-9,
                            f"{column} on {output_row['date']} not as displayed "
                            f"({language})",
                        )
                self.assertEqual(
                    "ausstieg",
                    output_rows[positions[2]].get("signal", ""),
                    f"the third table row is not an exit ({language})",
                )
                self.assertGreater(
                    _costs(output_rows[positions[2]]),
                    0.0,
                    f"the exit in the table shows no costs ({language})",
                )
                for i in positions[:2]:
                    self.assertTrue(
                        _as_bool(output_rows[i].get("invested", "")),
                        f"the days before the exit are not in the market "
                        f"({language})",
                    )
                for i in positions[3:]:
                    self.assertFalse(
                        _as_bool(output_rows[i].get("invested", "")),
                        f"the days after the exit are in the market ({language})",
                    )
                    self.assertGreater(
                        _interest(output_rows[i]),
                        0.0,
                        f"the days after the exit carry no interest ({language})",
                    )

    def test_no_dashes(self) -> None:
        for language, box in self._pairs():
            with self.subTest(language=language):
                self.assertTrue(box.strip(), f"the box is missing ({language})")
                for character in ("\u2014", "\u2013"):
                    self.assertNotIn(
                        character,
                        box + self.days[language],
                        f"dash in recompute or in {DAY_BY_DAY[language]!r} ({language})",
                    )
        path = EXAMPLES / SMA_SIGNAL / "README.md"
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            for character in ("\u2014", "\u2013"):
                self.assertNotIn(character, text, "dash in the package README")

    def test_no_new_word_hits_outside_the_boxes(self) -> None:
        for language, text in self.texts.items():
            with self.subTest(language=language):
                outside = LAYER_BLOCK.sub("", text)
                baseline = WORDLIST_BASE[f"sma-trend.{language}.md"]
                for word in BOX_WORDS:
                    # Own word boundary \w: umlauts count as part of the word,
                    # not as a boundary, otherwise a banned word would hit the
                    # required confirmation day (BAU-4).
                    count = len(
                        re.compile(
                            r"(?<!\w)" + re.escape(word) + r"(?!\w)", re.IGNORECASE
                        ).findall(outside)
                    )
                    self.assertLessEqual(
                        count,
                        baseline.get(word, 0),
                        f"new hits of the word list outside the boxes: "
                        f"{word!r} ({language})",
                    )

    def test_check_frontmatter_green(self) -> None:
        run = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_frontmatter.py")],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(0, run.returncode, run.stdout + run.stderr)


class TestSmaSignalPresetValues(unittest.TestCase):
    """Acceptance 4 (BAU-5): package values on the grid, equal to no preset."""

    def _package_values(self) -> dict[str, float]:
        path = EXAMPLES / SMA_SIGNAL / "input.csv"
        self.assertTrue(path.is_file(), "examples/sma-signal/input.csv is missing")
        input_rows = _read_csv(path.read_text(encoding="utf-8"))
        values: dict[str, float] = {}
        for column in PACKAGE_VALUES_SMA:
            raw = _package_value(input_rows, column)
            self.assertTrue(raw != "", f"the input does not name {column}")
            values[column] = float(raw)
        return values

    def _preset_values(self) -> tuple[set[float], set[float]]:
        pattern = re.compile(r"__([0-9]+)__B([0-9]+(?:[.,][0-9]+)?)__")
        windows: set[float] = set()
        buffers: set[float] = set()
        for path in (
            ROOT / "content" / "strategies" / "sma-trend.de.md",
            ROOT / "registry" / "strategy_preset_slugs.json",
        ):
            text = path.read_text(encoding="utf-8")
            for window_text, buffer_text in pattern.findall(text):
                windows.add(float(window_text))
                buffers.add(float(buffer_text.replace(",", ".")))
        self.assertTrue(
            windows, "no preset windows in frontmatter or registry"
        )
        self.assertTrue(
            buffers, "no preset buffers in frontmatter or registry"
        )
        return windows, buffers

    def test_values_equal_to_no_preset(self) -> None:
        values = self._package_values()
        windows, buffers = self._preset_values()
        self.assertNotIn(
            values["window_trading_days"], windows, "the window is as in the preset"
        )
        self.assertNotIn(
            values["buffer_percent"], buffers, "the buffer is as in the preset"
        )
        all_presets = windows | buffers
        for name, value in values.items():
            self.assertNotIn(
                value, all_presets, f"{name} {value} occurs like this in the presets"
            )

    def test_values_on_the_grid(self) -> None:
        values = self._package_values()
        window = values["window_trading_days"]
        buffer = values["buffer_percent"]
        costs = values["trading_cost_percent"]
        self.assertGreater(window, 0, "the window is not positive")
        self.assertGreaterEqual(window, 50, "the window is shorter than 50 trading days")
        self.assertLessEqual(window, 500, "the window is longer than 500 trading days")
        self.assertAlmostEqual(
            window / 5,
            round(window / 5),
            places=9,
            msg="the window is not on the 5 grid",
        )
        self.assertGreater(buffer, 0.0, "the buffer is not greater than 0")
        self.assertAlmostEqual(
            buffer / 0.5,
            round(buffer / 0.5),
            places=9,
            msg="the buffer is not on the 0.5 grid",
        )
        self.assertAlmostEqual(
            costs / 0.05,
            round(costs / 0.05),
            places=9,
            msg="the costs are not on the 0.05 grid",
        )


# Wave nachrechnen-material: the box and the package compare index and line
# unrounded. The eight table rows of the boxes are fixed here and are checked
# against output.csv.

TABLE_BOX_SMA = {
    "de": (
        "| Datum | Index | Linie | Im Markt (ja/nein) | Wert der Strategie |",
        "|---|---|---|---|---|",
        "| 1925-11-04 | 113.43 | 111.91 | ja | 73.88 |",
        "| 1925-11-05 | 113.56 | 111.91 | ja | 74.05 |",
        "| 1925-11-06 | 111.34 | 111.90 | nein | 74.11 |",
        "| 1925-11-09 | 113.80 | 115.30 | nein | 74.12 |",
        "| 1925-11-10 | 113.89 | 115.30 | nein | 74.13 |",
        "| 1925-11-11 | 113.94 | 115.30 | nein | 74.14 |",
        "| 1925-11-12 | 113.95 | 115.30 | nein | 74.15 |",
        "| 1925-11-13 | 113.91 | 115.30 | nein | 74.16 |",
    ),
    "en": (
        "| Date | Index | Line | In the market (yes/no) | Strategy value |",
        "|---|---|---|---|---|",
        "| 1925-11-04 | 113.43 | 111.91 | yes | 73.88 |",
        "| 1925-11-05 | 113.56 | 111.91 | yes | 74.05 |",
        "| 1925-11-06 | 111.34 | 111.90 | no | 74.11 |",
        "| 1925-11-09 | 113.80 | 115.30 | no | 74.12 |",
        "| 1925-11-10 | 113.89 | 115.30 | no | 74.13 |",
        "| 1925-11-11 | 113.94 | 115.30 | no | 74.14 |",
        "| 1925-11-12 | 113.95 | 115.30 | no | 74.15 |",
        "| 1925-11-13 | 113.91 | 115.30 | no | 74.16 |",
    ),
}

BOX_ROUNDED_FORBIDDEN = {
    "de": ("auf zwei Stellen gerundet", r"\operatorname{round}", "Gleichstand in der Rundung"),
    "en": ("rounded to two places", r"\operatorname{round}", "tie after rounding"),
}

FORMULA_UNROUNDED = r"P(t) \ge L(t)"

SENTENCE_DISPLAY_BOX_DE = "Linie und Geld folgen demselben Vergleich; gerundet wird nur für die Anzeige."

README_ROUNDED_FORBIDDEN = (
    "gerundeten Vergleich",
    "vergleicht gerundet",
    "gerundet mindestens",
    "mindestens linie_gerundet",
    "auf zwei Stellen gerundet",
    "rundet halbe Stellen",
    "an Gleichstandstagen",
    "einen Tag vom Geldstand abweichen",
    "rounded comparison",
    "compares rounded",
    "rounded at least",
    "at least line_rounded",
    "rounded to two places",
    "rounds half places",
    "on tie days",
    "differ from the money level by one day",
)

SENTENCE_BRIEF = (
    "If the index is unrounded just below the line but equal when rounded, "
    "it counts as below."
)
SENTENCE_ONLY_DISPLAY = "rounding is only for display"
SENTENCE_ONE_COMPARISON = "One comparison decides line state and money."
SENTENCE_START_UNROUNDED = "the index is at least on the line (unrounded)"

ROUNDED_WORD = re.compile(r"(?<![\w])(?:gerundet|rounded|round)(?![\w])")


def _flatten(text: str) -> str:
    return " ".join(text.split())


def _table_row(text: str, column: str) -> str:
    for row in text.splitlines():
        cells = _table_cells(row) if row.strip().startswith("|") else []
        if cells and cells[0] == column:
            return row
    return ""


class TestSmaSignalUnrounded(unittest.TestCase):
    """Wave nachrechnen-sma-gleichstand: one unrounded comparison."""

    @classmethod
    def setUpClass(cls) -> None:
        path = EXAMPLES / SMA_SIGNAL
        cls.code = (path / "recompute.py").read_text(encoding="utf-8")
        cls.output_text = (path / "output.csv").read_text(encoding="utf-8")
        cls.input_rows = _read_csv((path / "input.csv").read_text(encoding="utf-8"))
        cls.output_rows = _read_csv(cls.output_text)
        cls.readme = (path / "README.md").read_text(encoding="utf-8")
        cls.boxes: dict[str, str] = {}
        cls.same: dict[str, str] = {}
        cls.days: dict[str, str] = {}
        for language in ("de", "en"):
            text = (
                ROOT / "content" / "strategies" / f"sma-trend.{language}.md"
            ).read_text(encoding="utf-8")
            # Wave strategie-nachrechnen-it: table under the sixth H3 of
            # recompute, formulas under the last H3 of math.
            cls.boxes[language] = _recompute_box(text)
            cls.same[language] = _same_computation(text, language)
            cls.days[language] = _day_by_day(text, language)

    # Acceptance 1: no round( in the comparison

    def test_recompute_compares_without_round(self) -> None:
        comparison = re.compile(r">=|<=|(?<![<>=-])[<>](?![=])")
        for nr, line in enumerate(self.code.splitlines(), 1):
            code = line.split("#", 1)[0]
            if "round(" in code and comparison.search(code):
                self.fail(f"recompute.py line {nr} compares rounded: {line.strip()}")

    # Acceptance 2: tie day and alignment

    def test_alignment_of_comparison_line_state_and_money(self) -> None:
        input_by_date = {row["date"]: row for row in self.input_rows}
        checked = 0
        for output_row in self.output_rows:
            input_row = input_by_date.get(output_row["date"])
            self.assertIsNotNone(
                input_row, f"{output_row['date']} is missing in input.csv"
            )
            if (
                input_row.get("product_price", "") == ""
                or output_row.get("line", "") == ""
            ):
                continue
            above = float(input_row["index"]) >= float(output_row["line"])
            with self.subTest(date=output_row["date"]):
                self.assertEqual(above, _as_bool(output_row["above_line"]), "above_line")
                self.assertEqual(above, _as_bool(output_row["invested"]), "invested")
                self.assertEqual(
                    above, output_row["line_state"] == "drin", "line_state"
                )
            checked += 1
        self.assertGreater(checked, 0, "no day with a product price and a full line")

    # Acceptance 3: exit on a tie day of the rounding

    def test_exit_on_the_tie_day(self) -> None:
        index_by_date = {row["date"]: row.get("index", "") for row in self.input_rows}
        hits: list[str] = []
        ties: list[str] = []
        running = 0
        for row in self.output_rows:
            if row.get("signal", "") in ("einstieg", "ausstieg"):
                running += 1
            if row.get("line", "") == "" or row.get("line_rounded", "") == "":
                continue
            if float(row.get("index_rounded") or "nan") != float(row["line_rounded"]):
                continue
            raw = index_by_date.get(row["date"], "")
            if raw == "" or not float(raw) < float(row["line"]):
                continue
            self.assertFalse(
                _as_bool(row.get("above_line", "")),
                f"{row['date']}: unrounded below, above_line is ja",
            )
            self.assertFalse(
                _as_bool(row.get("invested", "")),
                f"{row['date']}: unrounded below, the money is in the market",
            )
            ties.append(row["date"])
            if row.get("signal", "") != "ausstieg":
                continue
            self.assertEqual(
                running,
                int(float(row.get("trade_count") or 0)),
                f"trade_count on {row['date']} does not count cumulatively",
            )
            hits.append(row["date"])
        self.assertTrue(
            ties,
            "the example shows no day on which index and line are equal when rounded",
        )
        self.assertTrue(
            hits,
            "the example shows no exit on a day on which index and line are "
            "equal when rounded",
        )

    def test_table_in_the_box_unchanged(self) -> None:
        for language, expected in TABLE_BOX_SMA.items():
            with self.subTest(language=language):
                actual = [
                    row
                    for row in self.same[language].splitlines()
                    if row.strip().startswith("|")
                ]
                self.assertEqual(list(expected), actual)

    # Acceptance 4: box de/en

    def test_box_without_rounded_comparison(self) -> None:
        for language, words in BOX_ROUNDED_FORBIDDEN.items():
            flat = _flatten(self.boxes[language] + "\n" + self.days[language])
            for word in words:
                with self.subTest(language=language, word=word):
                    self.assertNotIn(word, flat)

    def test_box_carries_the_unrounded_formula(self) -> None:
        for language, box in self.days.items():
            with self.subTest(language=language):
                self.assertIn(FORMULA_UNROUNDED, _flatten(box))

    def test_de_box_rounds_only_for_display(self) -> None:
        self.assertIn(SENTENCE_DISPLAY_BOX_DE, _flatten(self.days["de"]))

    # Acceptance 5: package README

    def test_readme_without_rounded_comparison(self) -> None:
        flat = _flatten(self.readme)
        for word in README_ROUNDED_FORBIDDEN:
            with self.subTest(word=word):
                self.assertNotIn(word, flat)

    def test_readme_rounded_only_at_the_allowed_places(self) -> None:
        for paragraph in re.split(r"\n\s*\n", self.readme):
            if paragraph.lstrip().startswith("|"):
                for row in paragraph.splitlines():
                    if ROUNDED_WORD.search(row):
                        self.assertIn(
                            "for display only", row, f"table row: {row}"
                        )
                continue
            flat = _flatten(paragraph).replace(SENTENCE_BRIEF, "")
            if ROUNDED_WORD.search(flat):
                self.assertTrue(
                    SENTENCE_ONLY_DISPLAY in flat or "for display only" in flat,
                    f"paragraph: {flat[:120]}",
                )

    def test_readme_column_table(self) -> None:
        above = _table_row(self.readme, "above_line")
        self.assertIn("unrounded", above)
        self.assertIn("at least", above)
        for column in ("index_rounded", "line_rounded"):
            with self.subTest(column=column):
                self.assertIn(
                    "for display only", _table_row(self.readme, column)
                )

    def test_readme_one_comparison_close_and_start(self) -> None:
        flat = _flatten(self.readme)
        self.assertNotIn("Zwei Zustände laufen nebeneinander", flat)
        self.assertNotIn("Two states run side by side", flat)
        for sentence in (
            SENTENCE_ONE_COMPARISON,
            SENTENCE_BRIEF,
            SENTENCE_ONLY_DISPLAY,
            SENTENCE_START_UNROUNDED,
        ):
            with self.subTest(sentence=sentence):
                self.assertIn(sentence, flat)

    def test_readme_steps_3_and_4_unrounded(self) -> None:
        steps = dict(
            (int(m.group(1)), _flatten(m.group(0)))
            for m in re.finditer(r"(?m)^(\d+)\.\s+.*(?:\n[ \t]+\S.*)*$", self.readme)
        )
        for nr in (3, 4):
            with self.subTest(step=nr):
                self.assertIn("unrounded", steps.get(nr, ""))
                self.assertIsNone(ROUNDED_WORD.search(steps.get(nr, "")))

    def test_readme_carries_the_exactness_sentence(self) -> None:
        self.assertIn(_flatten(SENTENCE_EXACTNESS_EN), _flatten(self.readme))

    def test_llms_and_examples_readme_without_rounded_comparison(self) -> None:
        for path in (LLMS, EXAMPLES / "README.md"):
            flat = _flatten(path.read_text(encoding="utf-8"))
            for word in README_ROUNDED_FORBIDDEN + ("auf zwei Stellen",):
                with self.subTest(file=path.name, word=word):
                    self.assertNotIn(word, flat)


class TestEntryPackage(unittest.TestCase):
    """BAU-5: examples/README.md and llms.txt name the package with a purpose."""

    def test_readme_and_llms_name_the_package(self) -> None:
        for path in (EXAMPLES / "README.md", LLMS):
            with self.subTest(file=str(path.relative_to(ROOT))):
                text = path.read_text(encoding="utf-8")
                self.assertIn(
                    SMA_SIGNAL, text, f"{path.name} does not name the package"
                )
                self.assertTrue(
                    f"{SMA_SIGNAL}/" in text or f"examples/{SMA_SIGNAL}" in text,
                    f"{path.name} does not name the package path",
                )
                sentences = [
                    s for s in re.split(r"(?<=[.!?])\s+|\n", text) if SMA_SIGNAL in s
                ]
                self.assertTrue(
                    any(len(s.split()) >= 5 for s in sentences),
                    f"{path.name} names the package without a purpose sentence",
                )


# ---------------------------------------------------------------------------
# Wave nachrechnen-hfea: package examples/rebalancing and the box
# "Zum Nachrechnen" in the derivation of hfea
# ---------------------------------------------------------------------------
#
# Contract for what BAU-1 leaves open (test author decision,
# 2026-09-30):
#   * input.csv and output.csv carry the same columns in every row
#     RUN_INPUT with the same values; output.csv appends RUN_OUTPUT.
#   * `deadline` is the deadline that applies after trading that day: in the
#     first row of a run, anchor day plus period; on the rebalancing day,
#     that day plus period; otherwise the deadline of the previous row.
#   * `rebalanced` and `band_breached` read through _as_bool; without a band,
#     `band_breached` is not true.
#   * `quote_before_percent` is the stock share from the unit counts of the
#     previous row at the day's prices, in the first row 100 · weight.
#   * A share running "far" away from the target means at least 5 percentage
#     points.
#   * The date cell of the box table carries the ISO date; the mark of the
#     rebalancing row is everything else in the cell.
#
# Wave hfea-nachrechnen-kalender (test author, 2026-10-07): the rule
# `termin` computes with calendar dates (the 1st of every month m with
# (m - 1) % period == 0); `deadline` there is the next date, in the
# anchor row strictly after the anchor day, after a rebalancing strictly
# after the executed date (the deadline of the previous row).
# `termin_und_band` keeps the deadline chain from the actual rebalancing day
# plus period with capping. Paragraphs are separated by blank lines; a
# paragraph belongs to term and band if it names `termin_und_band`,
# "Termin und Band" or "date and band".

REBALANCING = "rebalancing"
URL_REBALANCING = f"{BLOB}examples/rebalancing/README.md"
RULES = ("termin", "termin_und_band")

RUN_INPUT = (
    "run",
    "rule",
    "stock_weight_percent",
    "period_months",
    "band_percentage_points",
    "date",
    "stock_price",
    "bond_price",
)
RUN_OUTPUT = (
    "stock_shares",
    "bond_shares",
    "quote_before_percent",
    "quote_stock_percent",
    "deadline",
    "band_breached",
    "rebalanced",
    "value_strategy",
    "value_hold",
)
TABLE_REBALANCING = (
    "date",
    "stock_price",
    "bond_price",
    "quote_before_percent",
    "value_strategy",
)

SENTENCE_EXACTNESS_HFEA_DE = (
    "Mit denselben, um Splits und Ausschüttungen bereinigten Schlusskursen "
    "beider Produkte, an Tagen, an denen beide einen Kurs haben, und ab dem "
    "ersten gemeinsamen Tag rechnet die Seite dieselbe Wertkurve. Rohe "
    "Schlusskurse weichen ab jedem Ausschüttungstag ab."
)
SENTENCE_EXACTNESS_HFEA_EN = (
    "With the same closing prices of both products, adjusted for splits and "
    "distributions, on days on which both have a price, and from the first "
    "common day, the site computes the same value curve. Raw closing prices "
    "deviate from every distribution day onwards."
)
SENTENCE_BAND_DE = (
    "Die Bandbedingung oben rechnet der Backtest der Seite heute nicht; das "
    "Paket zeigt sie im zweiten Lauf."
)

COMPARISON_WORDS = (
    "besser",
    "schlechter",
    "höher als",
    "niedriger als",
    "übertrifft",
    "schlägt",
    "vorne",
    "better",
    "worse",
    "higher than",
    "lower than",
    "outperform",
    "beats",
)
ANNOUNCEMENT_WORDS = ("bald", "demnächst", "künftig", "soon", "upcoming")

# Word list outside the :::layer boxes, state main ffcca6b (counters).
WORDLIST_BASE_HFEA = {
    "hfea.de.md": {"Prognose": 1, "beste": 1},
    "hfea.en.md": {"forecast": 1, "best": 5},
}

PRESET_HFEA = re.compile(r"HFEA__(\d+)_(\d+)__([A-Z]+)__(?:BANDS(\d+(?:[.,]\d+)?)__)?")
PERIODS_PRESET = {
    "MONTHLY": 1,
    "QUARTERLY": 3,
    "SEMIANNUAL": 6,
    "SEMIANNUALLY": 6,
    "ANNUAL": 12,
    "ANNUALLY": 12,
    "YEARLY": 12,
}


def _word_boundary(word: str) -> re.Pattern[str]:
    return re.compile(r"(?<!\w)" + re.escape(word) + r"(?!\w)", re.IGNORECASE)


def _parse_date(text: str) -> date:
    return date.fromisoformat(text.strip())


def _add_months(start: date, months: int) -> date:
    """Add months, capped at the end of the month (like utils/dates.add_months)."""
    year, month = divmod(start.month - 1 + months, 12)
    year += start.year
    month += 1
    next_month = date(year + (month == 12), month % 12 + 1, 1)
    last_day = (next_month - timedelta(days=1)).day
    return date(year, month, min(start.day, last_day))


def _next_schedule_date(start: date, period: int) -> date:
    """First calendar date strictly after `start`: the 1st of a scheduled month."""
    year, month = start.year, start.month
    while True:
        month += 1
        if month > 12:
            year, month = year + 1, 1
        if (month - 1) % period == 0:
            return date(year, month, 1)


def _flatten(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _paragraphs(text: str) -> list[str]:
    return [_flatten(a).strip() for a in re.split(r"\n\s*\n", text) if a.strip()]


def _mentions_band(paragraph: str) -> bool:
    return bool(
        re.search(r"termin_und_band|Termin und Band|(?i:date and band)", paragraph)
    )


def _runs(rows: list[dict[str, str]]) -> dict[str, list[int]]:
    groups: dict[str, list[int]] = {}
    for i, row in enumerate(rows):
        groups.setdefault(row.get("run", ""), []).append(i)
    return groups


def _load_rebalancing_rows() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    path = EXAMPLES / REBALANCING
    if not (path / "input.csv").is_file() or not (path / "output.csv").is_file():
        raise AssertionError("examples/rebalancing/input.csv or output.csv is missing")
    return (
        _read_csv((path / "input.csv").read_text(encoding="utf-8")),
        _read_csv((path / "output.csv").read_text(encoding="utf-8")),
    )


def _run_rows(
    rows_output: list[dict[str, str]], rule: str
) -> list[dict[str, str]]:
    rows = [z for z in rows_output if z.get("rule") == rule]
    if not rows:
        raise AssertionError(f"no run with rule {rule!r} in output.csv")
    return rows


def _as_float(row: dict[str, str], column: str) -> float:
    return float(row[column])


def _target_weight(row: dict[str, str]) -> float:
    return _as_float(row, "stock_weight_percent") / 100.0


def _period(row: dict[str, str]) -> int:
    return int(float(row["period_months"]))


def _value_from(row: dict[str, str], previous: dict[str, str]) -> float:
    return _as_float(previous, "stock_shares") * _as_float(row, "stock_price") + _as_float(
        previous, "bond_shares"
    ) * _as_float(row, "bond_price")


def _number_from_cell(cell: str) -> float:
    match = re.search(r"-?\d+(?:[.,]\d+)?", cell)
    if not match:
        raise AssertionError(f"no number in the table cell {cell!r}")
    return float(match.group(0).replace(",", "."))


def _rebalance_box(text: str, language: str) -> tuple[str, str, str]:
    """(chapter recompute, its sixth H3, "Tag für Tag gerechnet" in math)."""
    # Wave strategie-nachrechnen-it: the open text is split into the sixth H3
    # of recompute and the last H3 of math.
    return (
        _section(text, "recompute"),
        _same_computation(text, language),
        _day_by_day(text, language),
    )


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?;])\s+|\n\s*\n", text) if s.strip()]


class TestRebalancingPackage(unittest.TestCase):
    """Acceptance 1: recompute reproduces output.csv, standard library, steps."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.path = EXAMPLES / REBALANCING
        if not cls.path.is_dir():
            raise AssertionError("examples/rebalancing is missing")

    def test_package_check_without_findings(self) -> None:
        self.assertEqual([], check_package(self.path))

    def test_recompute_reproduces_output(self) -> None:
        run = subprocess.run(
            [
                sys.executable,
                str(self.path / "recompute.py"),
                str(self.path / "input.csv"),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(0, run.returncode, run.stderr)
        problems = _compare_outputs(
            REBALANCING,
            _read_csv((self.path / "output.csv").read_text(encoding="utf-8")),
            _read_csv(run.stdout),
        )
        self.assertEqual([], problems)

    def test_imports_standard_library_only(self) -> None:
        code = (self.path / "recompute.py").read_text(encoding="utf-8")
        for module in _imports(code):
            self.assertIn(module, ALLOWED_IMPORTS, f"recompute.py imports {module!r}")

    def test_steps_in_code_and_readme_match(self) -> None:
        code = (self.path / "recompute.py").read_text(encoding="utf-8")
        readme = (self.path / "README.md").read_text(encoding="utf-8")
        steps_code = _code_steps(code)
        self.assertTrue(steps_code, "recompute.py has no step comments")
        self.assertEqual(steps_code, _readme_steps(readme))

    def test_no_short_name_of_the_strategy_in_the_package(self) -> None:
        for file in PACKAGE_FILES:
            with self.subTest(file=file):
                text = (self.path / file).read_text(encoding="utf-8")
                self.assertIsNone(
                    _word_boundary("HFEA").search(text),
                    f"{file} names the short name of the strategy",
                )


class TestRebalancingFormat(unittest.TestCase):
    """BAU-1 and acceptance 5: long format, two runs, no comparison row."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.rows_input, cls.rows_output = _load_rebalancing_rows()

    def test_columns_of_input_and_output(self) -> None:
        self.assertTrue(self.rows_input, "input.csv is empty")
        self.assertTrue(self.rows_output, "output.csv is empty")
        for column in RUN_INPUT:
            self.assertIn(
                column, self.rows_input[0], f"input.csv without column {column}"
            )
            self.assertIn(
                column, self.rows_output[0], f"output.csv without column {column}"
            )
        for column in RUN_OUTPUT:
            self.assertIn(
                column, self.rows_output[0], f"output.csv without column {column}"
            )

    def test_two_runs_with_fixed_values(self) -> None:
        groups = _runs(self.rows_input)
        self.assertEqual(2, len(groups), f"not exactly two runs: {list(groups)}")
        rules: list[str] = []
        for run, positions in groups.items():
            with self.subTest(run=run):
                self.assertEqual(
                    list(range(positions[0], positions[-1] + 1)),
                    positions,
                    f"the rows of run {run} are not contiguous",
                )
                rows = [self.rows_input[i] for i in positions]
                for column in (
                    "rule",
                    "stock_weight_percent",
                    "period_months",
                    "band_percentage_points",
                ):
                    values = {z.get(column, "") for z in rows}
                    self.assertEqual(
                        1, len(values), f"{column} is not the same in run {run}"
                    )
                first = rows[0]
                rules.append(first["rule"])
                self.assertEqual(60.0, _as_float(first, "stock_weight_percent"))
                self.assertEqual(
                    3.0 if first["rule"] == "termin" else 1.0,
                    _as_float(first, "period_months"),
                    f"period of run {run} ({first['rule']})",
                )
                if first["rule"] == "termin_und_band":
                    self.assertTrue(
                        _is_number(first["band_percentage_points"]),
                        "the run termin_und_band names no band",
                    )
                    self.assertGreater(_as_float(first, "band_percentage_points"), 0.0)
                days = [_parse_date(z["date"]) for z in rows]
                self.assertEqual(
                    sorted(set(days)),
                    days,
                    f"the days in run {run} do not increase strictly",
                )
        self.assertEqual(sorted(RULES), sorted(rules))

    def test_every_output_row_belongs_to_its_input_row(self) -> None:
        self.assertEqual(len(self.rows_input), len(self.rows_output))
        for e, a in zip(self.rows_input, self.rows_output):
            for column in RUN_INPUT:
                self.assertEqual(
                    e.get(column, ""),
                    a.get(column, ""),
                    f"row {e.get('run')}/{e.get('date')}: {column} differs",
                )

    def test_no_sum_or_comparison_row(self) -> None:
        runs = set(_runs(self.rows_input))
        for a in self.rows_output:
            self.assertRegex(a.get("date", ""), r"^\d{4}-\d{2}-\d{2}$")
            self.assertIn(a.get("run", ""), runs)
            self.assertIn(a.get("rule", ""), RULES)
        for column in self.rows_output[0]:
            for word in ("vergleich", "differenz", "vorsprung", "summe", "delta"):
                self.assertNotIn(
                    word, column.lower(), f"output.csv has a column {column}"
                )

    def test_values_of_the_default_version_do_not_occur(self) -> None:
        for e in self.rows_input:
            self.assertNotIn(_as_float(e, "stock_weight_percent"), (55.0, 45.0))
            # Run termin is quarterly (spec hfea-nachrechnen-kalender BAU-2).
            if e.get("rule") != "termin":
                self.assertNotEqual(3.0, _as_float(e, "period_months"))
            if _is_number(e.get("band_percentage_points", "")):
                self.assertNotIn(_as_float(e, "band_percentage_points"), (5.0, 10.0))


class TestRebalancingCalculation(unittest.TestCase):
    """Acceptance 3 and 4: anchor, deadline, band, unit counts, holding per run."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.rows_input, cls.rows_output = _load_rebalancing_rows()
        cls.runs = {
            run: [cls.rows_output[i] for i in positions]
            for run, positions in _runs(cls.rows_output).items()
        }
        if not cls.runs:
            raise AssertionError("output.csv contains no run")

    def test_anchor_at_the_first_common_day(self) -> None:
        for run, rows in self.runs.items():
            with self.subTest(run=run):
                z = rows[0]
                g = _target_weight(z)
                self.assertAlmostEqual(
                    g * 100.0 / _as_float(z, "stock_price"), _as_float(z, "stock_shares"), places=9
                )
                self.assertAlmostEqual(
                    (1.0 - g) * 100.0 / _as_float(z, "bond_price"),
                    _as_float(z, "bond_shares"),
                    places=9,
                )
                self.assertEqual(100.0, _as_float(z, "value_strategy"))
                self.assertEqual(100.0, _as_float(z, "value_hold"))
                self.assertAlmostEqual(100.0 * g, _as_float(z, "quote_before_percent"), places=9)
                self.assertFalse(
                    _as_bool(z.get("rebalanced", "")),
                    "the anchor day counts as rebalancing",
                )
                if z["rule"] == "termin":
                    self.assertEqual(
                        _next_schedule_date(_parse_date(z["date"]), _period(z)),
                        _parse_date(z["deadline"]),
                        "the deadline of the anchor row is not the first "
                        "calendar date strictly after the anchor day",
                    )
                else:
                    self.assertEqual(
                        _add_months(_parse_date(z["date"]), _period(z)),
                        _parse_date(z["deadline"]),
                        "the first deadline does not count from the anchor day",
                    )

    def test_deadline_and_rebalancing_follow_the_rule(self) -> None:
        for run, rows in self.runs.items():
            with self.subTest(run=run):
                for previous, z in zip(rows, rows[1:]):
                    deadline_before = _parse_date(previous["deadline"])
                    today = _parse_date(z["date"])
                    due = today >= deadline_before
                    if z["rule"] == "termin_und_band":
                        expected = due and _as_bool(z.get("band_breached", ""))
                    else:
                        expected = due
                    self.assertEqual(
                        expected,
                        _as_bool(z.get("rebalanced", "")),
                        f"rebalanced on {z['date']} does not follow the rule",
                    )
                    self.assertTrue(
                        z.get("deadline", ""), f"deadline empty on {z['date']}"
                    )
                    if expected and z["rule"] == "termin":
                        self.assertEqual(
                            deadline_before.day,
                            1,
                            f"the date before {z['date']} is not the first of a month",
                        )
                        self.assertEqual(
                            _next_schedule_date(deadline_before, _period(z)),
                            _parse_date(z["deadline"]),
                            f"the new deadline on {z['date']} is not the "
                            "next calendar date after the executed one",
                        )
                        self.assertLess(
                            today,
                            _parse_date(z["deadline"]),
                            f"on {z['date']} a date was skipped",
                        )
                    elif expected:
                        self.assertEqual(
                            _add_months(today, _period(z)),
                            _parse_date(z["deadline"]),
                            f"the new deadline on {z['date']} does not count from the "
                            "actual rebalancing day",
                        )
                    else:
                        self.assertEqual(
                            previous["deadline"],
                            z["deadline"],
                            f"the deadline changes on {z['date']} without rebalancing",
                        )

    def test_share_before_from_unit_counts_of_the_previous_row(self) -> None:
        for run, rows in self.runs.items():
            with self.subTest(run=run):
                for previous, z in zip(rows, rows[1:]):
                    value = _value_from(z, previous)
                    expected = (
                        100.0
                        * _as_float(previous, "stock_shares")
                        * _as_float(z, "stock_price")
                        / value
                    )
                    self.assertAlmostEqual(
                        expected,
                        _as_float(z, "quote_before_percent"),
                        places=9,
                        msg=f"quote_before_percent on {z['date']}",
                    )

    def test_band_breached_follows_from_share_before(self) -> None:
        for run, rows in self.runs.items():
            with self.subTest(run=run):
                for z in rows:
                    band_text = z.get("band_percentage_points", "")
                    if not _is_number(band_text):
                        self.assertFalse(_as_bool(z.get("band_breached", "")))
                        continue
                    distance = abs(_as_float(z, "quote_before_percent") - 100.0 * _target_weight(z))
                    band = float(band_text)
                    if abs(distance - band) <= 1e-9:
                        continue
                    self.assertEqual(
                        distance >= band,
                        _as_bool(z.get("band_breached", "")),
                        f"band_breached on {z['date']} does not follow from "
                        "|share before - target| >= band",
                    )

    def test_after_rebalancing_target_weight_and_value_preserved(self) -> None:
        seen = 0
        for run, rows in self.runs.items():
            with self.subTest(run=run):
                for previous, z in zip(rows, rows[1:]):
                    if not _as_bool(z.get("rebalanced", "")):
                        continue
                    seen += 1
                    value = _as_float(z, "value_strategy")
                    self.assertAlmostEqual(
                        100.0 * _target_weight(z), _as_float(z, "quote_stock_percent"), places=9
                    )
                    self.assertAlmostEqual(_value_from(z, previous), value, places=9)
                    self.assertAlmostEqual(_value_from(z, z), value, places=9)
                    self.assertAlmostEqual(
                        100.0 * _target_weight(z),
                        100.0 * _as_float(z, "stock_shares") * _as_float(z, "stock_price") / value,
                        places=9,
                    )
        self.assertGreater(seen, 0, "no rebalancing in the example")

    def test_between_the_dates_unit_counts_times_prices(self) -> None:
        for run, rows in self.runs.items():
            with self.subTest(run=run):
                for previous, z in zip(rows, rows[1:]):
                    if _as_bool(z.get("rebalanced", "")):
                        continue
                    for column in ("stock_shares", "bond_shares"):
                        self.assertAlmostEqual(
                            _as_float(previous, column),
                            _as_float(z, column),
                            places=12,
                            msg=f"{column} changes on {z['date']}",
                        )
                    self.assertAlmostEqual(
                        _value_from(z, z), _as_float(z, "value_strategy"), places=9
                    )
                    self.assertAlmostEqual(
                        _as_float(z, "quote_before_percent"),
                        _as_float(z, "quote_stock_percent"),
                        places=9,
                    )

    def test_value_hold_with_the_start_weights(self) -> None:
        for run, rows in self.runs.items():
            with self.subTest(run=run):
                a0 = _as_float(rows[0], "stock_price")
                b0 = _as_float(rows[0], "bond_price")
                for z in rows:
                    g = _target_weight(z)
                    expected = 100.0 * (
                        g * _as_float(z, "stock_price") / a0
                        + (1.0 - g) * _as_float(z, "bond_price") / b0
                    )
                    self.assertAlmostEqual(
                        expected, _as_float(z, "value_hold"), places=9, msg=z["date"]
                    )


class TestRebalancingEdgeCases(unittest.TestCase):
    """Acceptance 2: every minimum case from BAU-2 at its row."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.rows_input, cls.rows_output = _load_rebalancing_rows()

    def test_per_run_one_rebalancing_and_one_quiet_day(self) -> None:
        for rule in RULES:
            with self.subTest(rule=rule):
                rows = _run_rows(self.rows_output, rule)
                rebalanced = [z for z in rows[1:] if _as_bool(z.get("rebalanced", ""))]
                quiet = [z for z in rows[1:] if not _as_bool(z.get("rebalanced", ""))]
                self.assertTrue(rebalanced, f"run {rule} never rebalances")
                self.assertTrue(quiet, f"run {rule} has no quiet day")

    def test_deadline_on_saturday_rebalancing_on_monday(self) -> None:
        rows = _run_rows(self.rows_output, "termin")
        hits = 0
        for previous, z in zip(rows, rows[1:]):
            deadline = _parse_date(previous["deadline"])
            if deadline.weekday() != 5 or not _as_bool(z.get("rebalanced", "")):
                continue
            hits += 1
            today = _parse_date(z["date"])
            self.assertEqual(deadline + timedelta(days=2), today)
            self.assertEqual(0, today.weekday())
            self.assertEqual(
                1, deadline.day, "the Saturday date is not the first of a month"
            )
            self.assertEqual(
                _next_schedule_date(deadline, _period(z)),
                _parse_date(z["deadline"]),
                "the next deadline counts from Monday instead of from the calendar",
            )
            self.assertEqual(
                ("1927-01-01", "1927-01-03"), (previous["deadline"], z["date"])
            )
            self.assertEqual("1927-04-01", z["deadline"])
        self.assertTrue(hits, "no deadline on a Saturday with rebalancing on Monday")

    def test_capping_at_month_end_without_return(self) -> None:
        rows = _run_rows(self.rows_output, "termin_und_band")
        start = _parse_date(rows[0]["date"])
        hits = 0
        for previous, z in zip(rows, rows[1:]):
            if not _as_bool(z.get("rebalanced", "")):
                continue
            period = _period(z)
            deadline = _parse_date(previous["deadline"])
            if _add_months(start, period) == deadline and deadline.day < start.day:
                hits += 1
                self.assertGreater(
                    _parse_date(z["date"]),
                    date(1926, 10, 15),
                    "the capping case is not appended to run 2",
                )
                new_deadline = _parse_date(z["deadline"])
                self.assertEqual(_add_months(_parse_date(z["date"]), period), new_deadline)
                self.assertLess(
                    new_deadline.day,
                    start.day,
                    "after capping the deadline returns to the old day",
                )
                self.assertNotEqual(
                    _add_months(start, 2 * period),
                    new_deadline,
                    "after capping the deadline returns to the last day of the month",
                )
            start = _parse_date(z["date"])
        self.assertTrue(
            hits, "no capped deadline at month end in run termin_und_band"
        )

    def test_expired_date_without_band_then_rebalancing(self) -> None:
        rows = _run_rows(self.rows_output, "termin_und_band")
        waiting = [
            i
            for i in range(1, len(rows))
            if _parse_date(rows[i]["date"]) >= _parse_date(rows[i - 1]["deadline"])
            and not _as_bool(rows[i].get("band_breached", ""))
        ]
        self.assertTrue(waiting, "no expired date without a breached band")
        for i in waiting:
            self.assertFalse(_as_bool(rows[i].get("rebalanced", "")))
            self.assertEqual(rows[i - 1]["deadline"], rows[i]["deadline"])
        i = waiting[0]
        following = [
            j
            for j in range(i + 1, len(rows))
            if _as_bool(rows[j].get("band_breached", ""))
        ]
        self.assertTrue(following, "after waiting no day breaches the band")
        j = following[0]
        self.assertTrue(
            _as_bool(rows[j].get("rebalanced", "")),
            "on the first day with a breached band there is no rebalancing",
        )
        for k in range(i, j):
            self.assertFalse(_as_bool(rows[k].get("rebalanced", "")))

    def test_share_runs_far_away_from_the_target(self) -> None:
        distance = max(
            abs(_as_float(z, "quote_before_percent") - 100.0 * _target_weight(z))
            for z in self.rows_output
        )
        self.assertGreaterEqual(
            distance, 5.0, "in no run does the share run far away from the target"
        )


SENTENCE_CALENDAR_DE = (
    "Bei quartalsweisem Rebalancing rechnet die Regel mit dem ersten "
    "Handelstag jedes Quartals (allgemein: dem ersten Handelstag jedes "
    "Terminmonats). Das ist eine Konvention, keine Empfehlung."
)
SENTENCE_CALENDAR_EN = (
    "With quarterly rebalancing, the rule uses the first trading day of each "
    "quarter (in general: the first trading day of each scheduled month). "
    "This is a convention, not a recommendation."
)
SENTENCE_ANCHOR_DATE = "if the anchor day falls on a scheduled date, no rebalancing happens on it"
ACTUAL_REBALANCING_DAY = {
    "de": "tatsächlichen Umschichtungstag",
    "en": "actual rebalancing day",
}
WORDS_NEW_LINES = re.compile(
    r"\b(beste[nrs]?|besser|best|better|optimal|expected|forecast)\b", re.IGNORECASE
)

# Run 2 from before the wave hfea-nachrechnen-kalender (main a4e718c); stays
# line by line, the capping case is appended.
RUN2_INPUT_OLD = (
    "2,termin_und_band,60,1,6,1926-09-01,60.0,40.0",
    "2,termin_und_band,60,1,6,1926-09-30,68.7,39.45",
    "2,termin_und_band,60,1,6,1926-10-01,69.2,39.4",
    "2,termin_und_band,60,1,6,1926-10-12,74.1,38.9",
    "2,termin_und_band,60,1,6,1926-10-13,74.3,38.4",
    "2,termin_und_band,60,1,6,1926-10-14,75.8,37.9",
    "2,termin_und_band,60,1,6,1926-10-15,75.5,38.0",
)
RUN2_OUTPUT_OLD = (
    "2,termin_und_band,60,1,6,1926-09-01,60.0,40.0,1.0,1.0,60.0,60.0,"
    "1926-10-01,nein,nein,100.0,100.0",
    "2,termin_und_band,60,1,6,1926-09-30,68.7,39.45,1.0,1.0,63.522884882108,"
    "63.522884882108,1926-10-01,nein,nein,108.15,108.15",
    "2,termin_und_band,60,1,6,1926-10-01,69.2,39.4,1.0,1.0,63.720073664825,"
    "63.720073664825,1926-10-01,nein,nein,108.6,108.6",
    "2,termin_und_band,60,1,6,1926-10-12,74.1,38.9,1.0,1.0,65.575221238938,"
    "65.575221238938,1926-10-01,nein,nein,113.0,113.0",
    "2,termin_und_band,60,1,6,1926-10-13,74.3,38.4,1.0,1.0,65.927240461402,"
    "65.927240461402,1926-10-01,nein,nein,112.7,112.7",
    "2,termin_und_band,60,1,6,1926-10-14,75.8,37.9,0.9,1.2,66.666666666667,"
    "60.0,1926-11-14,ja,ja,113.7,113.7",
    "2,termin_und_band,60,1,6,1926-10-15,75.5,38.0,0.9,1.2,59.841479524439,"
    "59.841479524439,1926-11-14,nein,nein,113.55,113.5",
)


class TestRebalancingCalendar(unittest.TestCase):
    """Acceptance hfea-nachrechnen-kalender: run termin with calendar dates."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.path = EXAMPLES / REBALANCING
        cls.rows_input, cls.rows_output = _load_rebalancing_rows()
        cls.termin_rows = _run_rows(cls.rows_output, "termin")
        cls.by_day = {z["date"]: z for z in cls.termin_rows}

    def test_recompute_byte_identical(self) -> None:
        run = subprocess.run(
            [
                sys.executable,
                str(self.path / "recompute.py"),
                str(self.path / "input.csv"),
            ],
            capture_output=True,
            timeout=60,
        )
        self.assertEqual(0, run.returncode, run.stderr)
        self.assertEqual((self.path / "output.csv").read_bytes(), run.stdout)

    def test_run_termin_quarterly_from_1926_04_01(self) -> None:
        first = self.termin_rows[0]
        self.assertEqual("1926-04-01", first["date"])
        self.assertEqual(3, _period(first))
        self.assertFalse(_as_bool(first["rebalanced"]), "rebalanced on the anchor day")
        self.assertEqual("1926-07-01", first["deadline"])

    def test_rebalancing_exactly_on_the_dates(self) -> None:
        rebalanced = [
            z["date"] for z in self.termin_rows if _as_bool(z.get("rebalanced", ""))
        ]
        self.assertEqual(["1926-07-01", "1926-10-01", "1927-01-03"], rebalanced)
        self.assertEqual("1927-04-01", self.by_day["1927-01-03"]["deadline"])

    def test_first_trading_day_in_may_without_rebalancing(self) -> None:
        self.assertIn("1926-05-03", self.by_day, "1926-05-03 is missing in the run")
        z = self.by_day["1926-05-03"]
        self.assertFalse(_as_bool(z["rebalanced"]))
        self.assertEqual("1926-07-01", z["deadline"])

    def test_rebalanced_exactly_on_the_first_trading_day_after_each_date(self) -> None:
        anchor = _parse_date(self.termin_rows[0]["date"])
        period = _period(self.termin_rows[0])
        days = [_parse_date(z["date"]) for z in self.termin_rows]
        expected: set[date] = set()
        scheduled = _next_schedule_date(anchor, period)
        while scheduled <= days[-1]:
            first = min(t for t in days if t >= scheduled)
            in_between = [
                scheduled + timedelta(days=k)
                for k in range((first - scheduled).days)
            ]
            self.assertTrue(
                all(t.weekday() >= 5 for t in in_between),
                f"the input does not list the first trading day after {scheduled}",
            )
            expected.add(first)
            scheduled = _next_schedule_date(scheduled, period)
        actual = {
            _parse_date(z["date"]) for z in self.termin_rows if _as_bool(z.get("rebalanced", ""))
        }
        self.assertEqual(expected, actual)

    def test_run2_old_rows_unchanged(self) -> None:
        for file, old in (
            ("input.csv", RUN2_INPUT_OLD),
            ("output.csv", RUN2_OUTPUT_OLD),
        ):
            with self.subTest(file=file):
                rows = [
                    z
                    for z in (self.path / file).read_text(encoding="utf-8").splitlines()
                    if ",termin_und_band," in z
                ]
                self.assertEqual(list(old), rows[: len(old)])
                self.assertGreater(
                    len(rows), len(old), f"no capping case appended ({file})"
                )


class TestRebalancingCalendarTexts(unittest.TestCase):
    """BAU-3 and BAU-4: sentences per rule in README and box (de, en)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.readme = (EXAMPLES / REBALANCING / "README.md").read_text(encoding="utf-8")
        # Wave strategie-nachrechnen-it: "boxes" is "Tag für Tag gerechnet" in
        # math, "same" the sixth H3 of recompute, "chapters" the whole chapter.
        cls.boxes: dict[str, str] = {}
        cls.same: dict[str, str] = {}
        cls.chapters: dict[str, str] = {}
        for language in ("de", "en"):
            path = ROOT / "content" / "strategies" / f"hfea.{language}.md"
            chapter, same, days = _rebalance_box(
                path.read_text(encoding="utf-8"), language
            )
            cls.boxes[language] = days
            cls.same[language] = same
            cls.chapters[language] = chapter

    def _texts(self) -> list[tuple[str, str, str]]:
        return [
            ("README", "en", self.readme),
            ("box de", "de", self.boxes["de"]),
            ("box en", "en", self.boxes["en"]),
        ]

    def test_calendar_sentence_verbatim(self) -> None:
        for name, language, text in (
            ("README", "en", self.readme),
            ("sixth H3 de", "de", self.same["de"]),
            ("sixth H3 en", "en", self.same["en"]),
        ):
            with self.subTest(text=name):
                sentence = SENTENCE_CALENDAR_DE if language == "de" else SENTENCE_CALENDAR_EN
                self.assertIn(
                    sentence, _flatten(text), f"{name} without the calendar sentence"
                )

    def test_actual_rebalancing_day_only_with_termin_und_band(self) -> None:
        for name, language, text in self._texts():
            with self.subTest(text=name):
                word = ACTUAL_REBALANCING_DAY[language]
                paragraphs = _paragraphs(text)
                with_band = [a for a in paragraphs if _mentions_band(a)]
                without_band = [a for a in paragraphs if not _mentions_band(a)]
                self.assertTrue(
                    any(word in a for a in with_band),
                    f"{name}: the paragraph on term and band does not name {word!r}",
                )
                for paragraph in without_band:
                    self.assertNotIn(
                        word,
                        paragraph,
                        f"{name}: {word!r} appears in the rule after the date",
                    )
                sentence = SENTENCE_CALENDAR_DE if language == "de" else SENTENCE_CALENDAR_EN
                for paragraph in paragraphs:
                    if sentence in paragraph:
                        self.assertNotIn(word, paragraph)

    def test_readme_anchor_day_on_a_scheduled_date(self) -> None:
        flat = _flatten(self.readme)
        self.assertNotIn("Der Ankertag selbst ist kein Termin", flat)
        self.assertNotIn("the anchor day itself is not a scheduled date", flat)
        self.assertIn(SENTENCE_ANCHOR_DATE.lower(), flat.lower())

    def test_readme_period_and_input_follow_the_new_run(self) -> None:
        flat = _flatten(self.readme)
        self.assertNotIn("Periode von einem Monat", flat)
        self.assertNotIn("period of one month", flat)
        self.assertIn("on or after each scheduled date", flat)
        self.assertIn("The input lists not every trading day", flat)

    def test_readme_steps_separated_per_rule(self) -> None:
        steps = dict(_readme_steps(self.readme))
        section = re.search(r"(?ms)^## (?:Schritte|Steps)[ \t]*$(.*?)(?=^#|\Z)", self.readme)
        self.assertIsNotNone(section, "README.md has no section Steps")
        rows = {
            int(m.group(1)): _flatten(m.group(0))
            for m in re.finditer(r"(?m)^(\d+)\..*(?:\n[ \t]+\S.*)*$", section.group(1))
        }
        for number in (2, 5):
            with self.subTest(step=number):
                self.assertIn(number, steps)
                row = rows[number]
                self.assertIn("`termin`", row, f"step {number} without `termin`")
                self.assertIn(
                    "`termin_und_band`", row, f"step {number} without `termin_und_band`"
                )

    def test_box_without_deadline_chain_from_monday(self) -> None:
        for language, old in (
            ("de", ("zählt vom Montag", "Periode von einem Monat")),
            ("en", ("counts from the Monday", "period of one month")),
        ):
            with self.subTest(language=language):
                flat = _flatten(self.boxes[language])
                self.assertTrue(flat.strip(), f"box is missing ({language})")
                for part in old:
                    self.assertNotIn(part, flat)

    def test_words_and_recommendation_only_negated(self) -> None:
        for name, _, text in self._texts() + [
            ("recompute de", "de", self.chapters["de"]),
            ("recompute en", "en", self.chapters["en"]),
        ]:
            with self.subTest(text=name):
                self.assertEqual([], WORDS_NEW_LINES.findall(text), name)
                flat = _flatten(text)
                self.assertEqual(
                    flat.count("Empfehlung"), flat.count("keine Empfehlung"), name
                )
                self.assertEqual(
                    flat.lower().count("recommendation"),
                    flat.count("not a recommendation"),
                    name,
                )
                for character in (chr(0x2014), chr(0x2013)):
                    self.assertNotIn(character, text, f"dash in {name}")


class TestRebalancingReadme(unittest.TestCase):
    """BAU-3: recipe, column table, mandatory sentences, no comparison."""

    @classmethod
    def setUpClass(cls) -> None:
        path = EXAMPLES / REBALANCING / "README.md"
        if not path.is_file():
            raise AssertionError("examples/rebalancing/README.md is missing")
        cls.text = path.read_text(encoding="utf-8")

    def test_column_table_names_every_column(self) -> None:
        table_rows = [
            z for z in self.text.splitlines() if z.strip().startswith("|")
        ]
        self.assertTrue(table_rows, "README.md has no column table")
        for column in RUN_INPUT + RUN_OUTPUT:
            self.assertTrue(
                any(_word_boundary(column).search(z) for z in table_rows),
                f"the column table does not name {column}",
            )

    def test_mandatory_sentences(self) -> None:
        flat = _flatten(self.text)
        for part in (
            "first common day",
            "not from the beginning",
            "both products have a price",
            "4 decimal places",
            "0.01",
            "Both are explained separately",
            "state of the data",
            "NAV",
            "closing price",
            "the adjustments that LETF.io itself makes",
            "the outlier check",
            "its terms of use apply",
        ):
            self.assertIn(part, flat, f"README.md does not name {part!r}")

    def test_tax_and_costs_only_as_not_computed(self) -> None:
        hits = [
            s
            for s in _sentences(self.text)
            if re.search(r"(?i)(?<!\w)tax(?!\w)|trading costs", s)
        ]
        self.assertTrue(hits, "README.md does not name tax and trading costs")
        self.assertTrue(any(re.search(r"(?i)(?<!\w)tax(?!\w)", s) for s in hits))
        self.assertTrue(any(re.search("(?i)trading costs", s) for s in hits))
        for sentence in hits:
            self.assertIn(
                "computes no",
                sentence,
                f"tax or costs are not named as not computed: {sentence!r}",
            )

    def test_no_comparison_of_the_runs(self) -> None:
        for word in COMPARISON_WORDS:
            self.assertIsNone(
                _word_boundary(word).search(self.text),
                f"README.md compares with {word!r}",
            )

    def test_exact_only_in_the_fixed_sentence_and_no_dashes(self) -> None:
        rest = (
            _flatten(self.text)
            .replace(_flatten(SENTENCE_EXACTNESS_HFEA_DE), "")
            .replace(_flatten(SENTENCE_EXACTNESS_HFEA_EN), "")
        )
        for word in ("exakt", "exact", "dieselben zahlen", "the same numbers"):
            self.assertIsNone(re.search(word, rest, re.IGNORECASE), word)
        for mark in (chr(0x2014), chr(0x2013)):
            self.assertNotIn(mark, self.text, "dash in the package README")


class TestRebalancingBox(unittest.TestCase):
    """Acceptance 6: box Zum Nachrechnen in hfea (DE and EN) per BAU-4."""

    @classmethod
    def setUpClass(cls) -> None:
        # Wave strategie-nachrechnen-it: the old box is split. "boxes" is the
        # last H3 of math (Tag für Tag gerechnet), "same" the sixth H3 of
        # recompute, "chapters" the whole chapter recompute.
        cls.texts: dict[str, str] = {}
        cls.boxes: dict[str, str] = {}
        cls.same: dict[str, str] = {}
        cls.chapters: dict[str, str] = {}
        for language in ("de", "en"):
            path = ROOT / "content" / "strategies" / f"hfea.{language}.md"
            text = path.read_text(encoding="utf-8")
            cls.texts[language] = text
            chapter, same, days = _rebalance_box(text, language)
            cls.boxes[language] = days
            cls.same[language] = same
            cls.chapters[language] = chapter

    def _box(self, language: str) -> str:
        box = self.boxes[language]
        self.assertTrue(
            box.strip(),
            f"the last H3 of math is not {DAY_BY_DAY[language]!r} ({language})",
        )
        return box

    def _same(self, language: str) -> str:
        same = self.same[language]
        self.assertTrue(
            same.strip(), f"the sixth H3 of recompute is missing ({language})"
        )
        return same

    def _chapter(self, language: str) -> str:
        chapter = self.chapters[language]
        self.assertTrue(chapter.strip(), f"no chapter recompute ({language})")
        return chapter

    def test_compute_box_in_chapter_recompute_not_in_math(self) -> None:
        """BAU-4: formulas in math under Tag für Tag gerechnet, none in recompute."""
        for language, text in self.texts.items():
            with self.subTest(language=language):
                box = self._box(language)
                self.assertFalse(
                    box.strip().startswith("**"),
                    f"Tag für Tag gerechnet starts with a bold lead ({language})",
                )
                chapter = self._chapter(language)
                for mark in ("$$", "\\frac", "\\begin"):
                    self.assertNotIn(
                        mark, chapter, f"recompute shows a formula {mark} ({language})"
                    )
                self.assertIsNone(
                    re.search(r"(?m)^:::layer", chapter),
                    f"recompute still has a layer box ({language})",
                )
                math = _section(text, "math")
                self.assertTrue(math, f"no section math ({language})")
                self.assertNotIn("Zum Nachrechnen", math, language)
                self.assertEqual(
                    [],
                    [z for z in _link_targets(math) if "examples/" in z],
                    f"math still links into examples/ ({language})",
                )

    def test_starts_with_lead_sentence_and_ends_with_link(self) -> None:
        """BAU-4: no bold lead any more; the package link stands in recompute."""
        for language in ("de", "en"):
            with self.subTest(language=language):
                chapter = self._chapter(language)
                self.assertNotIn("**Zum Nachrechnen.**", chapter)
                self.assertIn(
                    URL_REBALANCING,
                    _link_targets(chapter),
                    f"recompute does not link the package README ({language})",
                )
                rest = _without_links(chapter)
                for word in WORDS_NO_PROMISE + ANNOUNCEMENT_WORDS:
                    self.assertIsNone(
                        _word_boundary(word).search(rest),
                        f"recompute lists {word!r} ({language})",
                    )
                # Fassung 3: the fixed BAU-4 sentence is allowed once; every
                # other "Deine Fassung"/"your version" stays forbidden.
                fixed = {
                    "de": "Deine Fassung kann diese Werte ändern",
                    "en": "Your own version can change these values",
                }[language]
                rest = _flatten(rest)
                self.assertIn(fixed, rest, f"the fixed sentence is missing ({language})")
                rest = rest.replace(fixed, "", 1)
                for word in ("Deine Fassung", "your version"):
                    self.assertIsNone(_word_boundary(word).search(rest), word)

    def test_umschichten_instead_of_rebalancing(self) -> None:
        # The fixed calendar sentence (BAU-4) says "Rebalancing" verbatim, and
        # the package link names the folder examples/rebalancing; both are no
        # prose. The German prose says umschichten.
        box = re.sub(r"\[[^\]]*\]\([^)]+\)", "", self._box("de"))
        box = _flatten(box).replace(SENTENCE_CALENDAR_DE, "")
        self.assertIn("umschicht", box.lower())
        self.assertNotIn("rebalancing", box.lower())

    def test_termin_first_then_termin_und_band(self) -> None:
        box = _without_links(self._box("de"))
        band_position = box.find("Termin und Band")
        self.assertGreater(band_position, 0, "the sentence on term and band is missing")
        for part in ("Stückzahl", "ersten gemeinsamen Tag"):
            position = box.find(part)
            self.assertGreaterEqual(position, 0, f"{part!r} is missing in the box")
            self.assertLess(position, band_position, f"{part!r} stands after the band")
        self.assertIn(SENTENCE_BAND_DE, box)
        self.assertGreater(box.find(SENTENCE_BAND_DE), band_position)
        for language in ("de", "en"):
            with self.subTest(language=language):
                k = self._box(language)
                self.assertTrue("≥" in k or "\\ge" in k, f"≥ is missing ({language})")
        en = self._box("en").lower()
        for part in ("first common day", "backtest", "second run"):
            self.assertIn(part, en)

    def test_katex_without_repetition_and_narrow(self) -> None:
        for language in ("de", "en"):
            with self.subTest(language=language):
                box = self._box(language)
                formulas = re.findall(r"\$\$(.+?)\$\$|\$([^$\n]+)\$", box, re.DOTALL)
                self.assertTrue(formulas, f"the box shows no formula ({language})")
                for repetition in ("w_e R_e + w_b R_b", "\\bigl|", "\\sigma", "\\sum"):
                    self.assertNotIn(
                        repetition, box, f"{repetition} is repeated ({language})"
                    )
                for block in re.findall(r"\$\$(.+?)\$\$", box, re.DOTALL):
                    for row in block.splitlines():
                        self.assertLessEqual(
                            len(re.sub(r"\s", "", row)),
                            70,
                            f"formula line too wide for 360 px ({language}): {row!r}",
                        )

    def test_exactness_sentence_fixed_and_exact_only_there(self) -> None:
        for language, sentence in (
            ("de", SENTENCE_EXACTNESS_HFEA_DE),
            ("en", SENTENCE_EXACTNESS_HFEA_EN),
        ):
            with self.subTest(language=language):
                same = _flatten(_without_links(self._same(language)))
                self.assertIn(
                    _flatten(sentence),
                    same,
                    f"the sixth H3 lacks the adjusted closing prices ({language})",
                )
                chapter = _flatten(_without_links(self._chapter(language)))
                rest = chapter.replace(_flatten(sentence), "")
                for word in ("exakt", "exact", "dieselben zahlen", "the same numbers"):
                    self.assertIsNone(re.search(word, rest, re.IGNORECASE), word)
                for part in ("Datenstand", "Ausreißer", "outlier", "NAV"):
                    self.assertNotIn(part, same, f"{part} belongs in the README")

    def test_box_against_names_fields_and_words(self) -> None:
        for language in ("de", "en"):
            with self.subTest(language=language):
                box = self._chapter(language) + "\n" + self._box(language)
                self.assertEqual([], _forbidden_hits(box))
                for word in BOX_WORDS + COMPARISON_WORDS:
                    self.assertIsNone(
                        _word_boundary(word).search(box),
                        f"the box contains {word!r} ({language})",
                    )
                for character in (chr(0x2014), chr(0x2013)):
                    self.assertNotIn(character, box, f"dash ({language})")

    def test_table_as_excerpt_around_the_saturday_date(self) -> None:
        _, rows_output = _load_rebalancing_rows()
        termin_rows = _run_rows(rows_output, "termin")
        for language, first_header, note in (
            ("de", "Datum", SENTENCE_TABLE_DE),
            ("en", "Date", SENTENCE_TABLE_EN),
        ):
            with self.subTest(language=language):
                box = self._same(language)
                header, body, position = _table(box)
                self.assertEqual(5, len(header), f"not five columns ({language})")
                self.assertEqual(first_header, header[0])
                for k in header:
                    self.assertIsNone(
                        re.search(r"(?i)halten|hold|vergleich|compar", k),
                        f"holding or comparison column {k!r} ({language})",
                    )
                self.assertEqual(8, len(body), f"not eight rows ({language})")
                rows = box.splitlines()
                j = position - 1
                while j >= 0 and not rows[j].strip():
                    j -= 1
                self.assertEqual(note, rows[j].strip() if j >= 0 else "")
                dates: list[str] = []
                marked: list[int] = []
                for n, row in enumerate(body):
                    match = re.search(r"\d{4}-\d{2}-\d{2}", row[0])
                    self.assertIsNotNone(match, f"no date in {row[0]!r}")
                    dates.append(match.group(0))
                    if row[0].strip() != match.group(0):
                        marked.append(n)
                positions = [i for i, a in enumerate(termin_rows) if a["date"] in dates]
                self.assertEqual(
                    8, len(positions), f"dates not in run termin ({language})"
                )
                self.assertEqual(list(range(positions[0], positions[0] + 8)), positions)
                rebalanced = [
                    n
                    for n, i in enumerate(positions)
                    if _as_bool(termin_rows[i].get("rebalanced", ""))
                ]
                self.assertEqual(
                    1, len(rebalanced), f"not exactly one date ({language})"
                )
                self.assertEqual(
                    rebalanced, marked, f"mark not on the date ({language})"
                )
                i_rebalanced = positions[rebalanced[0]]
                self.assertGreater(i_rebalanced, 0)
                self.assertEqual(
                    "1927-01-03",
                    termin_rows[i_rebalanced]["date"],
                    f"the table does not show the Saturday date 1927-01-01 "
                    f"({language})",
                )
                self.assertEqual(
                    5,
                    _parse_date(termin_rows[i_rebalanced - 1]["deadline"]).weekday(),
                    f"the shown date follows no deadline on a Saturday ({language})",
                )
                for row, i in zip(body, positions):
                    a = termin_rows[i]
                    for column, cell in zip(TABLE_REBALANCING[1:], row[1:]):
                        self.assertLessEqual(
                            abs(float(a[column]) - _number_from_cell(cell)),
                            0.005 + 1e-9,
                            f"{column} on {a['date']} not as displayed ({language})",
                        )

    def test_no_new_word_hits_outside_the_boxes(self) -> None:
        for language, text in self.texts.items():
            with self.subTest(language=language):
                outside = LAYER_BLOCK.sub("", text)
                base = WORDLIST_BASE_HFEA[f"hfea.{language}.md"]
                for word in BOX_WORDS:
                    count = len(_word_boundary(word).findall(outside))
                    self.assertLessEqual(count, base.get(word, 0), word)

    def test_check_frontmatter_green(self) -> None:
        run = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_frontmatter.py")],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(0, run.returncode, run.stdout + run.stderr)


class TestRebalancingPresetValues(unittest.TestCase):
    """BAU-5: weight, period and band equal to no preset, on the grid."""

    def test_values_equal_to_no_preset_and_on_the_grid(self) -> None:
        rows_input, _ = _load_rebalancing_rows()
        weights: set[float] = set()
        periods: set[int] = set()
        bands: set[float] = {10.0}
        for path in (
            ROOT / "content" / "strategies" / "hfea.de.md",
            ROOT / "registry" / "strategy_preset_slugs.json",
        ):
            for a, b, period, band in PRESET_HFEA.findall(
                path.read_text(encoding="utf-8")
            ):
                weights.update((float(a), float(b)))
                self.assertIn(period, PERIODS_PRESET, period)
                periods.add(PERIODS_PRESET[period])
                if band:
                    bands.add(float(band.replace(",", ".")))
        self.assertTrue(weights, "no presets in frontmatter or registry")
        for e in rows_input:
            weight = _as_float(e, "stock_weight_percent")
            period = _period(e)
            self.assertNotIn(weight, weights)
            # Run termin is quarterly (spec hfea-nachrechnen-kalender BAU-2).
            if e.get("rule") != "termin":
                self.assertNotIn(period, periods)
            self.assertTrue(30.0 <= weight <= 80.0 and weight % 5 == 0, weight)
            self.assertIn(period, (1, 3, 6, 12))
            if _is_number(e.get("band_percentage_points", "")):
                self.assertNotIn(_as_float(e, "band_percentage_points"), bands)


class TestEntryRebalancing(unittest.TestCase):
    """BAU-5: examples/README.md and llms.txt name the package with a purpose."""

    def test_readme_and_llms_name_the_package(self) -> None:
        for path in (EXAMPLES / "README.md", LLMS):
            with self.subTest(file=str(path.relative_to(ROOT))):
                text = path.read_text(encoding="utf-8")
                self.assertTrue(
                    f"{REBALANCING}/" in text or f"examples/{REBALANCING}" in text,
                    f"{path.name} does not name the package path",
                )
                sentences = [
                    s for s in re.split(r"(?<=[.!?])\s+|\n", text) if REBALANCING in s
                ]
                self.assertTrue(
                    any(len(s.split()) >= 5 for s in sentences),
                    f"{path.name} names the package without a purpose sentence",
                )


V5_ORDER = [
    "rule", "examples", "backtest", "parameters", "implementation",
    "staying-invested", "mistakes", "history", "tradeoffs", "criticism",
    "math", "recompute", "faq", "sources",
]
SMA_PAGES = ("sma-trend.de.md", "sma-trend.en.md")
FORUM_URLS = (
    "https://www.reddit.com/r/LETFs/",
    "https://www.reddit.com/r/mauerstrassenwetten/",
)


def _sma_page(name: str) -> str:
    return (ROOT / "content" / "strategies" / name).read_text(encoding="utf-8")


def _h2(text: str) -> list[str]:
    return re.findall(r"(?m)^##[ \t]+(\S.*?)[ \t]*$", text)


def _sources(text: str) -> list[dict]:
    import yaml

    lines = text.splitlines()
    end = lines.index("---", 1)
    return yaml.safe_load("\n".join(lines[1:end]))["sources"]


class TestStructureV5(unittest.TestCase):
    """Wave struktur-v5-inhalt: V5 chapter scheme on both SMA pages."""

    def test_h2_order_is_v5(self) -> None:
        for name in SMA_PAGES:
            with self.subTest(page=name):
                self.assertEqual(_h2(_sma_page(name)), V5_ORDER)

    def test_no_weiterlesen_one_recompute(self) -> None:
        for name in SMA_PAGES:
            with self.subTest(page=name):
                heads = _h2(_sma_page(name))
                self.assertEqual(heads.count("weiterlesen"), 0)
                self.assertEqual(heads.count("recompute"), 1)

    def test_recompute_intro_and_subsections(self) -> None:
        for name in SMA_PAGES:
            with self.subTest(page=name):
                body = _section(_sma_page(name), "recompute")
                first_h3 = re.search(r"(?m)^###[ \t]", body)
                first_box = re.search(r"(?m)^:::layer", body)
                self.assertIsNotNone(first_h3, "recompute has no H3")
                self.assertIsNone(first_box, "recompute still has a layer box")
                intro = body[: first_h3.start()]
                self.assertGreaterEqual(
                    len(intro.split()), 10, "recompute lacks an intro before the first H3"
                )
                h3 = re.findall(r"(?m)^###[ \t]+(\S.*?)[ \t]*$", body)
                # Wave strategie-nachrechnen-code: nine fixed H3, intro
                # without the quote box for agents.
                self.assertIsNone(re.search(r"(?m)^>", intro), "quote in the intro")
                self.assertIsNone(re.search(r"(?i)agent", intro), "agent in the intro")
                if name.endswith(".de.md"):
                    self.assertEqual(h3, RECOMPUTE_H3_DE)
                else:
                    self.assertEqual(h3, RECOMPUTE_H3_EN)

    def test_recompute_block_content(self) -> None:
        for name in SMA_PAGES:
            with self.subTest(page=name):
                body = _section(_sma_page(name), "recompute")
                self.assertIn(f"{BLOB}examples/sma-signal/README.md", body)
                # eight-day table: a markdown table with at least eight data rows
                rows = [
                    ln for ln in body.splitlines()
                    if ln.startswith("|") and not re.match(r"^\|[\s:|-]+\|$", ln)
                ]
                self.assertGreaterEqual(len(rows), 9, "eight-day table missing in recompute")
                # Wave strategie-nachrechnen-it: the formulas live in math now;
                # wave strategie-nachrechnen-code: pseudocode without LaTeX.
                for mark in ("$$", "\\frac", "\\begin", "\\leftarrow", "\\bigl"):
                    self.assertNotIn(mark, body, f"formula {mark} in recompute")
                self.assertRegex(body, r"(?m)^```text[ \t]*$", "no text block in recompute")

    def test_math_keeps_formula_condition_distribution(self) -> None:
        markers = {
            "sma-trend.de.md": ("Verteilung und Signale je Jahr", "Zwei Einschränkungen"),
            "sma-trend.en.md": ("Distribution and signals per year", "Two caveats"),
        }
        for name in SMA_PAGES:
            with self.subTest(page=name):
                body = _section(_sma_page(name), "math")
                self.assertIn(r"\mathrm{SMA}_n(t) = \frac{1}{n}", body)
                self.assertIn(r"\text{risk\_on}", body)
                for marker in markers[name]:
                    self.assertIn(marker, body)
                for target in _link_targets(body):
                    self.assertNotIn("examples/", target)

    def test_no_further_reading_forums_are_history_sources(self) -> None:
        for name in SMA_PAGES:
            with self.subTest(page=name):
                srcs = _sources(_sma_page(name))
                self.assertEqual(
                    [s["title"] for s in srcs if s.get("role") == "further_reading"], []
                )
                for url in FORUM_URLS:
                    hits = [s for s in srcs if s.get("url") == url]
                    self.assertEqual(len(hits), 1, url)
                    self.assertEqual(hits[0].get("role"), "source", url)
                    self.assertEqual(hits[0].get("supports"), ["history"], url)

    def test_chart_classes(self) -> None:
        for name in SMA_PAGES:
            with self.subTest(page=name):
                classes = re.findall(r"(?m)^:::chart\b[^\n]*\bclass=(\S+)", _sma_page(name))
                self.assertEqual(classes.count("rueckschau"), 0)
                self.assertEqual(classes.count("puls"), 0)
                self.assertEqual(classes.count("backtest"), 4)
                self.assertEqual(classes.count("pulse"), 1)


if __name__ == "__main__":
    unittest.main()
