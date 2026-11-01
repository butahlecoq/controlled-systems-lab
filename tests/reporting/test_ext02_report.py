from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
RENDERER = ROOT / "scripts/reports/ext02/render_saved.py"
STAGER_PATH = ROOT / "scripts/reports/stage_ext02.py"


def load_stager():
    spec = importlib.util.spec_from_file_location("csl_ext02_test_stager", STAGER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class Ext02ReportTests(unittest.TestCase):
    def test_saved_renderer_preserves_trials_and_derives_terminal_plot(self) -> None:
        branches = [
            {"catalogue_index": 0, "discrete_value": -1, "objective": 0,
             "complete_family_verified": True},
            {"catalogue_index": 1, "discrete_value": 0, "objective": 0,
             "complete_family_verified": True},
            {"catalogue_index": 2, "discrete_value": 1, "objective": 0,
             "complete_family_verified": True},
        ]
        trials = [{"trial": i, "warmup": i == 0, "branches": branches} for i in range(8)]
        record = {
            "schema": "csl.ext02-portfolio-record/1", "source_commit": "a" * 40,
            "scenario": "benchmarks/scenarios/ext02-analytic-two-state-mixed-v1.json",
            "scenario_sha256": "b" * 64, "executable_sha256": "c" * 64,
            "summary": {"trials": 7, "median_elapsed_ns": 1000,
                "minimum_elapsed_ns": 900, "maximum_elapsed_ns": 1100,
                "horizon": 1, "catalogue_size": 3, "history_count": 3,
                "retained_relation_rows": 63, "retained_relation_scalars": 411,
                "retained_numeric_bytes": 3288,
                "failures": 0, "timed_interval": "one API call"},
            "trials": trials,
        }
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            source = temporary_path / "capture"
            source.mkdir()
            measurement = source / "measurement.json"
            measurement.write_text(json.dumps(record), encoding="utf-8")
            (source / "raw.jsonl").write_text("{}\n", encoding="utf-8")
            (source / "trials.csv").write_text("trial,warmup\n0,true\n", encoding="utf-8")
            output = temporary_path / "rendered"
            subprocess.run([sys.executable, str(RENDERER), str(measurement), str(output)], check=True)
            page = (output / "index.html").read_text(encoding="utf-8")
            svg = (output / "figure.svg").read_text(encoding="utf-8")
            self.assertIn("1000 ns", page)
            self.assertIn("63", page)
            self.assertIn("registry-verified complete family", page)
            self.assertIn('cx="240.0" cy="340.0"', svg)
            self.assertIn('cx="240.0" cy="120.0"', svg)
            self.assertEqual((output / "raw.jsonl").read_text(), "{}\n")
            sums = (output / "SHA256SUMS").read_text().splitlines()
            for row in sums:
                checksum, name = row.split("  ", 1)
                self.assertEqual(checksum, hashlib.sha256((output / name).read_bytes()).hexdigest())
            self.assertTrue(output.with_suffix(".zip").is_file())

    def test_stager_checksums_and_copies_the_saved_bundle(self) -> None:
        stager = load_stager()
        record = {
            "schema": "csl.ext02-portfolio-record/1", "source_commit": "a" * 40,
            "scenario_sha256": "b" * 64, "executable_sha256": "c" * 64,
            "summary": {"trials": 7, "failures": 0, "horizon": 1,
                        "catalogue_size": 3, "history_count": 3,
                        "retained_relation_rows": 63},
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / stager.REPORT_ID
            bundle.mkdir()
            contents = {
                "README.md": b"report\n", "figure.svg": b"<svg/>\n",
                "index.html": b"<!doctype html><title>report</title>\n",
                "measurement.json": json.dumps(record).encode(),
                "raw.jsonl": b"{}\n", "stderr.txt": b"",
                "trials.csv": b"trial\n",
            }
            for name, data in contents.items():
                (bundle / name).write_bytes(data)
            sums = "".join(f"{hashlib.sha256(data).hexdigest()}  {name}\n"
                           for name, data in sorted(contents.items()))
            (bundle / "SHA256SUMS").write_text(sums, encoding="ascii")
            zip_path = bundle.with_suffix(".zip")
            zip_path.write_bytes(b"zip fixture")
            original_bundle = stager.BUNDLE
            stager.BUNDLE = bundle
            try:
                catalog = root / "ext02-publications.json"
                catalog.write_text(json.dumps({"schema": "csl.ext02-publications/1",
                    "reports": [stager.catalog_entry(bundle)]}), encoding="utf-8")
                site = root / "site"
                site.mkdir()
                (site / "index.html").write_text("<html><body><ul></ul></body></html>",
                                                 encoding="utf-8")
                self.assertEqual(stager.stage(catalog, site), stager.REPORT_ID)
                route = site / stager.REPORT_ID
                self.assertEqual((route / "figure.svg").read_bytes(), contents["figure.svg"])
                self.assertEqual((route / f"{stager.REPORT_ID}.zip").read_bytes(), b"zip fixture")
                self.assertIn(stager.REPORT_ID + "/index.html", (site / "index.html").read_text())
            finally:
                stager.BUNDLE = original_bundle


if __name__ == "__main__":
    unittest.main()
