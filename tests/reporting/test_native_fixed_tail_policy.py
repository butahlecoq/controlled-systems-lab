import copy
import os
import tempfile
from unittest import mock
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

    def test_native_stderr_survives_supervised_mid_query_kill(self):
        from run_closed_loop import run_limited
        marker = b'native-query-started-before-supervisor-kill\n'
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            bridge = folder / 'blocking-native-bridge'
            bridge.write_text('#!/usr/bin/python3\nimport sys,time\n'
                'assert sys.stdin.readline()\n'
                f'sys.stderr.buffer.write({marker!r});sys.stderr.flush()\n'
                'time.sleep(30)\n')
            bridge.chmod(0o755)
            script = ('import sys;sys.path.insert(0,' + repr(str(ROOT / 'benchmarks/reporting/closed_loop')) + ');'
                'from contracts import load_task,manifest_sha256;'
                'from native_fixed_tail_policy import create_policy;'
                't=load_task("syn-nl-lv-01");'
                'p=create_policy(t,task_sha256=manifest_sha256(t),controller_id="native-fixed-tail-box-ipopt/1",'
                'action_profile_id=t["control_domains"]["continuous"]["problem_id"],'
                'factory_options={"wall_seconds":60,"build_backend_profile":{}});'
                'p.query(t["task_id"],[120,60],0)')
            with mock.patch.dict(os.environ, {'CSL_NATIVE_POLICY_BRIDGE': str(bridge),
                    'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1'}):
                outcome = run_limited([sys.executable, '-c', script], folder / 'stdout', folder / 'stderr',
                    wall_seconds=4, cpu_seconds=10, address_space_bytes=8*1024**3)
            self.assertEqual(outcome['status'], 'timed_out')
            self.assertIn(marker, (folder / 'stderr').read_bytes())

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
