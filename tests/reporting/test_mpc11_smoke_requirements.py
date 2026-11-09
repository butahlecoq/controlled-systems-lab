import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('smoke_requirements', ROOT / 'benchmarks/reporting/mpc11/environment/smoke_requirements.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RequiredPluginTests(unittest.TestCase):
    def test_success_requires_both_execution_plugins(self):
        for ipopt, cvodes in [(True, False), (False, True), (False, False)]:
            self.assertEqual(MODULE.qualification_exit_code({'ipopt_plugin_available': ipopt,
                             'cvodes_plugin_available': cvodes}), 1)
        self.assertEqual(MODULE.qualification_exit_code({'ipopt_plugin_available': True,
                         'cvodes_plugin_available': True}), 0)

    def test_missing_plugin_receipt_is_not_success(self):
        self.assertEqual(MODULE.qualification_exit_code({'ipopt_plugin_available': True}), 1)


if __name__ == '__main__':
    unittest.main()
