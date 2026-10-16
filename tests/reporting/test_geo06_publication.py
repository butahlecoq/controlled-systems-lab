"""GEO-06's saved measurement must stage as a verifiable offline report."""
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
import geo06_registered_reports as geo06


SOURCE = ROOT / "reports" / "algorithm-results" / "geo06-b010fb3df212604b"


class Geo06PublicationTests(unittest.TestCase):
    def test_saved_report_has_verified_trials_and_self_contained_offline_zip(self):
        item = geo06.adapt(SOURCE)
        self.assertEqual(item.source_commit, "ce63bff5a0face88c3c5e977f7d96337e8cbe948")
        record = json.loads((SOURCE / "records.json").read_text(encoding="utf-8"))
        measured = [row for row in record["rows"] if row["warmup"] == 0]
        self.assertEqual((record["repetitions"], record["calls_per_trial"], len(measured)), (7, 1000, 21))
        self.assertEqual({row["status"] for row in measured}, {"passed"})
        artifacts = geo06.publication_artifacts(SOURCE, item)
        self.assertIn(b"2494000", artifacts["index.html"])
        self.assertIn(b"Square fixture", artifacts["index.html"])
        archive = geo06.offline_zip(SOURCE, item)
        with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
            self.assertEqual(zipped.read("index.html"), artifacts["index.html"])
            self.assertEqual(zipped.read(item.report_id + "/trials.csv"), (SOURCE / "trials.csv").read_bytes())
            self.assertEqual(zipped.read(item.report_id + "/publication-manifest.json"), artifacts["publication-manifest.json"])

    def test_tampered_raw_csv_is_rejected_before_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / SOURCE.name
            shutil.copytree(SOURCE, bundle)
            shutil.copyfile(SOURCE.parent / (SOURCE.name + ".source.zip"), root / (SOURCE.name + ".source.zip"))
            with (bundle / "trials.csv").open("ab") as output:
                output.write(b"\nforged,1,0,1,pass,0\n")
            with self.assertRaises(ValueError):
                geo06.adapt(bundle)


if __name__ == "__main__":
    unittest.main()
