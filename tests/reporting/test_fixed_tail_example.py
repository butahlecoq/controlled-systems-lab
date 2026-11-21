import importlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
example = importlib.import_module("fixed_tail_example")


class FixedTailExampleTests(unittest.TestCase):
    def test_saved_native_controls_match_the_five_independent_answers(self):
        assets, entry, card = example.build()
        audit = json.loads(assets["native-fixed-tail-2d-audit.json"])
        self.assertEqual(set(audit), set(example.FAMILIES))
        self.assertTrue(all(row["accepted"] for row in audit.values()))
        self.assertAlmostEqual(audit["box"]["source_cost"], 0.77, places=8)
        self.assertGreater(audit["parallelotope"]["source_cost"], audit["ellipsoid"]["source_cost"])
        self.assertIn(b"factor-domain norm", assets[example.PAGE])
        self.assertIn(b"math-matrix", assets[example.PAGE])
        self.assertIn(b"<mtable>", assets[example.PAGE])
        self.assertIn(b"future controls", assets[example.PAGE])
        self.assertIn("native-fixed-tail-2d", card)
        self.assertEqual(entry["raw_record"], "native-fixed-tail-2d-audit.json")

    def test_changed_saved_response_fails_before_any_render(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            shutil.copytree(ROOT / "examples" / example.DATA, root / "examples" / example.DATA)
            response = root / "examples" / example.DATA / "box/response.jsonl"
            response.write_bytes(response.read_bytes() + b" ")
            with self.assertRaisesRegex(ValueError, "hash/path mismatch"):
                example.build(root)

    def test_closed_form_audit_rejects_incorrect_control_and_history_shapes(self):
        for field in ("control", "history"):
            with self.subTest(field=field):
                responses = {
                    family: json.loads(
                        (ROOT / "examples" / example.DATA / family / "response.jsonl").read_text()
                    )
                    for family in example.FAMILIES
                }
                box = responses["box"]
                box[field].append(0)
                if field == "control":
                    box["history"] = [0, 0, *box["control"], *box["control"]]
                with self.assertRaisesRegex(ValueError, "coordinate count"):
                    example.audit(responses)

    def test_closed_form_audit_rejects_an_incorrect_native_action(self):
        responses = {
            family: json.loads(
                (ROOT / "examples" / example.DATA / family / "response.jsonl").read_text()
            )
            for family in example.FAMILIES
        }
        responses["box"]["control"] = [0, 0]
        with self.assertRaisesRegex(ValueError, "mathematical answer"):
            example.audit(responses)


if __name__ == "__main__":
    unittest.main()
