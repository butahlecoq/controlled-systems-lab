"""Observable exact-model, complete-family and stage-set evidence checks."""
from copy import deepcopy
from fractions import Fraction as Q
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
SCRIPT=ROOT/'docs/research/tools/check_b04_source_moments.py'
spec=importlib.util.spec_from_file_location('b04_moment_certificate',SCRIPT)
C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)


def trajectory(initial,controls):
    states=[list(map(Q,initial))]
    for u in controls:
        a,b,c,d=states[-1]
        states.append([a+Q(2208,110)*u,b-Q(25,4)*a,c-Q(1152,110)*u,d-Q(25,4)*c])
    return states


def objective_squared(z):
    a,b,c,d=z
    return (1200-a)**2+b*b+Q(64,9)*(450-c)**2+Q(64,9)*d*d+(b-Q(8,3)*d)**2


def inside(point,poly):
    p=tuple(map(Q,point));vs=[tuple(map(Q,v)) for v in poly]
    if len(vs)==1:return p==vs[0]
    if len(vs)==2:
        a,b=vs;cross=(b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])
        return cross==0 and all(min(a[j],b[j])<=p[j]<=max(a[j],b[j]) for j in (0,1))
    return bool(vs) and all((b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])>=0 for a,b in zip(vs,vs[1:]+vs[:1]))


class B04SourceMomentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs=C.load_inputs();cls.record=C.build_certificate(cls.inputs)

    def test_separate_source_cases_and_exact_rounding_band(self):
        exact=self.record['commented_initial'];rounded=self.record['active_rounded_initial']
        a=Q(exact['minimum_squared']);b=Q(rounded['minimum_squared'])
        self.assertTrue(Q('30.8985')**2<=a<Q('30.8995')**2)
        self.assertTrue(Q('31.1205')**2<=b<Q('31.1215')**2)
        self.assertNotEqual(exact['scenario_id'],rounded['scenario_id'])
        self.assertNotEqual(exact['initial'],rounded['initial'])

    def test_full_dynamics_and_cost_satisfy_global_identity(self):
        histories=[[Q(0)]*16,[Q(1,10),Q(-1,5),Q(1,10)]+[Q(0)]*13]
        for key in ('commented_initial','active_rounded_initial'):
            case=self.record[key];alpha,beta=map(Q,case['quadratic_coefficients'])
            for u in histories:
                states=trajectory(case['initial'],u)
                self.assertTrue(all(1176<=z[0]<=1224 and 432<=z[2]<=468 for z in states))
                s=sum(u);m=sum((15-j)*x for j,x in enumerate(u))
                expected=Q(case['minimum_squared'])+alpha*(s-Q(case['sum_control']))**2+beta*(m-Q(case['weighted_control_sum']))**2
                self.assertEqual(objective_squared(states[-1]),expected)
                self.assertGreater(expected,Q(case['minimum_squared']))

    def test_distinct_complete_optimal_histories_and_joint_state_lift(self):
        for key in ('commented_initial','active_rounded_initial'):
            case=self.record[key];u=list(map(Q,case['interior_witness_controls']));v=u[:]
            for j,delta in enumerate((Q(1,100),Q(-2,100),Q(1,100))):v[j]+=delta
            self.assertNotEqual(u,v)
            family=case['optimal_family'];h=family['H_matrix']
            self.assertEqual(h['row_count'],64)
            for controls in (u,v):
                for row in h['rows']:
                    self.assertLessEqual(sum(Q(a)*b for a,b in zip(row['coefficients'],controls)),Q(row['rhs']))
                self.assertEqual(sum(controls),Q(case['sum_control']))
                self.assertEqual(sum((15-j)*x for j,x in enumerate(controls)),Q(case['weighted_control_sum']))
                states=trajectory(case['initial'],controls)
                self.assertEqual(objective_squared(states[-1]),Q(case['minimum_squared']))
                for stage in family['affine_state_history_lift']['stages']:
                    lifted=[Q(a)+sum(Q(c)*b for c,b in zip(row,controls)) for a,row in zip(stage['offset'],stage['control_matrix'])]
                    self.assertEqual(lifted,states[stage['stage']])
            self.assertNotEqual(trajectory(case['initial'],u)[1],trajectory(case['initial'],v)[1])
            self.assertEqual(trajectory(case['initial'],u)[-1],trajectory(case['initial'],v)[-1])

    def test_semantic_source_edit_and_certificate_tampering_refused(self):
        changed=deepcopy(self.inputs);changed['model']['B']=['17','0','-12','0']
        with self.assertRaises(ValueError):C.build_certificate(changed)
        changed=deepcopy(self.record);changed['commented_initial']['minimum_squared']='0'
        with self.assertRaises(ValueError):C.verify_certificate(changed,self.inputs)

    def test_cli_refuses_to_overwrite_existing_output(self):
        with tempfile.TemporaryDirectory(prefix='b04-cert-output-') as tmp:
            output=Path(tmp)/'existing.json';output.write_text('preserve this file')
            result=subprocess.run([sys.executable,str(SCRIPT),'--write',str(output)],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(output.read_text(),'preserve this file')

    def test_stage_sets_and_boundary_cases(self):
        from scripts.reports.b04_source_moments import geometry as G
        record=G.build_stage_sets(self.record);stages=record['stages']
        self.assertEqual(len(stages),17)
        case=self.record['commented_initial'];lo,hi=map(Q,case['prefix_bounds'])
        first=stages[1]['moment_sets']['forward']
        self.assertEqual([list(map(Q,p)) for p in first],[[max(Q(-1),lo),Q(0)],[min(Q(1),hi),Q(0)]])
        s,m=Q(case['sum_control']),Q(case['weighted_control_sum'])
        lower=max(lo,s-1);upper=min(hi,s+1)
        self.assertEqual([list(map(Q,p)) for p in stages[15]['moment_sets']['backward']],[[lower,m-lower],[upper,m-upper]])
        for k,stage in enumerate(stages):
            self.assertEqual(stage['stage'],k)
            self.assertEqual(list(map(Q,stage['physical_witness'])),list(map(Q,case['interior_witness_states'][k])))
            for kind in ('forward','backward','corridor'):self.assertTrue(inside(stage['moment_witness'],stage['moment_sets'][kind]))
        self.assertEqual(len(stages[0]['moment_sets']['corridor']),1)
        self.assertEqual(len(stages[-1]['moment_sets']['corridor']),1)
        self.assertTrue(all(Q(stages[k]['corridor_area'])>0 for k in range(2,15)))

    def test_saved_mathematical_certificate_rechecks(self):
        C.verify_certificate(json.loads(C.DEFAULT_CERTIFICATE.read_text()),self.inputs)


if __name__=='__main__':unittest.main()
