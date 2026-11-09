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


class CSLReplayTests(unittest.TestCase):
    scenario=NonlinearTests.scenario
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

    def test_cli_rejects_case_dimensions_and_scales(self):
        import copy
        import subprocess
        for case,width in [('lv',1),('fuel',2)]:
            request=make_request(self.scenario(case),[[0.]*width]*(30 if case=='lv' else 40),'fixture')
            variants=[]
            bad=copy.deepcopy(request);bad['scenario']['states']=bad['scenario']['states'][:1];bad['initial_scaled']=bad['initial_scaled'][:1];variants.append(bad)
            bad=copy.deepcopy(request);bad['initial_scaled']=bad['initial_scaled'][:-1];variants.append(bad)
            bad=copy.deepcopy(request);bad['scenario']['controls']=[];variants.append(bad)
            bad=copy.deepcopy(request);bad['original_controls']=[[] for u in bad['original_controls']];bad['controls']=[[] for u in bad['controls']];variants.append(bad)
            bad=copy.deepcopy(request);bad['scenario']['states'][0]['scale']=0;variants.append(bad)
            bad=copy.deepcopy(request);bad['scenario']['states'][0]['scale']=1e309;variants.append(bad)
            for index,bad in enumerate(variants):
                with self.subTest(case=case,mutation=index):
                    with self.assertRaises(subprocess.CalledProcessError):self.bridge(bad)

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

class SavedNonlinearTests(unittest.TestCase):
    def test_saved_association_rejects_rebound_control(self):
        import os
        import shutil
        import tempfile
        import hashlib
        from check_nonlinear_saved import check
        source=os.environ.get('CSL_MPC11_NONLINEAR_BUNDLE')
        if not source:self.skipTest('CSL_MPC11_NONLINEAR_BUNDLE required')
        with tempfile.TemporaryDirectory() as tmp:
            bundle=Path(tmp)/'bundle';shutil.copytree(source,bundle)
            self.assertEqual(len(check(bundle)),2)
            request_path=bundle/'syn-nl-lv-01/rk4/request.json'
            request=json.loads(request_path.read_text());request['original_controls'][0][0]+=.001
            request_path.write_text(json.dumps(request))
            hashes_path=bundle/'file-hashes.json';hashes=json.loads(hashes_path.read_text())
            hashes[str(request_path.relative_to(bundle))]=hashlib.sha256(request_path.read_bytes()).hexdigest()
            hashes_path.write_text(json.dumps(hashes))
            with self.assertRaises(ValueError):check(bundle)

class SavedComparisonTests(unittest.TestCase):
    def test_rejects_rebound_comparison_metrics_and_identity(self):
        import os, shutil, tempfile, hashlib
        from check_nonlinear_saved import check
        source=os.environ.get('CSL_MPC11_NONLINEAR_BUNDLE')
        if not source:self.skipTest('CSL_MPC11_NONLINEAR_BUNDLE required')
        for key,value in [('max_physical_cvodes_rk4_difference',[12345,67890]),
                          ('max_physical_cvodes_sensitivity',[12,34]),
                          ('max_physical_rk4_sensitivity',[12,34]),
                          ('max_physical_affine_prediction_nonlinear_difference',[12,34]),
                          ('case_id','WRONG'),('witness_sha256','wrong'),('controls_sha256','wrong')]:
            with self.subTest(key=key),tempfile.TemporaryDirectory() as tmp:
                bundle=Path(tmp)/'bundle';shutil.copytree(source,bundle)
                path=bundle/'syn-nl-lv-01/comparison.json';record=json.loads(path.read_text());record[key]=value
                path.write_text(json.dumps(record));hp=bundle/'file-hashes.json';hashes=json.loads(hp.read_text())
                hashes[str(path.relative_to(bundle))]=hashlib.sha256(path.read_bytes()).hexdigest();hp.write_text(json.dumps(hashes))
                with self.assertRaises(ValueError):check(bundle)

if __name__=='__main__':unittest.main()

class NativeReplayBoundaryTests(unittest.TestCase):
    def test_mandatory_fields_projection_and_process_prefix(self):
        import tempfile
        from replay_evidence import read_native_attempt,RK4_FIELDS
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);raw={key:None for key in RK4_FIELDS}
            raw.update(schema='csl.mpc11.independent-replay/1',method='adaptive-rk4-step-doubling',provider='CSL::simulation',status='callback_failure',elapsed_seconds=.01)
            (folder/'stdout.json').write_text(json.dumps(raw));(folder/'stderr.txt').write_text('');(folder/'record.json').write_text(json.dumps({**raw,'objective':None}))
            receipt={'status':'completed','return_code':0,'elapsed_seconds':.1}
            call=lambda:read_native_attempt(folder,receipt,status_key='status',time_key='elapsed_seconds',extensions={'objective'})
            self.assertEqual(call()['status'],'callback_failure')
            for bad in [{},{key:value for key,value in raw.items() if key!='diagnostics'}]:
                (folder/'stdout.json').write_text(json.dumps(bad))
                with self.assertRaises(ValueError):call()
            (folder/'stdout.json').write_text(json.dumps(raw));receipt.update(status='failed',return_code=1)
            with self.assertRaises(ValueError):call()
            (folder/'record.json').unlink();self.assertIsNone(call())
            receipt.update(status='timed_out',return_code=None,elapsed_seconds=300.1);self.assertIsNone(call())
            receipt['elapsed_seconds']=1
            with self.assertRaises(ValueError):call()
