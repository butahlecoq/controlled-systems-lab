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
    @staticmethod
    def native_inputs(root: Path) -> tuple[Path, Path]:
        native_bridge = root / "native-policy"
        native_bridge.write_bytes(b"test native policy bridge")
        cache = root / "CMakeCache.txt"
        cache.write_text(
            "\n".join(
                (
                    f"CSL_SOURCE_ROOT:UNINITIALIZED={run_campaign.ROOT}",
                    "CMAKE_BUILD_TYPE:STRING=Release",
                    "CMAKE_GENERATOR:INTERNAL=Ninja",
                    "CMAKE_CXX_COMPILER:FILEPATH=/usr/bin/c++",
                    "CMAKE_CXX_COMPILER_ID:STRING=GNU",
                    "CMAKE_CXX_COMPILER_VERSION:STRING=16.2.1",
                    "CSL_ENABLE_HIGHS:BOOL=ON",
                    "CSL_ENABLE_QHULL:BOOL=ON",
                    "CSL_ENABLE_CASADI:BOOL=ON",
                    "casadi_DIR:PATH=/opt/casadi",
                )
            )
            + "\n",
            encoding="utf-8",
        )
        return native_bridge, cache

    def test_freeze_round_trip_revalidates_current_source_catalogues(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bridge = root / "bridge"
            bridge.write_bytes(b"test bridge")
            native_bridge, cache = self.native_inputs(root)
            path = root / "campaign.json"
            with (
                patch.object(run_campaign, "ensure_clean_source"),
                patch.object(run_campaign, "ensure_reviewed_source"),
                patch.object(run_campaign, "ensure_clean_tracked_source"),
                patch.object(run_campaign, "runtime_packages", return_value={"casadi": "3.8.0"}),
            ):
                run_campaign.freeze(path, bridge, native_bridge, cache, 300, 300)
                with self.assertRaisesRegex(ValueError, "already exists and is immutable"):
                    run_campaign.freeze(path, bridge, native_bridge, cache, 300, 300)
                loaded = run_campaign.read_freeze(path, bridge, native_bridge, cache)

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
        self.assertEqual(loaded["native_policy"]["name"], "native-policy")
        self.assertEqual(loaded["native_policy"]["build_profile"]["casadi"], "ON")
        self.assertEqual(
            loaded["native_policy"]["build_profile"]["casadi_package_version"], "3.8.0"
        )

    def test_freeze_rejects_changed_native_policy_binary_or_build_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bridge = root / "bridge"
            bridge.write_bytes(b"test bridge")
            native_bridge, cache = self.native_inputs(root)
            path = root / "campaign.json"
            with (
                patch.object(run_campaign, "ensure_clean_source"),
                patch.object(run_campaign, "ensure_reviewed_source"),
                patch.object(run_campaign, "ensure_clean_tracked_source"),
            ):
                run_campaign.freeze(path, bridge, native_bridge, cache, 300, 300)
                native_bridge.write_bytes(b"changed native policy bridge")
                with self.assertRaisesRegex(ValueError, "native policy bridge.*changed"):
                    run_campaign.read_freeze(path, bridge, native_bridge, cache)
                native_bridge.write_bytes(b"test native policy bridge")
                cache.write_text(cache.read_text() + "CSL_ENABLE_CASADI:BOOL=OFF\n")
                with self.assertRaisesRegex(ValueError, "native policy build profile.*changed"):
                    run_campaign.read_freeze(path, bridge, native_bridge, cache)

    def test_campaign_provider_identity_is_a_sidecar_and_checks_executed_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            native_bridge = root / "native-policy"
            native_bridge.write_bytes(b"native policy")
            native_hash = run_campaign.sha256_file(native_bridge)
            attempt_path = root / "attempt"
            attempt_path.mkdir()
            request = {"requested": {"graph_id": "graph/one"}}
            attempt = {
                "preparation_receipt": {"adapter_receipt": {"executable_sha256": native_hash}}
            }
            manifest = {"runner": "evidence"}
            (attempt_path / "request.json").write_text(json.dumps(request), encoding="utf-8")
            (attempt_path / "attempt.json").write_text(json.dumps(attempt), encoding="utf-8")
            (attempt_path / "run-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            record = {
                "native_policy": {
                    "sha256": native_hash,
                    "build_cache_sha256": "cache-hash",
                    "build_profile": {"casadi": "ON"},
                },
                "environment": {"runtime_packages": {"casadi": "3.8.0"}},
                "source_commit": "source",
                "bridge": {"sha256": "bridge-hash"},
                "resource_profile": {"profile_id": "profile"},
            }
            item = {
                "task_name": "syn-nl-lv-01",
                "task_sha256": "task-hash",
                "graph_id": "graph/one",
                "graph_fingerprint": "fingerprint",
                "capability_manifest_sha256": "catalogue-hash",
            }

            run_campaign.write_campaign_runtime_sidecar(attempt_path, record, item)
            binding = json.loads((attempt_path / "campaign-runtime.json").read_text())
            self.assertEqual(binding["executed_native_policy_bridge_sha256"], native_hash)
            self.assertEqual(json.loads((attempt_path / "request.json").read_text()), request)
            self.assertEqual(json.loads((attempt_path / "run-manifest.json").read_text()), manifest)

            attempt["preparation_receipt"]["adapter_receipt"]["executable_sha256"] = "wrong"
            (attempt_path / "attempt.json").write_text(json.dumps(attempt), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "different from its campaign freeze"):
                run_campaign.write_campaign_runtime_sidecar(attempt_path, record, item)

    def test_started_campaign_intent_recovers_runner_attempt_without_rewriting_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output_root = root / "results"
            native_bridge = root / "native-policy"
            native_bridge.write_bytes(b"native policy")
            bridge = root / "bridge"
            bridge.write_bytes(b"bridge")
            item = {
                "task_name": "syn-nl-lv-01",
                "graph_id": "graph/one",
                "graph_fingerprint": "fingerprint",
                "task_sha256": "task-hash",
                "capability_manifest_sha256": "catalogue-hash",
            }
            record = {
                "source_commit": "source",
                "bridge": {"sha256": run_campaign.sha256_file(bridge)},
                "native_policy": {
                    "sha256": run_campaign.sha256_file(native_bridge),
                    "build_cache_sha256": "cache-hash",
                    "build_profile": {"casadi": "ON"},
                },
                "environment": {"runtime_packages": {"casadi": "3.8.0"}},
                "resource_profile": {"profile_id": "profile"},
                "graphs": [item],
            }
            journal_path = run_campaign.campaign_journal_path(output_root, item)
            journal = run_campaign.campaign_binding(record, item)
            journal.update({"state": "started", "started_unix_ns": 1})
            run_campaign.write_json_atomically(journal_path, journal)
            attempt_path = output_root / item["task_name"] / "attempts" / "attempt-1"
            attempt_path.mkdir(parents=True)
            request = {
                "source_commit": "source",
                "requested": {"graph_id": "graph/one", "resource_profile_id": "profile"},
            }
            (attempt_path / "request.json").write_text(json.dumps(request))
            native_hash = run_campaign.sha256_file(native_bridge)
            attempt_data = {
                "attempt_id": "attempt-1",
                "status": "failed",
                "preparation_receipt": {"adapter_receipt": {"executable_sha256": native_hash}},
            }
            (attempt_path / "attempt.json").write_text(json.dumps(attempt_data))

            recovered = list(run_campaign.iter_verified_attempts(output_root, record))

            self.assertEqual(len(recovered), 1)
            self.assertEqual(json.loads(journal_path.read_text())["state"], "recovered")
            self.assertEqual(json.loads((attempt_path / "request.json").read_text()), request)
            self.assertEqual(json.loads((attempt_path / "attempt.json").read_text()), attempt_data)
            self.assertTrue((attempt_path / "campaign-runtime.json").is_file())
            sidecar_path = attempt_path / "campaign-runtime.json"
            sidecar = json.loads(sidecar_path.read_text())
            self.assertEqual(sidecar["executed_native_policy_bridge_sha256"], native_hash)
            sidecar["executed_native_policy_bridge_sha256"] = None
            sidecar_path.write_text(json.dumps(sidecar))
            self.assertEqual(list(run_campaign.iter_verified_attempts(output_root, record)), [])

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

    def test_paired_method_schedule_excludes_warmup_and_alternates_measured_order(self):
        self.assertEqual(
            run_campaign.paired_method_schedule(5),
            [
                {"phase": "warmup", "repetition": 0, "order": ["A", "B"]},
                {"phase": "measured", "repetition": 1, "order": ["A", "B"]},
                {"phase": "measured", "repetition": 2, "order": ["B", "A"]},
                {"phase": "measured", "repetition": 3, "order": ["A", "B"]},
                {"phase": "measured", "repetition": 4, "order": ["B", "A"]},
                {"phase": "measured", "repetition": 5, "order": ["A", "B"]},
            ],
        )
        with self.assertRaisesRegex(ValueError, "at least one measured repetition"):
            run_campaign.paired_method_schedule(0)

    def test_fixed_tail_representation_matrix_contains_each_unordered_pair_once(self):
        pairs = run_campaign.fixed_tail_representation_pairs()

        self.assertEqual(len(pairs), 10)
        self.assertEqual(len(set(pairs)), 10)
        self.assertIn(("polytope", "zonotope"), pairs)
        self.assertNotIn(("zonotope", "polytope"), pairs)

    def test_paired_graph_selection_requires_matched_task_action_and_solver(self):
        tasks = ("syn-nl-lv-01", "earth-orbit", "syn-nl-fuel-01")
        graphs = []
        for task in tasks:
            for side, representation in (("A", "box"), ("B", "ellipsoid")):
                graphs.append(
                    {
                        "task_name": task,
                        "task_id": task + "/1",
                        "graph_id": f"{task}/{side}",
                        "task_sha256": "task-hash",
                        "action_profile_id": "continuous-action/1",
                        "execution": {"id": "rk4/1"},
                        "controller": {
                            "id": f"method-{side}/1",
                            "solver": {"provider": "ipopt"},
                        },
                        "role_bindings": {
                            "control_optimizer": {"id": "ipopt"},
                            "representation": {"id": representation},
                        },
                    }
                )
        record = {"graphs": graphs}

        selected = run_campaign.select_paired_graphs(record, "method-A/1", "method-B/1")

        self.assertEqual(set(selected), set(tasks))
        self.assertEqual(selected[tasks[0]]["A"]["graph_id"], tasks[0] + "/A")
        record["graphs"][-1]["action_profile_id"] = "different-action/1"
        with self.assertRaisesRegex(ValueError, "do not share task, action, execution and solver"):
            run_campaign.select_paired_graphs(record, "method-A/1", "method-B/1")

    def test_comparison_pack_request_maps_completed_run_to_passed_measurement(self):
        task_name = "syn-nl-lv-01"
        methods = {
            "A": {
                "controller": {"id": "native-fixed-tail-polytope-ipopt/1", "version": "1"},
                "graph_fingerprint": "a" * 64,
                "source_files": [],
            },
            "B": {
                "controller": {"id": "native-fixed-tail-zonotope-ipopt/1", "version": "1"},
                "graph_fingerprint": "b" * 64,
                "source_files": [],
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            events = {}
            for side in ("A", "B"):
                attempt_path = root / side
                attempt_path.mkdir()
                (attempt_path / "attempt.json").write_text(
                    json.dumps(
                        {
                            "attempt_id": f"attempt-{side}",
                            "overall_status": "complete",
                            "preparation_receipt": {
                                "adapter_receipt": {"executable_sha256": "c" * 64}
                            },
                        }
                    ),
                    encoding="utf-8",
                )
                (attempt_path / "run-manifest.json").write_text(
                    json.dumps({"claim": "paired timing pilot"}), encoding="utf-8"
                )
                events[(task_name, "measured", 1, side)] = {
                    "attempt": str(attempt_path),
                    "order_index": 1 if side == "A" else 2,
                    "end_to_end_wall_seconds": 12.0,
                    "worker_wall_seconds": 4.0,
                }

            request = run_campaign.build_comparison_pack_request(
                {
                    "source_commit": "d" * 40,
                    "resource_profile": {"profile_id": "worker-wall-300-cpu-300/1"},
                    "native_policy": {
                        "sha256": "c" * 64,
                        "build_profile": {
                            "cxx_compiler_id": "GNU",
                            "cxx_compiler_version": "16.2.1",
                            "build_type": "Release",
                        },
                    },
                },
                task_name,
                methods,
                events,
                1,
            )

        attempts = [method["attempts"][0] for method in request["methods"]]
        self.assertEqual([attempt["status"] for attempt in attempts], ["completed", "completed"])
        self.assertEqual(
            [attempt["measurement"]["status"] for attempt in attempts], ["passed", "passed"]
        )

    def test_paired_timing_rejects_events_from_another_freeze(self):
        tasks = ("syn-nl-lv-01", "earth-orbit", "syn-nl-fuel-01")
        controllers = {
            "A": "native-fixed-tail-polytope-ipopt/1",
            "B": "native-fixed-tail-zonotope-ipopt/1",
        }
        graphs = [
            {
                "task_name": task,
                "task_id": task + "/1",
                "graph_id": f"{task}/{side}",
                "graph_fingerprint": "a" * 64,
                "task_sha256": "b" * 64,
                "action_profile_id": "same-profile",
                "execution": {"id": "rk4/1"},
                "controller": {"id": controller, "solver": {"provider": "ipopt"}},
                "role_bindings": {"control_optimizer": {"id": "ipopt"}},
            }
            for task in tasks
            for side, controller in controllers.items()
        ]
        record = {
            "source_commit": "c" * 40,
            "bridge": {"sha256": "d" * 64},
            "native_policy": {"sha256": "e" * 64},
            "resource_profile": {"profile_id": "profile/1"},
            "graphs": graphs,
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            freeze = root / "freeze.json"
            freeze.write_text("frozen campaign")
            output = root / "results"
            output.mkdir()
            event = {
                "schema": "csl.closed-loop-paired-timing-event/2",
                "freeze_sha256": "0" * 64,
                "source_commit": record["source_commit"],
                "bridge_sha256": record["bridge"]["sha256"],
                "native_policy_sha256": record["native_policy"]["sha256"],
                "resource_profile_id": record["resource_profile"]["profile_id"],
                "task_name": tasks[0],
                "phase": "warmup",
                "repetition": 0,
                "side": "A",
                "try_index": 1,
                "state": "completed",
            }
            (output / "paired-timing-events.jsonl").write_text(json.dumps(event) + "\n")
            with self.assertRaisesRegex(ValueError, "different freeze"):
                run_campaign.run_paired_timing(
                    record, freeze, output, root / "bridge", root / "native", root / "packer"
                )

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
            native_bridge = root / "native-policy"
            native_bridge.write_bytes(b"native policy")
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
                "native_policy": {
                    "name": native_bridge.name,
                    "sha256": run_campaign.sha256_file(native_bridge),
                    "build_cache_sha256": "frozen-cache-hash",
                    "build_profile": {"casadi": "ON"},
                },
                "environment": {"runtime_packages": {"casadi": "3.8.0"}},
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
            (existing / "campaign-runtime.json").write_text(
                json.dumps(run_campaign.campaign_binding(record, record["graphs"][0], existing))
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
                patch.object(run_campaign, "write_campaign_runtime_sidecar"),
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
                summary = run_campaign.run_campaign(
                    record, output_root, bridge, native_bridge, max_attempts=1
                )

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
