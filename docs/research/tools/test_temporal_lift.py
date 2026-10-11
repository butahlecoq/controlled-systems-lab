"""Public exact-reference checks; no archive, solver or checkout mutation."""
from pathlib import Path
import ast
import copy
import json
import subprocess
import sys
from types import SimpleNamespace
import unittest


def verifier_function():
    """Load the real validator without the script's snapshot-writing entrypoint.

    Only imports and the function definition execute. Negative inputs are deep
    copies in memory; neither reports nor tracked provenance are rewritten.
    """
    path = Path(__file__).with_name("verify_docs.py")
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    definitions = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))
                   or isinstance(node, ast.FunctionDef) and node.name == "verify_proof_provenance"]
    namespace = {}
    exec(compile(ast.Module(body=definitions, type_ignores=[]), str(path), "exec"), namespace)
    return namespace["verify_proof_provenance"]


class TemporalLiftTests(unittest.TestCase):
    def test_optimized_cli_runs_all_literal_checks(self):
        result = subprocess.run(
            [sys.executable, "-B", "-O", str(Path(__file__).with_name("check_temporal_lift.py"))],
            text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [
            "PASS temporal_affine_ltv_states",
            "PASS temporal_inverse_recovery",
            "PASS temporal_first_step_and_stage_bounds",
            "PASS temporal_rate_scaling",
            "PASS temporal_homogeneous_slice",
            "PASS temporal_uncoupled_counterexample",
            "PASS temporal_terminal_memory_fibre",
            "PASS temporal_marginal_coverage",
            "PASS temporal_four_state_embedding",
            "9 exact literal checks passed; continuum claims require the report proofs.",
        ])

    def test_wrong_arithmetic_is_rejected_under_optimization(self):
        code = """import check_temporal_lift as c
from unittest.mock import patch
wrong = c.observations()
wrong['temporal_inverse_recovery'] = ((0, 0, 0), (0, 0, 0))
with patch.object(c, 'observations', return_value=wrong):
    c.check_temporal_lift()
"""
        result = subprocess.run([sys.executable, "-B", "-O", "-c", code],
                                cwd=Path(__file__).parent, text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("ValueError: temporal_inverse_recovery:", result.stderr)


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.research = Path(__file__).resolve().parents[1]
        self.provenance = json.loads((self.research / "proof-audit-provenance.json").read_text(encoding="utf-8"))
        inventory = json.loads((self.research / "inventory.json").read_text(encoding="utf-8"))
        selected = json.loads((self.research / "archive-selected-sources.json").read_text(encoding="utf-8"))["selected_sources"]
        self.registered = {e["id"]: e for e in inventory + selected}
        self.verify = verifier_function()

    def test_valid_three_audit_record_with_python_and_pascal_anchors(self):
        self.assertEqual(self.verify(self.provenance, self.registered, self.research), {
            "sources": 20, "anchors": 63, "audits": 3, "review_events": 12,
            "findings": 6, "literal_checks": 18,
        })

    def test_stale_public_report_hash_is_not_an_antecedent_identity(self):
        bad = copy.deepcopy(self.provenance)
        bad["public_report_sha256"]["temporal-lift-source-audit"] = bad["audits"][-1]["final_antecedent_sha256"]
        with self.assertRaisesRegex(ValueError, "Public report hash differs"):
            self.verify(bad, self.registered, self.research)

    def test_report_hashes_survive_checkout_line_ending_conversion(self):
        class MemoryReports:
            def __init__(self, research, separator):
                self.research, self.separator = research, separator

            def __truediv__(self, name):
                raw = (self.research / name).read_bytes()
                converted = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n").replace(b"\n", self.separator)
                return SimpleNamespace(read_bytes=lambda: converted)

        for separator in (b"\n", b"\r\n"):
            with self.subTest(separator=separator):
                result = self.verify(self.provenance, self.registered, MemoryReports(self.research, separator))
                self.assertEqual(result, {"sources": 20, "anchors": 63, "audits": 3,
                    "review_events": 12, "findings": 6, "literal_checks": 18})

    def test_public_hash_coverage_is_complete(self):
        bad = copy.deepcopy(self.provenance)
        del bad["public_report_sha256"]["temporal-lift-source-audit"]
        with self.assertRaisesRegex(ValueError, "Public report hash coverage"):
            self.verify(bad, self.registered, self.research)

    def test_digest_convention_must_be_declared(self):
        bad = copy.deepcopy(self.provenance)
        bad["public_report_digest_convention"] = "raw-checkout-bytes"
        with self.assertRaisesRegex(ValueError, "Public report digest convention"):
            self.verify(bad, self.registered, self.research)

    def test_nonnewline_report_tampering_is_rejected(self):
        research = self.research

        class TamperedReports:
            def __truediv__(self, name):
                raw = (research / name).read_bytes() + b"Changed mathematical statement."
                return SimpleNamespace(read_bytes=lambda: raw)

        with self.assertRaisesRegex(ValueError, "Public report hash differs"):
            self.verify(self.provenance, self.registered, TamperedReports())

    def test_unknown_code_extension_is_rejected(self):
        bad = copy.deepcopy(self.registered)
        bad["L26"]["path"] = "not-code.txt"
        with self.assertRaisesRegex(ValueError, "Code anchor for non-code"):
            self.verify(self.provenance, bad, self.research)

    def test_review_chain_and_reference_corruption_are_rejected(self):
        mutations = (
            (lambda d: d["audits"][-1]["review_events"][1].update(result_version_sha256="0" * 64), "Broken fix-result"),
            (lambda d: d["audits"][-1]["review_events"][-1]["dispositions"].update({"R9-C1": "clarification_requested"}), "Unresolved review"),
            (lambda d: d["audits"][-1]["source_anchor_refs"].append("L11-99"), "Unknown/duplicate source anchor"),
            (lambda d: d["counterexample_checks"].pop(), "Counterexample reference coverage"),
            (lambda d: d["sources"][-1].update(original_sha256="0" * 64), "Registered source hash differs"),
        )
        for mutate, message in mutations:
            with self.subTest(message=message):
                bad = copy.deepcopy(self.provenance)
                mutate(bad)
                with self.assertRaisesRegex(ValueError, message):
                    self.verify(bad, self.registered, self.research)


if __name__ == "__main__":
    unittest.main()
