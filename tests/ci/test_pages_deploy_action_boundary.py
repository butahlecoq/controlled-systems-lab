"""Exercise the local Node action boundary with fake Actions runtime values."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ACTION_MAIN = ROOT / ".github/actions/pages-deploy/index.js"
WRAPPER = ROOT / "scripts/ci/deploy_pages_metadata_retry.py"


class PagesDeployActionBoundaryTests(unittest.TestCase):
    def run_action(self, bundle_source: str) -> tuple[subprocess.CompletedProcess[str], str]:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            wrapper = workspace / "scripts/ci/deploy_pages_metadata_retry.py"
            wrapper.parent.mkdir(parents=True)
            shutil.copyfile(WRAPPER, wrapper)
            deployer = workspace / "build/pinned-pages-deployer/dist/index.js"
            deployer.parent.mkdir(parents=True)
            deployer.write_text(bundle_source, encoding="utf-8")
            github_output = workspace / "github-output"
            github_output.touch()

            environment = os.environ.copy()
            environment.update(
                ACTIONS_RUNTIME_TOKEN="fixture-runtime-token",
                ACTIONS_RESULTS_URL="http://127.0.0.1:43210/",
                GITHUB_ACTION_PATH=str(ACTION_MAIN.parent),
                GITHUB_OUTPUT=str(github_output),
                GITHUB_WORKSPACE=str(workspace),
                INPUT_TOKEN="fixture-github-token",
                INPUT_TIMEOUT="600000",
                INPUT_ERROR_COUNT="10",
                INPUT_REPORTING_INTERVAL="5000",
                INPUT_ARTIFACT_NAME="github-pages",
                INPUT_PREVIEW="false",
            )
            result = subprocess.run(
                [shutil.which("node") or "node", str(ACTION_MAIN)],
                cwd=workspace,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            return result, github_output.read_text(encoding="utf-8")

    def test_local_action_keeps_official_inputs_and_defaults(self) -> None:
        manifest = (ROOT / ".github/actions/pages-deploy/action.yml").read_text(encoding="utf-8")

        self.assertIn("using: node24", manifest)
        for input_name, default in (
            ("token", "${{ github.token }}"),
            ("timeout", "'600000'"),
            ("error_count", "'10'"),
            ("reporting_interval", "'5000'"),
            ("artifact_name", "github-pages"),
            ("preview", "'false'"),
        ):
            with self.subTest(input_name=input_name):
                self.assertRegex(
                    manifest,
                    rf"(?m)^  {re.escape(input_name)}:\n(?:    [^\n]*\n)*?"
                    rf"    default: {re.escape(default)}$",
                )
        self.assertIn("  page_url:\n", manifest)
        quality_workflow = (ROOT / ".github/workflows/python-quality.yml").read_text(
            encoding="utf-8"
        )
        self.assertEqual(quality_workflow.count("- '.github/actions/pages-deploy/**'"), 2)

    def test_child_bundle_inherits_runtime_inputs_and_step_output(self) -> None:
        bundle = """
const fs = require('node:fs');
const required = {
  ACTIONS_RUNTIME_TOKEN: 'fixture-runtime-token',
  ACTIONS_RESULTS_URL: 'http://127.0.0.1:43210/',
  INPUT_TOKEN: 'fixture-github-token',
  INPUT_TIMEOUT: '600000',
  INPUT_ERROR_COUNT: '10',
  INPUT_REPORTING_INTERVAL: '5000',
  INPUT_ARTIFACT_NAME: 'github-pages',
  INPUT_PREVIEW: 'false',
};
for (const [name, expected] of Object.entries(required)) {
  if (process.env[name] !== expected) process.exit(19);
}
console.log('::add-mask::fixture-placeholder-secret');
fs.appendFileSync(process.env.GITHUB_OUTPUT, 'page_url=https://example.invalid/pages\\n');
"""
        result, output = self.run_action(bundle)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output, "page_url=https://example.invalid/pages\n")
        self.assertIn("::add-mask::fixture-placeholder-secret", result.stdout)

    def test_action_propagates_deployer_exit_status(self) -> None:
        result, _ = self.run_action("process.exit(7);\n")

        self.assertEqual(result.returncode, 7, result.stderr)

    def test_action_propagates_deployer_signal(self) -> None:
        result, _ = self.run_action("process.kill(process.pid, 'SIGTERM');\n")

        self.assertEqual(result.returncode, -15, result.stderr)


if __name__ == "__main__":
    unittest.main()
