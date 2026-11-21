"""Run the qualified saved-evidence profile and reject skipped coverage."""

import importlib
import sys
import unittest


def main() -> int:
    for name in ("numpy", "scipy", "casadi", "do_mpc"):
        importlib.import_module(name)
    modules = [
        "tests.reporting.test_mpc11_affine_saved",
        "tests.reporting.test_closed_loop_tasks",
        "tests.reporting.test_mpc11_publication",
        "tests.reporting.test_pages_augmentation_aggregation",
        "tests.reporting.test_b04_source_moments",
        "tests.reporting.test_stage_b04_source_moments",
    ]
    suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
    for name, module_suite in zip(modules, suite, strict=True):
        if module_suite.countTestCases() == 0:
            print(
                f"Required controller evidence module discovered no tests: {name}", file=sys.stderr
            )
            return 1
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() and result.testsRun and not result.skipped else 1


if __name__ == "__main__":
    raise SystemExit(main())
