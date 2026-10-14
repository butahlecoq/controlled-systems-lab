from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "algorithm-results"
SOURCE_ID = "syn-ts01-paired-20261014-b7f1ac0"
SOURCE = REPORTS / SOURCE_ID
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
import syn_ts01_paired_registered_reports as paired

SITE_SPEC = importlib.util.spec_from_file_location("syn_ts01_paired_test_site", ROOT / "scripts/reports/site.py")
assert SITE_SPEC is not None and SITE_SPEC.loader is not None
SITE = importlib.util.module_from_spec(SITE_SPEC)
SITE_SPEC.loader.exec_module(SITE)


class PairedTs01PublicationTests(unittest.TestCase):
    def catalogue_row(self):
        item = paired.adapt(SOURCE)
        archive = paired.offline_zip(SOURCE, item)
        row = {
            "report_id": item.report_id,
            "report_kind": item.kind,
            "source_report_id": item.source_report_id,
            "payload_schema": item.payload_schema,
            "payload_sha256": item.payload_sha256,
            "native_payload_sha256": item.native_payload_sha256,
            "source_commit": item.source_commit,
            "measured_scope": item.measured_scope,
            "evidence_limits": item.evidence_limits,
            "zip_sha256": hashlib.sha256(archive).hexdigest(),
        }
        return item, archive, row

    def test_versioned_bundle_is_catalogued_and_staged_from_exact_saved_bytes(self):
        item, archive, row = self.catalogue_row()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            shutil.copytree(SOURCE, root / SOURCE_ID)
            (root / (item.report_id + ".zip")).write_bytes(archive)
            catalogue = {"schema": "csl.algorithm-report-catalog/3", "artifact_ref": "main", "reports": [row]}
            catalog_path = root / "catalog.json"
            catalog_path.write_text(json.dumps(catalogue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            index = SITE.catalogue_index(catalogue)
            (root / "index.html").write_text(index, encoding="utf-8")

            with patch.object(SITE, "legacy_pins", return_value={}):
                staged = SITE.stage(catalog_path, root / "site", check=True)

            site_index = (staged / "index.html").read_text(encoding="utf-8")
            self.assertIn(item.report_id + "/index.html", site_index)
            self.assertIn(item.report_id + "/performance.svg", site_index)
            self.assertIn(item.report_id + ".zip", site_index)
            published = staged / item.report_id
            expected = paired.publication_artifacts(root / SOURCE_ID, item)
            for name, content in expected.items():
                self.assertEqual((published / name).read_bytes(), content, name)
            self.assertEqual((staged / (item.report_id + ".zip")).read_bytes(), archive)
            self.assertTrue(paired.validate_publication_manifest(published, row))

            with zipfile.ZipFile(staged / (item.report_id + ".zip")) as saved:
                self.assertEqual(saved.read(item.report_id + "/measurement-events.jsonl"), (SOURCE / "measurement-events.jsonl").read_bytes())
                self.assertEqual(saved.read(item.report_id + "/performance.svg"), (SOURCE / "performance.svg").read_bytes())

    def test_adapter_rejects_tampered_saved_trial_projection_even_when_manifest_is_resealed(self):
        with tempfile.TemporaryDirectory() as temp:
            bundle = Path(temp) / SOURCE_ID
            shutil.copytree(SOURCE, bundle)
            trials = bundle / "trials.csv"
            trials.write_bytes(trials.read_bytes().replace(b"5123800", b"5123801", 1))
            manifest_path = bundle / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"]["trials.csv"] = hashlib.sha256(trials.read_bytes()).hexdigest()
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "trial CSV differs"):
                paired.adapt(bundle)

    def test_publication_route_id_changes_with_a_resealed_bundle_file(self):
        original = paired.adapt(SOURCE)
        with tempfile.TemporaryDirectory() as temp:
            bundle = Path(temp) / SOURCE_ID
            shutil.copytree(SOURCE, bundle)
            readme = bundle / "README.md"
            readme.write_bytes(readme.read_bytes() + b"\nAdditional saved provenance note.\n")
            manifest_path = bundle / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"]["README.md"] = hashlib.sha256(readme.read_bytes()).hexdigest()
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
            changed = paired.adapt(bundle)
        self.assertEqual(changed.source_report_id, original.source_report_id)
        self.assertEqual(changed.payload_sha256, original.payload_sha256)
        self.assertNotEqual(changed.report_id, original.report_id)

    def test_catalogue_and_zip_are_bound_to_bundle_bytes(self):
        item, archive, row = self.catalogue_row()
        self.assertEqual(hashlib.sha256(archive).hexdigest(), row["zip_sha256"])
        catalogue = {"schema": "csl.algorithm-report-catalog/3", "artifact_ref": "main", "reports": [row]}
        links = SITE.catalogue_index(catalogue)
        self.assertIn(f'href="{item.report_id}/index.html"', links)
        self.assertIn(f'href="{item.report_id}/performance.svg"', links)
        self.assertIn(f'href="{item.report_id}.zip"', links)
        self.assertNotEqual(item.report_id, SOURCE_ID)

    def test_committed_catalogue_index_and_zip_match_the_publisher(self):
        item, archive, expected = self.catalogue_row()
        catalogue = json.loads((REPORTS / "catalog.json").read_text(encoding="utf-8"))
        rows = [row for row in catalogue["reports"] if row.get("source_report_id") == SOURCE_ID]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        for field in ("report_id", "report_kind", "source_report_id", "payload_schema", "payload_sha256",
                      "native_payload_sha256", "source_commit", "measured_scope", "evidence_limits", "zip_sha256"):
            self.assertEqual(row[field], expected[field], field)
        committed_zip = REPORTS / (item.report_id + ".zip")
        self.assertEqual(committed_zip.read_bytes(), archive)
        self.assertEqual(hashlib.sha256(committed_zip.read_bytes()).hexdigest(), row["zip_sha256"])
        self.assertEqual((REPORTS / "index.html").read_text(encoding="utf-8"), SITE.catalogue_index(catalogue))


if __name__ == "__main__":
    unittest.main()
