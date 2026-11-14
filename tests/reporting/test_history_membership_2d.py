"""Check the pinned 2D typed-history-membership publication."""

from __future__ import annotations

import hashlib
import importlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
report = importlib.import_module("stage_history_membership_2d")
capture = importlib.import_module("capture_history_membership_2d")


def _fixture(bundle: Path) -> dict[str, bytes]:
    records = bundle / "records"
    records.mkdir(parents=True)
    artifacts = {
        "history.csv": (
            "series,stage,x,y,u0,u1,source_J,zonotope_coefficient\n"
            "optimized,0,0,0,0.6,0.7690598923,1.1464101615,\n"
            "optimized,1,0.6,0,0.6,0.7690598923,1.1464101615,1\n"
            "optimized,2,0.6,0.7690598923,0.6,0.7690598923,1.1464101615,\n"
            "selected-zonotope,1,0.2,0,0,0,0,-1\n"
            "selected-zonotope,1,0.6,0,0,0,0,1\n"
        ).encode(),
        "history.svg": b'<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>',
        "records/stdout.txt": (
            f"source_commit={'a' * 40}; compiler=GNU-16.2.1; casadi_version=3.7.2; "
            "provider=csl.nlp.casadi-ipopt.history-cost@1; source_J=1.1464101615; "
            "u0=.6; u1=.7690598923; x1=.6,0; x2=.6,.7690598923; "
            "membership_lambda=1; supplied_start_readback=1; max_H_violation=0; "
            "diagnostics=IPOPT Solve_Succeeded"
        ).encode(),
        "records/build.log": b"Release target built\n",
        "records/build-configuration.json": json.dumps(
            {
                "schema": "csl.history-membership-build-identity/1",
                "source_root_matches_checkout": True,
                "source_commit": "a" * 40,
                "build_type": "Release",
                "generator": "Ninja",
                "casadi_enabled": True,
                "casadi_version": "3.7.2",
                "example_enabled": True,
                "cmake_version": "3.31.6",
                "compiler": {"executable": "g++", "id": "GNU", "version": "16.2.1"},
            },
            indent=2,
        ).encode(),
        "records/native-output.html": b"<html>native output</html>\n",
    }
    for relative, data in artifacts.items():
        (bundle / relative).write_bytes(data)
    expected_u1 = 1.0 - 0.4 / (3.0**0.5)
    expected_objective = 1.0 + 0.2 * (3.0**0.5 - 1.0)
    fake_sources = {path: ("source:" + path).encode() for path in report.SOURCE_PATHS}
    receipt = {
        "schema": report.SCHEMA,
        "source_commit": "a" * 40,
        "source_files": {
            path: hashlib.sha256(data).hexdigest() for path, data in fake_sources.items()
        },
        "binary_sha256": "1" * 64,
        "provider": "csl.nlp.casadi-ipopt.history-cost@1",
        "build_identity": json.loads(artifacts["records/build-configuration.json"]),
        "source_objective": "||x2-(1,1)||_2 + 0.5(|u0|+|u1|)",
        "selected_membership": {
            "stage": 1,
            "family": "zonotope",
            "center": [0.4, 0.0],
            "generator_matrix_rows": [[0.2], [0.0]],
            "coefficient_bounds": [-1.0, 1.0],
            "source_geometry_identity": "source-stage-1-zonotope",
        },
        "initialization": {
            "start_mode": "supplied_start",
            "primal_readback_matches": True,
            "membership_witness": [0.0],
        },
        "result": {
            "source_J": expected_objective,
            "u0": 0.6,
            "u1": expected_u1,
            "x1": [0.6, 0.0],
            "x2": [0.6, expected_u1],
            "membership_coefficients": [1.0],
            "maximum_history_violation": 0.0,
            "diagnostics": "IPOPT Solve_Succeeded; local numerical",
        },
        "analytic_reference": {
            "u0": 0.6,
            "u1": expected_u1,
            "source_J": expected_objective,
            "derivation": "test fixture",
        },
        "reproduction_command": "cmake --build build --target history_membership_2d_example",
        "artifacts": {
            relative: hashlib.sha256(data).hexdigest() for relative, data in artifacts.items()
        },
    }
    (records / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    report.finalize_capture(bundle)
    return fake_sources


class HistoryMembershipPublicationTests(unittest.TestCase):
    def test_captured_native_output_links_resolve_from_records_directory(self):
        rewritten = capture._record_native_html(
            b'<img src="history.svg"><a href="history.csv">history</a>'
        )
        self.assertEqual(
            rewritten,
            b'<img src="../history.svg"><a href="../history.csv">history</a>',
        )

    def test_report_contains_membership_answer_and_offline_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / report.REPORT_ID
            fake_sources = _fixture(bundle)
            real_run = report.subprocess.run

            def source_run(command, *args, **kwargs):
                if len(command) >= 3 and command[:2] == ["git", "show"]:
                    relative = command[2].split(":", 1)[1]
                    return SimpleNamespace(stdout=fake_sources[relative])
                return real_run(command, *args, **kwargs)

            with patch.object(report.subprocess, "run", side_effect=source_run):
                receipt = report.validate(bundle, ROOT)
            self.assertEqual(receipt["result"]["membership_coefficients"], [1.0])
            page = (bundle / "index.html").read_text(encoding="utf-8")
            self.assertIn("Constrain an intermediate state to a zonotope", page)
            self.assertIn("0.2; 0", page)
            self.assertIn("history_membership_2d_example", page)
            with zipfile.ZipFile(bundle / (report.REPORT_ID + ".zip")) as saved:
                self.assertIsNone(saved.testzip())

    def test_modified_history_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / report.REPORT_ID
            _fixture(bundle)
            (bundle / "history.csv").write_text("tampered\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "artifact hash differs|file hash differs"):
                report._receipt(bundle)

    def test_publication_rejects_local_workspace_paths(self):
        with self.assertRaisesRegex(ValueError, "local path"):
            report._require_public_text("records/build.log", "source=/home/alice/work/repo")


class HistoryMembershipBuildIdentityTests(unittest.TestCase):
    source_commit = "a" * 40

    def _cache(self, source_root: Path, build_root: Path, *, enabled: str = "ON") -> str:
        return "\n".join(
            (
                f"CMAKE_HOME_DIRECTORY:INTERNAL={source_root}",
                f"CMAKE_CXX_COMPILER:FILEPATH={sys.executable}",
                "CMAKE_BUILD_TYPE:STRING=Release",
                "CMAKE_GENERATOR:INTERNAL=Ninja",
                f"CMAKE_COMMAND:INTERNAL={sys.executable}",
                "CMAKE_CACHE_MAJOR_VERSION:INTERNAL=3",
                "CMAKE_CACHE_MINOR_VERSION:INTERNAL=31",
                "CMAKE_CACHE_PATCH_VERSION:INTERNAL=6",
                f"CSL_HISTORY_MEMBERSHIP_SOURCE_COMMIT:INTERNAL={self.source_commit}",
                "CSL_HISTORY_MEMBERSHIP_COMPILER:INTERNAL=GNU-16.2.1",
                "CSL_HISTORY_MEMBERSHIP_CASADI_VERSION:INTERNAL=3.7.2",
                "CSL_ENABLE_CASADI:BOOL=ON",
                f"CSL_BUILD_HISTORY_MEMBERSHIP_2D_EXAMPLE:BOOL={enabled}",
                "",
            )
        )

    @staticmethod
    def _compiler_receipt() -> str:
        return 'set(CMAKE_CXX_COMPILER_ID "GNU")\nset(CMAKE_CXX_COMPILER_VERSION "16.2.1")\n'

    def test_build_identity_accepts_exact_source_and_release_configuration(self):
        with tempfile.TemporaryDirectory() as temporary:
            build_root = Path(temporary) / "build"
            build_root.mkdir()
            run = SimpleNamespace(stdout="cmake version 3.31.6\n")
            with patch.object(capture.subprocess, "run", return_value=run):
                identity = capture._validate_build_identity(
                    ROOT,
                    build_root,
                    self._cache(ROOT, build_root),
                    self._compiler_receipt(),
                    self.source_commit,
                )
            self.assertTrue(identity["source_root_matches_checkout"])
            self.assertEqual(identity["source_commit"], self.source_commit)
            self.assertEqual(identity["compiler"]["id"], "GNU")

    def test_build_identity_rejects_wrong_source_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            build_root = Path(temporary) / "build"
            wrong_source = Path(temporary) / "wrong-source"
            build_root.mkdir()
            wrong_source.mkdir()
            with self.assertRaisesRegex(RuntimeError, "source root differs"):
                capture._validate_build_identity(
                    ROOT,
                    build_root,
                    self._cache(wrong_source, build_root),
                    self._compiler_receipt(),
                    self.source_commit,
                )

    def test_build_identity_rejects_stale_target_configuration(self):
        with tempfile.TemporaryDirectory() as temporary:
            build_root = Path(temporary) / "build"
            build_root.mkdir()
            with self.assertRaisesRegex(RuntimeError, "did not enable"):
                capture._validate_build_identity(
                    ROOT,
                    build_root,
                    self._cache(ROOT, build_root, enabled="OFF"),
                    self._compiler_receipt(),
                    self.source_commit,
                )

    def test_native_binary_rejects_wrong_compiled_source_commit(self):
        output = (
            f"source_commit={'b' * 40}; compiler=GNU-16.2.1; casadi_version=3.7.2; "
            "provider=csl.nlp.casadi-ipopt.history-cost@1; source_J=1; u0=.6; u1=.7; "
            "x1=.6,0; x2=.6,.7; membership_lambda=1; supplied_start_readback=1; "
            "max_H_violation=0; diagnostics=success"
        ).encode()
        with self.assertRaisesRegex(RuntimeError, "different source commit"):
            capture._native_output(output, self.source_commit, "GNU-16.2.1", "3.7.2")


if __name__ == "__main__":
    unittest.main()
