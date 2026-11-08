#!/usr/bin/env python3
"""Creates the copy of the preset slugs from the registry export of finance_api.

The content repo holds no connection to the API. So that `check_frontmatter.py`
can check the `definition_ids` against the real presets anyway, a committed copy
of the pure slug list (`registry/strategy_preset_slugs.json`) lies here, created
from the committed export `strategy_presets.json` of the finance_api repo.

Copied is exclusively the mapping region -> slugs, plus the commit of the source
repo the list comes from. No parameters, no product names, no documents: the
copy is an allow list, not a second data stock.

Dependencies: standard library (git only for determining the commit).

Call:
    python scripts/sync_preset_slugs.py --export ../finance_api/strategy_presets.json

Exit code 0 when the copy was written or already up to date; 1 on an error
(export unreadable, commit not determinable, export uncommitted).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_EXPORT = REPO_ROOT.parent / "finance_api" / "strategy_presets.json"
DEFAULT_OUTPUT = REPO_ROOT / "registry" / "strategy_preset_slugs.json"

GENERATED_BY = "scripts/sync_preset_slugs.py"
SOURCE_REPO = "finance_api"


class SyncError(Exception):
    """The export cannot be translated into a slug list."""


def load_export(path: Path) -> dict[str, Any]:
    """Reads the export as a JSON object."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SyncError(f"export not readable: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SyncError(f"export is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SyncError("export must be a JSON object")
    return data


def build_document(export: dict[str, Any], *, source_commit: str, source_file: str) -> dict[str, Any]:
    """Builds the content of the slug copy from the export.

    Pure function without file access, so that it stays testable.
    """
    presets = export.get("presets")
    if not isinstance(presets, list) or not presets:
        raise SyncError("export contains no non-empty list 'presets'")

    by_region: dict[str, list[str]] = {}
    seen: dict[str, str] = {}
    for index, preset in enumerate(presets):
        if not isinstance(preset, dict):
            raise SyncError(f"presets[{index}] is not an object")
        slug = preset.get("slug")
        region = preset.get("region")
        if not isinstance(slug, str) or not slug:
            raise SyncError(f"presets[{index}] has no slug")
        if not isinstance(region, str) or not region:
            raise SyncError(f"presets[{index}] ('{slug}') has no region")
        if slug in seen:
            raise SyncError(f"slug '{slug}' occurs twice (regions '{seen[slug]}' and '{region}')")
        seen[slug] = region
        by_region.setdefault(region, []).append(slug)

    return {
        "generated_by": GENERATED_BY,
        "source": {
            "repo": SOURCE_REPO,
            "file": source_file,
            "commit": source_commit,
            "export_version": export.get("version"),
            "export_source": export.get("source"),
        },
        "slugs": {region: sorted(slugs) for region, slugs in sorted(by_region.items())},
    }


def _git(args: Sequence[str], cwd: Path) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as exc:
        raise SyncError("git is not available; pass the commit with --source-commit") from exc
    except subprocess.CalledProcessError as exc:
        raise SyncError(f"git {' '.join(args)} failed: {exc.stderr.strip()}") from exc
    return result.stdout.strip()


def resolve_source_commit(export_path: Path, *, allow_dirty: bool) -> str:
    """Determines the commit that last changed the export."""
    directory = export_path.parent
    name = export_path.name

    if not allow_dirty:
        dirty = _git(["status", "--porcelain", "--", name], cwd=directory)
        if dirty:
            raise SyncError(
                f"'{export_path}' is not committed in the source repo ({dirty.splitlines()[0].strip()}); "
                "the commit hash would claim a different state. Commit it there first "
                "or combine --allow-dirty with --source-commit."
            )

    commit = _git(["log", "-1", "--format=%H", "--", name], cwd=directory)
    if not commit:
        raise SyncError(f"no commit found that touches '{export_path}'")
    return commit


def write_document(document: dict[str, Any], output: Path) -> bool:
    """Writes the copy and reports whether anything changed."""
    text = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    if output.exists() and output.read_text(encoding="utf-8") == text:
        return False
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    return True


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Creates the copy of the preset slugs from the registry export.")
    parser.add_argument(
        "--export",
        type=Path,
        default=DEFAULT_EXPORT,
        help=f"path to the export of finance_api (default: {DEFAULT_EXPORT})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"target file in the content repo (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--source-commit",
        help="commit hash of the source repo instead of determining it via git",
    )
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="allow an uncommitted export (only useful together with --source-commit)",
    )
    args = parser.parse_args(argv)

    export_path = args.export.resolve()
    try:
        export = load_export(export_path)
        commit = args.source_commit or resolve_source_commit(export_path, allow_dirty=args.allow_dirty)
        document = build_document(export, source_commit=commit, source_file=export_path.name)
    except SyncError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1

    changed = write_document(document, args.output)
    count = sum(len(slugs) for slugs in document["slugs"].values())
    regions = ", ".join(f"{region}: {len(slugs)}" for region, slugs in document["slugs"].items())
    state = "written" if changed else "unchanged"
    print(f"{args.output} {state}: {count} slugs ({regions}), source commit {commit[:12]}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
