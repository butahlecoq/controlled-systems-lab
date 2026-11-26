from __future__ import annotations

import hashlib
import json
import re
import sys
import unittest
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))

import landing  # noqa: E402
import source_index_figure  # noqa: E402
import source_index_names  # noqa: E402
import visual_examples  # noqa: E402


class SourceIndexDisplayNameTests(unittest.TestCase):
    def test_canonical_display_names_and_compatibility_aliases(self) -> None:
        names = source_index_names.load()
        self.assertEqual(names["schema"], "csl.source-index-geometry-display-names/1")
        self.assertEqual(
            source_index_names.family()["display_name"],
            "Legacy source-index geometry routines",
        )
        expected = {
            "kpabep": "Candidate-elimination hull reducer",
            "modif": "Simplex pivot oracle",
            "reach": "Affine reachability vertex generator",
        }
        for key, title in expected.items():
            with self.subTest(routine=key):
                self.assertEqual(source_index_names.display_name(key), title)
        self.assertEqual(
            source_index_names.display_name("near-tolerance"),
            "When tolerance removes a true hull vertex",
        )
        reducer = source_index_names.routine("kpabep")
        self.assertIn("btulshor", reducer["cli_aliases"])
        self.assertIn("candidate-elimination", reducer["cli_aliases"])
        self.assertIn("candidate-elimination-hull-reducer", reducer["cli_aliases"])
        self.assertIn("legacy-source-index", reducer["cli_aliases"])
        self.assertTrue(source_index_names.is_reducer_cli_alias("btulshor"))
        self.assertTrue(source_index_names.is_reducer_cli_alias("candidate-elimination"))
        self.assertFalse(source_index_names.is_reducer_cli_alias("quickhull"))

    def test_stable_provider_ids_and_symbols_resolve_to_display_names(self) -> None:
        self.assertEqual(
            source_index_names.display_name_for_identity("csl.hull.source.btulshor-kpabep"),
            "Candidate-elimination hull reducer",
        )
        self.assertEqual(
            source_index_names.display_name_for_identity("csl::geometry::legacy_btulshor::modif"),
            "Simplex pivot oracle",
        )
        self.assertEqual(
            source_index_names.display_name_for_identity("csl::geometry::legacy_btulshor::reach"),
            "Affine reachability vertex generator",
        )
        self.assertEqual(
            source_index_names.display_name_for_identity("csl::geometry::legacy_btulshor"),
            "Legacy source-index geometry routines",
        )
        self.assertIsNone(
            source_index_names.display_name_for_identity("csl.hull.source.quickhull-2d")
        )
        header = (ROOT / "include/csl/geometry/legacy_btulshor.hpp").read_text(encoding="utf-8")
        source = (ROOT / "src/geometry/source_index_hull.cpp").read_text(encoding="utf-8")
        implementation = (ROOT / "src/geometry/legacy_btulshor.cpp").read_text(encoding="utf-8")
        self.assertIn("csl.legacy.btulshor.modif.source-v1", header + source + implementation)
        self.assertIn("csl.legacy.btulshor.kpabep.source-v1", header + source + implementation)
        self.assertIn("csl.legacy.btulshor.reach.source-v1", header + source + implementation)
        self.assertIn('{{"csl.hull.source.btulshor-kpabep"}, "1.0.0"}', source)

    def test_maintained_pages_and_navigation_use_descriptive_titles(self) -> None:
        source_page = (ROOT / "docs/examples/source-index-geometry-2d.html").read_text(
            encoding="utf-8"
        )
        near_page = (ROOT / "docs/examples/kpabep-near-collinear-20261115.html").read_text(
            encoding="utf-8"
        )
        chapter = (ROOT / "docs/examples/learning/chapters/simplex-and-comparators.html").read_text(
            encoding="utf-8"
        )
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(
            "<title>Legacy source-index geometry routines in a 2D pipeline</title>", source_page
        )
        self.assertNotIn("Source-index hulls in a 2D geometry pipeline", source_page)
        self.assertIn("Candidate-elimination hull reducer", source_page)
        self.assertIn("simplex pivot oracle", source_page)
        self.assertIn("source_index_geometry_2d candidate-elimination", source_page)
        self.assertIn("<title>When tolerance removes a true hull vertex</title>", near_page)
        self.assertIn("<h1>When tolerance removes a true hull vertex</h1>", near_page)
        self.assertNotIn("Near-collinear KPABEP inclusion failure", near_page)
        self.assertIn("candidate-elimination hull reducer", chapter)
        self.assertIn("docs/catalogue/source-index-geometry-names.json", readme)
        report_family = source_index_names.report_family("btulshor-source-faithful")
        self.assertEqual(
            landing.FAMILIES["btulshor-source-faithful"].title,
            report_family["legacy_aliases"][0],
        )
        self.assertEqual(
            visual_examples.SOURCE_INDEX_TITLE,
            "Legacy source-index geometry routines in a 2D pipeline",
        )
        self.assertEqual(
            visual_examples.NEAR_TOLERANCE_TITLE,
            "When tolerance removes a true hull vertex",
        )
        coverage = json.loads((ROOT / "scripts/reports/algorithm_visual_coverage.json").read_text())
        family = next(
            row for row in coverage["families"] if row["id"] == "btulshor-source-faithful"
        )
        self.assertEqual(family["name"], report_family["display_name"])

    def test_source_index_figure_uses_descriptive_record_label(self) -> None:
        records = json.loads(
            (ROOT / "docs/examples/source-index-geometry-2d-records.json").read_text()
        )
        svg = source_index_figure.render_svg(records)
        self.assertIn(
            "They match the saved record for the Candidate-elimination hull reducer.", svg
        )
        self.assertNotIn("saved BTULSHOR record", svg)
        self.assertEqual(
            (ROOT / "docs/examples/source-index-geometry-2d.svg").read_text(encoding="utf-8"), svg
        )

    def test_established_routes_remain_in_the_route_inventories(self) -> None:
        names = source_index_names.load()
        presentation = json.loads(
            (ROOT / "scripts/reports/mathematical-presentation-routes.json").read_text()
        )
        routes = {row["route"]: row for row in presentation["routes"]}
        inventory = json.loads((ROOT / "scripts/reports/visual-route-inventory.json").read_text())
        gallery_assets = {
            asset for group in inventory["gallery_routes"] for asset in group["assets"]
        }
        for example in names["examples"]:
            with self.subTest(route=example["route"]):
                self.assertEqual(routes[example["route"]]["disposition"], "maintained")
                self.assertEqual(routes[example["route"]]["owner"], example["owner"])
                for field in ("route", "figure_route", "record_route"):
                    if field in example:
                        asset = example[field].removeprefix("examples/")
                        self.assertTrue((ROOT / "docs/examples" / asset).is_file())
                        self.assertIn(asset, gallery_assets)
        producers = {row["source"]: row for row in inventory["producers_and_routes"]}
        figure_producer = producers["scripts/reports/source_index_figure.py"]
        self.assertEqual(
            figure_producer["disposition"], "analytic-reference-checked-saved-run-renderer"
        )
        self.assertIn("source-index-geometry-2d.svg", figure_producer["asset_name_literals"])
        frozen_routes = {
            row["route"] for row in presentation["routes"] if row["disposition"] == "frozen"
        }
        catalog = json.loads((ROOT / "reports/algorithm-results/catalog.json").read_text())
        published_report_ids = {row["report_id"] for row in catalog["reports"]}
        for route in names["stable_routes"]:
            with self.subTest(stable_route=route):
                if route.startswith("examples/"):
                    continue
                if route.endswith(".zip"):
                    self.assertIn(route.removesuffix(".zip"), published_report_ids)
                    self.assertTrue((ROOT / "reports/algorithm-results" / route).is_file())
                else:
                    self.assertIn(route, frozen_routes)
                    bundle_route = route.split("/", 1)[1]
                    with ZipFile(
                        ROOT / "reports/algorithm-results" / f"{route.split('/')[0]}.zip"
                    ) as bundle:
                        self.assertIn(bundle_route, bundle.namelist())
        report_family = source_index_names.report_family("btulshor-source-faithful")
        self.assertTrue(
            any(
                re.fullmatch(report_family["route_pattern"], report_id)
                for report_id in published_report_ids
            )
        )

    def test_saved_evidence_bytes_and_bundle_hashes_are_unchanged(self) -> None:
        for item in source_index_names.load()["saved_evidence"]:
            with self.subTest(path=item["path"]):
                data = (ROOT / item["path"]).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), item["sha256"])
        bundle = ROOT / "reports/algorithm-results/btulshor-source-faithful-20261110-v1"
        for line in (bundle / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
            digest, name = line.split(maxsplit=1)
            with self.subTest(bundle_file=name):
                self.assertEqual(hashlib.sha256((bundle / name).read_bytes()).hexdigest(), digest)


if __name__ == "__main__":
    unittest.main()
