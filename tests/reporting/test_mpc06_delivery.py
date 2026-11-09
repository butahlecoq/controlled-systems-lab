import importlib.util
from fractions import Fraction as Q
from pathlib import Path
import unittest
import copy

ROOT=Path(__file__).resolve().parents[2]
PATH=ROOT/'scripts/reports/mpc06_delivery/reference.py'
SPEC=importlib.util.spec_from_file_location('mpc06_delivery_reference',PATH)
REF=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REF)

class ExactPolicyReferenceTests(unittest.TestCase):
    def test_common_positive_quadratic_and_zero_symmetric_fixture(self):
        for gain in ((0,0),(-1,-2)):
            result=REF.solve((Q(0),Q(0)),gain)
            self.assertEqual(result['a'],0)
            self.assertEqual(result['worst_cost'],Q(3,8))
            self.assertEqual(result['common_quadratic'],9)
            self.assertEqual(len(result['paths']),8)
            self.assertTrue(REF.check(result))

    def test_candidate_optimum_has_independent_active_subgradient_certificate(self):
        for initial in ((Q(1,8),Q(0)),(Q(3,8),-Q(1,8)),(-Q(1,4),Q(1,8))):
            for gain in ((0,0),(-1,-2)):
                result=REF.solve(initial,gain)
                self.assertTrue(REF.check(result))
                lo,hi=result['interval']
                for a in (lo,hi,(lo+hi)/2,result['a']):
                    costs=[REF.trajectory(initial,a,gain,path['disturbances'])['cost'] for path in result['paths']]
                    self.assertGreaterEqual(max(costs),result['worst_cost'])
                bad=copy.deepcopy(result);bad['worst_cost']+=Q(1,64)
                with self.assertRaises(ValueError):REF.check(bad)
                bad=copy.deepcopy(result);bad['certificate']=dict(kind='convex-active',paths=[0],weights=[Q(0)])
                with self.assertRaises(ValueError):REF.check(bad)
                bad=copy.deepcopy(result);bad['policy_class']='general-causal-optimum'
                with self.assertRaisesRegex(ValueError,'scope'):REF.check(bad)
                bad=copy.deepcopy(result);bad['a']=lo-Q(1,64)
                with self.assertRaises(ValueError):REF.check(bad)

    def test_reference_interval_has_exact_robust_endpoints(self):
        initial=(Q(1,8),Q(0))
        for gain in ((0,0),(-1,-2)):
            result=REF.solve(initial,gain);lo,hi=result['interval']
            for a in (lo,hi):
                self.assertTrue(all(REF.trajectory(initial,a,gain,p['disturbances'])['safe'] for p in result['paths']))
            for a in (lo-Q(1,64),hi+Q(1,64)):
                self.assertTrue(any(not REF.trajectory(initial,a,gain,p['disturbances'])['safe'] for p in result['paths']))

    def test_fixed_plan_and_fixed_feedback_have_different_quantifiers(self):
        disturbances=(Q(1,8),-Q(1,8),Q(1,8))
        open_loop=REF.trajectory((Q(0),Q(0)),Q(0),(0,0),disturbances)
        feedback=REF.trajectory((Q(0),Q(0)),Q(0),(-1,-2),disturbances)
        self.assertNotEqual(open_loop['controls'],feedback['controls'])
        self.assertEqual(open_loop['nominal_states'][-1],(0,0))
        self.assertEqual(feedback['nominal_states'][-1],(0,0))
        with self.assertRaises(ValueError):REF.solve((Q(0),Q(0)),(1,2))

if __name__=='__main__':unittest.main()
