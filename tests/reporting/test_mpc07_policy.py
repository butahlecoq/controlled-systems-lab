from pathlib import Path
import importlib.util
from fractions import Fraction as Q
import unittest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('mpc07_policy',ROOT/'benchmarks/reporting/mpc07/policy.py')
P=importlib.util.module_from_spec(spec);spec.loader.exec_module(P)

class PolicyTests(unittest.TestCase):
    def test_analytic_known_and_filter_oracles(self):
        self.assertEqual(P.oracle(2,Q(1),'fixed-plan'),4)
        self.assertEqual(P.oracle(2,Q(1),'adf'),1)
        self.assertEqual(P.oracle(8,Q(5,4),'adf'),Q(9))

    def test_independent_support_replay_and_causal_order(self):
        v=[Q(0)]*2;m=[[Q(0)]*2,[Q(-1),Q(0)]]
        checked=P.check_policy(2,Q(1),'adf',v,m)
        self.assertEqual(checked['worst_terminal_squared'],Q(1))
        self.assertEqual(checked['terminal_response'],[[Q(1,2),Q(0)],[Q(0),Q(1)]])
        m[0][1]=Q(1)
        with self.assertRaisesRegex(ValueError,'causal'):P.check_policy(2,Q(1),'adf',v,m)

    def test_future_access_wrong_shape_and_infeasible_policy_rejected(self):
        for v,m in [([0],[[0,0],[0,0]]),([0,0],[[0,0],[2,0]])]:
            with self.assertRaises(ValueError):P.check_policy(2,Q(1),'adf',v,m)

    def native_fixture(self):
        payload=P.program(2,Q(1),'adf')
        # Saved actual public-ConvexPort T2 LP witness, not a generated expected primal.
        primal=[0.,0.,-1.,0.,0.,0.,0.,1.,0.,1.,0.,.5,0.,0.,0.,1.,1.,0.,0.,1.]
        self.assertEqual(len(primal),len(payload['variables']))
        result=dict(program_sha256=payload['program_sha256'],case_id=payload['case_id'],
                    termination='completed',mathematical_outcome='optimal',primal=primal,
                    contract_diagnostics=[],primal_check=dict(row_violation=0.,variable_violation=0.))
        return payload,result

    def test_native_width_coordinate_and_auxiliary_corruption_are_rejected(self):
        import copy
        payload,result=self.native_fixture()
        self.assertEqual(P.check_result(payload,result)['worst_terminal_squared'],1)
        for mode in ('short','policy-coordinate','auxiliary'):
            changed=copy.deepcopy(result)
            if mode=='short':changed['primal'].pop()
            elif mode=='policy-coordinate':changed['primal'][2],changed['primal'][7]=changed['primal'][7],changed['primal'][2]
            else:changed['primal'][7]=-10.
            with self.subTest(mode=mode),self.assertRaises(ValueError):P.check_result(payload,changed)
        changed=copy.deepcopy(payload);changed['coordinates']['M'][1][0]=changed['coordinates']['bound']
        with self.assertRaisesRegex(ValueError,'authored'):P.check_result(changed,result)

    def test_physical_two_step_bound_is_distinct_from_filter_bound(self):
        v=[Q(0),Q(0)]
        original=P.physical_vertices_two_step(v,[[0,0],[-1,0]])
        filtered=P.physical_vertices_two_step(v,[[0,0],[-Q(4,5),0]])
        self.assertEqual(max(row['cost'] for row in original),Q(65,64)**2)
        self.assertEqual(max(row['cost'] for row in filtered),Q(389,320)**2)
        self.assertLess(max(row['cost'] for row in filtered),P.oracle(2,Q(5,4),'response'))
        self.assertTrue(all(abs(row['control'])<=1 for row in filtered))

    def test_profile_identifiers_are_safe_artifact_components(self):
        for sigma in P.SIGMAS:
            self.assertNotIn('/',P.program(2,sigma,'adf')['case_id'])

    def test_lp_distinct_formulations_bound_same_policy_class(self):
        a=P.program(4,Q(1),'adf');s=P.program(4,Q(1),'response')
        self.assertGreater(len(s['variables']),len(a['variables']))
        self.assertGreater(s['constraints']['rows'],a['constraints']['rows'])
        self.assertEqual(a['linear'][a['coordinates']['bound']],1)
        for name in ('future','unrestricted','author-sls'):
            with self.assertRaises(ValueError):P.program(2,Q(1),name)

if __name__=='__main__':unittest.main()

