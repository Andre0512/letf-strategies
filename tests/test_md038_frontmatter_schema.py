"""Acceptance of wave strategies-md038: the last MD038 findings are fixed.

`docs/frontmatter-schema.md` describes the exact spelling of a few spots:
the label with its trailing space, the list indent in the block list. The
code spans therefore carry spaces at their edges, and MD038 (no-space-in-code)
flags them for a reason. BAU-1 turns MD038 off only for these spots, without
changing the spans.

These tests cover section 4 (acceptance) and BAU-2 of the spec:

- Acceptance 1: `npx --yes markdownlint-cli2@0.14.0 docs/frontmatter-schema.md`
  reports zero findings. Without npx in the run, the main session checks this
  before the push.
- Acceptance 2: the code spans are character-for-character the same as on
  `cff60655`, except the changes that ALLOWED_SPAN_CHANGES names for them.
- Acceptance 3: the gates of the `strategies` target are green. The test gate
  itself (`python -m unittest discover -s tests`) calls this file along the way
  and cannot call itself, so the runner computes it afterwards; here run the
  two CI runs that a test can carry.
- BAU-2: the code spans from the basis lines 71 and 256 to 262 stand unchanged
  in the file, and every line with a span with leading or trailing space lies
  between a disable and an enable comment for MD038. The table for that
  (BASIS_SPANS) is checked by its own test against the basis commit, so it is
  not guessed.

Fence blocks and HTML comments carry no code spans; the span over two lines
("### Einstieg ... erste Schritte") stays a span and does not count among
those with spaces at the edges.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILE = "docs/frontmatter-schema.md"
# Acceptance 2 names this basis commit of the wave; on it stand the spans with
# the line numbers 71 and 256 to 262 that BAU-2 points to.
BASIS = "cff60655"
LINT = "markdownlint-cli2@0.14.0"

# The 15 code spans with spaces at the edges: line 71 and 256 to 262 of the basis.
# Their spelling is the content of the schema and must not change.
BASIS_SPANS = [
    (71, "  - aktien"),
    (256, "**<Richtung>:** "),
    (257, "**Länger:** "),
    (257, "**Kürzer:** "),
    (257, "**Größer:** "),
    (258, "**Kleiner:** "),
    (258, "**Mehr:** "),
    (258, "**Weniger:** "),
    (258, "**Höher:** "),
    (259, "**Niedriger:** "),
    (259, "**Breiter:** "),
    (259, "**Enger:** "),
    (260, "**Nur Termin:** "),
    (262, "**Was es kostet:** "),
    (262, "**Was es spart:** "),
]

# Acceptance 2 since wave strategies-repo-englisch (BAU-4): every change that
# the translation brings to a span of the basis, basis spelling to the expected
# new one. Exactly one changes: the placeholder {LÄNGE} in the slug format.
# Technical spans (keys, values, `class=` and `type=` values, paths, `:::`
# lines, the prefix strings of BAU-2, the fifteen entries of BASIS_SPANS) stay
# out of this list and must stand verbatim.
ALLOWED_SPAN_CHANGES: dict[str, str] = {
    "SMA__{INDEX}__{LEVEL}__{LÄNGE}__B{PUFFER_BPS}__{ISIN}":
        "SMA__{INDEX}__{LEVEL}__{LENGTH}__B{PUFFER_BPS}__{ISIN}",
}

FENCE = re.compile(r"^(\s*)(`{3,}|~{3,})(.*)$")
SPAN = re.compile(r"(`+)(.+?)\1", re.DOTALL)
# Region forms with a rule name; `disable-file` and `disable-line` are none of
# these (BAU-1: only the affected spots, never the whole file).
MUTE = re.compile(r"<!--\s*markdownlint-(disable|enable)(?!-)([^>]*?)-->")


def _without_comments(lines: list[str]) -> list[str]:
    """The lines without HTML comments; the line numbers stay."""
    out: list[str] = []
    in_comment = False
    for line in lines:
        if in_comment:
            end = line.find("-->")
            if end == -1:
                out.append("")
                continue
            line = line[end + 3 :]
            in_comment = False
        while True:
            start = line.find("<!--")
            if start == -1:
                break
            end = line.find("-->", start)
            if end == -1:
                line = line[:start]
                in_comment = True
                break
            line = line[:start] + line[end + 3 :]
        out.append(line)
    return out


def _without_fences(lines: list[str]) -> list[str]:
    """The lines without fence blocks; the line numbers stay."""
    out: list[str] = []
    fence: str | None = None
    for line in lines:
        m = FENCE.match(line)
        if fence is not None:
            if m and m.group(2)[0] == fence[0] and len(m.group(2)) >= len(fence) and not m.group(3).strip():
                fence = None
            out.append("")
        elif m:
            fence = m.group(2)
            out.append("")
        else:
            out.append(line)
    return out


def _spans(text: str) -> list[tuple[int, str]]:
    """(Line number of the start, content) per inline code span."""
    total = "\n".join(_without_fences(_without_comments(text.splitlines())))
    out: list[tuple[int, str]] = []
    for hit in SPAN.finditer(total):
        nr = total[: hit.start(2)].count("\n") + 1
        out.append((nr, hit.group(2)))
    return out


def _edge_spans(text: str) -> list[tuple[int, str]]:
    """The spans MD038 reports: with leading or trailing space."""
    return [(nr, content) for nr, content in _spans(text) if content != content.strip()]


def _unmatched_spans(basis: str, current: str, allowed: dict[str, str]) -> list[str]:
    """The spans of the basis that do not stand in `current`, in order.

    A span of the basis counts as standing when `current` carries it
    character-for-character or, when `allowed` names it, exactly in its new
    spelling. Every span has to find its content in the order of the basis;
    new spans of later waves may stand between them, and a missing span does
    not drag the ones after it into the report. A change that `allowed` does
    not name is therefore reported on its own.
    """
    contents = [content for _, content in _spans(current)]
    out: list[str] = []
    cursor = 0
    for _, content in _spans(basis):
        expected = allowed.get(content, content)
        for position in range(cursor, len(contents)):
            if contents[position] == expected:
                cursor = position + 1
                break
        else:
            out.append(content)
    return out


def _muted(lines: list[str], nr: int) -> bool:
    """True when MD038 is off from line `nr` through the last directive before it."""
    state = False
    for line in lines[: nr - 1]:
        m = MUTE.search(line)
        if m and "MD038" in m.group(2):
            state = m.group(1) == "disable"
    return state


def _re_enabled(lines: list[str], nr: int) -> bool:
    """True when MD038 is switched on again after line `nr`.

    Together with _muted that means: the line lies between a disable and an
    enable comment for MD038.
    """
    for line in lines[nr:]:
        m = MUTE.search(line)
        if m and "MD038" in m.group(2) and m.group(1) == "enable":
            return True
    return False


def _git(*arguments: str) -> str | None:
    if shutil.which("git") is None:
        return None
    run = subprocess.run(["git", *arguments], cwd=ROOT, capture_output=True, text=True)
    return run.stdout if run.returncode == 0 else None


class SelfCheckTest(unittest.TestCase):
    """The detection detects what it is meant to detect."""

    def test_spans_ignore_fences_and_comments(self) -> None:
        text = (
            "Text `  - aktien` und mehr\n"
            "```\n"
            "`  - im zaun`\n"
            "```\n"
            "<!-- `  - im kommentar` -->\n"
            "`### Einstieg\n"
            "und ende`\n"
        )
        self.assertEqual(_edge_spans(text), [(1, "  - aktien")])
        self.assertIn((6, "### Einstieg\nund ende"), _spans(text))

    def test_muted_knows_the_regions(self) -> None:
        lines = [
            "<!-- markdownlint-disable MD038 -->",
            "Zeile `  - aktien`",
            "<!-- markdownlint-enable MD038 -->",
            "Zeile `  - frei`",
            "<!-- markdownlint-disable MD038 -->",
            "Zeile `  - wieder`",
            "<!-- markdownlint-enable MD038 -->",
            "Zeile `  - danach`",
        ]
        self.assertTrue(_muted(lines, 2))
        self.assertFalse(_muted(lines, 4))
        self.assertTrue(_muted(lines, 6))
        self.assertFalse(_muted(lines, 8))

    def test_re_enabled_knows_the_regions(self) -> None:
        lines = [
            "<!-- markdownlint-disable MD038 -->",
            "Zeile `  - aktien`",
            "<!-- markdownlint-enable MD038 -->",
            "Zeile `  - frei`",
            "<!-- markdownlint-disable MD038 -->",
            "Zeile `  - wieder`",
        ]
        # Line 2 lies in a closed region, line 6 in an open one: muted, but
        # never switched on again.
        self.assertTrue(_re_enabled(lines, 2))
        self.assertTrue(_muted(lines, 6))
        self.assertFalse(_re_enabled(lines, 6))

    def test_unlisted_change_is_reported(self) -> None:
        """A changed span that ALLOWED_SPAN_CHANGES does not name turns the
        acceptance red; the same change listed is accepted."""
        basis = "The chapter `rueckschau` shows the backtest, the class `puls` the rule.\n"
        current = "The chapter `review` shows the backtest, the class `puls` the rule.\n"
        self.assertEqual(_unmatched_spans(basis, current, ALLOWED_SPAN_CHANGES), ["rueckschau"])
        self.assertEqual(_unmatched_spans(basis, current, {"rueckschau": "review"}), [])


class AcceptanceTest(unittest.TestCase):
    """Section 4 (acceptance) and BAU-2 of the spec."""

    def setUp(self) -> None:
        self.text = (ROOT / FILE).read_text(encoding="utf-8")
        self.lines = self.text.splitlines()

    def test_markdownlint_reports_no_findings(self) -> None:
        """Acceptance 1: the CI lint reports no finding for the file."""
        if shutil.which("npx") is None:
            self.skipTest("npx missing in the run; the main session checks before the push")
        run = subprocess.run(
            ["npx", "--yes", LINT, FILE],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_code_spans_verbatim_as_on_cff60655(self) -> None:
        """Acceptance 2: every code span of the basis stands verbatim in the
        file, or a change listed in ALLOWED_SPAN_CHANGES stands exactly in its
        new spelling."""
        basis = _git("show", f"{BASIS}:{FILE}")
        if basis is None:
            self.skipTest(f"basis commit {BASIS} is not readable in the run")
        # Every span of the basis stands in the same order and verbatim still
        # there; new spans from later waves (like `longterm`) are allowed.
        self.assertEqual(_unmatched_spans(basis, self.text, ALLOWED_SPAN_CHANGES), [])
        # A listed change stands in its new spelling: the old one is gone.
        current_spans = [content for _, content in _spans(self.text)]
        stale = [old for old in ALLOWED_SPAN_CHANGES if old in current_spans]
        self.assertEqual(stale, [], "an allowed change stands with its old spelling again")

    def test_basis_spans_sit_on_the_basis_lines(self) -> None:
        """BAU-2 points to the basis lines 71 and 256 to 262: the table
        BASIS_SPANS must show exactly these lines and contents."""
        basis = _git("show", f"{BASIS}:{FILE}")
        if basis is None:
            self.skipTest(f"basis commit {BASIS} is not readable in the run")
        self.assertEqual(_edge_spans(basis), BASIS_SPANS)

    def test_basis_lines_unchanged_and_affected_lines_muted(self) -> None:
        """BAU-2: the spans of the basis lines 71 and 256 to 262 stand
        unchanged in the file, and every line with a span with leading or
        trailing space lies between disable and enable for MD038."""
        edge = _edge_spans(self.text)
        self.assertEqual(
            [content for _, content in edge],
            [content for _, content in BASIS_SPANS],
            "the spans with spaces at the edges are no longer those of the basis",
        )
        for nr, content in edge:
            with self.subTest(line=nr, span=content):
                self.assertTrue(
                    _muted(self.lines, nr),
                    f"line {nr} with {content!r} does not lie under "
                    "a markdownlint-disable for MD038",
                )
                self.assertTrue(
                    _re_enabled(self.lines, nr),
                    f"line {nr} with {content!r} does not lie before "
                    "a markdownlint-enable for MD038",
                )

    def test_muting_only_at_the_affected_places(self) -> None:
        """BAU-1: MD038 is not switched off in the whole file."""
        free = [
            nr
            for nr, line in enumerate(self.lines, 1)
            if line.strip() and not _muted(self.lines, nr)
        ]
        self.assertTrue(free, "MD038 is switched off in the whole file")


class GatesTest(unittest.TestCase):
    """Acceptance 3: the gates of the target, as far as a test can carry them.

    The test gate (`python -m unittest discover -s tests`) calls this file along
    the way and cannot call itself; the runner computes it afterwards.
    """

    def test_frontmatter_check_with_zero(self) -> None:
        run = subprocess.run(
            [sys.executable, "scripts/check_frontmatter.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_markdown_lint_as_in_ci(self) -> None:
        if shutil.which("npx") is None:
            self.skipTest("npx missing in the run; the main session checks before the push")
        run = subprocess.run(
            ["npx", "--yes", LINT],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)


if __name__ == "__main__":
    unittest.main()
