import copy
import importlib.util
from pathlib import Path
import json
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('mpc11_scenarios', ROOT / 'benchmarks/reporting/mpc11/check_scenarios.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ScenarioTests(unittest.TestCase):
    def setUp(self):
        self.fuel = json.loads((ROOT / 'benchmarks/reporting/mpc11/scenarios/syn-nl-fuel-01.json').read_text())
        self.lv = json.loads((ROOT / 'benchmarks/reporting/mpc11/scenarios/syn-nl-lv-01.json').read_text())

    def test_both_complete_configs_are_accepted(self):
        for scenario in [self.fuel, self.lv]:
            self.assertEqual(len(MODULE.validate(scenario)), 64)

    def test_rejects_time_grid_or_coordinate_mismatch(self):
        for scenario in [self.fuel, self.lv]:
            bad = copy.deepcopy(scenario)
            bad['time']['grid'][-1] += .1
            with self.assertRaisesRegex(ValueError, 'grid'):
                MODULE.validate(bad)
            bad = copy.deepcopy(scenario)
            bad['affine']['trust_state_absolute'].pop()
            with self.assertRaisesRegex(ValueError, 'dimension'):
                MODULE.validate(bad)

    def test_rejects_changed_cost_normalization_or_fallback(self):
        for field, value in [('running_cost_denominator', 'remaining-intervals'), ('failure', 'reuse-last-command')]:
            bad = copy.deepcopy(self.lv)
            bad['nmpc'][field] = value
            with self.assertRaises(ValueError):
                MODULE.validate(bad)

    def test_rejects_infeasible_nominal_fuel_command_after_parameter_change(self):
        self.fuel['parameters']['Q_ox']['value'] = .1
        with self.assertRaisesRegex(ValueError, 'nominal command'):
            MODULE.validate(self.fuel)

    def test_rejects_nonfinite_cost_trust_or_changed_horizon(self):
        for section, field, value in [('objective', 'terminal_target', [float('nan'), 80]),
                                      ('affine', 'trust_state_absolute', [40, float('inf')]),
                                      ('nmpc', 'horizon', 'fixed-moving-window')]:
            bad = copy.deepcopy(self.lv)
            bad[section][field] = value
            with self.assertRaises(ValueError):
                MODULE.validate(bad)

    def test_rejects_nonpositive_scaling_and_initial_violation(self):
        for field, value in [('scale', 0), ('initial', -1)]:
            bad = copy.deepcopy(self.fuel)
            bad['states'][0][field] = value
            with self.assertRaises(ValueError):
                MODULE.validate(bad)


if __name__ == '__main__':
    unittest.main()
