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
        import zipfile
        with zipfile.ZipFile(SOURCE/'evidence/comparison-525871ea/capture.zip') as z:z.extractall(root)
        capture=root/'capture';receipt=root/'verified.json'
        self.write(receipt,{'schema':'csl.mpc10.check/1','input_files':inventory(capture),'checking_revision':'a'*40,'checking_sources':{p.name:sha(p) for p in SOURCE.glob('*.py')}})
        def committed(commit,name):
            return (SOURCE/name).read_bytes() if commit=='a'*40 else (capture/'source'/name).read_bytes()
        return capture,receipt,committed
    def test_rebound_raw_bytes_reject_stale_verification(self):
        with tempfile.TemporaryDirectory() as temporary:
            capture,receipt,source=self.make(Path(temporary))
            with mock.patch('benchmarks.reporting.mpc10.evidence.git_bytes',side_effect=source):
                checked_verification(capture,receipt)
                self.write(capture/'raw.json',{'objective':1000});self.write(capture/'file-hashes.json',inventory(capture))
                with self.assertRaisesRegex(ValueError,'verification input binding'):checked_verification(capture,receipt)
    def test_rebound_copied_source_rejects_recorded_source_binding(self):
        with tempfile.TemporaryDirectory() as temporary:
            capture,_,source=self.make(Path(temporary));path=capture/'source/fixtures.py';path.write_bytes(path.read_bytes()+b'\n# altered\n');self.write(capture/'file-hashes.json',inventory(capture))
            with self.assertRaisesRegex(ValueError,'copied source binding'):checked_capture(capture)
    def test_checker_git_bytes_and_revision_are_mandatory(self):
        for mode in ('option','self-rehashed'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as temporary:
                capture,receipt,source=self.make(Path(temporary));r=json.loads(receipt.read_text())
                if mode=='option':r['checking_revision']='--output=forged'
                self.write(receipt,r)
                def committed(commit,name):
                    value=source(commit,name)
                    return value+b'changed' if mode=='self-rehashed' and commit=='a'*40 else value
                with mock.patch('benchmarks.reporting.mpc10.evidence.git_bytes',side_effect=committed):
                    with self.assertRaisesRegex(ValueError,'full hexadecimal|checking commit'):checked_verification(capture,receipt)

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

class ClosedSourceInventoryTests(unittest.TestCase):
    def test_saved_capture_rejects_empty_subset_unknown_and_self_rehashed_sources(self):
        import zipfile
        archive=SOURCE/'evidence/comparison-525871ea/capture.zip'
        for mode in ('missing','empty','subset','unknown','self-rehashed'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
                with zipfile.ZipFile(archive) as z:z.extractall(tmp)
                capture=Path(tmp)/'capture';env=json.loads((capture/'environment.json').read_text())
                if mode=='missing':env.pop('source_sha256')
                elif mode=='empty':env['source_sha256']={}
                elif mode=='subset':env['source_sha256'].pop('oracle.py')
                elif mode=='unknown':env['source_sha256']['unknown.py']='0'*64
                else:
                    source=capture/'source/oracle.py';source.write_bytes(source.read_bytes()+b'\n# changed\n');env['source_sha256']['oracle.py']=sha(source)
                (capture/'environment.json').write_text(json.dumps(env));(capture/'file-hashes.json').write_text(json.dumps(inventory(capture)))
                with self.assertRaises(ValueError):checked_capture(capture)

    def test_saved_receipt_rejects_empty_subset_unknown_checker_maps(self):
        import zipfile
        archive=SOURCE/'evidence/comparison-525871ea/capture.zip'
        for mode in ('missing','empty','subset','unknown'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
                with zipfile.ZipFile(archive) as z:z.extractall(tmp)
                capture=Path(tmp)/'capture';receipt=Path(tmp)/'receipt.json'
                maps={p.name:sha(p) for p in SOURCE.glob('*.py')}
                if mode=='empty':maps={}
                elif mode=='subset':maps.pop('oracle.py')
                else:maps['unknown.py']='0'*64
                value={'schema':'csl.mpc10.check/1','input_files':inventory(capture),'checking_sources':maps}
                if mode=='missing':value.pop('checking_sources')
                receipt.write_text(json.dumps(value))
                with self.assertRaises(ValueError):checked_verification(capture,receipt)
