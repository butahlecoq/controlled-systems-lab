"""Behavioral checks against the saved, fixed-source SYN-06 verifier report."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
import stage_syn06 as syn06

_collector_spec = importlib.util.spec_from_file_location(
    "syn06_collector", ROOT / "reports/algorithm-results/tooling/syn06/collect.py")
collector = importlib.util.module_from_spec(_collector_spec)
_collector_spec.loader.exec_module(collector)

CATALOG = ROOT / "reports/algorithm-results/syn06-publications.json"


def source_bundle() -> Path:
    catalogue = json.loads(CATALOG.read_text(encoding="utf-8"))
    return CATALOG.parent / catalogue["reports"][0]["source_report_id"]


def rehash_native(bundle: Path) -> None:
    files = {name: (bundle / name).read_bytes() for name in syn06.SOURCE_FILES}
    manifest = {"schema": "csl.syn06-source-manifest/2", "report_id": bundle.name,
                "files": {name: syn06.digest_bytes(files[name]) for name in sorted(files)}}
    (bundle / "manifest.json").write_bytes(syn06.json_bytes(manifest))
    (bundle / "bundle.zip").write_bytes(syn06.registered.publication_zip(bundle.name,
        {**files, "manifest.json": (bundle / "manifest.json").read_bytes()}))


def rehash_record(bundle: Path, name: str, key: str, altered: bytes) -> None:
    (bundle / name).write_bytes(altered)
    record = json.loads((bundle / "records.json").read_text(encoding="utf-8"))
    record["payload"][key] = syn06.digest_bytes(altered)
    record["payload_sha256"] = syn06.digest(record["payload"])
    (bundle / "records.json").write_bytes(syn06.json_bytes(record))
    rehash_native(bundle)


class Syn06ReportTests(unittest.TestCase):
    def test_saved_bundle_and_public_zip_preserve_validated_evidence(self):
        source = source_bundle()
        expected = syn06.catalogue_entry(source)
        self.assertEqual(json.loads(CATALOG.read_text(encoding="utf-8"))["reports"], [expected])
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory) / "site"
            syn06.site.stage(CATALOG.parent / "catalog.json", site, check=True)
            old_paths = [path for path in site.rglob("*") if path.is_file() and path != site / "index.html"]
            old_bytes = {path.relative_to(site): hashlib.sha256(path.read_bytes()).hexdigest()
                         for path in old_paths}
            original_index = (site / "index.html").read_bytes()
            public_id = syn06.stage(CATALOG, site)
            self.assertEqual(public_id, expected["report_id"])
            self.assertNotEqual(original_index, (site / "index.html").read_bytes())
            self.assertIn(public_id + "/index.html", (site / "index.html").read_text(encoding="utf-8"))
            self.assertEqual(old_bytes, {relative: hashlib.sha256((site / relative).read_bytes()).hexdigest()
                                         for relative in old_bytes})
            public = site / public_id
            self.assertEqual((public / "raw-events.jsonl").read_bytes(), (source / "raw-events.jsonl").read_bytes())
            self.assertEqual((public / "index.html").read_bytes(), (source / "index.html").read_bytes())
            html = (public / "index.html").read_text(encoding="utf-8")
            self.assertIn("controls[1].inequalities[0]", html)
            self.assertIn("Optimality", html)
            self.assertIn("Checked calls", html)
            with zipfile.ZipFile(site / (public_id + ".zip")) as archive:
                self.assertEqual(archive.read(public_id + "/records.json"), (public / "records.json").read_bytes())
                self.assertEqual(archive.read(public_id + "/bundle.zip"), (source / "bundle.zip").read_bytes())

    def test_rehashed_contradictory_csv_cannot_be_published(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / source_bundle().name
            shutil.copytree(source_bundle(), bundle)
            path = bundle / "trials.csv"
            with path.open(encoding="utf-8", newline="") as stream:
                reader = csv.DictReader(stream)
                rows = list(reader)
                fields = reader.fieldnames
            rows[0]["checked_calls"] = str(int(rows[0]["checked_calls"]) - 1)
            path.write_bytes(syn06.csv_bytes(tuple(fields), rows))
            rehash_native(bundle)
            with self.assertRaisesRegex(ValueError, "CSV differs"):
                syn06.validate(bundle)

    def test_rehashed_failure_event_cannot_be_published(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / source_bundle().name
            shutil.copytree(source_bundle(), bundle)
            lines = (bundle / "raw-events.jsonl").read_text(encoding="utf-8").splitlines()
            event = json.loads(lines[1])
            event["failures"] = 1
            lines[1] = json.dumps(event)
            rehash_record(bundle, "raw-events.jsonl", "raw_sha256", ("\n".join(lines) + "\n").encode())
            with self.assertRaisesRegex(ValueError, "raw verifier result"):
                syn06.validate(bundle)

    def test_rehashed_named_residual_change_cannot_be_published(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / source_bundle().name
            shutil.copytree(source_bundle(), bundle)
            lines = (bundle / "raw-events.jsonl").read_text(encoding="utf-8").splitlines()
            event = json.loads(lines[1])
            event["residuals"][0]["violation"] = 0.125
            lines[1] = json.dumps(event)
            rehash_record(bundle, "raw-events.jsonl", "raw_sha256", ("\n".join(lines) + "\n").encode())
            with self.assertRaisesRegex(ValueError, "named residual"):
                syn06.validate(bundle)

    def test_rehashed_false_build_claim_cannot_be_published(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / source_bundle().name
            shutil.copytree(source_bundle(), bundle)
            build = json.loads((bundle / "build-provenance.json").read_text(encoding="utf-8"))
            build["clean_source_before_build"] = False
            rehash_record(bundle, "build-provenance.json", "build_sha256", syn06.json_bytes(build))
            with self.assertRaisesRegex(ValueError, "build provenance"):
                syn06.validate(bundle)

    def test_rehashed_private_path_cannot_be_published(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / source_bundle().name
            shutil.copytree(source_bundle(), bundle)
            log = (bundle / "build-log.txt").read_bytes() + b"C:\\Users\\private\\repo\n"
            rehash_record(bundle, "build-log.txt", "build_log_sha256", log)
            with self.assertRaisesRegex(ValueError, "private workspace path"):
                syn06.validate(bundle)

    def test_failed_process_journal_retains_partial_output(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = collector.Journal(Path(directory) / "evidence")
            command = [sys.executable, "-c",
                       "import sys; print('partial trial'); print('problem', file=sys.stderr); sys.exit(7)"]
            with self.assertRaisesRegex(collector.CollectionFailure, "exit code 7"):
                journal.capture("measurement", command)
            self.assertEqual((journal.path / "measurement.stdout").read_text().splitlines(), ["partial trial"])
            self.assertEqual((journal.path / "measurement.stderr").read_text().splitlines(), ["problem"])
            status = json.loads((journal.path / "status.json").read_text(encoding="utf-8"))
            self.assertEqual(status["status"], "failed")
            self.assertEqual(status["phases"][0]["return_code"], 7)
            self.assertEqual(status["phases"][0]["partial_output_lines"], 1)


if __name__ == "__main__":
    unittest.main()
