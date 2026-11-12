from pathlib import Path
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.reports import stage_mpc07_comparison as S
from benchmarks.reporting.mpc07 import capture as mpc07_capture

class PublicationTests(unittest.TestCase):
    def test_readme_source_comes_from_the_sealed_capture_bundle(self):
        self.assertEqual(hashlib.sha256(mpc07_capture.archived_readme()).hexdigest(),
                         '631c84d73f1b228bd6797a0e2ccf5e4d409fafcf6ef9a3cf820be69f89cd40cb')
    def site(self,root):
        site=root/'site';(site/'examples').mkdir(parents=True)
        for path in (site/'index.html',site/'examples/index.html'):path.write_text('<html><body>existing</body></html>')
        return site
    def test_all_saved_math_and_offline_authentication(self):
        with tempfile.TemporaryDirectory() as temporary:
            site=self.site(Path(temporary));route=S.stage(site)
            self.assertIn(route+'/index.html#minimal-example',(site/'examples/index.html').read_text())
            report=site/route;checks=json.loads((report/'verification.json').read_text())
            self.assertEqual(checks['attempts'],218);self.assertEqual(checks['joint_attainment']['maximum_gap'],'0')
            self.assertEqual((checks['online']['episodes'],checks['online']['stages']),(864,4032))
            self.assertEqual((checks['online']['measured_episodes'],checks['online']['measured_stages']),(360,1680))
            self.assertEqual(json.loads((report/'online-figure-data.json').read_bytes())['verification_sha256'],hashlib.sha256((report/'online-verification.json').read_bytes()).hexdigest())
            self.assertIn('intrinsic latency',(report/'verification.json').read_text());self.assertIn('timestamp',(report/'index.html').read_text())
            self.assertTrue((report/'figures/online-policy-traces.svg').is_file())
            result=subprocess.run([sys.executable,'-B',str(report/'offline_check.py')],cwd=Path(temporary),capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(json.loads(result.stdout)['attempts'],218)
            proof=next((report/'source-root/.git/objects').glob('*/*'));proof.write_bytes(proof.read_bytes()+b'changed')
            refused=subprocess.run([sys.executable,'-B',str(report/'offline_check.py')],cwd=Path(temporary),capture_output=True,text=True,timeout=60)
            self.assertNotEqual(refused.returncode,0);self.assertIn('invalid source object',refused.stderr)
            with self.assertRaisesRegex(ValueError,'exists'):S.stage(site)
    def test_tampered_frozen_inputs_refuse_before_site_writes(self):
        for name in ('offline.zip','summary.json','current-rechecks.json'):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);sources={}
                for key,path in S.SOURCES.items():sources[key]=root/key;shutil.copytree(path,sources[key])
                target=sources[S.FIXED_CURRENT]/name;target.write_bytes(target.read_bytes()+b' ')
                site=self.site(root);before=(site/'index.html').read_bytes()
                with self.assertRaises(ValueError):S.stage(site,sources)
                self.assertEqual((site/'index.html').read_bytes(),before);self.assertEqual(len(list(site.iterdir())),2)
    def test_checker_uses_private_namespace_without_touching_generic_modules(self):
        import textwrap
        code=textwrap.dedent("\n            from pathlib import Path\n            import sys,types\n            root=Path(sys.argv[1]);sys.path.insert(0,str(root))\n            sentinels={name:types.ModuleType(name) for name in ('report','capture','policy','joint_filter','joint_capture')}\n            sys.modules.update(sentinels)\n            from scripts.reports import stage_mpc07_comparison as stage\n            from benchmarks.reporting.mpc07 import report\n            assert stage._checker(root) is report\n            assert all(sys.modules[name] is module for name,module in sentinels.items())\n")
        with tempfile.TemporaryDirectory() as temporary:
            result=subprocess.run([sys.executable,'-B','-c',code,str(ROOT)],cwd=temporary,capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_missing_or_rehashed_online_assets_refuse_before_site_write(self):
        for name in ('online-policy-traces.svg','capture.zip'):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);sources={}
                for key,path in S.ONLINE_SOURCES.items():sources[key]=root/key;shutil.copytree(path,sources[key])
                (sources[S.ONLINE]/name).unlink()
                site=self.site(root);before={p:p.read_bytes() for p in site.rglob('*') if p.is_file()}
                with self.assertRaises(ValueError):S.stage(site,online_sources=sources)
                self.assertEqual(before,{p:p.read_bytes() for p in site.rglob('*') if p.is_file()})
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);sources={}
            for key,path in S.ONLINE_SOURCES.items():sources[key]=root/key;shutil.copytree(path,sources[key])
            target=sources[S.ONLINE_CURRENT]/'verification.json';target.write_bytes(target.read_bytes()+b'\n')
            folder=sources[S.ONLINE_CURRENT];(folder/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in sorted(folder.iterdir()) if p.name!='SHA256SUMS'))
            with self.assertRaisesRegex(ValueError,'reviewed frozen'):S.online_inputs(sources)
    def test_online_helper_and_committed_input_inventory_is_closed(self):
        online=S.online_inputs();self.assertEqual(len(online['reading']['checking_sources']),12)
        from unittest import mock
        bad=dict(online['files'][S.ONLINE_CURRENT]);value=json.loads(bad['verification.json']);value['checking_sources']={};bad['verification.json']=S.encoded(value)
        original=S.frozen
        def forged(source,identity):return bad if identity==S.ONLINE_CURRENT else original(source,identity)
        with mock.patch.object(S,'frozen',side_effect=forged),self.assertRaisesRegex(ValueError,'mandatory online'):S.online_inputs()

    def test_unsafe_paths_and_zip_members(self):
        for name in ('../escape','/absolute','a/../b','a//b','a\\b'):
            with self.subTest(name=name),self.assertRaises(ValueError):S.safe_name(name)
        import io,zipfile
        data=io.BytesIO()
        with zipfile.ZipFile(data,'w') as z:z.writestr('../escape',b'bad')
        with self.assertRaises(ValueError):S.checked_zip(data.getvalue())
    def test_stale_helper_bytes_cannot_be_exported(self):
        from unittest import mock
        with mock.patch.object(S,'helper_revision',return_value='0'*40),mock.patch.object(S.subprocess,'check_output',side_effect=subprocess.CalledProcessError(128,'git')):
            with self.assertRaises((ValueError,subprocess.CalledProcessError)):S.source_export({})

if __name__=='__main__':unittest.main()
