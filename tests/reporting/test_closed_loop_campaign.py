"""Check frozen catalogue accounting and append-only campaign resumption."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmarks/reporting/closed_loop"))
import capabilities  # noqa: E402
import run_campaign  # noqa: E402


class ClosedLoopCampaignTests(unittest.TestCase):
    def test_freeze_round_trip_revalidates_current_source_catalogues(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bridge = root / "bridge"
            bridge.write_bytes(b"test bridge")
            path = root / "campaign.json"
            with (
                patch.object(run_campaign, "ensure_clean_source"),
                patch.object(run_campaign, "ensure_reviewed_source"),
                patch.object(run_campaign, "ensure_clean_tracked_source"),
            ):
                run_campaign.freeze(path, bridge, 300, 300)
                with self.assertRaisesRegex(ValueError, "already exists and is immutable"):
                    run_campaign.freeze(path, bridge, 300, 300)
                loaded = run_campaign.read_freeze(path, bridge)

        self.assertEqual(loaded["source_commit"], run_campaign.source_commit())
        self.assertEqual(len(loaded["catalogues"]), 4)
        self.assertEqual(
            loaded["candidate_counts"]["canonical_active_graphs"], len(loaded["graphs"])
        )
        self.assertEqual(loaded["resource_profile"]["suite_worker_count"], 1)
        self.assertIsNone(loaded["resource_profile"]["suite_memory_allocation_bytes"])
        self.assertEqual(
            loaded["resource_profile"]["suite_memory_request_policy"],
            "min(2 GiB, 75% of available memory at attempt start); recorded by the runner",
        )
        self.assertEqual(loaded["bridge"]["name"], "bridge")

    def test_freeze_requires_a_commit_reachable_from_reviewed_main(self):
        with patch.object(
            run_campaign.subprocess,
            "check_call",
            side_effect=subprocess.CalledProcessError(1, "git merge-base"),
        ):
            with self.assertRaisesRegex(ValueError, "reachable from origin/main"):
                run_campaign.ensure_reviewed_source()

    def test_reviewed_source_gate_checks_commit_ancestry(self):
        with patch.object(run_campaign.subprocess, "check_call") as check_call:
            run_campaign.ensure_reviewed_source()

        check_call.assert_called_once_with(
            ["git", "merge-base", "--is-ancestor", "HEAD", "refs/remotes/origin/main"],
            cwd=run_campaign.ROOT,
        )

    def test_inventory_reconciles_all_catalogue_graph_references(self):
        sources, graphs, candidates = run_campaign.catalogue_inventory()
        expected_ids = set()
        expected_candidate_count = 0
        for manifest_path in run_campaign.MANIFEST_PATHS:
            manifest = capabilities.validate_manifest(manifest_path=manifest_path)
            expected_ids.update(graph["graph_id"] for graph in manifest["graphs"])
            expected_candidate_count += len(manifest.get("candidates", []))

        graph_ids = [graph["graph_id"] for graph in graphs]
        self.assertEqual(len(graph_ids), len(set(graph_ids)))
        self.assertEqual(set(graph_ids), expected_ids)
        self.assertEqual(
            sum(source["graph_count"] for source in sources),
            sum(
                len(capabilities.validate_manifest(manifest_path=path)["graphs"])
                for path in run_campaign.MANIFEST_PATHS
            ),
        )
        self.assertEqual(len(candidates), expected_candidate_count)
        self.assertEqual(
            {candidate["status"] for candidate in candidates}, {"requestable", "incompatible"}
        )
        self.assertTrue(all(graph["catalogue_path"] in graph["catalogues"] for graph in graphs))
        self.assertTrue(all(graph["admission"]["status"] == "admitted" for graph in graphs))

    def test_bounded_campaign_order_interleaves_all_three_tasks(self):
        graphs = [
            {"task_name": "syn-nl-lv-01", "graph_id": "lv-1"},
            {"task_name": "syn-nl-lv-01", "graph_id": "lv-2"},
            {"task_name": "earth-orbit", "graph_id": "orbit-1"},
            {"task_name": "syn-nl-fuel-01", "graph_id": "fuel-1"},
            {"task_name": "earth-orbit", "graph_id": "orbit-2"},
            {"task_name": "syn-nl-fuel-01", "graph_id": "fuel-2"},
            {"task_name": "syn-nl-fuel-01", "graph_id": "fuel-3"},
        ]

        ordered = run_campaign.campaign_order(graphs)

        self.assertEqual(
            [(graph["task_name"], graph["graph_id"]) for graph in ordered],
            [
                ("syn-nl-lv-01", "lv-1"),
                ("earth-orbit", "orbit-1"),
                ("syn-nl-fuel-01", "fuel-1"),
                ("syn-nl-lv-01", "lv-2"),
                ("earth-orbit", "orbit-2"),
                ("syn-nl-fuel-01", "fuel-2"),
                ("syn-nl-fuel-01", "fuel-3"),
            ],
        )
        with self.assertRaisesRegex(ValueError, "unknown task"):
            run_campaign.campaign_order([{"task_name": "unknown"}])

    def test_attempt_classification_keeps_refusal_reason_and_outcome(self):
        with tempfile.TemporaryDirectory() as directory:
            attempt_path = Path(directory) / "attempt.json"
            (Path(directory) / "resolution-refusal.json").write_text(
                json.dumps({"reason": "selected LP backend is unavailable"})
            )
            category, reason = run_campaign.classify_attempt(
                {"overall_status": "refused", "algorithm_status": "refused"}, attempt_path
            )

        self.assertEqual(category, "backend_unavailable")
        self.assertEqual(reason, "selected LP backend is unavailable")
        self.assertEqual(
            run_campaign.classify_attempt({"overall_status": "timed_out"}, attempt_path),
            ("timed_out", None),
        )

    def test_resume_skips_existing_pairs_without_replacing_attempts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output_root = root / "results"
            existing = output_root / "syn-nl-lv-01" / "attempts" / "existing"
            existing.mkdir(parents=True)
            (existing / "request.json").write_text(
                json.dumps(
                    {
                        "source_commit": "frozen-source",
                        "requested": {
                            "graph_id": "graph/already-attempted",
                            "resource_profile_id": "worker-wall-300-cpu-300/1",
                        },
                    }
                )
            )
            original_attempt = {"attempt_id": "existing", "status": "failed"}
            (existing / "attempt.json").write_text(json.dumps(original_attempt))
            bridge = root / "bridge"
            bridge.write_bytes(b"bridge")
            record = {
                "source_commit": "frozen-source",
                "bridge": {"name": bridge.name, "sha256": run_campaign.sha256_file(bridge)},
                "resource_profile": {
                    "profile_id": "worker-wall-300-cpu-300/1",
                    "attempt_wall_seconds": 300,
                    "attempt_cpu_seconds": 300,
                },
                "graphs": [
                    {
                        "task_name": "syn-nl-lv-01",
                        "graph_id": "graph/already-attempted",
                        "graph_fingerprint": "fingerprint-1",
                        "task_sha256": "task-hash",
                        "catalogue_path": "catalogue.json",
                        "capability_manifest_sha256": "manifest-hash",
                    },
                    {
                        "task_name": "syn-nl-lv-01",
                        "graph_id": "graph/missing",
                        "graph_fingerprint": "fingerprint-2",
                        "task_sha256": "task-hash",
                        "catalogue_path": "catalogue.json",
                        "capability_manifest_sha256": "manifest-hash",
                    },
                ],
                "candidate_counts": {"canonical_active_graphs": 2},
                "candidates": [],
            }
            (existing / "run-manifest.json").write_text(
                json.dumps(
                    {
                        "source_commit": "frozen-source",
                        "task_sha256": "task-hash",
                        "graph_id": "graph/already-attempted",
                        "graph_fingerprint": "fingerprint-1",
                        "capability_manifest_sha256": "manifest-hash",
                        "bridge_sha256": run_campaign.sha256_file(bridge),
                        "resource_profile_id": "worker-wall-300-cpu-300/1",
                    }
                )
            )
            result = {
                "attempt": str(output_root / "syn-nl-lv-01" / "attempts" / "new-attempt"),
                "overall_status": "failed",
                "algorithm_status": "failed",
                "postcheck_status": "not_run",
                "render_status": "not_run",
                "completed_holds": 0,
            }
            with (
                patch.object(run_campaign.run_closed_loop, "run_task", return_value=result) as run,
                patch.object(
                    run_campaign.run_closed_loop,
                    "write_coverage",
                    return_value=output_root / "runner-coverage.json",
                ),
                patch.object(
                    run_campaign,
                    "build_campaign_coverage",
                    return_value={"schema": "campaign-coverage-test/1"},
                ),
            ):
                summary = run_campaign.run_campaign(record, output_root, bridge, max_attempts=1)

            run.assert_called_once()
            self.assertEqual(run.call_args.args[0], "syn-nl-lv-01")
            self.assertEqual(run.call_args.kwargs["graph_id"], "graph/missing")
            self.assertEqual(summary["attempted_this_run"], 1)
            self.assertEqual(summary["skipped_existing_attempts"], 1)
            self.assertEqual(summary["remaining"], 0)
            self.assertEqual(json.loads((existing / "attempt.json").read_text()), original_attempt)
            self.assertTrue((output_root / "campaign-events.jsonl").is_file())


if __name__ == "__main__":
    unittest.main()
