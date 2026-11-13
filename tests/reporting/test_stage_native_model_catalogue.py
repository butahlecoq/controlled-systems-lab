"""Frozen native records publish unchanged and reject altered or unsafe inputs."""
import hashlib
from html.parser import HTMLParser
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
import stage_native_model_catalogue as native


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        self.links.extend(value for name, value in attrs if name in {"href", "src"})


class NativePublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bundle = self.root / "reports/algorithm-results" / native.ROUTE
        shutil.copytree(ROOT / "reports/algorithm-results" / native.ROUTE, self.bundle)
        (self.root / "docs/examples").mkdir(parents=True)
        for page in ("native-model-catalogue.html", "native-four-state-reachability.html"):
            shutil.copyfile(ROOT / "docs/examples" / page, self.root / "docs/examples" / page)

    def test_publication_preserves_every_saved_byte_and_lesson_links(self):
        files, entries, cards = native.build(self.root)
        self.assertEqual(len(entries), 2)
        for path in self.bundle.rglob("*"):
            if path.is_file():
                self.assertEqual(files[native.ROUTE + "/" + path.relative_to(self.bundle).as_posix()],
                                 path.read_bytes())
        for entry in entries:
            self.assertIn('id="' + entry["anchor"] + '"', cards)
            links = Links()
            links.feed(files[entry["page"]].decode())
            for link in links.links:
                if ":" not in link and not link.startswith("#") and link not in {"index.html", "examples.css"}:
                    self.assertIn(link, files)
        self.assertEqual(native.build(self.root), (files, entries, cards))

    def test_modified_raw_capture_is_rejected(self):
        path = self.bundle / "four-state/full-state-generators.csv"
        path.write_bytes(path.read_bytes() + b"altered\n")
        with self.assertRaisesRegex(ValueError, "digest differs"):
            native.build(self.root)

    def test_rewritten_manifest_is_rejected(self):
        path = self.bundle / "manifest.json"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "frozen publication identity"):
            native.build(self.root)

    def test_rewritten_archive_with_matching_sidecar_is_rejected(self):
        path = self.bundle / (native.ROUTE + ".zip")
        with zipfile.ZipFile(path, "a") as archive:
            archive.writestr("unexpected.txt", "not a saved native output")
        path.with_suffix(".zip.sha256").write_text(
            hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name + "\n")
        with self.assertRaisesRegex(ValueError, "archive members differ"):
            native.build(self.root)

    def test_symlinked_capture_and_ancestor_are_rejected(self):
        path = self.bundle / "four-state/full-state-generators.csv"
        external = self.root / "external.csv"
        path.rename(external)
        path.symlink_to(external)
        with self.assertRaisesRegex(ValueError, "symlinked"):
            native.build(self.root)
        path.unlink()
        external.rename(path)
        moved = self.root / "moved"
        self.bundle.rename(moved)
        self.bundle.symlink_to(moved, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlinked"):
            native.build(self.root)


if __name__ == "__main__":
    unittest.main()
