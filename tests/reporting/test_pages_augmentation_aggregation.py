"""Combined main-only Pages deployment retains all standalone report routes."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.reports import augment_pages_bundle, await_pages_augmentation_runs

ROOT = Path(__file__).resolve().parents[2]


def run(run_id: int, created: str, *, head: str, branch: str = "main",
        event: str = "workflow_run", status: str = "completed", conclusion: str = "success"):
    return {"id": run_id, "created_at": created, "head_sha": head,
            "head_branch": branch, "event": event, "status": status,
            "conclusion": conclusion}


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
            self.assertEqual((site / "existing-route/index.html").read_text(), "existing")
            self.assertEqual((site / "examples/index.html").read_text(), "examples")
            self.assertTrue((site / "docs/research/evidence/mpc01-strategy-ab-ts03-20261103-r1/strategy-ab-ts03-summary.html").is_file())
            for report_id in (routes["b04_c"], routes["mpc06"]):
                with zipfile.ZipFile(site / f"{report_id}.zip") as archive:
                    self.assertIn(f"{report_id}/publication-manifest.json", archive.namelist())

    def test_run_selection_excludes_old_same_sha_deployments(self):
        sha = "a" * 40
        runs = [
            run(1, "2026-11-03T02:00:00Z", head=sha),
            run(2, "2026-11-03T03:00:00Z", head=sha, status="in_progress", conclusion=""),
            run(3, "2026-11-03T03:05:00Z", head="b" * 40),
        ]
        current = await_pages_augmentation_runs.run_after_parent(
            runs, head_sha=sha, parent_created_at="2026-11-03T02:55:00Z")
        self.assertEqual(current["id"], 2)
        self.assertEqual(current["status"], "in_progress")

    def test_parent_run_is_latest_success_before_child_run(self):
        sha = "a" * 40
        runs = [
            run(1, "2026-11-03T02:00:00Z", head=sha, event="push"),
            run(2, "2026-11-03T02:30:00Z", head=sha, event="push", conclusion="failure"),
            run(3, "2026-11-03T03:00:00Z", head=sha, event="push"),
            run(4, "2026-11-03T03:05:00Z", head=sha, event="push"),
        ]
        parent = await_pages_augmentation_runs.select_parent_run(
            runs, head_sha=sha, child_created_at="2026-11-03T03:04:00Z")
        self.assertEqual(parent["id"], 3)

    def test_aggregation_wait_job_precedes_single_cumulative_deployment(self):
        workflow = (ROOT / ".github/workflows/pages-augmentation-aggregation.yml").read_text(encoding="utf-8")
        self.assertIn("MPC-06 tube objective Pages augmentation", workflow)
        self.assertIn("await_pages_augmentation_runs.py", workflow)
        self.assertIn("needs: await", workflow)
        self.assertIn("augment_pages_bundle.py", workflow)
        self.assertIn("group: github-pages", workflow)


if __name__ == "__main__":
    unittest.main()
