import copy
from fractions import Fraction as Q
import inspect
import hashlib
import tempfile
import shutil
import subprocess
import zipfile
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from benchmarks.reporting.mpc07.online.controller import prepare,CausalController
from benchmarks.reporting.mpc07.online.capture import execute
from benchmarks.reporting.mpc07.online.check import replay,check,checked_verification,inventory

INPUT=Path(__file__).resolve().parents[2]/'benchmarks/reporting/mpc07/online/profiles.json'


class OnlinePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.inputs=json.loads(INPUT.read_bytes())
    def profile(self,suffix):return next(p for p in self.inputs['profiles'] if p['id']==suffix)
    def test_api_cannot_receive_present_or_future_uncertainty(self):
        self.assertEqual(list(inspect.signature(CausalController.observe).parameters),['self','state'])
        self.assertEqual(list(inspect.signature(CausalController.action).parameters),['self'])
        p=self.profile('fixed-T2-1-adf');a=CausalController(prepare(p));b=CausalController(prepare(p))
        a.observe([0,0]);b.observe([0,0]);self.assertEqual(a.action(),b.action())
        a.observe([0,1]);b.observe([0,-1]);self.assertNotEqual(a.action(),b.action())
    def test_joint_reconstructs_both_normalized_past_coordinates(self):
        p=self.profile('joint-T2-optimized-diagonal-joint');c=CausalController(prepare(p));c.observe([0,0]);self.assertEqual(c.action(),0)
        residual,zeta=c.observe([.125,1]);self.assertEqual(residual,(.125,1))
        self.assertEqual(zeta,(.125/float(Q(p['policy']['filter'][0][0])),1/float(Q(p['policy']['filter'][0][1]))))
    def test_every_selected_policy_runs_both_physical_traces_and_exact_replay(self):
        self.assertEqual(len(self.inputs['profiles']),36)
        for p in self.inputs['profiles']:
            for f in self.inputs['trace_families']:
                with self.subTest(profile=p['id'],family=f):
                    result=execute(p,f,0);checked=replay(p,result,self.inputs['tolerance']);self.assertEqual(checked['status'],'verified-numerical-evaluation')
    def test_mutated_action_state_information_and_clock_are_rejected(self):
        p=self.profile('joint-T2-optimized-diagonal-joint');original=execute(p,'positive',0)
        for field in ('control','next_state','past_innovation','query_ns'):
            value=json.loads(json.dumps(original));row=value['steps'][1]
            if field=='query_ns':row[field]=-1
            elif field in ('next_state','past_innovation'):row[field][0]+=.01
            else:row[field]+=.01
            with self.subTest(field=field),self.assertRaises(ValueError):replay(p,value,self.inputs['tolerance'])
    def test_failure_keeps_the_action_and_observation_already_performed(self):
        p=self.profile('fixed-T2-1-adf')
        with patch('benchmarks.reporting.mpc07.online.capture.plant',side_effect=ValueError('plant test refusal')):row=execute(p,'positive',0)
        self.assertEqual(row['status'],'failed');self.assertEqual(row['steps'][0]['control'],0);self.assertEqual(row['steps'][0]['observation'],[0,0]);self.assertIn('plant test refusal',row['error'])
    def test_capture_refuses_missing_posix_support_without_creating_output(self):
        from benchmarks.reporting.mpc07.online import capture
        with tempfile.TemporaryDirectory() as tmp,patch.object(capture,'resource',None):
            destination=Path(tmp)/'capture'
            with self.assertRaisesRegex(ValueError,'POSIX'):capture.capture(destination)
            self.assertFalse(destination.exists())
    def test_archived_capture_refuses_rebound_source_and_returned_action(self):
        artifact=INPUT.parents[1]/'evidence/online-evaluation-0524f7e4'
        for mode in ('source-map','source','action'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
                with zipfile.ZipFile(artifact/'capture.zip') as z:z.extractall(tmp)
                root=Path(tmp)/'capture'
                def write(path,value):path.write_text(json.dumps(value,sort_keys=True)+'\n')
                if mode=='source-map':
                    env=json.loads((root/'environment.json').read_bytes());env['source_sha256']={};write(root/'environment.json',env)
                elif mode=='source':
                    env=json.loads((root/'environment.json').read_bytes());name='benchmarks/reporting/mpc07/online/controller.py';path=root/'source'/name;path.write_bytes(path.read_bytes()+b'\n# mutated\n');env['source_sha256'][name]=hashlib.sha256(path.read_bytes()).hexdigest();write(root/'environment.json',env)
                else:
                    path=root/'measured/stdout.jsonl';rows=[json.loads(s) for s in path.read_text().splitlines()];rows[0]['steps'][0]['control']+=.01;path.write_text(''.join(json.dumps(r)+'\n' for r in rows));process=json.loads((root/'measured/process.json').read_bytes());process['stdout_sha256']=hashlib.sha256(path.read_bytes()).hexdigest();write(root/'measured/process.json',process)
                (root/'SHA256SUMS').write_text(''.join(h+'  '+n+'\n' for n,h in inventory(root).items()))
                with self.assertRaises(ValueError):check(root)
    def test_pre_online_commit_cannot_authenticate_online_capture(self):
        artifact=INPUT.parents[1]/'evidence/online-evaluation-0524f7e4'
        with tempfile.TemporaryDirectory() as tmp:
            with zipfile.ZipFile(artifact/'capture.zip') as z:z.extractall(tmp)
            root=Path(tmp)/'capture';env=json.loads((root/'environment.json').read_bytes())
            revision='f4950e7ee72c00809340ff316f572952bb142802';env['source_revision']=revision
            names=[n for n in env['source_sha256'] if '/online/' not in n]
            shutil.rmtree(root/'source');env['source_sha256']={}
            for name in names:
                data=subprocess.check_output(['git','show','--end-of-options',revision+':'+name],cwd=INPUT.parents[4]);path=root/'source'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data);env['source_sha256'][name]=hashlib.sha256(data).hexdigest()
            (root/'environment.json').write_text(json.dumps(env))
            (root/'SHA256SUMS').write_text(''.join(h+'  '+n+'\n' for n,h in inventory(root).items()))
            from benchmarks.reporting.mpc07.online.check import authenticated
            with self.assertRaisesRegex(ValueError,'online source profile'):authenticated(root)
    def test_captured_input_bytes_must_match_committed_profile(self):
        artifact=INPUT.parents[1]/'evidence/online-evaluation-0524f7e4'
        with tempfile.TemporaryDirectory() as tmp:
            with zipfile.ZipFile(artifact/'capture.zip') as z:z.extractall(tmp)
            root=Path(tmp)/'capture';path=root/'inputs.json';path.write_bytes(path.read_bytes()+b'\n')
            env=json.loads((root/'environment.json').read_bytes());env['input_sha256']=hashlib.sha256(path.read_bytes()).hexdigest();(root/'environment.json').write_text(json.dumps(env))
            (root/'SHA256SUMS').write_text(''.join(h+'  '+n+'\n' for n,h in inventory(root).items()))
            from benchmarks.reporting.mpc07.online.check import authenticated
            with self.assertRaisesRegex(ValueError,'committed input'):authenticated(root)

    def test_figure_receipt_needs_full_checker_map_and_actual_replay(self):
        artifact=INPUT.parents[1]/'evidence/online-evaluation-0524f7e4'
        with tempfile.TemporaryDirectory() as tmp:
            with zipfile.ZipFile(artifact/'capture.zip') as z:z.extractall(tmp)
            root=Path(tmp)/'capture';path=Path(tmp)/'receipt.json';receipt=json.loads((artifact/'verification.json').read_bytes())
            receipt['checking_sources']={};path.write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError,'checking source'):checked_verification(root,path)

    def test_future_coefficients_are_refused_before_evaluation(self):
        p=copy.deepcopy(self.profile('fixed-T2-1-adf'));p['policy']['policy_M'][0][0]='1'
        with self.assertRaisesRegex(ValueError,'noncausal'):prepare(p)


if __name__=='__main__':unittest.main()
