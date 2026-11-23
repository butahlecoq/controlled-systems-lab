"""Exercise the child environment contract shared by REVIEW-05 capture commands."""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


@unittest.skipUnless(sys.platform == "linux", "The resource runner uses Linux wait4")
class Review05ResourceReceiptTests(unittest.TestCase):
    def test_default_environment_is_inherited_and_explicit_override_is_used(self):
        directory = Path(__file__).resolve().parents[2] / "benchmarks/reporting/review05"
        with patch.object(sys, "path", [str(directory), *sys.path]):
            from benchmarks.reporting.review05.run_horizon_ladder import run_with_resource_receipt

        command = [
            sys.executable,
            "-c",
            "import os; print(os.environ['CSL_REVIEW05_TEST_PARENT'])",
        ]
        with patch.dict(os.environ, {"CSL_REVIEW05_TEST_PARENT": "inherited"}):
            try:
                inherited = run_with_resource_receipt(command, 5)
            except TypeError as error:
                self.fail(f"Two-argument capture commands must inherit the environment: {error}")
            explicit = run_with_resource_receipt(
                command, 5, {"CSL_REVIEW05_TEST_PARENT": "explicit"}
            )

        for result, value in ((inherited, b"inherited\n"), (explicit, b"explicit\n")):
            code, timed_out, stdout, stderr, resources = result
            self.assertEqual((code, timed_out, stdout, stderr), (0, False, value, b""))
            self.assertEqual(resources["source"], "POSIX wait4 for the isolated strategy process")
            self.assertFalse(resources["timed_out"])
