"""Behavioral tests for retrying only pre-deployment Pages metadata misses."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.ci.deploy_pages_metadata_retry import run_deployer


EMPTY_ARTIFACT_ERROR = (
    'Error: No artifacts named "github-pages" were found for this workflow run.'
)


class DeployPagesMetadataRetryTests(unittest.TestCase):
    def run_fake_deployer(
        self, attempts: list[tuple[int, list[str]]]
    ) -> tuple[int, str, int, list[int]]:
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
                "code, lines = sequence[attempt - 1]\n"
                "for line in lines:\n"
                "    print(line, flush=True)\n"
                "if code < 0:\n"
                "    import os, signal\n"
                "    os.kill(os.getpid(), -code)\n"
                "sys.exit(code)\n",
                encoding="utf-8",
            )
            environment = os.environ.copy()
            environment.update(
                FAKE_COUNTER=str(counter),
                FAKE_SEQUENCE=json.dumps(attempts),
            )
            output = tempfile.TemporaryFile(mode="w+t", encoding="utf-8")
            delays: list[int] = []
            with mock.patch(
                "scripts.ci.deploy_pages_metadata_retry.time.sleep", side_effect=delays.append
            ):
                result = run_deployer(
                    [sys.executable, str(child)], environment=environment, output=output
                )
            output.seek(0)
            text = output.read()
            output.close()
            return result, text, int(counter.read_text()) if counter.exists() else 0, delays

    def test_retries_exact_empty_artifact_lookup_and_then_succeeds(self) -> None:
        result, output, attempts, delays = self.run_fake_deployer(
            [(1, [EMPTY_ARTIFACT_ERROR]), (0, ["deployment succeeded"])]
        )

        self.assertEqual((result, attempts, delays), (0, 2, [2]))
        self.assertIn(EMPTY_ARTIFACT_ERROR, output)
        self.assertIn("deployment succeeded", output)

    def test_stops_after_three_empty_artifact_lookup_failures(self) -> None:
        result, _, attempts, delays = self.run_fake_deployer(
            [(1, [EMPTY_ARTIFACT_ERROR])] * 3
        )

        self.assertEqual((result, attempts, delays), (1, 3, [2, 4]))

    def test_does_not_retry_other_failure_messages(self) -> None:
        for message in (
            'Error: Multiple artifacts named "github-pages" were unexpectedly found.',
            "Error: Resource not accessible by integration",
        ):
            with self.subTest(message=message):
                result, output, attempts, delays = self.run_fake_deployer([(1, [message])])
                self.assertEqual((result, attempts), (1, 1))
                self.assertEqual(delays, [])
                self.assertIn(message, output)

    def test_does_not_retry_if_deployment_creation_started(self) -> None:
        result, _, attempts, delays = self.run_fake_deployer(
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
        result, _, attempts, delays = self.run_fake_deployer(
            [(-15, [EMPTY_ARTIFACT_ERROR])]
        )

        self.assertEqual((result, attempts, delays), (-15, 1, []))


if __name__ == "__main__":
    unittest.main()
