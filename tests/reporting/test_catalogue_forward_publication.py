"""Check that the catalogue forward sweep reaches readers with its frozen evidence."""

import importlib
import json
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

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

    def test_feasible_history_stages_original_data_and_battery_projection(self) -> None:
        files, [entry], card = stage.build_feasible_history(ROOT)
        route = stage.FEASIBLE_HISTORY.route
        original = route + "/catalogue-feasible-history-evidence.zip"
        for path in (entry["page"], entry["figure"], original):
            self.assertIn(path, files)
            self.assertIn(path, card)
        with ZipFile(BytesIO(files[original])) as archive:
            summary = json.loads(archive.read("comparison-summary.json"))
            audit = json.loads(archive.read("independent-audit.json"))
            self.assertEqual(
                files[entry["figure"]], archive.read("battery-history-projections.svg")
            )
        self.assertEqual(len(audit), 35)
        self.assertEqual(
            summary["native"],
            {
                "full_history": {
                    "optimal": 991,
                    "infeasible": 32,
                    "unsupported": 96,
                    "undetermined": 1,
                },
                "intervals_only": {"optimal": 976, "unbounded": 48, "unsupported": 96},
            },
        )
        battery = audit["5"]
        supports = {}
        for profile in ("full_history", "intervals_only"):
            [sample] = [
                row
                for row in battery[profile]["samples"]
                if row["stage"] == 3 and row["direction"] == [-1, -1]
            ]
            supports[profile] = sample["native_support"]
        self.assertAlmostEqual(supports["intervals_only"] - supports["full_history"], 60.986)
        book = json.loads((ROOT / "docs/catalogue/learning-book-v1.json").read_bytes())
        [chapter] = [item for item in book["chapters"] if item["id"] == "native-forward-models"]
        self.assertIn("../examples/" + entry["page"], {item["href"] for item in chapter["records"]})
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            for name, content in files.items():
                path = site / "examples" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            ledger = json.loads(presentation.REGISTRY.read_bytes())
            page = "examples/" + entry["page"]
            [record] = [item for item in ledger["routes"] if item["route"] == page]
            presentation_audit = presentation.audit_site(site, {"routes": [record]})
            self.assertTrue(presentation_audit["passed"], presentation_audit["findings"])
            index = site / "index.html"
            index.write_text("<ul></ul>", encoding="utf-8")
            (site / "archive.html").touch()
            landing.build(site)
            [archive_entry], _ = landing.parse_index(index.read_text(encoding="utf-8"))
            self.assertEqual(archive_entry.report_id + "/index.html", page)
            self.assertEqual(archive_entry.commit, stage.FEASIBLE_HISTORY.source_commit)
            for _, path in archive_entry.links:
                self.assertTrue((site / path).is_file(), path)

    def test_exact_support_keeps_the_refusals_and_primal_dual_certificates(self) -> None:
        files, [entry], card = stage.build_exact_support(ROOT)
        route = stage.EXACT_SUPPORT.route
        original = route + "/catalogue-exact-support-evidence.zip"
        for path in (entry["page"], entry["figure"], original):
            self.assertIn(path, files)
            self.assertIn(path, card)
        with ZipFile(BytesIO(files[original])) as archive:
            self.assertEqual(files[entry["figure"]], archive.read("building-budget-projection.svg"))
            self.assertEqual(files[f"{route}/exact_support.cpp"], archive.read("exact_support.cpp"))
            audit = json.loads(archive.read("independent-exact-audit.json"))
            self.assertEqual(set(audit), {"23", "27", "28"})
            for model, strict in (("23", 0), ("27", 0), ("28", 12)):
                input_data = json.loads(archive.read(f"input/raw/{model}.json"))
                certificates = json.loads(archive.read(f"results/{model}.json"))
                self.assertEqual(audit[model]["budget_effect"]["strict_support_reductions"], strict)
                for profile in ("full_history", "intervals_only"):
                    self.assertEqual(audit[model][profile]["statuses"], {"exact-optimal": 32})
                    self.assertEqual(len(certificates[profile]), 32)
                    for original_row, row in zip(
                        input_data[profile]["samples"], certificates[profile], strict=True
                    ):
                        self.assertEqual(row["stage"], original_row["stage"])
                        self.assertEqual(row["direction"], original_row["direction"])
                        self.assertEqual(original_row["status"], "unsupported")
                        self.assertEqual(row["prior_native_status"], original_row["status"])
                        self.assertEqual(row["status"], "exact-optimal")
            self.assertAlmostEqual(
                audit["28"]["budget_effect"]["max_support_reduction_decimal"] * 1e13,
                1.2697696340859817,
            )
        book = json.loads((ROOT / "docs/catalogue/learning-book-v1.json").read_bytes())
        [chapter] = [item for item in book["chapters"] if item["id"] == "native-forward-models"]
        page = "examples/" + entry["page"]
        self.assertIn("../" + page, {item["href"] for item in chapter["records"]})
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            for name, content in files.items():
                target = site / "examples" / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            ledger = json.loads(presentation.REGISTRY.read_bytes())
            [record] = [item for item in ledger["routes"] if item["route"] == page]
            report = presentation.audit_site(site, {"routes": [record]})
            self.assertTrue(report["passed"], report["findings"])
            index = site / "index.html"
            index.write_text("<ul></ul>", encoding="utf-8")
            (site / "archive.html").touch()
            landing.build(site)
            [archive_entry], _ = landing.parse_index(index.read_text(encoding="utf-8"))
            self.assertEqual(archive_entry.report_id + "/index.html", page)
            self.assertEqual(archive_entry.commit, stage.EXACT_SUPPORT.source_commit)
            for _, path in archive_entry.links:
                self.assertTrue((site / path).is_file(), path)