class SavedOutcomeTests(unittest.TestCase):
    def test_empty_stopped_process_is_inconclusive_before_parsing(self):
        import tempfile,json,sys
        sys.path.insert(0,str(ROOT/'benchmarks/reporting/mpc07'))
        import capture
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);(folder/'receipt.json').write_text(json.dumps(dict(status='wall-limit',returncode=-9,timed_out=True)))
            (folder/'stdout.json').write_bytes(b'')
            self.assertEqual(capture.recheck(folder)['status'],'inconclusive-process-outcome')

    def test_summary_retains_unverified_attempts_in_denominator(self):
        import sys
        sys.path.insert(0,str(ROOT/'benchmarks/reporting/mpc07'))
        import report
        receipt=dict(warmup=False,horizon=2,sigma='1',policy_class='adf',variables=20,rows=39,nonzeros=77,
                     python_prepare_ns=10,whole_process_ns=100)
        rows=[dict(receipt=receipt,current_check=dict(status='verified-rational-reconstruction',worst_terminal_squared='1'),native_setup_ns=20,native_port_run_ns=30),
              dict(receipt=receipt,current_check=dict(status='inconclusive-process-outcome'))]
        summary=report.metrics(rows)['T2-sigma1-adf']
        self.assertEqual(summary['attempts'],2);self.assertEqual(summary['verified'],1)
        self.assertEqual(summary['outcomes']['inconclusive-process-outcome'],1)

    def test_spawn_failure_is_a_retained_process_outcome(self):
        import tempfile,sys
        sys.path.insert(0,str(ROOT/'benchmarks/reporting/mpc07'))
        import capture
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary)
            receipt=capture.attempt(folder,folder/'missing-binary',P.program(2,Q(1),'adf'))
            self.assertEqual(receipt['status'],'spawn-failed')
            self.assertIsNone(receipt['returncode'])
            self.assertEqual((folder/'stdout.json').read_bytes(),b'')
            self.assertTrue((folder/'process-resource.txt').is_file())

class ProvenanceRegressionTests(unittest.TestCase):
    def test_timeout_flag_cannot_bless_completed_zero_return(self):
        import tempfile,json,sys
        sys.path.insert(0,str(ROOT/'benchmarks/reporting/mpc07'));import capture
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary)
            (folder/'receipt.json').write_text(json.dumps(dict(status='completed',returncode=0,timed_out=True,whole_process_ns=100)))
            # No valid JSON is required: receipt coherence is checked first.
            (folder/'stdout.json').write_bytes(b'')
            self.assertEqual(capture.recheck(folder)['status'],'inconclusive-invalid-process-receipt')

    def test_self_rehashed_source_snapshot_requires_git_identity(self):
        import tempfile,json,zipfile,hashlib,sys
        sys.path.insert(0,str(ROOT/'benchmarks/reporting/mpc07'));import report
        artifact=ROOT/'benchmarks/reporting/mpc07/evidence/bounded-policy-0e821c2a/offline.zip'
        with tempfile.TemporaryDirectory() as temporary:
            with zipfile.ZipFile(artifact) as saved:saved.extractall(temporary)
            raw=Path(temporary)/'mpc07-report/RAW'
            target=raw/'source/policy.py';target.write_bytes(target.read_bytes()+b'\n# changed copied source\n')
            environment=json.loads((raw/'environment.json').read_text())
            environment['source_sha256']['policy.py']=hashlib.sha256(target.read_bytes()).hexdigest()
            (raw/'environment.json').write_text(json.dumps(environment))
            (raw/'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(raw).as_posix()}\n' for p in sorted(raw.rglob('*')) if p.is_file() and p.name!='SHA256SUMS'))
            with self.assertRaisesRegex(ValueError,'recorded Git commit'):report.checked_records(raw)

    def test_missing_inventory_and_option_revision_refuse_before_source_io(self):
        import tempfile,sys
        sys.path.insert(0,str(ROOT/'benchmarks/reporting/mpc07'));import report
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary)
            for revision,inventory,error in [('--output='+str(folder/'outside'),{},'full pinned'),('a'*40,{},'mandatory')]:
                environment=dict(source_commit=revision,native_source_commit=report.NATIVE_REVISION,source_sha256=inventory)
                with self.assertRaisesRegex(ValueError,error):report.authenticate_sources(folder,environment,ROOT)
            self.assertEqual(list(folder.iterdir()),[])

    def test_rebound_timeout_receipt_cannot_retain_saved_verified_disposition(self):
        import tempfile,json,zipfile,hashlib,sys
        sys.path.insert(0,str(ROOT/'benchmarks/reporting/mpc07'));import report
        artifact=ROOT/'benchmarks/reporting/mpc07/evidence/bounded-policy-0e821c2a/offline.zip'
        with tempfile.TemporaryDirectory() as temporary:
            with zipfile.ZipFile(artifact) as saved:saved.extractall(temporary)
            raw=Path(temporary)/'mpc07-report/RAW';attempt=raw/'attempts/0000'
            receipt=json.loads((attempt/'receipt.json').read_text());receipt['timed_out']=True
            (attempt/'receipt.json').write_text(json.dumps(receipt))
            checked=json.loads((attempt/'check.json').read_text())
            checked['bindings']['receipt.json']=hashlib.sha256((attempt/'receipt.json').read_bytes()).hexdigest()
            (attempt/'check.json').write_text(json.dumps(checked))
            (raw/'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(raw).as_posix()}
' for p in sorted(raw.rglob('*')) if p.is_file() and p!=raw/'SHA256SUMS'))
            with self.assertRaisesRegex(ValueError,'disposition differs'):report.checked_records(raw)
