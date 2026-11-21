"""Exercise B04 saved evidence validation without rendering or a solver."""

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = Path("docs/research/evidence/b04-reference-v1")
STYLE = ROOT / "scripts/reports/styles/control-v1.json"
sys.path.insert(0, str(ROOT / "scripts/reports"))

import b04_native_smoke_companion as companion  # noqa: E402


class B04NativeSmokeCompanionTests(unittest.TestCase):
    def setUp(self):
        temporary = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(temporary)
        self.evidence = self.root / EVIDENCE
        shutil.copytree(ROOT / EVIDENCE, self.evidence)
        self.enterContext(
            patch.object(
                companion,
                "__file__",
                str(self.root / "scripts/reports/b04_native_smoke_companion.py"),
            )
        )
        self.plot = self.enterContext(patch.object(companion, "_plot"))

    def test_rejects_nonfinite_or_malformed_native_states_before_plotting(self):
        smoke = self.evidence / "native-smoke-20261026"
        attempts = smoke / "b04-cold-attempts.jsonl"
        manifest_path = smoke / "manifest.json"
        original = attempts.read_text(encoding="utf-8")
        manifest = json.loads(manifest_path.read_bytes())
        for invalid in (17, "1234", [float("nan"), 1, 2, 3], [True, 1, 2, 3]):
            with self.subTest(state=invalid):
                rows = [json.loads(line) for line in original.splitlines() if line.strip()]
                rows[0]["trajectory"]["states"][0] = invalid
                raw = ("\n".join(json.dumps(row) for row in rows) + "\n").encode()
                attempts.write_bytes(raw)
                manifest["attempts_sha256"] = hashlib.sha256(raw).hexdigest()
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "B04 saved native attempt"):
                    companion.build(STYLE)
                self.plot.assert_not_called()

    def test_rejects_unplottable_exact_coordinate_before_plotting(self):
        path = self.evidence / "exact-optimal-reference.json"
        original = path.read_bytes()
        for invalid in ("1/0", "nan", float("inf"), None):
            with self.subTest(coordinate=invalid):
                reference = json.loads(original)
                reference["exact_optimal_states_one_solution"][0][0] = invalid
                path.write_text(json.dumps(reference), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "B04 exact saved witness"):
                    companion.build(STYLE)
                self.plot.assert_not_called()
