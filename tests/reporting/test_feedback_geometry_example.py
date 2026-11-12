from __future__ import annotations

import hashlib
from html.parser import HTMLParser
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
import feedback_geometry_example as example


class FeedbackGeometryExampleTests(unittest.TestCase):
    def test_stages_exact_saved_record_and_discoverable_card(self):
        assets, entry, card = example.build()
        self.assertEqual(entry["anchor"], example.ANCHOR)
        self.assertIn('id="' + example.ANCHOR + '"', card)
        record = ROOT / "examples" / example.DATA / "box/response.jsonl"
        self.assertEqual(assets[example.DATA + "/box/response.jsonl"], record.read_bytes())
        self.assertEqual(hashlib.sha256(assets[example.DATA + "/producer.py"]).hexdigest(),
            "351862fcf70461dd54b829652a0b60618ef402cfc4f3e9331b7045a1460c4976")
        self.assertIn(b"<svg", assets[example.FIGURE])
        class Links(HTMLParser):
            def __init__(self):
                super().__init__()
                self.links = []
            def handle_starttag(self, tag, attrs):
                value = dict(attrs).get("href")
                if tag == "a" and value and not value.startswith("https:"):
                    self.links.append(value)
        links = Links()
        links.feed(assets[example.PAGE].decode("utf-8"))
        for link in links.links:
            self.assertIn(link, assets)

    def test_refuses_modified_evidence_before_staging(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "examples").mkdir()
            shutil.copy(ROOT / "examples" / example.PAGE, root / "examples" / example.PAGE)
            shutil.copytree(ROOT / "examples" / example.DATA, root / "examples" / example.DATA)
            (root / "examples" / example.DATA / "box/request.jsonl").write_text("changed")
            with self.assertRaisesRegex(ValueError, "does not match"):
                example.build(root)
