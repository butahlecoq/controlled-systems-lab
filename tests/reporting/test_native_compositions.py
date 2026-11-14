"""Check exhaustive provider requests and exact selection through the common runner."""

from __future__ import annotations

import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmarks/reporting/closed_loop"))
import capabilities  # noqa: E402
import native_compositions  # noqa: E402
import run_closed_loop  # noqa: E402

from contracts import canonical_sha256, load_task  # noqa: E402


class NativeCompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = native_compositions.build_manifest()

    def test_candidate_accounting(self):
        rows = self.manifest["candidates"]
        self.assertEqual(len(rows), 480)
        self.assertEqual(len({r["candidate_id"] for r in rows}), 480)
        self.assertEqual(sum(r["status"] == "requestable" for r in rows), 460)
        self.assertEqual(sum(r["status"] == "incompatible" for r in rows), 20)
        self.assertEqual(len(self.manifest["graphs"]), 460)
        self.assertEqual(len({r["graph_id"] for r in self.manifest["graphs"]}), 460)

    def test_default_profiles_keep_their_canonical_graphs(self):
        defaults = {g["graph_id"]: g for g in capabilities.build_native_manifest()["graphs"]}
        aliases = [
            c
            for c in self.manifest["candidates"]
            if c.get("canonicalization") == "existing-default-graph"
        ]
        self.assertEqual(len(aliases), 15)
        graphs = {g["graph_id"]: g for g in self.manifest["graphs"]}
        for alias in aliases:
            identity = alias["canonical_graph_id"]
            self.assertEqual(graphs[identity], defaults[identity])

    def test_priorities_are_explicit_and_source_index_has_no_lp(self):
        priorities = []
        for candidate in self.manifest["candidates"]:
            options = candidate["factory_options"]
            lp = options["vertex_lp_provider"]
            if lp == "not_used":
                self.assertEqual(
                    options["reachable_set_method"]["id"], "csl.geometry.affine-sum.source-index"
                )
                if candidate["status"] == "incompatible":
                    self.assertNotEqual(candidate["dimension"], 2)
                    self.assertIsNone(candidate["canonical_graph_id"])
                    self.assertEqual(candidate["reason"]["field"], "points.dimension")
            elif lp["id"] == "phase-one-priority-tie":
                priorities.append(candidate)
                self.assertEqual(options["vertex_lp_priority_policy"], "structural-column-index/v1")
        self.assertEqual(len(priorities), 150)

    def test_exact_selection_uses_the_requested_provider_tuple(self):
        graph = next(
            g
            for g in self.manifest["graphs"]
            if g["controller"]["factory_options"].get("vertex_lp_priority_policy")
        )
        task_name = graph["task_id"].split("/")[0]
        _, selected = capabilities.resolve_graph(
            load_task(task_name),
            graph["action_profile_id"],
            manifest_path=capabilities.COMPOSITIONS_MANIFEST,
            graph_id=graph["graph_id"],
        )
        self.assertEqual(selected, graph)
        with self.assertRaisesRegex(ValueError, "no unique"):
            capabilities.resolve_graph(
                load_task(task_name),
                graph["action_profile_id"],
                graph["controller"]["id"],
                manifest_path=capabilities.COMPOSITIONS_MANIFEST,
            )

    def test_common_runner_selects_an_explicit_noncomposition_catalogue(self):
        manifest = capabilities.validate_manifest(manifest_path=capabilities.MANIFEST)
        graph = manifest["graphs"][0]
        task_name = (
            graph["task_id"].split("/")[0] if graph["task_id"].startswith("syn-") else "earth-orbit"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            attempt = run_closed_loop.run_task(
                task_name,
                root,
                root / "missing-bridge",
                graph_id=graph["graph_id"],
                capability_manifest_path=capabilities.MANIFEST,
            )
            self.assertEqual(attempt["status"], "refused")
            request = json.loads((Path(attempt["attempt"]) / "request.json").read_text())
            self.assertEqual(request["requested"]["graph_id"], graph["graph_id"])
            refusal = json.loads((Path(attempt["attempt"]) / "resolution-refusal.json").read_text())
            self.assertIn("common execution bridge does not exist", refusal["reason"])

    def test_signed_but_incorrect_exclusion_ledger_is_rejected(self):
        forged = copy.deepcopy(self.manifest)
        excluded = next(c for c in forged["candidates"] if c["status"] == "incompatible")
        excluded["reason"]["detail"] = "silently excluded"
        with tempfile.TemporaryDirectory() as directory:
            sidecar = Path(directory) / "manifest.sha256"
            sidecar.write_text(canonical_sha256(forged))
            with patch.object(capabilities, "COMPOSITIONS_SIDECAR", sidecar):
                with self.assertRaisesRegex(ValueError, "candidates or graphs"):
                    capabilities.validate_manifest(
                        forged, manifest_path=capabilities.COMPOSITIONS_MANIFEST
                    )

    def test_cli_refuses_unknown_graph_before_native_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            argv = [
                "run_closed_loop",
                "--task",
                "syn-nl-lv-01",
                "--bridge",
                str(root / "missing-binary"),
                "--output-root",
                str(root),
                "--graph-id",
                "not-a-source-bound-graph",
            ]
            with patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(run_closed_loop.main(), 1)
            requests = list(root.glob("*/attempts/*/request.json"))
            self.assertEqual(len(requests), 1)
            request = json.loads(requests[0].read_text())
            self.assertEqual(request["requested"]["graph_id"], "not-a-source-bound-graph")
            attempts = list(root.glob("*/attempts/*/attempt.json"))
            record = json.loads(attempts[0].read_text())
            self.assertEqual(record["algorithm_status"], "refused")
            self.assertIn("no unique", record["refusal"]["reason"])


if __name__ == "__main__":
    unittest.main()
