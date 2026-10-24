"""The installed trajectory verification schema rejects incomplete evidence."""
import json
from pathlib import Path
import unittest

import jsonschema


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "docs/artifacts/schemas/trajectory-verification-reports-v1.schema.json"


def sample():
    family_request = {
        "profile": "ts01_exact_integrator",
        "objective": "problem:fixture",
        "target": "exact_optimal_relation",
        "assurance": "numerical",
        "representation": "csl.polyhedron.h",
        "absolute_tolerance_bits": "3e7ad7f29abcaf48",
        "relative_tolerance_bits": "3e7ad7f29abcaf48",
        "materialization_limit": None,
    }
    lineage = [{"request": "request-1", "input": "set-1", "output": "set-2", "module": "module-1", "version": "1"}]
    provider = {
        "port": "csl.lp.v1",
        "requested": {"id": "csl.lp.highs", "version": "1"},
        "actual": {"id": "csl.lp.highs", "version": "1"},
    }
    return {
        "schema": "csl.trajectory-verification-reports/1",
        "problem_id": "problem:fixture",
        "reports": [{
            "witness_index": 0,
            "problem_id": "problem:fixture",
            "witness": {"problem_id": "problem:fixture", "states": [["0000000000000000"]],
                        "controls": [["0000000000000000"]], "original_objective_bits": "0000000000000000"},
            "verifier": {"id": "csl.trajectory.original", "version": "1"},
            "request": {
                "assurance": "numerical", "verification_assurance": "numerical",
                "absolute_tolerance_bits": "3e7ad7f29abcaf48", "relative_tolerance_bits": "3e7ad7f29abcaf48",
                "limits": {"residuals": 100, "membership_queries": 20},
                "bounds": {"lower": None, "upper": None}, "backend_bounds": [],
                "family_identity": {
                    "problem_id": "problem:fixture", "request": family_request,
                    "coordinates": {"state_dimension": 1, "control_dimension": 1, "external_dimension": 0, "horizon": 1},
                    "strategy": "csl.synthesis.reach-back", "strategy_version": "1", "lineage": lineage,
                },
                "expected_synthesis": {
                    "strategy": "csl.synthesis.reach-back", "strategy_version": "1",
                    "family_request": family_request, "lineage": lineage,
                },
                "outcome": {"subject": "problem:fixture", "value": "optimal",
                            "support": {"kind": "unestablished"}, "assumptions": []},
            },
            "termination": "completed", "bindings": "numerical_pass", "feasibility": "numerical_pass",
            "objective": "numerical_pass", "optimality": "unsupported", "completeness": "unsupported",
            "validated": "unsupported", "recomputed_objective_bits": "0000000000000000",
            "residuals": [{"field": "state[0]", "violation_bits": "0000000000000000",
                           "scale_bits": "0000000000000000", "tolerance_bits": "3e7ad7f29abcaf48", "satisfied": True}],
            "membership_queries": [
                {"kind": "not_run", "request_problem_id": "problem:fixture", "request_program_id": "q0", "reason": "deadline", "provider": provider},
                {"kind": "rejected", "request_problem_id": "problem:fixture", "request_program_id": "q1", "diagnostics": [], "provider": provider},
                {"kind": "solver_unsupported", "request_problem_id": "problem:fixture", "request_program_id": "q2", "diagnostics": [], "provider": provider},
                {"kind": "completed", "request_problem_id": "problem:fixture", "request_program_id": "q3", "returned_problem_id": "problem:fixture", "returned_program_id": "q3", "outcome": "optimal", "provider": provider},
                {"kind": "stopped", "request_problem_id": "problem:fixture", "request_program_id": "q4", "reason": "resource_limit", "provider": provider},
            ],
            "diagnostics": [],
        }],
    }


class TrajectoryVerificationSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(cls.schema)
        cls.validator = jsonschema.Draft202012Validator(cls.schema)

    def test_full_report_and_all_membership_query_variants_validate(self):
        self.validator.validate(sample())

    def test_schema_rejects_unknown_request_and_query_fields(self):
        report = sample()
        report["reports"][0]["request"]["misspelled_tolerance"] = "0000000000000000"
        with self.assertRaises(jsonschema.ValidationError):
            self.validator.validate(report)

        report = sample()
        report["reports"][0]["membership_queries"][0]["missing_provider"] = True
        with self.assertRaises(jsonschema.ValidationError):
            self.validator.validate(report)

    def test_schema_rejects_incomplete_family_and_evidence_payloads(self):
        report = sample()
        del report["reports"][0]["request"]["family_identity"]["coordinates"]
        with self.assertRaises(jsonschema.ValidationError):
            self.validator.validate(report)

        report = sample()
        report["reports"][0]["request"]["bounds"]["lower"] = {
            "value_bits": "0000000000000000", "evidence": {"problem_id": "problem:fixture", "support": {"kind": "mystery"}}
        }
        with self.assertRaises(jsonschema.ValidationError):
            self.validator.validate(report)


if __name__ == "__main__":
    unittest.main()
