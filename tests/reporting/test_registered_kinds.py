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
        for report in legacy['reports'][:2]:
            rid=report['report_id']
            shutil.copytree(Path(__file__).resolve().parents[2]/'reports'/'algorithm-results'/rid,root/rid)
            shutil.copyfile(Path(__file__).resolve().parents[2]/'reports'/'algorithm-results'/(rid+'.zip'),root/(rid+'.source.zip'))
            view=site.validate_bundle(root/rid)
            kind=report['report_kind']
            scope='Five analytic LP microfixtures' if kind=='lp' else 'Nine analytic convex microfixtures'
            limits='Single-adapter reference measurements; no comparator or application-scale claim; numerical references are not validated certificates'
            item=registered.PublicationRecord(kind,rid,registered._digest(view),report['source_commit'],scope,limits,tuple(sorted(site.FILES)),view['schema'],view['payload_sha256'])
            source_page=(root/rid/'index.html').read_text(encoding='utf-8')
            links='<p><a href="report-envelope.json">Versioned report envelope</a> · <a href="publication-manifest.json">Publication manifest</a></p>'
            staged_page=source_page.replace('</body>',links+'</body>') if '</body>' in source_page else source_page+links
            artifacts=registered.publication_artifacts(root/rid,item,staged_page.encode('utf-8'))
            archive=registered.publication_zip(rid,artifacts)
            (root/(rid+'.zip')).write_bytes(archive)
            reports.append({**report,'native_payload_sha256':view['payload_sha256'],'payload_sha256':item.payload_sha256,
                'payload_schema':view['schema'],'measured_scope':scope,'evidence_limits':limits,
                'zip_sha256':hashlib.sha256(archive).hexdigest()})
        for kind, rid in [('opt05-hull','opt05-hull-20261012-d1c211c2'), ('geo03-hv','geo03-20261012-37c3fb484e0d')]:
            source = FIXTURES / rid
            target = root / rid
            shutil.copytree(source, target)
            item = registered.adapt(target)
            (root / (rid + '.zip')).write_bytes(registered.offline_zip(target,item))
            reports.append({'report_id':rid, 'report_kind':kind, 'payload_sha256':item.payload_sha256,
                'payload_schema':item.payload_schema,
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

    def test_opt05_report_id_is_bound_to_source_commit(self):
        record=json.loads((FIXTURES/'opt05-hull-20261012-d1c211c2'/'records.json').read_text())
        record['code_commit']='a'*40
        with self.assertRaisesRegex(ValueError,'report ID does not match source commit'):
            registered.adapt_payload(record)

    def test_opt05_embedded_zip_hash_and_contents_are_validated(self):
        source=FIXTURES/'opt05-hull-20261012-d1c211c2'
        with tempfile.TemporaryDirectory() as temp:
            bundle=Path(temp)/source.name
            shutil.copytree(source,bundle)
            archive_path=bundle/'bundle.zip'
            original=archive_path.read_bytes()
            archive_path.write_bytes(original+b'corrupt')
            with self.assertRaisesRegex(ValueError,'bundle ZIP checksum mismatch'):
                registered.adapt(bundle)

            archive_path.write_bytes(original)
            with zipfile.ZipFile(archive_path) as archive:
                entries=[(item,archive.read(item.filename)) for item in archive.infolist()]
            with zipfile.ZipFile(archive_path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
                for item,content in entries:
                    if item.filename.endswith('/README.md'):
                        content+=b'\nchanged after packaging'
                    archive.writestr(item,content)
            digest=hashlib.sha256(archive_path.read_bytes()).hexdigest()
            (bundle/'bundle.zip.sha256').write_text(digest+'  bundle.zip\n',encoding='ascii',newline='\n')
            with self.assertRaisesRegex(ValueError,'bundle ZIP content mismatch'):
                registered.adapt(bundle)

    def test_geo03_rejects_missing_or_duplicate_summary_group(self):
        record=json.loads((FIXTURES/'geo03-20261012-37c3fb484e0d'/'records.json').read_text())
        missing=copy.deepcopy(record);missing['payload']['summary'].pop();missing['payload_sha256']=registered._digest(missing['payload'])
        with self.assertRaisesRegex(ValueError,'summary must contain'):
            registered.adapt_payload(missing)

    def test_geo03_report_id_is_bound_to_payload_digest(self):
        record=json.loads((FIXTURES/'geo03-20261012-37c3fb484e0d'/'records.json').read_text())
        record['payload']['scope_limitations'].append('Changed evidence under a reused ID')
        record['payload_sha256']=registered._digest(record['payload'])
        with self.assertRaisesRegex(ValueError,'report ID does not match payload digest'):
            registered.adapt_payload(record)

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
            repeated=site.stage(root/'catalog.json',Path(temp)/'stage-repeat',check=True)
            self.assertEqual((out/'index.html').read_bytes(),(repeated/'index.html').read_bytes())
            for report in catalogue['reports']:
                rid=report['report_id']
                self.assertEqual((out/(rid+'.zip')).read_bytes(),(repeated/(rid+'.zip')).read_bytes())
            page=(out/'index.html').read_text(encoding='utf-8')
            for report in catalogue['reports']:
                self.assertIn(report['measured_scope']+'; limits: '+report['evidence_limits'],page)
            self.assertIn('21 verified measured trials across 5x5, 9x9, and 13x13 square lattices',page)
            self.assertIn('56 measured trials across four bounded 2D fixtures in both conversion directions',page)
            self.assertIn('No comparator',page)
            opt_page=(out/'opt05-hull-20261012-d1c211c2'/'index.html').read_text(encoding='utf-8')
            geo_page=(out/'geo03-20261012-37c3fb484e0d'/'index.html').read_text(encoding='utf-8')
            self.assertIn('<td>2,135,700</td>',opt_page)
            self.assertIn('<td>1,029,100</td>',geo_page)
            self.assertIn('Checked latency SVG',geo_page)
            # Every kind in the current mixed catalogue uses the same outer publication contract.
            self.assertEqual({row['report_kind']:row['payload_schema'] for row in catalogue['reports']}, {
                'lp':'csl.algorithm-report-view/1',
                'convex':'csl.algorithm-report-view/2',
                'opt05-hull':'csl.hull-benchmark-records/1',
                'geo03-hv':'csl.geo03-hv-report/1'})
            for report in catalogue['reports']:
                rid=report['report_id']
                report_dir=out/rid
                envelope_bytes=(report_dir/'report-envelope.json').read_bytes()
                manifest_bytes=(report_dir/'publication-manifest.json').read_bytes()
                envelope=json.loads(envelope_bytes)
                manifest=json.loads(manifest_bytes)
                self.assertEqual(envelope['schema'],'csl.algorithm-report-envelope/1')
                self.assertEqual((envelope['report_id'],envelope['report_kind'],envelope['payload_schema']),
                    (rid,report['report_kind'],report['payload_schema']))
                self.assertEqual((envelope['source_commit'],envelope['measured_scope'],envelope['evidence_limits']),
                    (report['source_commit'],report['measured_scope'],report['evidence_limits']))
                if report['report_kind'] in ('lp','convex'):
                    self.assertEqual(envelope['native_payload_sha256'],report['native_payload_sha256'])
                    self.assertEqual(envelope['payload']['payload_sha256'],report['native_payload_sha256'])
                else:
                    self.assertNotIn('native_payload_sha256',envelope)
                    self.assertEqual(registered._digest(envelope['payload']),envelope['payload_sha256'])
                self.assertEqual(manifest['schema'],'csl.algorithm-report-publication-manifest/1')
                self.assertEqual((manifest['report_id'],manifest['report_kind']),
                    (rid,report['report_kind']))
                expected_files={path.relative_to(report_dir).as_posix() for path in report_dir.rglob('*')
                    if path.is_file() and path.name!='publication-manifest.json'}
                self.assertEqual(set(manifest['files']),expected_files)
                for name,digest in manifest['files'].items():
                    self.assertEqual(hashlib.sha256((report_dir/name).read_bytes()).hexdigest(),digest)
                self.assertTrue(site.validate_publication_manifest(report_dir,report))
                with zipfile.ZipFile(out/(rid+'.zip')) as archive:
                    self.assertEqual(archive.read(rid+'/report-envelope.json'),envelope_bytes)
                    self.assertEqual(archive.read(rid+'/publication-manifest.json'),manifest_bytes)
            for report in catalogue['reports'][2:]:
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
                    rid=report['report_id']
                    envelope=json.loads((out/rid/'report-envelope.json').read_text(encoding='utf-8'))
                    manifest=json.loads((out/rid/'publication-manifest.json').read_text(encoding='utf-8'))
                    self.assertEqual(envelope['schema'],'csl.algorithm-report-envelope/1')
                    self.assertEqual(envelope['payload_schema'],
                        'csl.hull-benchmark-records/1' if report['report_kind']=='opt05-hull' else 'csl.geo03-hv-report/1')
                    self.assertEqual((envelope['report_id'],envelope['report_kind'],envelope['payload_sha256']),
                        (rid,report['report_kind'],report['payload_sha256']))
                    self.assertEqual(registered._digest(envelope['payload']),envelope['payload_sha256'])
                    self.assertEqual(manifest['schema'],'csl.algorithm-report-publication-manifest/1')
                    self.assertEqual((manifest['report_id'],manifest['report_kind']),
                        (rid,report['report_kind']))
                    self.assertEqual(manifest['files']['report-envelope.json'],
                        hashlib.sha256((out/rid/'report-envelope.json').read_bytes()).hexdigest())
                    self.assertEqual(archive.read(rid+'/report-envelope.json'),
                        (out/rid/'report-envelope.json').read_bytes())
                    self.assertEqual(archive.read(rid+'/publication-manifest.json'),
                        (out/rid/'publication-manifest.json').read_bytes())
                    self.assertTrue(site.validate_publication_manifest(out/rid,report))

    def test_production_catalogue_uses_shared_outer_contract_for_all_kinds(self):
        repo=Path(__file__).resolve().parents[2]
        root=repo/'reports'/'algorithm-results'
        catalogue=json.loads((root/'catalog.json').read_text(encoding='utf-8'))
        self.assertEqual(catalogue['schema'],'csl.algorithm-report-catalog/3')
        self.assertEqual({item['report_kind'] for item in catalogue['reports']},{'lp','convex','opt05-hull','geo03-hv'})
        shared={'report_id','report_kind','payload_sha256','source_commit','zip_sha256'}
        for report in catalogue['reports']:
            self.assertTrue(shared <= set(report))
            self.assertRegex(report['payload_sha256'],r'^[0-9a-f]{64}$')
            self.assertRegex(report['source_commit'],r'^[0-9a-f]{40}$')
            self.assertRegex(report['zip_sha256'],r'^[0-9a-f]{64}$')
            if report['report_kind'] in ('opt05-hull','geo03-hv'):
                self.assertTrue({'measured_scope','evidence_limits'} <= set(report))
                # Per-kind saved schemas/manifests are validated at the boundary,
                # then projected into the same catalogue identity contract.
                adapted=registered.adapt(root/report['report_id'])
                self.assertEqual((report['report_id'],report['report_kind'],report['payload_sha256'],report['source_commit']),
                                 (adapted.report_id,adapted.kind,adapted.payload_sha256,adapted.source_commit))
                self.assertEqual((report['measured_scope'],report['evidence_limits']),
                                 (adapted.measured_scope,adapted.evidence_limits))
        with tempfile.TemporaryDirectory() as temp:
            first=site.stage(root/'catalog.json',Path(temp)/'stage-a',check=True)
            second=site.stage(root/'catalog.json',Path(temp)/'stage-b',check=True)
            index=(first/'index.html').read_text(encoding='utf-8')
            for report in catalogue['reports']:
                rid=report['report_id']
                self.assertIn(rid+'/index.html',index)
                self.assertIn(rid+'/records.json',index)
                self.assertIn(rid+'.zip',index)
                archive_bytes=(first/(rid+'.zip')).read_bytes()
                self.assertEqual(archive_bytes,(second/(rid+'.zip')).read_bytes())
                self.assertEqual(hashlib.sha256(archive_bytes).hexdigest(),report['zip_sha256'])
                if report['report_kind'] in ('opt05-hull','geo03-hv'):
                    with zipfile.ZipFile(first/(rid+'.zip')) as archive:
                        self.assertEqual(archive.read(rid+'/report-envelope.json'),(first/rid/'report-envelope.json').read_bytes())
                        self.assertEqual(archive.read(rid+'/publication-manifest.json'),(first/rid/'publication-manifest.json').read_bytes())
            for rid in ('opt05-hull-20261012-d1c211c2','geo03-20261012-37c3fb484e0d'):
                page=(first/rid/'index.html').read_text(encoding='utf-8')
                self.assertIn('records.json',page)
                self.assertIn('trials.csv',page)
                self.assertIn('summary.csv',page)
                self.assertIn('latency.svg',page)
                self.assertTrue((first/rid/'latency.svg').is_file())
                envelope=json.loads((first/rid/'report-envelope.json').read_text(encoding='utf-8'))
                manifest=json.loads((first/rid/'publication-manifest.json').read_text(encoding='utf-8'))
                report=next(item for item in catalogue['reports'] if item['report_id']==rid)
                self.assertEqual(envelope['schema'],'csl.algorithm-report-envelope/1')
                self.assertEqual((envelope['report_id'],envelope['report_kind'],envelope['payload_sha256'],envelope['source_commit']),
                                 (report['report_id'],report['report_kind'],report['payload_sha256'],report['source_commit']))
                self.assertEqual(manifest['schema'],'csl.algorithm-report-publication-manifest/1')
                self.assertEqual((manifest['report_id'],manifest['report_kind']),(rid,report['report_kind']))
                self.assertIn('report-envelope.json',manifest['files'])
                self.assertIn('index.html',manifest['files'])
                self.assertTrue(site.validate_publication_manifest(first/rid,report))
                tampered=json.loads((first/rid/'publication-manifest.json').read_text(encoding='utf-8'))
                tampered['files']['records.json']='0'*64
                (first/rid/'publication-manifest.json').write_text(json.dumps(tampered),encoding='utf-8')
                with self.assertRaisesRegex(ValueError,'publication manifest'):
                    site.validate_publication_manifest(first/rid,report)

    def test_real_stage_rejects_tampered_file_and_unregistered_kind(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'input';root.mkdir()
            catalogue=self.publication(root)
            geo=root/'geo03-20261012-37c3fb484e0d'
            (geo/'records.json').write_text('{}',encoding='utf-8')
            (root/'index.html').write_text(site.catalogue_index(catalogue),encoding='utf-8')
            with self.assertRaises(ValueError):
                site.stage(root/'catalog.json',Path(temp)/'bad-stage',check=True)
            self.assertFalse((Path(temp)/'bad-stage').exists())

    def test_publication_manifest_rejects_symlinked_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'input';root.mkdir()
            catalogue=self.publication(root)
            out=site.stage(root/'catalog.json',Path(temp)/'stage',check=True)
            rid=catalogue['reports'][2]['report_id']
            report_dir=out/rid
            victim=report_dir/'README.md'
            target=report_dir/'records.json'
            victim.unlink()
            try:
                victim.symlink_to(target)
            except (OSError, NotImplementedError) as error:
                self.skipTest(f"symlinks unavailable: {error}")
            with self.assertRaisesRegex(ValueError,'symlink'):
                site.validate_publication_manifest(report_dir,catalogue['reports'][2])

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

    def test_publication_envelope_and_manifest_reject_tampering(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'input';root.mkdir()
            catalogue=self.publication(root)
            out=site.stage(root/'catalog.json',Path(temp)/'stage',check=True)
            report=catalogue['reports'][2]
            report_dir=out/report['report_id']
            envelope_path=report_dir/'report-envelope.json'
            envelope=json.loads(envelope_path.read_text(encoding='utf-8'))
            envelope['payload']['trials'][0]['elapsed_ns'] += 1
            envelope_path.write_text(json.dumps(envelope),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'manifest file hash mismatch'):
                site.validate_publication_manifest(report_dir,report)
            # Recompute the outer file hash to prove the payload digest is also enforced.
            manifest_path=report_dir/'publication-manifest.json'
            manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
            manifest['files']['report-envelope.json']=hashlib.sha256(envelope_path.read_bytes()).hexdigest()
            manifest_path.write_text(json.dumps(manifest),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'payload hash mismatch'):
                site.validate_publication_manifest(report_dir,report)

    def test_hash_consistent_scope_text_is_escaped_in_generated_catalogue_html(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'input';root.mkdir()
            catalogue=self.publication(root)
            original_rid='geo03-20261012-37c3fb484e0d'
            records_path=root/original_rid/'records.json'
            record=json.loads(records_path.read_text(encoding='utf-8'))
            record['payload']['scope_limitations'].append('<script>alert(1)</script>')
            record['payload_sha256']=registered._digest(record['payload'])
            rid='geo03-20261012-'+record['payload_sha256'][:12]
            record['report_id']=rid
            records_path.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
            source_manifest=json.loads((root/original_rid/'manifest.json').read_text(encoding='utf-8'))
            source_manifest['files']['records.json']=hashlib.sha256(records_path.read_bytes()).hexdigest()
            source_manifest['report_id']=rid
            (root/original_rid/'manifest.json').write_text(json.dumps(source_manifest,indent=2)+'\n',encoding='utf-8')
            (root/original_rid).rename(root/rid)
            (root/(original_rid+'.zip')).rename(root/(rid+'.zip'))
            item=registered.adapt(root/rid)
            archive=registered.offline_zip(root/rid,item)
            (root/(rid+'.zip')).write_bytes(archive)
            report=next(row for row in catalogue['reports'] if row['report_id']==original_rid)
            report['report_id']=rid
            report['payload_sha256']=item.payload_sha256
            report['evidence_limits']=item.evidence_limits
            report['zip_sha256']=hashlib.sha256(archive).hexdigest()
            (root/'catalog.json').write_text(json.dumps(catalogue,indent=2)+'\n',encoding='utf-8')
            (root/'index.html').write_text(site.catalogue_index(catalogue),encoding='utf-8')
            out=site.stage(root/'catalog.json',Path(temp)/'stage',check=True)
            html=(out/'index.html').read_text(encoding='utf-8')
            self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;',html)
            self.assertNotIn('<script>alert(1)</script>',html)
            probe=copy.deepcopy(catalogue)
            probe['reports'][3]['source_commit']='"><svg onload="alert(1)">'
            probe_html=site.catalogue_index(probe)
            self.assertIn('&quot;&gt;&lt;svg onload=&quot;alert(1)&quot;&gt;',probe_html)
            self.assertNotIn('<svg onload=',probe_html)

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
            self.assertFalse((Path(temp)/'bad-stage').exists())


if __name__ == '__main__':
    unittest.main()
