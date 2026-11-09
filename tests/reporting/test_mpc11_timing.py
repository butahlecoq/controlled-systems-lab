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

    def test_interrupted_attempt_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);old=root/'trial/attempt-000';old.mkdir(parents=True);(old/'partial').write_text('keep')
            folder,receipt=unit(root,'trial',[sys.executable,'-c','print("done")'])
            self.assertEqual(folder.name,'attempt-001');self.assertEqual((old/'partial').read_text(),'keep')
            self.assertEqual(receipt['status'],'completed')

if __name__=='__main__':unittest.main()
