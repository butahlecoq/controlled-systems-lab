from pathlib import Path
import hashlib
import json
import sys
import tempfile
import unittest
from unittest import mock
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from benchmarks.reporting.mpc10.evidence import checked_capture,checked_verification,inventory,sha,SOURCE

class EvidenceTests(unittest.TestCase):
    def write(self,path,value):path.write_text(json.dumps(value,indent=2)+'\n')
    def make(self,root):
        capture=root/'capture';capture.mkdir();(capture/'source').mkdir();source=SOURCE/'fixtures.py';(capture/'source/fixtures.py').write_bytes(source.read_bytes())
        self.write(capture/'environment.json',{'source_revision':'a'*40,'source_sha256':{'fixtures.py':sha(source)}});self.write(capture/'raw.json',{'objective':.5});self.write(capture/'file-hashes.json',inventory(capture))
        receipt=root/'verified.json';self.write(receipt,{'schema':'csl.mpc10.check/1','input_files':inventory(capture),'checking_sources':{'evidence.py':sha(SOURCE/'evidence.py')}})
        return capture,receipt,source.read_bytes()
    def test_rebound_raw_bytes_reject_stale_verification(self):
        with tempfile.TemporaryDirectory() as temporary:
            capture,receipt,source=self.make(Path(temporary))
            with mock.patch('benchmarks.reporting.mpc10.evidence.subprocess.check_output',return_value=source):
                checked_verification(capture,receipt)
                self.write(capture/'raw.json',{'objective':1000});self.write(capture/'file-hashes.json',inventory(capture))
                with self.assertRaisesRegex(ValueError,'verification input binding'):checked_verification(capture,receipt)
    def test_rebound_copied_source_rejects_recorded_source_binding(self):
        with tempfile.TemporaryDirectory() as temporary:
            capture,_,source=self.make(Path(temporary));path=capture/'source/fixtures.py';path.write_bytes(source+b'\n# altered\n');self.write(capture/'file-hashes.json',inventory(capture))
            with self.assertRaisesRegex(ValueError,'copied source binding'):checked_capture(capture)
    def test_failed_empty_native_stream_remains_inconclusive(self):
        from benchmarks.reporting.mpc10.check import check
        from benchmarks.reporting.mpc10.fixtures import fixtures
        from benchmarks.reporting.mpc10.oracle import solve
        s=fixtures()[0];s['fixture_sha256']=hashlib.sha256(json.dumps(s,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);case=root/s['id'];case.mkdir();self.write(case/'fixture.json',s);self.write(case/'exact.json',solve(s))
            for name in ['native','scip-process']:
                folder=case/name;folder.mkdir();(folder/'stdout.txt').write_bytes(b'');(folder/'stderr.txt').write_bytes(b'worker failed')
                self.write(folder/'process.json',{'status':'failed','return_code':1,'stdout_sha256':sha(folder/'stdout.txt'),'stderr_sha256':sha(folder/'stderr.txt')})
            with mock.patch('benchmarks.reporting.mpc10.check.fixtures',return_value=[{k:v for k,v in s.items() if k!='fixture_sha256'}]),mock.patch('benchmarks.reporting.mpc10.check.checked_capture',return_value=inventory(root)):
                self.assertEqual(check(root)['reports'][0]['status'],'inconclusive-process')
    def test_git_option_revision_refuses_before_git(self):
        with tempfile.TemporaryDirectory() as temporary:
            capture,_,_=self.make(Path(temporary));r=json.loads((capture/'environment.json').read_text());r['source_revision']='--output=/tmp/forged';self.write(capture/'environment.json',r);self.write(capture/'file-hashes.json',inventory(capture))
            with mock.patch('benchmarks.reporting.mpc10.evidence.subprocess.check_output') as git:
                with self.assertRaisesRegex(ValueError,'full hexadecimal'):checked_capture(capture)
                git.assert_not_called()

if __name__=='__main__':unittest.main()
