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

class PublicationTests(unittest.TestCase):
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
            result=subprocess.run([sys.executable,'-B',str(report/'offline_check.py')],cwd=Path(temporary),capture_output=True,text=True,timeout=45)
            self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(json.loads(result.stdout)['attempts'],218)
            proof=next((report/'source-root/.git/objects').glob('*/*'));proof.write_bytes(proof.read_bytes()+b'changed')
            refused=subprocess.run([sys.executable,'-B',str(report/'offline_check.py')],cwd=Path(temporary),capture_output=True,text=True,timeout=45)
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
