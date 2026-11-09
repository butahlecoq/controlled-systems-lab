import copy
import sys
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'benchmarks/reporting/mpc08_explicit'))
import exact_regions as R
import capture_exact_regions as C


class ExactRegionTests(unittest.TestCase):
    def test_exact_partition_and_boundary_checks_reject_mutations(self):
        record=R.region_record();self.assertEqual(R.check_regions(record)['status'],'verified-exact-fixture')
        for kind in ('missing','control','value'):
            bad=copy.deepcopy(record)
            if kind=='missing':bad['regions'].pop()
            elif kind=='control':bad['regions'][0]['control'][2]+=1
            else:bad['regions'][0]['value'][0]+=1
            with self.subTest(kind=kind),self.assertRaises(ValueError):R.check_regions(bad)

    def test_recession_guard_rejects_lineality_and_unconstrained_directions(self):
        box=[(1,0,1),(-1,0,1),(0,1,1),(0,-1,1)]
        self.assertTrue(R.is_bounded(box))
        for rows in ([],[(1,0,1)],[(1,1,1),(-1,-1,1)],[(1,0,1),(0,1,1)]):
            with self.subTest(rows=rows):self.assertFalse(R.is_bounded(rows))

    def test_same_vertices_do_not_certify_an_unbounded_region(self):
        record=R.region_record();bad=copy.deepcopy(record);q=R.Q
        rows=[(-1,-1,-1),(-q(2,3),-2,-q(2,3)),(q(1,6),0,q(1,2)),(2,1,q(11,2)),(-2,-1,-1)]
        self.assertEqual(R.vertices(rows),R.vertices(record['regions'][0]['rows']))
        self.assertTrue(all(-a+2*b<=0 for a,b,c in rows))
        bad['regions'][0]['rows']=rows
        with self.assertRaisesRegex(ValueError,'unbounded'):R.check_regions(bad)

    def test_whole_successor_quantifiers_and_containment(self):
        record=R.geometric_record();self.assertEqual(R.check_geometry(record)['status'],'verified-exact-fixture')
        bad=copy.deepcopy(record);bad['radius']=R.Q(0)
        with self.assertRaises(ValueError):R.check_geometry(bad)
        self.assertLess(R.area(record['sets']['robust_pre_inner']['vertices']),R.area(record['sets']['robust_pre_T_robust']['vertices']))
        self.assertLess(R.area(record['sets']['robust_pre_T_robust']['vertices']),R.area(record['sets']['robust_pre_outer']['vertices']))

    def test_output_growth_refusal_does_not_discard_analytic_count(self):
        rows=R.fiber_ladder()['rows'];self.assertEqual([r['exact_vertex_count'] for r in rows],[1,2,6,70,924,12870])
        self.assertEqual(rows[-1]['status'],'refused-output-budget');self.assertNotIn('vertices',rows[-1])

    def test_actual_support_witness_and_repetition_mutations_reject(self):
        lookup={'S':dict(rows=[(1,0,1),(-1,0,1),(0,1,1),(0,-1,1)],direction=[1,0],minimum=-1)}
        rows=[dict(query_id='S',repetition=i,warmup=i==0,optimal=True,primal=[-1,0]) for i in range(6)]
        self.assertEqual(C.check_support(rows,lookup)['counts']['numerical-support-witness'],6)
        bad=copy.deepcopy(rows);bad[0]['primal']=[100,0]
        with self.assertRaises(ValueError):C.check_support(bad,lookup)
        bad=copy.deepcopy(rows);bad[1]=bad[0]
        with self.assertRaises(ValueError):C.check_support(bad,lookup)


if __name__=='__main__':unittest.main()
