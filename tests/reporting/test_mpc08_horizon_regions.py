from pathlib import Path
import sys
import copy
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'benchmarks/reporting/mpc08_explicit'))
import horizon_regions as H


class HorizonRegionsTests(unittest.TestCase):
    def test_full_original_quadratic_horizon_coverage(self):
        for n,cells,area in ((2,9,H.Q(47,3)),(4,7,H.Q(23)),(8,1,H.Q(24))):
            with self.subTest(horizon=n):
                record=H.produce(n);result=H.check(record)
                self.assertEqual((result['cells'],result['area']),(cells,area))
                self.assertEqual(record['family']['terminal_map'],[[n-1-j for j in range(n)],[1]*n])
                self.assertEqual(record['family']['intermediate_states'],'unconstrained')

    def test_missing_cell_and_forged_endpoint_or_family_rejected(self):
        source=H.produce(2)
        for kind in ('missing','endpoint','multiplier','fiber','unbounded'):
            r=copy.deepcopy(source)
            if kind=='missing':r['cells'].pop()
            elif kind=='endpoint':r['cells'][0]['endpoint'][0]=(H.Q(0),H.Q(0),H.Q(100))
            elif kind=='multiplier':r['cells'][-1]['multipliers']=[(H.Q(0),H.Q(0),H.Q(-1))]*len(r['cells'][-1]['active'])
            elif kind=='fiber':r['family']['terminal_map'][0][0]+=1
            else:r['cells'][0]['rows']=r['cells'][0]['rows'][4:]
            with self.subTest(kind=kind),self.assertRaises(ValueError):H.check(r)

    def test_corner_image_matches_all_zonotope_facets(self):
        for n in (2,4,8):
            rows=H.endpoint_rows(n)[:-4]
            for u in H.product((-1,1),repeat=n):
                z=(sum((n-1-j)*u[j] for j in range(n)),sum(u))
                self.assertTrue(all(a*z[0]+b*z[1]<=rhs[2] for a,b,rhs in rows))
            for a,b,rhs in rows:
                self.assertEqual(rhs[2],sum(abs(a*(n-1-j)+b) for j in range(n)))
        with self.assertRaises(ValueError):H.produce(16)
