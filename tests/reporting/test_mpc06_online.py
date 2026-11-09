import importlib.util
from fractions import Fraction as Q
from pathlib import Path
import unittest

P=Path(__file__).resolve().parents[2]/'scripts/reports/mpc06_online/model.py'
S=importlib.util.spec_from_file_location('mpc06_online_model',P)
M=importlib.util.module_from_spec(S)
S.loader.exec_module(M)

class OnlineTubeTests(unittest.TestCase):
    def test_terminal_elimination_and_unique_nominal_optimum(self):
        for p,q in [(Q(1,8),Q(0)),(Q(-1,4),Q(1,8)),(Q(0),Q(0))]:
            qp=M.problem((p,q),M.tightenings('polytope'))
            a=M.optimizer(qp)
            states,controls=M.plan((p,q),a)
            self.assertEqual(states[-1],(0,0))
            self.assertGreater(qp['quadratic'],0)
            self.assertTrue(M.feasible_plan(states,controls,M.tightenings('polytope')))
            derivative=2*qp['quadratic']*a+qp['linear']
            self.assertTrue(derivative==0 or (a==qp['lower'] and derivative>=0) or (a==qp['upper'] and derivative<=0))

    def test_finite_error_reference_contains_invariant_tube_feasible_set(self):
        for p in map(lambda x:Q(x,8),range(-4,5)):
            for q in map(lambda x:Q(x,8),range(-4,5)):
                tube=M.problem((p,q),M.tightenings('polytope'))
                exact=M.problem((p,q),M.tightenings('finite-reference'))
                if tube['feasible']:
                    self.assertTrue(exact['feasible'])
                    self.assertLessEqual(exact['lower'],tube['lower'])
                    self.assertGreaterEqual(exact['upper'],tube['upper'])
                    self.assertLessEqual(M.value(exact,M.optimizer(exact)),M.value(tube,M.optimizer(tube)))

    def test_outer_error_enclosure_does_not_imply_rpi(self):
        checks=M.representation_checks()
        for kind in ('polytope','zonotope','parallelotope','inflated-zonotope','ellipsoid-certified'):
            self.assertTrue(checks[kind]['contains_exact_Z'])
            self.assertTrue(checks[kind]['rpi'])
        for kind in ('box','ellipsoid-app04'):
            self.assertTrue(checks[kind]['contains_exact_Z'])
            self.assertFalse(checks[kind]['rpi'])
            self.assertIn('counterexample',checks[kind])
            with self.assertRaises(ValueError):M.tightenings(kind)

    def test_empty_tightening_and_infeasible_anchor_remain_failures(self):
        self.assertFalse(M.problem((Q(2),Q(0)),M.tightenings('polytope'))['feasible'])
        self.assertFalse(M.problem((Q(0),Q(0)),[(-Q(1),-Q(1),-Q(1))]*3)['feasible'])

    def test_exact_vertex_worst_cost_is_policy_specific(self):
        result=M.replay((Q(1,8),Q(0)),[Q(0),Q(1,16),Q(-1,16)])
        self.assertEqual(len(result['paths']),8)
        self.assertEqual(result['worst'],max(row['cost'] for row in result['paths']))
        for row in result['paths']:
            self.assertTrue(row['safe'])
        with self.assertRaises(ValueError):M.replay((Q(0),Q(0)),[Q(0)]*3,policy='measured-state-reset')

if __name__=='__main__':unittest.main()
