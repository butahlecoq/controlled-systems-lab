"""Check authentication of the frozen four-dimensional Buryatia lesson."""

from __future__ import annotations

import importlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
publication = importlib.import_module("stage_buryatia_dim4")
PAGE = Path("docs/examples/buryatia-dim4-literal-affine.html")
SCENARIO = Path("benchmarks/scenarios/buryatia-dim4-matlab-literal-affine-v1.json")


class BuryatiaDim4PublicationTests(unittest.TestCase):
    def test_changed_html_is_rejected_with_the_original_checksum_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory)
            input_dir = ROOT / PAGE.parent
            inputs = [
                ROOT / PAGE,
                ROOT / SCENARIO,
                *input_dir.glob("buryatia-dim4-*.json"),
                *input_dir.glob("buryatia-dim4-*-SHA256SUMS"),
            ]
            for source in inputs:
                destination = fixture / source.relative_to(ROOT)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)

            self.assertEqual(publication.build(fixture), publication.build(ROOT))
            page = fixture / PAGE
            page.write_bytes(page.read_bytes() + b"<!-- modified source page -->\n")

            with self.assertRaisesRegex(ValueError, "Buryatia source page hash differs"):
                publication.build(fixture)
