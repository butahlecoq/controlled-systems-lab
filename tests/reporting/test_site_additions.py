from __future__ import annotations

import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
import site_additions


class SiteAdditionsTests(unittest.TestCase):
    def test_rejects_colliding_file_and_parent_paths_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary) / "site"
            site.mkdir()
            with self.assertRaisesRegex(ValueError, "parent directory"):
                site_additions.prepare(site, {"Reports": b"file", "reports/index.html": b"page"})
            self.assertEqual(list(site.iterdir()), [])

    def test_rechecks_replacement_fingerprint_before_first_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary)
            index = site / "index.html"
            index.write_bytes(b"original")
            plan = site_additions.prepare(site, {"route.html": b"route", "index.html": b"new"},
                                          replace_existing={"index.html"})
            index.write_bytes(b"concurrent change")
            with self.assertRaisesRegex(ValueError, "changed after preparation"):
                site_additions.commit(plan)
            self.assertEqual(index.read_bytes(), b"concurrent change")
            self.assertFalse((site / "route.html").exists())

    def test_commit_writes_nested_index_before_site_index(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary)
            writes = []
            plan = site_additions.prepare(site, {
                "index.html": b"site",
                "reports/index.html": b"nested",
                "reports/data.json": b"data",
            })

            def writer(path: Path, content: bytes) -> None:
                writes.append(path.relative_to(site).as_posix())
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)

            site_additions.commit(plan, writer=writer)
            self.assertEqual(writes[-2:], ["reports/index.html", "index.html"])

    def test_failed_site_index_replace_preserves_existing_index(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary)
            index = site / "index.html"
            index.write_bytes(b"original")
            plan = site_additions.prepare(site, {"route.html": b"route", "index.html": b"updated"},
                                          replace_existing={"index.html"})
            replace = site_additions.os.replace

            def fail_index_replace(source: Path, destination: Path) -> None:
                if destination == index:
                    raise OSError("injected final replace failure")
                replace(source, destination)

            with patch.object(site_additions.os, "replace", side_effect=fail_index_replace):
                with self.assertRaisesRegex(OSError, "final replace failure"):
                    site_additions.commit(plan)
            self.assertEqual(index.read_bytes(), b"original")
            self.assertEqual((site / "route.html").read_bytes(), b"route")
            self.assertEqual({path.name for path in site.iterdir()}, {"index.html", "route.html"})

    @unittest.skipUnless(os.name == "posix", "POSIX file mode semantics")
    def test_replacement_preserves_existing_mode_and_new_routes_are_public_readable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary)
            index = site / "index.html"
            index.write_bytes(b"original")
            index.chmod(0o640)
            plan = site_additions.prepare(site, {"route.html": b"route", "index.html": b"updated"},
                                          replace_existing={"index.html"})
            site_additions.commit(plan)
            self.assertEqual(stat.S_IMODE(index.stat().st_mode), 0o640)
            self.assertEqual(stat.S_IMODE((site / "route.html").stat().st_mode), 0o644)


if __name__ == "__main__":
    unittest.main()
