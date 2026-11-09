import importlib.util
from fractions import Fraction as Q
from pathlib import Path
import unittest
import copy
import json
import sys
import tempfile

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

    def test_global_error_clock_is_not_reset_by_reoptimization(self):
        self.assertEqual(M.tightenings("finite-reference",2),M.tightenings("polytope"))
        self.assertNotEqual(M.tightenings("finite-reference",1),M.tightenings("finite-reference",0))

    def test_exact_reference_endpoints_replay_all_disturbances_and_exterior_fails(self):
        initial=(Q(1,8),Q(0))
        qp=M.problem(initial,M.tightenings('finite-reference'))
        for a in (qp['lower'],qp['upper']):
            _,controls=M.plan(initial,a)
            self.assertTrue(all(p['safe'] for p in M.replay(initial,controls)['paths']))
        for a in (qp['lower']-Q(1,64),qp['upper']+Q(1,64)):
            _,controls=M.plan(initial,a)
            self.assertTrue(any(not p['safe'] for p in M.replay(initial,controls)['paths']))

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

class OnlineCaptureTests(unittest.TestCase):
    def test_saved_native_protocol_is_bound_and_replay_detects_corruption(self):
        sys.path.insert(0,str(P.parent))
        import study
        import check
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);driver=folder/'fixture-driver'
            driver.write_text("""#!/usr/bin/env python3
import json,math,sys
print(json.dumps(dict(schema='csl.mpc06-online-approximation/1',direction='outer',radii=[math.sqrt(2)/8]*2,center=[0,0],orientation=[[1,0],[1,1]],construction_ns=1)),flush=True)
for i,line in enumerate(sys.stdin):
 a,b,c,lo,hi=map(float,line.split());x=min(hi,max(lo,-b/(2*a)))
 print(json.dumps(dict(schema='csl.mpc06-online-qp/1',status='completed',backend='csl.convex.highs',backend_version='test-protocol',program='nominal-qp/'+str(i),a=x,objective=a*x*x+b*x+c,prepare_ns=1,setup_ns=1,solve_ns=1)),flush=True)
""")
            driver.chmod(0o700)
            result=study.run(driver,folder/'capture',1)
            frozen=json.loads(json.dumps(result,default=study.encode))
            self.assertEqual(check.verify(frozen)['status'],'verified')
            self.assertEqual(check.verify(frozen)['completed_native_qps'],36)
            corrupt=copy.deepcopy(frozen);corrupt['attempts'][0]['steps'][0]['native']['a']=10
            with self.assertRaisesRegex(ValueError,'optimum'):check.verify(corrupt)
            corrupt=copy.deepcopy(frozen);corrupt['policy']['kind']='measured-state-reset'
            with self.assertRaisesRegex(ValueError,'policy'):check.verify(corrupt)
            corrupt=copy.deepcopy(frozen);corrupt['attempts'][0]['actual']['worst']='0'
            with self.assertRaisesRegex(ValueError,'cost'):check.verify(corrupt)

if __name__=='__main__':unittest.main()
