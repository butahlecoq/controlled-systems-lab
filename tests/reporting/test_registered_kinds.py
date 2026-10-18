"""Typed native report adapters preserve producer identity and evidence scope."""
import json
import csv
import hashlib
import copy
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts' / 'reports'))
import registered_reports as registered
import geo04_registered_reports as geo04_publication
import geo02_registered_reports as geo02_publication
import geo05_registered_reports as geo05_publication
import geo06_registered_reports as geo06_publication
import b08_exact_registered_reports as b08_publication
import issue3_registered_reports as issue3_publication
import syn01_registered_reports as syn01_publication
import syn02_registered_reports as syn02_publication
import syn_ts01_paired_registered_reports as syn_ts01_paired_publication
import opt11_registered_reports as opt11_publication
SITE_PATH = Path(__file__).resolve().parents[2] / 'scripts' / 'reports' / 'site.py'
SITE_SPEC = importlib.util.spec_from_file_location('csl_report_site', SITE_PATH)
site = importlib.util.module_from_spec(SITE_SPEC)
SITE_SPEC.loader.exec_module(site)

FIXTURES = Path(__file__).resolve().parents[2] / 'reports' / 'algorithm-results'


class RegisteredKindTests(unittest.TestCase):
    def test_opt04_catalogue_row_links_the_published_performance_figure(self):
        catalogue = {'schema': 'csl.algorithm-report-catalog/3', 'artifact_ref': 'main', 'reports': [{
            'report_id': 'opt04-20261013T000000Z-' + 'a' * 64,
            'source_report_id': 'opt04-20261013T000000Z-123456789abc',
            'report_kind': 'opt04-phase-one', 'source_commit': '1' * 40,
            'measured_scope': 'Five analytic feasibility fixtures',
            'evidence_limits': 'Descriptive only'}]}
        html = site.catalogue_index(catalogue)
        self.assertIn('href="' + catalogue['reports'][0]['report_id'] + '/performance.svg"', html)

    def test_committed_opt04_bundle_is_registered_and_stages_typed_publication(self):
        catalog_path = FIXTURES / 'catalog.json'
        catalogue = json.loads(catalog_path.read_text(encoding='utf-8'))
        reports = [report for report in catalogue['reports'] if report.get('report_kind') == 'opt04-phase-one']
        self.assertEqual(1, len(reports))
        row = reports[0]
        source = FIXTURES / row['source_report_id']
        publication = site.opt04.adapt(source)
        self.assertEqual(publication.report_id, row['report_id'])
        self.assertEqual(publication.payload_sha256, row['payload_sha256'])
        self.assertEqual(publication.native_payload_sha256, row['native_payload_sha256'])
        self.assertEqual(publication.measured_scope, row['measured_scope'])
        self.assertEqual(publication.evidence_limits, row['evidence_limits'])
        public_zip_bytes = site.opt04.offline_zip(source, publication)
        self.assertEqual(hashlib.sha256(public_zip_bytes).hexdigest(), row['zip_sha256'])
        public_zip = FIXTURES / (row['report_id'] + '.zip')
        self.assertTrue(public_zip.is_file())
        self.assertEqual(public_zip_bytes, public_zip.read_bytes())

        with tempfile.TemporaryDirectory() as directory:
            staged = site.stage(catalog_path, Path(directory) / 'site', check=True)
            report_dir = staged / row['report_id']
            self.assertIn(row['report_id'] + '/performance.svg', (staged / 'index.html').read_text(encoding='utf-8'))
            self.assertEqual(site.opt04.public_svg(json.loads((source / 'records.json').read_text())),
                             (report_dir / 'performance.svg').read_bytes())
            self.assertEqual((source / 'index.html').read_bytes(),
                             (report_dir / 'source-evidence' / 'index.html').read_bytes())
            with zipfile.ZipFile(staged / (row['report_id'] + '.zip')) as archive:
                self.assertIn(row['report_id'] + '/source-evidence/bundle.zip', archive.namelist())
                self.assertEqual((report_dir / 'performance.svg').read_bytes(), archive.read(row['report_id'] + '/performance.svg'))

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
        production=Path(__file__).resolve().parents[2]/'reports'/'algorithm-results'
        legacy=json.loads((production/'catalog.json').read_text())
        shutil.copyfile(production/'legacy-publications.json',root/'legacy-publications.json')
        reports=[]
        for report in legacy['reports'][:2]:
            source_id=report['source_report_id']
            shutil.copytree(production/source_id,root/source_id)
            shutil.copyfile(production/(source_id+'.source.zip'),root/(source_id+'.source.zip'))
            shutil.copyfile(production/(source_id+'.zip'),root/(source_id+'.zip'))
            view=site.validate_bundle(root/source_id)
            kind=report['report_kind']
            count_label={5:'Five',9:'Nine'}[len(view['payload']['scenarios'])]
            scope=f"{count_label} analytic {'convex' if kind=='convex' else 'LP'} microfixtures"
            limits='Single-adapter reference measurements; no comparator or application-scale claim; numerical references are not validated certificates'
            rid=site.lp_convex_publication_id(root,source_id)
            item=registered.PublicationRecord(kind,rid,registered._digest(view),report['source_commit'],scope,limits,tuple(sorted(site.FILES)),view['schema'],view['payload_sha256'],source_id)
            source_page=(root/source_id/'index.html').read_text(encoding='utf-8')
            links='<p>Publication <code>'+rid+'</code>; source <code>'+source_id+'</code>. <a href="report-envelope.json">Versioned report envelope</a> · <a href="publication-manifest.json">Publication manifest</a></p>'
            staged_page=source_page.replace('</body>',links+'</body>') if '</body>' in source_page else source_page+links
            artifacts=registered.publication_artifacts(root/source_id,item,staged_page.encode('utf-8'))
            archive=registered.publication_zip(rid,artifacts)
            (root/(rid+'.zip')).write_bytes(archive)
            reports.append({**report,'report_id':rid,'source_report_id':source_id,
                'native_payload_sha256':view['payload_sha256'],'payload_sha256':item.payload_sha256,
                'payload_schema':view['schema'],'measured_scope':scope,'evidence_limits':limits,
                'zip_sha256':hashlib.sha256(archive).hexdigest()})
        for kind, rid in [('opt05-hull','opt05-hull-20261012-d1c211c2'), ('geo03-hv','geo03-20261012-3c12ca125831')]:
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
        for kind,source_id in [('opt05-hull','opt05-hull-20261012-d1c211c2'),('geo03-hv','geo03-20261012-3c12ca125831')]:
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
        for kind,source_id in [('opt05-hull','opt05-hull-20261012-d1c211c2'),('geo03-hv','geo03-20261012-3c12ca125831')]:
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
        record=json.loads((FIXTURES/'geo03-20261012-3c12ca125831'/'records.json').read_text())
        missing=copy.deepcopy(record);missing['payload']['summary'].pop();missing['payload_sha256']=registered._digest(missing['payload'])
        with self.assertRaisesRegex(ValueError,'summary must contain'):
            registered.adapt_payload(missing)

    def test_geo03_report_id_is_bound_to_payload_digest(self):
        record=json.loads((FIXTURES/'geo03-20261012-3c12ca125831'/'records.json').read_text())
        record['payload']['scope_limitations'].append('Changed evidence under a reused ID')
        record['payload_sha256']=registered._digest(record['payload'])
        with self.assertRaisesRegex(ValueError,'report ID does not match payload digest'):
            registered.adapt_payload(record)

    def test_geo03_adapter_preserves_native_payload_digest_and_limitations(self):
        result = registered.adapt(FIXTURES / 'geo03-20261012-3c12ca125831')
        self.assertEqual(result.kind, 'geo03-hv')
        self.assertTrue(result.report_id.startswith('geo03-20261012-'))
        self.assertEqual(len(result.report_id.rsplit('-',1)[1]),64)
        self.assertEqual(result.source_report_id, 'geo03-20261012-3c12ca125831')
        self.assertEqual(result.payload_sha256, '3c12ca12583170423a81142c8f4b743cf88a16e463267d6864ddda4b56bd9044')
        self.assertIn('56', result.measured_scope)
        self.assertTrue(result.evidence_limits)

    def test_geo04_adapter_preserves_validated_measurement_scope(self):
        result = geo04_publication.adapt(FIXTURES / 'geo04-20261012T224946Z-c37852bcc80d')
        self.assertEqual(result.kind, 'geo04-intersection')
        self.assertEqual(result.source_report_id, 'geo04-20261012T224946Z-c37852bcc80d')
        self.assertIn('28', result.measured_scope)
        self.assertIn('4 analytic', result.measured_scope)
        self.assertIn('no comparator', result.evidence_limits.lower())
        self.assertIn('incomplete', result.evidence_limits.lower())

    def test_geo04_report_id_is_bound_to_saved_payload_digest(self):
        record = json.loads((FIXTURES / 'geo04-20261012T224946Z-c37852bcc80d' / 'records.json').read_text(encoding='utf-8'))
        record['report_id'] = 'geo04-20261012T224946Z-000000000000'
        with self.assertRaisesRegex(ValueError, 'report ID does not match payload digest'):
            geo04_publication.adapt_payload(record)

    def test_geo04_report_stages_with_scoped_page_and_reproducible_download(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'input'; root.mkdir()
            catalogue = self.publication(root)
            source_id = 'geo04-20261012T224946Z-c37852bcc80d'
            shutil.copytree(FIXTURES / source_id, root / source_id)
            shutil.copyfile(FIXTURES / (source_id + '.zip'), root / (source_id + '.zip'))
            item = geo04_publication.adapt(root / source_id)
            archive = geo04_publication.offline_zip(root / source_id, item)
            (root / (item.report_id + '.zip')).write_bytes(archive)
            catalogue['reports'].append({
                'report_id': item.report_id, 'report_kind': item.kind,
                'payload_sha256': item.payload_sha256, 'payload_schema': item.payload_schema,
                'source_commit': item.source_commit, 'measured_scope': item.measured_scope,
                'evidence_limits': item.evidence_limits,
                'zip_sha256': hashlib.sha256(archive).hexdigest(),
                'source_report_id': item.source_report_id,
            })
            (root / 'catalog.json').write_text(json.dumps(catalogue, indent=2) + '\n', encoding='utf-8')
            (root / 'index.html').write_text(site.catalogue_index(catalogue), encoding='utf-8')
            staged = site.stage(root / 'catalog.json', Path(temp) / 'site', check=True)
            page = (staged / item.report_id / 'index.html').read_text(encoding='utf-8')
            self.assertIn('Phase timing figure', page)
            self.assertIn('No competitor, speedup, application-scale, or scalability claim is made.', page)
            self.assertTrue((staged / item.report_id / 'raw-driver-output.csv').is_file())
            self.assertEqual((staged / (item.report_id + '.zip')).read_bytes(), archive)
            catalogue_page = (staged / 'index.html').read_text(encoding='utf-8')
            self.assertIn(item.report_id + '/raw-driver-output.csv', catalogue_page)
            self.assertNotIn(item.report_id + '/trials.csv', catalogue_page)
            envelope = json.loads((staged / item.report_id / 'report-envelope.json').read_text(encoding='utf-8'))
            self.assertEqual(envelope['source_report_id'], source_id)
            self.assertEqual(envelope['native_payload_sha256'], item.native_payload_sha256)
            self.assertTrue(site.validate_publication_manifest(staged / item.report_id, {
                'report_id': item.report_id, 'report_kind': item.kind, 'payload_schema': item.payload_schema,
                'payload_sha256': item.payload_sha256, 'source_commit': item.source_commit,
                'measured_scope': item.measured_scope, 'evidence_limits': item.evidence_limits,
                'native_payload_sha256': item.native_payload_sha256, 'source_report_id': source_id,
            }))

    def test_unregistered_schema_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'unregistered'):
            registered.adapt_payload({'schema': 'csl.future/1', 'report_id': 'future'})

    def test_geo_tampered_payload_is_rejected(self):
        record = json.loads((FIXTURES / 'geo03-20261012-3c12ca125831' / 'records.json').read_text())
        record['payload']['summary'][0]['failures'] = 1
        record['payload_sha256'] = registered._digest(record['payload'])
        with self.assertRaises(ValueError):
            registered.adapt_payload(record)

    def test_malformed_external_shapes_have_controlled_errors(self):
        with self.assertRaises(ValueError):
            registered.adapt_payload({'schema':'csl.geo03-hv-report/1','report_id':'geo03-20261012-3c12ca125831','payload':[]})
        with self.assertRaises(ValueError):
            registered.adapt_payload({'schema':'csl.hull-benchmark-records/1','report_id':'opt05-hull-20261012-d1c211c2','trials':[{}]})

    def test_geo_source_commit_is_required(self):
        record = json.loads((FIXTURES / 'geo03-20261012-3c12ca125831' / 'records.json').read_text())
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
            geo_page=(out/registered.adapt(FIXTURES/'geo03-20261012-3c12ca125831').report_id/'index.html').read_text(encoding='utf-8')
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
                    self.assertEqual(envelope['source_report_id'],report['source_report_id'])
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

    def test_opt06_bundle_manifest_is_read_only_and_publication_site_stages(self):
        repo=Path(__file__).resolve().parents[2]
        root=repo/'reports'/'algorithm-results'
        source_id='opt06-basis-reuse-20261014-ef70e8c5-r2'
        source=root/source_id
        item=registered.adapt(source)
        self.assertEqual(item.kind,'opt06-basis-reuse')
        self.assertEqual(item.source_commit,'ef70e8c580a9556b0f5d96e49070d33221bf5b64')
        self.assertEqual(len(item.files),93)
        self.assertIn('42 verified measured trials',item.measured_scope)
        page=registered.render_page(source,item)
        self.assertIn('Membership LP calls (excluding Phase-I)',page)
        self.assertIn('Phase-I solves',page)
        with tempfile.TemporaryDirectory() as temp:
            copied=Path(temp)/source.name
            shutil.copytree(source,copied)
            manifest=copied/'manifest.sha256'
            before=hashlib.sha256(manifest.read_bytes()).hexdigest()
            with (copied/'summary.csv').open('ab') as stream:
                stream.write(b'tampered\n')
            validator=copied/'harness'/'validate.py'
            result=subprocess.run([sys.executable,str(validator),str(copied)],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(hashlib.sha256(manifest.read_bytes()).hexdigest(),before)
            staged=site.stage(root/'catalog.json',Path(temp)/'site',check=True)
            self.assertTrue((staged/item.report_id/'index.html').is_file())
            self.assertTrue((staged/(item.report_id+'.zip')).is_file())
            published=(staged/item.report_id/'index.html').read_text(encoding='utf-8')
            self.assertIn('42 verified measured trials',published)

    def test_production_catalogue_uses_shared_outer_contract_for_all_kinds(self):
        repo=Path(__file__).resolve().parents[2]
        root=repo/'reports'/'algorithm-results'
        catalogue=json.loads((root/'catalog.json').read_text(encoding='utf-8'))
        self.assertEqual(catalogue['schema'],'csl.algorithm-report-catalog/3')
        self.assertEqual({item['report_kind'] for item in catalogue['reports']},{'lp','convex','opt04-phase-one','opt05-hull','opt06-basis-reuse','opt07-ordered-hull','opt11-recursive-hull','geo03-hv','geo04-intersection','geo02-affine-sum','geo05-projection-predecessor','geo06-quickhull','b08-displayed-exact','issue3-finite-catalogue','syn01-nominal-forward','syn02-terminal-minimizers','syn07-ts01-analytic','syn04-strategy-b-ts01','syn04-strategy-b-ts02','syn03-strategy-a-ts01','syn03-strategy-a-ts02','syn-ts01-paired-comparison'})
        shared={'report_id','report_kind','payload_sha256','source_commit','zip_sha256'}
        for report in catalogue['reports']:
            self.assertTrue(shared <= set(report))
            self.assertIn('source_report_id',report)
            self.assertNotEqual(report['report_id'],report['source_report_id'])
            self.assertRegex(report['payload_sha256'],r'^[0-9a-f]{64}$')
            self.assertRegex(report['source_commit'],r'^[0-9a-f]{40}$')
            self.assertRegex(report['zip_sha256'],r'^[0-9a-f]{64}$')
            if report['report_kind'] in ('opt05-hull','opt06-basis-reuse','geo03-hv','geo02-affine-sum','geo05-projection-predecessor','geo06-quickhull','b08-displayed-exact','issue3-finite-catalogue','syn01-nominal-forward','syn02-terminal-minimizers','syn-ts01-paired-comparison','opt11-recursive-hull'):
                self.assertTrue({'measured_scope','evidence_limits'} <= set(report))
                # Per-kind saved schemas/manifests are validated at the boundary,
                # then projected into the same catalogue identity contract.
                self.assertIn('source_report_id',report)
                self.assertNotEqual(report['report_id'],report['source_report_id'])
                publisher=(syn02_publication if report['report_kind']=='syn02-terminal-minimizers' else
                           syn_ts01_paired_publication if report['report_kind']=='syn-ts01-paired-comparison' else
                           syn01_publication if report['report_kind']=='syn01-nominal-forward' else
                           geo02_publication if report['report_kind']=='geo02-affine-sum' else
                           geo05_publication if report['report_kind']=='geo05-projection-predecessor' else
                           geo06_publication if report['report_kind']=='geo06-quickhull' else
                           opt11_publication if report['report_kind']=='opt11-recursive-hull' else registered)
                if report['report_kind']=='b08-displayed-exact':
                    publisher=b08_publication
                if report['report_kind']=='issue3-finite-catalogue':
                    publisher=issue3_publication
                adapted=publisher.adapt(root/report['source_report_id'])
                self.assertEqual((report['report_id'],report['report_kind'],report['payload_sha256'],report['source_commit']),
                                 (adapted.report_id,adapted.kind,adapted.payload_sha256,adapted.source_commit))
                self.assertEqual(report['source_report_id'],adapted.source_report_id)
                self.assertEqual((report['measured_scope'],report['evidence_limits']),
                                 (adapted.measured_scope,adapted.evidence_limits))
        registered_rows=[report for report in catalogue['reports'] if report['report_kind'] in ('opt05-hull','opt06-basis-reuse','geo03-hv')]
        source_ids={report['source_report_id'] for report in registered_rows}
        public_ids={report['report_id'] for report in registered_rows}
        self.assertEqual(source_ids,{path.name for path in root.iterdir() if path.is_dir() and path.name.startswith(('opt05-hull-','opt06-basis-reuse-','geo03-'))})
        producer_geo_zip=root/'geo03-20261012-3c12ca125831.zip'
        self.assertEqual(hashlib.sha256(producer_geo_zip.read_bytes()).hexdigest(),
                         'e518e1c1786a67561d4cc0336231746f5f2e748cd0aaaba707d2c4eaf97dfd50')
        self.assertEqual(producer_geo_zip.read_bytes(),(root/'geo03-20261012-3c12ca125831.source.zip').read_bytes())
        self.assertEqual(public_ids|{'geo03-20261012-3c12ca125831'},
                         {path.stem for path in root.iterdir() if path.suffix=='.zip' and not path.name.endswith('.source.zip') and path.name.startswith(('opt05-hull-','opt06-basis-reuse-','geo03-'))})
        with tempfile.TemporaryDirectory() as temp:
            first=site.stage(root/'catalog.json',Path(temp)/'stage-a',check=True)
            second=site.stage(root/'catalog.json',Path(temp)/'stage-b',check=True)
            pins=json.loads((root/'legacy-publications.json').read_text(encoding='utf-8'))
            self.assertEqual(registered._digest(pins),site.LEGACY_PINS_SHA256)
            live_anchors={
                'lp-20261012T000346Z-ee5e9193b7a5':('2b7d31cb884861fdab7abe2d1fad8dadb4be1489f5e1edda4afdc8b05b3c22c2','4a59e312cdfdfd3fb38abbc4ceac8991a9d41a76689b8bc926fe061aaa5027c6'),
                'convex-20261012T041854Z-4d54a407c9b2':('14882d50e392e3abfd57504c6f9fb175aa73f6ace856a8f20322ffdc9f1220fc','46581b40d1f9cf6a30b05937eda2c4d89d336d4ba25c0ed4130dd908aafe9b40')}
            self.assertEqual(set(pins['reports']),set(live_anchors))
            for source_id,(page_sha,zip_sha) in live_anchors.items():
                source_pins=pins['reports'][source_id]
                self.assertEqual(source_pins['files']['index.html'],page_sha)
                self.assertEqual(source_pins['zip_sha256'],zip_sha)
                for name,digest in source_pins['files'].items():
                    self.assertEqual(hashlib.sha256((first/source_id/name).read_bytes()).hexdigest(),digest)
                    self.assertEqual((first/source_id/name).read_bytes(),(root/source_id/name).read_bytes())
                self.assertEqual(hashlib.sha256((first/(source_id+'.zip')).read_bytes()).hexdigest(),zip_sha)
                self.assertEqual((first/(source_id+'.zip')).read_bytes(),(root/(source_id+'.source.zip')).read_bytes())
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
            for report in catalogue['reports']:
                if report['report_kind'] not in ('opt05-hull','geo03-hv'):
                    continue
                rid=report['report_id']
                page=(first/rid/'index.html').read_text(encoding='utf-8')
                self.assertIn('records.json',page)
                self.assertIn('trials.csv',page)
                self.assertIn('summary.csv',page)
                self.assertIn('latency.svg',page)
                self.assertTrue((first/rid/'latency.svg').is_file())
                envelope=json.loads((first/rid/'report-envelope.json').read_text(encoding='utf-8'))
                manifest=json.loads((first/rid/'publication-manifest.json').read_text(encoding='utf-8'))
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

    def test_new_lp_source_stages_without_extending_historical_pinset(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'input';root.mkdir()
            catalogue=self.publication(root)
            historical=catalogue['reports'][0]
            old_source=historical['source_report_id']
            old_view=site.data.load_view(root/old_source/'records.json')
            payload=copy.deepcopy(old_view['payload'])
            payload['created_utc']='2026-10-12T00:03:47Z'
            view=site.data.seal(payload)
            source_id=view['report_id']
            self.assertNotEqual(source_id,old_source)
            bundle=root/source_id
            shutil.copytree(root/old_source,bundle)
            (bundle/'records.json').write_text(json.dumps(view,indent=2)+'\n',encoding='utf-8')
            exported=json.loads((bundle/'export.json').read_text(encoding='utf-8'))
            exported['payload_sha256']=view['payload_sha256']
            exported['plot']['payload_sha256']=view['payload_sha256']
            (bundle/'export.json').write_text(json.dumps(exported,indent=2)+'\n',encoding='utf-8')
            svg=(bundle/'latency.svg').read_text(encoding='utf-8')
            (bundle/'index.html').write_text(site.render.document(view,svg,exported['artifact_ref']),encoding='utf-8')
            manifest=json.loads((bundle/'manifest.json').read_text(encoding='utf-8'))
            manifest['report_id']=source_id
            manifest['files']={name:site.data.file_digest(bundle/name) for name in manifest['files']}
            (bundle/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
            site.make_zip(bundle,root/(source_id+'.source.zip'))
            rid=site.lp_convex_publication_id(root,source_id)
            scope,limits=site.lp_convex_publication_metadata('lp',view)
            item=registered.PublicationRecord('lp',rid,registered._digest(view),historical['source_commit'],scope,limits,
                                              tuple(sorted(site.FILES)),view['schema'],view['payload_sha256'],source_id)
            source_page=(bundle/'index.html').read_text(encoding='utf-8')
            links='<p>Publication <code>'+rid+'</code>; source <code>'+source_id+'</code>. <a href="report-envelope.json">Versioned report envelope</a> · <a href="publication-manifest.json">Publication manifest</a></p>'
            staged_page=source_page.replace('</body>',links+'</body>')
            artifacts=registered.publication_artifacts(bundle,item,staged_page.encode('utf-8'))
            archive=registered.publication_zip(rid,artifacts)
            (root/(rid+'.zip')).write_bytes(archive)
            catalogue['reports'].append({**historical,'report_id':rid,'source_report_id':source_id,
                'payload_sha256':item.payload_sha256,'native_payload_sha256':view['payload_sha256'],
                'zip_sha256':hashlib.sha256(archive).hexdigest()})
            (root/'catalog.json').write_text(json.dumps(catalogue,indent=2)+'\n',encoding='utf-8')
            (root/'index.html').write_text(site.catalogue_index(catalogue),encoding='utf-8')
            staged=site.stage(root/'catalog.json',Path(temp)/'stage',check=True)
            self.assertTrue((staged/rid/'report-envelope.json').is_file())
            self.assertEqual((staged/(old_source+'.zip')).read_bytes(),(root/(old_source+'.source.zip')).read_bytes())
            self.assertTrue((staged/historical['report_id']/'report-envelope.json').is_file())
            catalogue['reports'].remove(historical)
            (root/'catalog.json').write_text(json.dumps(catalogue,indent=2)+'\n',encoding='utf-8')
            (root/'index.html').write_text(site.catalogue_index(catalogue),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'legacy publication sources differ'):
                site.stage(root/'catalog.json',Path(temp)/'missing-historical',check=True)

    def test_legacy_retention_rejects_changed_bytes_and_rehashed_pinset(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'input';root.mkdir()
            self.publication(root)
            source_id='lp-20261012T000346Z-ee5e9193b7a5'
            archive=root/(source_id+'.zip')
            archive.write_bytes(archive.read_bytes()+b'altered')
            with self.assertRaisesRegex(ValueError,'legacy publication ZIP differs'):
                site.stage(root/'catalog.json',Path(temp)/'altered-zip',check=True)
            archive.write_bytes((root/(source_id+'.source.zip')).read_bytes())
            pins_path=root/'legacy-publications.json'
            pins=json.loads(pins_path.read_text(encoding='utf-8'))
            pins['reports'][source_id]['files']['index.html']='0'*64
            pins_path.write_text(json.dumps(pins),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'legacy publication pinset differs'):
                site.stage(root/'catalog.json',Path(temp)/'altered-pins',check=True)

    def test_lp_convex_public_ids_change_with_source_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'input';root.mkdir()
            self.publication(root)
            for source_id in ('lp-20261012T000346Z-ee5e9193b7a5',
                              'convex-20261012T041854Z-4d54a407c9b2'):
                with self.subTest(source_id=source_id):
                    original=site.lp_convex_publication_id(root,source_id)
                    evidence=root/source_id/'process-stderr.txt'
                    native=evidence.read_bytes()
                    evidence.write_bytes(native+b'\nchanged evidence')
                    self.assertNotEqual(site.lp_convex_publication_id(root,source_id),original)
                    evidence.write_bytes(native)

    def test_real_stage_rejects_tampered_file_and_unregistered_kind(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'input';root.mkdir()
            catalogue=self.publication(root)
            geo=root/'geo03-20261012-3c12ca125831'
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
            (root/'geo03-20261012-3c12ca125831'/'unexpected.dat').write_text('extra')
            with self.assertRaisesRegex(ValueError,'unregistered files'):
                site.stage(root/'catalog.json',Path(temp)/'extra-stage',check=True)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'input';root.mkdir()
            catalogue=self.publication(root)
            catalogue['reports'][3]['report_id']=catalogue['reports'][2]['report_id']
            (root/'catalog.json').write_text(json.dumps(catalogue),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'duplicate'):
                site.stage(root/'catalog.json',Path(temp)/'dupe-stage',check=False)

    def test_real_stage_rejects_lp_convex_scope_or_evidence_not_bound_to_view(self):
        for field in ('measured_scope','evidence_limits'):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temp:
                root=Path(temp)/'input';root.mkdir()
                catalogue=self.publication(root)
                catalogue['reports'][0][field]+=' forged'
                (root/'catalog.json').write_text(json.dumps(catalogue,indent=2)+'\n',encoding='utf-8')
                with self.assertRaisesRegex(ValueError,'scope/evidence differs from validated report policy'):
                    site.stage(root/'catalog.json',Path(temp)/'bad-stage',check=False)
                self.assertFalse((Path(temp)/'bad-stage').exists())

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
            original_rid='geo03-20261012-3c12ca125831'
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
            rid='geo03-20261012-3c12ca125831'
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
