"""Publication boundary tests: saved evidence only; no optimization/native worker."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.reports import stage_mpc10_comparison as S


def site(folder):
    folder.mkdir();(folder/'examples').mkdir();(folder/'index.html').write_text('<html><body>Prior landing</body></html>');(folder/'examples/index.html').write_text('<html><body>Prior examples</body></html>');(folder/'prior.txt').write_text('immutable prior evidence');return folder


def files(folder):return {p.relative_to(folder).as_posix():p.read_bytes() for p in folder.rglob('*') if p.is_file()}


class MPC10PublicationTests(unittest.TestCase):
    def test_source_identity_survives_unrelated_commits_and_retains_merged_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            repository=Path(temporary)
            def git(*args):return subprocess.check_output(['git',*args],cwd=repository,stderr=subprocess.PIPE,text=True).strip()
            git('init','-b','main');git('config','user.name','Publication test');git('config','user.email','test@example.invalid')
            def commit(name,content):
                (repository/name).write_text(content);git('add',name);git('commit','-m',name);return git('rev-parse','HEAD')
            commit('first.py','first\n');revision=commit('second.py','second\n')
            capture={'environment.json':S.encoded(dict(source_revision=revision,source_sha256={}))}
            with patch.object(S,'ROOT',repository),patch.object(S,'HELPERS',['first.py','second.py']):
                original=S.source_export(capture);commit('unrelated.txt','unrelated\n');self.assertEqual(S.source_export(capture),original)
                git('branch','other');commit('first.py','changed first\n');git('checkout','other');commit('second.py','changed second\n');git('checkout','main');git('merge','--no-ff','other','-m','combine helpers')
                merged=S.source_export(capture);self.assertEqual(merged[1]['helper_revision'],git('rev-parse','HEAD'));self.assertNotEqual(merged,original)
                commit('more-unrelated.txt','unrelated after merge\n');self.assertEqual(S.source_export(capture),merged)
                (repository/'first.py').write_text('uncommitted\n')
                with self.assertRaisesRegex(ValueError,'differs from committed source'):S.source_export(capture)

    def test_offline_source_receipt_checks_work_outside_checkout(self):
        before=files(S.FROZEN)
        with tempfile.TemporaryDirectory(prefix='mpc10-publication-test-') as temporary:
            base=Path(temporary);target=site(base/'site');route=S.stage(target)
            self.assertEqual((target/'prior.txt').read_text(),'immutable prior evidence');self.assertIn('Prior landing',(target/'index.html').read_text());self.assertIn('Prior examples',(target/'examples/index.html').read_text())
            self.assertFalse((target/route/'source-root/.git').exists())
            with zipfile.ZipFile(target/(route+'.zip')) as archive:
                self.assertIsNone(archive.testzip());self.assertEqual(len(archive.namelist()),len(set(archive.namelist())));archive.extractall(base/'outside')
            offline=base/'outside'/route
            self.assertEqual(S.sums((offline/'OFFLINE_SHA256SUMS').read_bytes()),{n:S.digest(v) for n,v in files(offline).items() if n!='OFFLINE_SHA256SUMS' and n!='SHA256SUMS'})
            environment={k:v for k,v in os.environ.items() if k not in ('GIT_DIR','GIT_WORK_TREE','GIT_OBJECT_DIRECTORY','GIT_ALTERNATE_OBJECT_DIRECTORIES')};environment.update(GIT_CONFIG_GLOBAL=os.devnull,GIT_CONFIG_SYSTEM=os.devnull,GIT_CONFIG_NOSYSTEM='1')
            checked=subprocess.run([sys.executable,'-B','offline_check.py'],cwd=offline,env=environment,capture_output=True,text=True,timeout=60)
            self.assertEqual(checked.returncode,0,checked.stderr);self.assertEqual(json.loads(checked.stdout)['cases'],26)
            receipt=json.loads((offline/'source-files.json').read_bytes());helper='benchmarks/reporting/mpc10/oracle.py';path=offline/'source-root'/helper;path.write_bytes(path.read_bytes()+b'\nFORGED=True\n');receipt['helper_sha256'][helper]=S.digest(path.read_bytes())
            with self.assertRaisesRegex(ValueError,'authentic Git object'):S.verify_source(offline/'source-root',receipt)
            unchanged=files(target)
            with self.assertRaisesRegex(ValueError,'immutable'):S.stage(target)
            self.assertEqual(files(target),unchanged)
        self.assertEqual(files(S.FROZEN),before)

    def test_frozen_rehash_mutation_refuses_and_preserves_site(self):
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary);copy=base/'original';shutil.copytree(S.FROZEN,copy);(copy/'metrics.json').write_text('{}\n');(copy/'SHA256SUMS').write_text(''.join(S.digest(p.read_bytes())+'  '+p.name+'\n' for p in sorted(copy.iterdir()) if p.name!='SHA256SUMS'))
            target=site(base/'site');before=files(target)
            with patch.object(S,'FROZEN',copy):
                with self.assertRaisesRegex(ValueError,'reviewed evidence'):S.reviewed(copy,S.FROZEN_SHA)
            self.assertEqual(files(target),before)

    def test_reader_mutation_rejects_after_inventory_renewal(self):
        with tempfile.TemporaryDirectory() as temporary:
            copy=Path(temporary)/'reading';shutil.copytree(S.READING,copy);receipt=json.loads((copy/'verification.json').read_bytes());receipt['checking_sources']={};(copy/'verification.json').write_bytes(S.encoded(receipt));(copy/'SHA256SUMS').write_text(''.join(S.digest(p.read_bytes())+'  '+p.name+'\n' for p in sorted(copy.iterdir()) if p.name!='SHA256SUMS'))
            # Exercise the structural receipt boundary after renewing the outer pin too.
            with patch.object(S,'READING_SHA',S.digest((copy/'SHA256SUMS').read_bytes())):
                with self.assertRaisesRegex(ValueError,'saved bindings/metrics check failed'):S.validate(reading=copy)

    def test_callback_failure_and_symlink_preserve_site(self):
        with tempfile.TemporaryDirectory() as temporary:
            target=site(Path(temporary)/'site');before=files(target)
            def fail(*args):raise ValueError('gallery failure')
            with self.assertRaisesRegex(ValueError,'gallery failure'):S.stage(target,example_card_writer=fail)
            self.assertEqual(before,files(target));(target/'examples/index.html').unlink();(target/'examples/index.html').symlink_to(target/'index.html')
            with self.assertRaisesRegex(ValueError,'symlink'):S.stage(target)
            self.assertEqual((target/'index.html').read_bytes(),before['index.html'])

    def test_unsafe_archive_members_refuse(self):
        import io
        for name,mode in [('../outside',0o100644),('symlink',0o120777)]:
            data=io.BytesIO()
            with zipfile.ZipFile(data,'w') as archive:
                item=zipfile.ZipInfo(name);item.external_attr=mode<<16;archive.writestr(item,b'x')
            with self.subTest(name=name),self.assertRaises(ValueError):S.capture_files(data.getvalue())
