"""Stage educational 2D illustrations from reviewed native records, without solving."""
from __future__ import annotations

import argparse
from html import escape
import json
import math
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import urlsplit

import audit_visual_routes
import approx_extension_companions
import geometry_opt_companions
import report_data
import site_additions
import stage_ext07 as ext07_reports
import visual_illustrations
import visual_example_geometry as geometry_examples
import visual_example_fuel_layers
import visual_example_hybrid as hybrid_examples

CASE_OWNERS = {
    "hull": geometry_examples,
    "intersection": geometry_examples,
    "hybrid": hybrid_examples,
    "two_parameter": hybrid_examples,
    "projected_reachability": hybrid_examples,
}

SAVED_FIGURES = (
    dict(route="ext04-continuous-ebcf879d07ee9157", image="example-2d.svg", page="index.html",
         family="Continuous feedback · EXT-04", title="A partial observation policy over an initial set",
         alt="Four initial state generators map to four terminal states under a position-only affine policy.",
         summary="A numerical all-joint check over a four-vertex two-state set, with its raw records and reproduction details in the linked report."),
    dict(route="app02-box-8ff979de60ea9d22", image="polygons.svg", page="index.html",
         family="Box approximation", title="Box outer approximation",
         alt="Planar reachable-set polygons and their box approximation."),
    dict(route="app03-zonotope-4522855018fa9b0b", image="zonotope-2d.svg", page="example-2d.html",
         family="Zonotopes", title="A planar zonotope", alt="A planar zonotope and its generator geometry."),
    dict(route="app04-ellipsoid-fd302c34092f8b19", image="ellipsoid-2d.svg", page="example-2d.html",
         family="Ellipsoidal approximation", title="A planar ellipsoid", alt="A planar ellipsoidal approximation."),
    dict(route="exp04-replay-93fe3b87795e1d3a", image="trajectory.svg", page="index.html",
         family="Sampled replay", title="Replay a sampled trajectory",
         alt="Saved sampled nonlinear replay trajectory."),
    dict(route="ext05-discretization-a40ba9647cc023dc", image="trajectory-2d.svg", page="example-2d.html",
         family="Discretization", title="A two-dimensional discretized model",
         alt="Saved two-dimensional discretization example."),
    dict(route="ext07-hybrid-51d9ee2e89d240eb", image="joint-relation-2d.svg", page="example-2d.html",
         family="Hybrid reachability", title="A hybrid joint relation",
         alt="Saved two-dimensional hybrid joint-relation example."),
    dict(route="geo08-lazy-6dbdd6b2f9235837", image="lazy-2d.svg", page="example-2d.html",
         family="Lazy geometry", title="Evaluate a lazy planar set",
         alt="Planar set expression shown before and after materialization."),
    dict(route="opt10-smooth-188130d94d7bf2de", image="feasible-box-2d.svg", page="example-2d.html",
         family="Smooth convex optimization", title="Feasible directions in a box",
         alt="A planar feasible box, objective direction, and selected point."),
    dict(source_report_id="syn04-strategy-b-ts03-20261022-2c0c9210", image="control-projection.svg",
         page="index.html", family="Strategy B control synthesis",
         title="Strategy B on the T-S03 control projection",
         alt="Saved T-S03 control projection from Strategy B.",
         summary="T-S03 has a one-dimensional state, two stages and one scalar control per stage. The plotted axes are u₀ and u₁, showing a projection of the complete optimal relation. The report records exact-profile completeness with numerical assurance; it does not establish generic Strategy B completeness."),
    dict(route="lotka-volterra-sampled-20261023", image="geometry.svg", page="index.html",
         family="Lotka–Volterra reachability samples", title="A sampled Lotka–Volterra orbit",
         alt="Seeded two-state Lotka–Volterra control samples trace an orbit; local panels show sample hulls.",
         summary="512 deterministic control histories illustrate the discrete recurrence. Dots and sample hulls do not certify the full reachable sets or reproduce the historical figure."),
    dict(route="syn03-nominal-exact-2d-8b94095", image="optimal-face.svg", page="index.html",
         family="Strategy A · nominal linear exact profile", title="A complete 2D optimal face",
         alt="The feasible upper triangle in the unit square and its full optimal diagonal segment from (0,1) to (1,0).",
         summary="The installed Strategy A example returned objective 1 and a registry-verified complete face x+y=1, 0<=x,y<=1. The page retains inputs, raw result and the numerical assurance limits."),
    dict(source_report_id="b06-owner-confirmed-7df01ba3af5e4c46", image="terminal-projections.svg",
         page="index.html", family="Fuel minimax reference", title="B06 fuel terminal set: two projections",
         alt="Numerical projections of the four-state terminal reachable set onto flow and stock-balance coordinates; the stock target is outside the projected set.",
         summary="The figure uses all 1,024 disturbance-corner histories for the unique winning fixed plan. The owner-confirmed disturbance box is not printed in L09, so this is a distinct reference case rather than a historical reproduction."),
    dict(source_report_id="b09-a08-source-reference-4818ddde", image="projections-lambda0.svg",
         page="index.html", family="Fuel minimax reference", title="B09 fuel reachable set: lambda = 0",
         alt="The four-state fuel model's terminal reachable set projected into flow and stock coordinates, with open-loop and receding-horizon replay paths.",
         summary="The shaded polygons project the uncertain four-dimensional terminal set into oxidizer/fuel flow and stock planes. Red and blue paths are separate nonlinear replays; they are not set boundaries or globally optimal feedback claims."),
    dict(source_report_id="b09-a08-source-reference-4818ddde", image="projections-lambda1.svg",
         page="index.html", family="Fuel minimax reference", title="B09 fuel reachable set: lambda = 1",
         alt="The four-state fuel model's terminal reachable set projected into flow and stock coordinates for the coupled objective, with open-loop and receding-horizon replay paths.",
         summary="The shaded polygons project the uncertain four-dimensional terminal set into oxidizer/fuel flow and stock planes. Red and blue paths are separate nonlinear replays; they are not set boundaries or globally optimal feedback claims."),
)


require = report_data.require


def load_examples(catalog):
    """Combine case-owned data prepared by the geometry and hybrid modules."""
    return geometry_examples.load_examples(catalog) + hybrid_examples.load_examples(catalog)


