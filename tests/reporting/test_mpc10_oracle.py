from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'benchmarks/reporting/mpc10'))
from fixtures import fixtures
from oracle import solve

class OracleTests(unittest.TestCase):
    def case(self,name):return next(s for s in fixtures() if s['id']==name)
    def test_published_2d_literal_and_reset_ties(self):
        r=solve(self.case('published-2d-identity'));self.assertEqual(r['optimum'],'0');self.assertEqual(r['branches'][0]['witness']['states'],['-1','0'])
        r=solve(self.case('guard-negative-reset'));self.assertEqual(r['optimum'],'1/2');self.assertEqual(len(r['all_optimal_paths']),2);self.assertEqual(r['branches'][0]['witness']['continuous_controls'],['3/2'])
    def test_timing_failures_forbidden_and_empty(self):
        for name in ['source-pre-invariant-fails','guard-fails','destination-invariant-fails','forbidden-transition','finite-empty-T1']:
            with self.subTest(name=name):self.assertIsNone(solve(self.case(name))['optimum'])
        self.assertEqual(len(solve(self.case('finite-empty-T0'))['branches']),1)
    def test_duplicate_catalogue_identity_and_continuous_flat_family(self):
        r=solve(self.case('finite-T1'));self.assertEqual(r['all_optimal_paths'],[{'actions':[1]},{'actions':[2]}])
        r=solve(self.case('flat-continuous-ties'));self.assertGreater(len(r['all_optimal_paths']),1)
    def test_zero_horizon_has_no_transition(self):
        r=solve(self.case('hybrid-T0'));self.assertEqual(r['branches'][0]['path'],{'modes':['A'],'edges':[]})

if __name__=='__main__':unittest.main()
