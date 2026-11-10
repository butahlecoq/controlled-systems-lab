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


class SavedHorizonEvidenceTests(unittest.TestCase):
    def test_archive_recheck_and_rebound_native_fiber_mutation(self):
        import tempfile,zipfile,json,hashlib
        import capture_horizon_regions as C
        root=Path(__file__).resolve().parents[2]
        artifact=root/'reports/algorithm-results/mpc08-horizon-regions-01762505-20261110/capture.zip'
        with tempfile.TemporaryDirectory() as temporary:
            target=Path(temporary)
            with zipfile.ZipFile(artifact) as z:
                self.assertIsNone(z.testzip());z.extractall(target)
            self.assertEqual(C.recheck(target)['status'],'checked')
            rows=[json.loads(line) for line in (target/'stdout.jsonl').read_text().splitlines()]
            complete=next(row for row in rows if row['complete']);complete['equality_values'][0]=100
            (target/'stdout.jsonl').write_text('\n'.join(json.dumps(row) for row in rows)+'\n')
            (target/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in sorted(target.iterdir()) if p.name!='SHA256SUMS'))
            with self.assertRaisesRegex(ValueError,'complete native H relation'):C.recheck(target)

    def test_native_missing_repeat_and_promoted_resource_outcome_rejected(self):
        import zipfile,json
        import capture_horizon_regions as C
        root=Path(__file__).resolve().parents[2]
        artifact=root/'reports/algorithm-results/mpc08-horizon-regions-01762505-20261110/capture.zip'
        with zipfile.ZipFile(artifact) as z:rows=[json.loads(line) for line in z.read('stdout.jsonl').splitlines()]
        with self.assertRaisesRegex(ValueError,'inventory'):C.check_native(rows[:-1])
        bad=copy.deepcopy(rows);row=next(r for r in bad if r['termination']==3);row['complete']=True
        with self.assertRaises(ValueError):C.check_native(bad)
