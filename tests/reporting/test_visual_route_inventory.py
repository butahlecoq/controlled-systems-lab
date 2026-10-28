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
        committed=json.loads((ROOT/"scripts/reports/visual-route-inventory.json").read_text())
        self.assertEqual(committed,inventory)
        self.assertEqual(inventory["schema"],"csl.visual-route-inventory/1")
        producers={entry["source"]:entry for entry in inventory["producers_and_routes"]}
        self.assertIn("scripts/reports/env717/check_two_points.py", producers)
        self.assertEqual(producers["scripts/reports/env717/check_two_points.py"]["follow_up_issue"],717)
        self.assertEqual(producers["scripts/reports/env717/check_two_points.py"]["asset_name_literals"],
                         ["projections.svg"])
        self.assertNotIn("policy.svg", producers["scripts/reports/site.py"]["asset_name_literals"])
        self.assertIn("visual.svg", producers["scripts/reports/ext03_transform/report.py"]["asset_name_literals"])
        self.assertNotIn("csl.report.svg", {
            asset for entry in producers.values() for asset in entry["asset_name_literals"]})
        for source in ("scripts/reports/control_figures.py","scripts/reports/plot.py",
                       "scripts/reports/visual_examples.py","scripts/reports/visual_illustrations.py",
                       "scripts/reports/visual_example_geometry.py","scripts/reports/visual_example_hybrid.py"):
            self.assertIn(source,producers)
        for source in ("scripts/reports/visual_example_geometry.py",
                       "scripts/reports/visual_example_hybrid.py"):
            self.assertEqual(producers[source]["disposition"],"gallery-case-content-owner")
        for source in ("benchmarks/reporting/issue6/b07_render_projection.py",
                       "benchmarks/reporting/issue6/b09_render_projection.py"):
            self.assertIn(source,producers)
            self.assertEqual(producers[source]["disposition"],"frozen-renderer-preserved-with-shared-policy-companion")
        for source in ("scripts/reports/b08_exact_report.py", "scripts/reports/exp04/render_saved.py",
                       "scripts/reports/issue3/render_saved.py", "scripts/reports/issue3/validated_saved.py",
                       "scripts/reports/issue4_volterra/render.py", "scripts/reports/issue6/render.py"):
            self.assertEqual(producers[source]["disposition"],
                             "frozen-renderer-preserved-with-shared-policy-companion")
        self.assertEqual(producers["benchmarks/reporting/approximation_pilot/summarize.py"]["disposition"],
                         "reviewed-static-diagram-exception")
        self.assertEqual(producers["scripts/reports/issue422/build_bundle.py"]["disposition"],
                         "composes-or-copies-existing-saved-figure")
        self.assertEqual(producers["scripts/reports/render.py"]["disposition"],
                         "publication-validation-or-frozen-route")
        self.assertEqual(producers["scripts/reports/viz10_plot_companions.py"]["disposition"],
                         "shared-quantitative-policy-companion-renderer")
        viz10_sources = (
            "benchmarks/reporting/approximation_pilot/summarize.py",
            "benchmarks/reporting/issue6/b07_render_projection.py",
            "benchmarks/reporting/issue6/b09_render_projection.py",
            "scripts/reports/b08_exact_report.py", "scripts/reports/exp04/render_saved.py",
            "scripts/reports/issue3/render_saved.py", "scripts/reports/issue3/validated_saved.py",
            "scripts/reports/issue422/build_bundle.py", "scripts/reports/issue4_volterra/render.py",
            "scripts/reports/issue6/render.py", "scripts/reports/render.py")
        for source in viz10_sources:
            self.assertTrue(producers[source]["role_and_disposition_reason"], source)
        self.assertEqual(producers["scripts/reports/control_figures.py"]["disposition"],
                         "adopted-shared-quantitative-policy")
        self.assertEqual(producers["scripts/reports/visual_illustrations.py"]["disposition"],
                         "reviewed-static-diagram-exception")
        self.assertEqual(producers["scripts/reports/ext03_transform/report.py"]["disposition"],
                         "composes-or-copies-existing-saved-figure")
        self.assertEqual(producers["scripts/reports/app02/render_saved.py"]["disposition"],
                         "frozen-renderer-preserved-with-shared-policy-companion")
        self.assertEqual(producers["scripts/reports/app03/render_saved.py"]["disposition"],
                         "frozen-renderer-preserved-with-shared-policy-companion")
        self.assertEqual(producers["scripts/reports/ext01/render_saved.py"]["disposition"],
                         "frozen-renderer-preserved-with-shared-policy-companion")
        self.assertEqual(producers["scripts/reports/ext05/render_saved.py"]["disposition"],
                         "frozen-renderer-preserved-with-shared-policy-companion")
        self.assertEqual(producers["scripts/reports/geometry_figures.py"]["disposition"],
                         "shared-quantitative-policy-companion-renderer")
        self.assertEqual(producers["benchmarks/reporting/it17_hull/summarize.py"]["disposition"],
                         "reviewed-static-diagram-exception")
        for source in ("scripts/reports/geo02/render.py", "scripts/reports/geo03/build_report.py",
                       "scripts/reports/geo04/render.py", "scripts/reports/geo05/render.py",
                       "scripts/reports/geo07/render_saved.py", "scripts/reports/geo07_dependent/render_saved.py",
                       "scripts/reports/geo07_port/render_saved.py", "scripts/reports/geo08/render_saved.py",
                       "scripts/reports/opt04/render.py", "scripts/reports/opt10/render_saved.py",
                       "scripts/reports/opt12_render.py"):
            self.assertEqual(producers[source]["disposition"],
                             "frozen-renderer-preserved-with-shared-policy-companion")
        self.assertEqual(producers["scripts/reports/geometry_opt_companions.py"]["disposition"],
                         "shared-quantitative-policy-companion-renderer")
        allowed={"adopted-shared-quantitative-policy","reviewed-static-diagram-exception",
                 "gallery-composition-and-route","publication-validation-or-frozen-route",
                 "deferred-family-specific-migration", "composes-or-copies-existing-saved-figure",
                 "frozen-renderer-preserved-with-shared-policy-companion",
                 "measurement-collector-preserved-with-saved-data-companion",
                 "shared-quantitative-policy-companion-renderer", "gallery-case-content-owner"}
        self.assertTrue(all(entry["disposition"] in allowed for entry in producers.values()))
        deferred=[entry for entry in producers.values()
                  if entry["disposition"]=="deferred-family-specific-migration"]
        self.assertTrue(deferred)
        follow_up_counts={number:sum(entry["follow_up_issue"]==number for entry in deferred)
                          for number in (684,685,686,687,708,717)}
        self.assertEqual(follow_up_counts,
                         {684:4,685:0,686:18,687:1,708:1,717:6})
        self.assertTrue(all(entry["follow_up_issue"] in follow_up_counts for entry in deferred))
        routes={entry["route"]:entry for entry in inventory["frozen_published_routes"]}
        self.assertGreater(len(routes),40)
        self.assertTrue(all(entry["disposition"].startswith("deferred: original frozen route-level readability")
                            for entry in routes.values()))
        self.assertTrue(all(entry["follow_up_issue"] ==
                            audit_visual_routes.FROZEN_ROUTE_FOLLOW_UP_ISSUES.get(
                                entry["route"],
                                717 if entry["route"].startswith("env717-") else 669)
                            for entry in routes.values()))
        self.assertEqual(routes["exp02-paired-profiles-20261027-r1"]["follow_up_issue"], 686)
        self.assertEqual(routes["app03-zonotope-4522855018fa9b0b"]["companion_route"],
                         "examples/app03-zonotope-v1.html")
        self.assertEqual(routes["app01-plan-20261016-22d406fd"]["companion_route"],
                         "examples/app01-plan-timing-v1.html")
        self.assertEqual(routes["app03-zonotope-4522855018fa9b0b"]["follow_up_issue"], 669)
        self.assertEqual(routes["env717-simple-control-pilot-v1"]["follow_up_issue"], 717)
        self.assertEqual(routes["env717-two-points-pilot-v1"]["follow_up_issue"], 717)
        self.assertEqual(routes["env717-max-coordinate-pilot-v1"]["follow_up_issue"], 717)
        self.assertTrue(any(name.endswith("terminal-projections.svg")
                            for entry in routes.values() for name in entry["assets"]))
        self.assertEqual(inventory["gallery_routes"][0]["route"],"examples/index.html")
        gallery_assets=set(inventory["gallery_routes"][0]["assets"])
        self.assertEqual(gallery_assets,{
            "examples.css", "fuel-b06-viz06.html", "fuel-b06-viz06-source.json",
            "fuel-b06-viz06-export.json", "fuel-b06-viz03.html", "fuel-b06-viz06-before.svg",
            "fuel-b06-viz06-flow.svg", "fuel-b06-viz06-flow.png",
            "fuel-b06-viz06-stock.svg", "fuel-b06-viz06-stock.png",
            "fuel-b06-viz06-trajectory.svg", "fuel-b06-viz06-trajectory.png",
            "fuel-b06-viz06-timing.svg", "fuel-b06-viz06-timing.png",
            "lotka-volterra-sampled-v1.html", "lotka-volterra-sampled-v1.svg",
            "lotka-volterra-sampled-v1.png", "lotka-volterra-sampled-v1-export.json",
            "app02-diamond-v1.html", "app02-diamond-v1.svg", "app02-diamond-v1.png",
            "app02-diamond-v1-export.json", "app04-square-v1.html", "app04-square-v1.svg",
            "app04-square-v1.png", "app04-square-v1-export.json",
            "app03-zonotope-v1.html", "app03-zonotope-v1.svg",
            "app03-zonotope-v1.png", "app03-zonotope-v1-export.json",
            "ext01-b08-timing-v1.html", "ext01-b08-timing-v1.svg",
            "ext01-b08-timing-v1.png", "ext01-b08-timing-v1-export.json",
            "ext05-states-v1.html", "ext05-states-v1.svg", "ext05-states-v1.png",
            "ext05-states-v1-export.json",
            "app01-plan-timing-v1.html", "app01-plan-timing-v1.svg",
            "app01-plan-timing-v1.png", "app01-plan-timing-v1-export.json",
            "mpc03-open-loop-pilot-v1/index.html",
            "mpc03-open-loop-pilot-v1/record.json",
            "mpc03-open-loop-pilot-v1/pilot-output.json",
            "mpc03-open-loop-pilot-v1/build-provenance.json",
            "mpc03-open-loop-pilot-v1/disturbance-tube.svg",
            "mpc03-b08-l04-miQCP-v1/index.html",
            "mpc03-b08-l04-miQCP-v1/record.json",
            "mpc03-b08-l04-miQCP-v1/solver-output.json",
            "mpc03-b08-l04-miQCP-v1/independent-oracle.json",
            "mpc03-b08-l04-miQCP-v1/disturbance-tube.svg",
            *audit_visual_routes.geometry_companion_assets(),
            *audit_visual_routes.viz10_companion_assets()})
        self.assertEqual((ROOT/"docs/examples/examples.css").read_bytes(),
                         (ROOT/"scripts/reports/visual_examples.css").read_bytes())
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
