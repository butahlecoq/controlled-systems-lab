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

    def test_interrupted_attempt_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);old=root/'trial/attempt-000';old.mkdir(parents=True);(old/'partial').write_text('keep')
            folder,receipt=unit(root,'trial',[sys.executable,'-c','print("done")'])
            self.assertEqual(folder.name,'attempt-001');self.assertEqual((old/'partial').read_text(),'keep')
            self.assertEqual(receipt['status'],'completed')

if __name__=='__main__':unittest.main()
