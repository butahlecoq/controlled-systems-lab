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
        self.assertIn("scripts/reports/env717/capture_two_particle_minimax.py", producers)
        self.assertIn("scripts/reports/stage_env717_two_particle_minimax.py", producers)
        self.assertIn("scripts/reports/env717/capture_homicidal_chauffeur.py", producers)
        self.assertIn("scripts/reports/stage_env717_homicidal_chauffeur.py", producers)
        self.assertEqual(producers["scripts/reports/ext02/render_saved.py"]["disposition"],
                         "analytic-reference-checked-saved-run-renderer")
        self.assertEqual(producers["scripts/reports/exp824/make_report.py"]["follow_up_issue"], 687)
        for source in ("scripts/reports/mpc04/check_max_coordinate.py",
                       "scripts/reports/mpc04/max_coordinate_replanning.py"):
            self.assertEqual(producers[source]["follow_up_issue"], 600)
            self.assertEqual(producers[source]["disposition"],
                             "deferred-family-specific-migration")
        self.assertEqual(producers["scripts/reports/stage_mpc04_max_coordinate.py"]["disposition"],
                         "publication-validation-or-frozen-route")
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
        for source in ("scripts/reports/ext04/render_saved.py", "scripts/reports/ext07/render_saved.py",
                       "scripts/reports/ext04/affine_synthesis_report.py",
                       "scripts/reports/ext07/two_parameter_render_saved.py",
                       "scripts/reports/finite_feedback/render_saved.py"):
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
        for source in ("scripts/reports/mpc01/b04_native_smoke_projection.py",
                       "scripts/reports/mpc01/b04_projection_example.py"):
            self.assertEqual(producers[source]["disposition"],
                             "frozen-report-plot-preserved-with-phase-plane-companion")
            self.assertEqual(producers[source]["companion_ids"], ["b04-native-smoke"])
        self.assertEqual(producers["scripts/reports/b04_native_smoke_companion.py"]["disposition"],
                         "shared-quantitative-policy-companion-renderer")
        self.assertEqual(producers["scripts/reports/visual_illustrations.py"]["disposition"],
                         "reviewed-static-diagram-exception")
        self.assertEqual(producers["scripts/reports/ext03_transform/report.py"]["disposition"],
                         "composes-or-copies-existing-saved-figure")
        self.assertEqual(producers["scripts/reports/mpc09/make_report.py"]["disposition"],
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
        self.assertEqual(producers["benchmarks/reporting/it17_hull/summarize_4d.py"]["disposition"],
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
                 "shared-quantitative-policy-companion-renderer", "gallery-case-content-owner",
                 "frozen-evidence-collector-preserved",
                 "frozen-evidence-collector-preserved-with-gallery-timing-companion",
                 "frozen-evidence-collector-preserved-with-failure-aware-gallery-companion",
                 "frozen-renderer-preserved-with-gallery-companion",
                 "frozen-report-composer-preserved", "publication-identity-map-preserved",
                 "frozen-renderer-preserved-with-failure-aware-gallery-companion",
                 "frozen-envelope-collector-preserved-with-gallery-timing-companion",
                 "frozen-report-plot-preserved-with-saved-relation-companion",
                 "frozen-report-plot-preserved-with-relation-and-timing-companions",
                 "frozen-bundle-composer-preserved", "frozen-report-plot-preserved-with-labeled-projection",
                 "frozen-bundle-composer-preserved-with-saved-timing-companion",
                 "frozen-report-plot-preserved-with-projection-and-timing-companions",
                 "frozen-report-plot-preserved-with-saved-timing-companion",
                 "frozen-report-plot-preserved-with-phase-plane-companion",
                 "frozen-report-plot-preserved-with-gallery-companion",
                 "frozen-repeated-b04-figure-preserved-with-shared-policy-companion",
                 "reviewed: frozen control-family report preserved with shared-policy saved-data companion",
                 "regeneration-entrypoint-preserved-gallery-never-invokes-it",
                 "saved-control-witness-gallery-companion-builder",
                 "reviewed-analytic-diagram-preserved",
                 "analytic-reference-checked-saved-run-renderer"}
        self.assertTrue(all(entry["disposition"] in allowed for entry in producers.values()))
        deferred=[entry for entry in producers.values()
                  if entry["disposition"]=="deferred-family-specific-migration"]
        self.assertTrue(deferred)
        follow_up_counts={number:sum(entry["follow_up_issue"]==number for entry in deferred)
                          for number in (600,684,685,686,687,708,717,824)}
        self.assertEqual(follow_up_counts,
                         {600:2,684:0,685:0,686:0,687:6,708:1,717:17,824:2})
        self.assertEqual(producers["scripts/reports/env717/check_pendulum_terminal.py"]["follow_up_issue"], 717)
        reviewed=[entry for entry in producers.values() if entry.get("role")]
        self.assertEqual(len(reviewed),25)
        self.assertEqual(set(entry["source"] for entry in reviewed),
                         set(audit_visual_routes.control_witness_companions.source_inventory()))
        self.assertTrue(all(entry["follow_up_issue"] in follow_up_counts for entry in deferred))
        routes={entry["route"]:entry for entry in inventory["frozen_published_routes"]}
        self.assertGreater(len(routes),40)
        self.assertEqual(routes["issue824-two-points-box-pilot-v2"]["assets"], ["projections.svg"])
        self.assertEqual(routes["issue824-two-points-box-pilot-v3"]["assets"], ["projections.svg"])
        self.assertEqual(routes["issue824-two-points-box-pilot-v4"]["assets"], ["projections.svg"])
        self.assertEqual(routes["issue824-two-points-zonotope-pilot-v1"]["assets"], ["projections.svg"])
        self.assertEqual(routes["issue824-two-points-zonotope-pilot-v2"]["assets"],
                         ["planar-example.svg", "projections.svg"])
        self.assertEqual(routes["issue824-two-points-ellipsoid-minimax-v1"]["assets"],
                         ["ellipsoid-planar-example.svg", "planar-example.svg", "projections.svg"])
        self.assertEqual(routes["issue824-two-points-ellipsoid-minimax-v1"]["follow_up_issue"],824)
        self.assertEqual(routes["mpc09-two-particle-output-feedback-v1"]["follow_up_issue"],605)
        self.assertEqual(routes["mpc04-max-coordinate-replanning-pilot-20261030"]["assets"],
                         ["trajectory.svg"])
        self.assertEqual(routes["mpc04-max-coordinate-replanning-pilot-20261030"]["follow_up_issue"], 600)
        hull_4d=routes["exp02-it17-hull-4d-simplex-20261028-r1"]
        self.assertEqual(hull_4d["assets"],["2d-visual-companion.svg", "input-projections.svg"])
        self.assertTrue(hull_4d["index_sha256"])
        paired=routes["exp02-paired-profiles-20261027-r1"]
        self.assertIn("reviewed: frozen control-family", paired["disposition"])
        self.assertEqual(paired["companion_route"],
                         "examples/control-witness-v1.html#exp02-ts02-control-family")
        self.assertNotIn("follow_up_issue", paired)
        self.assertTrue(all(entry["disposition"].startswith("deferred: original frozen route-level readability")
                            for entry in routes.values() if entry["route"] != paired["route"]))
        self.assertTrue(all(entry["follow_up_issue"] ==
                            audit_visual_routes.FROZEN_ROUTE_FOLLOW_UP_ISSUES.get(
                                entry["route"],
                                717 if entry["route"].startswith("env717-") else 669)
                            for entry in routes.values() if entry["route"] != paired["route"]))
        self.assertEqual(routes["app03-zonotope-4522855018fa9b0b"]["companion_route"],
                         "examples/app03-zonotope-v1.html")
        self.assertEqual(routes["app01-plan-20261016-22d406fd"]["companion_route"],
                         "examples/app01-plan-timing-v1.html")
        self.assertEqual(routes["ext04-df62c7c6d295e135"]["companion_route"],
                         "examples/ext04-observed-replay-v1.html")
        self.assertEqual(routes["ext04-affine-synthesis-7eadf7c7ecbb2bbd"]["companion_route"],
                         "examples/ext04-affine-synthesis-v1.html")
        self.assertEqual(routes["ext07-hybrid-51d9ee2e89d240eb"]["companion_route"],
                         "examples/ext07-feasible-relation-v1.html")
        self.assertEqual(routes["ext07-hybrid-two-parameter-26f402289a309403"]["companion_route"],
                         "examples/ext07-two-control-family-v1.html")
        self.assertEqual(routes["finite-feedback-a6e96fd96c7ac7cc"]["companion_route"],
                         "examples/finite-feedback-timing-v1.html")
        self.assertEqual(routes["app03-zonotope-4522855018fa9b0b"]["follow_up_issue"], 669)
        self.assertEqual(routes["env717-simple-control-pilot-v1"]["follow_up_issue"], 717)
        self.assertEqual(routes["env717-two-points-pilot-v1"]["follow_up_issue"], 717)
        self.assertEqual(routes["env717-max-coordinate-pilot-v1"]["follow_up_issue"], 717)
        self.assertEqual(routes["env717-sphere-game-pilot-v1"]["follow_up_issue"], 717)
        self.assertEqual(routes["env717-point-on-plane-pilot-v1"]["follow_up_issue"], 717)
        self.assertEqual(routes["env717-time-sphere-pilot-v1"]["follow_up_issue"], 717)
        self.assertEqual(routes["env717-two-particle-minimax-v1"]["follow_up_issue"], 717)
        self.assertEqual(routes["env717-homicidal-chauffeur-v1"]["follow_up_issue"], 717)
        self.assertEqual(routes["env717-multipoint-cost-game-pilot-v1"]["follow_up_issue"], 717)
        self.assertTrue(any(name.endswith("terminal-projections.svg")
                            for entry in routes.values() for name in entry["assets"]))
        self.assertEqual(inventory["gallery_routes"][0]["route"],"examples/index.html")
        gallery_assets=set(inventory["gallery_routes"][0]["assets"])
        self.assertEqual(gallery_assets,{
            "examples.css", "fuel-b06-viz06.html", "fuel-b06-viz06-source.json",
            "adaptive-ode-replay.csv", "adaptive-ode-replay.html",
            "adaptive-ode-replay.json", "adaptive-ode-replay.svg",
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
            "ext04-observed-replay-v1.html", "ext04-observed-replay-v1.svg",
            "ext04-observed-replay-v1.png", "ext04-observed-replay-v1-export.json",
            "ext04-affine-synthesis-v1.html", "ext04-affine-synthesis-v1.svg",
            "ext04-affine-synthesis-v1.png", "ext04-affine-synthesis-v1-export.json",
            "ext07-feasible-relation-v1.html", "ext07-feasible-relation-v1.svg",
            "ext07-feasible-relation-v1.png", "ext07-feasible-relation-v1-export.json",
            "ext07-two-control-family-v1.html", "ext07-two-control-family-v1.svg",
            "ext07-two-control-family-v1.png", "ext07-two-control-family-v1-export.json",
            "finite-feedback-timing-v1.html", "finite-feedback-timing-v1.svg",
            "finite-feedback-timing-v1.png", "finite-feedback-timing-v1-export.json",
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
            *audit_visual_routes.viz10_companion_assets(),
            *audit_visual_routes.control_witness_companions.asset_paths()})

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
