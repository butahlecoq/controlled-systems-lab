"""Small, accessible MathML fragments for numeric matrices and vectors."""

from __future__ import annotations

import json
from html import escape
from typing import Sequence


def matrix_html(
    matrix: Sequence[Sequence[int | float]],
    label: str,
    *,
    display_significant_digits: int | None = None,
) -> str:
    """Render a rectangular numeric matrix as accessible MathML with CSS brackets.

    A column vector is represented as one value per row, for example ``[[2], [5]]``.
    The returned fragment uses the shared ``.math-matrix`` styles in examples.css.
    """
    if not matrix or not matrix[0]:
        raise ValueError("matrix must have at least one row and one column")
    column_count = len(matrix[0])
    if any(len(row) != column_count for row in matrix):
        raise ValueError("matrix rows must all have the same column count")

    def display_value(value: int | float) -> str:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise TypeError("MathML matrices require numeric values")
        exact = json.dumps(value, allow_nan=False)
        if display_significant_digits is not None:
            return format(value, f".{display_significant_digits}g")
        return exact

    rendered_rows = []
    spoken_rows = []
    for row in matrix:
        values = [display_value(value) for value in row]
        cells = "".join(f"<mtd><mn>{escape(value)}</mn></mtd>" for value in values)
        rendered_rows.append(f"<mtr>{cells}</mtr>")
        spoken_rows.append(", ".join(values))
    accessible_label = f"{label}: {'; '.join(spoken_rows)}"
    return (
        '<span class="math-matrix" role="math" aria-label="'
        + escape(accessible_label, quote=True)
        + '"><span class="math-bracket math-bracket-left" aria-hidden="true"></span>'
        '<math display="inline" aria-hidden="true"><mtable columnspacing="0.7em" rowspacing="0.25em">'
        + "".join(rendered_rows)
        + '</mtable></math><span class="math-bracket math-bracket-right" aria-hidden="true"></span></span>'
    )
