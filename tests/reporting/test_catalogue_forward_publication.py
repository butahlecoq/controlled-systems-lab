"""Check that the catalogue forward sweep reaches readers with its frozen evidence."""

import hashlib
import importlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
landing = importlib.import_module("landing")
stage = importlib.import_module("stage_catalogue_forward_reachability")
presentation = importlib.import_module("audit_mathematical_presentation")


class CatalogueForwardPublicationTests(unittest.TestCase):
    def test_gallery_book_and_archive_link_the_verified_capture(self) -> None:
        files, [entry], gallery_card = stage.build(ROOT)
        route = stage.IDENTITY.route
        page = entry["page"]
        for name in (page, entry["figure"], entry["raw_record"], f"{route}/{route}.zip"):
            self.assertIn(name, files)
            if name != entry["raw_record"]:
                self.assertIn(name, gallery_card)
        result = json.loads(files[f"{route}/support-audit.json"])
        self.assertEqual(result["models"], 35)
        self.assertEqual(result["model_stages"], 140)
        self.assertEqual(result["support_checks"], 7592)
        self.assertLess(result["max_scaled_support_error"], result["scaled_tolerance"])
        book = json.loads((ROOT / "docs/catalogue/learning-book-v1.json").read_bytes())
        [chapter] = [
            chapter for chapter in book["chapters"] if chapter["id"] == "native-forward-models"
        ]
        self.assertIn("../examples/" + page, {item["href"] for item in chapter["records"]})

        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            for name, content in files.items():
                path = site / "examples" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            ledger = json.loads(presentation.REGISTRY.read_bytes())
            [record] = [item for item in ledger["routes"] if item["route"] == "examples/" + page]
            audit = presentation.audit_site(site, {"routes": [record]})
            self.assertTrue(audit["passed"], audit["findings"])
            index = site / "index.html"
            index.write_text("<ul></ul>", encoding="utf-8")
            (site / "archive.html").touch()
            landing.build(site)
            [card], _ = landing.parse_index(index.read_text(encoding="utf-8"))
            self.assertEqual(card.report_id + "/index.html", "examples/" + page)
            self.assertEqual(card.commit, stage.IDENTITY.source_commit)
            self.assertIn("authored", card.scope)
            for _, path in card.links:
                self.assertTrue((site / path).is_file(), path)

    def test_feasible_history_stages_original_data_and_battery_projection(self) -> None:
        files, [entry], card = stage.build_feasible_history(ROOT)
        route = stage.FEASIBLE_HISTORY.route
        original = route + "/catalogue-feasible-history-evidence.zip"
        for path in (entry["page"], entry["figure"], original):
            self.assertIn(path, files)
            self.assertIn(path, card)
        with ZipFile(BytesIO(files[original])) as archive:
            summary = json.loads(archive.read("comparison-summary.json"))
            audit = json.loads(archive.read("independent-audit.json"))
            self.assertEqual(
                files[entry["figure"]], archive.read("battery-history-projections.svg")
            )
        self.assertEqual(len(audit), 35)
        self.assertEqual(
            summary["native"],
            {
                "full_history": {
                    "optimal": 991,
                    "infeasible": 32,
                    "unsupported": 96,
                    "undetermined": 1,
                },
                "intervals_only": {"optimal": 976, "unbounded": 48, "unsupported": 96},
            },
        )
        battery = audit["5"]
        supports = {}
        for profile in ("full_history", "intervals_only"):
            [sample] = [
                row
                for row in battery[profile]["samples"]
                if row["stage"] == 3 and row["direction"] == [-1, -1]
            ]
            supports[profile] = sample["native_support"]
        self.assertAlmostEqual(supports["intervals_only"] - supports["full_history"], 60.986)
        book = json.loads((ROOT / "docs/catalogue/learning-book-v1.json").read_bytes())
        [chapter] = [item for item in book["chapters"] if item["id"] == "native-forward-models"]
        self.assertIn("../examples/" + entry["page"], {item["href"] for item in chapter["records"]})
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            for name, content in files.items():
                path = site / "examples" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            ledger = json.loads(presentation.REGISTRY.read_bytes())
            page = "examples/" + entry["page"]
            audited_pages = {page, f"examples/{stage.RING_INITIAL_SUPPORT}/index.html"}
            records = [item for item in ledger["routes"] if item["route"] in audited_pages]
            presentation_audit = presentation.audit_site(site, {"routes": records})
            self.assertTrue(presentation_audit["passed"], presentation_audit["findings"])
            index = site / "index.html"
            index.write_text("<ul></ul>", encoding="utf-8")
            (site / "archive.html").touch()
            landing.build(site)
            [archive_entry], _ = landing.parse_index(index.read_text(encoding="utf-8"))
            self.assertEqual(archive_entry.report_id + "/index.html", page)
            self.assertEqual(archive_entry.commit, stage.FEASIBLE_HISTORY.source_commit)
            for _, path in archive_entry.links:
                self.assertTrue((site / path).is_file(), path)

    def test_ring_certificate_replays_from_the_offline_companion(self) -> None:
        files, _, card = stage.build_feasible_history(ROOT)
        route = stage.RING_INITIAL_SUPPORT
        archive_path = f"{route}/{route}.zip"
        self.assertIn(archive_path, card)
        self.assertIn(f"{route}/index.html", card)
        original = stage.HISTORY_EVIDENCE
        self.assertEqual(
            files[f"{route}/{original}"], files[f"{stage.FEASIBLE_HISTORY.route}/{original}"]
        )
        with (
            ZipFile(BytesIO(files[archive_path])) as archive,
            tempfile.TemporaryDirectory() as directory,
        ):
            names = {
                path.removeprefix(f"{route}/") for path in files if path.startswith(f"{route}/")
            }
            self.assertEqual(set(archive.namelist()), names - {f"{route}.zip"})
            for name in archive.namelist():
                self.assertEqual(archive.read(name), files[f"{route}/{name}"])
            archive.extractall(directory)
            saved = Path(directory)
            replay = subprocess.check_output([sys.executable, "verify_support.py"], cwd=saved)
            self.assertEqual(replay, archive.read("certificate.json"))
            result = json.loads(replay)
            self.assertEqual(result["native_status"], "undetermined")
            self.assertEqual(result["certificate_status"], "exact-optimal")
            self.assertEqual(result["support"], "13914569883186085/72057594037927936")
            page = (saved / "index.html").read_text(encoding="utf-8")
            self.assertEqual(presentation.inspect_html(page), [])
            for asset in (
                "examples.css",
                "verify_support.py",
                "certificate.json",
                original,
                "initial-support.svg",
                "plot_support.py",
                "manifest.json",
            ):
                self.assertIn(f'="{asset}"', page)
                self.assertTrue((saved / asset).is_file())
            (saved / original).write_bytes(b"invalid archive")
            rejected = subprocess.run(
                [sys.executable, "verify_support.py"], cwd=saved, capture_output=True, check=False
            )
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn(b"Unexpected input archive SHA-256", rejected.stderr)

    def test_ring_stager_rejects_a_modified_figure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory)
            relative = Path("reports/algorithm-results")
            for route in (stage.FEASIBLE_HISTORY.route, stage.RING_INITIAL_SUPPORT):
                shutil.copytree(ROOT / relative / route, fixture / relative / route)
            (fixture / relative / stage.RING_INITIAL_SUPPORT / "initial-support.svg").write_bytes(
                b"<svg/>"
            )
            with self.assertRaisesRegex(ValueError, "asset digest differs: initial-support.svg"):
                stage.build_feasible_history(fixture)

    def test_exact_support_keeps_the_refusals_and_primal_dual_certificates(self) -> None:
        files, [entry], card = stage.build_exact_support(ROOT)
        route = stage.EXACT_SUPPORT.route
        original = route + "/catalogue-exact-support-evidence.zip"
        for path in (entry["page"], entry["figure"], original):
            self.assertIn(path, files)
            self.assertIn(path, card)
        with ZipFile(BytesIO(files[original])) as archive:
            self.assertEqual(files[entry["figure"]], archive.read("building-budget-projection.svg"))
            self.assertEqual(files[f"{route}/exact_support.cpp"], archive.read("exact_support.cpp"))
            audit = json.loads(archive.read("independent-exact-audit.json"))
            self.assertEqual(set(audit), {"23", "27", "28"})
            for model, strict in (("23", 0), ("27", 0), ("28", 12)):
                input_data = json.loads(archive.read(f"input/raw/{model}.json"))
                certificates = json.loads(archive.read(f"results/{model}.json"))
                self.assertEqual(audit[model]["budget_effect"]["strict_support_reductions"], strict)
                for profile in ("full_history", "intervals_only"):
                    self.assertEqual(audit[model][profile]["statuses"], {"exact-optimal": 32})
                    self.assertEqual(len(certificates[profile]), 32)
                    for original_row, row in zip(
                        input_data[profile]["samples"], certificates[profile], strict=True
                    ):
                        self.assertEqual(row["stage"], original_row["stage"])
                        self.assertEqual(row["direction"], original_row["direction"])
                        self.assertEqual(original_row["status"], "unsupported")
                        self.assertEqual(row["prior_native_status"], original_row["status"])
                        self.assertEqual(row["status"], "exact-optimal")
            self.assertAlmostEqual(
                audit["28"]["budget_effect"]["max_support_reduction_decimal"] * 1e13,
                1.2697696340859817,
            )
        book = json.loads((ROOT / "docs/catalogue/learning-book-v1.json").read_bytes())
        [chapter] = [item for item in book["chapters"] if item["id"] == "native-forward-models"]
        page = "examples/" + entry["page"]
        self.assertIn("../" + page, {item["href"] for item in chapter["records"]})
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            for name, content in files.items():
                target = site / "examples" / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            ledger = json.loads(presentation.REGISTRY.read_bytes())
            [record] = [item for item in ledger["routes"] if item["route"] == page]
            report = presentation.audit_site(site, {"routes": [record]})
            self.assertTrue(report["passed"], report["findings"])
            index = site / "index.html"
            index.write_text("<ul></ul>", encoding="utf-8")
            (site / "archive.html").touch()
            landing.build(site)
            [archive_entry], _ = landing.parse_index(index.read_text(encoding="utf-8"))
            self.assertEqual(archive_entry.report_id + "/index.html", page)
            self.assertEqual(archive_entry.commit, stage.EXACT_SUPPORT.source_commit)
            for _, path in archive_entry.links:
                self.assertTrue((site / path).is_file(), path)

    def test_backward_reachability_keeps_the_exact_certificates_and_battery_trajectory(
        self,
    ) -> None:
        files, [entry], card = stage.build_backward_reachability(ROOT)
        route = stage.BACKWARD_REACHABILITY.route
        original = f"{route}/catalogue-backward-support-evidence.zip"
        for path in (entry["page"], entry["figure"], original):
            self.assertIn(path, files)
            self.assertIn(path, card)

        with ZipFile(BytesIO(files[original])) as archive:
            self.assertEqual(files[entry["figure"]], archive.read("battery-forward-backward.svg"))
            self.assertEqual(files[f"{route}/predecessor.cpp"], archive.read("predecessor.cpp"))
            audit = json.loads(archive.read("backward-audit.json"))
            battery = json.loads(archive.read("battery-geometry.json"))

        self.assertEqual(audit["models"], 35)
        self.assertEqual(audit["checked_supports"], 1120)
        self.assertIs(audit["tampered_support_rejected"], True)
        self.assertEqual(len(audit["records"]), 35)
        for record in audit["records"].values():
            self.assertEqual(record["count"], 32)
            self.assertEqual(record["status"], "all-sampled-supports-exact")
        self.assertEqual([row["k"] for row in battery["stages"]], [0, 1, 2, 3])
        self.assertEqual(battery["terminal_state"], ["33", "684736294544664953/9007199254740992"])

        page = "examples/" + entry["page"]
        book = json.loads((ROOT / "docs/catalogue/learning-book-v1.json").read_bytes())
        [chapter] = [item for item in book["chapters"] if item["id"] == "native-forward-models"]
        self.assertIn("../" + page, {item["href"] for item in chapter["records"]})
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            for name, content in files.items():
                target = site / "examples" / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            ledger = json.loads(presentation.REGISTRY.read_bytes())
            audited_pages = {page, f"examples/{stage.CONSTRAINED_PREDECESSORS.route}/index.html"}
            records = [item for item in ledger["routes"] if item["route"] in audited_pages]
            report = presentation.audit_site(site, {"routes": records})
            self.assertTrue(report["passed"], report["findings"])
            index = site / "index.html"
            index.write_text("<ul></ul>", encoding="utf-8")
            (site / "archive.html").touch()
            landing.build(site)
            [archive_entry], _ = landing.parse_index(index.read_text(encoding="utf-8"))
            self.assertEqual(archive_entry.report_id + "/index.html", page)
            self.assertEqual(archive_entry.commit, stage.BACKWARD_REACHABILITY.source_commit)
            for _, path in archive_entry.links:
                self.assertTrue((site / path).is_file(), path)

    def test_constrained_predecessor_companion_keeps_rational_and_native_receipts(self) -> None:
        files, _, card = stage.build_backward_reachability(ROOT)
        route = stage.CONSTRAINED_PREDECESSORS.route
        page = f"{route}/index.html"
        bundled = f"{route}/{route}.zip"
        self.assertIn(page, card)
        self.assertIn(bundled, card)
        self.assertFalse(any(name.startswith(f"{route}/replay/") for name in files))
        book = json.loads((ROOT / "docs/catalogue/learning-book-v1.json").read_bytes())
        [chapter] = [
            chapter for chapter in book["chapters"] if chapter["id"] == "native-forward-models"
        ]
        self.assertIn("../examples/" + page, {item["href"] for item in chapter["records"]})
        with ZipFile(BytesIO(files[bundled])) as offline:
            manifest = json.loads(offline.read("manifest.json"))
            self.assertTrue(manifest["offline_files_sha256"])
            self.assertEqual(offline.read("REPLAY.txt"), files[f"{route}/REPLAY.txt"])
            self.assertEqual(offline.read("index.html"), files[page])
            numeric = json.loads(offline.read("replay/native/audit-with-ipopt.json"))
            exact = json.loads(offline.read("replay/native/audit-building-exact.json"))
            self.assertEqual(
                numeric["checked"], {"authored": 1120, "saved_controls": 1120, "full": 1110}
            )
            self.assertEqual(numeric["fails"], [])
            self.assertEqual(exact["certificate_count"], 32)
            remaining = {
                (item["stage"], tuple(item["direction"])) for item in numeric["exceptions"]
            }
            self.assertEqual(
                {item["model_id"] for item in numeric["exceptions"]}, {"catalogue-2026/model-28/1"}
            )
            self.assertEqual(len(remaining), 10)
            self.assertLessEqual(remaining, {(k, tuple(d)) for k, d in exact["certified"]})

    def test_frozen_bundle_rejects_changed_offline_bytes_even_with_archive_pin(self) -> None:
        original = stage.CONSTRAINED_PREDECESSORS
        route = original.route
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = root / "reports/algorithm-results" / route
            fixture.mkdir(parents=True)

            def sha(data: bytes) -> str:
                return hashlib.sha256(data).hexdigest()

            page = b"saved page"
            manifest = json.dumps(
                {
                    "schema": original.schema,
                    "source_commit": original.source_commit,
                    "files_sha256": {"index.html": sha(page)},
                    "offline_files_sha256": {"replay/audit.json": sha(b"correct")},
                }
            ).encode()
            (fixture / "manifest.json").write_bytes(manifest)
            (fixture / "index.html").write_bytes(page)
            archive = fixture / f"{route}.zip"
            with ZipFile(archive, "w") as bundle:
                for name, value in {
                    "index.html": page,
                    "manifest.json": manifest,
                    "replay/audit.json": b"changed",
                }.items():
                    bundle.writestr(name, value)
            digest = sha(archive.read_bytes())
            (fixture / f"{archive.name}.sha256").write_text(f"{digest}  {archive.name}\n")
            identity = replace(original, manifest_sha256=sha(manifest), archive_sha256=digest)
            with self.assertRaisesRegex(
                ValueError, "offline asset digest differs: replay/audit.json"
            ):
                stage.read_bundle(root, identity)

    def test_finite_action_keeps_both_runs_and_their_figures(self) -> None:
        files, [entry], card = stage.build_finite_action(ROOT)
        route = stage.FINITE_ACTION.route
        evidence = f"{route}/catalogue-separable-box-evidence.zip"
        package = f"{route}/{route}.zip"
        self.assertIn("all 175 routes", card)
        self.assertIn("45 baseline refusals", card)
        for path in (entry["page"], entry["figure"], package):
            self.assertIn(path, files)
            self.assertIn(path, card)
        with ZipFile(BytesIO(files[evidence])) as candidate:
            comparison = json.loads(candidate.read("comparison.json"))
            manifest = json.loads(files[entry["raw_record"]])
            self.assertEqual(
                manifest["candidate_sdk_commit"],
                json.loads(candidate.read("provenance.json"))["candidate_sdk_commit"],
            )
            self.assertEqual(
                files[f"{route}/terminal-box-corner.svg"], candidate.read("terminal-box-corner.svg")
            )
            self.assertEqual(
                files[f"{route}/catalogue_finite_action.cpp"],
                candidate.read("catalogue_finite_action.cpp"),
            )
            with ZipFile(
                BytesIO(candidate.read("baseline-finite-action-evidence.zip"))
            ) as baseline:
                self.assertEqual(
                    files[entry["figure"]], baseline.read("hospital-finite-actions.svg")
                )
                original = json.loads(baseline.read("audit.json"))
                self.assertEqual(original["feedback_counts"]["box"]["selected"], 25)
        self.assertEqual(comparison["recovered_box_models"], list(range(26, 36)))
        self.assertEqual(comparison["retained_box_models"], list(range(1, 26)))
        self.assertEqual(comparison["matching_nonbox_outcomes"], 140)

        zonotope_replay = f"{route}/catalogue-zonotope-replay-evidence.zip"
        with ZipFile(BytesIO(files[zonotope_replay])) as candidate:
            comparison = json.loads(candidate.read("comparison.json"))
            self.assertEqual(
                manifest["candidate_zonotope_sdk_commit"],
                json.loads(candidate.read("provenance.json"))["candidate_zonotope_sdk"],
            )
            combined = json.loads(candidate.read("combined/audit.json"))
            counts = combined["feedback_counts"]
            for profile in ("box", "zonotope", "ellipsoid", "polytope"):
                self.assertEqual(counts[profile]["selected"], 35)
            self.assertEqual(counts["parallelotope"]["selected"], 15)
            with ZipFile(BytesIO(candidate.read("zonotope-proof-evidence.zip"))) as proof:
                self.assertEqual(
                    files[f"{route}/zonotope-certificate-coverage.svg"],
                    proof.read("zonotope-certificate-coverage.svg"),
                )
        self.assertEqual(comparison["recovered_zonotope_models"], list(range(21, 36)))
        self.assertEqual(comparison["unchanged_zonotope_models"], list(range(1, 21)))
        self.assertEqual(comparison["matching_other_outcomes"], 140)

        parallelotope_replay = f"{route}/catalogue-parallelotope-replay-evidence.zip"
        with ZipFile(BytesIO(files[parallelotope_replay])) as candidate:
            comparison = json.loads(candidate.read("comparison.json"))
            provenance = json.loads(candidate.read("provenance.json"))
            self.assertEqual(
                manifest["candidate_parallelotope_sdk_commit"],
                provenance["candidate_parallelotope_sdk"],
            )
            counts = json.loads(candidate.read("audit.json"))["feedback_counts"]
            self.assertEqual(len(counts), 5)
            self.assertTrue(all(result == {"selected": 35} for result in counts.values()))
            self.assertEqual(comparison["unchanged_rows"], 155)
            self.assertEqual(len(comparison["recovered"]), 20)
            self.assertEqual(
                files[f"{route}/pair-shear-projection.svg"],
                candidate.read("pair-shear-projection.svg"),
            )

        book = json.loads((ROOT / "docs/catalogue/learning-book-v1.json").read_bytes())
        [chapter] = [
            item for item in book["chapters"] if item["id"] == "native-model-tracking-first-pass"
        ]
        page = "examples/" + entry["page"]
        self.assertIn("../" + page, {item["href"] for item in chapter["records"]})
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            for name, content in files.items():
                target = site / "examples" / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            ledger = json.loads(presentation.REGISTRY.read_bytes())
            [record] = [item for item in ledger["routes"] if item["route"] == page]
            report = presentation.audit_site(site, {"routes": [record]})
            self.assertTrue(report["passed"], report["findings"])
            index = site / "index.html"
            index.write_text("<ul></ul>", encoding="utf-8")
            (site / "archive.html").touch()
            landing.build(site)
            [archive_entry], _ = landing.parse_index(index.read_text(encoding="utf-8"))
            self.assertEqual(archive_entry.commit, stage.FINITE_ACTION.source_commit)
            self.assertIn(("Joint replay", "examples/" + parallelotope_replay), archive_entry.links)
            for _, path in archive_entry.links:
                self.assertTrue((site / path).is_file(), path)
