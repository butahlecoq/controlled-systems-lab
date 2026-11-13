"""Saved native MPC data, drawings and publication preserve their source identity."""
import hashlib
import importlib
import shutil
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/reports'))
renderer = importlib.import_module("native_discrete_models")
native = importlib.import_module("stage_native_discrete_models")


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attributes):
        self.links.extend(value for name, value in attributes if name in {'href', 'src'})


class NativeDiscreteTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.bundle = self.root / 'reports/algorithm-results' / native.ROUTE
        shutil.copytree(renderer.BUNDLE, self.bundle)
        (self.root / 'docs/examples').mkdir(parents=True)
        for page in (*native.PAGES, 'examples.css'):
            shutil.copyfile(ROOT / 'docs/examples' / page, self.root / 'docs/examples' / page)

    def test_same_payload_repack_with_recomputed_sidecar_is_rejected(self):
        import zipfile
        path = self.bundle / (native.ROUTE + '.zip')
        original = path.read_bytes()
        with zipfile.ZipFile(path) as archive:
            payloads = [(name, archive.read(name)) for name in archive.namelist()]
        with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_STORED) as archive:
            for name, content in payloads:
                archive.writestr(name, content)
        self.assertNotEqual(path.read_bytes(), original)
        with zipfile.ZipFile(path) as archive:
            self.assertEqual([(name, archive.read(name)) for name in archive.namelist()], payloads)
        path.with_suffix('.zip.sha256').write_text(
            hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.name+'\n')
        with self.assertRaisesRegex(ValueError, 'archive differs from frozen publication identity'):
            native.build(self.root)

    def test_noncanonical_archive_sidecar_is_rejected(self):
        path = self.bundle / (native.ROUTE + '.zip.sha256')
        canonical = path.read_bytes()
        for content in (canonical.rstrip(b'\n'), canonical+b'\n', b' '+canonical):
            with self.subTest(content=content):
                path.write_bytes(content)
                with self.assertRaisesRegex(ValueError, 'archive checksum differs'):
                    native.build(self.root)
        path.write_bytes(canonical)

    def test_literal_numerical_replay_and_immutable_raw_identity(self):
        result = renderer.check(self.bundle)
        self.assertEqual(result['replans'], 15)
        self.assertAlmostEqual(result['realized_running_cost_no_terminal'], 28.0588822368079)
        expected = {'plans.csv': 'c1a9379f999d2a484d029e52ace29d08b7337b387ecb749e00aab453569f087d',
                    'models.csv': '498d3ff2ab5fcf817b7d0d1a22e6fa0a9344bdf40880f41aa8bab2329e5cf514',
                    'run.txt': 'c32b58155bcf29911e5af1f4a80aa7f491b827ac0fa06078ddd1cb33fcada9ce'}
        for name, digest in expected.items():
            self.assertEqual(hashlib.sha256((self.bundle / 'raw' / name).read_bytes()).hexdigest(), digest)

    def test_incomplete_duplicate_or_changed_prediction_is_rejected(self):
        path = self.bundle / 'raw/plans.csv'
        original = path.read_text()
        rows = original.splitlines(keepends=True)
        for content in (''.join(rows[:-1]), original + rows[1], original.replace('0,predicted_state,0,0,0\n', '0,predicted_state,0,0,1\n')):
            path.write_text(content)
            with self.assertRaises(ValueError):
                renderer.check(self.bundle)
        path.write_text(original)

    def test_frozen_stage_preserves_bytes_links_and_archive_inventory(self):
        files, entries, cards = native.build(self.root)
        self.assertEqual(native.build(self.root), (files, entries, cards))
        self.assertEqual(len(entries), 1)
        self.assertIn('id="native-quadcopter-mpc"', cards)
        for page in native.PAGES:
            links = Links()
            links.feed(files[page].decode())
            for link in links.links:
                if ':' not in link and not link.startswith(('#', '../')) and link not in {'index.html', 'examples.css'}:
                    self.assertIn(link.split('#')[0], files)
        path = self.bundle / 'raw/plans.csv'
        path.write_bytes(path.read_bytes() + b'altered\n')
        with self.assertRaisesRegex(ValueError, 'digest differs'):
            native.build(self.root)

    def test_composed_routes_have_real_producers_and_book_navigation(self):
        finalizer = importlib.import_module('pages_route_retirement')
        book = importlib.import_module('learning_book')
        files, entries, cards = native.build(self.root)
        site = self.root / 'site'
        for name, content in files.items():
            path = site / 'examples' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        (site / 'index.html').write_text('<html><body><a href="examples/index.html">Examples</a></body></html>')
        (site / 'examples/index.html').write_text('<html><body>'+cards+'</body></html>')
        shutil.copyfile(ROOT / 'docs/examples/examples.css', site / 'examples/examples.css')
        book.build(site, figure_index_path=ROOT / "docs/examples/closed-loop/figure-index.json")
        inventory = finalizer.inventory(site)
        for route in ('examples/native-discrete-models.html', 'examples/native-quadcopter-mpc.html'):
            self.assertIn('scripts/reports/stage_native_discrete_models.py',
                          inventory['html_routes'][route]['producer']['files'])
        chapter = (site / 'learn/native-quadcopter-mpc.html').read_text()
        self.assertIn('../examples/native-quadcopter-mpc.html', chapter)
        self.assertIn('../examples/native-discrete-models-v1/phase-x3-x6-screen.svg', chapter)

    def test_rewritten_manifest_unlisted_file_and_symlink_are_rejected(self):
        manifest = self.bundle / 'manifest.json'
        original = manifest.read_bytes()
        manifest.write_bytes(original + b' ')
        with self.assertRaisesRegex(ValueError, 'frozen publication identity'):
            native.build(self.root)
        manifest.write_bytes(original)
        extra = self.bundle / 'unexpected.txt'
        extra.write_text('not captured')
        with self.assertRaisesRegex(ValueError, 'unlisted files'):
            native.build(self.root)
        extra.unlink()
        path = self.bundle / 'raw/plans.csv'
        target = self.root / 'outside.csv'
        path.rename(target)
        path.symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'symlinked'):
            native.build(self.root)

    def test_archive_rewrite_with_matching_checksum_is_rejected(self):
        import zipfile
        archive = self.bundle / (native.ROUTE + '.zip')
        with zipfile.ZipFile(archive, 'a') as stream:
            stream.writestr('invented.txt', b'not evidence')
        archive.with_suffix('.zip.sha256').write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+'  '+archive.name+'\n')
        with patch.object(native, 'ARCHIVE_SHA256', hashlib.sha256(archive.read_bytes()).hexdigest()):
            with self.assertRaisesRegex(ValueError, 'archive members differ'):
                native.build(self.root)

    def test_drawn_lines_are_all_saved_predictions_and_executed_values(self):
        import matplotlib.pyplot as plt
        subplots = plt.subplots
        figures = []
        def remember(*args, **kwargs):
            result = subplots(*args, **kwargs)
            figures.append(result)
            return result
        with patch.object(plt, 'subplots', side_effect=remember):
            assets = renderer.draw(self.bundle)
        _, _, plans = renderer.read_saved(self.bundle)
        actual = [p['observed'] for p in plans] + [plans[-1]['next']]
        self.assertEqual(len(figures), 8)
        self.assertEqual(len(assets), 16)
        for theme_offset in (0, 4):
            for offset, (a, b) in enumerate(((0, 1), (2, 5))):
                axis = figures[theme_offset+offset][1]
                self.assertEqual(len(axis.lines), 16)
                for r in range(15):
                    self.assertEqual(list(axis.lines[r].get_xdata()), [x[a] for x in plans[r]['states']])
                    self.assertEqual(list(axis.lines[r].get_ydata()), [x[b] for x in plans[r]['states']])
                self.assertEqual(list(axis.lines[-1].get_xdata()), [x[a] for x in actual])
                self.assertEqual(list(axis.lines[-1].get_ydata()), [x[b] for x in actual])
            axes = figures[theme_offset+2][1]
            for coordinate, axis in enumerate(axes.flat):
                self.assertEqual(len(axis.lines), 17)
                self.assertEqual(list(axis.lines[15].get_ydata()), [x[coordinate] for x in actual])
            for coordinate, axis in enumerate(figures[theme_offset+3][1].flat):
                self.assertEqual(len(axis.lines), 18)
                self.assertEqual(list(axis.lines[15].get_ydata())[:-1], [p['applied'][coordinate] for p in plans])
        for name, content in assets.items():
            self.assertEqual((self.bundle / name).read_bytes(), content, name)


if __name__ == '__main__':
    unittest.main()
