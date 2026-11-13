"""Inventory report/gallery visual producers and frozen published figure routes."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re

import control_witness_companions


ROOT = Path(__file__).resolve().parents[2]
VISUAL_SIGNAL = re.compile(r"<svg|savefig\s*\(|write_image\s*\(|\.svg\b|\.png\b|render_svg", re.I)
ASSET_NAME = re.compile(r"(?<![A-Za-z0-9_.-])[A-Za-z0-9_.-]+\.(?:svg|png)(?![A-Za-z0-9_.-])")
MIGRATION_ISSUES = {
    "approximation-and-extensions": 684,
    "geometry-and-optimization": 685,
    "control-strategy-and-witness": 686,
    "historical-and-benchmarks": 687,
}
FOLLOW_UP_ISSUE_OVERRIDES = {
    "scripts/reports/exp824/make_ellipsoid_minimax_report.py": 824,
}
COMPOSED_SAVED_ROUTES = {
    "scripts/reports/btulshor/capture.py",
    "scripts/reports/mpc01/summarize_per_attempt.py",
    "scripts/reports/exp824/make_nominal_report.py",
    "scripts/reports/ext03_transform/report.py",
    "scripts/reports/ext04/continuous_report.py",
    "scripts/reports/ext04/h_policy_report.py",
    "scripts/reports/issue422/build_bundle.py",
    "scripts/reports/stage_env717_unlimited_bolza.py",
    "scripts/reports/stage_mpc03.py",
    "scripts/reports/stage_mpc03_b08.py",
    "scripts/reports/mpc05/make_report.py",
    "scripts/reports/mpc05/reference.py",
    "scripts/reports/mpc09/make_report.py",
    "scripts/reports/visual_example_fuel_layers.py",
}
ASSET_NAME_LITERAL_OVERRIDES = {
    # The B04 renderer selects one of these stems with a runtime flag.
    "scripts/reports/mpc01/b04_native_smoke_projection.py": [
        "b04-repeated-projections.svg", "native-smoke-projections.svg"],
}
PINNED_HISTORICAL_SOURCE_SNAPSHOTS = {
    "scripts/reports/lotka_volterra_sampled_frozen_321ac099.py": {
        "disposition": "pinned-historical-source-snapshot",
        "role_and_disposition_reason": (
            "Exact historical producer bytes retained only to authenticate the existing sampled Lotka–Volterra "
            "example; this source snapshot makes no full-reachability claim and has no algorithm-family deferral."),
        "source_snapshot": {
            "source_commit": "3be2f4257eeb4d00a81b3275ba9f576fb1332e87",
            "source_path": "scripts/reports/lotka_volterra_sampled.py",
            "sha256": "321ac099e8185c8b1b9a76af9859c9b818682b429ba705f1410a19d648238f1c",
        },
        "companion_ids": ["lotka-volterra-sampled-20261023"],
    },
}
FROZEN_DIAGRAM_EXCEPTIONS = {
    "benchmarks/reporting/approximation_pilot/summarize.py",
    "benchmarks/reporting/mpc08_explicit/explicit_double_integrator.py",
    "benchmarks/reporting/mpc08_explicit/explicit_nonunique_double_integrator.py",
}
PUBLICATION_EXPORT_ROUTES = {
    "scripts/reports/package_feedback_history.py",
    "scripts/reports/package_history_functional.py",
    "scripts/reports/stage_b04_source_moments.py",
    "scripts/reports/stage_btulshor.py",
    "scripts/reports/btulshor/render.py",
    "scripts/reports/stage_mpc06_offline_costs.py",
    "scripts/reports/stage_mpc07_comparison.py",
    "scripts/reports/stage_mpc10_comparison.py",
    "scripts/reports/stage_mpc08_complete.py",
    "scripts/reports/render.py", "scripts/reports/mpc05/check_smoke.py",
    "scripts/reports/exp824/finalize_limited_report.py",
    "scripts/reports/augment_pages_bundle.py",
    "scripts/reports/stage_mpc11_mesh_timing.py",
    "scripts/reports/stage_buryatia_dim4.py",
    "benchmarks/reporting/mpc11/evidence/figures-60bda0fb/source/figures.py",
}
VIZ10_ROLE_REASONS = {
    "scripts/reports/stage_buryatia_dim4.py":
        "Authenticates the source-bound four-state affine capture and copies its raw record, model manifest, lesson and derived terminal projection into the Pages gallery; no native propagation or numerical analysis runs during staging.",
    "scripts/reports/stage_b04_source_moments.py":
        "Verifies exact source-candidate moment and all-stage set certificates, then copies source-bound saved physical-plane figures; no original program, optimization or rendering runs during staging.",
    "scripts/reports/b04_source_moments/figures.py":
        "Draws all 17 exact source-candidate forward, backward and intersection sets in the two physical state planes, with one labelled optimal witness and shared quantitative styles; it makes no historical-run or timing claim.",
    "scripts/reports/stage_mpc06_offline_costs.py":
        "Authenticates saved canonical tube-construction clocks and exact consumer identities, then copies the existing invariant figure; no solver, measurement or plotting runs during staging.",
    "scripts/reports/stage_mpc11_mesh_timing.py":
        "Rechecks immutable mesh and repeated-controller archives, builds labelled saved-data study companions and copies complete source/raw inputs; no optimization or integration runs.",
    "scripts/reports/stage_mpc07_comparison.py":
        "Authenticates both robust-policy capture families and copied two-state figures; rechecks saved exact policies without optimization or plotting.",
    "scripts/reports/stage_mpc10_comparison.py":
        "Authenticates the finite/mixed/hybrid capture, reading receipt and copied two-dimensional path figures; no solver or renderer runs during staging.",
    "benchmarks/reporting/mpc10/figures.py":
        "Plots authenticated saved two-dimensional native hybrid paths with distinct parallel-edge identities and shared quantitative styles; no family claim follows from sampled anchors.",
    "scripts/reports/mpc06_online/render.py":
        "Renders checked-source-bound native outcomes and saved actual paths; the shared Matplotlib publication companion remains in issue #602. This is not a benchmark producer.",
    "scripts/reports/stage_mpc08_complete.py":
        "Rechecks both immutable MPC08 captures and copies their saved labelled figures into one bounded report/example; it runs no solver or figure producer.",
    "benchmarks/reporting/mpc08_explicit/capture_horizon_regions.py":
        "Draws independently checked exact original-quadratic endpoint cells for matched N2/4/8 with shared numeric axes; full optimizer fibers and native resource refusals remain separate products.",
    "benchmarks/reporting/mpc08_explicit/capture_exact_regions.py":
        "Draws exact checked fixture regions and nominal/robust predecessors with shared numeric axes; numerical native observations remain separate from whole-set proof authority.",
    "benchmarks/reporting/mpc08_explicit/explicit_double_integrator.py":
        "Generates one exact 2D critical-region diagram from the rational fixture, with labelled initial and terminal coordinates; it is not a general plotting path.",
    "benchmarks/reporting/mpc08_explicit/explicit_nonunique_double_integrator.py":
        "Draws the exact initial-state rectangle and one full two-control optimal fiber with a distinct minimum-norm selector; solver candidates are not presented as complete-family evidence.",
    "benchmarks/reporting/approximation_pilot/summarize.py":
        "Draws a reviewed static fixture diagram from authored input shapes and area formulas; it does not plot a saved run record.",
    "benchmarks/reporting/issue6/b07_render_projection.py":
        "Frozen B07 report producer for saved four-state terminal rows; the shared-policy companion plots x1/x3 and x2/x4 rows directly without constructing a hull.",
    "benchmarks/reporting/issue6/b09_render_projection.py":
        "Frozen B09 report producer and nonlinear replay display; the shared-policy companion plots stored terminal rows and replay endpoints separately without recomputing the projected hull.",
    "scripts/reports/b08_exact_report.py":
        "Produces a quantitative plot from saved fresh-process durations; the companion reads the immutable records and separates the excluded warmup.",
    "scripts/reports/exp04/render_saved.py":
        "Validates saved EXP-04 records and plots two-state replay paths; the companion retains the physical coordinates and discloses independent unit scales.",
    "scripts/reports/issue3/render_saved.py":
        "Validates and plots saved finite-catalogue timing summaries; the companion shows saved median and min/max values without recollection.",
    "scripts/reports/issue3/validated_saved.py":
        "Validates a frozen capture and draws its authored analytic 2D fixture; the companion preserves the two plan points and target as an illustration.",
    "scripts/reports/issue422/build_bundle.py":
        "Assembles a report bundle by copying the pre-existing fixed-plan SVG; it does not create or transform plot data.",
    "scripts/reports/issue4_volterra/render.py":
        "Validates and publishes a saved interval certificate with error-box artwork; the companion reads endpoint strings from the frozen record and does not rerun the checker.",
    "scripts/reports/issue6/render.py":
        "Publishes the saved B06 four-state projection; a VIZ-03 shared-policy companion already provides labeled x1/x3 flow and x2/x4 stock projections.",
    "scripts/reports/mpc06/render_tube_objective.py":
        "Renders the saved exact-rational tube-policy witness in a two-dimensional position/velocity projection; it does not rerun optimization or measure performance.",
    "scripts/reports/render.py":
        "Generic report exporter validates and copies a supplied saved figure; it does not produce quantitative plot data.",
    "benchmarks/reporting/closed_loop/run_closed_loop.py":
        "Runs source-bound observed-state episodes and can render a completed saved attempt without another policy query; phase plots show the single observed trajectory and do not synthesize reachable sets.",
    "scripts/reports/render_closed_loop_pilot.py":
        "Validates and renders the fixed source-bound attempt, replay, and coverage records into a versioned standalone report and 2D example; it does not execute a solver or plant.",
}
SAVED_COMPANION_ROUTES = {
    "scripts/reports/mpc01/summarize_repeated_comparison.py",
    "scripts/reports/app02/render_saved.py",
    "scripts/reports/app03/render_saved.py",
    "scripts/reports/app04/render_saved.py",
    "scripts/reports/ext01/render_saved.py",
    "scripts/reports/ext04/render_saved.py",
    "scripts/reports/ext04/affine_synthesis_report.py",
    "scripts/reports/ext05/render_saved.py",
    "scripts/reports/ext07/render_saved.py",
    "scripts/reports/ext07/two_parameter_render_saved.py",
    "scripts/reports/finite_feedback/render_saved.py",
    "scripts/reports/lotka_volterra_sampled.py",
    "scripts/reports/geo02/render.py",
    "scripts/reports/geo03/build_report.py",
    "scripts/reports/geo04/render.py",
    "scripts/reports/geo05/render.py",
    "scripts/reports/geo07/render_saved.py",
    "scripts/reports/geo07_dependent/render_saved.py",
    "scripts/reports/geo07_port/render_saved.py",
    "scripts/reports/geo08/render_saved.py",
    "scripts/reports/opt04/render.py",
    "scripts/reports/opt10/render_saved.py",
    "scripts/reports/opt12_render.py",
    "scripts/reports/b08_exact_report.py",
    "scripts/reports/exp04/render_saved.py",
    "scripts/reports/issue3/render_saved.py",
    "scripts/reports/issue3/validated_saved.py",
    "scripts/reports/issue4_volterra/render.py",
    "scripts/reports/issue6/render.py",
    "benchmarks/reporting/issue6/b07_render_projection.py",
    "benchmarks/reporting/issue6/b09_render_projection.py",
}
SAVED_DATA_COMPANION_COLLECTORS = {"scripts/reports/app01/collect.py"}
SAVED_DATA_ILLUSTRATION_RENDERERS = {
    "scripts/reports/buryatia/render_2d.py": (
        "Renders all saved source-qualified native affine 2D stages and a terminal overlay; the factor matrix is "
        "retained in each ellipse record and the sampled boundary is checked against that represented set. "
        "The page makes no nonlinear, feedback, minimax or timing claim."),
    "scripts/reports/plot_feedback_history.py": "Projects complete saved full-state H, generator and ellipsoid F/B/I sets from one observed query, preserving every stage and physical coordinate order with shared quantitative axis styling.",
    "scripts/reports/render_history_functional.py": "Renders corrected labels on saved affine-history state and control records using the existing closed-loop plotter; it does not execute a controller or solver.",
    "scripts/reports/render_issue944_each_choice.py": (
        "Renders the immutable source-bound Strategy A choice records and independent recovered-history values "
        "with shared screen/print tokens; it runs no solver and makes no full-family or performance claim."),
    "scripts/reports/render_issue944_postfix.py": (
        "Renders the source-bound post-fix Strategy A choice records and independent recovered-history values "
        "with shared screen/print tokens; it runs no solver and makes no full-family or performance claim."),
    "scripts/reports/native_terminal_cost_example.py": (
        "Renders the source-bound before/after native diagnostic exchanges and analytic terminal-cost contours "
        "with shared screen/print tokens; it runs no solver and makes no full-episode or performance claim."),
    "scripts/reports/nominal_tube_figure.py": (
        "Renders committed full-state H rows F, B and I from the original 30-stage frozen-affine Lotka capture; "
        "the numerical half-plane clipping keeps the saved coefficients and checks plotted vertices against raw rows. "
        "A saved nonlinear NMPC trajectory is overlaid separately. This does not claim nonlinear reachable sets or "
        "global control optimality."),
}
SAVED_DATA_COMPANION_RENDERERS = {
    "benchmarks/reporting/closed_loop/run_closed_loop.py",
    "scripts/reports/recorded_closed_loop_figures.py",
    "scripts/reports/render_closed_loop_pilot.py",
    "scripts/reports/source_index_figure.py",
    "scripts/reports/mpc06_online/render.py",
    "scripts/reports/mpc06_delivery/figures.py",
    "scripts/reports/render_adaptive_ode_example.py",
    "scripts/reports/qhull_highs_strategy_a_example.py",
    "scripts/reports/ext02/render_saved.py",
    "scripts/reports/mpc06/render_tube_objective.py",
    "scripts/reports/env717/check_unlimited_bolza.py",
    "benchmarks/reporting/review05/render_profile_matrix.py",
    "benchmarks/reporting/review05/render_dimension_ladder.py",
    "benchmarks/reporting/review05/render_constraint_ladder.py",
}
FROZEN_COMPANIONS = {
    "mpc06-online-anchor-v1": "mpc06-complete-6b7059d62473d32d4210/index.html",
    "mpc06-online-anchor-checked-v2": "mpc06-complete-6b7059d62473d32d4210/index.html",
    "mpc06-online-anchor-portable-v3": "mpc06-complete-6b7059d62473d32d4210/index.html",
    "mpc06-completion-v1": "mpc06-complete-6b7059d62473d32d4210/index.html",
    "mpc06-completion-v2": "mpc06-complete-6b7059d62473d32d4210/index.html",
    "review05-family-query-20261110-3b98f5b0": "review05-family-query-d6af180b0e398d78ebd2/index.html",
    "review05-build-phases-20261110-468cc0eb": "review05-family-query-d6af180b0e398d78ebd2/index.html",
    "app01-plan-20261016-22d406fd": "examples/app01-plan-timing-v1.html",
    "exp02-paired-profiles-20261027-r1": "examples/control-witness-v1.html#exp02-ts02-control-family",
    "mpc03-open-loop-pilot-v1": "examples/index.html",
    "mpc03-b08-l04-miQCP-v1": "examples/index.html",
    "mpc08-explicit-nonunique-v1": "examples/index.html",
    "app02-box-8ff979de60ea9d22": "examples/app02-diamond-v1.html",
    "app03-zonotope-4522855018fa9b0b": "examples/app03-zonotope-v1.html",
    "app04-ellipsoid-fd302c34092f8b19": "examples/app04-square-v1.html",
    "ext01-fixed-plan-20261016-11b7bc74": "examples/ext01-b08-timing-v1.html",
    "ext04-df62c7c6d295e135": "examples/ext04-observed-replay-v1.html",
    "ext04-affine-synthesis-7eadf7c7ecbb2bbd": "examples/ext04-affine-synthesis-v1.html",
    "ext07-hybrid-51d9ee2e89d240eb": "examples/ext07-feasible-relation-v1.html",
    "ext07-hybrid-two-parameter-26f402289a309403": "examples/ext07-two-control-family-v1.html",
    "ext05-discretization-a40ba9647cc023dc": "examples/ext05-states-v1.html",
    "finite-feedback-a6e96fd96c7ac7cc": "examples/finite-feedback-timing-v1.html",
    "lotka-volterra-sampled-20261023": "examples/lotka-volterra-sampled-v1.html",
}
FROZEN_REVIEWED_ROUTES = {
    "review05-family-query-20261110-3b98f5b0":
        "reviewed: root inspected the shared-policy scalar control projection and recorded state paths; exact family coverage is checked separately",
    "exp02-paired-profiles-20261027-r1":
        "reviewed: frozen control-family report preserved with shared-policy saved-data companion",
}
FROZEN_ROUTE_FOLLOW_UP_ISSUES = {
    "mpc06-completion-v1": 602,
    "mpc06-completion-v2": 602,
    "issue824-two-points-nominal-v1": 824,
    "issue824-two-points-nominal-v2": 824,
    "issue824-two-points-zonotope-minimax-v1": 824,
    "issue824-two-points-zonotope-minimax-v2": 824,
    "issue824-two-points-parallelotope-pilot-v1": 824,
    "issue824-two-points-ellipsoid-minimax-v1": 824,
    "issue824-two-points-ellipsoid-minimax-v2": 824,
    "issue824-two-points-matched-minimax-v1": 824,
    "issue824-two-points-matched-minimax-resource-v1": 824,
    "mpc04-max-coordinate-replanning-pilot-20261030": 600,
    "mpc08-explicit-nonunique-v1": 604,
    # This report's phase-plane figure is owned and reviewed with MPC-05.
    "mpc05-causal-tree-pilot-v1": 601,
    "mpc05-causal-tree-pilot-v2": 601,
    "mpc09-two-particle-output-feedback-v1": 605,
    # The paired synthesis profile is a control-family report and its current
    # readability follow-up belongs to the active control/witness migration.
    "exp02-paired-profiles-20261027-r1": 686,
    "exp02-it17-a44-paper-order-20261028-r3": 94,
    "exp02-it17-dyadic-250-20261029-r1": 94,
}


def migration_issue(source: str) -> int:
    if source == "scripts/reports/exp824/make_zonotope_minimax_report.py":
        return 824
    if "/mpc04/" in source or source == "scripts/reports/stage_mpc04_max_coordinate.py":
        return 600
    if "/mpc09/" in source or source == "scripts/reports/stage_mpc09_output_feedback.py":
        return 605
    if "/mpc01/" in source:
        return MIGRATION_ISSUES["control-strategy-and-witness"]
    if "/mpc06/" in source:
        return MIGRATION_ISSUES["control-strategy-and-witness"]
    if source == "scripts/reports/fuel_reachability_layers.py":
        return 708
    if "/env717/" in source:
        return 717
    if "/viz04/" in source:
        return MIGRATION_ISSUES["control-strategy-and-witness"]
    if any(token in source for token in ("/app0", "/ext", "/finite_feedback", "/lotka_volterra")):
        return MIGRATION_ISSUES["approximation-and-extensions"]
    if source == "scripts/reports/exp03/render_two_points_approximation.py":
        return 717
    if "/exp03/" in source:
        return MIGRATION_ISSUES["approximation-and-extensions"]
    if any(token in source for token in ("/geo", "/opt", "/it17_hull")):
        return MIGRATION_ISSUES["geometry-and-optimization"]
    if "/syn" in source or "/ts01" in source:
        return MIGRATION_ISSUES["control-strategy-and-witness"]
    return MIGRATION_ISSUES["historical-and-benchmarks"]


def source_inventory(root: Path) -> list[dict]:
    entries = []
    reviewed = control_witness_companions.source_inventory()
    found = set()
    bases = (root / "scripts/reports", root / "benchmarks/reporting")
    for base in bases:
        for path in sorted(base.rglob("*.py")):
            relative = path.relative_to(root)
            if path.name in {"audit_visual_routes.py", "pages_route_retirement.py"} or any(
                    part.startswith("test") for part in relative.parts):
                continue
            source = path.read_text(encoding="utf-8")
            matches = VISUAL_SIGNAL.findall(source)
            relative = relative.as_posix()
            if not matches and relative not in reviewed:
                continue
            tree = ast.parse(source, filename=relative)
            assets = sorted({asset for node in ast.walk(tree)
                             if isinstance(node, ast.Constant) and isinstance(node.value, str)
                             for asset in ASSET_NAME.findall(node.value)})
            assets = sorted(set(assets) | set(ASSET_NAME_LITERAL_OVERRIDES.get(relative, ())))
            if relative in PINNED_HISTORICAL_SOURCE_SNAPSHOTS:
                spec = PINNED_HISTORICAL_SOURCE_SNAPSHOTS[relative]
                if hashlib.sha256(path.read_bytes()).hexdigest() != spec["source_snapshot"]["sha256"]:
                    raise ValueError("pinned historical producer snapshot bytes differ: " + relative)
                entries.append({"source": relative, "signal_count": len(matches),
                                "asset_name_literals": assets, **spec})
                continue
            if relative in reviewed:
                spec = reviewed[relative]
                found.add(relative)
                entries.append({"source": relative, "signal_count": len(matches),
                                "asset_name_literals": assets,
                                "role": spec.role,
                                "disposition": spec.disposition,
                                "companion_ids": list(spec.companion_ids)})
                continue
            if relative in COMPOSED_SAVED_ROUTES:
                disposition = "composes-or-copies-existing-saved-figure"
            elif relative in SAVED_DATA_COMPANION_COLLECTORS:
                disposition = "measurement-collector-preserved-with-saved-data-companion"
            elif relative in SAVED_DATA_ILLUSTRATION_RENDERERS:
                disposition = "saved-data-illustration-renderer"
            elif relative in SAVED_DATA_COMPANION_RENDERERS:
                disposition = "analytic-reference-checked-saved-run-renderer"
            elif relative in FROZEN_DIAGRAM_EXCEPTIONS:
                disposition = "reviewed-static-diagram-exception"
            elif relative in PUBLICATION_EXPORT_ROUTES:
                disposition = "publication-validation-or-frozen-route"
            elif relative in SAVED_COMPANION_ROUTES:
                disposition = "frozen-renderer-preserved-with-shared-policy-companion"
            elif relative.endswith(("/geometry_figures.py", "/approx_extension_companions.py",
                                    "/geometry_opt_companions.py", "/viz10_plot_companions.py")):
                disposition = "shared-quantitative-policy-companion-renderer"
            elif relative in {"scripts/reports/b04_source_moments/figures.py",
                              "scripts/reports/stage_projection_figures.py",
                              "benchmarks/reporting/review05/render_family_query.py",
                              "benchmarks/reporting/mpc11/figures.py",
                              "benchmarks/reporting/mpc08_explicit/capture_exact_regions.py",
                              "benchmarks/reporting/mpc08_explicit/capture_horizon_regions.py",
                              "benchmarks/reporting/mpc07/report.py",
                              "benchmarks/reporting/mpc07/online/figures.py",
                              "benchmarks/reporting/mpc10/figures.py",
                              "benchmarks/reporting/mpc11/study_report.py"}:
                disposition = "adopted-shared-quantitative-policy"
            elif relative.endswith("/control_witness_companions.py"):
                disposition = "saved-control-witness-gallery-companion-builder"
            elif relative in {"benchmarks/reporting/it17_hull/summarize.py",
                              "benchmarks/reporting/it17_hull/summarize_3d.py",
                              "benchmarks/reporting/it17_hull/summarize_4d.py"}:
                disposition = "reviewed-static-diagram-exception"
            elif relative in {"scripts/reports/mpc03/b08_miqcp.py",
                              "scripts/reports/mpc03/b08_report.py"}:
                disposition = "adopted-shared-quantitative-policy"
            elif relative.endswith("/control_figures.py") or relative.endswith("/plot.py"):
                disposition = "adopted-shared-quantitative-policy"
            elif relative.endswith("/visual_illustrations.py"):
                disposition = "reviewed-static-diagram-exception"
            elif relative in {"scripts/reports/visual_example_geometry.py",
                              "scripts/reports/visual_example_hybrid.py",
                              "scripts/reports/feedback_geometry_example.py"}:
                disposition = "gallery-case-content-owner"
            elif relative.endswith("/visual_examples.py"):
                disposition = "gallery-composition-and-route"
            elif ("registered_reports.py" in path.name or path.name.startswith(("stage_", "validate_"))
                  or "publication_policy" in path.name
                  or path.name in {"site.py", "report_data.py", "registered_report_policies.py",
                                   "schema3_publication_policies.py"}):
                disposition = "publication-validation-or-frozen-route"
            else:
                disposition = "deferred-family-specific-migration"
            entries.append({"source": relative, "signal_count": len(matches),
                            "asset_name_literals": assets, "disposition": disposition,
                            **({"role_and_disposition_reason": VIZ10_ROLE_REASONS[relative]}
                               if relative in VIZ10_ROLE_REASONS else
                               {"role_and_disposition_reason": SAVED_DATA_ILLUSTRATION_RENDERERS[relative]}
                               if relative in SAVED_DATA_ILLUSTRATION_RENDERERS else {}),
                            **({"follow_up_issue": FOLLOW_UP_ISSUE_OVERRIDES.get(
                                    relative, migration_issue(relative))}
                               if disposition == "deferred-family-specific-migration" else {})})
    missing = set(reviewed) - found
    if missing:
        raise ValueError("reviewed VIZ-09 sources missing from visual scan: " + ", ".join(sorted(missing)))
    return entries


def frozen_routes(root: Path) -> list[dict]:
    base = root / "reports/algorithm-results"
    routes = []
    for page in sorted(base.rglob("index.html")):
        bundle = page.parent
        figures = sorted(path for path in bundle.iterdir()
                         if path.is_file() and path.suffix.lower() in {".svg", ".png"})
        if not figures:
            continue
        route = bundle.relative_to(base).as_posix()
        entry = {"route": route, "source_bundle": route,
                 "assets": [path.name for path in figures],
                 "index_sha256": hashlib.sha256(page.read_bytes()).hexdigest(),
                 "disposition": FROZEN_REVIEWED_ROUTES.get(
                     route, "deferred: original frozen route-level readability review remains; companion availability is listed separately")}
        if route not in FROZEN_REVIEWED_ROUTES:
            entry["follow_up_issue"] = FROZEN_ROUTE_FOLLOW_UP_ISSUES.get(
                route, 717 if route.startswith("env717-") else 669)
        if route in FROZEN_COMPANIONS:
            entry["companion_route"] = FROZEN_COMPANIONS[route]
        routes.append(entry)
    return routes


def build(root: Path = ROOT) -> dict:
    root = Path(root).resolve()
    return {"schema": "csl.visual-route-inventory/1",
            "policy": {"id": "csl-report-quantitative-v1",
                       "solution": "Matplotlib 3.11.2 static SVG/PNG plus passive hand-authored SVG for reviewed diagrams",
                       "no_solver_or_geometry_runs": True},
            "source_discovery": {"method": "deterministic text scan of scripts/reports/**/*.py and benchmarks/reporting/**/*.py for SVG/PNG/savefig/write_image/render_svg signals",
                                 "review_required": "signal hits are candidate producers or route validators; inspect the role before migration"},
            "producers_and_routes": source_inventory(root),
            "frozen_published_routes": frozen_routes(root),
            "gallery_routes": [
                {"route": "examples/index.html", "assets": [
                    "examples.css", "fuel-b06-viz06.html", "fuel-b06-viz06-source.json",
                    "fuel-b06-viz06-export.json", "fuel-b06-viz03.html", "fuel-b06-viz06-before.svg",
                    "fuel-b06-viz06-flow.svg", "fuel-b06-viz06-flow.png",
                    "fuel-b06-viz06-stock.svg", "fuel-b06-viz06-stock.png",
                    "fuel-b06-viz06-trajectory.svg", "fuel-b06-viz06-trajectory.png",
                    "fuel-b06-viz06-timing.svg", "fuel-b06-viz06-timing.png",
                    "lotka-volterra-sampled-v1.html", "lotka-volterra-sampled-v1.svg",
                    "lotka-volterra-sampled-v1.png", "lotka-volterra-sampled-v1-export.json",
                    "app02-diamond-v1.html", "app02-diamond-v1.svg",
                    "app02-diamond-v1.png", "app02-diamond-v1-export.json",
                    "app04-square-v1.html", "app04-square-v1.svg",
                    "app04-square-v1.png", "app04-square-v1-export.json",
                    "app03-zonotope-v1.html", "app03-zonotope-v1.svg",
                    "app03-zonotope-v1.png", "app03-zonotope-v1-export.json",
                    "ext01-b08-timing-v1.html", "ext01-b08-timing-v1.svg",
                    "ext01-b08-timing-v1.png", "ext01-b08-timing-v1-export.json",
                    "ext05-states-v1.html", "ext05-states-v1.svg",
                    "ext05-states-v1.png", "ext05-states-v1-export.json",
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
                    "mpc03-b08-l04-miQCP-v1/disturbance-tube.svg", "adaptive-ode-replay.html",
                    "adaptive-ode-replay.csv", "adaptive-ode-replay.svg", "adaptive-ode-replay.json",
                    "buryatia-dim4-literal-affine-v1/index.html",
                    "buryatia-dim4-literal-affine-v1/buryatia-dim4-literal-affine-v1-records.json",
                    "buryatia-dim4-literal-affine-v1/buryatia-dim4-literal-affine-v1-capture.json",
                    "buryatia-dim4-literal-affine-v1/buryatia-dim4-literal-affine-v1-SHA256SUMS",
                    "buryatia-dim4-literal-affine-v1/buryatia-dim4-matlab-literal-affine-v1.json",
                    "buryatia-dim4-literal-affine-v1/terminal-x1-x2.svg"] + geometry_companion_assets() +
                    viz10_companion_assets() + control_witness_companions.asset_paths(),
                 "disposition": "adopted-shared-quantitative-policy"}],
            "migration_owner": "#669 owns the shared policy; deferred family renderers link to scoped follow-up issues #684–#687, while frozen report bundles remain immutable evidence"}


def geometry_companion_assets() -> list[str]:
    from geometry_opt_companions import GEOMETRY_REPORTS, TIMING_REPORTS
    assets = ["geometry-optimization-v1.html"]
    for slug, report_id, *_ in TIMING_REPORTS:
        assets.extend((f"geometry-opt/{slug}/figure.svg", f"geometry-opt/{slug}/figure.png",
                       f"geometry-opt/{slug}/export.json", f"geometry-opt/data/{report_id}.json"))
    for slug, report_id, *_ in GEOMETRY_REPORTS:
        assets.extend((f"geometry-opt/{slug}/geometry.svg", f"geometry-opt/{slug}/geometry.png",
                       f"geometry-opt/{slug}/export.json", f"geometry-opt/data/{report_id}.json"))
    return assets


def viz10_companion_assets() -> list[str]:
    base = ROOT / "docs/examples/viz10"
    return ["viz10/" + path.relative_to(base).as_posix()
            for path in sorted(base.rglob("*")) if path.is_file()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "scripts/reports/visual-route-inventory.json")
    args = parser.parse_args()
    result = build()
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
