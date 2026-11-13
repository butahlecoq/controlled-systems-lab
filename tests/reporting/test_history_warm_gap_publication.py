"""Publication must bind its new reading layer to the saved algorithm records."""

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))


class WarmGapPublicationTest(unittest.TestCase):
    def test_saved_wave_is_complete_using_tracked_files_only(self):
        import history_warm_gap_report

        relative = "reports/closed-loop-history-functional/warm-gap-9540-v1"
        tracked = subprocess.check_output(
            ["git", "-C", str(ROOT), "ls-files", "-z", relative], text=True
        ).split("\0")
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "bundle"
            for name in filter(None, tracked):
                target = bundle / Path(name).relative_to(relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, target)
            self.assertEqual(history_warm_gap_report.validate(bundle)["complete"], 8)

    def test_saved_wave_retains_all_outcomes_and_source_bound_queries(self):
        import history_warm_gap_report

        result = history_warm_gap_report.validate(
            ROOT / "reports/closed-loop-history-functional/warm-gap-9540-v1"
        )
        self.assertEqual(
            result,
            {"attempts": 16, "profiles": 15, "complete": 8, "accepted_queries": 304, "figures": 32},
        )

    def test_staging_rejects_rehashed_score_that_disagrees_with_raw_attempt(self):
        import stage_history_functional as publication

        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            source = temporary / "source"
            shutil.copytree(ROOT / "reports/closed-loop-history-functional", source)
            bundle = source / "warm-gap-9540-v1"
            index = json.loads((bundle / "records.json").read_text())
            record = index["records"][0]
            receipt_path = bundle / "records" / record["id"] / "receipt.json"
            receipt = json.loads(receipt_path.read_text())
            for value in (record, receipt):
                value["physical_objective"]["total"] += 1
                value["audit"]["applied_original_objective"]["total"] += 1
            receipt_path.write_text(json.dumps(receipt))
            (bundle / "records.json").write_text(json.dumps(index))
            manifest = bundle / "files.sha256"
            manifest.write_text(
                "".join(
                    hashlib.sha256(path.read_bytes()).hexdigest()
                    + "  "
                    + str(path.relative_to(bundle))
                    + "\n"
                    for path in sorted(bundle.rglob("*"))
                    if path.is_file() and path != manifest
                )
            )
            site = temporary / "site"
            (site / "examples").mkdir(parents=True)
            (site / "examples/index.html").write_text('<section id="analytic-illustrations">')
            with self.assertRaisesRegex(
                ValueError, "Published score differs from raw physical objective"
            ):
                publication.stage(source, site)
