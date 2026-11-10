"""Run the qualified saved-evidence profile and reject skipped coverage."""
import importlib
import unittest


def main():
    for name in ('numpy', 'scipy', 'casadi', 'do_mpc'):
        importlib.import_module(name)
    suite = unittest.defaultTestLoader.loadTestsFromNames([
        'tests.reporting.test_mpc11_affine_saved',
        'tests.reporting.test_mpc11_publication',
        'tests.reporting.test_pages_augmentation_aggregation',
    ])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() and result.testsRun and not result.skipped else 1


if __name__ == '__main__':
    raise SystemExit(main())
