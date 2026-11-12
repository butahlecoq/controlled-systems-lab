from __future__ import annotations

import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/reports"))

import qhull_highs_strategy_a_example as example


class PageMarkup(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.main_classes: list[str] = []
        self.stylesheets: list[str] = []
        self.math_rows = 0
        self.math_cells = 0
        self.labels: list[str] = []
        self.control_witness_label = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "main":
            self.main_classes.extend((attributes.get("class") or "").split())
        elif tag == "link" and attributes.get("rel") == "stylesheet":
            self.stylesheets.append(attributes.get("href", ""))
        elif tag == "mtr":
            self.math_rows += 1
        elif tag == "mtd":
            self.math_cells += 1
        elif tag == "span" and attributes.get("role") == "math":
            self.labels.append(attributes.get("aria-label", ""))

    def handle_data(self, data: str) -> None:
        if "Checked feasible control witness" in data:
            self.control_witness_label = True


class QhullHighsStrategyAExampleTests(unittest.TestCase):
    def test_plot_points_share_origin_and_tick_mapping(self) -> None:
        record = example.load_record()
        svg = ElementTree.fromstring(example.figure(record))
        namespace = {"svg": "http://www.w3.org/2000/svg"}
        points = [element.attrib for element in svg.findall(".//svg:circle", namespace)]
        self.assertEqual(example.plot_point([0, 0]), (165, 310))
        self.assertEqual(example.plot_point([1, 0]), (525, 310))
        self.assertEqual(example.plot_point([1, 1]), (525, 130))
        self.assertEqual(example.plot_point([0, 1]), (165, 130))
        qp = next(point for point in points if point.get("fill") == "#7657a6")
        lp = next(point for point in points if point.get("fill") == "#bd6c22")
        self.assertEqual((int(qp["cx"]), int(qp["cy"])), example.plot_point([0, 0]))
        self.assertEqual((int(lp["cx"]), int(lp["cy"])), example.plot_point([1, 0]))
        axis_paths = [element.attrib.get("d", "") for element in svg.findall(".//svg:path", namespace)]
        self.assertTrue(any("M105 310H610" in path for path in axis_paths))
        self.assertTrue(any("M165 390V55" in path for path in axis_paths))

    def test_page_uses_shared_shell_mathml_and_witness_language(self) -> None:
        markup = PageMarkup()
        markup.feed(example.page(example.load_record()))
        self.assertEqual(markup.stylesheets, ["examples.css"])
        self.assertIn("page-content", markup.main_classes)
        self.assertIn("walkthrough", markup.main_classes)
        self.assertGreaterEqual(markup.math_rows, 10)
        self.assertGreaterEqual(markup.math_cells, 20)
        self.assertTrue(any(label.startswith("Ordered V point matrix:") for label in markup.labels))
        self.assertTrue(any(label.startswith("Returned H bound column vector:") for label in markup.labels))
        self.assertIn("Checked feasible control witness", example.page(example.load_record()))
        self.assertNotIn("<style>", example.page(example.load_record()))


if __name__ == "__main__":
    unittest.main()
