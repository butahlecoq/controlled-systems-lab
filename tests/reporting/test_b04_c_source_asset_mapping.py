import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "docs/research/tools"))
import finalize_b04_c_exact_fiber as finalize


class B04CSourceAssetMappingTests(unittest.TestCase):
    def test_text_source_keeps_the_frozen_markdown_publication_route(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            destination = Path(directory) / "published"
            source.mkdir()
            note = b"captured research evidence\n"
            (source / "README.txt").write_bytes(note)
            (source / "record.json").write_bytes(b"{}\n")

            self.assertEqual(finalize.evidence_source_path(source, "README.md"),
                             source / "README.txt")
            self.assertEqual(hashlib.sha256(
                finalize.evidence_source_path(source, "README.md").read_bytes()).digest(),
                hashlib.sha256(note).digest())

            finalize.copy_bundle_for_publication(source, destination)

            self.assertFalse((destination / "README.txt").exists())
            self.assertEqual((destination / "README.md").read_bytes(), note)
            self.assertEqual((destination / "record.json").read_bytes(), b"{}\n")


if __name__ == "__main__":
    unittest.main()
