"""Tests for scripts/sync_preset_slugs.py (standard library, unittest)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_frontmatter as cf  # noqa: E402
import sync_preset_slugs as sync  # noqa: E402

COMMIT = "a" * 40

EXPORT = {
    "version": 1,
    "source": "alerts/strategies.py TRACKER_PRESETS",
    "presets": [
        {"slug": "SMA__SPX__GRTR__200__B0__US74347X8645", "region": "us", "kind": "sma"},
        {"slug": "HFEA__55_45__QUARTERLY__BANDS5__XS2595672036", "region": "eu", "kind": "hfea"},
        {"slug": "SMA__MSCI_USA__NETR__200__B0__FR0010755611", "region": "eu", "kind": "sma"},
    ],
}


def build(export: dict[str, object] = EXPORT) -> dict[str, object]:
    return sync.build_document(export, source_commit=COMMIT, source_file="strategy_presets.json")


class BuildDocumentTestCase(unittest.TestCase):
    def test_slugs_grouped_by_region_and_sorted(self) -> None:
        document = build()
        self.assertEqual(
            document["slugs"],
            {
                "eu": [
                    "HFEA__55_45__QUARTERLY__BANDS5__XS2595672036",
                    "SMA__MSCI_USA__NETR__200__B0__FR0010755611",
                ],
                "us": ["SMA__SPX__GRTR__200__B0__US74347X8645"],
            },
        )

    def test_source_block_carries_commit_and_export_metadata(self) -> None:
        source = build()["source"]
        self.assertEqual(source["repo"], "finance_api")
        self.assertEqual(source["file"], "strategy_presets.json")
        self.assertEqual(source["commit"], COMMIT)
        self.assertEqual(source["export_version"], 1)
        self.assertEqual(source["export_source"], "alerts/strategies.py TRACKER_PRESETS")

    def test_only_slugs_are_copied(self) -> None:
        """No parameters, no product names, no documents."""
        document = build(
            {
                "version": 1,
                "presets": [
                    {
                        "slug": "SMA__SPX__GRTR__200__B0__US74347X8645",
                        "region": "us",
                        "product_name": "Irgendein Produkt",
                        "document": {"nodes": []},
                        "v2_batch_parameters": {"sma_length": 200},
                    }
                ],
            }
        )
        self.assertEqual(sorted(document), ["generated_by", "slugs", "source"])
        dumped = json.dumps(document)
        for leaked in ("product_name", "Irgendein Produkt", "document", "sma_length"):
            self.assertNotIn(leaked, dumped)

    def test_empty_presets_is_error(self) -> None:
        with self.assertRaises(sync.SyncError):
            build({"version": 1, "presets": []})

    def test_preset_without_slug_is_error(self) -> None:
        with self.assertRaises(sync.SyncError):
            build({"presets": [{"region": "eu"}]})

    def test_preset_without_region_is_error(self) -> None:
        with self.assertRaises(sync.SyncError):
            build({"presets": [{"slug": "SMA__SPX__GRTR__200__B0__US74347X8645"}]})

    def test_duplicate_slug_is_error(self) -> None:
        with self.assertRaises(sync.SyncError):
            build(
                {
                    "presets": [
                        {"slug": "SMA__SPX__GRTR__200__B0__US74347X8645", "region": "us"},
                        {"slug": "SMA__SPX__GRTR__200__B0__US74347X8645", "region": "eu"},
                    ]
                }
            )


class LoadExportTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)

    def test_missing_export_is_error(self) -> None:
        with self.assertRaises(sync.SyncError):
            sync.load_export(self.directory / "gibtsnicht.json")

    def test_broken_export_is_error(self) -> None:
        path = self.directory / "kaputt.json"
        path.write_text("{nicht json", encoding="utf-8")
        with self.assertRaises(sync.SyncError):
            sync.load_export(path)


class WriteDocumentTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.output = Path(self._tmp.name) / "registry" / "strategy_preset_slugs.json"

    def test_write_then_rewrite_is_idempotent(self) -> None:
        document = build()
        self.assertTrue(sync.write_document(document, self.output))
        self.assertFalse(sync.write_document(document, self.output))

    def test_written_file_is_readable_by_the_checker(self) -> None:
        sync.write_document(build(), self.output)
        registry = cf.SlugRegistry.load(self.output)
        self.assertEqual(registry.source_commit, COMMIT)
        self.assertEqual(registry.region_of("SMA__SPX__GRTR__200__B0__US74347X8645"), "us")
        self.assertIsNone(registry.region_of("SMA__SPX__GRTR__200__B0"))


class CommittedCopyTestCase(unittest.TestCase):
    """The committed copy must match what the checker expects."""

    def test_committed_copy_has_the_generated_shape(self) -> None:
        document = json.loads(cf.DEFAULT_REGISTRY.read_text(encoding="utf-8"))
        self.assertEqual(document["generated_by"], sync.GENERATED_BY)
        self.assertEqual(document["source"]["repo"], sync.SOURCE_REPO)
        self.assertEqual(len(document["source"]["commit"]), 40)
        for region, slugs in document["slugs"].items():
            self.assertRegex(region, r"^[a-z]{2}$")
            self.assertEqual(slugs, sorted(slugs))
            self.assertEqual(len(slugs), len(set(slugs)))


if __name__ == "__main__":
    unittest.main()
