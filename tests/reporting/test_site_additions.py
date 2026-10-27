from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

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


if __name__ == "__main__":
    unittest.main()
