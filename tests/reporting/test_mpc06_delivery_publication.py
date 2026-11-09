"""Source/report staging preserves inputs and rejects stale evidence."""
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import json
import hashlib
import zipfile
import importlib.util
from scripts.reports.mpc06_delivery import records,figures
from scripts.reports import stage_mpc06_delivery as STAGE

HAS_MATPLOTLIB=importlib.util.find_spec('matplotlib') is not None

@unittest.skipUnless(HAS_MATPLOTLIB,'publication tests require pinned report environment')
class Mpc06DeliveryPublicationTests(unittest.TestCase):
    def build(self,folder):
        original=records.subprocess.check_output
        def clean_status(command,**kwargs):
            return '' if command==['git','status','--porcelain'] else original(command,**kwargs)
        source=folder/'input'
        with mock.patch.object(records.subprocess,'check_output',side_effect=clean_status):records.build(records.UPSTREAM,source)
        report=folder/'report';figures.render(source,report)
        return source,report

    def sums(self,source):
        files=sorted(p for p in source.rglob('*') if p.is_file() and p!=source/'SHA256SUMS')
        (source/'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(source).as_posix()}\n' for p in files))

    def test_deterministic_stage_keeps_inputs_old_routes_and_offline_members(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);source,report=self.build(folder)
            before={p.relative_to(report):p.read_bytes() for p in report.rglob('*') if p.is_file()}
            archives=[];routes=[]
            for side in ('one','two'):
                site=folder/side;site.mkdir();(site/'index.html').write_text('<html><body>older route</body></html>')
                route=STAGE.stage(report,site);routes.append(route);archives.append((site/(route+'.zip')).read_bytes())
                self.assertIn('older route',(site/'index.html').read_text())
                with zipfile.ZipFile(site/(route+'.zip')) as bundle:
                    for name in ('publication-manifest.json','figure-export.json','invariant-tightenings.svg','actual-state-paths.png','feasibility-grid.svg','input/result.json'):
                        self.assertIn(route+'/'+name,bundle.namelist())
            self.assertEqual(routes[0],routes[1]);self.assertEqual(archives[0],archives[1])
            self.assertEqual({p.relative_to(report):p.read_bytes() for p in report.rglob('*') if p.is_file()},before)

    def test_rebound_upstream_record_is_not_a_new_mathematical_certificate(self):
        import shutil
        with tempfile.TemporaryDirectory() as temporary:
            source=Path(temporary)/'online';shutil.copytree(records.UPSTREAM,source)
            path=source/'checked-inputs/mpc06-online-anchor-v1/result.json'
            value=json.loads(path.read_text());value['attempts'][0]['actual']['worst']='0'
            path.write_text(json.dumps(value));self.sums(source)
            with self.assertRaisesRegex(ValueError,'independently reviewed immutable capture'):
                records.upstream(source)

    def test_rebound_copied_source_is_not_authenticated_by_inventory(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);source,_=self.build(folder)
            path=source/'source/reference.py';path.write_text(path.read_text()+'\n# changed retained source\n')
            self.sums(source)
            with self.assertRaisesRegex(ValueError,'copied source binding'):
                records.validate(source)

    def test_tampered_exact_cost_or_figure_cannot_be_blessed_by_checksums(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);source,report=self.build(folder)
            path=source/'result.json';record=json.loads(path.read_text());record['cases'][0]['references'][0]['worst_cost']='0'
            path.write_text(json.dumps(record));self.sums(source)
            with self.assertRaises(ValueError):records.validate(source)
            figure=report/'actual-state-paths.svg';figure.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
            self.sums(report)
            with self.assertRaisesRegex(ValueError,'rendering'):STAGE.validate(report)

if __name__=='__main__':unittest.main()
