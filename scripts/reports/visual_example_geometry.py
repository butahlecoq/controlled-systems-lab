"""Saved geometry case ownership for the educational gallery."""
from __future__ import annotations

import json
import re
from pathlib import Path
from html import escape

import geo04_registered_reports as intersection_reports
import geo06_registered_reports as hull_reports
import report_data
from report_data import require


def load_examples(catalog):
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


def presentation(example):
    """Return the saved-geometry case explanation and its reproduction contract."""
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
        caption = "Green: hull boundary; amber: omitted points. Slash-separated original IDs coincide. Equal x/y scale."
        platform_note = ('For Visual Studio, use its developer shell, configure with its generator, and run '
                         '<code>Release/csl_geo06_quickhull_report.exe --smoke</code> in the build directory. '
                         'This is a functional smoke, not a new benchmark; discard smoke timing values.')
        report_links = (f'<p><a href="../{example["report_id"]}/index.html">Reviewed numerical report ↗</a> · '
                        f'<a href="../{example["report_id"]}/records.json">Full saved native records ↗</a></p>')
        provenance = f'<p class="provenance">Algorithm source <code>{example["source"]}</code></p>'
    else:
        explanation = ("Keep points that satisfy both shapes: the square −1 ≤ x,y ≤ 1 and the diamond "
                       "|x| + |y| ≤ 1.5. Each shape cuts off four corners of the other. The shared region is an octagon.")
        result = "Expected vertices: (±1, ±0.5) and (±0.5, ±1), all sign combinations."
        notes = ("The plot uses the saved native vertex coordinates, not idealized oracle replacements. "
                 "Qhull/HiGHS outputs match this fixture within absolute tolerance 1e−7; they are numerical geometry, "
                 "not a validated exact enclosure. Vertex row order is not a promised cyclic boundary order.")
        option, target, flags = "GEO04", "csl_geo04_intersection_report", ""
        driver = "reports/algorithm-results/tooling/geo04/polyhedral_intersection_driver.cpp"
        extra = "<p>The complete inputs below use A·[x,y] ≤ b for each shape. The driver links CSL::polyhedral, CSL::qhull_conversion and CSL::highs_lp.</p>"
        caption = "Green: returned intersection. Blue: input square; amber: input diamond. Labels are saved output row IDs. Equal x/y scale."
        platform_note = ('For Visual Studio, use its developer shell, configure with its generator, and run '
                         '<code>Release/csl_geo04_intersection_report.exe --smoke</code> in the build directory. '
                         'This is a functional smoke, not a new benchmark; discard smoke timing values.')
        report_links = (f'<p><a href="../{example["report_id"]}/index.html">Reviewed numerical report ↗</a> · '
                        f'<a href="../{example["report_id"]}/records.json">Full saved native records ↗</a></p>')
        provenance = f'<p class="provenance">Algorithm source <code>{example["source"]}</code></p>'
    command = (f'cmake -S . -B build/visual-{option.lower()} -DCMAKE_BUILD_TYPE=Release '
               f'-DBUILD_TESTING=OFF -DCSL_BUILD_{option}_REPORT=ON{flags}\n'
               f'cmake --build build/visual-{option.lower()} --config Release --target {target} --parallel 2\n'
               f'./build/visual-{option.lower()}/{target} --smoke')
    return {
        "explanation": explanation, "result": result, "notes": notes, "caption": caption,
        "example_type": "2D geometry", "extra": extra, "command": command,
        "reproduction": f'<p>From a checkout of harness commit <code>{example["harness"]}</code>, using CMake 3.31+ and a C++20 compiler:</p>',
        "platform_note": platform_note,
        "source_url": "https://github.com/butahlecoq/controlled-systems-lab/blob/" + example["harness"] + "/" + driver,
        "source_provenance": provenance,
        "raw_record_link": "",
        "report_links": report_links,
    }


def inventory_entry(example):
    family = ("Polytope hull construction" if example["kind"] == "hull"
              else "Polytope intersection")
    return {
        "family": family,
        "title": example["title"],
        "status": "educational-example",
        "anchor": example["slug"],
        "page": "index.html#" + example["slug"],
        "figure": example["slug"] + ".svg",
        "source_page": f'../{example["report_id"]}/index.html',
        "raw_record": f'../{example["report_id"]}/records.json',
    }
