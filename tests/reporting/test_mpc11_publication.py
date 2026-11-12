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
HAS_MPC11 = all(importlib.util.find_spec(name) is not None for name in ('numpy','scipy','casadi','do_mpc'))
STAGER = importlib.util.module_from_spec(spec)
spec.loader.exec_module(STAGER)


class PublicationTests(unittest.TestCase):
    def test_published_guides_are_read_from_existing_sealed_source_commits(self):
        expected={
            'FIGURES.md':'0f9d16078fbb6b22a660e06be4a41181cb97fc83c2cb0208243cc60098f94009',
            'AFFINE-RECHECK.md':'9cb919d44f0c942c98989b86d812c1782788ade8fe30c791ba1d6eedfbfb76aa',
            'environment/README.md':'cb6ba1ee49fa53e88a2a16bb1173ab1fd64df4e20d5e68f5d6e6ba1f00d7c137',
        }
        for name,digest in expected.items():
            with self.subTest(name=name):
                commit,content=STAGER.captured_source_asset('benchmarks/reporting/mpc11/'+name)
                self.assertEqual(hashlib.sha256(content).hexdigest(),digest)
                self.assertIn(commit,{'ed2dda1ef049ac4fbe259a800d3314e446ceee28',
                                      '73463ec9bc1c2b82e654e61afed1aa07b56f0e53'})

    def test_host_diagnostics_do_not_change_immutable_publication_bytes(self):
        import contextlib,copy,io
        from types import SimpleNamespace
        from unittest import mock
        frozen=json.loads((STAGER.EVIDENCE/STAGER.FIGURES/'receipt.json').read_text())['saved_checks']
        results=[]
        for value in (1e-14,2e-14):
            reports=copy.deepcopy(frozen);reports['nmpc'][0]['max_nlp_objective_rebuild_difference']=value
            log=io.StringIO()
            with tempfile.TemporaryDirectory() as temporary:
                site=Path(temporary);(site/'examples').mkdir();(site/'index.html').write_text('<body></body>');(site/'examples/index.html').write_text('<body></body>')
                with mock.patch.object(STAGER,'current_renderer',return_value=SimpleNamespace(checked_inputs=lambda **kwargs:reports)),contextlib.redirect_stderr(log):
                    route=STAGER.stage(site)
                results.append((route,(site/route/'publication-manifest.json').read_bytes(),(site/(route+'.zip')).read_bytes(),log.getvalue()))
        self.assertEqual(results[0][:3],results[1][:3])
        self.assertNotEqual(results[0][3],results[1][3])

    def test_current_diagnostics_do_not_replace_frozen_identity_or_scope(self):
        import copy
        frozen=json.loads((STAGER.EVIDENCE/STAGER.FIGURES/'receipt.json').read_text())['saved_checks']
        current=copy.deepcopy(frozen);current['nmpc'][0]['max_nlp_objective_rebuild_difference']=1e-14
        STAGER.checked_report_agreement(current,frozen)
        changes=[('status','incomplete'),('transcriptions_checked',999),('completed_objective',999.),
                 ('max_nlp_objective_rebuild_difference',-1.),('max_stationarity_rebuild_difference',float('nan')),
                 ('sampled_execution_physical_state_violation',[])]
        for field,value in changes:
            altered=copy.deepcopy(current);altered['nmpc'][0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):
                STAGER.checked_report_agreement(altered,frozen)

    def test_saved_checker_failure_exposes_underlying_diagnostic(self):
        from unittest import mock
        from types import SimpleNamespace
        import subprocess
        checker=mock.Mock(side_effect=subprocess.CalledProcessError(1,['checker'],stderr='checker diagnostic marker'))
        with mock.patch.object(STAGER,'current_renderer',return_value=SimpleNamespace(checked_inputs=checker)):
            with self.assertRaisesRegex(ValueError,'checker diagnostic marker'):
                STAGER.validate()

    @unittest.skipUnless(HAS_MPC11,'full publication is checked in the hash-locked optional controller CI profile')
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
