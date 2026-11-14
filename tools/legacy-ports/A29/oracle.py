"""A29 identity wrapper for the shared exact binary64 source-hull checker."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_DIGEST_DOMAIN = b"A29-row-wise-binary64-le/1"
_SHARED_PATH = Path(__file__).resolve().parents[1] / "common" / "exact_binary64_hull.py"
_SPEC = importlib.util.spec_from_file_location("csl_exact_binary64_hull", _SHARED_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"cannot load shared exact hull checker at {_SHARED_PATH}")
_SHARED = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_SHARED)


def manifest_digest(points: list[list[float]]) -> str:
    return _SHARED.manifest_digest(points, _DIGEST_DOMAIN)


def check(input_points: list[list[float]], output_points: list[list[float]] | None,
          max_points: int = 64) -> dict:
    return _SHARED.check(input_points, output_points, max_points, _DIGEST_DOMAIN)
