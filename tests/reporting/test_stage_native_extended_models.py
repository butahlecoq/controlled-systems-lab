"""Publish both forward lessons with complete, usable saved evidence."""

import importlib
import posixpath
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
native = importlib.import_module("stage_native_extended_models")


class References(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []

    def handle_starttag(self, tag, attrs):
        self.paths.extend(value for name, value in attrs if name in {"href", "src"})


class ExtendedNativePublicationTests(unittest.TestCase):
    def test_complete_saved_bundle_and_both_lessons_publish_unchanged(self):
        files, entries, cards = native.build(ROOT)
        bundle = ROOT / "reports/algorithm-results" / native.ROUTE
        for path in bundle.rglob("*"):
            if path.is_file():
                with self.subTest(path=path.relative_to(bundle)):
                    self.assertEqual(
                        files[native.ROUTE + "/" + path.relative_to(bundle).as_posix()],
                        path.read_bytes(),
                    )
        self.assertEqual(
            {entry["anchor"] for entry in entries},
            {
                "native-slide50-reachability",
                "native-spatial-flight",
            },
        )
        for entry in entries:
            self.assertIn('id="' + entry["anchor"] + '"', cards)
            self.assertIn(entry["figure"], files)
            self.assertEqual(
                files[entry["page"]], (ROOT / "docs/examples" / entry["page"]).read_bytes()
            )

    def test_canonical_and_offline_lessons_have_resolvable_local_downloads(self):
        files, _, _ = native.build(ROOT)
        shared_pages = {"examples.css", "index.html", "native-model-catalogue.html"}
        for page, content in files.items():
            if not page.endswith(".html"):
                continue
            references = References()
            references.feed(content.decode())
            for reference in references.paths:
                parts = urlsplit(reference)
                if parts.scheme or parts.netloc or not parts.path:
                    continue
                path = posixpath.normpath(posixpath.join(posixpath.dirname(page), parts.path))
                with self.subTest(page=page, reference=reference):
                    self.assertFalse(path.startswith("../"))
                    self.assertTrue(
                        path in files or path in shared_pages,
                        "missing published local asset: " + path,
                    )


if __name__ == "__main__":
    unittest.main()
