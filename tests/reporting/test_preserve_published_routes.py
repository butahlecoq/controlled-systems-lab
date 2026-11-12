"""Regression checks for source-owned historical publication restoration."""
import io
import json
import stat
import tarfile
import zipfile
from unittest.mock import patch
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts.reports import preserve_published_routes as preservation
from scripts.reports import audit_published_route_preservation as baseline_audit


class PublishedRoutePreservationTests(unittest.TestCase):
    def test_baseline_audit_distinguishes_indexes_from_frozen_evidence(self):
        indexes = ('examples/visual-route-inventory.json', 'examples/visual-coverage.json',
                   'examples/closed-loop/figure-index.json', 'examples/algorithm-coverage.json')
        payloads = {name: b'{"entries": []}' for name in indexes}
        payloads.update({'report/raw.json': b'{"cost": 1}', 'report/raw.zip': b'saved archive',
                         'pages-mpc11-environment.json': b'{"python": "qualified"}'})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            site, source = root / 'site', root / 'source'
            site.mkdir()
            source.mkdir()
            baseline = root / 'baseline.tar'
            with tarfile.open(baseline, 'w') as bundle:
                for name, data in payloads.items():
                    member = tarfile.TarInfo(name)
                    member.size = len(data)
                    bundle.addfile(member, io.BytesIO(data))
                    target = site / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
            manifest = json.loads((preservation.SOURCE / 'manifest.json').read_text())
            manifest['baseline']['artifact_tar_sha256'] = preservation.digest(baseline.read_bytes())
            (source / 'manifest.json').write_text(json.dumps(manifest))
            for name in indexes:
                (site / name).write_bytes(b'{"entries": ["new illustration"]}')
            with patch.object(baseline_audit, 'SOURCE', source):
                self.assertTrue(baseline_audit.audit(baseline, site)['passed'])
                for name, field in (('report/raw.json', 'unexpected_changed'),
                                    ('report/raw.zip', 'changed_or_missing_zips')):
                    with self.subTest(name=name):
                        (site / name).write_bytes(b'altered scientific evidence')
                        result = baseline_audit.audit(baseline, site)
                        self.assertFalse(result['passed'])
                        self.assertIn(name, result[field])
                        (site / name).write_bytes(payloads[name])
                receipt = 'pages-mpc11-environment.json'
                (site / receipt).unlink()
                result = baseline_audit.audit(baseline, site)
                self.assertFalse(result['passed'])
                self.assertEqual(result['missing'], [receipt])

    def test_historical_helper_predecessors_survive_on_a_fresh_site(self):
        predecessors = {
            'b04-source-moments-11fb3cd7d83f868d3c3d':
                '509c9293a4b23e3e16024f702a377b685bfb654b40dd3d74a5334e29f3790db1',
            'mpc11-controller-comparison-cc50fc8473b24ee929ac':
                '14a7f042fb3fb4ffb3268f55a7ff3f0b3436fcf9a1a59e51aa65106955a9ae3c',
        }
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            preservation.stage(site)
            for route, expected in predecessors.items():
                with self.subTest(route=route):
                    archive = site / (route + '.zip')
                    self.assertTrue(archive.is_file())
                    self.assertEqual(preservation.digest(archive.read_bytes()), expected)
                    with zipfile.ZipFile(archive) as bundle:
                        for name in bundle.namelist():
                            self.assertEqual((site / name).read_bytes(), bundle.read(name))

    def test_original_routes_archives_and_repeat(self):
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            assets = preservation.payloads()
            self.assertEqual(preservation.stage(site)['preserved_routes'], 570)
            self.assertEqual({p.relative_to(site).as_posix(): p.read_bytes()
                              for p in site.rglob('*') if p.is_file()}, assets)
            self.assertEqual(preservation.stage(site)['preserved_routes'], 570)
            self.assertEqual(preservation.stage(site)['preserved_top_level_zips'], 5)
            self.assertEqual(sum(n.endswith('.zip') for n in assets), 28)
            self.assertFalse(any('.git' in Path(n).parts for n in assets))

    def test_tampered_archive_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source'
            shutil.copytree(preservation.SOURCE, source)
            archive = next(source.glob('*.zip'))
            archive.write_bytes(archive.read_bytes() + b'corrupt')
            site = root / 'site'
            site.mkdir()
            with self.assertRaisesRegex(ValueError, 'hash/size'):
                preservation.stage(site, source)
            self.assertEqual(list(site.iterdir()), [])

    def test_existing_frozen_copy_tamper_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            preservation.stage(site)
            route = next(n for n in preservation.payloads() if n.endswith('index.html'))
            (site / route).write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError, 'conflicting preserved route'):
                preservation.stage(site)
            self.assertEqual((site / route).read_bytes(), b'tampered')

    def test_symlink_boundary_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            site, outside = root / 'site', root / 'outside'
            site.mkdir()
            outside.mkdir()
            (site / 'docs').symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'symlink'):
                preservation.stage(site)
            self.assertEqual(list(outside.iterdir()), [])
            self.assertEqual(len(list(site.iterdir())), 1)

    def test_only_known_migrated_checksum_alias_can_be_replaced(self):
        manifest = json.loads((preservation.SOURCE / 'manifest.json').read_text())
        alias = next(a for a in manifest['aliases'] if 'replaces_sha256' in a)
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            path = site / alias['route']
            path.parent.mkdir(parents=True)
            path.write_bytes(b'unreviewed checksum inventory')
            with self.assertRaisesRegex(ValueError, 'conflicting preserved route'):
                preservation.stage(site)

    def test_zip_member_symlink_and_quota(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            info = zipfile.ZipInfo('old/member')
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            data = io.BytesIO()
            with zipfile.ZipFile(data, 'w') as bundle:
                bundle.writestr(info, b'outside')
            content = data.getvalue()
            (source / 'old.zip').write_bytes(content)
            manifest = {'schema': 'csl.published-route-preservation/1', 'aliases': [],
                        'archives': [{'path': 'old.zip', 'size': len(content),
                                      'sha256': preservation.digest(content),
                                      'members': {'old/member': {'size': 7,
                                                  'sha256': preservation.digest(b'outside'),
                                                  'publish': True}}}]}
            (source / 'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'unsafe preserved ZIP member'):
                preservation.payloads(source)
            with patch.object(preservation, 'MAX_EXPANDED', 1):
                with self.assertRaisesRegex(ValueError, 'inventory/quota'):
                    preservation.payloads(source)

    def test_unsafe_member_paths(self):
        for name in ('.', '../escape', '/absolute', 'a/../escape', 'a//b', 'a\\b', './a'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                preservation.safe(name)


if __name__ == '__main__':
    unittest.main()
