"""Stage educational 2D illustrations from reviewed native records, without solving."""
from __future__ import annotations

import argparse
from html import escape
import json
import math
from pathlib import Path
import re
import shutil

import geo04_registered_reports as intersection_reports
import geo06_registered_reports as hull_reports
import report_data


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_examples(catalog):
    """Validate source bundles using their existing publishers before reading data."""
    catalog = Path(catalog)
    entries = json.loads(catalog.read_text(encoding="utf-8"))["reports"]
    selected = {}
    # Pin the educational snapshots, so a later report of the same kind does
    # not silently change an example or make catalogue selection ambiguous.
    for kind, source_id, adapter in (("geo06-quickhull", "geo06-b010fb3df212604b", hull_reports),
                                     ("geo04-intersection", "geo04-20261012T224946Z-c37852bcc80d", intersection_reports)):
        matches = [entry for entry in entries
                   if entry["report_kind"] == kind and entry["source_report_id"] == source_id]
        require(len(matches) == 1, "gallery needs one reviewed " + kind + " report")
        entry = matches[0]
        for key in ("source_report_id", "report_id"):
            require(re.fullmatch(r"[A-Za-z0-9-]+", entry[key]) is not None, "unsafe report route")
        bundle = catalog.parent / entry["source_report_id"]
        publication = adapter.adapt(bundle)
        require(publication.report_id == entry["report_id"], "catalogue publication identity differs")
        records_path = report_data.local_file(bundle, "records.json")
        selected[kind] = (entry, json.loads(records_path.read_text(encoding="utf-8")), records_path)

    entry, record, records_path = selected["geo06-quickhull"]
    examples = []
    for name, title, domain in (("square_duplicates", "Find the convex hull", (-.25, 1.25)),
                                 ("collinear_endpoints", "When the hull is a line", (-.5, 3.5))):
        fixture = record["catalog"][name]
        rows = [row for row in record["rows"] if row["scenario"] == name]
        indices = [int(value) for value in rows[0]["indices"].split(":")]
        examples.append(dict(slug=name, title=title, points=fixture["points"], indices=indices,
                             vertices=[fixture["points"][i] for i in indices], domain=domain,
                             inputs={"points": fixture["points"]}, report_id=entry["report_id"],
                             records_path=records_path, source=record["source_commit"],
                             harness=record["harness_commit"], kind="hull"))

    entry, record, records_path = selected["geo04-intersection"]
    trial = next(row for row in record["trials"] if row["scenario"] == "crossing_octagon")
    vertices = trial["vertices_json"]
    # Separate literal geometric oracle; do not replace native floating outputs
    # by these ideal vertices in the plot, table or downloadable example record.
    expected = {(1,.5),(1,-.5),(-1,.5),(-1,-.5),(.5,1),(-.5,1),(.5,-1),(-.5,-1)}
    require(len(vertices) == 8 and {tuple(round(v, 7) for v in p) for p in vertices} == expected,
            "intersection differs from the eight literal vertices")
    examples.append(dict(slug="crossing_octagon", title="Intersect two sets", vertices=vertices,
                         points=vertices, indices=list(range(8)), domain=(-1.8, 1.8),
                         inputs=record["expected"]["crossing_octagon"]["inputs"],
                         report_id=entry["report_id"], records_path=records_path,
                         source=record["algorithm"]["source_commit"],
                         harness=record["algorithm"]["harness_commit"], kind="intersection"))
    return examples


def plot(example):
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
                   "Blue dashed square and amber dashed diamond overlap in the green eight-vertex intersection. Labels are saved output row IDs.")
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 580 510" role="img" '
            'aria-labelledby="title desc"><title id="title">' + escape(example["title"]) + '</title>'
            '<desc id="desc">' + description + '</desc><rect width="580" height="510" fill="#172019"/>'
            '<g font-family="monospace" font-size="14" fill="#d1d9cc">' + "".join(elements) +
            '<text x="285" y="502" text-anchor="middle">x (dimensionless)</text>'
            '<text x="18" y="245" transform="rotate(-90 18 245)" text-anchor="middle">y (dimensionless)</text>'
            '</g></svg>')


