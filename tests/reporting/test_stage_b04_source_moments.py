"""Behavioral checks for the B04 exact source-candidate publication stager."""
from __future__ import annotations

import builtins
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/reports"))
import stage_b04_source_moments as stage_b04


class StageB04SourceMomentsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.site = self.make_site("site")

    def make_site(self, name: str) -> Path:
        site = self.root / name
        examples = site / "examples"
        examples.mkdir(parents=True)
        (site / "index.html").write_text("<!doctype html><html><body></body></html>", encoding="utf-8")
        (examples / "index.html").write_text("<!doctype html><html><body></body></html>", encoding="utf-8")
        return site

    def copy_evidence(self, target: Path) -> Path:
        (target / "b04-source-moment-figures").mkdir(parents=True)
        names = [stage_b04.INPUT_NAME, stage_b04.CERT_NAME, stage_b04.STAGES_NAME]
        for name in names:
            shutil.copyfile(stage_b04.EVIDENCE / name, target / name)
        for name in (stage_b04.EXPORT_NAME, stage_b04.SVG_NAME, stage_b04.PNG_NAME):
            shutil.copyfile(stage_b04.FIGURES / name, target / "b04-source-moment-figures" / name)
        return target

    def test_stage_builds_complete_bundle_and_rechecks_it_outside_checkout(self):
        real_import = builtins.__import__

        def no_plotting(name, *args, **kwargs):
            if name == "matplotlib" or name.startswith("matplotlib."):
                raise AssertionError("staging must not import Matplotlib")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=no_plotting):
            route = stage_b04.stage(self.site)

        page = (self.site / route / "index.html").read_text(encoding="utf-8")
        self.assertIn("B04-SOURCE-COMMENTED-X0-V1", page)
        self.assertIn("B04-SOURCE-ACTIVE-X0-V1", page)
        self.assertIn("30.899136030011613430", page)
        self.assertIn("31.121409450500400415", page)
        self.assertIn("14-dimensional", page)
        family = page.split('<section id="complete-optimal-family">', 1)[1].split("</section>", 1)[0]
        self.assertIn("B04-SOURCE-COMMENTED-X0-V1", family)
        self.assertIn("separately gives the corresponding relation", family)
        self.assertIn("B04-SOURCE-ACTIVE-X0-V1", family)
        self.assertIn("Performance was not measured", page)
        self.assertIn("aria-label=\"Seventeen exact witness states\"", page)
        self.assertIn("aria-label=\"Sixteen exact witness controls\"", page)
        self.assertEqual(page.count("<tr><th>"), 38)  # two minima, sixteen controls, seventeen stages, three header rows
        self.assertTrue((self.site / route / f"figures/{stage_b04.SVG_NAME}").is_file())
        self.assertTrue((self.site / route / f"figures/{stage_b04.PNG_NAME}").is_file())
        root_index = (self.site / "index.html").read_text(encoding="utf-8")
        gallery = (self.site / "examples/index.html").read_text(encoding="utf-8")
        self.assertIn(f'href="{route}/index.html"', root_index)
        self.assertIn(f'href="../{route}/index.html#minimal-example"', gallery)

        archive_path = self.site / f"{route}.zip"
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
            self.assertEqual(len(names), len(set(names)))
            self.assertTrue(all(name.startswith(route + "/") for name in names))
            self.assertFalse(any(name.endswith((".m", ".pas", ".fig")) for name in names))
            archive.extractall(self.root / "extracted")
        extracted = self.root / "extracted" / route
        self.assertTrue((extracted / "minimal-inputs.json").is_file())
        self.assertTrue((extracted / "offline_check.py").is_file())
        manifest = json.loads((extracted / "publication-manifest.json").read_text())
        self.assertEqual(manifest["source_anchor"]["commit"], stage_b04.SOURCE_COMMIT)
        self.assertEqual(manifest["adapter_provenance"]["sha256"],
                         hashlib.sha256(Path(stage_b04.__file__).read_bytes()).hexdigest())
        self.assertEqual(manifest["figure_export"]["schema"], "b04.source-candidate.figure-export/1")
        result = subprocess.run([sys.executable, "-B", "offline_check.py"], cwd=extracted,
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("17 stage sets", result.stdout)
        self.assertFalse((extracted / ".git").exists())

    def test_missing_or_tampered_public_evidence_fails_before_site_mutation(self):
        for mutation, message in (
            ("certificate", "source-anchor Git blob: docs/research/evidence/b04-source-moment-certificate.json"),
            ("figure", "source-anchor Git blob: docs/research/evidence/b04-source-moment-figures/b04-all-stage-reachability.svg"),
            ("missing", "missing or unsafe public evidence: b04-all-stage-reachability.png"),
        ):
            with self.subTest(mutation=mutation):
                evidence = self.copy_evidence(self.root / f"evidence-{mutation}")
                if mutation == "certificate":
                    path = evidence / stage_b04.CERT_NAME
                    path.write_bytes(path.read_bytes() + b" ")
                elif mutation == "figure":
                    path = evidence / "b04-source-moment-figures" / stage_b04.SVG_NAME
                    path.write_bytes(path.read_bytes() + b"<!-- changed -->")
                else:
                    (evidence / "b04-source-moment-figures" / stage_b04.PNG_NAME).unlink()
                site = self.make_site(f"site-{mutation}")
                original_index = (site / "index.html").read_bytes()
                with self.assertRaisesRegex(ValueError, message):
                    stage_b04.stage(site, evidence_dir=evidence)
                self.assertEqual((site / "index.html").read_bytes(), original_index)
                self.assertEqual({path.name for path in site.iterdir()}, {"examples", "index.html"})

    def test_double_stage_and_symlink_route_are_refused(self):
        route = stage_b04.stage(self.site)
        before_index = (self.site / "index.html").read_bytes()
        before_gallery = (self.site / "examples/index.html").read_bytes()
        with self.assertRaisesRegex(ValueError, "route is already linked"):
            stage_b04.stage(self.site)
        self.assertEqual((self.site / "index.html").read_bytes(), before_index)
        self.assertEqual((self.site / "examples/index.html").read_bytes(), before_gallery)

        second = self.make_site("symlink-site")
        target = self.root / "outside"
        target.mkdir()
        (second / route).symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "immutable report route already exists"):
            stage_b04.stage(second)
        self.assertEqual((second / "index.html").read_text(), "<!doctype html><html><body></body></html>")

    def test_live_style_changes_do_not_change_historical_source_or_bundle(self):
        baseline = stage_b04.stage(self.site)
        live_style = ROOT / "scripts/reports/figure_style.py"
        read_bytes = Path.read_bytes

        def changed_style(path):
            content = read_bytes(path)
            return content + b"\nPALETTE = ('new-live-color',)\n" if path == live_style else content

        changed_site = self.make_site("changed-live-style")
        with patch.object(Path, "read_bytes", changed_style):
            changed = stage_b04.stage(changed_site)
        self.assertEqual(changed, baseline)
        self.assertEqual((changed_site / (changed + ".zip")).read_bytes(),
                         (self.site / (baseline + ".zip")).read_bytes())
        self.assertEqual((changed_site / changed / "source-root/scripts/reports/figure_style.py").read_bytes(),
                         read_bytes(live_style))

    def test_tampered_selected_historical_style_is_rejected(self):
        historical_style = ROOT / "benchmarks/reporting/mpc11/evidence/figures-60bda0fb/source/figure_style.py"
        read_bytes = Path.read_bytes

        def tampered_style(path):
            content = read_bytes(path)
            return content + b"\n# changed historical source\n" if path == historical_style else content

        with patch.object(Path, "read_bytes", tampered_style):
            with self.assertRaisesRegex(ValueError, "source-anchor Git blob: scripts/reports/figure_style.py"):
                stage_b04.stage(self.site)
        self.assertEqual({path.name for path in self.site.iterdir()}, {"examples", "index.html"})


if __name__ == "__main__":
    unittest.main()
