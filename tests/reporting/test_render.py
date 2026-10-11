"""Saved-input rendering and offline safety behavior."""
import copy
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
import report_data as data


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("render"), "saved-input renderer is missing")
        self.renderer = __import__("render")

    def test_offline_html_csv_escape_diagnostics_and_keep_negative_numbers(self):
        view = data.load_view(ROOT / "tests/reporting/fixtures/view-v1.json")
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "report"
            self.renderer.render(view, out)
            html = (out / "index.html").read_text(encoding="utf-8")
            self.assertIn("TEST DATA", html)
            self.assertIn("&lt;script&gt;", html)
            self.assertNotIn("<script>", html)
            self.assertIn("unestablished", html)
            self.assertTrue("input-to-verified-result" in html.lower())
            self.assertIn("not added", html)
            with (out / "trials.csv").open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 25)
            self.assertEqual(rows[1]["original_objective"], "-1.0")
            self.assertEqual(rows[2]["original_objective"], "-6.0")
            self.assertEqual(rows[3]["outcome"], "infeasible")
            self.assertEqual(rows[3]["original_objective"], "")
            self.assertEqual(rows[0]["public_run_ns"], "10")
            self.assertEqual(self.renderer.csv_text("=cmd()"), "'=cmd()")
            with self.assertRaises(FileExistsError):
                self.renderer.render(view, out)

    def test_failed_cancelled_unsupported_and_missing_rows_remain_visible(self):
        view = data.load_view(ROOT / "tests/reporting/fixtures/view-v1.json")
        trial = view["payload"]["trials"][0]
        trial["result"]["termination"] = "cancelled"
        trial["result"]["outcome"] = "undetermined"
        trial["validation"] = {"passed":False,"errors":["cancelled before expected solve"]}
        view = data.seal(view["payload"])
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "report"
            self.renderer.render(view, out)
            page = (out/"index.html").read_text(encoding="utf-8")
            self.assertIn("INVALID FOR BENCHMARK", page)
            self.assertIn("cancelled", page)
            with (out/"trials.csv").open(encoding="utf-8") as stream:
                self.assertEqual(len(list(csv.DictReader(stream))),25)

    def test_svg_drawing_and_internal_references_allowed_unsafe_content_rejected(self):
        safe = b'<svg xmlns="http://www.w3.org/2000/svg"><defs><path id="p" d="M 0 0 L 1 1"/></defs><use href="#p"/></svg>'
        self.assertEqual(data.validate_svg(safe), safe.decode())
        unsafe = [b'<!DOCTYPE svg><svg/>', b'<!ENTITY x SYSTEM "file:///secret"><svg/>',
                  b'<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>',
                  b'<svg xmlns="http://www.w3.org/2000/svg" onload="bad()"/>',
                  b'<svg xmlns="http://www.w3.org/2000/svg"><foreignObject/></svg>',
                  b'<svg xmlns="http://www.w3.org/2000/svg"><use href="https://bad/a"/></svg>',
                  b'<svg xmlns="http://www.w3.org/2000/svg"><path style="fill:url(https://bad)"/></svg>',
                  b'<svg xmlns="http://www.w3.org/2000/svg"><metadata/></svg>',
                  b'<svg xmlns="http://www.w3.org/2000/svg" xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"/>',
                  b'<?xml version="1.0"?><svg/>']
        for content in unsafe:
            with self.subTest(content=content), self.assertRaises(ValueError):
                data.validate_svg(content)

    def test_path_traversal_absolute_and_escape_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)/"bundle"
            root.mkdir()
            (root/"ok.json").write_text("{}")
            self.assertEqual(data.local_file(root,"ok.json"),root/"ok.json")
            for name in ("../x","/x","C:/x","https://x","a\\b","a/../../x"):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    data.local_file(root,name)
            outside = Path(temp)/"outside.json"
            outside.write_text("{}")
            try:
                (root/"link.json").symlink_to(outside)
            except OSError:
                return  # OS policy may deny symlink creation; traversal checks above still ran.
            with self.assertRaises(ValueError):
                data.local_file(root,"link.json")

    def test_site_rejects_unbound_raw_sidecar_and_external_inline_style(self):
        spec=importlib.util.spec_from_file_location("report_site",ROOT/"scripts/reports/site.py")
        site=importlib.util.module_from_spec(spec);spec.loader.exec_module(site)
        with self.assertRaises(ValueError):
            site.OfflineHTML(set()).feed('<p style="background:url(https://bad)">x</p>')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            content={"raw-events.jsonl":b"raw", "process-stderr.txt":b"", "build-provenance.txt":b"build", "profile.json":b"{}"}
            for name,value in content.items(): (root/name).write_bytes(value)
            sha=lambda name:hashlib.sha256(content[name]).hexdigest()
            p={"process":{"events_sha256":sha("raw-events.jsonl"),"stderr_sha256":sha("process-stderr.txt")},
               "provenance":{"build_log_sha256":sha("build-provenance.txt")},"profile":{"sha256":sha("profile.json")}}
            site.validate_sidecar_hashes(root,p)
            (root/"raw-events.jsonl").write_bytes(b"different raw records")
            with self.assertRaises(ValueError): site.validate_sidecar_hashes(root,p)


if __name__ == "__main__":
    unittest.main()
