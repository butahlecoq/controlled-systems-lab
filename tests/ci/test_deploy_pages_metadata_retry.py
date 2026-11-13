"""Behavioral tests for retrying only pre-deployment Pages metadata misses."""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from scripts.ci.deploy_pages_metadata_retry import run_deployer

EMPTY_ARTIFACT_ERROR = 'Error: No artifacts named "github-pages" were found for this workflow run.'


class DeployPagesMetadataRetryTests(unittest.TestCase):
    def run_fake_deployer(
        self,
        attempts: list[tuple[int, list[str]] | tuple[int, list[str], list[str]]],
    ) -> tuple[int, str, int, list[int], str]:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            counter = root / "attempts"
            child = root / "fake_deployer.py"
            child.write_text(
                "import json, os, pathlib, sys\n"
                "counter = pathlib.Path(os.environ['FAKE_COUNTER'])\n"
                "attempt = int(counter.read_text()) + 1 if counter.exists() else 1\n"
                "counter.write_text(str(attempt))\n"
                "sequence = json.loads(os.environ['FAKE_SEQUENCE'])\n"
                "code, lines, *outputs = sequence[attempt - 1]\n"
                "for line in lines:\n"
                "    print(line, flush=True)\n"
                "if outputs:\n"
                "    with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:\n"
                "        output.write('\\n'.join(outputs[0]) + '\\n')\n"
                "if code < 0:\n"
                "    import os, signal\n"
                "    os.kill(os.getpid(), -code)\n"
                "sys.exit(code)\n",
                encoding="utf-8",
            )
            github_output = root / "github-output"
            github_output.touch()
            child_environment = {
                "FAKE_COUNTER": str(counter),
                "FAKE_SEQUENCE": json.dumps(attempts),
                "GITHUB_OUTPUT": str(github_output),
            }
            output = tempfile.TemporaryFile(mode="w+t", encoding="utf-8")
            delays: list[int] = []
            with (
                mock.patch.dict(os.environ, child_environment),
                mock.patch(
                    "scripts.ci.deploy_pages_metadata_retry.time.sleep", side_effect=delays.append
                ),
            ):
                result = run_deployer([sys.executable, str(child)], output=output)
            output.seek(0)
            text = output.read()
            output.close()
            step_outputs = github_output.read_text(encoding="utf-8")
            return (
                result,
                text,
                int(counter.read_text()) if counter.exists() else 0,
                delays,
                step_outputs,
            )

    def test_retries_exact_empty_artifact_lookup_and_then_succeeds(self) -> None:
        result, output, attempts, delays, step_outputs = self.run_fake_deployer(
            [
                (1, [EMPTY_ARTIFACT_ERROR]),
                (0, ["deployment succeeded"], ["page_url=https://example.invalid/pages"]),
            ]
        )

        self.assertEqual((result, attempts, delays), (0, 2, [2]))
        self.assertIn(EMPTY_ARTIFACT_ERROR, output)
        self.assertIn("deployment succeeded", output)
        self.assertEqual(step_outputs, "page_url=https://example.invalid/pages\n")

    def test_forwards_mask_command_before_child_exits(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            release = root / "release-child"
            child = root / "fake_deployer.py"
            child.write_text(
                "import pathlib, sys, time\n"
                "print('::add-mask::fixture-secret', flush=True)\n"
                "release = pathlib.Path(sys.argv[1])\n"
                "while not release.exists():\n"
                "    time.sleep(0.01)\n",
                encoding="utf-8",
            )
            received_output = threading.Event()

            class OutputSink(io.StringIO):
                def write(self, value: str) -> int:
                    written = super().write(value)
                    if "::add-mask::fixture-secret" in value:
                        received_output.set()
                    return written

            output = OutputSink()
            result: list[int] = []
            worker = threading.Thread(
                target=lambda: result.append(
                    run_deployer([sys.executable, str(child), str(release)], output=output)
                )
            )
            worker.start()
            try:
                forwarded_while_running = received_output.wait(timeout=2)
            finally:
                release.touch()
                worker.join(timeout=2)

            self.assertTrue(forwarded_while_running)
            self.assertFalse(worker.is_alive())
            self.assertEqual(result, [0])
            self.assertEqual(output.getvalue(), "::add-mask::fixture-secret\n")

    def test_stops_after_three_empty_artifact_lookup_failures(self) -> None:
        result, _, attempts, delays, _ = self.run_fake_deployer([(1, [EMPTY_ARTIFACT_ERROR])] * 3)

        self.assertEqual((result, attempts, delays), (1, 3, [2, 4]))

    def test_does_not_retry_other_failure_messages(self) -> None:
        for message in (
            'Error: Multiple artifacts named "github-pages" were unexpectedly found.',
            "Error: Resource not accessible by integration",
        ):
            with self.subTest(message=message):
                result, output, attempts, delays, _ = self.run_fake_deployer([(1, [message])])
                self.assertEqual((result, attempts), (1, 1))
                self.assertEqual(delays, [])
                self.assertIn(message, output)

    def test_does_not_retry_if_deployment_creation_started(self) -> None:
        result, _, attempts, delays, _ = self.run_fake_deployer(
            [
                (
                    1,
                    [
                        EMPTY_ARTIFACT_ERROR,
                        "Creating Pages deployment with payload:",
                    ],
                )
            ]
        )

        self.assertEqual((result, attempts, delays), (1, 1, []))

    def test_does_not_retry_child_terminated_by_signal(self) -> None:
        result, _, attempts, delays, _ = self.run_fake_deployer([(-15, [EMPTY_ARTIFACT_ERROR])])

        self.assertEqual((result, attempts, delays), (-15, 1, []))


if __name__ == "__main__":
    unittest.main()
