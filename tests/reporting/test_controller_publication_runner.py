"""The qualified profile must fail when required coverage is skipped."""
import contextlib
import io
import unittest
from unittest import mock
from tests.reporting import run_controller_publication_checks as runner


class ControllerPublicationRunnerTests(unittest.TestCase):
    def test_skipped_and_failed_checks_cannot_qualify_the_profile(self):
        for outcome, expected in [('passed', 0), ('skipped', 1), ('failed', 1)]:
            def check(outcome=outcome):
                if outcome == 'skipped':
                    raise unittest.SkipTest('missing optional dependency')
                if outcome == 'failed':
                    raise AssertionError('evidence check failed')
            suite = unittest.TestSuite([unittest.FunctionTestCase(check)])
            with self.subTest(outcome=outcome), mock.patch.object(runner.importlib, 'import_module'), \
                    mock.patch.object(runner.unittest.defaultTestLoader, 'loadTestsFromNames', return_value=suite), \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(runner.main(), expected)


if __name__ == '__main__':
    unittest.main()
