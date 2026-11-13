"""Exercise the locked source-only diagnostic and its independent saved-data checks."""

from __future__ import annotations

import csv
import hashlib
import importlib
import io
import json
import posixpath
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
native = importlib.import_module("stage_native_row_scaling_diagnostic")


class Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.paths: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.paths.extend(value for name, value in attrs if name in {"href", "src"} and value)


class RowScalingPublicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bundle = self.root / "reports/algorithm-results" / native.ROUTE
        shutil.copytree(ROOT / "reports/algorithm-results" / native.ROUTE, self.bundle)

    def run_checker(self, root: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-B",
                str(self.bundle / "source/check_evidence.py"),
                str(root or self.bundle),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_all_saved_assets_and_the_card_are_staged_without_rewriting(self) -> None:
        files, entries, card = native.build(self.root)
        expected = {
            native.ROUTE + "/" + path.relative_to(self.bundle).as_posix(): path.read_bytes()
            for path in self.bundle.rglob("*")
            if path.is_file()
        }
        self.assertEqual(files, expected)
        self.assertEqual(len(entries), 1)
        self.assertIn(entries[0]["figure"], files)
        self.assertIn(entries[0]["page"], files)
        self.assertIn('id="native-row-scaling-diagnostic"', card)
        self.assertIn("trivial zero-state", card)
        self.assertIn("numerical", card)

    def test_portable_check_replays_original_coordinates_and_keeps_failed_cases(self) -> None:
        result = self.run_checker()
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        completed = payload["models"][0]["original_coordinate_check"]
        self.assertEqual(completed["full_state_transitions"], 9)
        self.assertEqual(completed["state_dimension"], 8)
        self.assertTrue(completed["initial_state_zero"])
        self.assertEqual(completed["maximum_dynamics_residual"], 0)
        self.assertEqual(completed["maximum_objective_difference"], 0)
        self.assertEqual([row["completed_plan"] for row in payload["models"]], [True, False, False])
        self.assertEqual(payload["analytic_check"], "passed")

    def test_independent_checker_rejects_a_non_equivalent_scaled_coefficient(self) -> None:
        path = self.bundle / "records/attempts/model-23-row-scale-output/replan-0/csr.csv"
        rows = list(csv.DictReader(io.StringIO(path.read_text())))
        rows[0]["scaled"] = str(float(rows[0]["scaled"]) + 1)
        with path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        result = self.run_checker()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not exact positive row scaling", result.stderr)
        with self.assertRaisesRegex(ValueError, "digest differs"):
            native.build(self.root)

    def test_independent_checker_rejects_a_wrong_original_state_trajectory(self) -> None:
        path = self.bundle / "records/attempts/model-23-row-scale-output/trace.csv"
        rows = list(csv.DictReader(io.StringIO(path.read_text())))
        changed = False
        for row in rows:
            if (
                row["kind"] == "predicted_state"
                and row["stage"] == "1"
                and row["coordinate"] == "0"
            ):
                row["value"] = "1"
                changed = True
                break
        self.assertTrue(changed)
        with path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        result = self.run_checker()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("original full-state dynamics violated", result.stderr)

    def test_every_archive_member_is_source_data_or_figure_and_has_no_host_home_path(self) -> None:
        path = self.bundle / (native.ROUTE + ".zip")
        with zipfile.ZipFile(path) as archive:
            self.assertEqual(len(archive.namelist()), len(set(archive.namelist())))
            for name in archive.namelist():
                data = archive.read(name)
                with self.subTest(name=name):
                    self.assertFalse(data.startswith((b"\x7fELF", b"!<arch>\n", b"MZ")))
                    self.assertNotIn(
                        Path(name).suffix, {".a", ".o", ".so", ".dll", ".exe", ".pyc", ".md"}
                    )
                    self.assertNotIn(b"/home/", data)
            curation = json.loads(archive.read("records/curation.json"))
            self.assertEqual(curation["captured_file_count"], 93)
            self.assertEqual(curation["omitted_binary_count"], 2)
            self.assertEqual(len(curation["entries"]), 93)

    def test_unlisted_executable_and_missing_failure_log_are_rejected(self) -> None:
        extra = self.bundle / "unexpected-executable"
        extra.write_bytes(b"\x7fELF")
        with self.assertRaisesRegex(ValueError, "unlisted"):
            native.build(self.root)
        extra.unlink()
        log = self.bundle / "records/attempts/model-28-row-scale-output/native-replan-0.txt"
        log.unlink()
        with self.assertRaisesRegex(ValueError, "missing"):
            native.build(self.root)

    def test_repacked_archive_is_rejected_even_with_an_updated_checksum(self) -> None:
        path = self.bundle / (native.ROUTE + ".zip")
        with zipfile.ZipFile(path) as archive:
            payloads = [(name, archive.read(name)) for name in archive.namelist()]
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
            for name, data in payloads:
                archive.writestr(name, data)
        path.with_suffix(".zip.sha256").write_text(
            hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name + "\n"
        )
        with self.assertRaisesRegex(ValueError, "archive differs"):
            native.build(self.root)

    def test_future_site_css_does_not_regenerate_the_locked_zip(self) -> None:
        before = native.build(self.root)[0]
        style = self.root / "docs/examples/examples.css"
        style.parent.mkdir(parents=True)
        style.write_text("body { color: rebeccapurple; }")
        self.assertEqual(native.build(self.root)[0], before)

    def test_local_report_links_and_frozen_renderer_are_usable(self) -> None:
        files, _, _ = native.build(self.root)
        separate = "native-model-tracking-first-pass-v1/index.html"
        for page, content in files.items():
            if not page.endswith(".html"):
                continue
            parser = Links()
            parser.feed(content.decode())
            for reference in parser.paths:
                parts = urlsplit(reference)
                if parts.scheme or parts.netloc or not parts.path:
                    continue
                path = posixpath.normpath(posixpath.join(posixpath.dirname(page), parts.path))
                self.assertTrue(path in files or path == separate, path)
        result = subprocess.run(
            [sys.executable, "-B", str(self.bundle / "source/render_snapshot.py"), "--check"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
