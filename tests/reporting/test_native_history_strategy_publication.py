"""Verify exact staging of the lesson and the saved 30-profile comparison."""

import importlib
import json
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
stage = importlib.import_module("stage_native_history_strategies")
presentation = importlib.import_module("audit_mathematical_presentation")


class PageLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.paths: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for key, value in attrs:
            if key in {"href", "src"} and value:
                link = urlsplit(value)
                if not link.scheme and not link.netloc and link.path:
                    self.paths.append(link.path)


class NativeHistoryPublicationTests(unittest.TestCase):
    def test_verified_archive_exposes_only_lesson_assets_and_compact_coverage(self) -> None:
        files, [entry], card = stage.build(ROOT)
        self.assertIn(f'href="{entry["page"]}"', card)
        self.assertFalse(any("/raw/" in path for path in files))
        links = PageLinks()
        links.feed(files[entry["page"]].decode())
        self.assertTrue(all(f"{stage.ROUTE}/{path}" in files for path in links.paths))
        archive_path = f"{stage.ROUTE}/{stage.ROUTE}.zip"
        with ZipFile(BytesIO(files[archive_path])) as offline:
            self.assertEqual(offline.read("index.html"), files[entry["page"]])
            self.assertEqual(sorted(set(links.paths) - set(offline.namelist())), [])
        for download in (archive_path, archive_path + ".sha256"):
            self.assertIn(f'href="{download}"', card)
        summary = json.loads(files[entry["raw_record"]])
        self.assertEqual(summary["research_revision"], stage.SOURCE)
        self.assertEqual(summary["native_sdk_revision"], stage.SDK)
        self.assertEqual(len({row["graph"] for row in summary["episodes"]}), 30)
        self.assertEqual(sum(len(row["applied_controls"]) for row in summary["episodes"]), 900)
        self.assertTrue(
            all(
                row["status"] == row["replay"] == row["render"] == "complete"
                for row in summary["episodes"]
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            page = site / "examples" / entry["page"]
            page.parent.mkdir(parents=True)
            page.write_bytes(files[entry["page"]])
            routes = json.loads(presentation.REGISTRY.read_bytes())["routes"]
            audit = presentation.audit_site(site, {"routes": routes})
            self.assertTrue(audit["passed"], audit["findings"])
