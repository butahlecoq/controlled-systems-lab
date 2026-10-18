from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "algorithm-results"
sys.path.insert(0, str(ROOT / "scripts" / "reports"))

import opt12_registered_reports as publisher
import registered_reports
site_spec = importlib.util.spec_from_file_location("opt12_publication_site", ROOT / "scripts" / "reports" / "site.py")
report_site = importlib.util.module_from_spec(site_spec)
sys.modules[site_spec.name] = report_site
site_spec.loader.exec_module(report_site)


class Opt12PublicationTests(unittest.TestCase):
    def test_registered_bundle_stages_with_catalogued_immutable_identity(self):
        catalog = json.loads((REPORTS / "catalog.json").read_text(encoding="utf-8"))
        report = next(row for row in catalog["reports"] if row.get("report_kind") == publisher.KIND)
        bundle = REPORTS / report["source_report_id"]
        item = publisher.adapt(bundle)

        self.assertEqual(report["report_id"], item.report_id)
        self.assertEqual(report["source_report_id"], item.source_report_id)
        self.assertEqual(report["payload_sha256"], item.payload_sha256)
        self.assertEqual(report["native_payload_sha256"], item.native_payload_sha256)
        self.assertEqual(report["source_commit"], item.source_commit)
        self.assertEqual(report["measured_scope"], item.measured_scope)
        self.assertEqual(report["evidence_limits"], item.evidence_limits)

        artifacts = publisher.publication_artifacts(bundle, item)
        archive = publisher.offline_zip(bundle, item)
        self.assertEqual(report["zip_sha256"], hashlib.sha256(archive).hexdigest())
        expected = {"report_id": item.report_id, "report_kind": item.kind,
                    "payload_schema": item.payload_schema, "payload_sha256": item.payload_sha256,
                    "source_commit": item.source_commit, "measured_scope": item.measured_scope,
                    "evidence_limits": item.evidence_limits,
                    "native_payload_sha256": item.native_payload_sha256,
                    "source_report_id": item.source_report_id}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / item.report_id
            output.mkdir()
            for name, content in artifacts.items():
                destination = output / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
            self.assertTrue(registered_reports.validate_publication_manifest(output, expected))

        page_files = set(item.files) | {"report-envelope.json", "publication-manifest.json",
                                        "../" + item.report_id + ".zip"}
        report_site.OfflineHTML(page_files).feed(artifacts["index.html"].decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
