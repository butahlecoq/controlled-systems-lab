"""Frozen native flexible-pitch publication rejects altered and unsafe inputs."""
import hashlib
from html.parser import HTMLParser
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
import stage_native_flexible_pitch as native


class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.links = []

    def handle_starttag(self, tag, attrs):
        self.links.extend(value for name, value in attrs if name in {"href", "src"})


class FlexiblePitchPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bundle = self.root / "reports/algorithm-results" / native.ROUTE
        shutil.copytree(ROOT / "reports/algorithm-results" / native.ROUTE, self.bundle)
        (self.root / "docs/examples").mkdir(parents=True)
        shutil.copyfile(ROOT / "docs/examples/native-flexible-pitch.html",
                        self.root / "docs/examples/native-flexible-pitch.html")
        common = subprocess.check_output(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                                         cwd=ROOT, text=True).strip()
        # Read-only git-show validation in a copied fixture. No mutation uses it.
        (self.root / ".git").write_text("gitdir: " + common + "\n")

    def test_frozen_payloads_and_every_lesson_link_are_preserved(self):
        files, entries, card = native.build(self.root)
        self.assertEqual(len(entries), 1)
        self.assertIn('id="native-flexible-pitch"', card)
        for path in self.bundle.rglob("*"):
            if path.is_file():
                self.assertTrue(files[native.ROUTE + "/" + path.relative_to(self.bundle).as_posix()] == path.read_bytes(),
                                "staged payload bytes differ: " + path.relative_to(self.bundle).as_posix())
        links = Links(); links.feed(files["native-flexible-pitch.html"].decode())
        for link in links.links:
            if ":" not in link and not link.startswith("#") and link not in {"index.html", "examples.css", "native-model-catalogue.html"}:
                self.assertTrue(link in files, "missing staged lesson link: " + link)
        self.assertEqual(native.build(self.root), (files, entries, card))

    def test_changed_physical_generator_is_rejected(self):
        path = self.bundle / "16-state-generators.csv"
        path.write_bytes(path.read_bytes() + b"altered\n")
        with self.assertRaisesRegex(ValueError, "digest differs"):
            native.build(self.root)

    def test_rewritten_manifest_is_rejected(self):
        path = self.bundle / "manifest.json"; path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "frozen publication identity"):
            native.build(self.root)

    def test_repacked_archive_cannot_add_an_unlisted_file(self):
        path = self.bundle / (native.ROUTE + ".zip")
        with zipfile.ZipFile(path, "a") as archive:
            archive.writestr("unexpected.txt", "not native output")
        path.with_suffix(".zip.sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name + "\n")
        with self.assertRaisesRegex(ValueError, "frozen archive identity"):
            native.build(self.root)

    def test_same_payload_repack_with_matching_sidecar_is_rejected(self):
        path = self.bundle / (native.ROUTE + ".zip")
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        with zipfile.ZipFile(path) as archive:
            members = {name: archive.read(name) for name in archive.namelist()}
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
            for name, content in members.items():
                archive.writestr(name, content)
        after = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertNotEqual(before, after)
        path.with_suffix(".zip.sha256").write_text(after + "  " + path.name + "\n")
        with self.assertRaisesRegex(ValueError, "frozen archive identity"):
            native.build(self.root)

    def test_unlisted_and_symlinked_inputs_are_rejected(self):
        extra = self.bundle / "unexpected.txt"; extra.write_text("not native output")
        with self.assertRaisesRegex(ValueError, "unlisted files"):
            native.build(self.root)
        extra.unlink()
        path = self.bundle / "8-state-generators.csv"; moved = self.root / "external.csv"
        path.rename(moved); path.symlink_to(moved)
        with self.assertRaisesRegex(ValueError, "symlinked"):
            native.build(self.root)

    def test_checksum_sidecar_bytes_are_canonical(self):
        path = self.bundle / (native.ROUTE + ".zip.sha256")
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "checksum differs"):
            native.build(self.root)

    def test_capture_ancestor_must_be_available(self):
        (self.root / ".git").unlink()
        with self.assertRaisesRegex(ValueError, "full-history checkout"):
            native.build(self.root)


if __name__ == "__main__":
    unittest.main()