def point_table(example):
    rows = []
    seen = {}
    for index, p in enumerate(example["points"]):
        if example["kind"] == "intersection":
            role = "intersection vertex"
        elif tuple(p) in seen:
            role = "duplicate of point " + str(seen[tuple(p)])
        else:
            role = "hull vertex" if index in example["indices"] else "interior / omitted"
        seen.setdefault(tuple(p), index)
        rows.append(f'<tr><td>{index}</td><td>{p[0]:.6g}</td><td>{p[1]:.6g}</td><td>{role}</td></tr>')
    heading = "Original point ID" if example["kind"] == "hull" else "Saved output row ID"
    return ('<div class="scroll" tabindex="0" role="region" aria-label="Point coordinates"><table>'
            f'<caption>Coordinates (rounded to six significant digits; raw JSON retains binary64 values)</caption>'
            f'<thead><tr><th scope="col">{heading}</th><th scope="col">x</th><th scope="col">y</th>'
            '<th scope="col">Role</th></tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>')


def section(example, number):
    if example["kind"] == "hull":
        explanation = ("Stretch a rubber band around these points. The band touches only the extreme vertices; "
                       "the center point does not change the hull. Coincident input rows share one location.")
        if example["slug"] == "collinear_endpoints":
            explanation = ("All points lie on y = x. The convex hull is the segment from (0, 0) to (3, 3), "
                           "so only its two endpoints are retained. Intermediate collinear points are omitted.")
        result = "Returned original vertex IDs: " + json.dumps(example["indices"]) + "."
        notes = ("The first input ID wins for coincident points. Polygon vertices start at the lexicographically "
                 "smallest point and continue counterclockwise, without repeating the closing vertex. "
                 "QuickHull uses exact orientation for the supplied binary64 coordinates; these small cases do not establish general performance.")
        option, target = "GEO06", "csl_geo06_quickhull_report"
        flags = " -DCSL_ENABLE_HIGHS=OFF -DCSL_ENABLE_QHULL=OFF"
        driver = "benchmarks/reporting/geo06/quickhull_driver.cpp"
        extra = ('<details><summary>Minimal public C++ call</summary><pre><code>' + escape(
            '#include <csl/geometry/quickhull_2d.hpp>\n#include <iostream>\n#include <vector>\n\n'
            'int main() {\n    const std::vector<csl::Vector> points = ' +
            json.dumps(example["points"]).replace("[", "{").replace("]", "}") + ';\n'
            '    auto result = csl::geometry::quickhull_2d(points);\n'
            '    const auto* hull = std::get_if<csl::geometry::QuickHull2D>(&result);\n'
            '    if (!hull) return 1;\n'
            '    for (auto id : hull->vertex_indices) std::cout << id << " ";\n}\n'
            '// Link the installed target CSL::quickhull_2d (C++20).\n') + '</code></pre></details>')
    else:
        explanation = ("Keep points that satisfy both shapes: the square −1 ≤ x,y ≤ 1 and the diamond "
                       "|x| + |y| ≤ 1.5. Each shape cuts off four corners of the other. The shared region is an octagon.")
        result = "Expected vertices: (±1, ±0.5) and (±0.5, ±1), all sign combinations."
        notes = ("The plot uses the saved native vertex coordinates, not idealized oracle replacements. "
                 "Qhull/HiGHS outputs match this fixture within absolute tolerance 1e−7; they are numerical geometry, "
                 "not a validated exact enclosure. Vertex row order is not a promised cyclic boundary order.")
        option, target = "GEO04", "csl_geo04_intersection_report"
        flags = " -DCSL_ENABLE_HIGHS=ON -DCSL_ENABLE_QHULL=ON"
        driver = "benchmarks/reporting/geo04/polyhedral_intersection_driver.cpp"
        extra = "<p>The complete inputs below use A·[x,y] ≤ b for each shape. The driver links CSL::polyhedral, CSL::qhull_conversion and CSL::highs_lp.</p>"
    command = (f'cmake -S . -B build/visual-{option.lower()} -DCMAKE_BUILD_TYPE=Release '
               f'-DBUILD_TESTING=OFF -DCSL_BUILD_{option}_REPORT=ON{flags}\n'
               f'cmake --build build/visual-{option.lower()} --config Release --target {target} --parallel 2\n'
               f'./build/visual-{option.lower()}/{target} --smoke')
    source_url = "https://github.com/butahlecoq/controlled-systems-lab/blob/" + example["harness"] + "/" + driver
    return (f'<section id="{example["slug"]}"><p class="eyebrow">Example {number:02d} / 2D geometry</p>'
            f'<h2>{example["title"]}</h2><p>{explanation}</p>'
            f'<figure><img src="{example["slug"]}.svg" alt="{escape(explanation, quote=True)}">'
            '<figcaption>Green: returned boundary. Labels identify original points or saved output rows. '
            'Intersection inputs: blue square, amber diamond. Equal x/y scale.</figcaption></figure>'
            f'<p class="answer">{result}</p>{point_table(example)}'
            '<details><summary>Complete minimal input</summary><pre><code>' + escape(json.dumps(example["inputs"], indent=2)) + '</code></pre></details>'
            + extra + '<details><summary>Reproduce the native functional example</summary>'
            f'<p>From a checkout of harness commit <code>{example["harness"]}</code>, using CMake 3.31+ and a C++20 compiler:</p>'
            '<pre><code>' + escape(command) + '</code></pre>'
            '<p>For Visual Studio, use its developer shell, configure with its generator, and run '
            '<code>Release/' + target + '.exe --smoke</code> in the build directory. '
            'This is a functional smoke, not a new benchmark; discard smoke timing values.</p>'
            f'<p><a href="{source_url}">Complete native fixture/driver ↗</a></p></details>'
            f'<p class="limits">{notes}</p><p class="provenance">Algorithm source <code>{example["source"]}</code></p>'
            f'<p><a href="../{example["report_id"]}/index.html">Reviewed numerical report ↗</a> · '
            f'<a href="../{example["report_id"]}/records.json">Full saved native records ↗</a></p></section>')


