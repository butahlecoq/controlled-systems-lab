"""Tests for reviewed mutable and order-only publication audit changes."""

import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.reports import audit_published_route_preservation as baseline_audit
from scripts.reports import preserve_published_routes as preservation


class PublishedRouteAuditPolicyTests(unittest.TestCase):
    def test_only_reviewed_learning_links_and_installed_list_order_are_mutable(self):
        learning_routes = ("learn/install-consumer.html", "learn/chapter-manifest.json")
        receipt = baseline_audit.ORDER_INSENSITIVE_RECEIPT_ROUTE
        package_a = {"metadata": {"name": "alpha", "version": "1.0"}, "requested": True}
        package_b = {"metadata": {"name": "beta", "version": "2.0"}, "requested": False}
        receipt_value = {
            "version": 1,
            "pip_version": "24.0",
            "environment": {"python_full_version": "3.11.14", "platform_system": "Linux"},
            "installed": [package_a, package_a, package_b],
        }
        payloads = {
            learning_routes[0]: b'<a href="source-at-6603">installed consumer</a>',
            learning_routes[1]: b'{"chapters":[{"href":"source-at-6603"}]}',
            receipt: json.dumps(receipt_value, sort_keys=True).encode(),
            "report/raw.json": b'{"cost": 1}',
            "report/raw.zip": b"saved archive",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            site, source = root / "site", root / "source"
            site.mkdir()
            source.mkdir()
            baseline = root / "baseline.tar"
            with tarfile.open(baseline, "w") as bundle:
                for name, data in payloads.items():
                    member = tarfile.TarInfo(name)
                    member.size = len(data)
                    bundle.addfile(member, io.BytesIO(data))
                    target = site / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
            manifest = json.loads((preservation.SOURCE / "manifest.json").read_text())
            manifest["baseline"]["artifact_tar_sha256"] = preservation.digest(baseline.read_bytes())
            (source / "manifest.json").write_text(json.dumps(manifest))
            self.assertEqual(
                set(manifest["order_insensitive_receipts_reviewed_separately"]), {receipt}
            )
            self.assertTrue(
                set(learning_routes) <= set(manifest["mutable_routes_reviewed_separately"])
            )

            (site / learning_routes[0]).write_bytes(
                b'<a href="source-at-main">installed consumer</a>'
            )
            (site / learning_routes[1]).write_bytes(b'{"chapters":[{"href":"source-at-main"}]}')
            reordered = json.loads(json.dumps(receipt_value))
            reordered["installed"] = [package_b, package_a, package_a]
            (site / receipt).write_text(json.dumps(reordered, sort_keys=True))

            with patch.object(baseline_audit, "SOURCE", source):
                result = baseline_audit.audit(baseline, site)
                self.assertTrue(result["passed"], result)
                self.assertEqual(set(result["reviewed_mutable_changes"]), set(learning_routes))
                self.assertIn(receipt, result["reviewed_receipt_order_changes"])

                rejecting_receipts = {
                    "package version": lambda value: value["installed"][0]["metadata"].__setitem__(
                        "version", "changed"
                    ),
                    "package metadata": lambda value: value["installed"][0]["metadata"].__setitem__(
                        "summary", "changed"
                    ),
                    "environment": lambda value: value["environment"].__setitem__(
                        "python_full_version", "3.12.0"
                    ),
                    "missing field": lambda value: value["installed"][0]["metadata"].pop("name"),
                    "missing installed inventory": lambda value: value.pop("installed"),
                    "added duplicate": lambda value: value["installed"].append(package_a),
                    "removed duplicate": lambda value: value["installed"].pop(),
                }
                for label, mutate in rejecting_receipts.items():
                    with self.subTest(receipt_change=label):
                        changed = json.loads(json.dumps(reordered))
                        mutate(changed)
                        (site / receipt).write_text(json.dumps(changed, sort_keys=True))
                        result = baseline_audit.audit(baseline, site)
                        self.assertFalse(result["passed"])
                        self.assertIn(receipt, result["unexpected_changed"])

                (site / receipt).write_text(json.dumps(reordered, sort_keys=True))
                (site / "report/raw.json").write_bytes(b'{"cost": 2}')
                result = baseline_audit.audit(baseline, site)
                self.assertFalse(result["passed"])
                self.assertIn("report/raw.json", result["unexpected_changed"])

                (site / "report/raw.json").write_bytes(payloads["report/raw.json"])
                (site / "report/raw.zip").write_bytes(b"changed saved archive")
                result = baseline_audit.audit(baseline, site)
                self.assertFalse(result["passed"])
                self.assertIn("report/raw.zip", result["changed_or_missing_zips"])

                (site / "report/raw.zip").unlink()
                result = baseline_audit.audit(baseline, site)
                self.assertFalse(result["passed"])
                self.assertIn("report/raw.zip", result["missing"])
                self.assertIn("report/raw.zip", result["changed_or_missing_zips"])

                (site / receipt).unlink()
                result = baseline_audit.audit(baseline, site)
                self.assertFalse(result["passed"])
                self.assertIn(receipt, result["missing"])


if __name__ == "__main__":
    unittest.main()
