"""The finite graph universe and current source-owned factory catalogues coexist."""

from __future__ import annotations

import json
import sys
import unittest
import copy
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/catalogue"))
sys.path.insert(0, str(ROOT / "benchmarks/reporting/closed_loop"))
import capabilities  # noqa: E402
from full_catalogue import (  # noqa: E402
    controller_catalogue,
    controller_graphs,
    predecessor_graphs,
    source_bound_capability_candidates,
)
from check_full_catalogue import check_current_factory_rows  # noqa: E402


class FullCatalogueDiscoveryTests(unittest.TestCase):
    def test_discovers_current_factories_without_claiming_runtime_preparation(self) -> None:
        candidates = source_bound_capability_candidates(ROOT)

        self.assertEqual(len(candidates), 65)
        self.assertEqual(
            sum(row["controller_route"] == "native_graph_policy" for row in candidates), 30
        )
        self.assertEqual(
            sum(row["controller_route"] == "continuous_history" for row in candidates), 20
        )
        self.assertEqual(
            sum(row["controller_route"] == "native_fixed_tail" for row in candidates), 15
        )
        self.assertEqual(
            {row["task_id"] for row in candidates},
            {
                "syn-nl-lv-01/continuous-receding/1",
                "env717-earth-orbit/continuous-receding/1",
                "syn-nl-fuel-01/continuous-receding/1",
            },
        )
        self.assertTrue(all(row["status"] == "preparation_not_attempted" for row in candidates))
        self.assertTrue(
            all(
                row["catalogue_source"]["declared_admission"]["status"] == "admitted"
                for row in candidates
            )
        )
        self.assertTrue(
            all(
                row["catalogue_source"]["runtime_preparation"] == "not_attempted"
                for row in candidates
            )
        )
        self.assertTrue(
            all(
                row["catalogue_source"]["factory_registration"] == "registered"
                for row in candidates
            )
        )
        self.assertTrue(
            all(row["catalogue_source"]["runtime_binary"] == "not_inspected" for row in candidates)
        )
        self.assertEqual(len({row["graph_fingerprint"] for row in candidates}), 65)
        self.assertEqual(
            len(
                {
                    (
                        row["task_id"],
                        row["action_profile_id"],
                        row["objective_id"],
                        row["controller_id"],
                        json.dumps(row["module_tuple"], sort_keys=True),
                    )
                    for row in candidates
                }
            ),
            65,
        )

    def test_factory_roles_and_provider_choices_are_kept_verbatim(self) -> None:
        candidates = source_bound_capability_candidates(ROOT)
        graph = next(row for row in candidates if row["controller_route"] == "native_graph_policy")
        history = next(row for row in candidates if row["controller_route"] == "continuous_history")

        self.assertEqual(
            graph["module_tuple"]["controller"]["factory_options"]["conversion_provider"],
            "not_used",
        )
        self.assertEqual(graph["module_tuple"]["role_bindings"]["converter"], "not_used")
        self.assertEqual(history["module_tuple"]["role_bindings"]["vertex_lp"], "not_used")
        self.assertEqual(history["module_tuple"]["role_bindings"]["converter"], "not_used")
        self.assertEqual(
            history["module_tuple"]["operation_roles"], {"controller.solve": "control_optimizer"}
        )
        self.assertTrue(graph["catalogue_source"]["declared_admission"]["basis"])

    def test_current_discovery_appends_without_rewriting_historical_candidates(self) -> None:
        inventory = json.loads(
            (ROOT / "docs/catalogue/module-composition-inventory-v1.json").read_text()
        )
        unavailable_receipts = {
            "routes": [
                {
                    "task_id": f"{task}/continuous-receding/1",
                    "status": "backend_unavailable",
                    "first_unmet": {
                        "field": "python.dependency.test-fixture",
                        "reason": "This source expansion test does not prepare MPC11.",
                    },
                }
                for task in ("syn-nl-lv-01", "syn-nl-fuel-01")
            ]
        }
        original = controller_graphs(
            ROOT,
            inventory,
            unavailable_receipts,
            {"qhull": True, "highs": True},
        )
        self.assertEqual(len(original), 3318)

        combined = controller_catalogue(original, ROOT)

        self.assertEqual(combined[: len(original)], original)
        self.assertEqual(len(combined), 3383)
        self.assertEqual(
            {row["controller_route"] for row in original},
            {
                "csl.synthesis.reach-back",
                "csl.synthesis.strategy-b",
                "csl.synthesis.ts01-analytic",
                "csl::optimization::finite_action_nominal",
                "csl::reachability::nominal_forward",
                "csl::reachability::prepare_nominal_predecessor",
                "csl::reachability::finite_feedback::solve",
                "csl::optimization::finite_causal_minimax::solve",
                "benchmarks/reporting/mpc11/run_nmpc.py",
            },
        )
        self.assertEqual(
            [row["graph_id"] for row in combined[: len(original)]],
            [row["graph_id"] for row in original],
        )
        backends = {"qhull": True, "highs": True}
        self.assertEqual(
            predecessor_graphs(combined, inventory, backends),
            predecessor_graphs(original, inventory, backends),
        )

    def test_factory_or_dependency_mismatch_fails_closed(self) -> None:
        path = ROOT / "docs/catalogue/closed-loop-native-capabilities-v1.json"
        manifest = json.loads(path.read_text())
        manifest["graphs"][0]["controller"]["factory_options"]["conversion_provider"] = {
            "id": "invented-converter",
            "version": "1",
        }
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            capabilities.validate_manifest(value=manifest, manifest_path=path)

    def test_factory_manifest_omissions_fail_source_definition_validation(self) -> None:
        path = ROOT / "docs/catalogue/closed-loop-native-capabilities-v1.json"
        manifest = json.loads(path.read_text())
        manifest["graphs"] = manifest["graphs"][1:]
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            capabilities.validate_manifest(value=manifest, manifest_path=path)

    def test_factory_registration_must_match_the_declared_adapter(self) -> None:
        path = ROOT / "docs/catalogue/closed-loop-native-capabilities-v1.json"
        manifest = json.loads(path.read_text())
        manifest["graphs"][0]["controller"]["policy_factory"] = "unregistered:create_policy"
        with mock.patch.object(capabilities, "validate_manifest", return_value=manifest):
            with self.assertRaisesRegex(
                ValueError, "does not select its registered policy factory"
            ):
                source_bound_capability_candidates(ROOT)

    def test_checker_binds_factory_rows_to_source_task_graphs(self) -> None:
        candidates = source_bound_capability_candidates(ROOT)
        check_current_factory_rows(candidates, ROOT)

        role_row = next(
            row for row in candidates if row["controller_route"] == "continuous_history"
        )
        mutations = {
            "task": lambda row: row.update(task_id="invented-physical-task/1"),
            "action": lambda row: row.update(action_profile_id="invented-action/1"),
            "objective": lambda row: row.update(objective_id="invented-objective/1"),
            "module-role": lambda row: row["module_tuple"]["role_bindings"].update(
                converter="invented-converter"
            ),
            "fingerprint": lambda row: row.update(graph_fingerprint="0" * 64),
            "source-id": lambda row: row.update(graph_id="invented-source-graph/1"),
        }
        for label, mutate in mutations.items():
            with self.subTest(identity_field=label):
                selected = copy.deepcopy(candidates)
                target = next(row for row in selected if row["graph_id"] == role_row["graph_id"])
                mutate(target)
                with self.assertRaises(AssertionError):
                    check_current_factory_rows(selected, ROOT)


if __name__ == "__main__":
    unittest.main()
