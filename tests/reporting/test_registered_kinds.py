"""Typed native report adapters preserve producer identity and evidence scope."""
import json
import csv
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
    def rehash_native(self, bundle, kind):
        if kind=='geo03-hv':
            manifest_path=bundle/'manifest.json'
            manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
            for name in manifest['files']:
                manifest['files'][name]=hashlib.sha256((bundle/name).read_bytes()).hexdigest()
            manifest_path.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
            return
        excluded={'manifest.sha256','bundle.zip','bundle.zip.sha256'}
        names=sorted(path.relative_to(bundle).as_posix() for path in bundle.rglob('*') if path.is_file() and path.name not in excluded)
        manifest=''.join(hashlib.sha256((bundle/name).read_bytes()).hexdigest()+'  '+name+'\n' for name in names)
        (bundle/'manifest.sha256').write_text(manifest,encoding='utf-8',newline='\n')
        with zipfile.ZipFile(bundle/'bundle.zip','w',compression=zipfile.ZIP_STORED) as archive:
            for name in names+['manifest.sha256']:
                archive.write(bundle/name,bundle.name+'/'+name)
        digest=hashlib.sha256((bundle/'bundle.zip').read_bytes()).hexdigest()
        (bundle/'bundle.zip.sha256').write_text(digest+'  bundle.zip\n',encoding='ascii',newline='\n')

    def rewrite_csv_cell(self, path, field):
        with path.open(newline='',encoding='utf-8') as stream:
            reader=csv.DictReader(stream)
            fields=reader.fieldnames
            rows=list(reader)
        rows[0][field]='999999999' if rows[0][field]!='999999999' else '999999998'
        with path.open('w',newline='',encoding='utf-8') as stream:
            writer=csv.DictWriter(stream,fieldnames=fields)
            writer.writeheader();writer.writerows(rows)

    def publication(self, root):
        legacy=json.loads((Path(__file__).resolve().parents[2]/'reports'/'algorithm-results'/'catalog.json').read_text())
        reports=[]
        for report in legacy['reports']:
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
            (root / (item.report_id + '.zip')).write_bytes(registered.offline_zip(target,item))
            reports.append({'report_id':item.report_id, 'report_kind':kind, 'payload_sha256':item.payload_sha256,
                'payload_schema':item.payload_schema,
                'source_commit':item.source_commit, 'measured_scope':item.measured_scope,
                'evidence_limits':item.evidence_limits, 'zip_sha256':hashlib.sha256((root/(item.report_id+'.zip')).read_bytes()).hexdigest(),
                **({'source_report_id':item.source_report_id} if item.source_report_id else {})})
        catalogue={'schema':'csl.algorithm-report-catalog/3','artifact_ref':'main','reports':reports}
        (root/'catalog.json').write_text(json.dumps(catalogue,indent=2)+'\n',encoding='utf-8')
        (root/'index.html').write_text(site.catalogue_index(catalogue),encoding='utf-8')
        return catalogue

    def test_opt05_adapter_keeps_measured_scope_and_no_comparator(self):
        result = registered.adapt(FIXTURES / 'opt05-hull-20261012-d1c211c2')
        self.assertEqual(result.kind, 'opt05-hull')
        self.assertTrue(result.report_id.startswith('opt05-hull-20261012-'))
        self.assertEqual(len(result.report_id.rsplit('-',1)[1]),64)
        self.assertEqual(result.source_report_id, 'opt05-hull-20261012-d1c211c2')
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

    def test_registered_public_ids_bind_complete_native_evidence_and_publisher(self):
        for kind,source_id in [('opt05-hull','opt05-hull-20261012-d1c211c2'),('geo03-hv','geo03-20261012-37c3fb484e0d')]:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temp:
                source=FIXTURES/source_id
                bundle=Path(temp)/source_id
                shutil.copytree(source,bundle)
                original=registered.adapt(bundle)
                (bundle/'README.md').write_bytes((bundle/'README.md').read_bytes()+b'\nMore reproduction detail.\n')
                self.rehash_native(bundle,kind)
                changed=registered.adapt(bundle)
                self.assertEqual(changed.source_report_id,original.source_report_id)
                self.assertEqual(changed.source_commit,original.source_commit)
                self.assertEqual(changed.payload_sha256,original.payload_sha256)
                self.assertNotEqual(changed.report_id,original.report_id)

    def test_opt05_same_source_with_different_saved_measurement_gets_new_public_id(self):
        source_id='opt05-hull-20261012-d1c211c2'
        with tempfile.TemporaryDirectory() as temp:
            bundle=Path(temp)/source_id
            shutil.copytree(FIXTURES/source_id,bundle)
            original=registered.adapt(bundle)
            record=json.loads((bundle/'records.json').read_text(encoding='utf-8'))
            group=[trial for trial in record['trials'] if trial['case_id']=='grid-25' and not trial['warmup']]
            latest=max(group,key=lambda trial:trial['elapsed_ns'])
            old_max=latest['elapsed_ns'];latest['elapsed_ns']=old_max+1
            next(row for row in record['summary'] if row['case_id']=='grid-25')['max_ns']=old_max+1
            for name in ('records.json','evidence/accepted-002/records.json'):
                (bundle/name).write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
            for name,field in (('trials.csv','elapsed_ns'),('evidence/accepted-002/trials.csv','elapsed_ns'),('summary.csv','max_ns'),('evidence/accepted-002/summary.csv','max_ns')):
                path=bundle/name
                path.write_text(path.read_text(encoding='utf-8').replace(str(old_max),str(old_max+1),1),encoding='utf-8')
            self.rehash_native(bundle,'opt05-hull')
            changed=registered.adapt(bundle)
            self.assertEqual(changed.source_report_id,original.source_report_id)
            self.assertEqual(changed.source_commit,original.source_commit)
            self.assertNotEqual(changed.payload_sha256,original.payload_sha256)
            self.assertNotEqual(changed.report_id,original.report_id)

    def test_registered_csv_must_match_json_even_with_consistent_native_hashes(self):
        for kind,source_id in [('opt05-hull','opt05-hull-20261012-d1c211c2'),('geo03-hv','geo03-20261012-37c3fb484e0d')]:
            for name,field in [('trials.csv','elapsed_ns' if kind=='opt05-hull' else 'run_ns'),('summary.csv','max_ns' if kind=='opt05-hull' else 'run_ns_max_ns')]:
                with self.subTest(kind=kind,file=name), tempfile.TemporaryDirectory() as temp:
                    bundle=Path(temp)/source_id
                    shutil.copytree(FIXTURES/source_id,bundle)
                    self.rewrite_csv_cell(bundle/name,field)
                    self.rehash_native(bundle,kind)
                    with self.assertRaisesRegex(ValueError,name.replace('.','\\.')+' differs from validated records'):
                        registered.adapt(bundle)

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
        self.assertTrue(result.report_id.startswith('geo03-20261012-'))
        self.assertEqual(len(result.report_id.rsplit('-',1)[1]),64)
        self.assertEqual(result.source_report_id, 'geo03-20261012-37c3fb484e0d')
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
            opt_page=(out/registered.adapt(FIXTURES/'opt05-hull-20261012-d1c211c2').report_id/'index.html').read_text(encoding='utf-8')
            geo_page=(out/registered.adapt(FIXTURES/'geo03-20261012-37c3fb484e0d').report_id/'index.html').read_text(encoding='utf-8')
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
                    if report['report_kind'] in ('opt05-hull','geo03-hv'):
                        self.assertEqual(envelope['source_report_id'],report['source_report_id'])
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
                self.assertIn('reports/algorithm-results/'+(report.get('source_report_id') or rid), page)
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
            original_public_id=next(row['report_id'] for row in catalogue['reports'] if row.get('source_report_id')==original_rid)
            (root/(original_public_id+'.zip')).unlink()
            item=registered.adapt(root/rid)
            archive=registered.offline_zip(root/rid,item)
            (root/(item.report_id+'.zip')).write_bytes(archive)
            report=next(row for row in catalogue['reports'] if row.get('source_report_id')==original_rid)
            report['report_id']=item.report_id
            report['source_report_id']=rid
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
            old_public_id=next(x['report_id'] for x in catalogue['reports'] if x.get('source_report_id')==rid)
            (root/(old_public_id+'.zip')).unlink()
            (root/(item.report_id+'.zip')).write_bytes(archive)
            report=next(x for x in catalogue['reports'] if x.get('source_report_id')==rid)
            report['report_id']=item.report_id
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
