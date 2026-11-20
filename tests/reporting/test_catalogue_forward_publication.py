"""Check that the catalogue forward sweep reaches readers with its frozen evidence."""

import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
landing = importlib.import_module("landing")
stage = importlib.import_module("stage_catalogue_forward_reachability")
presentation = importlib.import_module("audit_mathematical_presentation")


class CatalogueForwardPublicationTests(unittest.TestCase):
    def test_gallery_book_and_archive_link_the_verified_capture(self) -> None:
        files, [entry], gallery_card = stage.build(ROOT)
        route = stage.IDENTITY.route
        page = entry["page"]
        for name in (page, entry["figure"], entry["raw_record"], f"{route}/{route}.zip"):
            self.assertIn(name, files)
            if name != entry["raw_record"]:
                self.assertIn(name, gallery_card)
        result = json.loads(files[f"{route}/support-audit.json"])
        self.assertEqual(result["models"], 35)
        self.assertEqual(result["model_stages"], 140)
        self.assertEqual(result["support_checks"], 7592)
        self.assertLess(result["max_scaled_support_error"], result["scaled_tolerance"])
        book = json.loads((ROOT / "docs/catalogue/learning-book-v1.json").read_bytes())
        [chapter] = [
            chapter for chapter in book["chapters"] if chapter["id"] == "native-forward-models"
        ]
        self.assertIn("../examples/" + page, {item["href"] for item in chapter["records"]})

        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            for name, content in files.items():
                path = site / "examples" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            ledger = json.loads(presentation.REGISTRY.read_bytes())
            [record] = [item for item in ledger["routes"] if item["route"] == "examples/" + page]
            audit = presentation.audit_site(site, {"routes": [record]})
            self.assertTrue(audit["passed"], audit["findings"])
            index = site / "index.html"
            index.write_text("<ul></ul>", encoding="utf-8")
            (site / "archive.html").touch()
            landing.build(site)
            [card], _ = landing.parse_index(index.read_text(encoding="utf-8"))
            self.assertEqual(card.report_id + "/index.html", "examples/" + page)
            self.assertEqual(card.commit, stage.IDENTITY.source_commit)
            self.assertIn("authored", card.scope)
            for _, path in card.links:
                self.assertTrue((site / path).is_file(), path)
