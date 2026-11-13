from pathlib import Path
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/reports'))
import native_fixed_tail_episode_report as report


class NativeEpisodeReportTests(unittest.TestCase):
    def test_complete_matrix_raw_bytes_and_scope_survive_staging(self):
        assets, entry, card = report.build()
        page = assets[report.ROUTE+'/index.html'].decode()
        self.assertIn('450 native queries and 7,925 physical-region instances', page)
        self.assertIn('predates the finer construction-role event trace', page)
        self.assertIn('These probes are not full episodes', page)
        self.assertIn('stored indices (0, 2)', page)
        self.assertIn('stored indices (1, 3)', page)
        self.assertIn('15 nonlinear episodes', card)
        self.assertEqual(entry['page'], report.ROUTE+'/index.html')
        for name, _, _ in report.TASKS:
            for family in report.FAMILIES:
                relative=f'records/{name}-{family}/raw.zip'
                self.assertEqual(assets[report.ROUTE+'/'+relative], (ROOT/report.SOURCE/relative).read_bytes())
        svg = ET.fromstring(assets[entry['figure']])
        self.assertEqual(svg.attrib['role'], 'img')
        self.assertIsNotNone(svg.find('{http://www.w3.org/2000/svg}desc'))

    def test_changed_receipt_cost_cannot_be_relabelled_as_an_archive_result(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root/report.SOURCE
            shutil.copytree(ROOT/report.SOURCE, source)
            path = source/'records/earth-orbit-box/receipt.json'
            receipt=json.loads(path.read_text())
            receipt['physical_objective']['total']+=1
            path.write_text(json.dumps(receipt))
            manifest=source/'files.sha256'
            rows=[]
            for line in manifest.read_text().splitlines():
                digest, name=line.split('  ',1)
                if name=='records/earth-orbit-box/receipt.json':
                    digest=hashlib.sha256(path.read_bytes()).hexdigest()
                rows.append(digest+'  '+name+'\n')
            manifest.write_text(''.join(rows))
            with self.assertRaisesRegex(ValueError, 'cost differs'):
                report.build(root)


if __name__ == '__main__':
    unittest.main()
