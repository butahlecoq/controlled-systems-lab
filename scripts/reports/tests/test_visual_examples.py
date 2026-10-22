import tempfile
import unittest
from pathlib import Path

import visual_examples


class VisualGalleryInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.site = Path(self.temp.name)
        self.gallery = self.site / "examples"
        self.gallery.mkdir()
        (self.gallery / "index.html").write_text(
            '<main id="main"><section id="saved-report-figures"></section>'
            '<section id="example-one"></section></main>', encoding="utf-8")
        (self.gallery / "example-one.svg").write_text("<svg/>", encoding="utf-8")
        report = self.site / "report"
        report.mkdir()
        (report / "index.html").write_text("report", encoding="utf-8")
        (report / "records.json").write_text("{}", encoding="utf-8")
        self.entry = {"anchor": "example-one", "figure": "example-one.svg",
                      "source_page": "../report/index.html", "raw_record": "../report/records.json"}

    def tearDown(self):
        self.temp.cleanup()

    def test_inventory_targets_resolve_within_published_site(self):
        visual_examples.validate_gallery_inventory(self.gallery, [self.entry])

    def test_inventory_rejects_missing_figure(self):
        (self.gallery / "example-one.svg").unlink()
        with self.assertRaisesRegex(ValueError, "missing or escaping file"):
            visual_examples.validate_gallery_inventory(self.gallery, [self.entry])

    def test_inventory_rejects_duplicate_gallery_anchor(self):
        with self.assertRaisesRegex(ValueError, "anchors must be unique"):
            visual_examples.validate_gallery_inventory(self.gallery, [self.entry, self.entry])


if __name__ == "__main__":
    unittest.main()
