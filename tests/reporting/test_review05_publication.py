from __future__ import annotations
import hashlib
import http.server
import os
import subprocess
import sys
import threading
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
from urllib.parse import urljoin
import unittest
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('review05_publication',ROOT/'scripts/reports/stage_review05_family_query.py')
STAGER=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STAGER)
QUERY=ROOT/'reports/algorithm-results/review05-family-query-20261110-3b98f5b0'
PHASE=ROOT/'reports/algorithm-results/review05-build-phases-20261110-468cc0eb'

class PublicationTests(unittest.TestCase):
    def test_checked_immutable_reports_stage_with_discoverable_scalar_example(self):
        self.assertTrue(callable(getattr(STAGER,'stage',None)))
        before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for root in (QUERY,PHASE) for p in root.rglob('*') if p.is_file()}
        with tempfile.TemporaryDirectory() as directory:
            site=Path(directory)/'site';(site/'examples').mkdir(parents=True)
            (site/'index.html').write_text('<html><body><h1>Archive</h1></body></html>')
            (site/'examples/index.html').write_text('<html><body><h1>Examples</h1></body></html>')
            route=STAGER.stage(site)
            self.assertRegex(route,r'^review05-family-query-[0-9a-f]{20}$')
            self.assertIn(route+'/index.html',(site/'index.html').read_text())
            gallery=(site/'examples/index.html').read_text()
            self.assertIn('<article',gallery);self.assertIn('scalar state dimension 1',gallery)
            self.assertIn('../'+route+'/index.html#scalar-2d',gallery)
            self.assertEqual((site/route/QUERY.name/'offline.zip').read_bytes(),(QUERY/'offline.zip').read_bytes())
            self.assertEqual((site/route/QUERY.name/'checks.json').read_bytes(),(QUERY/'checks.json').read_bytes())
            self.assertEqual((site/route/PHASE.name/'phase-summary.json').read_bytes(),(PHASE/'phase-summary.json').read_bytes())
            page=(site/route/'index.html').read_text()
            self.assertIn('inconclusive',page.lower());self.assertIn('does not follow from selected witnesses',page)
            with zipfile.ZipFile(site/(route+'.zip')) as archive:
                self.assertIsNone(archive.testzip())
                self.assertIn(route+'/'+QUERY.name+'/control-projection.svg',archive.namelist())
                self.assertEqual(archive.read(route+'/'+QUERY.name+'/offline.zip'),(QUERY/'offline.zip').read_bytes())
            marker=json.loads((site/route/'publication-manifest.json').read_text())
            self.assertEqual(marker['verification']['query']['verified'],168)
            self.assertEqual(marker['verification']['phase']['verified'],84)
            # A repeated immutable route cannot overwrite an existing publication.
            saved=(site/'index.html').read_bytes()
            with self.assertRaises(ValueError):STAGER.stage(site)
            self.assertEqual((site/'index.html').read_bytes(),saved)
        self.assertEqual(before,{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for root in (QUERY,PHASE) for p in root.rglob('*') if p.is_file()})

    def test_historical_benchmark_links_are_out_of_scope_and_scoped_alias_is_published(self):
        self.assertFalse((ROOT/'benchmarks/reporting/review05/README.md').exists())
        sealed_readme=STAGER._historical_route_readme()
        self.assertEqual(hashlib.sha256(sealed_readme).hexdigest(),STAGER.HISTORICAL_ROUTE_README_SHA)
        retirement=STAGER._historical_route_metadata()
        self.assertEqual(json.loads(retirement)['schema'],'csl.retired-working-guide-route/1')
        with tempfile.TemporaryDirectory() as directory:
            site=Path(directory)/'site';(site/'examples').mkdir(parents=True)
            (site/'index.html').write_text('<html><body><h1>Archive</h1></body></html>')
            (site/'examples/index.html').write_text('<html><body><h1>Examples</h1></body></html>')
            report_ids=('review05-horizon-match-20261031','review05-dimension-20261031')
            for report_id in report_ids:
                source=ROOT/'reports/algorithm-results'/report_id/'README.md'
                destination=site/report_id/'README.md'
                destination.parent.mkdir(parents=True)
                destination.write_bytes(source.read_bytes())
            route=STAGER.stage(site)
            alias=site.joinpath(*STAGER.HISTORICAL_ROUTE_ALIAS.parts)
            metadata_alias=site.joinpath(*STAGER.HISTORICAL_ROUTE_METADATA_ALIAS.parts)
            self.assertEqual(alias.read_bytes(),sealed_readme)
            self.assertEqual(metadata_alias.read_bytes(),retirement)
            self.assertEqual(hashlib.sha256(metadata_alias.read_bytes()).hexdigest(),hashlib.sha256(retirement).hexdigest())
            current_index=(site/route/'index.html').read_text()
            self.assertIn('../benchmarks/reporting/review05/route-retirement.json',current_index)
            for report_id in report_ids:
                page=site/report_id/'README.md'
                href='../../../benchmarks/reporting/review05/README.md'
                self.assertIn(href,page.read_text())
                old_target=(page.parent/href).resolve()
                self.assertFalse(old_target.is_relative_to(site.resolve()))
                published_url=urljoin('https://butahlecoq.github.io/controlled-systems-lab/'+report_id+'/README.md',href)
                self.assertEqual(published_url,'https://butahlecoq.github.io/benchmarks/reporting/review05/README.md')
            scoped_url='https://butahlecoq.github.io/controlled-systems-lab/benchmarks/reporting/review05/README.md'
            self.assertEqual(scoped_url, json.loads(retirement)['current_project_route']['public_alias'])
            self.assertEqual((site/'benchmarks/reporting/review05/README.md').read_bytes(),sealed_readme)

    def test_tampered_summary_checks_or_figure_fail_before_any_stage_write(self):
        self.assertTrue(callable(getattr(STAGER,'stage',None)))
        for filename in ('summary.json','checks.json','control-projection.svg','offline.zip'):
            with self.subTest(filename=filename),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);source=root/QUERY.name;shutil.copytree(QUERY,source)
                path=source/filename;path.write_bytes(path.read_bytes()+b'corruption')
                site=root/'site';(site/'examples').mkdir(parents=True)
                for index in (site/'index.html',site/'examples/index.html'):index.write_text('<html><body></body></html>')
                before={str(p.relative_to(site)):p.read_bytes() for p in site.rglob('*') if p.is_file()}
                with self.assertRaises(ValueError):STAGER.stage(site,query_source=source)
                self.assertEqual(before,{str(p.relative_to(site)):p.read_bytes() for p in site.rglob('*') if p.is_file()})

    def test_rehashed_changed_manifest_is_not_the_reviewed_evidence(self):
        self.assertTrue(callable(getattr(STAGER,'validate',None)))
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/QUERY.name;shutil.copytree(QUERY,source)
            (source/'summary.json').write_text('{}')
            sums=source/'SHA256SUMS';lines=[]
            for line in sums.read_text().splitlines():
                _,name=line.split('  ',1);lines.append(hashlib.sha256((source/name).read_bytes()).hexdigest()+'  '+name)
            sums.write_text('\n'.join(lines)+'\n')
            with self.assertRaisesRegex(ValueError,'reviewed'):STAGER.validate(source,PHASE)

    def test_changed_raw_zip_member_and_phase_artifact_are_refused(self):
        raw=b'{"registered_synthesis_ns":1}'
        manifest=(hashlib.sha256(raw).hexdigest()+'  attempts/0000/stdout.txt\n').encode()
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as archive:
            archive.writestr('SHA256SUMS',manifest)
            archive.writestr('attempts/0000/stdout.txt',b'{"registered_synthesis_ns":1e18}')
        with self.assertRaisesRegex(ValueError,'checksum'):STAGER.checked_zip(stream.getvalue(),manifest)
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/PHASE.name;shutil.copytree(PHASE,source)
            (source/'attempts/0000/stdout.txt').write_text('{}')
            with self.assertRaisesRegex(ValueError,'checksum'):STAGER.validate(QUERY,source)

    def test_current_checker_refusal_blocks_staging_even_with_frozen_cached_checks(self):
        original=STAGER._module
        def module(name):
            value=original(name)
            if name=='check_family_query':value.check_process=lambda *args:{'status':'incorrect','reason':'current independent rejection'}
            return value
        with tempfile.TemporaryDirectory() as directory:
            site=Path(directory);(site/'examples').mkdir()
            for index in (site/'index.html',site/'examples/index.html'):index.write_text('<html><body></body></html>')
            with patch.object(STAGER,'_module',side_effect=module),self.assertRaisesRegex(ValueError,'current.*mathematical'):
                STAGER.stage(site)
            self.assertEqual({str(p.relative_to(site)) for p in site.rglob('*') if p.is_file()}, {'index.html','examples/index.html'})

    def test_unsafe_site_index_is_refused_without_touching_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);site=root/'site';(site/'examples').mkdir(parents=True)
            target=root/'outside.html';target.write_text('preserve outside')
            (site/'index.html').symlink_to(target)
            (site/'examples/index.html').write_text('<html><body></body></html>')
            with self.assertRaises(ValueError):STAGER.stage(site)
            self.assertEqual(target.read_text(),'preserve outside')

    def test_existing_managed_deploy_gate_rejects_stale_head(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                data=json.dumps({'commit':{'sha':'2'*40}}).encode()
                self.send_response(200);self.end_headers();self.wfile.write(data)
            def log_message(self,*args):pass
        server=http.server.HTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory);output=root/'github-output';site=root/'site';site.mkdir()
                environment=dict(os.environ,GITHUB_REPOSITORY='example/reports',GITHUB_SHA='1'*40,
                    GITHUB_TOKEN='local-test-token',GITHUB_OUTPUT=str(output),PAGES_SITE_DIR=str(site),
                    GITHUB_API_URL='http://127.0.0.1:'+str(server.server_port))
                environment.pop('PAGES_SOURCE_RUN_ID',None);environment.pop('GITHUB_EVENT_PATH',None)
                result=subprocess.run([sys.executable,str(ROOT/'scripts/reports/check_deploy_head.py')],
                    env=environment,capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(output.read_text(),'current=false\n')
                self.assertFalse((site/'pages-augmentation-source.json').exists())
        finally:server.shutdown();server.server_close();thread.join()

    def test_unsafe_zip_members_and_symlinked_sources_are_refused(self):
        self.assertTrue(callable(getattr(STAGER,'checked_zip',None)))
        for name in ('../escape','/absolute','C:/escape','safe\\escape','same/../escape'):
            stream=io.BytesIO()
            with zipfile.ZipFile(stream,'w') as archive:archive.writestr(name,b'x')
            with self.subTest(name=name),self.assertRaises(ValueError):STAGER.checked_zip(stream.getvalue())
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/QUERY.name;source.symlink_to(QUERY,target_is_directory=True)
            with self.assertRaises(ValueError):STAGER.validate(source,PHASE)

if __name__=='__main__':unittest.main()
