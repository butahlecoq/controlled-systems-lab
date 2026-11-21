"""The qualified profile must fail when required coverage is skipped."""

import contextlib
import io
import unittest
from unittest import mock

from tests.reporting import run_controller_publication_checks as runner


class ControllerPublicationRunnerTests(unittest.TestCase):
    def test_skipped_and_failed_checks_cannot_qualify_the_profile(self):
        for outcome, expected in [("passed", 0), ("skipped", 1), ("failed", 1)]:

            def check(outcome=outcome):
                if outcome == "skipped":
                    raise unittest.SkipTest("missing optional dependency")
                if outcome == "failed":
                    raise AssertionError("evidence check failed")

            def discover(modules):
                return unittest.TestSuite(
                    unittest.TestSuite([unittest.FunctionTestCase(check)]) for _ in modules
                )

            with (
                self.subTest(outcome=outcome),
                mock.patch.object(runner.importlib, "import_module"),
                mock.patch.object(
                    runner.unittest.defaultTestLoader, "loadTestsFromNames", side_effect=discover
                ),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(runner.main(), expected)

    def test_empty_required_module_cannot_be_hidden_by_other_passing_tests(self):
        check = mock.Mock()
        missing = "tests.reporting.test_mpc11_publication"

        def passing_check():
            check()

        def discover(modules):
            return unittest.TestSuite(
                unittest.TestSuite(
                    [] if name == missing else [unittest.FunctionTestCase(passing_check)]
                )
                for name in modules
            )

        output = io.StringIO()
        with (
            mock.patch.object(runner.importlib, "import_module"),
            mock.patch.object(
                runner.unittest.defaultTestLoader, "loadTestsFromNames", side_effect=discover
            ),
            contextlib.redirect_stderr(output),
        ):
            self.assertEqual(runner.main(), 1)
        self.assertIn(missing, output.getvalue())
        check.assert_not_called()


if __name__ == "__main__":
    unittest.main()
