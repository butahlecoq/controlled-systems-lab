"""Regression coverage for legacy workflow_run commits without the MPC-06 report."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/mpc06-tube-objective-pages-augmentation.yml"
REPORT = Path("reports/algorithm-results/mpc06-tube-objective-v1/result.json")
VERIFIER = Path("tests/reporting/test_mpc06_tube_objective.py")


def scope_step() -> str:
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    marker = "      - name: Detect MPC-06 report source in the triggering revision"
    try:
        start = lines.index(marker)
    except ValueError as error:
        raise AssertionError("workflow must retain the source-presence guard") from error
    run_marker = "        run: |"
    if lines[start + 1] != "        id: scope":
        raise AssertionError("scope guard must expose its result as step output")
    if lines[start + 2] != run_marker:
        raise AssertionError("scope guard must use an executable run block")
    block = []
    for line in lines[start + 3:]:
        if line and not line.startswith("          "):
            break
        block.append(line[10:] if line else "")
    return textwrap.dedent("\n".join(block))


class Mpc06TubeObjectivePagesAugmentationTests(unittest.TestCase):
    def run_scope(self, root: Path, output: Path | None = None) -> tuple[subprocess.CompletedProcess[str], str]:
        if output is None:
            output = root / "workflow-output.txt"
        environment = os.environ.copy()
        environment["GITHUB_OUTPUT"] = str(output)
        result = subprocess.run(
            ["bash", "-e", "-c", scope_step()],
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        return result, output.read_text(encoding="utf-8") if output.exists() else ""

    def test_legacy_revision_skips_when_report_is_absent(self):
        with tempfile.TemporaryDirectory(prefix="mpc06-legacy-run-") as temporary:
            root = Path(temporary)
            result, output = self.run_scope(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("eligible=false", output)
            self.assertIn("predates the MPC-06 tube objective report", result.stdout)

    def test_report_revision_proceeds_when_independent_verifier_is_present(self):
        with tempfile.TemporaryDirectory(prefix="mpc06-current-run-") as temporary:
            root = Path(temporary)
            (root / REPORT).parent.mkdir(parents=True)
            (root / REPORT).touch()
            (root / VERIFIER).parent.mkdir(parents=True)
            (root / VERIFIER).touch()
            result, output = self.run_scope(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("eligible=true", output)

    def test_current_source_revision_is_eligible(self):
        with tempfile.TemporaryDirectory(prefix="mpc06-current-source-") as temporary:
            result, output = self.run_scope(ROOT, Path(temporary) / "workflow-output.txt")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("eligible=true", output)

    def test_partial_report_revision_fails_instead_of_silently_skipping(self):
        with tempfile.TemporaryDirectory(prefix="mpc06-incomplete-run-") as temporary:
            root = Path(temporary)
            (root / REPORT).parent.mkdir(parents=True)
            (root / REPORT).touch()
            result, output = self.run_scope(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("report exists without its independent verifier test", result.stderr)
            self.assertEqual(output, "")

    def test_all_report_steps_are_gated_on_scope(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertGreaterEqual(source.count("steps.scope.outputs.eligible == 'true'"), 10)


if __name__ == "__main__":
    unittest.main()
