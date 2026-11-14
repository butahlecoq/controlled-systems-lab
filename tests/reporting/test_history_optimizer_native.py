"""Source-bound gallery checks for the native whole-history optimizer example."""

from __future__ import annotations

import hashlib
import importlib
import json
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
report = importlib.import_module("stage_history_optimizer_native")


def _fixture(bundle: Path) -> None:
    records = bundle / "records"
    records.mkdir(parents=True)
    (bundle / "history.csv").write_text(
        "series,stage,position,velocity,u0,u1,source_J\n"
        "whole-history-source-J,0,0,0,1,1,1\n"
        "whole-history-source-J,1,1,0,1,1,1\n"
        "whole-history-source-J,2,1,1,1,1,1\n",
        encoding="utf-8",
    )
    (bundle / "history.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>',
        encoding="utf-8",
    )
    (records / "build.log").write_text("Release target built\n", encoding="utf-8")
    (records / "CMakeCache.txt").write_text("CSL_ENABLE_CASADI:BOOL=ON\n", encoding="utf-8")
    (records / "native-output.html").write_text("<html>native output</html>\n", encoding="utf-8")
    (records / "stdout.txt").write_text(
        "provider=csl.nlp.casadi-ipopt.history-cost@1\n", encoding="utf-8"
    )
    source_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    ).stdout.strip()
    source_files = {
        relative: hashlib.sha256(
            subprocess.run(
                ["git", "show", f"{source_commit}:{relative}"],
                cwd=ROOT,
                check=True,
                stdout=subprocess.PIPE,
            ).stdout
        ).hexdigest()
        for relative in report.SOURCE_PATHS
    }
    receipt = {
        "schema": report.SCHEMA,
        "source_commit": source_commit,
        "source_files": source_files,
        "source_tree": "controlled-systems-lab",
        "binary_sha256": "1" * 64,
        "provider": "csl.nlp.casadi-ipopt.history-cost@1",
        "source_objective": "||x2-(1,1)||_2 + 0.5(|u0|+|u1|)",
        "result": {
            "source_J": 1,
            "u0": 1,
            "u1": 1,
            "maximum_history_violation": 0,
            "diagnostics": "local numerical",
        },
        "reproduction_command": "cmake --build build --target history_optimizer_2d_example",
        "artifacts": {
            "csv_sha256": hashlib.sha256((bundle / "history.csv").read_bytes()).hexdigest(),
            "figure_sha256": hashlib.sha256((bundle / "history.svg").read_bytes()).hexdigest(),
            "native_html_sha256": hashlib.sha256(
                (records / "native-output.html").read_bytes()
            ).hexdigest(),
            "stdout_sha256": hashlib.sha256((records / "stdout.txt").read_bytes()).hexdigest(),
            "build_log_sha256": hashlib.sha256((records / "build.log").read_bytes()).hexdigest(),
            "cmake_cache_sha256": hashlib.sha256(
                (records / "CMakeCache.txt").read_bytes()
            ).hexdigest(),
        },
    }
    (records / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    report.finalize_capture(bundle)


class NativeHistoryReportTests(unittest.TestCase):
    def test_archive_is_hash_pinned_and_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / report.REPORT_ID
            _fixture(bundle)
            receipt = report.validate(bundle, ROOT)
            self.assertEqual(len(receipt["source_commit"]), 40)
            page = (bundle / "index.html").read_text(encoding="utf-8")
            self.assertIn("authored source cost", page)
            self.assertIn("1.1035533906", page)
            figure = ET.fromstring((bundle / "history.svg").read_bytes())
            self.assertTrue(figure.tag.endswith("svg"))
            with zipfile.ZipFile(bundle / f"{report.REPORT_ID}.zip") as saved:
                self.assertIsNone(saved.testzip())
            (bundle / "history.csv").write_text("changed\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "receipt digest differs|file digest differs"):
                report.validate(bundle, ROOT)

    def test_current_source_capture_is_present_in_gallery_outputs(self):
        files, inventory, card = report.build(ROOT)
        self.assertIn(report.ROUTE, inventory[0]["page"])
        self.assertIn(report.FIGURE, files)
        self.assertIn(report.ARCHIVE, files)
        self.assertIn(report.RECORD, card)
        receipt = json.loads(files[report.RECORD])
        self.assertEqual(receipt["provider"], "csl.nlp.casadi-ipopt.history-cost@1")
        self.assertEqual(
            hashlib.sha256(files[report.FIGURE]).hexdigest(), receipt["artifacts"]["figure_sha256"]
        )


if __name__ == "__main__":
    unittest.main()
