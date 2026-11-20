"""Verify the disturbance lesson against the exact saved evidence archive."""

import hashlib
import json
import re
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/reports"))

import audit_mathematical_presentation as presentation
import audit_published_route_preservation as preservation_audit
import landing
import stage_catalogue_disturbance_control as stage

ROOT = Path(__file__).resolve().parents[2]


class CatalogueDisturbancePublicationTests(unittest.TestCase):
    def test_lesson_tables_and_figures_match_the_verified_archive(self) -> None:
        files, [entry], card = stage.build(ROOT)
        route = stage.IDENTITY.route
        with ZipFile(BytesIO(files[f"{route}/{route}.zip"])) as offline:
            html = offline.read("index.html").decode()
            for target in re.findall(r'(?:href|src)="([^"]+)"', html):
                ref = urlsplit(target)
                if not ref.scheme and ref.path:
                    self.assertIn(ref.path, offline.namelist())
        evidence = files[f"{route}/catalogue-disturbance-evidence.zip"]
        with ZipFile(BytesIO(evidence)) as archive:
            hashes = [
                line.split("  ", 1) for line in archive.read("SHA256SUMS").decode().splitlines()
            ]
            self.assertEqual(
                sorted(archive.namelist()), sorted([name for _, name in hashes] + ["SHA256SUMS"])
            )
            for digest, name in hashes:
                self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), digest, name)
            for name in (
                "puffer-robust-predecessor.svg",
                "ev-causal-minimax.svg",
                "minimax-audit.json",
            ):
                self.assertEqual(files[f"{route}/{name}"], archive.read(name))
            predecessors = json.loads(archive.read("robust-predecessors.json"))
            self.assertEqual(len(predecessors["results"]), 35)
            for profile, label in enumerate(("10%", "1%")):
                empty = [
                    sum(
                        model["profiles"][profile]["stages"][k]["status"] == "empty"
                        for model in predecessors["results"]
                    )
                    for k in range(3)
                ]
                cells = "".join(f"<td>{value}</td>" for value in empty)
                self.assertIn(f'<th scope="row">{label}</th>{cells}', html)
            audit = json.loads(archive.read("minimax-audit.json"))
            self.assertEqual(audit["checked_fixed_plans"], 315)
            self.assertEqual(audit["checked_second_decision_states"], 485)
            self.assertEqual(
                audit["strict_advantage"], ["catalogue-2026/model-6/1", "catalogue-2026/model-30/1"]
            )
            for row in audit["rows"]:
                if row["model_id"] in audit["strict_advantage"]:
                    self.assertIn(
                        f"<td>{row['fixed']:.11f}</td><td>{row['causal']:.11f}</td>", html
                    )
        for path in (entry["page"], entry["figure"], f"{route}/{route}.zip"):
            self.assertIn(path, files)
            self.assertIn(path, card)

    def test_book_and_archive_discover_the_lesson(self) -> None:
        files, [entry], _ = stage.build(ROOT)
        route = "examples/" + entry["page"]
        book = json.loads((ROOT / "docs/catalogue/learning-book-v1.json").read_bytes())
        [chapter] = [
            chapter
            for chapter in book["chapters"]
            if chapter["id"] == "native-model-tracking-first-pass"
        ]
        self.assertIn("../" + route, {record["href"] for record in chapter["records"]})
        preservation = json.loads(
            (ROOT / "reports/published-route-preservation/manifest.json").read_bytes()
        )
        [insertion] = [
            row
            for row in preservation["learning_navigation_insertions_reviewed_separately"]
            if row["chapter_id"] == chapter["id"]
        ]
        self.assertEqual(
            hashlib.sha256(preservation_audit._canonical_json(chapter).encode()).hexdigest(),
            insertion["chapter_sha256"],
        )
        registry = json.loads(presentation.REGISTRY.read_bytes())
        [record] = [record for record in registry["routes"] if record["route"] == route]
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            for path, content in files.items():
                target = site / "examples" / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            report = presentation.audit_site(site, {"routes": [record]})
            self.assertTrue(report["passed"], report["findings"])
            index = site / "index.html"
            index.write_text("<ul></ul>", encoding="utf-8")
            (site / "archive.html").touch()
            landing.build(site)
            [archive_entry], _ = landing.parse_index(index.read_text(encoding="utf-8"))
            self.assertEqual(archive_entry.commit, stage.IDENTITY.source_commit)
            self.assertEqual(len(archive_entry.links), 2)
            for _, path in archive_entry.links:
                self.assertTrue((site / path).is_file(), path)