def plot(example):
    if example["kind"] == "two_parameter":
        def point(p):
            return (80 + p[0] * 400, 440 - p[1] * 400)

        def polygon(points, color, fill, dashed=False):
            coords = " ".join(f"{x:.6f},{y:.6f}" for x, y in map(point, points))
            dash = ' stroke-dasharray="8 6"' if dashed else ""
            return (f'<polygon points="{coords}" fill="{fill}" stroke="{color}" '
                    f'stroke-width="3"{dash}/>')

        elements = []
        for value in (0, 0.5, 1):
            x, y = point((value, value))
            elements += [f'<line x1="{x}" y1="40" x2="{x}" y2="440" stroke="#3c493d"/>',
                         f'<line x1="80" y1="{y}" x2="480" y2="{y}" stroke="#3c493d"/>',
                         f'<text x="{x}" y="470" text-anchor="middle">{value:g}</text>',
                         f'<text x="68" y="{y+5}" text-anchor="end">{value:g}</text>']
        full, half = example["polygons"][1], example["polygons"][0]
        elements += [polygon(full["feasible_polygon_in_control_coordinates"], "#d6af75", "#d6af7518", True),
                     polygon(half["feasible_polygon_in_control_coordinates"], "#b4cda3", "#b4cda333"),
                     '<text x="92" y="132">enter-half path</text>',
                     '<text x="335" y="388">enter-full only</text>',
                     '<text x="290" y="72" text-anchor="middle">objective = 0 everywhere</text>']
        description = ("The amber dashed triangle is the enter-full path. The green quadrilateral is the "
                       "enter-half path and lies within it. Every point on both labelled paths is optimal "
                       "for the constant zero objective.")
        return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 580 510" role="img" '
                'aria-labelledby="title desc"><title id="title">' + escape(example["title"]) + '</title>'
                '<desc id="desc">' + description + '</desc><rect width="580" height="510" fill="#172019"/>'
                '<g font-family="monospace" font-size="14" fill="#d1d9cc">' + "".join(elements) +
                '<text x="285" y="502" text-anchor="middle">u₀ (first free control)</text>'
                '<text x="18" y="245" transform="rotate(-90 18 245)" text-anchor="middle">u₁ (second free control)</text>'
                '</g></svg>')
    low, high = example["domain"]

    def point(p):
        return (80 + (p[0]-low)*400/(high-low), 440 - (p[1]-low)*400/(high-low))

    def coordinates(points):
        return " ".join(f"{x:.6f},{y:.6f}" for x, y in map(point, points))

    def boundary(points, color, fill="none", dashed=False):
        tag = "polygon" if len(points) > 2 else "polyline"
        dash = ' stroke-dasharray="8 6"' if dashed else ""
        return (f'<{tag} points="{coordinates(points)}" fill="{fill}" '
                f'stroke="{color}" stroke-width="2.5"{dash}/>')

    elements = []
    for value in sorted({low, 0, high}):
        x, y = point((value, value))
        elements += [f'<line x1="{x}" y1="40" x2="{x}" y2="440" stroke="#3c493d"/>',
                     f'<line x1="80" y1="{y}" x2="480" y2="{y}" stroke="#3c493d"/>',
                     f'<text x="{x}" y="470" text-anchor="middle">{value:g}</text>',
                     f'<text x="68" y="{y+5}" text-anchor="end">{value:g}</text>']
    if example["kind"] == "intersection":
        elements.append(boundary([[-1,-1],[1,-1],[1,1],[-1,1]], "#91a9c7", dashed=True))
        elements.append(boundary([[-1.5,0],[0,-1.5],[1.5,0],[0,1.5]], "#d6af75", dashed=True))
        vertices = sorted(example["vertices"], key=lambda p: math.atan2(p[1], p[0]))
    else:
        vertices = example["vertices"]
    elements.append(boundary(vertices, "#b4cda3", "#b4cda31c" if len(vertices) > 2 else "none"))
    if example["kind"] in {"hybrid", "projected_reachability"}:
        labels = (("unique minimum", "feasible endpoint") if example["kind"] == "hybrid"
                  else ("projected endpoint", "projected endpoint"))
        colors = (("#d6af75", "#b4cda3") if example["kind"] == "hybrid"
                  else ("#b4cda3", "#b4cda3"))
        for index, (p, label, color) in enumerate(zip(example["points"],
                labels, colors)):
            x, y = point(p)
            elements.append(f'<circle cx="{x}" cy="{y}" r="6" fill="{color}"/>')
            elements.append(f'<text x="{x+9}" y="{y-10}">{label}</text>')
    else:
        groups = {}
        for index, p in enumerate(example["points"]):
            groups.setdefault(tuple(p), []).append(index)
        for p, ids in groups.items():
            x, y = point(p)
            retained = any(index in example["indices"] for index in ids)
            color = "#b4cda3" if retained else "#d6af75"
            label = "/".join(str(index) for index in ids)
            elements.append(f'<circle cx="{x}" cy="{y}" r="5" fill="{color}"/>')
            elements.append(f'<text x="{x+9}" y="{y-10}">{label}</text>')
    description = ("Original point IDs label each location; slash-separated IDs coincide. Green points are hull vertices."
                   if example["kind"] == "hull" else
                   "Blue dashed square and amber dashed diamond overlap in the green eight-vertex intersection. Labels are saved output row IDs."
                   if example["kind"] == "intersection" else
                   "The green segment is the projected terminal state set x1 in [0, 0.5]; the axes show the feasible control and terminal-state relation."
                   if example["kind"] == "projected_reachability" else
                   "The feasible two-stage relation is the green segment x2 equals u0 from zero to one half; the gold point is its unique minimum.")
    x_label, y_label = (("u₀ (free control)", "x₂ (terminal state)") if example["kind"] == "hybrid"
                        else ("u₀ (free control)", "x₁ (terminal state)") if example["kind"] == "projected_reachability"
                        else ("x (dimensionless)", "y (dimensionless)"))
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 580 510" role="img" '
            'aria-labelledby="title desc"><title id="title">' + escape(example["title"]) + '</title>'
            '<desc id="desc">' + description + '</desc><rect width="580" height="510" fill="#172019"/>'
            '<g font-family="monospace" font-size="14" fill="#d1d9cc">' + "".join(elements) +
            '<text x="285" y="502" text-anchor="middle">' + escape(x_label) + '</text>'
            '<text x="18" y="245" transform="rotate(-90 18 245)" text-anchor="middle">' + escape(y_label) + '</text>'
            '</g></svg>')


def point_table(example):
    rows = []
    seen = {}
    for index, p in enumerate(example["points"]):
        if example["kind"] in {"hybrid", "projected_reachability"}:
            role = ("unique minimum" if index == 0 else "feasible interval endpoint") \
                if example["kind"] == "hybrid" else "projected terminal endpoint"
        elif example["kind"] == "two_parameter":
            role = "feasible polygon vertex; shared vertices preserve separate path labels"
        elif example["kind"] == "intersection":
            role = "intersection vertex"
        elif tuple(p) in seen:
            role = "duplicate of point " + str(seen[tuple(p)])
        else:
            role = "hull vertex" if index in example["indices"] else "interior / omitted"
        seen.setdefault(tuple(p), index)
        rows.append(f'<tr><td>{index}</td><td>{p[0]:.6g}</td><td>{p[1]:.6g}</td><td>{role}</td></tr>')
    heading = ("Original point ID" if example["kind"] == "hull" else
               "Fixture point" if example["kind"] == "hybrid" else
               "Projected endpoint" if example["kind"] == "projected_reachability" else
               "Polygon vertex" if example["kind"] == "two_parameter" else "Saved output row ID")
    caption = ("Exact illustrative values; the continuous feasible set is the full segment."
               if example["kind"] == "hybrid" else
               "Exact endpoints of the projected terminal interval; the plotted relation is the complete line segment."
               if example["kind"] == "projected_reachability" else
               "Exact polygon vertices; identical locations belong to separately labelled path branches."
               if example["kind"] == "two_parameter" else
               "Coordinates (rounded to six significant digits; raw JSON retains binary64 values)")
    x_label, y_label = (("u₀", "x₂") if example["kind"] == "hybrid" else
                        ("u₀", "x₁") if example["kind"] == "projected_reachability" else
                        ("u₀", "u₁") if example["kind"] == "two_parameter" else ("x", "y"))
    return ('<div class="scroll" tabindex="0" role="region" aria-label="Point coordinates"><table>'
            f'<caption>{caption}</caption>'
            f'<thead><tr><th scope="col">{heading}</th><th scope="col">{x_label}</th><th scope="col">{y_label}</th>'
            '<th scope="col">Role</th></tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>')


