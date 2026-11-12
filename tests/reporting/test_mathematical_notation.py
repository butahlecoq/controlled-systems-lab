from __future__ import annotations

import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/reports"))

from mathematical_notation import matrix_html


class MatrixMarkup(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows = 0
        self.cells = 0
        self.mathml_tables = 0
        self.math_labels: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs = dict(attrs)
        if tag == "mtr":
            self.rows += 1
        elif tag == "mtd":
            self.cells += 1
        elif tag == "mtable":
            self.mathml_tables += 1
        elif tag == "span" and attrs.get("role") == "math":
            self.math_labels.append(attrs.get("aria-label", ""))


class MathematicalNotationTests(unittest.TestCase):
    def test_projection_matrix_uses_declared_mathml_dimensions(self) -> None:
        html = matrix_html([[1, 0, 0, 0], [0, 0, 1, 0]], "Projection matrix P")
        parsed = MatrixMarkup()
        parsed.feed(html)
        self.assertEqual((parsed.mathml_tables, parsed.rows, parsed.cells), (1, 2, 8))
        self.assertEqual(parsed.math_labels, ["Projection matrix P: 1, 0, 0, 0; 0, 0, 1, 0"])
        self.assertIn("math-bracket-left", html)
        self.assertIn("math-bracket-right", html)

    def test_scale_column_vector_has_one_value_per_row(self) -> None:
        html = matrix_html([[100], [30], [3], [1]], "Raw scales")
        parsed = MatrixMarkup()
        parsed.feed(html)
        self.assertEqual((parsed.rows, parsed.cells), (4, 4))
        self.assertIn("Raw scales: 100; 30; 3; 1", parsed.math_labels[0])


if __name__ == "__main__":
    unittest.main()
