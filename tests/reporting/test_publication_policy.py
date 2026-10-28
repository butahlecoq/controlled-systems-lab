"""Publication policy owns a kind's staging identity and admission rules."""
import sys
import json
from pathlib import Path
import shutil
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "reports"))
import publication_policy
# Load the report site under a unique name; its imports register the concrete policies.
import importlib.util
SITE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "reports" / "site.py"
SITE_SPEC = importlib.util.spec_from_file_location("csl_publication_policy_site", SITE_PATH)
report_site = importlib.util.module_from_spec(SITE_SPEC)
SITE_SPEC.loader.exec_module(report_site)
FIXTURES = Path(__file__).resolve().parents[2] / "reports" / "algorithm-results"


class PublicationPolicyTests(unittest.TestCase):
    def test_only_supported_registered_kinds_resolve(self):
        self.assertEqual(
            publication_policy.registered_kinds(),
            {
                "b08-displayed-exact", "ext03-temporal-transform", "geo02-affine-sum", "geo03-hv",
                "geo04-intersection", "geo05-projection-predecessor", "geo06-quickhull",
                "issue3-finite-catalogue", "issue3-validated-minimax", "issue6-b06-reference",
                "issue6-b06-manifest-correction",
                "issue6-b07-reference", "issue6-b09-reference", "opt04-phase-one", "opt05-hull",
                "opt06-basis-reuse", "opt07-ordered-hull", "opt11-recursive-hull", "opt12-warm-start",
                "syn-ts01-paired-comparison", "syn01-nominal-forward", "syn02-terminal-minimizers",
                "syn03-strategy-a-ts01", "syn03-strategy-a-ts02", "syn04-strategy-b-ts01",
                "syn04-strategy-b-ts02", "syn04-strategy-b-ts03", "syn07-ts01-analytic",
            },
        )
        with self.assertRaisesRegex(ValueError, "unsupported registered publication kind"):
            publication_policy.for_kind("unknown-kind")

    def test_adapter_policy_rejects_wrong_source_identity(self):
        cases = (
            ("geo04-intersection", "geo04-20261012T224946Z-c37852bcc80d", "geo05-20261012T224946Z-c37852bcc80d"),
            ("geo05-projection-predecessor", "geo05-4dc3c0557570a52e", "geo04-4dc3c0557570a52e"),
            ("issue6-b09-reference", "b09-a08-source-reference-4818ddde", "b09-wrong-source"),
        )
        for kind, accepted, rejected in cases:
            with self.subTest(kind=kind):
                policy = publication_policy.for_kind(kind)
                self.assertTrue(policy.accepts_source_id(accepted))
                self.assertFalse(policy.accepts_source_id(rejected))

    def test_duplicate_kind_registration_fails_closed(self):
        policy = publication_policy.for_kind("geo04-intersection")
        with self.assertRaisesRegex(ValueError, "duplicate publication kind registration"):
            publication_policy.register(policy)

    def test_policy_retains_b09_archive_and_figure_admission_checks(self):
        policy = publication_policy.for_kind("issue6-b09-reference")
        self.assertTrue(policy.native_digest)
        self.assertEqual(policy.svg_files, ("projections-lambda0.svg", "projections-lambda1.svg"))
        self.assertTrue(policy.include_parent_archive)
        self.assertTrue(policy.committed_archive)

    def test_geo04_keeps_the_staging_svg_check(self):
        self.assertEqual(publication_policy.for_kind("geo04-intersection").svg_files,
                         ("latency.svg",))

    def test_issue3_policy_keeps_native_payload_digest_admission(self):
        self.assertTrue(publication_policy.for_kind("issue3-finite-catalogue").native_digest)

    def test_staging_rejects_wrong_source_identity_before_opening_bundle(self):
        catalogue = json.loads((FIXTURES / "catalog.json").read_text(encoding="utf-8"))
        row = next(row for row in catalogue["reports"] if row.get("report_kind") == "geo04-intersection")
        row["source_report_id"] = "../" + row["source_report_id"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copyfile(FIXTURES / "legacy-publications.json", root / "legacy-publications.json")
            catalog_path = root / "catalog.json"
            catalog_path.write_text(json.dumps({**catalogue, "reports": [row]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid registered source bundle identity"):
                report_site.stage(catalog_path, root / "site", check=False)

    def test_staging_rejects_unsupported_report_kind(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copyfile(FIXTURES / "legacy-publications.json", root / "legacy-publications.json")
            catalogue = {"schema": "csl.algorithm-report-catalog/3", "reports": [{
                "report_id": "unsupported-test", "report_kind": "unknown-kind"}]}
            catalog_path = root / "catalog.json"
            catalog_path.write_text(json.dumps(catalogue), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unknown catalogue kind"):
                report_site.stage(catalog_path, root / "site", check=False)

    def test_staging_rejects_schema_and_digest_mismatches_after_adapter_validation(self):
        catalogue = json.loads((FIXTURES / "catalog.json").read_text(encoding="utf-8"))
        original = next(row for row in catalogue["reports"]
                        if row.get("report_kind") == "geo05-projection-predecessor")
        source_id = original["source_report_id"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copyfile(FIXTURES / "legacy-publications.json", root / "legacy-publications.json")
            shutil.copytree(FIXTURES / source_id, root / source_id)
            shutil.copyfile(FIXTURES / (source_id + ".zip"), root / (source_id + ".zip"))
            for field, bad_value, message in (
                    ("payload_schema", "csl.unknown/1", "payload schema differs"),
                    ("payload_sha256", "0" * 64, "provenance mismatch")):
                row = {**original, field: bad_value}
                catalog_path = root / "catalog.json"
                catalog_path.write_text(json.dumps({**catalogue, "reports": [row]}), encoding="utf-8")
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, message):
                    report_site.stage(catalog_path, root / ("site-" + field), check=False)

    def test_staging_rejects_issue3_native_digest_mismatch(self):
        catalogue = json.loads((FIXTURES / "catalog.json").read_text(encoding="utf-8"))
        original = next(row for row in catalogue["reports"]
                        if row.get("report_kind") == "issue3-finite-catalogue")
        source_id = original["source_report_id"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copyfile(FIXTURES / "legacy-publications.json", root / "legacy-publications.json")
            shutil.copytree(FIXTURES / source_id, root / source_id)
            shutil.copyfile(FIXTURES / (original["report_id"] + ".zip"),
                            root / (original["report_id"] + ".zip"))
            row = {**original, "native_payload_sha256": "0" * 64}
            catalog_path = root / "catalog.json"
            catalog_path.write_text(json.dumps({**catalogue, "reports": [row]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "catalogue native digest differs"):
                report_site.stage(catalog_path, root / "site", check=False)


if __name__ == "__main__":
    unittest.main()
