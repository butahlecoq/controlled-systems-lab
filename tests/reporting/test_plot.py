"""Real pinned producer -> strict consumer -> offline bundle oracle."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[2]
os.environ.setdefault("MPLCONFIGDIR",str(ROOT/"build/html01/mpl-config"))
sys.path.insert(0,str(ROOT/"scripts/reports"))
import report_data as data

PROLOG='<?xml version="1.0" encoding="utf-8" standalone="no"?>\n<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN"\n  "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">\n'


class PlotTests(unittest.TestCase):
    def setUp(self):
        if importlib.util.find_spec("matplotlib") is None:
            self.skipTest("separate pinned reporting environment required; plot did not run")
        import matplotlib
        self.assertEqual(matplotlib.__version__,"3.11.2")
        self.assertIsNotNone(importlib.util.find_spec("plot"),"plot adapter missing")
        self.plot=__import__("plot")

    def test_real_pinned_drawing_roundtrips_renderer_site_and_zip_final_bytes(self):
        import render
        # Avoid Python's already-loaded stdlib site module.
        spec=importlib.util.spec_from_file_location("report_site",ROOT/"scripts/reports/site.py")
        self.assertTrue(Path(spec.origin).is_file(),"site adapter missing")
        site=importlib.util.module_from_spec(spec);spec.loader.exec_module(site)
        view=data.load_view(ROOT/"tests/reporting/fixtures/view-v1.json")
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            metadata=self.plot.plot(view,root/"figures")
            final=(root/"figures/latency.svg").read_bytes()
            self.assertFalse(final.startswith(b'<?xml'))
            self.assertNotIn(b'<!DOCTYPE',final)
            self.assertNotIn(b'<metadata',final)
            self.assertEqual(hashlib.sha256(final).hexdigest(),metadata["files"]["latency.svg"])
            series=metadata["series"]["public_run"][0]
            self.assertEqual(series["values"],[10,20,30,40,50])
            self.assertEqual(series["summary"],{"median":30,"min":10,"max":50,"count":5})
            bundle=render.render(view,root/view["report_id"],root/"figures")
            site.validate_bundle(bundle,allow_test=True)
            archive=site.make_zip(bundle,root/"offline.zip",allow_test=True)
            with zipfile.ZipFile(archive) as saved:
                self.assertEqual(saved.read(view["report_id"]+"/latency.svg"),final)
                self.assertEqual(len(saved.namelist()),14)
            self.assertIn(final.decode(),(bundle/"index.html").read_text(encoding="utf-8"))
            with self.assertRaises(ValueError): site.validate_bundle(bundle)
            summary=(bundle/"summary.csv").read_bytes()
            (bundle/"summary.csv").write_bytes(summary.replace(b",ns,",b",ms,",1))
            manifest=data.parse_json((bundle/"manifest.json").read_text(encoding="utf-8"))
            manifest["files"]["summary.csv"]=data.file_digest(bundle/"summary.csv")
            (bundle/"manifest.json").write_text(json.dumps(manifest),encoding="utf-8")
            with self.assertRaises(ValueError): site.validate_bundle(bundle,allow_test=True)
            (bundle/"summary.csv").write_bytes(summary)
            manifest["files"]["summary.csv"]=data.file_digest(bundle/"summary.csv")
            (bundle/"manifest.json").write_text(json.dumps(manifest),encoding="utf-8")
            (bundle/"latency.svg").write_bytes(final.replace(b'<svg',b'<svg data-tamper="1"',1))
            with self.assertRaises(ValueError): site.validate_bundle(bundle,allow_test=True)

    def test_default_metadata_and_unnormalized_prolog_are_rejected(self):
        import matplotlib.pyplot as plt
        fig,ax=plt.subplots();ax.plot([0,1],[0,1])
        try:
            raw=io.StringIO();fig.savefig(raw,format="svg")
            content=raw.getvalue()
            self.assertTrue(content.startswith(PROLOG))
            with self.assertRaises(ValueError): data.validate_svg(content.encode())
            with self.assertRaises(ValueError): data.validate_svg(content[len(PROLOG):].encode())
            clean=io.StringIO()
            fig.savefig(clean,format="svg",metadata={"Date":None,"Format":None,"Type":None,"Creator":None})
            normalized=self.plot.normalize_owned_svg(clean.getvalue())
            self.assertNotEqual(hashlib.sha256(normalized).hexdigest(),hashlib.sha256(clean.getvalue().encode()).hexdigest())
            for altered in (clean.getvalue().replace('svg11.dtd','evil.dtd'), 'x'+clean.getvalue(),
                            clean.getvalue().replace('<svg','<!ENTITY x "bad"><svg',1)):
                with self.assertRaises(ValueError): self.plot.normalize_owned_svg(altered)
        finally: plt.close(fig)


if __name__=="__main__": unittest.main()
