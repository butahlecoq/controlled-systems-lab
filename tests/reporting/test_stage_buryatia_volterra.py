"""Keep the published 2D Buryatia lesson tied to its saved native capture."""

from __future__ import annotations

import hashlib
import importlib
import json
import shutil
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
publication = importlib.import_module("stage_buryatia_volterra")
MANIFEST = "buryatia-volterra-affine-2d-manifest.json"
PAGE = "buryatia-volterra-affine-2d.html"


class Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.values: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.values.extend(value for key, value in attrs if key in {"href", "src"} and value)


class BuryatiaPublicationTests(unittest.TestCase):
    def source_files(self) -> list[str]:
        manifest = json.loads((ROOT / "docs/examples" / MANIFEST).read_text())
        return [MANIFEST] + [
            Path(row["path"]).name
            for row in manifest["artifacts"] + manifest["superseded_artifacts"]
        ]

    def copy_source(self, root: Path) -> None:
        destination = root / "docs/examples"
        destination.mkdir(parents=True)
        for name in self.source_files():
            shutil.copyfile(ROOT / "docs/examples" / name, destination / name)

    def test_current_and_superseded_assets_publish_byte_exactly_and_repeatably(self) -> None:
        before = {
            name: (ROOT / "docs/examples" / name).read_bytes() for name in self.source_files()
        }
        outputs, entries, card = publication.build(ROOT)
        self.assertEqual(outputs, before)
        self.assertEqual(publication.build(ROOT), (outputs, entries, card))
        self.assertEqual(len(outputs), 8)
        self.assertEqual(entries[0]["page"], PAGE)
        self.assertEqual(entries[0]["raw_record"], "buryatia-volterra-affine-2d-records.json")
        self.assertIn(PAGE, card)
        self.assertIn("superseded", card)
        self.assertIn("35a708df541409bd8d7c0bddaeafcda60c26dbae", entries[0]["source_page"])
        manifest = json.loads(outputs[MANIFEST])
        record = json.loads(outputs["buryatia-volterra-affine-2d-records.json"])
        self.assertEqual(record["native_build"], manifest["native_build"])
        self.assertEqual(record["intervals"], 60)
        self.assertEqual(len(record["records"]), 366)
        self.assertEqual(
            {name: (ROOT / "docs/examples" / name).read_bytes() for name in self.source_files()},
            before,
        )

    def test_current_and_historical_html_links_have_published_targets(self) -> None:
        outputs, _, _ = publication.build(ROOT)
        for name, content in outputs.items():
            if not name.endswith(".html"):
                continue
            parser = Links()
            parser.feed(content.decode())
            for value in parser.values:
                parsed = urlsplit(value)
                if not parsed.scheme and not parsed.netloc and parsed.path:
                    self.assertTrue(parsed.path in outputs or parsed.path == "examples.css", value)
        self.assertEqual(
            hashlib.sha256(outputs[MANIFEST]).hexdigest(),
            "530e085cdcec35f6ad67ff4ce35109fec9f65d80cd5a5c567443a613178d7988",
        )

    def test_both_html_routes_have_exact_source_owners(self) -> None:
        retirement = importlib.import_module("pages_route_retirement")
        for page in (PAGE, "buryatia-volterra-affine-2d-superseded-v1.html"):
            owners = retirement.EXAMPLE_ROUTE_PRODUCERS["examples/" + page]
            self.assertIn("scripts/reports/stage_buryatia_volterra.py", owners)
            self.assertIn("docs/examples/" + MANIFEST, owners)
            self.assertIn("docs/examples/" + page, owners)
            self.assertTrue(all((ROOT / path).is_file() for path in owners))
            self.assertTrue(
                {"docs/examples/" + name for name in self.source_files()}.issubset(owners)
            )
        self.assertIn(
            "scripts/reports/stage_buryatia_volterra.py", retirement.GALLERY_INDEX_PRODUCERS
        )

    def test_each_changed_asset_is_rejected_including_the_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory)
            self.copy_source(fixture)
            for name in self.source_files():
                with self.subTest(asset=name):
                    path = fixture / "docs/examples" / name
                    original = path.read_bytes()
                    path.write_bytes(original + b" ")
                    with self.assertRaisesRegex(ValueError, "digest|identity"):
                        publication.build(fixture)
                    path.write_bytes(original)

    def test_manifest_cannot_relabel_the_saved_native_producer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory)
            self.copy_source(fixture)
            path = fixture / "docs/examples" / MANIFEST
            value = json.loads(path.read_text())
            value["native_build"]["git_revision"] = "0" * 40
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "identity"):
                publication.build(fixture)

    def test_missing_and_symlinked_source_members_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory)
            self.copy_source(fixture)
            path = fixture / "docs/examples" / PAGE
            path.unlink()
            with self.assertRaisesRegex(ValueError, "missing"):
                publication.build(fixture)
            path.symlink_to(ROOT / "docs/examples" / PAGE)
            with self.assertRaisesRegex(ValueError, "symlink"):
                publication.build(fixture)


if __name__ == "__main__":
    unittest.main()
