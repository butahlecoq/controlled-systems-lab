"""Observable malformed-input and iterator contracts for publication helpers."""

import copy
import importlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
report_data = importlib.import_module("report_data")
collector = importlib.import_module("collector_common")
figure_style = importlib.import_module("figure_style")
site_design = importlib.import_module("site_design")
visual_examples = importlib.import_module("visual_examples")
site_spec = importlib.util.spec_from_file_location(
    "spine_report_site", ROOT / "scripts/reports/site.py"
)
if site_spec is None or site_spec.loader is None:
    raise ImportError("report site helper is unavailable")
report_site = importlib.util.module_from_spec(site_spec)
site_spec.loader.exec_module(report_site)


class PublicationSpineBoundaryTests(unittest.TestCase):
    def test_breadcrumbs_accept_one_shot_iterators_and_omit_empty_navigation(self) -> None:
        self.assertEqual(
            site_design.page_start("Title", crumbs=iter(())), site_design.page_start("Title")
        )
        pairs = [("Examples", "../examples/index.html"), ("Lesson", "index.html")]
        self.assertEqual(
            site_design.page_start("Title", crumbs=iter(pairs)),
            site_design.page_start("Title", crumbs=pairs),
        )

    def test_adjacent_tick_spacing_accepts_iterators_and_keeps_labels_distinct(self) -> None:
        ticks = [1.00001, 1.00002, 1.00003]
        labels = [figure_style.format_tick(value, iter(ticks)) for value in ticks]
        self.assertEqual(len(set(labels)), len(ticks))
        self.assertEqual(figure_style.format_tick(-0.0, iter(())), "0.0")

    def test_site_retains_existing_module_aliases(self) -> None:
        for attribute, module in (
            ("opt04", "opt04_registered_reports"),
            ("opt11", "opt11_registered_reports"),
            ("issue6_b07", "issue6_b07_registered_reports"),
        ):
            self.assertIs(getattr(report_site, attribute), importlib.import_module(module))

    def test_offline_html_rejects_unknown_elements_and_external_styles(self) -> None:
        for markup, message in (
            ("<unknown></unknown>", "unsupported offline HTML element"),
            (
                "<style>@import 'https://example.invalid/style.css';</style>",
                "external HTML stylesheet",
            ),
            (
                "<style>body{background:url(https://example.invalid/x)}</style>",
                "external HTML stylesheet",
            ),
        ):
            with self.subTest(markup=markup), self.assertRaisesRegex(ValueError, message):
                report_site.OfflineHTML(set()).feed(markup)
        parser = report_site.OfflineHTML(set())
        parser.handle_data(data="ordinary text")
        parser.feed("<style>body{color:red}</style>")

    def test_missing_gallery_owner_and_unsafe_routes_fail_before_copy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = root / "catalog.json"
            catalog.write_text(json.dumps({"reports": []}), encoding="utf-8")
            for entry, message in (
                ({"source_report_id": "missing"}, "missing catalogued visual report"),
                ({"route": "../unsafe"}, "unsafe visual report route"),
                ({"route": None}, "unsafe visual report route"),
                ({"route": 1}, "unsafe visual report route"),
            ):
                with (
                    self.subTest(entry=entry),
                    patch.object(visual_examples, "SAVED_FIGURES", [entry]),
                ):
                    with self.assertRaisesRegex(ValueError, message):
                        visual_examples.saved_figure_sections(catalog, root)
            self.assertEqual(sorted(path.name for path in root.iterdir()), ["catalog.json"])

    def test_walkthrough_rejects_missing_saved_measurement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            record = Path(directory) / "records.json"
            record.write_text('{"rows": []}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "needs a measured saved analytic_2d record"):
                visual_examples.issue3_control_walkthrough(record, "safe-route")

    def test_mismatched_lp_coordinate_dimensions_are_rejected(self) -> None:
        view = report_data.load_view(ROOT / "tests/reporting/fixtures/view-v1.json")
        scenario = copy.deepcopy(view["payload"]["scenarios"][0])
        trial = next(
            row for row in view["payload"]["trials"] if row["case_id"] == scenario["case_id"]
        )
        self.assertTrue(report_data.reference_matches(trial, scenario))
        scenario["input"]["linear"].append(0)
        with self.assertRaisesRegex(ValueError, "zip\\(\\) argument 2 is shorter"):
            report_data.reference_matches(trial, scenario)

    def test_process_timeout_retains_partial_output_and_replacement_decoding(self) -> None:
        command = [sys.executable, "-c", "import os,time;os.write(1,b'partial\\xff');time.sleep(3)"]
        stdout, stderr, code, timed_out = collector.capture_process(command, timeout_seconds=1)
        self.assertEqual(stdout, "partial\ufffd")
        self.assertEqual(stderr, "")
        self.assertEqual(code, 124)
        self.assertTrue(timed_out)


if __name__ == "__main__":
    unittest.main()
