"""Typed native report adapters preserve producer identity and evidence scope."""
import json
import hashlib
import copy
import importlib.util
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts' / 'reports'))
import registered_reports as registered
SITE_PATH = Path(__file__).resolve().parents[2] / 'scripts' / 'reports' / 'site.py'
SITE_SPEC = importlib.util.spec_from_file_location('csl_report_site', SITE_PATH)
site = importlib.util.module_from_spec(SITE_SPEC)
SITE_SPEC.loader.exec_module(site)

FIXTURES = Path(__file__).parent / 'fixtures' / 'registered'


class RegisteredKindTests(unittest.TestCase):
    def publication(self, root):
        legacy=json.loads((Path(__file__).resolve().parents[2]/'reports'/'algorithm-results'/'catalog.json').read_text())
        reports=[]
        for report in legacy['reports']:
            rid=report['report_id']
            shutil.copytree(Path(__file__).resolve().parents[2]/'reports'/'algorithm-results'/rid,root/rid)
            shutil.copyfile(Path(__file__).resolve().parents[2]/'reports'/'algorithm-results'/(rid+'.zip'),root/(rid+'.zip'))
            reports.append(report)
        for kind, rid in [('opt05-hull','opt05-hull-20261012-d1c211c2'), ('geo03-hv','geo03-20261012-37c3fb484e0d')]:
            source = FIXTURES / rid
            target = root / rid
            shutil.copytree(source, target)
            item = registered.adapt(target)
            (root / (rid + '.zip')).write_bytes(registered.offline_zip(target,item))
            reports.append({'report_id':rid, 'report_kind':kind, 'payload_sha256':item.payload_sha256,
                'source_commit':item.source_commit, 'measured_scope':item.measured_scope,
                'evidence_limits':item.evidence_limits, 'zip_sha256':hashlib.sha256((root/(rid+'.zip')).read_bytes()).hexdigest()})
        catalogue={'schema':'csl.algorithm-report-catalog/3','artifact_ref':'main','reports':reports}
        (root/'catalog.json').write_text(json.dumps(catalogue,indent=2)+'\n',encoding='utf-8')
        (root/'index.html').write_text(site.catalogue_index(catalogue),encoding='utf-8')
        return catalogue

    def test_opt05_adapter_keeps_measured_scope_and_no_comparator(self):
        result = registered.adapt(FIXTURES / 'opt05-hull-20261012-d1c211c2')
        self.assertEqual(result.kind, 'opt05-hull')
        self.assertEqual(result.report_id, 'opt05-hull-20261012-d1c211c2')
        self.assertIn('trial', result.measured_scope.lower())
        self.assertIn('no comparator', result.evidence_limits.lower())

    def test_opt05_rejects_incomplete_summary_and_wrong_case_points(self):
        record=json.loads((FIXTURES/'opt05-hull-20261012-d1c211c2'/'records.json').read_text())
        duplicate=copy.deepcopy(record);duplicate['summary'][0]=copy.deepcopy(duplicate['summary'][1])
        with self.assertRaisesRegex(ValueError,'summary must contain'):
            registered.adapt_payload(duplicate)
        wrong_points=copy.deepcopy(record);wrong_points['summary'][0]['points']=26
        with self.assertRaisesRegex(ValueError,'point count differs'):
            registered.adapt_payload(wrong_points)

    def test_geo03_rejects_missing_or_duplicate_summary_group(self):
        record=json.loads((FIXTURES/'geo03-20261012-37c3fb484e0d'/'records.json').read_text())
        missing=copy.deepcopy(record);missing['payload']['summary'].pop();missing['payload_sha256']=registered._digest(missing['payload'])
        with self.assertRaisesRegex(ValueError,'summary must contain'):
            registered.adapt_payload(missing)

    def test_geo03_adapter_preserves_native_payload_digest_and_limitations(self):
        result = registered.adapt(FIXTURES / 'geo03-20261012-37c3fb484e0d')
        self.assertEqual(result.kind, 'geo03-hv')
        self.assertEqual(result.report_id, 'geo03-20261012-37c3fb484e0d')
        self.assertEqual(result.payload_sha256, '37c3fb484e0da72e4710cdc8f1e5ebe27b906c2ecd3b3396c43f67d0b8e4196c')
        self.assertIn('56', result.measured_scope)
        self.assertTrue(result.evidence_limits)

    def test_unregistered_schema_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'unregistered'):
            registered.adapt_payload({'schema': 'csl.future/1', 'report_id': 'future'})

    def test_geo_tampered_payload_is_rejected(self):
        record = json.loads((FIXTURES / 'geo03-20261012-37c3fb484e0d' / 'records.json').read_text())
        record['payload']['summary'][0]['failures'] = 1
        record['payload_sha256'] = registered._digest(record['payload'])
        with self.assertRaises(ValueError):
            registered.adapt_payload(record)

    def test_malformed_external_shapes_have_controlled_errors(self):
        with self.assertRaises(ValueError):
            registered.adapt_payload({'schema':'csl.geo03-hv-report/1','report_id':'geo03-20261012-37c3fb484e0d','payload':[]})
        with self.assertRaises(ValueError):
            registered.adapt_payload({'schema':'csl.hull-benchmark-records/1','report_id':'opt05-hull-20261012-d1c211c2','trials':[{}]})

    def test_geo_source_commit_is_required(self):
        record = json.loads((FIXTURES / 'geo03-20261012-37c3fb484e0d' / 'records.json').read_text())
        record['payload']['report_source_commit'] = ''
        record['payload_sha256'] = registered._digest(record['payload'])
        with self.assertRaisesRegex(ValueError, 'source commit'):
            registered.adapt_payload(record)

    def test_real_stage_publishes_registered_links_and_exact_zip_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'input';root.mkdir()
            catalogue=self.publication(root)
            out=site.stage(root/'catalog.json',Path(temp)/'stage',check=True)
            page=(out/'index.html').read_text(encoding='utf-8')
            self.assertIn('21 verified measured trials across 5x5, 9x9, and 13x13 square lattices',page)
            self.assertIn('56 measured trials across four bounded 2D fixtures in both conversion directions',page)
            self.assertIn('No comparator',page)
            opt_page=(out/'opt05-hull-20261012-d1c211c2'/'index.html').read_text(encoding='utf-8')
            geo_page=(out/'geo03-20261012-37c3fb484e0d'/'index.html').read_text(encoding='utf-8')
            self.assertIn('<td>2,135,700</td>',opt_page)
            self.assertIn('<td>1,029,100</td>',geo_page)
            self.assertIn('Checked latency SVG',geo_page)
            for report in catalogue['reports']:
                rid=report['report_id']
                self.assertIn(rid+'/index.html',page)
                self.assertIn('reports/algorithm-results/'+rid, page)
                staged_zip=(out/(rid+'.zip')).read_bytes()
                self.assertEqual(staged_zip,(root/(rid+'.zip')).read_bytes())
                self.assertTrue((out/rid/'index.html').is_file())
            for report in catalogue['reports'][2:]:
                with zipfile.ZipFile(out/(report['report_id']+'.zip')) as archive:
                    self.assertIn(report['report_id']+'/records.json',archive.namelist())
                    self.assertIn('Measured scope',archive.read('index.html').decode())

    def test_real_stage_rejects_tampered_file_and_unregistered_kind(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'input';root.mkdir()
            catalogue=self.publication(root)
            geo=root/'geo03-20261012-37c3fb484e0d'
            (geo/'records.json').write_text('{}',encoding='utf-8')
            (root/'index.html').write_text(site.catalogue_index(catalogue),encoding='utf-8')
            with self.assertRaises(ValueError):
                site.stage(root/'catalog.json',Path(temp)/'bad-stage',check=True)

    def test_real_stage_rejects_unregistered_file_and_duplicate_id(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'input';root.mkdir()
            catalogue=self.publication(root)
            (root/'geo03-20261012-37c3fb484e0d'/'unexpected.dat').write_text('extra')
            with self.assertRaisesRegex(ValueError,'unregistered files'):
                site.stage(root/'catalog.json',Path(temp)/'extra-stage',check=True)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'input';root.mkdir()
            catalogue=self.publication(root)
            catalogue['reports'][3]['report_id']=catalogue['reports'][2]['report_id']
            (root/'catalog.json').write_text(json.dumps(catalogue),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'duplicate'):
                site.stage(root/'catalog.json',Path(temp)/'dupe-stage',check=False)

    def test_real_stage_rejects_hash_consistent_unsafe_svg(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'input';root.mkdir()
            catalogue=self.publication(root)
            rid='geo03-20261012-37c3fb484e0d'
            svg=b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
            (root/rid/'latency.svg').write_bytes(svg)
            manifest=json.loads((root/rid/'manifest.json').read_text())
            manifest['files']['latency.svg']=hashlib.sha256(svg).hexdigest()
            (root/rid/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
            item=registered.adapt(root/rid)
            archive=registered.offline_zip(root/rid,item)
            (root/(rid+'.zip')).write_bytes(archive)
            report=next(x for x in catalogue['reports'] if x['report_id']==rid)
            report['zip_sha256']=hashlib.sha256(archive).hexdigest()
            (root/'catalog.json').write_text(json.dumps(catalogue),encoding='utf-8')
            (root/'index.html').write_text(site.catalogue_index(catalogue),encoding='utf-8')
            with self.assertRaises(ValueError):
                site.stage(root/'catalog.json',Path(temp)/'unsafe-stage',check=True)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'input';root.mkdir()
            catalogue=self.publication(root)
            (root/'index.html').write_text(site.catalogue_index(catalogue),encoding='utf-8')
            catalogue['reports'][2]['report_kind']='not-registered'
            (root/'catalog.json').write_text(json.dumps(catalogue),encoding='utf-8')
            with self.assertRaises(ValueError):
                site.stage(root/'catalog.json',Path(temp)/'bad-stage',check=True)


if __name__ == '__main__':
    unittest.main()
