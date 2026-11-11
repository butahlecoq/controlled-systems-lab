"""Combined main-only Pages deployment retains all standalone report routes."""
from __future__ import annotations

import hashlib
import json
import importlib.util
from pathlib import Path
import tempfile
import tarfile
import unittest
import zipfile
from io import BytesIO
from unittest import mock

from scripts.reports import (augment_pages_bundle, await_pages_augmentation_runs,
                             pages_route_retirement, replay_mpc11_published_variants)

ROOT = Path(__file__).resolve().parents[2]


def run(run_id: int, created: str, updated: str, *, head: str,
        branch: str = "main", event: str = "workflow_run", status: str = "completed",
        conclusion: str = "success"):
    return {"id": run_id, "created_at": created, "updated_at": updated,
            "head_sha": head, "head_branch": branch, "event": event,
            "status": status, "conclusion": conclusion}


HAS_MPC11 = all(importlib.util.find_spec(name) is not None for name in ('numpy','scipy','casadi','do_mpc'))


class PagesAugmentationAggregation(unittest.TestCase):
    @unittest.skipUnless(HAS_MPC11,'full cumulative staging is checked in the hash-locked optional controller CI profile')
    def test_combines_mpc01_b04_and_mpc06_routes_into_one_site(self):
        with tempfile.TemporaryDirectory(prefix="pages-augmentation-aggregation-") as temporary:
            site = Path(temporary) / "site"
            site.mkdir()
            legacy_root = b'<!doctype html><html><body><p id="base">Base reports</p></body></html>'
            (site / "index.html").write_bytes(legacy_root)
            (site / "existing-route").mkdir()
            existing_page = (b'<!doctype html><html><body><h1>Existing report</h1>'
                             b'<a href="records.json">Raw records</a> '
                             b'<a href="../existing-route.zip">Offline bundle</a></body></html>')
            (site / "existing-route/index.html").write_bytes(existing_page)
            records = b'{"schema":"csl.fixture-record/1","value":7}\n'
            (site / "existing-route/records.json").write_bytes(records)
            envelope = {
                "schema": "csl.report-envelope/1",
                "report_id": "existing-route",
                "source_report_id": "fixture-existing-report",
                "source_commit": "a" * 40,
                "payload_sha256": hashlib.sha256(records).hexdigest(),
            }
            envelope_bytes = (json.dumps(envelope, sort_keys=True) + "\n").encode()
            (site / "existing-route/report-envelope.json").write_bytes(envelope_bytes)
            with zipfile.ZipFile(site / "existing-route.zip", "w") as archive:
                archive.writestr("existing-route/records.json", records)
                archive.writestr("existing-route/report-envelope.json", envelope_bytes)
            existing_zip_hash = hashlib.sha256((site / "existing-route.zip").read_bytes()).hexdigest()
            (site / "catalog.json").write_text(json.dumps({
                "schema": "csl.algorithm-report-catalog/3",
                "reports": [{
                    "report_id": "existing-route",
                    "report_kind": "finite-feedback",
                    "source_commit": "a" * 40,
                    "payload_sha256": hashlib.sha256(records).hexdigest(),
                    "zip_sha256": existing_zip_hash,
                }],
            }, sort_keys=True) + "\n", encoding="utf-8")
            (site / "examples").mkdir()
            (site / "examples/index.html").write_text(
                '<!doctype html><html><body><h1 id="algorithm-coverage">Examples</h1></body></html>',
                encoding="utf-8")
            (site / "examples/examples.css").write_text("body{color:inherit}\n", encoding="utf-8")

            routes = augment_pages_bundle.stage_all(site)

            landing = (site / "index.html").read_text(encoding="utf-8")
            archive_page = (site / "archive.html").read_text(encoding="utf-8")
            inventory = json.loads((site / "pages-route-inventory.json").read_text(encoding="utf-8"))
            self.assertIn('data-csl-pages-learning-root="1"', landing)
            self.assertIn('href="examples/index.html"', landing)
            self.assertIn('href="archive.html"', landing)
            preserved_legacy = (site / "legacy-index.html").read_bytes()
            self.assertEqual(preserved_legacy, pages_route_retirement.legacy_root_snapshot())
            self.assertNotEqual(preserved_legacy, legacy_root)
            self.assertEqual(hashlib.sha256(preserved_legacy).hexdigest(),
                             "29376974f806ad83816be9b42bda19fbeccaebc9a7ca79c291ed3d9ea3d522d2")
            self.assertNotIn('id="base"', landing)
            strategy_summary = "docs/research/evidence/mpc01-strategy-ab-ts03-20261103-r1/strategy-ab-ts03-summary.html"
            self.assertIn(f'href="{strategy_summary}"', archive_page)
            for name in ("mpc01", "b04_c", "mpc06", "mpc06_complete", "mpc06_offline",
                         "review05", "mpc11", "mpc08", "mpc07", "mpc10", "mpc11_studies",
                         "b04_source"):
                self.assertIn(f'href="{routes[name]}/index.html"', archive_page)
            self.assertIn(routes["mpc06_offline"]+"/index.html#offline-example", (site/"examples/index.html").read_text())
            self.assertIn(routes["mpc06_complete"]+"/index.html", (site/routes["mpc06_offline"]/"index.html").read_text())
            self.assertEqual((site / "existing-route/index.html").read_bytes(), existing_page)
            self.assertEqual((site / "existing-route/records.json").read_bytes(), records)
            self.assertEqual(hashlib.sha256((site / "existing-route.zip").read_bytes()).hexdigest(), existing_zip_hash)
            self.assertIn("existing-route/index.html", archive_page)
            gallery = (site / "examples/index.html").read_text()
            self.assertIn('href="../index.html">Learn</a>', gallery)
            self.assertIn('href="../archive.html">Evidence archive</a>', gallery)
            self.assertIn(routes["review05"]+"/index.html#scalar-2d", (site/"examples/index.html").read_text())
            self.assertIn(routes["review05"]+"/index.html", archive_page)
            self.assertIn(routes["mpc11"]+"/index.html", archive_page)
            self.assertIn(routes["mpc11"]+"/index.html", (site/"examples/index.html").read_text())
            self.assertTrue((site / "docs/research/evidence/mpc01-strategy-ab-ts03-20261103-r1/strategy-ab-ts03-summary.html").is_file())
            self.assertIn(routes["mpc08"]+"/index.html#minimal-example", (site/"examples/index.html").read_text())
            self.assertIn(routes["mpc08"]+"/index.html", archive_page)
            for name in ('mpc07','mpc10','b04_source'):
                self.assertIn(routes[name]+'/index.html#minimal-example',(site/'examples/index.html').read_text())
                self.assertIn(routes[name]+'/index.html',archive_page)
            online = json.loads((site/routes["mpc07"]/"online-verification.json").read_text())
            self.assertEqual(sum(row["episodes"] for row in online["reports"]), 864)
            self.assertEqual(sum(row["stages"] for row in online["reports"]), 4032)
            self.assertIn("figures/online-policy-traces.svg", (site/routes["mpc07"]/"index.html").read_text())
            self.assertIn(routes["mpc11_studies"]+"/index.html#mesh-example",(site/"examples/index.html").read_text())
            self.assertIn(routes["mpc11_studies"]+"/index.html",archive_page)
            retained_mpc11 = {
                "mpc11-controller-comparison-5d94c9106e1cf07e4a2e": "dd270a903dff87a24385e205aaa705efb98f7a86019bdce024824d6fba1bc363",
                "mpc11-mesh-timing-dcb9e6e302ed2fabeb71": "f886dce8913fd833929ecc18ab6d9b2a1c087b4992b77505fb41377494d0070a",
                "mpc11-controller-comparison-967db980c95590a5150b": "a14f045212e4bbd3858e1efa2ea62e2387c648bbb7742ef8cd4ec1317873866e",
                "mpc11-mesh-timing-e1d5ebe497051adfdfad": "c8a84931f056a25c0cfb88b7ec8a24b16be4c119794d6e3964247d3af4374854",
            }
            self.assertEqual(routes["mpc11"], "mpc11-controller-comparison-967db980c95590a5150b")
            self.assertEqual(routes["mpc11_studies"], "mpc11-mesh-timing-e1d5ebe497051adfdfad")
            self.assertEqual(routes["retained_mpc11_variants"], retained_mpc11)
            for route, expected_zip_hash in retained_mpc11.items():
                self.assertTrue((site / route / "index.html").is_file())
                self.assertEqual(hashlib.sha256((site / (route + ".zip")).read_bytes()).hexdigest(),
                                 expected_zip_hash)
                self.assertIn(f'href="{route}/index.html"', archive_page)
                self.assertIn("archive.html", inventory["html_routes"][route + "/index.html"]["inbound_html_references"])
            first_variant_hashes = {
                route: hashlib.sha256((site / route / "index.html").read_bytes()).hexdigest()
                for route in retained_mpc11
            }
            self.assertEqual(replay_mpc11_published_variants.preserve(site), retained_mpc11)
            self.assertEqual({
                route: hashlib.sha256((site / route / "index.html").read_bytes()).hexdigest()
                for route in retained_mpc11
            }, first_variant_hashes)
            self.assertEqual(inventory["html_route_count"], len(inventory["html_routes"]))
            expected_indexes = sum(route.endswith("/index.html") and route != "index.html"
                                   for route in inventory["html_routes"])
            self.assertEqual(inventory["navigation_transition"]["archive_index_route_count"], expected_indexes)
            self.assertEqual(inventory["navigation_transition"]["new_root_report_link_count"], 0)
            self.assertEqual(inventory["html_routes"]["existing-route/index.html"]["visibility"], "archive")
            self.assertIn("archive.html", inventory["html_routes"][strategy_summary]["inbound_html_references"])
            for report_id in (routes["b04_c"], routes["mpc06"], routes["mpc06_complete"], routes["mpc06_offline"], routes["review05"], routes["mpc11"], routes["mpc08"], routes["mpc07"], routes["mpc10"], routes["mpc11_studies"], routes["b04_source"]):
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

    def test_await_handoff_requires_parent_and_all_other_route_artifacts(self):
        sha = "a" * 40
        child = {"head_branch": "main", "event": "workflow_run",
                 "conclusion": "success", "head_sha": sha}
        parent = {"id": 42, "head_sha": sha, "head_branch": "main",
                  "name": "Algorithm report records and site", "event": "push",
                  "status": "completed", "conclusion": "success",
                  "created_at": "2026-11-11T09:00:00Z",
                  "updated_at": "2026-11-11T09:10:00Z"}
        marker = {"schema": "csl.pages-augmentation-source/1",
                  "report_run_id": 42, "head_sha": sha}
        with (mock.patch.object(await_pages_augmentation_runs, "get_json",
                                side_effect=[child, parent]) as get_json,
              mock.patch.object(await_pages_augmentation_runs, "run_marker",
                                return_value=marker),
              mock.patch.object(await_pages_augmentation_runs, "workflow_runs",
                                return_value=[parent]),
              mock.patch.object(await_pages_augmentation_runs, "matching_augmentation",
                                return_value={"conclusion": "success"}) as matching):
            result = await_pages_augmentation_runs.await_augmentations(
                "https://api.example", "owner/repository", "token", 99, 30, 1)
        self.assertEqual(result, 42)
        self.assertEqual(get_json.call_args_list, [
            mock.call("https://api.example", "owner/repository", "token", "actions/runs/99"),
            mock.call("https://api.example", "owner/repository", "token", "actions/runs/42"),
        ])
        self.assertEqual([call.args[3] for call in matching.call_args_list], [
            "mpc01-per-attempt-pages-augmentation.yml",
            "b04-c-pages-augmentation.yml",
        ])
        self.assertTrue(all(call.args[4] is parent for call in matching.call_args_list))

    def test_await_skips_artifacts_for_a_superseded_report_run(self):
        sha = "a" * 40
        child = {"head_branch": "main", "event": "workflow_run",
                 "conclusion": "success", "head_sha": sha}
        parent = {"id": 42, "head_sha": sha, "head_branch": "main",
                  "name": "Algorithm report records and site", "event": "push",
                  "status": "completed", "conclusion": "success"}
        newer = {"id": 43, "head_sha": sha, "head_branch": "main",
                 "event": "push", "status": "completed", "conclusion": "success",
                 "updated_at": "2026-11-11T09:12:00Z"}
        marker = {"schema": "csl.pages-augmentation-source/1",
                  "report_run_id": 42, "head_sha": sha}
        with (mock.patch.object(await_pages_augmentation_runs, "get_json",
                                side_effect=[child, parent]),
              mock.patch.object(await_pages_augmentation_runs, "run_marker",
                                return_value=marker),
              mock.patch.object(await_pages_augmentation_runs, "workflow_runs",
                                return_value=[newer]),
              mock.patch.object(await_pages_augmentation_runs, "matching_augmentation") as matching):
            result = await_pages_augmentation_runs.await_augmentations(
                "https://api.example", "owner/repository", "token", 99, 30, 1)
        self.assertIsNone(result)
        matching.assert_not_called()

    def test_aggregation_wait_job_precedes_single_cumulative_deployment(self):
        workflow = (ROOT / ".github/workflows/pages-augmentation-aggregation.yml").read_text(encoding="utf-8")
        self.assertIn("MPC-06 tube objective Pages augmentation", workflow)
        self.assertIn("await_pages_augmentation_runs.py", workflow)
        self.assertIn("needs: await", workflow)
        self.assertIn("augment_pages_bundle.py", workflow)
        self.assertIn("group: github-pages", workflow)
        self.assertIn("PAGES_SOURCE_RUN_ID", workflow)
        self.assertLess(workflow.index("pip install"), workflow.index("name: Stage and verify all Pages augmentations together"))

    def test_only_cumulative_workflow_can_publish_pages(self):
        workflows = ROOT / ".github/workflows"
        aggregation = workflows / "pages-augmentation-aggregation.yml"
        sources = [
            workflows / "algorithm-reports.yml",
            workflows / "mpc01-per-attempt-pages-augmentation.yml",
            workflows / "b04-c-pages-augmentation.yml",
            workflows / "mpc06-tube-objective-pages-augmentation.yml",
        ]
        self.assertIn("actions/deploy-pages@", aggregation.read_text(encoding="utf-8"))
        self.assertIn("actions/upload-pages-artifact@", aggregation.read_text(encoding="utf-8"))
        publishers = [path.name for path in workflows.glob("*.yml")
                      if "actions/deploy-pages@" in path.read_text(encoding="utf-8")]
        self.assertEqual(publishers, [aggregation.name])
        for path in sources:
            with self.subTest(workflow=path.name):
                source = path.read_text(encoding="utf-8")
                self.assertIn("actions/upload-pages-artifact@", source)
                self.assertNotIn("actions/deploy-pages@", source)
                self.assertNotIn("actions/configure-pages@", source)
                self.assertNotIn("pages: write", source)
                self.assertNotIn("id-token: write", source)
        base = sources[0].read_text(encoding="utf-8")
        self.assertIn("push:\n    branches: [main]", base)
        for path in sources[1:]:
            with self.subTest(workflow_run=path.name):
                source = path.read_text(encoding="utf-8")
                self.assertIn("workflow_run:", source)
                self.assertIn("workflows: [Algorithm report records and site]", source)
                self.assertIn("branches: [main]", source)
        aggregation_text = aggregation.read_text(encoding="utf-8")
        self.assertIn("Wait for every single-route artifact for this source revision", aggregation_text)
        self.assertIn("await_pages_augmentation_runs.py", aggregation_text)
        waiter = (ROOT / "scripts/reports/await_pages_augmentation_runs.py").read_text(encoding="utf-8")
        for name in ("mpc01-per-attempt-pages-augmentation.yml",
                     "b04-c-pages-augmentation.yml",
                     "mpc06-tube-objective-pages-augmentation.yml"):
            self.assertIn(name, waiter)


if __name__ == "__main__":
    unittest.main()