def build(catalog, site):
    examples = load_examples(catalog)
    site = Path(site).resolve(strict=True)
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
    out.mkdir(exist_ok=True)
    outputs = {e["slug"] + ".svg": plot(e) for e in examples}
    navigation = "".join(f'<a href="#{e["slug"]}">{e["title"]}</a>' for e in examples)
    body = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Visual examples · Controlled Systems Lab</title><link rel="stylesheet" href="examples.css"></head>'
            '<body><a class="skip" href="#main">Skip to examples</a><div class="shell"><aside>'
            '<a class="brand" href="../index.html">[ csl ]<br>Controlled Systems Lab</a>'
            '<p class="eyebrow">Learn by looking</p><nav aria-label="Examples">' + navigation +
            '<a href="../index.html">All numerical reports ↗</a></nav></aside><main id="main">'
            '<header><p class="eyebrow">Small inputs / visible answers</p><h1>Algorithms,<br><em>in two dimensions.</em></h1>'
            '<p>See what goes in, what comes out, and why. Start with hull vertices, then intersect two simple sets.</p>'
            '<p class="limits">These are educational illustrations of reviewed saved outputs, not an execution trace '
            'or new performance measurements. All configurations are complete and every result links back to native records.</p>'
            '<p><a href="minimal-inputs.json" download>Download inputs and displayed outputs (JSON)</a></p></header>'
            + "".join(section(e, i+1) for i, e in enumerate(examples)) +
            '<section><h2>Next: control in the plane</h2><p>Position/velocity trajectories and reachable sets are a planned extension. '
            'The true two-state scenario is tracked in <a href="https://github.com/butahlecoq/controlled-systems-lab/issues/421">#421</a>; '
            'current scalar integrator examples do not establish a two-state demonstration.</p></section>'
            '<footer>Controlled Systems Lab · Saved evidence, visible geometry.</footer></main></div></body></html>')
    outputs["index.html"] = body
    export = [{key: value for key, value in e.items() if key not in {"records_path", "domain"}} for e in examples]
    outputs["minimal-inputs.json"] = json.dumps({"schema": "csl.visual-examples/1", "examples": export}, indent=2) + "\n"
    for name, content in outputs.items():
        require(not (out / name).is_symlink(), "gallery file must not be a symlink")
        (out / name).write_text(content, encoding="utf-8")
    require(not (out / "examples.css").is_symlink(), "gallery stylesheet must not be a symlink")
    shutil.copyfile(Path(__file__).with_name("visual_examples.css"), out / "examples.css")
    link = '<p id="visual-examples-link"><a href="examples/index.html">Visual examples: minimal 2D inputs, hull vertices and plots →</a></p>'
    if 'id="visual-examples-link"' not in original:
        index.write_text(re.sub(r"(<body\b[^>]*>)", lambda match: match[1] + link, original, count=1), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    build(args.catalog, args.site)


if __name__ == "__main__":
    main()
