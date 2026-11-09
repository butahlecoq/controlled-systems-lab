"""Publication must never turn changed saved evidence into a trusted figure."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('mpc11_publication', ROOT/'scripts/reports/stage_mpc11_controller_comparison.py')
STAGER = importlib.util.module_from_spec(spec)
spec.loader.exec_module(STAGER)


class PublicationTests(unittest.TestCase):
    def test_real_stage_preserves_sources_and_discovers_both_cases(self):
        before = {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in STAGER.EVIDENCE.rglob('*') if p.is_file()}
        with tempfile.TemporaryDirectory() as temporary:
            site=Path(temporary);(site/'examples').mkdir()
            for p in [site/'index.html',site/'examples/index.html']:p.write_text('<html><body></body></html>')
            route=STAGER.stage(site)
            self.assertIn(route,(site/'examples/index.html').read_text())
            text=(site/route/'index.html').read_text()
            for word in ['m_ox','q_ox','m_f','q_f','Lotka','Shrinking','inconclusive','equations']:
                self.assertIn(word,text)
            manifest=json.loads((site/route/'publication-manifest.json').read_text())
            self.assertEqual(len(manifest['input_archives']),3)
            self.assertEqual(manifest['verification']['nmpc_steps'],70)
            for kind,data in manifest['input_archives'].items():
                self.assertEqual(hashlib.sha256((site/route/'raw'/f'{kind}.zip').read_bytes()).hexdigest(),data['sha256'])
            with self.assertRaisesRegex(ValueError,'immutable'):STAGER.stage(site)
        self.assertEqual(before,{p:hashlib.sha256(p.read_bytes()).hexdigest() for p in STAGER.EVIDENCE.rglob('*') if p.is_file()})

    def test_mutated_figure_receipt_or_raw_refused_before_writes(self):
        for relative in ['figures-60bda0fb/syn-nl-lv-01-plotted-data.json',
                         'figures-60bda0fb/receipt.json','nmpc-pilot-55f65110/capture.zip',
                         'affine-pilot-b3978a98/summary.json']:
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary); evidence=root/'evidence';shutil.copytree(STAGER.EVIDENCE,evidence)
                path=evidence/relative;path.write_bytes(path.read_bytes()+b' ')
                site=root/'site';site.mkdir();(site/'examples').mkdir()
                for p in [site/'index.html',site/'examples/index.html']:p.write_text('<html><body></body></html>')
                with self.assertRaises(ValueError):STAGER.stage(site,evidence=evidence)
                self.assertEqual(sorted(p.relative_to(site).as_posix() for p in site.rglob('*') if p.is_file()),['examples/index.html','index.html'])

    def test_rehashed_changed_evidence_cannot_replace_reviewed_anchor(self):
        with tempfile.TemporaryDirectory() as temporary:
            evidence=Path(temporary)/'evidence';shutil.copytree(STAGER.EVIDENCE,evidence)
            figures=evidence/'figures-60bda0fb'; changed=figures/'receipt.json';changed.write_bytes(changed.read_bytes()+b' ')
            manifest=figures/'SHA256SUMS'
            rows=[]
            for line in manifest.read_text().splitlines():
                checksum,name=line.split('  ',1)
                rows.append(hashlib.sha256((figures/name).read_bytes()).hexdigest()+'  '+name)
            manifest.write_text('\n'.join(rows)+'\n')
            with self.assertRaisesRegex(ValueError,'reviewed figure manifest'):STAGER.validate(evidence)

    def test_duplicate_and_symbolic_zip_members_refused(self):
        import warnings
        for mode in ('duplicate','symbolic'):
            stream=io.BytesIO()
            with warnings.catch_warnings(), zipfile.ZipFile(stream,'w') as archive:
                warnings.simplefilter('ignore',UserWarning)
                if mode=='duplicate':
                    archive.writestr('same',b'x');archive.writestr('same',b'y')
                else:
                    entry=zipfile.ZipInfo('link');entry.external_attr=0o120777<<16;archive.writestr(entry,b'target')
            with self.assertRaises(ValueError):STAGER.safe_zip(stream.getvalue())

    def test_unsafe_zip_and_symlink_paths_refused(self):
        for name in ['../outside','/absolute','bad\\name','safe/../outside']:
            stream=io.BytesIO()
            with zipfile.ZipFile(stream,'w') as archive:archive.writestr(name,b'x')
            with self.subTest(name=name), self.assertRaises(ValueError):STAGER.safe_zip(stream.getvalue())
        with tempfile.TemporaryDirectory() as temporary:
            site=Path(temporary);(site/'examples').mkdir();outside=site/'outside';outside.write_text('<body></body>')
            (site/'index.html').symlink_to(outside);(site/'examples/index.html').write_text('<body></body>')
            with self.assertRaises(ValueError):STAGER.stage(site)


if __name__=='__main__':unittest.main()