def section(example, number):
    owner = CASE_OWNERS[example["kind"]]
    content = owner.presentation(example)
    return (f'<section id="{example["slug"]}"><p class="eyebrow">Example {number:02d} / {content["example_type"]}</p>'
            f'<h2>{example["title"]}</h2><p>{content["explanation"]}</p>'
            f'<figure><img src="{example["slug"]}.svg" alt="{escape(content["explanation"], quote=True)}">'
            f'<figcaption>{content["caption"]}</figcaption></figure>'
            f'<p class="answer">{content["result"]}</p>{point_table(example)}'
            '<details><summary>Complete minimal input</summary><pre><code>' + escape(json.dumps(example["inputs"], indent=2)) + '</code></pre></details>'
            + content["extra"] + '<details><summary>Reproduce the functional example</summary>' + content["reproduction"] +
            '<pre><code>' + escape(content["command"]) + '</code></pre>'
            '<p>' + content["platform_note"] + '</p>'
            f'<p><a href="{content["source_url"]}">Complete native fixture/driver ↗</a></p></details>'
            f'<p class="limits">{content["notes"]}</p>' + content["source_provenance"] +
            content["raw_record_link"] + content["report_links"] + '</section>')


def saved_figure_sections(catalog, site):
    entries = json.loads(Path(catalog).read_text(encoding="utf-8"))["reports"]
    by_source = {entry["source_report_id"]: entry for entry in entries if "source_report_id" in entry}
    cards = []
    inventory = []
    for number, entry in enumerate(SAVED_FIGURES, start=1):
        report_id = entry.get("route")
        if "source_report_id" in entry:
            published = by_source.get(entry["source_report_id"])
            require(published is not None, "missing catalogued visual report: " + entry["source_report_id"])
            report_id = published["report_id"]
        require(re.fullmatch(r"[A-Za-z0-9-]+", report_id or "") is not None, "unsafe visual report route")
        route = Path(site) / report_id
        image_path = route / entry["image"]
        require(not route.is_symlink() and image_path.is_file() and not image_path.is_symlink(),
                "missing staged visual figure: " + report_id + "/" + entry["image"])
        require((route / entry["page"]).is_file() and (route / "records.json").is_file(),
                "saved visual needs a report page and raw records: " + report_id)
        image = f"../{report_id}/{entry['image']}"
        page = f"../{report_id}/{entry['page']}"
        records = f"../{report_id}/records.json"
        cards.append(
            f'<article id="saved-figure-{number}" class="saved-figure"><p class="eyebrow">' + escape(entry["family"]) +
            '</p><h3><a href="' + escape(page, quote=True) + '">' + escape(entry["title"]) +
            '</a></h3><a href="' + escape(page, quote=True) + '"><img src="' +
            escape(image, quote=True) + '" alt="' + escape(entry["alt"], quote=True) +
            '"></a><p>' + escape(entry.get("summary", "Figure from the immutable saved report; no solver was rerun for this gallery.")) + '</p>'
            '<p><a href="' + escape(page, quote=True) + '">Inputs, answer and reproduction details ↗</a> · '
            '<a href="' + escape(records, quote=True) + '">Raw record ↗</a></p></article>')
        inventory.append({"family": entry["family"], "title": entry["title"], "report_id": report_id,
                          "figure": entry["image"], "page": entry["page"], "records": "records.json"})
    return ''.join(cards), inventory


