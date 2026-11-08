"""Acceptance of the wave heal-hfea-korpus-abgleich: the Markdown lint of the CI is green.

The lint itself (`npx --yes markdownlint-cli2@0.14.0`) runs in the CI as its own
step. These tests rebuild the rules it was red with on main in Python, so that
`python3 -m unittest discover -s tests` finds the same spots without Node:

- MD013 with `line_length` 120 and (after the wave) `heading_line_length` 120: a
  line is too long when whitespace still stands behind column 120; tables and
  code blocks are excluded, frontmatter as well.
- MD009 (whitespace at the end of the line), MD012 (several blank lines), MD022
  (blank line around headings), MD031 (blank line around code blocks), MD040
  (language on the code block), MD047 (file ends with exactly one line break).

Plus the guard rails of the spec: the configuration differs from main only by
`heading_line_length`, no `markdownlint-disable` comments, headings and wording
stay the same (comparison against the base commit of the wave, only while main
still stands there), and the frontmatter script ends with exit 0.

The guard rail against muting knows exactly one exception since
strategies-md038 (spec version 2, BAU-3): `docs/frontmatter-schema.md` may turn
MD038 off at the spots with spaces in code spans, and only with the two exact
comment lines `<!-- markdownlint-disable MD038 -->` and
`<!-- markdownlint-enable MD038 -->`. Everything else stays forbidden.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / ".markdownlint-cli2.jsonc"
LIMIT = 120
# Base commit of the wave heal-hfea-korpus-abgleich; the comparisons on unchanged
# wording, headings and configuration only hold against this state.
BASE = "cff60655c15c45765f666de49599f5b756d5c489"

# All Markdown files the lint checks in the CI (`**/*.md` without node_modules).
MD_FILES = sorted(
    p
    for p in ROOT.rglob("*.md")
    if "node_modules" not in p.parts and ".claude" not in p.relative_to(ROOT).parts
)

FENCE = re.compile(r"^(\s*)(`{3,}|~{3,})(.*)$")
LIST = re.compile(r"^\s{0,3}(?:[-*+]|(\d{1,9})[.)])(?:\s|$)")
HEADING = re.compile(r"^#{1,6}(?:\s|$)")
# Default of MD026 `punctuation`; the question mark of the FAQ is allowed.
MD026_CHARS = ".,;:!。，；：！"


def _without_comments(jsonc: str) -> str:
    """Removes `//` line comments outside of strings."""
    out = []
    for line in jsonc.splitlines():
        in_string = False
        i = 0
        while i < len(line):
            c = line[i]
            if c == '"' and (i == 0 or line[i - 1] != "\\"):
                in_string = not in_string
            elif not in_string and line.startswith("//", i):
                line = line[:i]
                break
            i += 1
        out.append(line)
    return "\n".join(out)


def _load_config(text: str) -> dict:
    return json.loads(_without_comments(text))


def _git(*arguments: str) -> str | None:
    if shutil.which("git") is None:
        return None
    run = subprocess.run(["git", *arguments], cwd=ROOT, capture_output=True, text=True)
    return run.stdout if run.returncode == 0 else None


def _base_applies() -> bool:
    """True as long as main still stands on the base commit of the wave."""
    main = _git("rev-parse", "--verify", "--quiet", "main^{commit}")
    return main is not None and main.strip() == BASE


def _git_base(path: str) -> str | None:
    return _git("show", f"{BASE}:{path}")


def _lines_with_kind(text: str) -> list[tuple[int, str, str]]:
    """(line number, line, kind) with kind in frontmatter, fence, code, text."""
    lines = text.split("\n")
    if text.endswith("\n"):
        lines = lines[:-1]
    out: list[tuple[int, str, str]] = []
    i = 0
    if lines and lines[0] == "---":
        out.append((1, lines[0], "frontmatter"))
        i = 1
        while i < len(lines):
            out.append((i + 1, lines[i], "frontmatter"))
            i += 1
            if lines[i - 1] == "---":
                break
    open_fence: str | None = None
    while i < len(lines):
        line = lines[i]
        m = FENCE.match(line)
        if open_fence is None and m:
            open_fence = m.group(2)
            out.append((i + 1, line, "fence_open"))
        elif (
            open_fence is not None
            and m
            and m.group(2).startswith(open_fence[0])
            and len(m.group(2)) >= len(open_fence)
            and not m.group(3).strip()
        ):
            open_fence = None
            out.append((i + 1, line, "fence_close"))
        elif open_fence is not None:
            out.append((i + 1, line, "code"))
        else:
            out.append((i + 1, line, "text"))
        i += 1
    return out


def _too_long(line: str) -> bool:
    """MD013 not strict: too long only when whitespace stands behind column 120."""
    return len(line) > LIMIT and re.search(r"\s", line[LIMIT:]) is not None


def _is_table(line: str) -> bool:
    return line.lstrip().startswith("|")


def findings(text: str) -> list[str]:
    """Findings in the format `line: rule description`."""
    out: list[str] = []
    lines = _lines_with_kind(text)
    blank_streak = 0
    for idx, (number, line, kind) in enumerate(lines):
        before = lines[idx - 1] if idx > 0 else None
        after = lines[idx + 1] if idx + 1 < len(lines) else None
        if kind == "text":
            if not _is_table(line) and _too_long(line):
                out.append(f"{number}: MD013 line length {len(line)}")
            if line != line.rstrip():
                rest = len(line) - len(line.rstrip(" "))
                if "\t" in line[len(line.rstrip()) :] or rest != 2 or not line.strip():
                    out.append(f"{number}: MD009 trailing whitespace")
            if not line.strip():
                blank_streak += 1
                if blank_streak == 2:
                    out.append(f"{number}: MD012 several blank lines")
            else:
                blank_streak = 0
            if HEADING.match(line):
                end = line.rstrip().rstrip("#").rstrip()[-1:]
                if end and end in MD026_CHARS:
                    out.append(f"{number}: MD026 punctuation at end of heading")
                if before is not None and before[1].strip() and before[2] != "frontmatter":
                    out.append(f"{number}: MD022 no blank line before heading")
                if after is not None and after[1].strip():
                    out.append(f"{number}: MD022 no blank line after heading")
            m = LIST.match(line)
            if m and (m.group(1) is None or m.group(1) == "1") and before is not None:
                b_number, b_line, b_kind = before
                if (
                    b_kind == "text"
                    and b_line.strip()
                    and not LIST.match(b_line)
                    and not b_line.startswith((" ", "\t"))
                    and not HEADING.match(b_line)
                    and not _is_table(b_line)
                    and not line.startswith((" ", "\t"))
                ):
                    out.append(f"{number}: MD032 no blank line before list")
        else:
            blank_streak = 0
        if kind == "fence_open":
            if not FENCE.match(line).group(3).strip():
                out.append(f"{number}: MD040 code block without language")
            if before is not None and before[1].strip() and before[2] != "frontmatter":
                out.append(f"{number}: MD031 no blank line before code block")
        if kind == "fence_close" and after is not None and after[1].strip():
            out.append(f"{number}: MD031 no blank line after code block")
    if text and not text.endswith("\n"):
        out.append(f"{len(lines)}: MD047 end of file")
    return out


def _words(text: str) -> list[str]:
    """Word sequence without fence languages; wrapping and whitespace do not matter."""
    lines = []
    for line in text.split("\n"):
        m = FENCE.match(line)
        lines.append(m.group(1) + m.group(2) if m else line)
    return "\n".join(lines).split()


# BAU-3 (wave strategies-md038, spec version 2): only in this one file, and there
# only these two exact lines. Every other file stays free of them.
MD038_FILE = "docs/frontmatter-schema.md"
MD038_COMMENTS = (
    "<!-- markdownlint-disable MD038 -->",
    "<!-- markdownlint-enable MD038 -->",
)


def mute_findings(rel: str, text: str) -> list[str]:
    """Findings of the guard rail against muting, one line per finding.

    Outside `docs/frontmatter-schema.md` every `markdownlint-disable` is
    forbidden. In this file only the two exact MD038 lines are allowed; every
    other comment with `markdownlint-` is a finding, and every disable is
    followed by an enable.
    """
    if rel != MD038_FILE:
        if "markdownlint-disable" in text:
            return ["markdownlint-disable in the text"]
        return []
    out: list[str] = []
    sequence: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), 1):
        if "markdownlint-" not in line:
            continue
        if line.strip() not in MD038_COMMENTS:
            out.append(f"{number}: forbidden comment {line.strip()!r}")
            continue
        sequence.append((number, "disable" if "disable" in line else "enable"))
    for i, (number, kind) in enumerate(sequence):
        if kind == "disable" and not any(a == "enable" for _, a in sequence[i + 1 :]):
            out.append(f"{number}: markdownlint-disable without a following enable")
    return out


class SelfCheckTest(unittest.TestCase):
    """The rebuild recognizes what it is supposed to recognize."""

    def test_long_line_with_whitespace_behind_column_120(self) -> None:
        self.assertTrue(_too_long("a" * 119 + " b c"))
        self.assertFalse(_too_long("a" * 120 + "bbbbb"))
        self.assertFalse(_too_long("a" * 119 + " " + "b" * 30))

    def test_code_block_and_table_are_excluded(self) -> None:
        word = "wort " * 30
        text = f"# T\n\n```text\n{word}\n```\n\n| {word} |\n"
        self.assertEqual([b for b in findings(text) if "MD013" in b], [])
        self.assertTrue(any("MD013" in b for b in findings(f"# T\n\n{word}\n")))

    def test_more_rules(self) -> None:
        self.assertIn("3: MD040 code block without language", findings("# T\n\n```\nx\n```\n"))
        self.assertIn(
            "4: MD031 no blank line before code block", findings("# T\n\nText\n```text\nx\n```\n")
        )
        self.assertIn(
            "5: MD031 no blank line after code block", findings("# T\n\n```text\nx\n```\nText\n")
        )
        self.assertEqual(findings("# T\n\nText\n\n```text\nx\n```\n\nText\n"), [])
        self.assertIn("5: MD012 several blank lines", findings("# T\n\nText\n\n\nText\n"))
        self.assertIn("3: MD009 trailing whitespace", findings("# T\n\nText \n"))
        self.assertIn("4: MD032 no blank line before list", findings("# T\n\nText\n- a\n"))
        self.assertIn("1: MD047 end of file", findings("# T"))
        self.assertIn("1: MD026 punctuation at end of heading", findings("# T.\n"))
        self.assertEqual(findings("# T?\n"), [])

    def test_muting_only_as_md038_region(self) -> None:
        """BAU-3: the guard rail is green only for the two MD038 lines."""
        region = (
            "<!-- markdownlint-disable MD038 -->\n"
            "Zeile `  - aktien`\n"
            "<!-- markdownlint-enable MD038 -->\n"
        )
        self.assertEqual(mute_findings(MD038_FILE, region), [])
        # One disable without rule and one with another rule make the guard
        # rail red (BAU-3).
        for comment in (
            "<!-- markdownlint-disable -->",
            "<!-- markdownlint-disable MD013 -->",
            "<!-- markdownlint-disable-file MD038 -->",
            "<!-- markdownlint-disable-next-line MD038 -->",
            "<!-- markdownlint-configure-file -->",
        ):
            with self.subTest(comment=comment):
                self.assertTrue(
                    mute_findings(MD038_FILE, f"{comment}\nZeile\n"),
                    f"{comment} must make the guard rail red",
                )
        # Every disable is followed by an enable.
        self.assertTrue(
            mute_findings(MD038_FILE, "<!-- markdownlint-disable MD038 -->\nZeile\n")
        )
        # In every other file every disable stays forbidden.
        self.assertTrue(mute_findings("README.md", "<!-- markdownlint-disable MD038 -->\n"))


class ConfigurationTest(unittest.TestCase):
    """`.markdownlint-cli2.jsonc` changes only by `heading_line_length` 120."""

    def test_heading_limit_equals_line_limit(self) -> None:
        md013 = _load_config(CONFIG.read_text(encoding="utf-8"))["config"]["MD013"]
        self.assertEqual(md013.get("heading_line_length"), LIMIT)
        self.assertEqual(md013.get("line_length"), LIMIT)

    def test_everything_else_as_on_the_base(self) -> None:
        if not _base_applies():
            self.skipTest(f"main no longer stands on the base {BASE[:8]} of the wave")
        old = _load_config(_git_base(".markdownlint-cli2.jsonc"))
        new = _load_config(CONFIG.read_text(encoding="utf-8"))
        # Allowed are exactly two changes: MD013.heading_line_length 120 and
        # MD026.punctuation without period (spec version 4).
        self.assertEqual(new["config"]["MD013"].pop("heading_line_length", None), LIMIT)
        old["config"]["MD013"].pop("heading_line_length", None)
        md026_old = old["config"].pop("MD026", {})
        self.assertEqual(
            new["config"].pop("MD026", None), {**md026_old, "punctuation": ",;:!。，；：！"}
        )
        self.assertEqual(new, old)

    def test_no_muting_in_the_text(self) -> None:
        """BAU-3: only the MD038 regions in `docs/frontmatter-schema.md`.

        In all other `.md` files every `markdownlint-disable` stays forbidden;
        in this file only the two exact MD038 lines are allowed, and every
        disable is followed by an enable.
        """
        for path in MD_FILES:
            with self.subTest(file=str(path.relative_to(ROOT))):
                reports = mute_findings(
                    path.relative_to(ROOT).as_posix(), path.read_text(encoding="utf-8")
                )
                self.assertEqual(reports, [])


class LintTest(unittest.TestCase):
    """Every Markdown file of the lint is free of findings in the rebuild."""

    def test_no_findings(self) -> None:
        # MD026 with the characters from the configuration of the worktree (the
        # key missing means the default); `findings` checks MD026 with the
        # default, so its MD026 findings are replaced here by the check against
        # the configuration.
        md026 = _load_config(CONFIG.read_text(encoding="utf-8"))["config"].get("MD026", {})
        chars = md026.get("punctuation", MD026_CHARS) if isinstance(md026, dict) else MD026_CHARS
        for path in MD_FILES:
            with self.subTest(file=str(path.relative_to(ROOT))):
                text = path.read_text(encoding="utf-8")
                found = [b for b in findings(text) if " MD026 " not in b]
                for number, line, kind in _lines_with_kind(text):
                    if kind == "text" and HEADING.match(line):
                        end = line.rstrip().rstrip("#").rstrip()[-1:]
                        if end and end in chars:
                            found.append(f"{number}: MD026 punctuation at end of heading")
                self.assertEqual(found, [])

    def test_localized_spots_are_wrapped(self) -> None:
        """The 15 spots of the localization: no prose over 120 characters."""
        files = [
            "content/strategies/hfea.de.md",
            "content/strategies/hfea.en.md",
            "content/strategies/sma-trend.de.md",
            "content/strategies/sma-trend.en.md",
            "examples/sma-signal/README.md",
            "examples/leverage-model/README.md",
            "examples/rebalancing/README.md",
        ]
        for rel in files:
            text = (ROOT / rel).read_text(encoding="utf-8")
            for number, line, kind in _lines_with_kind(text):
                if kind != "text" or _is_table(line) or HEADING.match(line):
                    continue
                with self.subTest(file=rel, line=number):
                    self.assertFalse(_too_long(line), line[:80])


def _headings(text: str) -> list[str]:
    return [z for _, z, kind in _lines_with_kind(text) if kind == "text" and HEADING.match(z)]


def _long_over_80(line: str) -> bool:
    return len(line) > 80 and re.search(r"\s", line[80:]) is not None


class UnchangedTest(unittest.TestCase):
    """Only wrapping, whitespace and fence languages change, never words or headings.

    Acceptance of this wave against its base commit; only holds while main still
    stands there, so later content waves do not fail on this comparison.
    """

    def setUp(self) -> None:
        if not _base_applies():
            self.skipTest(f"main no longer stands on the base {BASE[:8]} of the wave")

    def _pairs(self):
        for path in MD_FILES:
            rel = path.relative_to(ROOT).as_posix()
            old = _git_base(rel)
            if old is None:
                continue
            yield rel, old, path.read_text(encoding="utf-8")

    def test_wording_same(self) -> None:
        for rel, old, new in self._pairs():
            with self.subTest(file=rel):
                self.assertEqual(_words(new), _words(old))

    def test_headings_same(self) -> None:
        for rel, old, new in self._pairs():
            with self.subTest(file=rel):
                self.assertEqual(_headings(new), _headings(old))

    def test_long_headings_stay(self) -> None:
        """The 9 headings over 80 characters of the base stand unchanged."""
        # Counted like the grep of the spec (`^#.{81,}`): only the length, not
        # the whitespace behind column 80; by that criterion it would be 5.
        long_old: list[str] = []
        long_new: list[str] = []
        for _, old, new in self._pairs():
            long_old += [z for z in _headings(old) if re.match(r"^#.{81,}", z)]
            long_new += [z for z in _headings(new) if re.match(r"^#.{81,}", z)]
        self.assertEqual(len(long_old), 9)
        self.assertEqual(long_new, long_old)


class FrontmatterScriptTest(unittest.TestCase):
    def test_exit_zero(self) -> None:
        run = subprocess.run(
            [sys.executable, "scripts/check_frontmatter.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)


if __name__ == "__main__":
    unittest.main()
