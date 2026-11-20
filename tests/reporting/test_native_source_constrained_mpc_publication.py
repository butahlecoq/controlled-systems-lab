"""Verify that the gallery and archive expose the same frozen catalogue evidence."""

import importlib
import json
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
landing = importlib.import_module("landing")
presentation = importlib.import_module("audit_mathematical_presentation")
stage = importlib.import_module("stage_native_source_constrained_mpc")


class PageLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.local_paths: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name in {"href", "src"} and value:
                link = urlsplit(value)
                if not link.scheme and not link.netloc and link.path:
                    self.local_paths.append(link.path)


class CataloguePublicationTests(unittest.TestCase):
    def test_gallery_and_archive_link_all_saved_outcomes(self) -> None:
        files, [entry], gallery_card = stage.build(ROOT)
        self.assertIn(f'href="{entry["page"]}"', gallery_card)
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            for name, content in files.items():
                path = site / "examples" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            page = site / "examples" / entry["page"]
            parsed = PageLinks()
            parsed.feed(page.read_text(encoding="utf-8"))
            self.assertEqual(
                {path for path in parsed.local_paths if path.startswith("raw/")},
                {f"raw/{model}.json" for model in range(1, 36)},
            )
            for path in parsed.local_paths:
                self.assertTrue((page.parent / path).is_file(), path)
            registry = json.loads(presentation.REGISTRY.read_bytes())
            audit = presentation.audit_site(site, {"routes": registry["routes"]})
            self.assertTrue(audit["passed"], audit["findings"])
            index = site / "index.html"
            index.write_text("<ul></ul>", encoding="utf-8")
            (site / "archive.html").touch()
            landing.build(site)
            [report], _ = landing.parse_index(index.read_text(encoding="utf-8"))
            self.assertEqual(report.report_id + "/index.html", "examples/" + entry["page"])
            self.assertEqual(report.commit, stage.IDENTITY.source_commit)
            for _, relative in report.links:
                self.assertTrue((site / relative).is_file(), relative)