def validate_gallery_inventory(out, entries):
    page = (out / "index.html").read_text(encoding="utf-8")
    site_root = out.parent.resolve()
    require(page.count('id="saved-report-figures"') == 1,
            "saved report figures need one gallery section")
    anchors = set(re.findall(r'\bid="([A-Za-z0-9_-]+)"', page))
    require(len(anchors) == len(re.findall(r'\bid="', page)), "duplicate/unsafe gallery anchor")
    require(len({entry["anchor"] for entry in entries}) == len(entries),
            "visual inventory anchors must be unique")
    rendered = set(re.findall(r'<section id="([A-Za-z0-9_-]+)"', page)) - {
        "saved-report-figures", "analytic-illustrations", "algorithm-coverage"}
    rendered.update(re.findall(r'<article\b[^>]*\bid="(saved-figure-[A-Za-z0-9_-]+)"', page))
    rendered.update(re.findall(r'<article class="saved-figure" id="([A-Za-z0-9_-]+)"', page))
    listed = {entry["anchor"] for entry in entries}
    require(rendered == listed,
            "every rendered gallery example must appear in the visual inventory; missing=" +
            repr(sorted(rendered - listed)) + ", stale=" + repr(sorted(listed - rendered)))
    for entry in entries:
        required = ("family", "title", "status", "anchor", "page", "figure", "source_page", "raw_record")
        require(all(isinstance(entry.get(field), str) and entry[field] for field in required),
                "visual inventory entry is missing required metadata or provenance")
        require(entry["status"] in {"educational-example", "saved-report-figure",
                                    "saved-data-companion", "analytic-illustration"},
                "unknown visual inventory status")
        require(entry["anchor"] in anchors, "visual inventory target is missing from gallery")
        page_ref, _, page_anchor = entry["page"].partition("#")
        page_target = (out / page_ref).resolve()
        require(page_target.is_relative_to(site_root) and page_target.is_file() and
                (not page_anchor or page_anchor in anchors),
                "visual inventory page or anchor is missing or escaping")
        if "walkthrough_page" in entry:
            walkthrough = (out / entry["walkthrough_page"]).resolve()
            require(walkthrough.is_relative_to(site_root) and walkthrough.is_file(),
                    "visual inventory walkthrough page is missing or escaping")
        raw_path = (out / entry["raw_record"]).resolve()
        require(raw_path.is_relative_to(site_root) and raw_path.is_file(),
                "visual inventory raw record is missing or escaping")
        try:
            raw_data = json.loads(raw_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raise ValueError("visual inventory raw record must be readable JSON") from None
        require(isinstance(raw_data, dict), "visual inventory raw record must be a JSON object")
        if entry["status"] == "analytic-illustration":
            require(all(field in raw_data for field in
                        ("inputs", "answer", "reproduction_command", "evidence")) and
                    ("related_saved_report" in raw_data or "source_path" in raw_data),
                    "analytic visual record needs inputs, answer, reproduction and source provenance")
        for field in ("figure", "source_page", "raw_record", "report_records"):
            if field not in entry:
                continue
            if field == "source_page" and urlsplit(entry[field]).scheme:
                continue
            target = (out / entry[field]).resolve()
            require(target.is_relative_to(site_root) and target.is_file(),
                    "visual inventory links to a missing or escaping file: " + field)


def algorithm_coverage(catalog, site, gallery_inventory):
    source = Path(__file__).with_name("algorithm_visual_coverage.json")
    result = json.loads(source.read_text(encoding="utf-8"))
    require(result.get("schema") == "csl.algorithm-visual-coverage/1",
            "unsupported algorithm coverage schema")
    architecture = Path(__file__).parents[2] / result["source"]
    require(architecture.is_file(),
            "algorithm coverage architecture source is missing")
    architecture_text = architecture.read_text(encoding="utf-8")
    reports = json.loads(Path(catalog).read_text(encoding="utf-8"))["reports"]
    require(Path(catalog).resolve() == Path(__file__).parents[2] / result["catalog_source"],
            "algorithm coverage was built from an unexpected report catalog")
    kinds = {entry["report_kind"] for entry in reports}
    mapped_kinds = {kind for family in result["families"] for kind in family["catalog_kinds"]}
    require(kinds <= mapped_kinds, "algorithm coverage omits catalog report kinds: " +
            ", ".join(sorted(kinds - mapped_kinds)))
    require(all(kind in kinds for family in result["families"] for kind in family["catalog_kinds"]),
            "algorithm coverage refers to an unknown catalog report kind")
    for report in reports:
        route = Path(site) / report["report_id"]
        raw_name = "results.jsonl" if report["report_kind"] == "issue6-b07-reference" else "records.json"
        require((route / "index.html").is_file() and (route / raw_name).is_file(),
                "algorithm coverage catalog report is not staged: " + report["report_id"])
    gallery = {entry["anchor"]: entry for entry in gallery_inventory}
    for family in result["families"]:
        require(all(module in architecture_text for module in family["modules"]),
                "algorithm family module is absent from its architecture source: " + family["id"])
        require(family["implementation_issues"],
                "algorithm family needs a linked implementation issue: " + family["id"])
        require(family["support"].startswith("supported-") or family["limit"],
                "unsupported 2D family needs a support limit: " + family["id"])
        require(not family["support"].startswith("supported-") or family["examples"],
                "supported 2D family needs a gallery example: " + family["id"])
        for example in family["examples"]:
            require(example in gallery, "algorithm coverage points to a missing gallery example: " + example)
        family["gallery_examples"] = [gallery[name] for name in family["examples"]]
        family["catalog_reports"] = [
            {"report_kind": entry["report_kind"], "report_id": entry["report_id"],
             "page": "../" + entry["report_id"] + "/index.html",
             "raw_record": "../" + entry["report_id"] + "/" +
                           ("results.jsonl" if entry["report_kind"] == "issue6-b07-reference" else "records.json")}
            for entry in reports if entry["report_kind"] in family["catalog_kinds"]]
        for route in family["report_routes"]:
            target = Path(site) / route
            require((target / "index.html").is_file() and (target / "records.json").is_file(),
                    "algorithm coverage report route is not staged: " + route)
        family["additional_reports"] = [
            {"report_id": route, "page": "../" + route + "/index.html",
             "raw_record": "../" + route + "/records.json"}
            for route in family["report_routes"]]
        family["implementation_issues"] = [
            {"number": number,
             "url": f"https://github.com/butahlecoq/controlled-systems-lab/issues/{number}"}
            for number in family["implementation_issues"]]
    return result


def coverage_html(coverage):
    rows = []
    for family in coverage["families"]:
        examples = " · ".join(
            f'<a href="#{escape(entry["anchor"], quote=True)}">{escape(entry["title"])}</a>' +
            (f' · <a href="{escape(entry["walkthrough_page"], quote=True)}">End-to-end walkthrough</a>'
             if entry.get("walkthrough_page") else "")
            for entry in family["gallery_examples"]) or "No 2D example currently published"
        issues = " · ".join(
            f'<a href="{escape(issue["url"], quote=True)}">Issue #{issue["number"]}</a>'
            for issue in family["implementation_issues"])
        reports = family["catalog_reports"] + family["additional_reports"]
        report_links = " · ".join(
            f'<a href="{escape(report["page"], quote=True)}">{escape(report["report_id"])}</a>'
            for report in reports)
        rows.append('<article class="coverage-row"><h3>' + escape(family["name"]) + '</h3>'
                    '<p class="eyebrow">' + escape(family["composition"]) + ' · ' +
                    escape(family["support"]) + '</p><p>' + escape(family["limit"]) +
                    '</p><p>Examples: ' + examples + '</p><p>Saved reports: ' +
                    (report_links or "No saved report") + '</p><p>Related work: ' + issues + '</p></article>')
    return ''.join(rows)


def issue3_control_walkthrough(record_path, report_id):
    """Create a saved-data-only end-to-end view of the two-plan analytic run."""
    document = json.loads(Path(record_path).read_text(encoding="utf-8"))
    rows = document["rows"]
    saved = next((row for row in rows if row.get("fixture") == "analytic_2d"
                  and not row.get("warmup")), None)
    require(saved is not None, "issue3 walkthrough needs a measured saved analytic_2d record")
    request = json.loads(saved["input_canonical"])
    identity = [["0x1p+0", "0x0p+0"], ["0x0p+0", "0x1p+0"]]
    require(request["system"]["horizon"] == 1 and request["initial"] == ["0x0p+0", "0x0p+0"]
            and request["system"]["A"] == identity and request["system"]["B"] == identity
            and request["system"]["E"] == identity and request["system"]["c"] == ["0x0p+0", "0x0p+0"]
            and request["actions"] == [["0x0p+0", "0x0p+0"], ["0x1p+0", "0x0p+0"]]
            and request["disturbance_vertices"] == [["0x0p+0", "0x0p+0"]]
            and request["safe_sets"] == "universal"
            and request["objective"] == {"type": "residual_norm_terminal", "C": identity,
                                          "target": ["0x1p+0", "0x0p+0"]},
            "issue3 walkthrough saved fixture changed; review the geometry before publishing")
    result = saved["result"]
    require(result["status"] == "validated_bounds" and result["lower"] == 0
            and result["upper"] == 0 and result["plans"] == 2
            and result["histories_examined"] == 2,
            "issue3 walkthrough saved result changed; review the explanation before publishing")
    source_commit = saved["source_commit"]
    harness_commit = saved["harness_commit"]
    figure = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 420" role="img" aria-labelledby="title desc">'
              '<title id="title">Issue 3 one-step terminal states and target</title>'
              '<desc id="desc">The two finite actions end at (0,0) and (1,0). The target is (1,0), so the second action attains zero residual.</desc>'
              '<rect width="640" height="420" fill="#172019"/>')
    for x, label in ((120, "0"), (240, "0.5"), (360, "1"), (480, "1.5")):
        figure += f'<line x1="{x}" y1="60" x2="{x}" y2="310" stroke="#354337"/><text x="{x}" y="338" text-anchor="middle" fill="#dce5d5">{label}</text>'
    for y, label in ((310, "−0.5"), (230, "0"), (150, "0.5")):
        figure += f'<line x1="80" y1="{y}" x2="530" y2="{y}" stroke="#354337"/><text x="65" y="{y+5}" text-anchor="end" fill="#dce5d5">{label}</text>'
    figure += ('<line x1="80" y1="230" x2="530" y2="230" stroke="#b4cda3" stroke-width="2"/>'
               '<circle cx="360" cy="230" r="12" fill="#f0c674"/><text x="377" y="210" fill="#f0c674">target (1,0)</text>'
               '<circle cx="120" cy="230" r="10" fill="#72b7b2"/><text x="95" y="198" fill="#72b7b2">action 0: (0,0), cost 1</text>'
               '<circle cx="360" cy="230" r="7" fill="#b4cda3" stroke="#fff" stroke-width="2"/><text x="370" y="262" fill="#b4cda3">action 1: (1,0), cost 0</text>'
               '<text x="300" y="385" text-anchor="middle" fill="#dce5d5">terminal state x₁ coordinate (dimensionless)</text>'
               '<text transform="translate(20 210) rotate(-90)" text-anchor="middle" fill="#dce5d5">terminal state y₁ coordinate (dimensionless)</text></svg>')
    page = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>One saved control task from input to verified result</title>'
            '<link rel="stylesheet" href="examples.css"></head><body><main class="walkthrough">'
            '<p><a href="index.html#algorithm-coverage">← Algorithm family coverage</a></p>'
            '<p class="eyebrow">Saved validated API run · Issue #3</p>'
            '<h1>One finite-action control task, end to end</h1>'
            '<p>This walkthrough reads the saved <code>analytic_2d</code> input and result. It does not rerun the solver. '
            'The plotted terminal points are independently calculated from the saved matrices and actions.</p>'
            '<h2>1. Define the problem</h2><p>One transition: <code>x₁ = x₀ + u₀ + w₀</code>, '
            '<code>x₀=(0,0)</code>, zero disturbance, universal safety sets, and terminal objective '
            '<code>||x₁−(1,0)||₂</code>. The ordered finite action catalogue is <code>[(0,0),(1,0)]</code>.</p>'
            '<h2>2. Run the supported profile</h2><p>The recorded profile is the validated finite-action minimax API, with horizon 1, '
            '2 plans, 2 histories total, and a 100,000 interval-operation limit. The raw record reports '
            '<code>validated_bounds [0,0]</code>. This is a small analytic fixture of the implemented validated profile.</p>'
            '<h2>3. Select from the complete finite family</h2><p>Both catalogue plans were examined. Direct substitution gives terminal states '
            '<code>(0,0)</code> and <code>(1,0)</code>; their terminal residual norms are 1 and 0. The selected witness is action index 1, '
            '<code>u₀=(1,0)</code>. The API driver checks that plan index 1 is feasible and has exact bounds [0,0].</p>'
            '<figure><img src="issue3-control-walkthrough.svg" alt="The two terminal states and target in 2D state coordinates">'
            '<figcaption>Independent arithmetic from the saved system, initial state, action catalogue, disturbance and target. '
            'This figure is not an emitted solver trace.</figcaption></figure>'
            '<h2>4. Independently verify the answer</h2><p>Using the saved identity matrices and zero disturbance, '
            '<code>x₁=x₀+u₀</code>. Evaluating the objective at both possible states gives a minimum of exactly zero. '
            'That agrees with the saved validated interval [0,0] and the driver’s assertions that both plans were returned '
            'and action index 1 was feasible. Safety is universal in this fixture, so there are no state inequalities to test.</p>'
            '<h2>5. Inspect the saved export and provenance</h2><ul><li><a href="../' + escape(report_id, quote=True) +
            '/records.json">Raw records and exact hexadecimal input ↗</a></li><li><a href="../' + escape(report_id, quote=True) +
            '/index.html">Saved run report ↗</a></li><li><a href="https://github.com/butahlecoq/controlled-systems-lab/blob/' +
            escape(harness_commit, quote=True) + '/benchmarks/reporting/issue3/validated_driver.cpp">Validated-run harness at its recorded commit ↗</a></li>'
            '<li><a href="https://github.com/butahlecoq/controlled-systems-lab/blob/' +
            escape(source_commit, quote=True) + '/include/csl/optimization/validated_finite_action_minimax.hpp">Validated API header at its recorded source commit ↗</a></li></ul>'
            '<p>Evidence boundary: this explains the saved analytic fixture only. It does not generalize to continuous action sets '
            'or claim correctness beyond the recorded API result and the direct finite calculation above.</p>'
            '<p>Rebuild the gallery from the repository root with '
            '<code>python scripts/reports/visual_examples.py --catalog reports/algorithm-results/catalog.json --site build/report-site</code>.</p>'
            '</main></body></html>')
    return figure, page


