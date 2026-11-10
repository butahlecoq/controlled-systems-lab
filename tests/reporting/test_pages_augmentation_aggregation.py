"""Combined main-only Pages deployment retains all standalone report routes."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import tarfile
import unittest
import zipfile
from io import BytesIO

from scripts.reports import augment_pages_bundle, await_pages_augmentation_runs

ROOT = Path(__file__).resolve().parents[2]


def run(run_id: int, created: str, updated: str, *, head: str,
        branch: str = "main", event: str = "workflow_run", status: str = "completed",
        conclusion: str = "success"):
    return {"id": run_id, "created_at": created, "updated_at": updated,
            "head_sha": head, "head_branch": branch, "event": event,
            "status": status, "conclusion": conclusion}


class PagesAugmentationAggregation(unittest.TestCase):
    def test_combines_mpc01_b04_and_mpc06_routes_into_one_site(self):
        with tempfile.TemporaryDirectory(prefix="pages-augmentation-aggregation-") as temporary:
            site = Path(temporary) / "site"
            site.mkdir()
            (site / "index.html").write_text(
                '<!doctype html><html><body><p id="base">Base reports</p></body></html>',
                encoding="utf-8")
            (site / "existing-route").mkdir()
            (site / "existing-route/index.html").write_text("existing", encoding="utf-8")
            (site / "examples").mkdir()
            (site / "examples/index.html").write_text("examples", encoding="utf-8")

            routes = augment_pages_bundle.stage_all(site)

            landing = (site / "index.html").read_text(encoding="utf-8")
            self.assertIn('id="base"', landing)
            self.assertIn(f'href="{routes["mpc01"]}/index.html"', landing)
            self.assertIn("mpc01-strategy-ab-ts03-20261103-r1/strategy-ab-ts03-summary.html", landing)
            self.assertIn(f'href="{routes["b04_c"]}/index.html"', landing)
            self.assertIn(f'href="{routes["b04_c"]}.zip"', landing)
            self.assertIn(f'href="{routes["mpc06"]}/index.html"', landing)
            self.assertIn(f'href="{routes["mpc06"]}.zip"', landing)
            self.assertIn(f'href="{routes["mpc06_complete"]}/index.html"', landing)
            self.assertIn(f'href="{routes["mpc06_complete"]}.zip"', landing)
            self.assertEqual((site / "existing-route/index.html").read_text(), "existing")
            self.assertEqual((site / "examples/index.html").read_text(), "examples")
            self.assertTrue((site / "docs/research/evidence/mpc01-strategy-ab-ts03-20261103-r1/strategy-ab-ts03-summary.html").is_file())
            for report_id in (routes["b04_c"], routes["mpc06"], routes["mpc06_complete"]):
                with zipfile.ZipFile(site / f"{report_id}.zip") as archive:
                    self.assertIn(f"{report_id}/publication-manifest.json", archive.namelist())

    def test_marker_is_bound_to_the_exact_report_run(self):
        source = {"schema": "csl.pages-augmentation-source/1",
                  "report_run_id": 42, "head_sha": "a" * 40}
        tar_bytes = BytesIO()
        with tarfile.open(fileobj=tar_bytes, mode="w") as archive:
            encoded = (json.dumps(source, sort_keys=True, separators=(",", ":")) + "\n").encode()
            item = tarfile.TarInfo("./pages-augmentation-source.json")
            item.size = len(encoded)
            archive.addfile(item, BytesIO(encoded))
        zipped = BytesIO()
        with zipfile.ZipFile(zipped, "w") as archive:
            archive.writestr("artifact.tar", tar_bytes.getvalue())

        self.assertEqual(await_pages_augmentation_runs.source_marker(zipped.getvalue()), source)

    def test_latest_report_is_selected_by_completion_time_for_same_sha(self):
        sha = "a" * 40
        runs = [
            run(10, "2026-11-03T03:00:00Z", "2026-11-03T03:08:00Z", head=sha, event="push"),
            run(11, "2026-11-03T03:02:00Z", "2026-11-03T03:05:00Z", head=sha, event="workflow_dispatch"),
            run(12, "2026-11-03T03:03:00Z", "2026-11-03T03:09:00Z", head=sha,
                event="push", conclusion="failure"),
            run(13, "2026-11-03T03:04:00Z", "2026-11-03T03:10:00Z", head="b" * 40, event="push"),
        ]
        latest = await_pages_augmentation_runs.latest_report_run(runs, head_sha=sha)
        self.assertEqual(latest["id"], 10)

    def test_aggregation_wait_job_precedes_single_cumulative_deployment(self):
        workflow = (ROOT / ".github/workflows/pages-augmentation-aggregation.yml").read_text(encoding="utf-8")
        self.assertIn("MPC-06 tube objective Pages augmentation", workflow)
        self.assertIn("await_pages_augmentation_runs.py", workflow)
        self.assertIn("needs: await", workflow)
        self.assertIn("augment_pages_bundle.py", workflow)
        self.assertIn("group: github-pages", workflow)
        self.assertIn("PAGES_SOURCE_RUN_ID", workflow)
        self.assertLess(workflow.index("pip install"), workflow.index("name: Stage and verify all Pages augmentations together"))


if __name__ == "__main__":
    unittest.main()
