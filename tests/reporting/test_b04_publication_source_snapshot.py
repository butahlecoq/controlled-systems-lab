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


def copy_sources(root: Path) -> None:
    for name in publication.SOURCE_FILES:
        if name in publication.FROZEN_SOURCE_HASHES:
            continue
        relative = Path(name)
        if name in publication.SNAPSHOT_FILES:
            relative = publication.SNAPSHOT_ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    for relative in (publication.SNAPSHOT_ROOT, publication.SPINE_SNAPSHOT_ROOT):
        shutil.copytree(ROOT / relative, root / relative, dirs_exist_ok=True)


class B04PublicationSourceSnapshotTests(unittest.TestCase):
    def test_publication_identity_and_zip_match_catalogue(self):
        catalogue = json.loads((ROOT / "reports/algorithm-results/catalog.json").read_text())
        row = next(row for row in catalogue["reports"] if row["report_kind"] == publication.KIND)
        adapted = publication.adapt(BUNDLE)
        self.assertEqual(adapted.report_id, row["report_id"])
        self.assertEqual(
            hashlib.sha256(publication.offline_zip(BUNDLE, adapted)).hexdigest(), row["zip_sha256"]
        )

    def test_rejects_tampered_snapshot_scientific_source_and_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / BUNDLE.name
            shutil.copytree(BUNDLE, bundle)
            copy_sources(root)
            with patch.object(publication, "ROOT", root):
                for relative in (
                    publication.SNAPSHOT_ROOT / "scripts/reports/site.py",
                    Path("docs/research/tools/check_b04_c_exact_fiber.py"),
                ):
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

    def test_live_spine_changes_preserve_the_original_publication_bytes(self):
        original = publication.adapt(BUNDLE)
        expected_archive = publication.offline_zip(BUNDLE, original)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copy_sources(root)
            with patch.object(publication, "ROOT", root):
                for name in publication.SPINE_SOURCE_FILES:
                    source = root / name
                    source.write_bytes(source.read_bytes() + b"\n")
                adapted = publication.adapt(BUNDLE)
                self.assertEqual(adapted, original)
                self.assertEqual(publication.offline_zip(BUNDLE, adapted), expected_archive)

    def test_rejects_tampered_missing_and_symlinked_spine_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copy_sources(root)
            source = root / publication.SPINE_SNAPSHOT_ROOT / "scripts/reports/report_data.py"
            raw = source.read_bytes()
            with patch.object(publication, "ROOT", root):
                source.write_bytes(raw + b"\n")
                with self.assertRaisesRegex(ValueError, "source file hash mismatch"):
                    publication.adapt(BUNDLE)
                source.unlink()
                with self.assertRaisesRegex(ValueError, "missing or unregistered files"):
                    publication.adapt(BUNDLE)
                outside = root / "outside.py"
                outside.write_bytes(raw)
                source.symlink_to(outside)
                with self.assertRaisesRegex(ValueError, "symlinks are forbidden"):
                    publication.adapt(BUNDLE)

    def test_rejects_unregistered_spine_member_and_changed_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copy_sources(root)
            snapshot = root / publication.SPINE_SNAPSHOT_ROOT
            extra = snapshot / "extra.py"
            with patch.object(publication, "ROOT", root):
                extra.write_text("value = 1\n", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "missing or unregistered files"):
                    publication.adapt(BUNDLE)
                extra.unlink()
                manifest = snapshot / "manifest.json"
                manifest.write_bytes(manifest.read_bytes() + b" ")
                with self.assertRaisesRegex(ValueError, "spine source manifest hash mismatch"):
                    publication.adapt(BUNDLE)

    def test_rejects_wrong_owner_even_with_a_matching_manifest_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copy_sources(root)
            manifest = root / publication.SPINE_SNAPSHOT_ROOT / "manifest.json"
            document = json.loads(manifest.read_bytes())
            for key, value in (
                ("owner_report_id", "another-report"),
                ("owner_manifest_sha256", "0" * 64),
            ):
                with self.subTest(field=key):
                    wrong = dict(document)
                    wrong[key] = value
                    raw = json.dumps(wrong).encode()
                    manifest.write_bytes(raw)
                    with (
                        patch.object(publication, "ROOT", root),
                        patch.object(
                            publication,
                            "SPINE_SNAPSHOT_MANIFEST_SHA256",
                            hashlib.sha256(raw).hexdigest(),
                        ),
                    ):
                        with self.assertRaisesRegex(ValueError, "source owner mismatch"):
                            publication.adapt(BUNDLE)

    def test_rejects_a_symlinked_source_owner_ancestor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            root.mkdir()
            copy_sources(root)
            outside = root.parent / "outside-docs"
            (root / "docs").rename(outside)
            (root / "docs").symlink_to(outside, target_is_directory=True)
            with patch.object(publication, "ROOT", root):
                with self.assertRaisesRegex(ValueError, "source directory is missing or unsafe"):
                    publication.adapt(BUNDLE)


if __name__ == "__main__":
    unittest.main()
