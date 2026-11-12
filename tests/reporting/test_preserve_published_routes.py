"""Regression checks for source-owned historical publication restoration."""
import io
import json
import stat
import zipfile
from unittest.mock import patch
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts.reports import preserve_published_routes as preservation


class PublishedRoutePreservationTests(unittest.TestCase):
    def test_original_routes_archives_and_repeat(self):
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            assets = preservation.payloads()
            self.assertEqual(preservation.stage(site)['preserved_routes'], 461)
            self.assertEqual({p.relative_to(site).as_posix(): p.read_bytes()
                              for p in site.rglob('*') if p.is_file()}, assets)
            self.assertEqual(preservation.stage(site)['preserved_routes'], 461)
            self.assertEqual(sum(n.endswith('.zip') for n in assets), 18)
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
