"""Saved finite-feedback evidence and schema-3 publication behavior."""
from __future__ import annotations

import csv
import hashlib
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
import stage_finite_feedback as stage

BUNDLE = ROOT / "reports/algorithm-results/finite-feedback-a6e96fd96c7ac7cc"
CATALOGUE = BUNDLE.parent / "finite-feedback-publications.json"


class Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.paths: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self.paths.extend(value for key, value in attrs if key == "href" and value)


class FiniteFeedbackReportTests(unittest.TestCase):
    def test_saved_numerical_work_and_timing_are_rederived_from_raw(self):
        record = stage.report.render(BUNDLE, check=True)
        self.assertEqual(record["source_commit"], "d0da7cb3b167f21e620b716b615e7b77cf5bd7aa")
        self.assertEqual(record["harness_commit"], "6602f0f88a8ef2071edefbbd913f7c4bbb6201df")
        self.assertEqual(record["work"]["measured_registered_calls"], 28)
        self.assertEqual(record["work"]["failed"], 0)
        self.assertEqual({row["scenario"]: row["median_ns"] for row in record["summary"]},
                         {"clipping": 3500, "branching": 4700, "empty-action": 3100, "nominal": 3300})
        rows = list(csv.DictReader(io.StringIO((BUNDLE / "measure.stdout.log").read_text(encoding="utf-8"))))
        self.assertEqual(len(rows), 32)
        self.assertEqual(sum(row["purpose"] == "warmup" for row in rows), 4)
        self.assertEqual(sum(row["purpose"] == "trial" for row in rows), 28)
        self.assertIn("inconclusive exploratory single-adapter", (BUNDLE / "index.html").read_text())
        self.assertIn("Other action-tensor cells are not independently checked", (BUNDLE / "index.html").read_text())
        self.assertEqual(record["oracle_scope"]["action_cells"]["nominal"], ["stage 0 state 0"])
        pre = json.loads((BUNDLE / "prebuild-receipt.json").read_text())
        post = json.loads((BUNDLE / "postrun-receipt.json").read_text())
        self.assertEqual((pre["commit"], pre["tree"], pre["status_sha256"]),
                         (post["commit"], post["tree"], post["status_sha256"]))
        self.assertEqual(pre["tracked_count"], 1438)
        graph = json.loads((BUNDLE / "build-graph.json").read_text())
        self.assertEqual(graph["selected_artifact"], "Release/csl_finite_feedback_report.exe")
        self.assertIn("csl_contracts", graph["targets"])
        self.assertIn("src/contracts/problem.cpp", graph["targets"]["csl_contracts"]["sources"])

    def test_staged_route_and_offline_zip_match_saved_bytes(self):
        catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))
        expected = stage.catalogue_entry(BUNDLE)
        self.assertEqual(catalogue["reports"], [expected])
        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary) / "site"
            site.mkdir()
            (site / "index.html").write_text('<!doctype html><html lang="en"><body><ul></ul></body></html>')
            (site / "old.txt").write_bytes(b"unchanged")
            public_id = stage.stage(CATALOGUE, site)
            self.assertEqual((site / "old.txt").read_bytes(), b"unchanged")
            self.assertEqual((site / public_id / "measure.stdout.log").read_bytes(),
                             (BUNDLE / "measure.stdout.log").read_bytes())
            self.assertEqual(hashlib.sha256((site / (public_id + ".zip")).read_bytes()).hexdigest(),
                             expected["zip_sha256"])
            with zipfile.ZipFile(site / (public_id + ".zip")) as archive:
                self.assertEqual(archive.read(public_id + "/records.json"),
                                 (BUNDLE / "records.json").read_bytes())
                for page in ("index.html", public_id + "/index.html"):
                    links = Links()
                    links.feed(archive.read(page).decode())
                    self.assertTrue(links.paths)
                    for href in links.paths:
                        with self.subTest(page=page, href=href):
                            self.assertIn((Path(page).parent / href).as_posix(), archive.namelist())
            with self.assertRaises(ValueError):
                stage.stage(CATALOGUE, site)

    def test_source_or_rendered_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / BUNDLE.name
            shutil.copytree(BUNDLE, copied)
            for name in ("measure.stdout.log", "prebuild-receipt.json", "postrun-receipt.json",
                         "source-tree.txt", "build-graph.json", "records.json", "index.html"):
                with self.subTest(name=name):
                    path = copied / name
                    original = path.read_bytes()
                    path.write_bytes(original + b"\n")
                    with self.assertRaises(ValueError):
                        stage.validate(copied)
                    path.write_bytes(original)

    def test_workflow_stages_the_extension(self):
        workflow = (ROOT / ".github/workflows/algorithm-reports.yml").read_text(encoding="utf-8")
        self.assertIn("scripts/reports/stage_finite_feedback.py", workflow)
        self.assertIn("reports/algorithm-results/finite-feedback-publications.json", workflow)


if __name__ == "__main__":
    unittest.main()
