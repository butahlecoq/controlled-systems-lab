"""Check the deterministic Lotka–Volterra sample record and publication."""

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
import lotka_volterra_sampled as report
import stage_lotka_volterra_sampled as publisher

FROZEN_GENERATOR = ROOT / "scripts/reports/lotka_volterra_sampled_frozen_321ac099.py"
FROZEN_GENERATOR_SHA256 = "321ac099e8185c8b1b9a76af9859c9b818682b429ba705f1410a19d648238f1c"
frozen_spec = importlib.util.spec_from_file_location("frozen_lotka_volterra_sampled", FROZEN_GENERATOR)
frozen_report = importlib.util.module_from_spec(frozen_spec)
frozen_spec.loader.exec_module(frozen_report)


class SampledLotkaVolterraTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.commit = "987e6c8117aa95d186383deb2f03b56297f4facb"
        cls.record = report.simulate(cls.commit)

    def test_samples_replay_from_saved_controls(self):
        record = self.record
        self.assertEqual(record["claim_scope"],
                         "512 deterministic sampled control histories; not the full reachable set, not an inner/outer certificate, and not a historical reproduction.")
        self.assertEqual(len(record["sampled_controls"]), report.SAMPLES)
        self.assertEqual(len(record["sampled_states"]), report.SAMPLES)
        a, b, c, d, e = (report.PARAMETERS[key] for key in ("a", "b", "c", "d", "e"))
        step = record["model"]["step"]["value"]
        for controls, states in zip(record["sampled_controls"], record["sampled_states"]):
            self.assertEqual(len(controls), report.HORIZON)
            self.assertEqual(len(states), report.HORIZON + 1)
            self.assertEqual(states[0], [410.0, 300.0])
            x, y = 410.0, 300.0
            for index, control in enumerate(controls):
                x, y = x + step*(a*x-b*x*y+e*control), y + step*(-c*y+d*x*y)
                expected = [round(x, 12), round(y, 12)]
                self.assertEqual(states[index+1], expected)
                self.assertTrue(report.CONTROL[0] <= control <= report.CONTROL[1])

    def test_publication_is_deterministic_and_labels_sample_hulls(self):
        first = report.generated_files(self.commit)
        second = report.generated_files(self.commit)
        self.assertEqual(first, second)
        record = json.loads(first["records.json"])
        self.assertEqual(record["displayed_stages"], list(report.STAGES))
        svg = first["geometry.svg"].decode()
        page = first["index.html"].decode()
        self.assertIn("not certified reachable sets", svg)
        self.assertIn("not the full reachable sets", page)
        self.assertIn("sample hull; local zoom", svg)
        self.assertIn("L05 Example 1 source dossier", page)
        self.assertIn(
            "https://github.com/butahlecoq/controlled-systems-lab/blob/"
            "797b606faee21d9cc22004c882fc7e120113be20/"
            "docs/research/l05-example1-source-dossier.md", page)
        cloud = [trace[15] for trace in record["sampled_states"]]
        self.assertGreaterEqual(len(report.convex_hull(cloud)), 3)

    def test_saved_bundle_is_reproducible_and_stages_as_a_local_page(self):
        self.assertEqual(report.sha(FROZEN_GENERATOR.read_bytes()), FROZEN_GENERATOR_SHA256)
        frozen_report.build(report.REPORT_DIR, None, True)
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            (site / "index.html").write_text("<!doctype html><html><body></body></html>")
            route = site / publisher.stage(report.REPORT_DIR, site)
            for name in ("geometry.svg", "index.html", "manifest.json", "records.json"):
                self.assertEqual((route / name).read_bytes(), (report.REPORT_DIR / name).read_bytes())


if __name__ == "__main__":
    unittest.main()
