import copy
import sys
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'benchmarks/reporting/mpc08_explicit'))
import exact_regions as R


class ExactRegionTests(unittest.TestCase):
    def test_exact_partition_and_boundary_checks_reject_mutations(self):
        record=R.region_record();self.assertEqual(R.check_regions(record)['status'],'verified-exact-fixture')
        for kind in ('missing','control','value'):
            bad=copy.deepcopy(record)
            if kind=='missing':bad['regions'].pop()
            elif kind=='control':bad['regions'][0]['control'][2]+=1
            else:bad['regions'][0]['value'][0]+=1
            with self.subTest(kind=kind),self.assertRaises(ValueError):R.check_regions(bad)

    def test_whole_successor_quantifiers_and_containment(self):
        record=R.geometric_record();self.assertEqual(R.check_geometry(record)['status'],'verified-exact-fixture')
        bad=copy.deepcopy(record);bad['radius']=R.Q(0)
        with self.assertRaises(ValueError):R.check_geometry(bad)
        self.assertLess(R.area(record['sets']['robust_pre_inner']['vertices']),R.area(record['sets']['robust_pre_T_robust']['vertices']))
        self.assertLess(R.area(record['sets']['robust_pre_T_robust']['vertices']),R.area(record['sets']['robust_pre_outer']['vertices']))

    def test_output_growth_refusal_does_not_discard_analytic_count(self):
        rows=R.fiber_ladder()['rows'];self.assertEqual([r['exact_vertex_count'] for r in rows],[1,2,6,70,924,12870])
        self.assertEqual(rows[-1]['status'],'refused-output-budget');self.assertNotIn('vertices',rows[-1])


if __name__=='__main__':unittest.main()
