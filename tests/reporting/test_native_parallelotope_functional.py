"""The published finite-plan figures must describe the actual frozen episodes."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/reports'))
import native_parallelotope_functional as report


class NativeParallelotopePublicationTest(unittest.TestCase):
    def test_saved_episodes_have_all_original_holds_and_both_replays(self):
        manifest = report.check(report.BUNDLE)
        self.assertEqual(sum(r['completed_holds'] for r in manifest['tasks'].values()), 90)
        coverage = {'complete': 0, 'incomplete': 0}
        for name, _, horizon, _ in report.TASKS:
            data = json.loads((report.BUNDLE / name / 'figure-data.json').read_bytes())
            self.assertEqual(len(data['queries']), horizon)
            self.assertEqual(sum(len(q['sets'][0]['stages']) for q in data['queries']), horizon*(horizon+3)//2)
            for query in data['queries']:
                coverage[query['coverage']] += 1
            self.assertEqual(set(manifest['tasks'][name]['replay']), {'common', 'tight'})
            self.assertTrue(all(r['status'] == 'complete' for r in manifest['tasks'][name]['replay'].values()))
        self.assertEqual(coverage, {'incomplete': 79, 'complete': 11})

    def test_figure_substitution_is_rejected_even_with_updated_file_checksums(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / 'bundle'
            shutil.copytree(report.BUNDLE, bundle)
            path = bundle / 'syn-nl-lv-01/figure-data.json'
            data = json.loads(path.read_bytes())
            data['states'][1][0] += 1
            report.write_json(path, data)
            sums = bundle / 'files.sha256'
            sums.write_text(''.join(f'{report.sha(p.read_bytes())}  {p.relative_to(bundle).as_posix()}\n'
                                   for p in sorted(bundle.rglob('*')) if p.is_file() and p != sums))
            with self.assertRaisesRegex(ValueError, 'figure data differ'):
                report.check(bundle)

    def test_four_state_frame_recovers_physical_initial_state(self):
        for name in ('earth-orbit', 'syn-nl-fuel-01'):
            data = json.loads((report.BUNDLE / name / 'figure-data.json').read_bytes())
            for query in data['queries']:
                corners = report.physical_corners(query['sets'][0]['stages'][0], data['source_derived_frame'])
                center = [sum(p[i] for p in corners)/len(corners) for i in range(4)]
                for actual, expected in zip(center, data['states'][query['update']]):
                    self.assertAlmostEqual(actual, expected, places=9)

    def test_changed_raw_member_is_rejected(self):
        import zipfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'raw.zip'
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('request.json', b'changed')
            with self.assertRaisesRegex(ValueError, 'raw archive bytes differ'):
                report.checked_archive(path, {'request.json': {'bytes': 7, 'sha256': report.sha(b'original')}})


if __name__ == '__main__':
    unittest.main()
