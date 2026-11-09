"""Behavior checks for independent nonlinear execution, not affine predictions."""
import importlib.util
import json
import math
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'benchmarks/reporting/mpc11'))
try:
    import casadi
except ImportError:
    raise unittest.SkipTest('optional MPC-11 environment required')
from nonlinear import execute_cvodes, make_request

class NonlinearTests(unittest.TestCase):
    def scenario(self,name):
        return json.loads((ROOT/f'benchmarks/reporting/mpc11/scenarios/syn-nl-{name}-01.json').read_text())

    def test_coexistence_stationary(self):
        s=self.scenario('lv');s['states'][0]['initial']=100;s['states'][1]['initial']=80
        r=execute_cvodes(make_request(s,[[0.]]*30,'fixture'))
        self.assertEqual(r['status'],'complete')
        self.assertLess(max(abs(a-b) for a,b in zip(r['physical_states'][-1],[100,80])),1e-9)

    def test_zero_command_analytic_drain(self):
        s=self.scenario('fuel');r=execute_cvodes(make_request(s,[[0.,0.]]*40,'fixture'))
        self.assertEqual(r['status'],'complete')
        decay=math.exp(-10)
        expected=[100-4*(1-decay),30-1.2*(1-decay),2*decay,.6*decay]
        self.assertLess(max(abs(a-b) for a,b in zip(r['physical_states'][-1],expected)),1e-7)

    def test_hold_association_and_domain(self):
        s=self.scenario('fuel')
        with self.assertRaises(ValueError):make_request(s,[[0.,0.]]*39,'fixture')
        s['states'][0]['initial']=-1
        r=execute_cvodes(make_request(s,[[0.,0.]]*40,'fixture'))
        self.assertEqual(r['status'],'model-domain-error')
        self.assertEqual(len(r['physical_states']),1)
        self.assertIsNone(r['objective'])

if __name__=='__main__':unittest.main()

class CSLReplayTests(NonlinearTests):
    def bridge(self,request):
        import os
        import subprocess
        import tempfile
        bridge=os.environ.get('CSL_MPC11_REPLAY_BRIDGE')
        if not bridge:self.skipTest('CSL_MPC11_REPLAY_BRIDGE required')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'request.json';path.write_text(json.dumps(request))
            p=subprocess.run([bridge,str(path)],capture_output=True,text=True,check=True)
        return json.loads(p.stdout)

    def test_cpp_analytic_and_hold_association(self):
        s=self.scenario('lv');s['states'][0]['initial']=100;s['states'][1]['initial']=80
        request=make_request(s,[[0.]]*30,'fixture');r=self.bridge(request)
        self.assertEqual(r['status'],'complete')
        self.assertLess(max(abs(a-b) for a,b in zip(r['physical_states'][-1],[100,80])),1e-9)
        request['controls'][1]=[.01]
        import subprocess
        with self.assertRaises(subprocess.CalledProcessError):self.bridge(request)

    def test_cpp_fuel_analytic_cancel_domain_and_prefix(self):
        s=self.scenario('fuel');request=make_request(s,[[0.,0.]]*40,'fixture');r=self.bridge(request)
        self.assertEqual(r['status'],'complete');decay=math.exp(-10)
        self.assertLess(max(abs(a-b) for a,b in zip(r['physical_states'][-1],[100-4*(1-decay),30-1.2*(1-decay),2*decay,.6*decay])),1e-7)
        request['cancel_before_start']=True;r=self.bridge(request)
        self.assertEqual(r['status'],'cancelled');self.assertLess(len(r['physical_states']),len(request['times']))
        del request['cancel_before_start'];request['initial_scaled'][0]=-1;r=self.bridge(request)
        self.assertEqual(r['status'],'callback_failure');self.assertEqual(len(r['physical_states']),1)
        request=make_request(s,[[0.,0.]]*40,'fixture');request['max_attempts']=1;request['abstol']=1e-20;request['reltol']=1e-20
        r=self.bridge(request);self.assertEqual(r['status'],'resource_limit');self.assertLess(len(r['physical_states']),len(request['times']))
