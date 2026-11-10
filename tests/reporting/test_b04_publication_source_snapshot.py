import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
import b04_c_exact_registered_reports as publication

BUNDLE = ROOT / "reports/algorithm-results/b04-c-exact-dyadic-v1"


class B04PublicationSourceSnapshotTests(unittest.TestCase):
    def test_publication_identity_and_zip_match_catalogue(self):
        catalogue = json.loads((ROOT / "reports/algorithm-results/catalog.json").read_text())
        row = next(row for row in catalogue["reports"] if row["report_kind"] == publication.KIND)
        adapted = publication.adapt(BUNDLE)
        self.assertEqual(adapted.report_id, row["report_id"])
        self.assertEqual(hashlib.sha256(publication.offline_zip(BUNDLE, adapted)).hexdigest(),
                         row["zip_sha256"])

    def test_rejects_tampered_snapshot_scientific_source_and_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / BUNDLE.name
            shutil.copytree(BUNDLE, bundle)
            for name in publication.SOURCE_FILES:
                relative = Path(name)
                if name in publication.SNAPSHOT_FILES:
                    relative = publication.SNAPSHOT_ROOT / relative
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, target)
            with patch.object(publication, "ROOT", root):
                for relative in (publication.SNAPSHOT_ROOT / "scripts/reports/site.py",
                                 Path("docs/research/tools/check_b04_c_exact_fiber.py")):
                    source = root / relative
                    original = source.read_bytes()
                    source.write_bytes(original + b"\n# tampered\n")
                    with self.subTest(source=str(relative)):
                        with self.assertRaisesRegex(ValueError, "source hash mismatch"):
                            publication.adapt(bundle)
                    source.write_bytes(original)
                manifest = bundle / "manifest.json"
                manifest.write_bytes(manifest.read_bytes() + b" ")
                with self.assertRaisesRegex(ValueError, "manifest hash mismatch"):
                    publication.adapt(bundle)


if __name__ == "__main__":
    unittest.main()
