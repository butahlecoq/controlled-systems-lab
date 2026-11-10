from pathlib import Path
import importlib.util
from fractions import Fraction as Q
import sys
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'benchmarks/reporting/mpc07'))
import joint_filter as J

class JointFilterTests(unittest.TestCase):
    def test_physical_exact_lower_bound_and_filter_gain(self):
        self.assertEqual(J.oracle(2,'joint'),Q(65,64)**2)
        self.assertEqual(J.oracle(8,'joint'),Q(65,64)**14)
        self.assertLess(J.oracle(2,'joint'),Q(9,4))

    def test_canonical_policy_proves_causal_filter_inclusion(self):
        s,h=J.canonical(4)
        checked=J.check_policy(4,'joint',s,h)
        self.assertEqual(checked['virtual_terminal_squared'],J.oracle(4,'joint'))
        self.assertTrue(all(row[0]>=Q(1,1024) for row in s))
        s[1][1]=Q(1)
        with self.assertRaisesRegex(ValueError,'uncertainty'):J.check_policy(4,'joint',s,h)

    def test_noninvertible_and_future_access_refuse(self):
        for mode in ('zero','future'):
            s,h=J.canonical(2)
            if mode=='zero':s[0][0]=0
            else:h[0][3]=1
            with self.assertRaises(ValueError):J.check_policy(2,'joint',s,h)

    def test_saved_native_roundoff_reconstructs_exact_response_and_rejects_real_change(self):
        import json,copy
        result=json.loads((ROOT/'tests/reporting/fixtures/mpc07-joint-gain-t08.json').read_text())
        payload=J.program(8,'fixed-gain')
        checked=J.check_result(payload,result)
        self.assertEqual(checked['upper_minus_virtual_profile_oracle_squared'],0)
        changed=copy.deepcopy(result)
        index=payload['coordinates']['state_response'][-1][0][2]
        changed['primal'][index]+=.001
        with self.assertRaises(ValueError):J.check_result(payload,changed)

    def test_fixed_filter_virtual_optimum_is_not_a_physical_lower_bound(self):
        s=[[J.RHO,Q(5,4)] for _ in range(2)];h=[[Q(0)]*4,[Q(0),Q(-1),Q(0),Q(0)]]
        checked=J.check_policy(2,'fixed-filter',s,h)
        self.assertEqual(checked['virtual_profile_oracle_squared'],Q(9,4))
        self.assertEqual(checked['physical_unrestricted_lower_squared'],Q(65,64)**2)
        self.assertNotIn('physical_lower_oracle_squared',checked)

    def test_joint_filter_has_design_variables_and_fixed_intersection(self):
        p=J.program(2,'joint');f=J.program(2,'fixed-filter')
        self.assertEqual(len(p['coordinates']['filter']),2)
        self.assertNotEqual(p['variables'],f['variables'])
        self.assertEqual(p['profile']['physical_delta_bound'],'1/64')

if __name__=='__main__':unittest.main()

class JointSavedCaptureTests(unittest.TestCase):
    def test_renewed_source_or_timeout_metadata_cannot_bless_saved_capture(self):
        import tempfile,zipfile,json,hashlib
        import report
        artifact=ROOT/'benchmarks/reporting/mpc07/evidence/joint-filter-04369201/offline.zip'
        for mode in ('source','timeout','repetitions'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as temporary:
                with zipfile.ZipFile(artifact) as z:z.extractall(temporary)
                raw=Path(temporary)/'mpc07-joint-report/RAW'
                if mode=='source':
                    target=raw/'source/joint_filter.py';target.write_bytes(target.read_bytes()+b'\n# renewed copied source\n')
                    env=json.loads((raw/'environment.json').read_text());env['source_sha256']['joint_filter.py']=hashlib.sha256(target.read_bytes()).hexdigest()
                    (raw/'environment.json').write_text(json.dumps(env));error='recorded Git commit'
                elif mode=='repetitions':
                    env=json.loads((raw/'environment.json').read_text());env['repetitions']=True
                    (raw/'environment.json').write_text(json.dumps(env));error='five repetitions'
                else:
                    folder=raw/'attempts/0000';r=json.loads((folder/'receipt.json').read_text());r['timed_out']=True
                    (folder/'receipt.json').write_text(json.dumps(r));c=json.loads((folder/'check.json').read_text())
                    c['bindings']['receipt.json']=hashlib.sha256((folder/'receipt.json').read_bytes()).hexdigest()
                    (folder/'check.json').write_text(json.dumps(c));error='current exact disposition'
                (raw/'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(raw).as_posix()}\n' for p in sorted(raw.rglob('*')) if p.is_file() and p!=raw/'SHA256SUMS'))
                with self.assertRaisesRegex(ValueError,error):report.checked_records(raw)

class JointAttainmentRenderingTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec('matplotlib') is not None,'saved rendering requires optional pinned Matplotlib')
    def test_saved_valid_positive_gap_remains_an_upper_bound_in_rendered_report(self):
        import tempfile,zipfile,json,hashlib
        import capture,report,joint_capture
        artifact=ROOT/'benchmarks/reporting/mpc07/evidence/joint-filter-04369201/offline.zip'
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary)
            with zipfile.ZipFile(artifact) as z:z.extractall(base)
            raw=base/'mpc07-joint-report/RAW'
            folder=[p for p in sorted((raw/'attempts').iterdir())
                    if (lambda r:r['horizon']==2 and r['policy_class']=='joint')(json.loads((p/'receipt.json').read_text()))][-1]
            payload=json.loads((folder/'program.json').read_text());native=json.loads((folder/'stdout.json').read_text())
            index=payload['coordinates']['control'][1][1];native['primal'][index]+=2**-40
            (folder/'stdout.json').write_text(json.dumps(native))
            checked=joint_capture.recheck(folder)
            self.assertGreater(checked['upper_minus_physical_lower_squared'],0)
            self.assertEqual(checked['status'],'verified-joint-rational-policy')
            checked['independent_check_ns']=0
            checked['bindings']={name:capture.sha(folder/name) for name in ('program.json','receipt.json','stdout.json','stderr.txt','process-resource.txt')}
            capture.write(folder/'check.json',checked)
            (raw/'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(raw).as_posix()}\n' for p in sorted(raw.rglob('*')) if p.is_file() and p!=raw/'SHA256SUMS'))
            output=base/'correct-report';report.render_joint(raw,output)
            text=(output/'index.html').read_text()
            self.assertIn('positive exact gap',text)
            self.assertNotIn('returned joint upper bound attains',text)
            summary=json.loads((output/'summary.json').read_text())
            self.assertGreater(Q(summary['joint_attainment']['maximum_gap']),0)
            group=summary['groups']['T2-sigmaoptimized-diagonal-joint']
            self.assertIsNone(group['exact_virtual_worst_squared'])
            bounds=group['virtual_policy_bound_range']
            self.assertLess(Q(bounds['minimum']),Q(bounds['maximum']))


class ExactAttainmentTextTests(unittest.TestCase):
    def test_sub_float_positive_gap_is_never_rounded_into_attainment(self):
        import report
        lower=Q(65,64)**2;gap=Q(1,10**100)
        row=dict(receipt=dict(policy_class='joint'),current_check=dict(status='verified-joint-rational-policy',
                 virtual_terminal_squared=str(lower+gap),physical_unrestricted_lower_squared=str(lower),upper_minus_physical_lower_squared=str(gap)))
        decision=report.joint_attainment([row])
        self.assertFalse(decision['all_attain_lower'])
        self.assertEqual(Q(decision['maximum_gap']),gap)
        row['current_check']['virtual_terminal_squared']=str(lower);row['current_check']['upper_minus_physical_lower_squared']='0'
        self.assertTrue(report.joint_attainment([row])['all_attain_lower'])
