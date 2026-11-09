from pathlib import Path
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from benchmarks.reporting.mpc10.fixtures import fixtures
from benchmarks.reporting.mpc10.oracle import solve
from benchmarks.reporting.mpc10.check import check_native

@unittest.skipUnless(os.environ.get('CSL_MPC10_BRIDGE'),'optional actual CSL MPC10 bridge required')
class NativeTests(unittest.TestCase):
    def run_case(self,name):
        s=next(s for s in fixtures() if s['id']==name);s['fixture_sha256']=hashlib.sha256(json.dumps(s,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'fixture.json';p.write_text(json.dumps(s));native=subprocess.run([os.environ['CSL_MPC10_BRIDGE'],str(p)],capture_output=True,timeout=90,check=True)
        return s,json.loads(native.stdout)
    def test_real_rows_values_ties_and_zero_horizon(self):
        for name in ['published-2d-identity','guard-negative-reset','finite-T1','mixed-T1','hybrid-T0','flat-continuous-ties']:
            with self.subTest(name=name):
                s,r=self.run_case(name);checked=check_native(s,solve(s),r);self.assertEqual(checked['status'],'verified-bounded-branches')
    def test_row_mutation_rejects_even_when_anchor_still_satisfies_it(self):
        s,r=self.run_case('published-2d-identity');r['branches'][0]['program']['matrix'][0][0]*=2
        with self.assertRaisesRegex(ValueError,'native rows differ'):check_native(s,solve(s),r)
    def test_omitted_parallel_tie_and_changed_face_reject(self):
        s,r=self.run_case('guard-negative-reset');missing=copy.deepcopy(r);missing['branches'].pop()
        with self.assertRaisesRegex(ValueError,'branch inventory'):check_native(s,solve(s),missing)
        r['candidate_optimal_faces'][0]['optimal_relation']['values'][-1]+=.25
        with self.assertRaisesRegex(ValueError,'candidate face differs'):check_native(s,solve(s),r)

if __name__=='__main__':unittest.main()
