import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'benchmarks/reporting/closed_loop'))
from capabilities import build_history_manifest
from contracts import load_task
from fixed_tail_validation import validate_regions


class NativeFixedTailTests(unittest.TestCase):
    def test_native_profiles_preserve_original_continuous_tasks_and_cpp_source(self):
        graphs = build_history_manifest()['graphs']
        for name in ('syn-nl-lv-01', 'syn-nl-fuel-01', 'earth-orbit'):
            task = load_task(name)
            for family in ('polytope', 'box', 'zonotope', 'parallelotope', 'ellipsoid'):
                graph = next(g for g in graphs if g['task_id'] == task['task_id'] and
                             g['controller']['id'] == f'native-fixed-tail-{family}-ipopt/1')
                self.assertEqual(graph['action_profile_id'], task['control_domains']['continuous']['problem_id'])
                self.assertEqual(graph['objective_id'], task['objective']['objective_id'])
                self.assertEqual(graph['controller']['policy_factory'], 'native_fixed_tail_policy:create_policy')
                self.assertEqual(graph['role_bindings']['representation']['id'], family)
                paths = {p['path'] for p in graph['source_files']}
                self.assertIn('src/reachability/fixed_tail_policy.cpp', paths)
                self.assertIn('src/adapters/nlp/casadi_fixed_tail.cpp', paths)
                self.assertNotIn('benchmarks/reporting/closed_loop/history_norm_solver.py', paths)

    def test_factor_domain_is_infinity_ball_with_l1_support(self):
        h = {'inequalities': [[1, 0], [-1, 0], [0, 1], [0, -1]],
             'upper_bounds': [1, 1, 1, 1], 'equalities': [], 'equality_values': []}
        region = {'stage': 0, 'family': 'box', 'reference': h,
                  'membership': {'center': [0, 0], 'factor': [[1, 0], [0, 1]],
                                 'support_norm': 'l1', 'factor_domain_norm': 'linf'}}
        response = {'family': 'box', 'history': [1, 1], 'regions': [region],
                    'reduced_argmin': {'region_factors': [[1, 1]]}}
        self.assertTrue(validate_regions(response, 2, 0)['accepted'])
        bad = copy.deepcopy(response)
        bad['regions'][0]['membership']['factor_domain_norm'] = 'l2'
        with self.assertRaises(ValueError):
            validate_regions(bad, 2, 0)
        bad = copy.deepcopy(response)
        bad['reduced_argmin']['region_factors'] = [[1.1, 1]]
        self.assertFalse(validate_regions(bad, 2, 0)['accepted'])
        bad = copy.deepcopy(response)
        bad['regions'] = []
        with self.assertRaises(ValueError):
            validate_regions(bad, 2, 0)


if __name__ == '__main__':
    unittest.main()
