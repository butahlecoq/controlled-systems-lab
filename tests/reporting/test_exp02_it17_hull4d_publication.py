from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
sys.path.insert(0, str(ROOT / "benchmarks/reporting/it17_hull"))

import exp02_it17_hull4d as publication
import summarize_4d

BUNDLE = ROOT / "reports/algorithm-results/exp02-it17-hull-4d-simplex-20261028-r1"


class Exp02Hull4DPublicationTests(unittest.TestCase):
    def test_every_attempt_is_retained_and_exact_certificate_checks_pass(self) -> None:
        rows = summarize_4d.read_rows(BUNDLE / "raw/raw-rows.jsonl")
        self.assertEqual(len(rows), 36)
        measured = [row for row in rows if not row["warmup"]]
        self.assertEqual(len(measured), 30)
        lp_measured = [row for row in measured if row["method"] != "geometric-quickhull"]
        self.assertEqual(len(lp_measured), 25)
        self.assertTrue(all(row["outcome"] == "verified" for row in lp_measured))
        self.assertEqual(sum(row["reducer_status_complete"] is True for row in lp_measured), 15)
        self.assertTrue(all(row["outcome"] == "unsupported_dimension" and row["elapsed_ns"] == 0
                            for row in rows if row["method"] == "geometric-quickhull"))
        config = json.loads((BUNDLE / "raw/run-config.json").read_text(encoding="utf-8"))
        self.assertEqual(config["input_sha256"], rows[0]["input_sha256"])
        renderer_hash = hashlib.sha256(Path(summarize_4d.__file__).read_bytes()).hexdigest()
        self.assertEqual((BUNDLE / "raw/summarizer.sha256").read_text(encoding="utf-8").strip(),
                         renderer_hash)

    def test_validator_rejects_rows_with_a_shared_but_wrong_input_hash(self) -> None:
        rows = [json.loads(line) for line in
                (BUNDLE / "raw/raw-rows.jsonl").read_text(encoding="utf-8").splitlines()]
        for row in rows:
            row["input_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as temporary:
            raw = Path(temporary) / "tampered.jsonl"
            raw.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "independently hashed source and fixture"):
                summarize_4d.read_rows(raw)

    def test_report_preserves_withheld_timings_and_six_input_projections(self) -> None:
        with (BUNDLE / "summary.csv").open(encoding="utf-8") as stream:
            summary = {row["method"]: row for row in csv.DictReader(stream)}
        for method in (summarize_4d.METHODS[0], summarize_4d.METHODS[2]):
            self.assertEqual(summary[method]["reducer_complete"], "0/5")
            self.assertEqual(summary[method]["elapsed_median_ms"], "")
        for method in (summarize_4d.METHODS[1], summarize_4d.METHODS[3],
                       summarize_4d.METHODS[4]):
            self.assertEqual(summary[method]["reducer_complete"], "5/5")
            self.assertNotEqual(summary[method]["elapsed_median_ms"], "")
        page = (BUNDLE / "index.html").read_text(encoding="utf-8")
        figure = (BUNDLE / "input-projections.svg").read_text(encoding="utf-8")
        self.assertIn("no speedup claim", page)
        self.assertIn("input points only", figure)
        self.assertIn('transform="rotate(-90', figure)
        for pair in ("x1–x2", "x1–x3", "x1–x4", "x2–x3", "x2–x4", "x3–x4"):
            self.assertIn(f"Projection {pair}", figure)

    def test_offline_package_is_deterministic_and_verifies(self) -> None:
        first = publication.package(BUNDLE)
        self.assertEqual(first, publication.package(BUNDLE))
        self.assertEqual(first, publication.verify_bundle(BUNDLE))

    def test_stager_adds_route_and_rejects_tampering_and_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / BUNDLE.name
            shutil.copytree(BUNDLE, bundle)
            site = root / "site"
            site.mkdir()
            (site / "index.html").write_text("<!doctype html><html><ul></ul></html>",
                                              encoding="utf-8")
            self.assertEqual(publication.stage(bundle, site), BUNDLE.name)
            index = (site / "index.html").read_text(encoding="utf-8")
            self.assertIn(f"{BUNDLE.name}/index.html", index)
            self.assertIn("two exact but incomplete outputs", index)
            self.assertTrue((site / BUNDLE.name / f"{BUNDLE.name}.zip").is_file())

            (bundle / "summary.csv").write_text("tampered\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                publication.verify_bundle(bundle)

            symlink_bundle = root / (BUNDLE.name + "-symlink")
            shutil.copytree(BUNDLE, symlink_bundle)
            (symlink_bundle / "external.txt").symlink_to(bundle / "summary.csv")
            with self.assertRaisesRegex(ValueError, "symlinks"):
                publication.bundle_files(symlink_bundle)


if __name__ == "__main__":
    unittest.main()
