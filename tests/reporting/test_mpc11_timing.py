"""Immutable capture checkpoints preserve failed outcomes and reject mutation."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'benchmarks/reporting/mpc11'))
try:from run_timing import unit,validate_receipt
except ImportError:raise unittest.SkipTest('optional MPC-11 environment required')

class TimingTests(unittest.TestCase):
    def test_completed_failure_is_not_retried_and_payload_mutation_rejects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);command=[sys.executable,'-c','import sys;print("raw failure");sys.exit(2)']
            folder,first=unit(root,'trial',command)
            self.assertEqual(first['return_code'],2)
            same,second=unit(root,'trial',command)
            self.assertEqual(folder,same);self.assertEqual(first,second)
            (folder/'stdout.txt').write_text('forged')
            with self.assertRaisesRegex(ValueError,'payload binding'):validate_receipt(folder)

    def test_warmup_is_separate_and_five_arm_orders_alternate(self):
        from unittest import mock
        from run_timing import capture
        with tempfile.TemporaryDirectory() as tmp:
            calls=[]
            def fake_unit(root,key,command):
                calls.append(key);return root/key,{'status':'completed'}
            with mock.patch('run_timing.source_identity',return_value={'fixture':True}),mock.patch('run_timing.unit',side_effect=fake_unit):
                capture(Path(tmp),Path('/fixture/affine'),Path('/fixture/replay'))
            orders=[]
            for prefix in ['warmup',*[f'rep-{i:02d}' for i in range(5)]]:
                arms=[key.split('/')[1] for key in calls if key.startswith(prefix+'/') and not key.endswith('/nonlinear')]
                orders.append(arms)
            self.assertEqual(orders,[['affine','nmpc'],['affine','nmpc'],['nmpc','affine'],['affine','nmpc'],['nmpc','affine'],['affine','nmpc']])
            self.assertEqual(len(calls),18)

    def test_copied_source_mutation_rejects_after_inventory_rebound(self):
        import hashlib,inspect
        import do_mpc
        from unittest import mock
        from check_timing import checked_sources
        from run_timing import sha
        source=ROOT/'benchmarks/reporting/mpc11/nmpc.py'
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);snapshot=root/'sources';snapshot.mkdir()
            copied=snapshot/'nmpc.py';copied.write_bytes(source.read_bytes())
            environment={'source_revision':'a'*40,'identity':{'source_sha256':{'nmpc.py':sha(source)},'do_mpc_controller_source_sha256':sha(Path(inspect.getfile(do_mpc.controller.MPC)))}}
            (root/'environment.json').write_text(json.dumps(environment))
            with mock.patch('check_timing.subprocess.check_output',return_value=source.read_bytes()):
                checked_sources(root,snapshot)
                copied.write_bytes(copied.read_bytes()+b'\n# mutation\n')
                (snapshot/'SHA256SUMS').write_text(hashlib.sha256(copied.read_bytes()).hexdigest()+'  nmpc.py\n')
                with self.assertRaisesRegex(ValueError,'copied source snapshot binding'):checked_sources(root,snapshot)

    def test_committed_capture_snapshot_allows_separately_recorded_reader_changes(self):
        import inspect
        import do_mpc
        from unittest import mock
        from check_timing import checked_sources
        from run_timing import sha
        source=ROOT/'benchmarks/reporting/mpc11/nmpc.py'
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);snapshot=root/'sources';snapshot.mkdir()
            (snapshot/'nmpc.py').write_bytes(source.read_bytes())
            environment={'source_revision':'a'*40,'identity':{'source_sha256':{'nmpc.py':sha(source)},'do_mpc_controller_source_sha256':sha(Path(inspect.getfile(do_mpc.controller.MPC)))}}
            (root/'environment.json').write_text(json.dumps(environment))
            def changed_reader(path):
                return '0'*64 if path==source else sha(path)
            with mock.patch('check_timing.sha',side_effect=changed_reader),mock.patch('check_timing.subprocess.check_output',return_value=source.read_bytes()):
                result=checked_sources(root,snapshot)
                self.assertEqual(result['current_reader_sources']['nmpc.py'],'0'*64)
                self.assertNotEqual(result['capture_source_sha256']['nmpc.py'],'0'*64)
                with self.assertRaisesRegex(ValueError,'supply the committed capture source snapshot'):
                    checked_sources(root)

    def test_git_option_revision_rejects_without_git_invocation(self):
        from unittest import mock
        from check_timing import checked_sources
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            (root/'environment.json').write_text(json.dumps({'source_revision':'--output=/tmp/forged','identity':{'source_sha256':{}}}))
            with mock.patch('check_timing.subprocess.check_output') as git:
                with self.assertRaisesRegex(ValueError,'full hexadecimal commit'):checked_sources(root)
                git.assert_not_called()

    def test_partial_results_never_enter_completed_timing_samples(self):
        from check_timing import complete_checks
        ids=['SYN-NL-LV-01','SYN-NL-FUEL-01']
        self.assertTrue(complete_checks('nmpc',[{'case_id':c,'status':'complete'} for c in ids]))
        self.assertFalse(complete_checks('nmpc',[{'case_id':c,'status':'inconclusive-replay'} for c in ids]))
        modes=['cvodes','cvodes-tight','rk4','rk4-tight']
        rows=[{'case_id':c,'statuses':{m:'complete' for m in modes},'process_statuses':{m:'completed' for m in modes}} for c in ids]
        self.assertTrue(complete_checks('nonlinear',rows))
        rows[0]['statuses']['rk4']='resource_limit'
        self.assertFalse(complete_checks('nonlinear',rows))

    def test_interrupted_attempt_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);old=root/'trial/attempt-000';old.mkdir(parents=True);(old/'partial').write_text('keep')
            folder,receipt=unit(root,'trial',[sys.executable,'-c','print("done")'])
            self.assertEqual(folder.name,'attempt-001');self.assertEqual((old/'partial').read_text(),'keep')
            self.assertEqual(receipt['status'],'completed')

if __name__=='__main__':unittest.main()
