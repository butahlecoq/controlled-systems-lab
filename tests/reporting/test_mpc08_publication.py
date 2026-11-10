from pathlib import Path
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.reports import stage_mpc08_complete as S


def site(folder):
    folder.mkdir();(folder/'examples').mkdir();(folder/'index.html').write_text('<html><body><p>Prior landing</p></body></html>')
    (folder/'examples/index.html').write_text('<html><body><article id="prior">Prior gallery</article></body></html>')
    (folder/'prior-report').mkdir();(folder/'prior-report/data.txt').write_text('frozen previous result')
    return folder


def files(folder):return {p.relative_to(folder).as_posix():p.read_bytes() for p in folder.rglob('*') if p.is_file()}


class MPC08PublicationTests(unittest.TestCase):
    def test_saved_checks_and_source_captures_remain_unchanged(self):
        before=(files(S.EXACT_SOURCE),files(S.HORIZON_SOURCE))
        frozen,captures,checks=S.validate()
        self.assertEqual(checks['exact']['native_observations'],360)
        self.assertEqual(checks['exact']['support_observations'],432)
        self.assertEqual([r['cells'] for r in checks['horizon']['exact']],[9,7,1])
        self.assertEqual([len(captures[k]) for k in (S.EXACT_ID,S.HORIZON_ID)],[17,10])
        self.assertEqual(before,(files(S.EXACT_SOURCE),files(S.HORIZON_SOURCE)))

    def test_offline_bundle_works_outside_any_source_checkout(self):
        with tempfile.TemporaryDirectory(prefix='mpc08-publication-test-') as temporary:
            base=Path(temporary);target=site(base/'site');route=S.stage(target)
            self.assertIn('Prior landing',(target/'index.html').read_text())
            self.assertIn('id="prior"',(target/'examples/index.html').read_text())
            self.assertEqual((target/'prior-report/data.txt').read_text(),'frozen previous result')
            self.assertIn(route+'/index.html#minimal-example',(target/'examples/index.html').read_text())
            self.assertFalse((target/route/'source-root/.git').exists())
            with zipfile.ZipFile(target/(route+'.zip')) as archive:
                self.assertIsNone(archive.testzip())
                names=archive.namelist();self.assertEqual(len(names),len(set(names)))
                self.assertTrue(all(not Path(n).is_absolute() and '..' not in Path(n).parts for n in names))
                archive.extractall(base/'outside')
            offline=base/'outside'/route
            for line in (offline/'OFFLINE_SHA256SUMS').read_text().splitlines():
                checksum,name=line.split('  ',1);self.assertEqual(hashlib.sha256((offline/name).read_bytes()).hexdigest(),checksum)
            git=offline/'source-root/.git';self.assertFalse((git/'hooks').exists())
            S.verify_export(offline/'source-root',json.loads((offline/'source-files.json').read_bytes()))
            self.assertLess(sum(p.stat().st_size for p in git.rglob('*') if p.is_file()),1024**2)
            environment={k:v for k,v in os.environ.items() if k not in ('GIT_DIR','GIT_WORK_TREE','GIT_OBJECT_DIRECTORY','GIT_ALTERNATE_OBJECT_DIRECTORIES')}
            environment.update(GIT_CONFIG_GLOBAL=os.devnull,GIT_CONFIG_SYSTEM=os.devnull,GIT_CONFIG_NOSYSTEM='1')
            self.assertNotEqual(subprocess.run(['git','rev-parse','--show-toplevel'],cwd=offline,env=environment,capture_output=True).returncode,0)
            checked=subprocess.run([sys.executable,'-B','offline_check.py'],cwd=offline,env=environment,capture_output=True,text=True,timeout=30)
            self.assertEqual(checked.returncode,0,checked.stderr)
            self.assertEqual(json.loads(checked.stdout)['horizon']['status'],'checked')
            # Rebinding a copied helper hash still cannot forge its Git source.
            source=offline/'source-root/benchmarks/reporting/mpc08_explicit/exact_regions.py';source.write_bytes(source.read_bytes()+b'\nFORGED=True\n')
            receipt=json.loads((offline/'source-files.json').read_bytes());receipt['helper_sha256']['benchmarks/reporting/mpc08_explicit/exact_regions.py']=hashlib.sha256(source.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError,'authentic Git object'):S.verify_export(offline/'source-root',receipt)
            before=files(target)
            with self.assertRaisesRegex(ValueError,'immutable'):S.stage(target)
            self.assertEqual(before,files(target))

    def test_rehashed_frozen_mutation_rejects_before_any_site_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary);copy=base/S.EXACT_ID;shutil.copytree(S.EXACT_SOURCE,copy)
            summary=copy/'summary.json';summary.write_bytes(summary.read_bytes()+b'\n')
            (copy/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in sorted(copy.iterdir()) if p.name!='SHA256SUMS'))
            target=site(base/'site');before=files(target)
            with self.assertRaisesRegex(ValueError,'reviewed immutable'):S.stage(target,copy)
            self.assertEqual(before,files(target))

    def test_zip_path_and_symlink_members_refuse(self):
        for name,mode in (('../outside',0o100644),('symlink',0o120777)):
            data=io.BytesIO()
            with zipfile.ZipFile(data,'w') as archive:
                entry=zipfile.ZipInfo(name);entry.external_attr=mode<<16;archive.writestr(entry,b'x')
            with self.subTest(name=name),self.assertRaises(ValueError):S.checked_zip(data.getvalue(),1)

    def test_callback_failure_and_symlink_destinations_preserve_site(self):
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary);target=site(base/'site');before=files(target)
            def failing_writer(*args):raise ValueError('gallery failure')
            with self.assertRaisesRegex(ValueError,'gallery failure'):S.stage(target,example_card_writer=failing_writer)
            self.assertEqual(before,files(target))
            (target/'examples/index.html').unlink();(target/'examples/index.html').symlink_to(target/'index.html')
            with self.assertRaisesRegex(ValueError,'symlink'):S.stage(target)
            self.assertEqual((target/'index.html').read_bytes(),before['index.html'])
