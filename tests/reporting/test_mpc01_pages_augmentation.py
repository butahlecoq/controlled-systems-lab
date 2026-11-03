"""Adversarial checks for extraction of an upstream Pages tar artifact."""
from __future__ import annotations

import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/reports/mpc01/augment_pages.py"
SPEC = importlib.util.spec_from_file_location("mpc01_augment_pages", SCRIPT)
augment = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(augment)


def make_artifact(path: Path, members: list[tuple[tarfile.TarInfo, bytes | None]]) -> None:
    with tarfile.open(path, "w:") as archive:
        for info, content in members:
            archive.addfile(info, io.BytesIO(content) if content is not None else None)


def regular(name: str, content: bytes = b"ok") -> tuple[tarfile.TarInfo, bytes]:
    info = tarfile.TarInfo(name)
    info.size = len(content)
    info.mode = 0o644
    return info, content


class PagesArtifactExtractionTests(unittest.TestCase):
    def _extract(self, members):
        temporary = tempfile.TemporaryDirectory(prefix="mpc01-pages-tar-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        download = root / "download"
        download.mkdir()
        make_artifact(download / "artifact.tar", members)
        destination = root / "site"
        return augment.extract_pages_site(download, destination), root

    def test_extracts_regular_site_files_and_directories(self):
        site, _ = self._extract([
            (self._directory("./"), None),
            (regular("index.html", b"<html></html>")),
            (self._directory("examples/"), None),
            (regular("examples/index.html", b"<html>examples</html>")),
        ])
        self.assertEqual((site / "index.html").read_bytes(), b"<html></html>")
        self.assertEqual((site / "examples/index.html").read_bytes(), b"<html>examples</html>")

    @staticmethod
    def _directory(name: str) -> tarfile.TarInfo:
        info = tarfile.TarInfo(name)
        info.type = tarfile.DIRTYPE
        info.mode = 0o755
        return info

    def test_rejects_traversal_before_writing_outside_destination(self):
        temporary = tempfile.TemporaryDirectory(prefix="mpc01-pages-traversal-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        download = root / "download"
        download.mkdir()
        make_artifact(download / "artifact.tar", [regular("../escape", b"no")])
        destination = root / "site"
        with self.assertRaisesRegex(ValueError, "unsafe Pages artifact path"):
            augment.extract_pages_site(download, destination)
        self.assertFalse((root / "escape").exists())
        self.assertFalse(destination.exists())

    def test_rejects_absolute_paths_and_symlinks(self):
        absolute = tarfile.TarInfo("/tmp/escape")
        absolute.size = 1
        symlink = tarfile.TarInfo("link")
        symlink.type = tarfile.SYMTYPE
        symlink.linkname = "../escape"
        for member in ((absolute, b"x"), (symlink, None), regular(".", b"x")):
            with self.subTest(member=member[0].name):
                with self.assertRaises(ValueError):
                    self._extract([member])

    def test_rejects_hardlinks_duplicate_paths_and_file_parent_conflicts(self):
        hardlink = tarfile.TarInfo("link")
        hardlink.type = tarfile.LNKTYPE
        hardlink.linkname = "index.html"
        cases = (
            [regular("index.html"), (hardlink, None)],
            [regular("same"), regular("same")],
            [regular("child/file"), regular("child")],
        )
        for members in cases:
            with self.subTest(names=[item[0].name for item in members]):
                with self.assertRaises(ValueError):
                    self._extract(members)

    def test_rejects_malformed_download_layout_and_missing_root_index(self):
        with tempfile.TemporaryDirectory(prefix="mpc01-pages-layout-") as temporary:
            root = Path(temporary)
            download = root / "download"
            download.mkdir()
            (download / "other.tar").write_bytes(b"not accepted")
            with self.assertRaisesRegex(ValueError, "exactly one regular artifact.tar"):
                augment.extract_pages_site(download, root / "site")
        with self.assertRaisesRegex(ValueError, "no regular root index.html"):
            self._extract([regular("examples/index.html")])


if __name__ == "__main__":
    unittest.main()
