"""Validate the saved #1096 nonaxis parallelotope A/B campaign publication."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))

import stage_app02_nonaxis_ab as campaign  # noqa: E402

CATALOG = ROOT / "reports/algorithm-results/app02-nonaxis-ab-publications.json"


class NonaxisCampaignPublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
        cls.entry = cls.catalog["reports"][0]
        cls.bundle = CATALOG.parent / cls.entry["report_id"]
        cls.manifest = campaign.validate(cls.bundle)
        cls.summary = json.loads((cls.bundle / "summary.json").read_text(encoding="utf-8"))

    def test_catalog_and_archive_bind_the_saved_report(self):
        self.assertEqual(self.catalog["schema"], campaign.CATALOG_SCHEMA)
        self.assertEqual(campaign.catalog_entry(self.bundle), self.entry)
        self.assertEqual(self.manifest["report_id"], self.entry["report_id"])
        self.assertEqual(self.manifest["source_commit"], campaign.SOURCE_COMMIT)
        self.assertEqual(self.manifest["campaign"]["tasks"], list(campaign.TASKS))
        self.assertEqual(self.manifest["campaign"]["controllers"], campaign.CONTROLLERS)

    def test_campaign_retains_both_pairs_and_three_tasks(self):
        costs = self.summary["costs"]
        self.assertEqual(len(costs), 12)
        self.assertEqual({row["pair"] for row in costs}, {"axis-vs-rotated", "axis-vs-selected"})
        self.assertEqual({row["task"] for row in costs}, set(campaign.TASKS))
        self.assertEqual({row["frame"] for row in costs}, {"axis", "fixed-45", "selected"})
        self.assertEqual(len(self.summary["attempts"]), 60)
        self.assertEqual(len(self.summary["certificates"]), 12)

    def test_sampled_support_and_budgets_are_disclosed(self):
        gaps = [row for row in self.summary["support"] if row["role"] == "all"]
        self.assertTrue(gaps)
        self.assertTrue(all(row["frame_checks_passed"] == row["membership_rows"] for row in gaps))
        self.assertTrue(
            any(row["max_excess"] > 1.0 for row in gaps if row["frame"] == "fixed-45"),
            "the fixed-45 looseness finding must remain visible",
        )
        for row in self.summary["costs"]:
            accounted = sum(row["statuses"].values())
            self.assertEqual(
                accounted,
                row["measured_attempts"],
                "every measured attempt keeps a status, including incomplete ones",
            )
            self.assertEqual(
                row["complete_measured"] + row["incomplete_measured"], row["measured_attempts"]
            )
        blowups = self.summary["frames"]["totals"]["numerical_blowup_attempts"]
        self.assertEqual(blowups, 5, "the Earth-orbit fixed-45 blow-up must remain disclosed")

    def test_index_lists_figures_and_files(self):
        index = (self.bundle / "index.html").read_text(encoding="utf-8")
        for name in self.manifest["files_sha256"]:
            if name.endswith(".svg"):
                self.assertIn(name, index)
        for name in ("summary.json", "attempts.csv", "support-gaps.csv", "certificates.csv"):
            self.assertIn(name, index)
        self.assertIn("not a uniform error bound", index)
        self.assertIn("Limitations", index)
        self.assertIn("five attempts", index)

    def test_stager_adds_the_route_once(self):
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            (site / "index.html").write_text(
                "<html><body><ul></ul></body></html>", encoding="utf-8"
            )
            report_id = campaign.stage(CATALOG, site)
            self.assertEqual(report_id, self.entry["report_id"])
            route = site / report_id
            self.assertTrue((route / "index.html").is_file())
            self.assertTrue((route / "bundle.zip").is_file())
            self.assertEqual(
                (route / "summary.json").read_bytes(), (self.bundle / "summary.json").read_bytes()
            )
            index = (site / "index.html").read_text(encoding="utf-8")
            self.assertIn(f'{report_id}/index.html', index)
            with self.assertRaises(ValueError):
                campaign.stage(CATALOG, site)


if __name__ == "__main__":
    unittest.main()
