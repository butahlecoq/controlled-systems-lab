"""Saved studies must authenticate inputs before publishing discoverable figures."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('studies_publication',ROOT/'scripts/reports/stage_mpc11_mesh_timing.py')
S=importlib.util.module_from_spec(spec);spec.loader.exec_module(S)
HAS_STACK=all(importlib.util.find_spec(n) is not None for n in ('numpy','scipy','casadi','do_mpc'))


def site_at(path):
    path.mkdir();(path/'examples').mkdir()
    for name in ('index.html','examples/index.html'):(path/name).write_text('<html><body><p>previous result</p></body></html>')
    return path


class StudyPublicationTests(unittest.TestCase):
    def test_rehashed_changed_summary_is_not_a_new_mathematical_authority(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);evidence=root/'evidence';evidence.mkdir()
            target=evidence/S.MESH;shutil.copytree(S.EVIDENCE/S.MESH,target)
            summary=target/'summary.json';value=json.loads(summary.read_bytes());value['cases'][0]['ni1']['executed_objective_J0']+=1;summary.write_bytes(S.encoded(value))
            inventory={p.name:S.digest(p.read_bytes()) for p in target.iterdir() if p.name!='SHA256SUMS'}
            (target/'SHA256SUMS').write_text(''.join(h+'  '+n+'\n' for n,h in sorted(inventory.items())))
            site=site_at(root/'site');before={p:p.read_bytes() for p in site.rglob('*') if p.is_file()}
            with self.assertRaisesRegex(ValueError,'immutable'):S.stage(site,evidence)
            self.assertEqual(before,{p:p.read_bytes() for p in site.rglob('*') if p.is_file()})

    def test_unsafe_duplicate_or_symlink_zip_is_refused(self):
        import io,stat
        for names,mode in [(['../outside'],0o100644),(['one','one'],0o100644),(['link'],stat.S_IFLNK|0o777)]:
            with self.subTest(names=names,mode=mode):
                stream=io.BytesIO()
                with zipfile.ZipFile(stream,'w') as archive:
                    for name in names:
                        item=zipfile.ZipInfo(name);item.external_attr=mode<<16;archive.writestr(item,b'content')
                with self.assertRaises(ValueError):S.archive_files(stream.getvalue(),len(names))

    def test_gallery_failure_precedes_checks_and_site_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            site=site_at(Path(temporary)/'site');before={p:p.read_bytes() for p in site.rglob('*') if p.is_file()}
            with self.assertRaisesRegex(ValueError,'discovery'):S.stage(site,example_card_writer=lambda *args:None)
            self.assertEqual(before,{p:p.read_bytes() for p in site.rglob('*') if p.is_file()})

    def test_saved_checker_failure_leaves_previous_site_unchanged(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as temporary:
            site=site_at(Path(temporary)/'site');before={p:p.read_bytes() for p in site.rglob('*') if p.is_file()}
            with mock.patch.object(S,'check_and_render',side_effect=ValueError('saved numerical failure')):
                with self.assertRaisesRegex(ValueError,'saved numerical failure'):S.stage(site)
            self.assertEqual(before,{p:p.read_bytes() for p in site.rglob('*') if p.is_file()})

    @unittest.skipUnless(HAS_STACK,'full 560 saved checks require the existing locked MPC11 profile')
    def test_real_stage_preserves_raw_and_exports_complete_studies(self):
        before={p:S.digest(p.read_bytes()) for key in S.SPECS for p in (S.EVIDENCE/key).iterdir()}
        with tempfile.TemporaryDirectory() as temporary:
            site=site_at(Path(temporary)/'site');route=S.stage(site);report=site/route
            manifest=json.loads((report/'publication-manifest.json').read_bytes())
            self.assertEqual((manifest['verification']['mesh_transcriptions'],manifest['verification']['timing_transcriptions']),(140,420))
            for key in S.SPECS:
                self.assertEqual((report/'evidence'/key/'capture.zip').read_bytes(),(S.EVIDENCE/key/'capture.zip').read_bytes())
            data=json.loads((report/'figure-data.json').read_bytes())
            self.assertEqual(data['cases'][1]['phase_pairs'],[['m_ox','q_ox'],['m_f','q_f']])
            self.assertEqual(len(data['timing_aggregates']),4)
            for name in S.FIGURES:
                for ext in ('svg','png'):self.assertGreater((report/(name+'.'+ext)).stat().st_size,1000)
            self.assertIn('previous result',(site/'index.html').read_text());self.assertIn(route,(site/'examples/index.html').read_text())
            self.assertIn('inconclusive',(report/'index.html').read_text())
            with zipfile.ZipFile(site/(route+'.zip')) as archive:
                self.assertIsNone(archive.testzip());self.assertEqual(len(archive.namelist()),len(set(archive.namelist())))
                self.assertEqual(archive.read(route+'/index.html'),(report/'index.html').read_bytes())
            with self.assertRaisesRegex(ValueError,'immutable'):S.stage(site)
            if os.environ.get('CSL_MPC11_STUDY_PREVIEW'):
                shutil.copytree(site,Path(os.environ['CSL_MPC11_STUDY_PREVIEW']))
        self.assertEqual(before,{p:S.digest(p.read_bytes()) for key in S.SPECS for p in (S.EVIDENCE/key).iterdir()})


if __name__=='__main__':unittest.main()
