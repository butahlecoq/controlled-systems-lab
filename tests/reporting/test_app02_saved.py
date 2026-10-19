"""Check APP-02 saved numerical evidence and exact-byte regeneration."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("app02_render_test", ROOT / "scripts/reports/app02/render_saved.py")
render = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(render)
BUNDLE = ROOT / "reports/algorithm-results/app02-box-8ff979de60ea9d22"


class SavedApp02Test(unittest.TestCase):
    def test_raw_cases_regenerate_complete_report(self) -> None:
        render.render(BUNDLE, check=True)
        record = render.validate(BUNDLE)
        self.assertEqual(record["source_commit"],
                         "8fecba49e34c37e5e01c40218a8f014a179818fd")
        self.assertEqual([row["case"] for row in record["measurement"]["summary"]],
                         list(render.collect.CASES))
        self.assertEqual(sum(row["successes"] for row in record["measurement"]["summary"]),
                         3500)
        self.assertEqual(sum(row["failures"] for row in record["measurement"]["summary"]), 0)

    def test_changed_raw_timing_cannot_keep_the_saved_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copy = Path(temporary) / BUNDLE.name
            shutil.copytree(BUNDLE, copy)
            raw = copy / "measure.csv"
            raw.write_bytes(raw.read_bytes().replace(b"warmup,interval-box,0,100,enclosed,true,",
                                                   b"warmup,interval-box,0,100,enclosed,false,"))
            with self.assertRaises(ValueError):
                render.render(copy, check=True)


if __name__ == "__main__":
    unittest.main()
