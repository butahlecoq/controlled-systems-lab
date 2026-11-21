"""Verify that the gallery and archive expose the same frozen catalogue evidence."""

import importlib
import json
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
landing = importlib.import_module("landing")
presentation = importlib.import_module("audit_mathematical_presentation")
stage = importlib.import_module("stage_native_source_constrained_mpc")


class PageLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.local_paths: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name in {"href", "src"} and value:
                link = urlsplit(value)
                if not link.scheme and not link.netloc and link.path:
                    self.local_paths.append(link.path)


class CataloguePublicationTests(unittest.TestCase):
    def test_gallery_and_archive_link_all_saved_outcomes(self) -> None:
        files, [entry], gallery_card = stage.build(ROOT)
        self.assertIn(f'href="{entry["page"]}"', gallery_card)
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            for name, content in files.items():
                path = site / "examples" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            page = site / "examples" / entry["page"]
            parsed = PageLinks()
            parsed.feed(page.read_text(encoding="utf-8"))
            self.assertEqual(
                {path for path in parsed.local_paths if path.startswith("raw/")},
                {f"raw/{model}.json" for model in range(1, 36)},
            )
            for path in parsed.local_paths:
                self.assertTrue((page.parent / path).is_file(), path)
            registry = json.loads(presentation.REGISTRY.read_bytes())
            audit = presentation.audit_site(site, {"routes": registry["routes"]})
            self.assertTrue(audit["passed"], audit["findings"])
            index = site / "index.html"
            index.write_text("<ul></ul>", encoding="utf-8")
            (site / "archive.html").touch()
            landing.build(site)
            [report], _ = landing.parse_index(index.read_text(encoding="utf-8"))
            self.assertEqual(report.report_id + "/index.html", "examples/" + entry["page"])
            self.assertEqual(report.commit, stage.IDENTITY.source_commit)
            for _, relative in report.links:
                self.assertTrue((site / relative).is_file(), relative)


class ConvexBackendPublicationTests(unittest.TestCase):
    def test_comparison_matches_independent_policy_audits(self) -> None:
        original, _, _ = stage.build(ROOT)
        files, [entry], _ = stage.build_convex_backends(ROOT)
        route = entry["anchor"]

        def evidence(name: str) -> ZipFile:
            return ZipFile(BytesIO(files[f"{route}/{name}"]))

        with (
            evidence("catalogue-row-scaled-highs-evidence.zip") as scaled,
            evidence("catalogue-installed-ipopt-evidence.zip") as installed,
            evidence("catalogue-ipopt-source-qp-evidence.zip") as probe,
        ):
            audits = (
                json.loads(original[f"{stage.IDENTITY.route}/independent-audit.json"]),
                json.loads(scaled.read("raw/independent-audit.json")),
                json.loads(installed.read("raw/independent-audit.json")),
            )
            self.assertEqual(
                files[f"{route}/bicycle-row-scaling.svg"], scaled.read("bicycle-row-scaling.svg")
            )
            self.assertEqual(
                files[f"{route}/twenty-zone-ipopt.svg"], probe.read("twenty-zone-ipopt.svg")
            )
            self.assertEqual(
                json.loads(installed.read("comparison.json"))["matched_scratch_policy_records"], 70
            )
            self.assertEqual(
                files[entry["raw_record"]], installed.read("raw/independent-audit.json")
            )
            kkt = json.loads(probe.read("full-kkt-audit.json"))

        provider_labels = (
            "Released HiGHS 1.11.0",
            "HiGHS with bounded row scaling",
            "Installed Ipopt 3.14.19",
        )
        page = files[f"{route}/index.html"].decode()
        completions = []
        for label, audit in zip(provider_labels, audits, strict=True):
            self.assertEqual(audit["literal_matrix_entries_checked"], 25380)
            self.assertEqual({row["number"] for row in audit["rows"]}, set(range(1, 36)))
            opened = {
                row["number"] for row in audit["rows"] if row["open_loop"]["status"] == "complete"
            }
            closed = {
                row["number"] for row in audit["rows"] if row["closed_loop"]["status"] == "complete"
            }
            pairs = opened & closed
            counts = "".join(
                f"<td>{count}</td>" for count in (len(opened), len(closed), len(pairs))
            )
            self.assertIn(f'<tr><th scope="row">{label}</th>{counts}</tr>', page)
            completions.append((opened, closed))

        released, row_scaled, ipopt = completions
        self.assertEqual(row_scaled[0] - released[0], {23})
        self.assertEqual(row_scaled[1] - released[1], {23})
        self.assertEqual(ipopt[0] - released[0], {23, 27, 28})
        self.assertEqual(ipopt[1] - released[1], {23, 27, 28, 30})
        self.assertEqual(set(range(1, 36)) - (ipopt[0] & ipopt[1]), {9})
        self.assertEqual(sum(row["accepted"] for row in kkt.values()), 136)
        self.assertEqual(kkt["9"], {"attempts": 2, "accepted": 0, "statuses": [2, 2]})

    def test_companion_links_resolve_and_publish_with_the_original(self) -> None:
        original, [baseline], _ = stage.build(ROOT)
        files, [entry], card = stage.build_convex_backends(ROOT)
        self.assertIn(f'href="{entry["page"]}"', card)
        self.assertIn(entry["raw_record"], files)
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            for name, content in (original | files).items():
                path = site / "examples" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            page = site / "examples" / entry["page"]
            parsed = PageLinks()
            parsed.feed(page.read_text(encoding="utf-8"))
            for path in parsed.local_paths:
                self.assertTrue((page.parent / path).is_file(), path)
            registry = json.loads(presentation.REGISTRY.read_bytes())
            audit = presentation.audit_site(site, {"routes": registry["routes"]})
            self.assertTrue(audit["passed"], audit["findings"])
            index = site / "index.html"
            index.write_text("<ul></ul>", encoding="utf-8")
            (site / "archive.html").touch()
            landing.build(site)
            reports, _ = landing.parse_index(index.read_text(encoding="utf-8"))
            self.assertEqual(
                {report.report_id + "/index.html" for report in reports},
                {"examples/" + baseline["page"], "examples/" + entry["page"]},
            )
            for report in reports:
                for _, relative in report.links:
                    self.assertTrue((site / relative).is_file(), relative)

    def test_download_contains_its_baseline_and_local_links(self) -> None:
        original, _, _ = stage.build(ROOT)
        files, [entry], _ = stage.build_convex_backends(ROOT)
        route = entry["anchor"]
        baseline_name = stage.IDENTITY.route + ".zip"
        with (
            tempfile.TemporaryDirectory() as directory,
            ZipFile(BytesIO(files[f"{route}/{route}.zip"])) as archive,
        ):
            package = Path(directory)
            archive.extractall(package)
            parsed = PageLinks()
            parsed.feed((package / "index.html").read_text(encoding="utf-8"))
            self.assertIn(baseline_name, parsed.local_paths)
            for path in parsed.local_paths:
                self.assertTrue((package / path).is_file(), path)
            self.assertEqual(
                (package / baseline_name).read_bytes(),
                original[f"{stage.IDENTITY.route}/{baseline_name}"],
            )