def build(catalog, site):
    examples = load_examples(catalog)
    site = Path(site).resolve(strict=True)
    saved_figures, saved_inventory = saved_figure_sections(catalog, site)
    fuel_layer_files, fuel_layer_inventory, fuel_layer_card = visual_example_fuel_layers.build(
        Path(__file__).resolve().parents[2])
    saved_figures += fuel_layer_card
    last_topic_anchor = "visual-fuel-b06-viz03"
    last_topic_title = "B06 fuel terminal set: readable 4D-to-2D projections"
    analytic_files, analytic_inventory = visual_illustrations.build(Path(catalog))
    index = report_data.local_file(site, "index.html")
    original = index.read_text(encoding="utf-8")
    require(original.count("</body>") == 1 and len(re.findall(r"<body\b[^>]*>", original)) == 1,
            "staged report index has no unique body")
    # Validate every input/link before making any output visible. The publisher
    # already validated full report artifacts; never rewrite those artifacts here.
    for example in examples:
        route = site / example["report_id"]
        require(not route.is_symlink() and (route / "index.html").is_file(), "missing staged report route")
        report_data.local_file(route, "index.html")
        require(report_data.local_file(route, "records.json").read_bytes() == example["records_path"].read_bytes(),
                "staged records differ from reviewed source")
    out = site / "examples"
    require(not out.is_symlink(), "gallery output must not be a symlink")
    outputs = {e["slug"] + ".svg": plot(e) for e in examples}
    outputs.update(analytic_files)
    with tempfile.TemporaryDirectory(prefix="csl-gallery-geometry-") as temporary:
        geometry_root = Path(temporary) / "examples"
        _, geometry_inventory, geometry_assets = geometry_opt_companions.build(geometry_root)
        for asset in geometry_assets:
            outputs[asset] = (geometry_root / asset).read_bytes()
    fuel_assets = Path(__file__).parents[2] / "docs/examples"
    fuel_files = ("fuel-b06-viz03.html", "fuel-b06-viz03-source.json", "fuel-b06-viz03-export.json",
                  "fuel-b06-flow-projection.svg", "fuel-b06-flow-projection.png", "fuel-b06-stock-projection.svg",
                  "fuel-b06-stock-projection.png", "fuel-b06-trajectory.svg", "fuel-b06-trajectory.png", "fuel-b06-timing.svg", "fuel-b06-timing.png",
                  "fuel-b06-viz06.html", "fuel-b06-viz06-source.json", "fuel-b06-viz06-export.json",
                  "fuel-b06-viz06-before.svg",
                  "fuel-b06-viz06-flow.svg", "fuel-b06-viz06-flow.png", "fuel-b06-viz06-stock.svg", "fuel-b06-viz06-stock.png",
                  "fuel-b06-viz06-trajectory.svg", "fuel-b06-viz06-trajectory.png", "fuel-b06-viz06-timing.svg", "fuel-b06-viz06-timing.png")
    for name in fuel_files:
        path = fuel_assets / name
        require(path.is_file(), "missing VIZ-03 fuel figure asset: " + str(path))
        outputs[name] = path.read_text(encoding="utf-8") if path.suffix == ".html" else path.read_bytes()
    viz10_assets = Path(__file__).parents[2] / "docs/examples/viz10"
    require((viz10_assets / "index.html").is_file(), "missing VIZ-10 saved-data plot gallery")
    for path in sorted(viz10_assets.rglob("*")):
        if path.is_file() and "mpl-config" not in path.parts:
            name = "viz10/" + path.relative_to(viz10_assets).as_posix()
            outputs[name] = path.read_text(encoding="utf-8") if path.suffix == ".html" else path.read_bytes()
    gallery_inventory = []
    for example in examples:
        owner = CASE_OWNERS[example["kind"]]
        gallery_inventory.append(owner.inventory_entry(example))
    gallery_inventory.extend(analytic_inventory)
    gallery_inventory.extend(fuel_layer_inventory)
    geometry_first = geometry_inventory[0]
    gallery_inventory.append({"family": "Geometry and optimization",
                              "title": "Readable geometry and timing figures",
                              "status": "saved-data-companion", "anchor": "geometry-optimization-companions",
                              "page": "index.html#geometry-optimization-companions",
                              "figure": geometry_first["figure"],
                              "source_page": "geometry-optimization-v1.html",
                              "raw_record": geometry_first["records"]})
    for entry in gallery_inventory:
        if entry["anchor"] == "visual-issue3-validated-minimax-2d":
            entry["walkthrough_page"] = "issue3-control-walkthrough.html"
    for figure_index, entry in enumerate(saved_inventory):
        report_page = entry["page"]
        report_figure = entry["figure"]
        report_record = entry["records"]
        entry["anchor"] = f"saved-figure-{figure_index+1}"
        entry["page"] = "index.html#saved-report-figures"
        entry["figure"] = f"../{entry['report_id']}/{report_figure}"
        entry["source_page"] = f"../{entry['report_id']}/{report_page}"
        entry["raw_record"] = f"../{entry['report_id']}/{report_record}"
        entry["status"] = "saved-report-figure"
        gallery_inventory.append(entry)
    fuel_anchor = "visual-fuel-b06-viz03"
    fuel_entry = {"family":"Fuel minimax reference", "title":"B06 fuel terminal set: readable 4D-to-2D projections",
                  "status":"saved-data-companion", "anchor":fuel_anchor, "page":"fuel-b06-viz06.html",
                  "figure":"fuel-b06-viz06-flow.svg", "source_page":"https://github.com/butahlecoq/controlled-systems-lab/blob/main/reports/algorithm-results/b06-owner-confirmed-7df01ba3af5e4c46/index.html",
                  "raw_record":"fuel-b06-viz06-source.json"}
    gallery_inventory.append(fuel_entry)
    viz10_entry = {"family": "Historical and benchmark reports",
                   "title": "VIZ-10 saved-data plots, including B07 and B09 fuel projections",
                   "status": "saved-data-companion", "anchor": "saved-figure-viz10-plots",
                   "page": "viz10/index.html",
                   "figure": "viz10/b07-b07-reconstruction-s0-l0-d0.png",
                   "source_page": "../issue6-b07-reference-a394915af10636430cdcd757d95a9d987eaa6c4c0b742bef7ba1aa04638a2cdd/index.html",
                   "raw_record": "viz10/manifest.json"}
    gallery_inventory.append(viz10_entry)
    lotka_route = "lotka-volterra-sampled-20261023"
    lotka_anchor = "saved-figure-lotka-quantitative"
    gallery_inventory.append({"family": "Lotka–Volterra reachability samples",
                              "title": "Stage-banded Lotka–Volterra samples · shared quantitative axes",
                              "status": "saved-data-companion", "anchor": lotka_anchor,
                              "page": "index.html#" + lotka_anchor,
                              "figure": "lotka-volterra-sampled-v1.svg",
                              "source_page": "../" + lotka_route + "/index.html",
                              "raw_record": "../" + lotka_route + "/records.json"})
    lotka_companion = approx_extension_companions.lotka_volterra_companion(
        site / lotka_route / "records.json", Path(__file__).parent / "styles/control-v1.json")
    app02_companion = approx_extension_companions.app02_companion(
        site / "app02-box-8ff979de60ea9d22" / "records.json", Path(__file__).parent / "styles/control-v1.json")
    app03_companion = approx_extension_companions.app03_companion(
        site / "app03-zonotope-4522855018fa9b0b" / "records.json", Path(__file__).parent / "styles/control-v1.json")
    app04_companion = approx_extension_companions.app04_companion(
        site / "app04-ellipsoid-fd302c34092f8b19" / "records.json", Path(__file__).parent / "styles/control-v1.json")
    ext05_companion = approx_extension_companions.ext05_companion(
        site / "ext05-discretization-a40ba9647cc023dc" / "records.json", Path(__file__).parent / "styles/control-v1.json")
    ext01_companion = approx_extension_companions.ext01_companion(
        site / "ext01-fixed-plan-303ad863ca3af58dc6a515844c474fe0e1af9349e55cb8acd1ff1a3f220f1b54" / "records.json",
        Path(__file__).parent / "styles/control-v1.json")
    app01_source_id = "app01-plan-20261016-22d406fd"
    app01_publication_catalog = Path(catalog).resolve().with_name("app01-publications.json")
    app01_publications = json.loads(app01_publication_catalog.read_text(encoding="utf-8"))
    require(app01_publications.get("schema") == "csl.app01-report-extension/1" and
            isinstance(app01_publications.get("reports"), list),
            "APP-01 publication catalogue differs")
    app01_matches = [entry for entry in app01_publications["reports"]
                     if entry.get("source_report_id") == app01_source_id]
    require(len(app01_matches) == 1, "APP-01 source identity is missing or duplicated in publication catalogue")
    app01_report_id = app01_matches[0].get("report_id")
    require(isinstance(app01_report_id, str) and
            re.fullmatch(r"app01-plan-\d{8}-[0-9a-f]{64}", app01_report_id),
            "APP-01 publication route is invalid")
    app01_route = site / app01_report_id
    require(not app01_route.is_symlink() and (app01_route / "index.html").is_file(),
            "missing staged APP-01 publication route")
    app01_record_path = report_data.local_file(app01_route, "records.json")
    app01_source_record = app01_publication_catalog.parent / app01_source_id / "records.json"
    require(app01_record_path.read_bytes() == app01_source_record.read_bytes(),
            "staged APP-01 records differ from reviewed source")
    app01_companion = approx_extension_companions.app01_companion(
        app01_record_path,
        Path(__file__).parent / "styles/control-v1.json", app01_report_id)
    for family, title, stem, report_id in (
            ("Box approximation", "APP-02 diamond approximations", "app02-diamond-v1", "app02-box-8ff979de60ea9d22"),
            ("Ellipsoidal approximation", "APP-04 square and ellipses", "app04-square-v1", "app04-ellipsoid-fd302c34092f8b19"),
            ("Discretization", "EXT-05 saved state samples", "ext05-states-v1", "ext05-discretization-a40ba9647cc023dc")):
        gallery_inventory.append({"family": family, "title": title,
                                  "status": "saved-data-companion",
                                  "anchor": stem, "page": stem + ".html",
                                  "figure": stem + ".svg",
                                  "source_page": "../" + report_id + "/index.html",
                                  "raw_record": "../" + report_id + "/records.json"})
    gallery_inventory.append({"family": "Fixed-plan minimax", "title": "EXT-01 B08 full-catalogue timing",
                              "status": "saved-data-companion", "anchor": "ext01-b08-timing-v1",
                              "page": "ext01-b08-timing-v1.html", "figure": "ext01-b08-timing-v1.svg",
                              "source_page": "../ext01-fixed-plan-303ad863ca3af58dc6a515844c474fe0e1af9349e55cb8acd1ff1a3f220f1b54/index.html",
                              "raw_record": "../ext01-fixed-plan-303ad863ca3af58dc6a515844c474fe0e1af9349e55cb8acd1ff1a3f220f1b54/records.json"})
    gallery_inventory.append({"family": "Zonotopes", "title": "APP-03 saved planar zonotope and outer cover",
                              "status": "saved-data-companion", "anchor": "app03-zonotope-v1",
                              "page": "app03-zonotope-v1.html", "figure": "app03-zonotope-v1.svg",
                              "source_page": "../app03-zonotope-4522855018fa9b0b/index.html",
                              "raw_record": "../app03-zonotope-4522855018fa9b0b/records.json"})
    gallery_inventory.append({"family": "Inner state-plan checks", "title": "APP-01 saved plan-check timings",
                              "status": "saved-data-companion", "anchor": "app01-plan-timing-v1",
                              "page": "app01-plan-timing-v1.html", "figure": "app01-plan-timing-v1.svg",
                              "source_page": "../" + app01_report_id + "/index.html",
                              "raw_record": "../" + app01_report_id + "/records.json"})
    coverage_data = algorithm_coverage(catalog, site, gallery_inventory)
    issue3_report = next(entry for entry in json.loads(Path(catalog).read_text(encoding="utf-8"))["reports"]
                         if entry["report_kind"] == "issue3-validated-minimax")
    workflow_figure, workflow_page = issue3_control_walkthrough(
        Path(catalog).resolve().parent / issue3_report["source_report_id"] / "records.json",
        issue3_report["report_id"])
    navigation = "".join(f'<a href="#{e["slug"]}">{e["title"]}</a>' for e in examples)
    navigation += '<a href="#analytic-illustrations">Analytic geometry and optimization</a>'
    navigation += '<a href="#algorithm-coverage">Algorithm coverage map</a>'
    navigation += '<a href="#saved-report-figures">More saved algorithm figures</a>'
    body = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Visual examples · Controlled Systems Lab</title><link rel="stylesheet" href="examples.css"></head>'
            '<body><a class="skip" href="#main">Skip to examples</a><div class="shell"><aside>'
            '<a class="brand" href="../index.html">[ csl ]<br>Controlled Systems Lab</a>'
            '<p class="eyebrow">Learn by looking</p>'
            f'<a class="nav-shortcut" href="#{last_topic_anchor}">Jump to final example: {escape(last_topic_title)} ↓</a>'
            '<nav aria-label="Examples" tabindex="0">' + navigation +
            '<a href="../index.html">All numerical reports ↗</a></nav></aside><main id="main">'
            '<header><p class="eyebrow">Small inputs / visible answers</p><h1>Algorithms,<br><em>in two dimensions.</em></h1>'
            '<p>See what goes in, what comes out, and why. Explore hull vertices, set intersections, hybrid control families, and projected reachability.</p>'
            '<p class="limits">These educational pages show reviewed saved outputs or explicit analytic constructions; '
            'they are not new performance measurements. Each page states whether it replays saved output or illustrates a literal fixture.</p>'
            '<p><a href="minimal-inputs.json" download>Download inputs and displayed outputs (JSON)</a> · '
            '<a href="visual-coverage.json" download>Download current gallery inventory (JSON)</a> · '
            '<a href="visual-route-inventory.json" download>Download report figure routes and migration status (JSON)</a> · '
            '<a href="algorithm-coverage.json" download>Download algorithm-family coverage (JSON)</a></p>'
            '<p class="limits">This inventory describes figures currently linked here; it does not imply that every implemented algorithm already has a 2D example. '
            'The full algorithm-coverage gap is tracked in <a href="https://github.com/butahlecoq/controlled-systems-lab/issues/563">issue #563</a>.</p></header>'
            + "".join(section(e, i+1) for i, e in enumerate(examples)) +
            '<section id="analytic-illustrations"><p class="eyebrow">Hand-derived examples</p>'
            '<h2>Analytic geometry and optimization</h2><p>These exact low-dimensional examples explain the operations with literal inputs and answers. They are not solver traces or performance evidence.</p>'
            '<div class="saved-grid">' + visual_illustrations.cards(analytic_inventory) + '</div></section>' +
            '<section id="algorithm-coverage"><p class="eyebrow">Implementation map</p>'
            '<h2>Algorithm families and 2D limits</h2><p>This map follows the current framework composition document and published report catalog. '
            'It separates the nominal synthesis path from installed modules outside that path and records where this gallery has no supported 2D case.</p>'
            '<div class="coverage-grid">' + coverage_html(coverage_data) + '</div></section>' +
            '<section id="saved-report-figures"><p class="eyebrow">Reviewed report figures</p>'
            '<h2>More algorithms, from saved evidence</h2><p>Most displayed figures are published inside their original reports. '
            'Cards marked “Saved-data companion” are generated into this gallery from frozen records; they do not change those reports. '
            'Open a report for exact inputs, answers, reproduction commands, provenance and evidence limits.</p>'
            '<div class="saved-grid">' + saved_figures +
            '<article class="saved-figure" id="geometry-optimization-companions"><p class="eyebrow">Geometry and optimization · Saved-data companion</p>'
            '<h3>Readable geometry and timing figures</h3><p>Eleven companions replot frozen report records with the shared quantitative axis policy. '
            'The geometry examples use saved 2D coordinates; timing charts show saved medians and observed ranges.</p>'
            '<p><a href="geometry-optimization-v1.html">Open geometry and optimization figures →</a></p></article>' +
            f'<article class="saved-figure" id="{lotka_anchor}"><p class="eyebrow">Saved sample geometry · Saved-data companion</p>'
            '<h3>Lotka–Volterra samples with shared quantitative axes</h3>'
            '<a href="lotka-volterra-sampled-v1.html"><img src="lotka-volterra-sampled-v1.svg" '
            'alt="Saved Lotka–Volterra state samples across four stage bands"></a>'
            '<p>Replots the frozen sample record with numeric ticks, major grids, and disclosed independent scales; samples are not reachability bounds.</p>'
            '<p><a href="lotka-volterra-sampled-v1.html">Open the saved-data companion →</a></p></article>' +
            '<article class="saved-figure" id="app02-diamond-v1"><p class="eyebrow">Box approximation · Saved-data companion</p>'
            '<h3>APP-02 diamond approximations</h3><a href="app02-diamond-v1.html"><img src="app02-diamond-v1.svg" '
            'alt="Saved APP-02 diamond input, outer bounds, and inner box on labelled x-y axes"></a>'
            '<p>Replots the frozen vertices with numeric ticks, major grids, and equal x-y scales.</p>'
            '<p><a href="app02-diamond-v1.html">Open the saved-data companion →</a></p></article>' +
            '<article class="saved-figure" id="app04-square-v1"><p class="eyebrow">Ellipsoidal approximation · Saved-data companion</p>'
            '<h3>APP-04 square and ellipses</h3><a href="app04-square-v1.html"><img src="app04-square-v1.svg" '
            'alt="Saved APP-04 square and two enclosing ellipses on labelled x-y axes"></a>'
            '<p>Replots the frozen vertices and radii with numeric ticks, major grids, and equal x-y scales.</p>'
            '<p><a href="app04-square-v1.html">Open the saved-data companion →</a></p></article>' +
            '<article class="saved-figure" id="ext05-states-v1"><p class="eyebrow">Discretization · Saved-data companion</p>'
            '<h3>EXT-05 saved state samples</h3><a href="ext05-states-v1.html"><img src="ext05-states-v1.svg" '
            'alt="Three archived EXT-05 position-velocity states at times zero, one, and three"></a>'
            '<p>Plots only the archived state samples; it does not interpolate the continuous trajectory.</p>'
            '<p><a href="ext05-states-v1.html">Open the saved-data companion →</a></p></article>' +
            '<article class="saved-figure" id="ext01-b08-timing-v1"><p class="eyebrow">Fixed-plan minimax · Saved-data companion</p>'
            '<h3>EXT-01 B08 full-catalogue timing</h3><a href="ext01-b08-timing-v1.html"><img src="ext01-b08-timing-v1.svg" '
            'alt="Seven saved EXT-01 B08 timing observations in milliseconds on labelled numeric axes"></a>'
            '<p>Plots the seven frozen observations as separate points with numeric ticks and major grids; no speedup or winner is claimed.</p>'
            '<p><a href="ext01-b08-timing-v1.html">Open the saved-data companion →</a></p></article>' +
            '<article class="saved-figure" id="app03-zonotope-v1"><p class="eyebrow">Zonotopes · Saved-data companion</p>'
            '<h3>APP-03 saved planar zonotope and outer cover</h3>'
            '<a href="app03-zonotope-v1.html"><img src="app03-zonotope-v1.svg" '
            'alt="Saved APP-03 planar zonotope and outer axis cover with numeric x-y axes"></a>'
            '<p>Replots the archived generator sums and outer-cover generators with numeric ticks, major grids, and equal x-y scales.</p>'
            '<p><a href="app03-zonotope-v1.html">Open the saved-data companion →</a></p></article>' +
            '<article class="saved-figure" id="app01-plan-timing-v1"><p class="eyebrow">Inner state-plan checks · Saved-data companion</p>'
            '<h3>APP-01 saved plan-check timings</h3>'
            '<a href="app01-plan-timing-v1.html"><img src="app01-plan-timing-v1.svg" '
            'alt="Three archived APP-01 median timings on numeric axes, one for each saved fixture"></a>'
            '<p>Plots archived medians for valid, invalid, and empty-inner fixtures. Each point summarizes seven batches of 40,000 checks; it does not claim a performance winner.</p>'
            '<p><a href="app01-plan-timing-v1.html">Open the saved-data companion →</a></p></article>' +
            f'<article class="saved-figure" id="{fuel_anchor}"><p class="eyebrow">Fuel minimax reference · Saved-data companion</p>'
            f'<h3>{escape(fuel_entry["title"])}</h3>'
            f'<p>{escape("Readable, versioned SVG and PNG projections of the saved 4D B06 terminal set, with exact values, units, target, evidence limits and reproduction commands.")}</p>'
            f'<a href="{fuel_entry["page"]}"><img src="{fuel_entry["figure"]}" alt="{escape("B06 four-state terminal set projected onto flow coordinates")}"></a>'
            f'<p><a href="{fuel_entry["page"]}">Open the fuel projections and timing figures →</a></p></article>' +
            f'<article class="saved-figure" id="{viz10_entry["anchor"]}"><p class="eyebrow">Historical and benchmark reports · Saved-data companion</p>'
            f'<h3>{escape(viz10_entry["title"])}</h3>'
            '<a href="viz10/index.html"><img src="viz10/b07-b07-reconstruction-s0-l0-d0.png" '
            'alt="B07 terminal points projected from four state coordinates onto oxidizer/fuel flow and stock axes"></a>'
            '<p>Plots saved B07 and B09 four-state terminal rows in labeled flow and stock coordinate pairs. The figures show points and do not reconstruct a filled enclosure.</p>'
            '<p><a href="viz10/index.html">Open the historical and benchmark saved-data plots →</a></p></article>' +
            '</div></section><footer>Controlled Systems Lab · Saved evidence, visible geometry.</footer></main></div>'
            '<script>document.querySelector(".nav-shortcut").addEventListener("click",event=>{'
            'const target=document.querySelector(event.currentTarget.hash);if(!target)return;'
            'event.preventDefault();history.pushState(null,"",event.currentTarget.hash);'
            'target.scrollIntoView({behavior:"instant",block:"start"});});</script></body></html>')
    outputs["index.html"] = body
    export = [{key: value for key, value in e.items() if key not in {"records_path", "domain"}} for e in examples]
    outputs["minimal-inputs.json"] = json.dumps({"schema": "csl.visual-examples/1", "examples": export}, indent=2) + "\n"
    outputs["visual-coverage.json"] = json.dumps(
        {"schema": "csl.visual-gallery-inventory/1", "entries": gallery_inventory}, indent=2) + "\n"
    outputs["visual-route-inventory.json"] = json.dumps(
        audit_visual_routes.build(Path(__file__).resolve().parents[2]), indent=2, ensure_ascii=False) + "\n"
    outputs["algorithm-coverage.json"] = json.dumps(coverage_data, indent=2, ensure_ascii=False) + "\n"
    outputs.update(fuel_layer_files)
    outputs["issue3-control-walkthrough.svg"] = workflow_figure
    outputs["issue3-control-walkthrough.html"] = workflow_page
    outputs.update(lotka_companion)
    outputs.update(app02_companion)
    outputs.update(app03_companion)
    outputs.update(app04_companion)
    outputs.update(ext05_companion)
    outputs.update(ext01_companion)
    outputs.update(app01_companion)
    outputs.update(hybrid_examples.download_records(examples))
    link = '<p id="visual-examples-link"><a href="examples/index.html">Visual examples: minimal 2D inputs, hull vertices and plots →</a></p>'
    output_files = {name: (content if isinstance(content, bytes) else content.encode("utf-8"))
                    for name, content in outputs.items()}
    output_files["examples.css"] = Path(__file__).with_name("visual_examples.css").read_bytes()

    with tempfile.TemporaryDirectory(prefix="csl-gallery-validation-") as temporary:
        validation_site = Path(temporary)
        validation_out = validation_site / "examples"
        validation_out.mkdir()
        for name, content in output_files.items():
            target = validation_out / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        references = []
        for entry in gallery_inventory:
            for field in ("page", "walkthrough_page", "figure", "source_page", "raw_record", "report_records"):
                value = entry.get(field)
                references.extend(value if isinstance(value, list) else [value])
        for value in references:
            if not isinstance(value, str) or urlsplit(value).scheme:
                continue
            ref = value.split("#", 1)[0]
            staged = (validation_out / ref).resolve()
            if staged.is_relative_to(validation_site) and staged.is_file():
                continue
            source = (out / ref).resolve()
            if not source.is_relative_to(site):
                raise ValueError("visual inventory reference escapes the site")
            relative = source.relative_to(site)
            staged = validation_site / relative
            current = site
            for part in relative.parts:
                current = current / part
                require(not current.is_symlink(), "visual inventory source must not be a symlink")
            require(source.is_file(), "visual inventory source is missing")
            source_file = source
            staged.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_file, staged)
        validate_gallery_inventory(validation_out, gallery_inventory)

    site_files = {"examples/" + name: content for name, content in output_files.items()}
    if 'id="visual-examples-link"' not in original:
        site_files["index.html"] = re.sub(
            r"(<body\b[^>]*>)", lambda match: match[1] + link, original, count=1).encode("utf-8")
    plan = site_additions.prepare(site, site_files, replace_existing=frozenset(site_files))
    site_additions.commit(plan)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    build(args.catalog, args.site)


if __name__ == "__main__":
    main()
