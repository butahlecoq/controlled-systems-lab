import copy
from fractions import Fraction as Q
import inspect
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from benchmarks.reporting.mpc07.online.controller import prepare,CausalController
from benchmarks.reporting.mpc07.online.capture import execute
from benchmarks.reporting.mpc07.online.check import replay

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
    def test_future_coefficients_are_refused_before_evaluation(self):
        p=copy.deepcopy(self.profile('fixed-T2-1-adf'));p['policy']['policy_M'][0][0]='1'
        with self.assertRaisesRegex(ValueError,'noncausal'):prepare(p)


if __name__=='__main__':unittest.main()
