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
import subprocess

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
import report_data as data


class RenderTests(unittest.TestCase):
    def test_site_import_and_existing_catalogue_render_without_report_dependencies(self):
        code = '''
import importlib.util
from pathlib import Path
import sys
assert importlib.util.find_spec("jsonschema") is None
sys.path.insert(0, str(Path(sys.argv[1]) / "scripts/reports"))
spec = importlib.util.spec_from_file_location("csl_site_without_report_deps", Path(sys.argv[1]) / "scripts/reports/site.py")
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)
print(publisher.catalogue_index({"reports": []}))
assert "jsonschema" not in sys.modules
'''
        result = subprocess.run([sys.executable, "-S", "-c", code, str(ROOT)], capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("<title>CSL algorithm reports</title>", result.stdout)

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
            self.assertIn("TEST DATA \u2014 functional or literal fixture",html)
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
            self.assertEqual({key:rows[0][key] for key in ("sequence","harness","termination","support","validation_passed","row_residual","variable_residual","end_to_end_scope")},
                             {"sequence":"1","harness":"returned","termination":"completed","support":"unestablished","validation_passed":"True","row_residual":"0.0","variable_residual":"0.0","end_to_end_scope":"end_to_end"})
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
        styled = b'<svg xmlns="http://www.w3.org/2000/svg"><style>text{font:13px system-ui,sans-serif;fill:#172033}.scenario{font-weight:600}</style><text class="scenario" x="0" y="1">fixture</text></svg>'
        self.assertEqual(data.validate_svg(styled), styled.decode())
        unsafe = [b'<!DOCTYPE svg><svg/>', b'<!ENTITY x SYSTEM "file:///secret"><svg/>',
                  b'<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>',
                  b'<svg xmlns="http://www.w3.org/2000/svg" onload="bad()"/>',
                  b'<svg xmlns="http://www.w3.org/2000/svg"><foreignObject/></svg>',
                  b'<svg xmlns="http://www.w3.org/2000/svg"><use href="https://bad/a"/></svg>',
                  b'<svg xmlns="http://www.w3.org/2000/svg"><path style="fill:url(https://bad)"/></svg>',
                  b'<svg xmlns="http://www.w3.org/2000/svg"><text class="scenario onload=bad"/></svg>',
                  b'<svg xmlns="http://www.w3.org/2000/svg"><style>text:hover{fill:red}</style></svg>',
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
            self.assertTrue(data.local_file(root,"ok.json").samefile(root/"ok.json"))
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

    def test_offline_generated_vocabulary_rejects_resource_attributes(self):
        spec=importlib.util.spec_from_file_location("report_site",ROOT/"scripts/reports/site.py")
        site=importlib.util.module_from_spec(spec);spec.loader.exec_module(site)
        for page in ('<meta http-equiv="refresh" content="0; URL=https://example.invalid/">',
                     '<img srcset="https://example.invalid/image.png 1x">',
                     '<video poster="https://example.invalid/x">', '<body background="https://example.invalid/x">',
                     '<a href="#ok" ping="https://example.invalid/x">x</a>', '<input autofocus>',
                     '<meta name="viewport" content="safe" http-equiv="refresh">'):
            with self.subTest(page=page),self.assertRaises(ValueError): site.OfflineHTML(set()).feed(page)

    def test_repository_fallback_ref_is_distinct_from_measured_source(self):
        spec=importlib.util.spec_from_file_location("report_site",ROOT/"scripts/reports/site.py")
        site=importlib.util.module_from_spec(spec);spec.loader.exec_module(site)
        view=data.load_view(ROOT/'tests/reporting/fixtures/view-v1.json')
        catalog={"reports":[{"report_id":view['report_id'],"source_commit":"a"*40}]}
        page=site.catalogue_index(catalog)
        self.assertIn('/tree/main/reports/algorithm-results/'+view['report_id'],page)
        self.assertIn('current main',page)
        self.assertIn('a'*40,page)
        for ref in ('../escape','https://bad','unknown-branch'):
            with self.subTest(ref=ref),self.assertRaises(ValueError): site.catalogue_index({**catalog,'artifact_ref':ref})
        fixed=site.catalogue_index({**catalog,'artifact_ref':'b'*40})
        self.assertIn('/tree/'+'b'*40+'/reports/algorithm-results/',fixed)
        self.assertIn('a'*40,fixed)


if __name__ == "__main__":
    unittest.main()
