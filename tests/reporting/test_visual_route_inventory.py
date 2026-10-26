import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts/reports"))
import audit_visual_routes


class VisualRouteInventoryTests(unittest.TestCase):
    def test_known_producers_historical_routes_and_fuel_companion_are_in_inventory(self):
        inventory=audit_visual_routes.build(ROOT)
        self.assertEqual(inventory["schema"],"csl.visual-route-inventory/1")
        producers={entry["source"]:entry for entry in inventory["producers_and_routes"]}
        for source in ("scripts/reports/control_figures.py","scripts/reports/plot.py",
                       "scripts/reports/visual_examples.py","scripts/reports/visual_illustrations.py"):
            self.assertIn(source,producers)
        self.assertEqual(producers["scripts/reports/control_figures.py"]["disposition"],
                         "adopted-shared-quantitative-policy")
        self.assertEqual(producers["scripts/reports/visual_illustrations.py"]["disposition"],
                         "reviewed-static-diagram-exception")
        allowed={"adopted-shared-quantitative-policy","reviewed-static-diagram-exception",
                 "gallery-composition-and-route","publication-validation-or-frozen-route",
                 "deferred-family-specific-migration"}
        self.assertTrue(all(entry["disposition"] in allowed for entry in producers.values()))
        deferred=[entry for entry in producers.values()
                  if entry["disposition"]=="deferred-family-specific-migration"]
        self.assertTrue(deferred)
        self.assertTrue(all(entry["follow_up_issue"]==669 for entry in deferred))
        routes={entry["route"]:entry for entry in inventory["frozen_published_routes"]}
        self.assertGreater(len(routes),40)
        self.assertTrue(any(name.endswith("terminal-projections.svg")
                            for entry in routes.values() for name in entry["assets"]))
        self.assertEqual(inventory["gallery_routes"][0]["route"],"examples/index.html")
        before=ROOT/"docs/examples/fuel-b06-viz06-before.svg"
        self.assertEqual(hashlib.sha256(before.read_bytes()).hexdigest(),
                         "ac5997b750ef20fb80c90b46549a1110cf10f7ff37bbb5f9d72ab1cc44461f20")
        source=json.loads((ROOT/"docs/examples/fuel-b06-viz06-source.json").read_text())
        self.assertEqual(source["provenance"]["scenario_id"],"b06-owner-confirmed-disturbance-v1")
        page=(ROOT/"docs/examples/fuel-b06-viz06.html").read_text()
        self.assertIn("7df01ba3af5e4c46e867e2d737aca56a8f2461af",page)
        self.assertIn("B06 finite-action minimax",page)
        for series in (row for row in source["series"] if row["kind"]=="projection"):
            coordinates=list(zip(*series["points"]))
            for index,values in enumerate(coordinates):
                target=series["target"][index]
                for value in (min(values),max(values),target):
                    label=str(int(value)) if float(value).is_integer() else repr(float(value))
                    self.assertIn(label,page)
        self.assertEqual(len(next(row for row in source["series"] if row["kind"]=="projection")["points"]),1024)
        export=json.loads((ROOT/"docs/examples/fuel-b06-viz06-export.json").read_text())
        self.assertEqual(export["input_sha256"],hashlib.sha256((ROOT/"docs/examples/fuel-b06-viz06-source.json").read_bytes()).hexdigest())
        self.assertEqual(export["style_sha256"],hashlib.sha256((ROOT/"scripts/reports/styles/control-v1.json").read_bytes()).hexdigest())
        for name,digest in export["files"].items():
            self.assertEqual(hashlib.sha256((ROOT/"docs/examples"/name).read_bytes()).hexdigest(),digest,name)
        self.assertEqual(export["before_reference_sha256"],hashlib.sha256(before.read_bytes()).hexdigest())


if __name__=="__main__": unittest.main()
