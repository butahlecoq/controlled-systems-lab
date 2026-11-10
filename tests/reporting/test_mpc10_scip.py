from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
try:import pyscipopt
except ImportError:raise unittest.SkipTest('optional locked PySCIPOpt environment required')
from benchmarks.reporting.mpc10.fixtures import fixtures
from benchmarks.reporting.mpc10.scip_reference import solve

class SCIPTests(unittest.TestCase):
    def case(self,name):return next(s for s in fixtures() if s['id']==name)
    def run_case(self,name,path=None,interrupted=False):
        with tempfile.TemporaryDirectory() as tmp:
            return solve(self.case(name),Path(tmp)/'run',path,interrupted)
    def test_parallel_edges_and_negative_reset_preserve_path_and_control(self):
        for edge in ['switch-a','switch-b']:
            path={'modes':['source','target'],'edges':[edge]};r=self.run_case('guard-negative-reset',path)
            self.assertEqual(r['path'],path);self.assertEqual(r['status'],'optimal');self.assertAlmostEqual(r['objective'],.5);self.assertAlmostEqual(r['controls'][0],1.5)
    def test_distinct_catalogue_indices_are_not_merged(self):
        for j in [1,2]:
            r=self.run_case('finite-T1',{'actions':[j]});self.assertEqual(r['path'],{'actions':[j]});self.assertAlmostEqual(r['objective'],0.)
    def test_physical_timing_failures_and_forbidden_transition(self):
        for name in ['source-pre-invariant-fails','guard-fails','destination-invariant-fails','forbidden-transition']:
            with self.subTest(name=name):self.assertEqual(self.run_case(name)['status'],'infeasible')
    def test_zero_horizon_and_actual_interrupted_search(self):
        r=self.run_case('hybrid-T0');self.assertEqual(r['path'],{'modes':['A'],'edges':[]});self.assertEqual(r['controls'],[]);self.assertEqual(r['objective'],-1.)
        r=self.run_case('hybrid-T3',interrupted=True);self.assertEqual(r['status'],'nodelimit');self.assertIsNone(r['primal_bound']);self.assertNotIn('objective',r)

if __name__=='__main__':unittest.main()
