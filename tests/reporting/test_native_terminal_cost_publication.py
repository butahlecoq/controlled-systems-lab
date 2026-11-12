from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock
import zipfile
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts/reports"))
import native_terminal_cost_example as example


class NativeTerminalCostPublicationTests(unittest.TestCase):
    def test_original_and_corrected_minima_match_the_source_formulas(self):
        before, after, specs=example.load_records(example.BUNDLE)
        target=next(row["observed_state"] for row in after["rows"] if row["task"]=="syn-nl-lv-01")
        for spec,expected in zip(specs,[2*np.asarray(target),target]):
            actual=np.linalg.solve(np.asarray(spec["Q"]),-np.asarray(spec["linear"]))
            np.testing.assert_allclose(actual,expected,rtol=0,atol=1e-12)
        self.assertAlmostEqual(example.quadratic(specs[0],target),-1.0)
        self.assertAlmostEqual(example.quadratic(specs[1],target),0.0)
        self.assertEqual(before["source_commit"],"0ef47d9a1593c57039eda572db3ccda7d620fc19")

    def test_stage_preserves_raw_bytes_archive_and_mathematical_view(self):
        raw={p.relative_to(example.BUNDLE):p.read_bytes() for p in example.BUNDLE.rglob("*.json")}
        with tempfile.TemporaryDirectory() as temporary:
            site=Path(temporary)/"site"
            example.stage(site)
            example.stage(site)
            target=site/example.ROUTE
            for name,content in raw.items():self.assertEqual((target/name).read_bytes(),content)
            page=(target/"index.html").read_text()
            self.assertEqual(page.count('class="math-matrix"'),4)
            self.assertIn('class="cost-print"',page)
            self.assertIn('Q = 2D',page)
            self.assertNotIn('&quot;Q&quot;:',page)
            for line in (target/"SHA256SUMS").read_text().splitlines():
                digest,name=line.split("  ",1)
                self.assertEqual(hashlib.sha256((target/name).read_bytes()).hexdigest(),digest)
            source_archive=example.BUNDLE.parent/(example.ROUTE+".zip")
            archive=site/source_archive.name
            self.assertEqual(archive.read_bytes(),source_archive.read_bytes())
            with zipfile.ZipFile(archive) as zipped:self.assertIsNone(zipped.testzip())

    def test_saved_archive_mismatch_cannot_stage_a_partial_bundle(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            bundle=root/"source"/example.ROUTE
            shutil.copytree(example.BUNDLE,bundle)
            for suffix in (".zip",".zip.sha256"):
                name=example.ROUTE+suffix
                shutil.copyfile(example.BUNDLE.parent/name,bundle.parent/name)
            (bundle/"after/record.json").write_text("{}")
            site=root/"site"
            with mock.patch.object(example,"BUNDLE",bundle):
                with self.assertRaisesRegex(ValueError,"payload differs"):
                    example.stage(site)
            self.assertFalse(site.exists())

    def test_gallery_card_resolves_to_the_actual_flat_publication_route(self):
        import visual_examples

        class Links(HTMLParser):
            def __init__(self):super().__init__(); self.values=[]
            def handle_starttag(self,tag,attrs):
                self.values.extend(value for key,value in attrs if key in {"href","src"})

        with tempfile.TemporaryDirectory() as temporary:
            site=Path(temporary)/"site"
            example.stage(site)
            descriptor=next(row for row in visual_examples.SAVED_FIGURES if row.get("route")==example.ROUTE)
            with mock.patch.object(visual_examples,"SAVED_FIGURES",(descriptor,)):
                markup,inventory=visual_examples.saved_figure_sections(ROOT/"reports/algorithm-results/catalog.json",site)
            links=Links(); links.feed(markup)
            self.assertTrue(links.values)
            for href in links.values:
                target=urlsplit(urljoin("https://butahlecoq.github.io/controlled-systems-lab/examples/index.html",href))
                prefix="/controlled-systems-lab/"
                self.assertTrue(target.path.startswith(prefix),target.path)
                self.assertTrue((site/target.path[len(prefix):]).is_file(),target.path)
            self.assertEqual(len(inventory),1)

    def test_visual_inventory_records_the_implemented_illustration_role(self):
        import audit_visual_routes
        producer=next(row for row in audit_visual_routes.build(ROOT)["producers_and_routes"]
                      if row["source"]=="scripts/reports/native_terminal_cost_example.py")
        self.assertEqual(producer["disposition"],"saved-data-illustration-renderer")
        self.assertIn("source-bound",producer["role_and_disposition_reason"])
        self.assertNotIn("follow_up_issue",producer)
