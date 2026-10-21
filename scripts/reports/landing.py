"""Render a readable landing page for the published algorithm report archive.

The Pages root index is assembled from the immutable catalogue and from the
per-family staging scripts, each of which appends one list item. This module
turns that assembled list into a page a reader can navigate: every report gets
a plain-language title and summary, the report's own measured scope and
evidence limits, and direct links to the report page, its raw records, its
measured tables and its offline bundle.

The page reuses the published report appearance - the dark Gruvbox palette,
system sans-serif, cyan links, green headings and orange code used by the saved
report pages - so the archive index and the reports read as one site.

Every published report family needs a human-readable description here. A
missing family is an error, not a silently cryptic list entry, so a newly
published report cannot reach the archive without an explanation.
"""
from __future__ import annotations

import argparse
from html import escape
from html.parser import HTMLParser
from pathlib import Path
import re


# Reading order of the archive. Each entry is (key, heading, introduction).
GROUPS = (
    ("optimization", "Convex optimization",
     "Optimizers and hull construction. These reports measure one registered adapter on small, "
     "hand-checkable inputs and record what the solver returned and how long it took."),
    ("geometry", "Geometry",
     "Set and polyhedron operations. These reports apply the registered geometry and conversion "
     "ports to small bounded fixtures and check the returned representation against literal "
     "expected values."),
    ("synthesis", "Control synthesis",
     "Reachability, terminal minimizers and complete strategy families for discrete-time "
     "control. These reports record which relations were constructed, which verifier accepted "
     "them and what the measured calls cost."),
    ("extensions", "Extensions and models",
     "Approximation, replay and extension profiles: boxes, zonotopes, ellipsoids, discretized "
     "and hybrid models, and sampled plant replays."),
    ("verification", "Verification and profiling",
     "Independent re-checks of saved witnesses and diagnostic process profiles kept separate "
     "from the published latency statistics."),
)


# Report family -> (group key, title, plain-language summary). The family key is
# the longest matching prefix of a report ID.
FAMILIES = {
    "lp": ("optimization", "Linear programming reference run",
           "Runs the registered HiGHS linear-programming adapter on five small analytic "
           "microfixtures and records the solved objective, the solver status and the timing of "
           "every call. It is the reference path that later optimization reports compare their "
           "own adapters against, so it measures one adapter only."),
    "convex": ("optimization", "Convex optimization reference run",
               "Runs the registered HiGHS convex adapter on nine small analytic microfixtures and "
               "records the returned optimum, the solver status and the timing of every call. "
               "Like the linear reference run it measures a single adapter and makes no "
               "solver comparison."),
    "opt04": ("optimization", "Phase-one feasibility search",
              "Searches for a feasible point of equality- and nonnegativity-constrained problems "
              "with an internal phase-one method, then checks the returned witness against an "
              "independent HiGHS reference. The report records feasibility outcomes and timing; a "
              "witness is not a description of the complete feasible set."),
    "opt05-hull": ("optimization", "Convex hull construction",
                   "Builds the convex hull of square lattices of points and compares the result "
                   "with an independently checked hull. The recorded trials cover small lattices "
                   "only, and the checks are numerical rather than exact."),
    "opt06": ("optimization", "Basis reuse across linear programs",
              "Measures a paired workflow in which the solver basis of one linear program is "
              "reused for the next, over three small two-dimensional point clouds. The numbers "
              "are descriptive paired timings; they do not establish a general speedup."),
    "opt07": ("optimization", "Ordered hull construction with exact certificates",
              "Runs measured batches of the ordered-hull builder over three fixed small point "
              "clouds and independently checks each produced hull with exact dyadic deletion "
              "certificates. The timings are single-adapter observations on one host."),
    "opt11": ("optimization", "Recursive hull construction",
              "Compares a recursive hull construction with a baseline hull on the same three "
              "fixed binary64 point clouds, alternating baseline and recursive batches. The "
              "comparison is descriptive and specific to the recorded backend and host."),
    "opt12": ("optimization", "Warm-start transfer cost",
              "Measures how much work can be saved when a solved linear program is reused as a "
              "warm start for the next one, over three synthetic linear programs with seven "
              "alternating repetitions per side. The observed transfer-cost ranges overlap, so "
              "the report keeps its performance interpretation inconclusive."),
    "geo02": ("geometry", "Affine maps and Minkowski sums",
              "Applies affine maps and independent Minkowski sums to small point clouds and "
              "checks the returned geometry against literal expected values. The later run adds "
              "exact dyadic deletion certificates for the generated binary64 candidate hulls; "
              "the earlier run keeps the full candidate cloud."),
    "geo03": ("geometry", "Vertex and half-space conversion",
              "Converts small bounded two-dimensional fixtures between the vertex and half-space "
              "representations in both directions and checks the results. The report covers "
              "contract fixtures only, with no workload-size baseline and no inner conversion "
              "phase timing."),
    "geo04": ("geometry", "Polyhedral intersection",
              "Intersects small analytic polyhedra and records the returned representation and "
              "the timing of every attempt. The HiGHS-based reduction remains incomplete and "
              "retains all rows, and no comparator or speedup claim is made."),
    "geo05": ("geometry", "Projection and predecessors",
              "Projects small bounded two-dimensional fixtures and computes their predecessor "
              "sets, recording the outcome of every attempt. Support for the half-space "
              "relation remains unestablished, and the checks are numeric samples rather than "
              "exact set equality."),
    "geo06": ("geometry", "QuickHull hull construction",
              "Runs measured batches of a thousand QuickHull calls over three small analytic "
              "point clouds and verifies every produced hull against a literal oracle. The "
              "timed interval includes index copies and the oracle comparison itself."),
    "geo07-generator-sets": ("geometry", "Generator-set evaluation",
                              "Evaluates generator-set requests over three bounded public "
                              "generator-set fixtures, with five thousand fresh calls per "
                              "measured batch. These are exploratory single-adapter timings "
                              "without a comparator or a limiter profile."),
    "geo07-registered-ports": ("geometry", "Registered geometry and conversion ports",
                                "Drives the registered geometry and conversion ports over three "
                                "bounded public fixtures, five thousand fresh calls per batch. "
                                "The observations are exploratory and inconclusive."),
    "geo07-dependent-registered": ("geometry", "Dependent Minkowski sums",
                                   "Measures dependent-sum requests through the registered ports "
                                   "over two bounded public fixtures, with two thousand checked "
                                   "calls per batch. Only single-adapter observations on the "
                                   "recorded host are reported."),
    "geo08": ("geometry", "Lazy geometry",
              "Checks a planar set expression that is evaluated only when a support query asks "
              "for it, and then materializes the native vertex form. It shows that a lazy set "
              "can be queried and materialized consistently on a small example."),
    "syn01": ("synthesis", "Nominal forward reachability",
              "Propagates reachable states forward for two authored scalar analytic fixtures "
              "over a two-step discrete horizon and checks the bounds of the returned row. The "
              "reachability relation is numerical and is not a validated certificate."),
    "syn02": ("synthesis", "Terminal minimizers",
              "Optimizes a supplied terminal objective over a supplied terminal slice and "
              "returns the candidate minimizers together with a sampled relation. This is a "
              "terminal subproblem rather than a complete control synthesis, and one shifted "
              "fixture returns an undetermined numerical failure."),
    "syn03-strategy-a-ts01": ("synthesis", "Strategy A on the T-S01 profile",
                              "Runs the registered Strategy A synthesis path on the exact "
                              "two-step scalar integrator profile and verifies the produced "
                              "relation with the registered analytic verifier. The seven "
                              "measured trials describe one strategy, not a comparison."),
    "syn03-strategy-a-ts02": ("synthesis", "Strategy A on the T-S02 profile",
                              "Runs Strategy A on the constant-integrator profile: forward "
                              "reachability and terminal optimization through the registered "
                              "HiGHS provider, followed by reconstruction and verification of the "
                              "full history relation."),
    "syn04-strategy-b-ts01": ("synthesis", "Strategy B on the T-S01 profile",
                              "Runs the registered Strategy B synthesis path on the exact "
                              "two-step scalar integrator profile and verifies the resulting "
                              "complete-family relation with the registered analytic verifier. A "
                              "separate diagnostic profile is excluded from the reported "
                              "statistics."),
    "syn04-strategy-b-ts02": ("synthesis", "Strategy B on the T-S02 profile",
                              "Runs Strategy B on the constant-integrator profile, where the "
                              "admitted path constructs and verifies the full feasible relation "
                              "analytically. The registered linear and convex providers are "
                              "prepared but their numerical solve operations are not invoked."),
    "syn07-ts01": ("synthesis", "Exact optimal relation for the T-S01 profile",
                   "Records the analytic theorem for the strict two-step scalar integrator "
                   "profile: the exact optimal relation together with exact membership examples. "
                   "Completeness is established only for that admitted profile, and the outer "
                   "API still reports numerical assurance."),
    "syn-ts01-paired": ("synthesis", "Paired Strategy A and B comparison on T-S01",
                        "Runs one paired experiment that alternates Strategy A and Strategy B "
                        "on the same exact-profile fixture, with one excluded warmup and seven "
                        "measured pairs. The timing distributions overlap, so no winner is "
                        "claimed."),
    "issue3-finite-catalogue": ("synthesis", "Finite-action minimax over a catalogue",
                                "Evaluates a finite catalogue of control actions with a minimax "
                                "rule over eight checked fixtures and records batch timings with "
                                "fixture-specific call counts. All winning flags and the selected "
                                "action cells are checked; the remaining cells of the action "
                                "tensor are not."),
    "finite-feedback-registered": ("synthesis", "Finite feedback games",
                                   "Plays authored finite games through the registered feedback "
                                   "port and checks every winning flag and selected action cell "
                                   "across four games. Concurrent work is not quantified, and no "
                                   "global causal minimax claim is made."),
    "b08-displayed-exact": ("synthesis", "Printed B08 model with an exact plan search",
                            "Searches 625 control plans over the 256 corners of the printed "
                            "rounded B08 linear model and checks the selected plan. The printed "
                            "rounded model is used as printed; the historical 67.12 value, the "
                            "unrounded arrays and the nonlinear plant remain unresolved."),
    "app01-plan": ("extensions", "State-plan check and trajectory verification",
                   "Runs the registered inner state-plan check and then verifies the produced "
                   "trajectory against the original problem statement over three literal scalar "
                   "fixtures."),
    "app02-box": ("extensions", "Box and parallelotope approximations",
                  "Approximates a small diamond by axis-aligned and by rotated parallelotopes, "
                  "and by inner boxes, checking every stored inclusion relation on exact "
                  "binary64 examples. A two-dimensional example shows the shapes."),
    "app03-zonotope": ("extensions", "Zonotope reduction and outer cover",
                       "Reduces a planar zonotope to an outer cover that keeps selected generator "
                       "factors and replaces the omitted ones with independent coordinate-axis "
                       "generators, verified from the stored coefficients. A two-dimensional "
                       "example shows the cover."),
    "app04-ellipsoid": ("extensions", "Directional ellipsoid approximation",
                        "Approximates a small convex set by a directional ellipsoid over three "
                        "planar cases and checks the returned parameters against the stored "
                        "values. A two-dimensional example shows the ellipse and the set."),
    "ext01-fixed-plan": ("extensions", "Fixed-plan worst-case evaluation",
                         "Evaluates a fixed control plan against worst-case disturbances over "
                         "four native fixtures using the convex provider. The result is a "
                         "numerical worst-case value for the displayed rounded model, not a "
                         "validated enclosure."),
    "ext04-observed-replay": ("extensions", "Observed replay of sampled systems",
                              "Replays sampled, explicitly observed system trajectories through "
                              "the public replay path and checks the recorded outcomes. The "
                              "observations are exploratory and cover one path only."),
    "ext05-discretization": ("extensions", "Continuous-model discretization",
                             "Discretizes a continuous double integrator into a discrete model "
                             "and checks the discrete transition against the continuous one. A "
                             "two-dimensional example shows the sampled trajectory."),
    "ext07-hybrid-two-parameter": ("extensions", "Hybrid system with two control parameters",
                                   "Checks a one-step hybrid system with switched dynamics and "
                                   "two control parameters, and records the measured calls of the "
                                   "registered hybrid path."),
    "ext07-hybrid": ("extensions", "Hybrid one-step verifier",
                     "Checks a one-step hybrid system with switched dynamics and a piecewise "
                     "linear state update, and records the measured calls of the registered "
                     "hybrid path."),
    "opt10-smooth": ("extensions", "Declared smooth-convex adapter",
                     "Runs the declared smooth-convex adapter on a two-dimensional box-quadratic "
                     "problem and checks the returned optimum and iterates against the stored "
                     "values. A two-dimensional example shows the problem."),
    "issue4-volterra": ("extensions", "Candidate Volterra model-error bound",
                        "Records a sixty-stage validated two-dimensional bound on the "
                        "same-control deviation between the candidate Volterra model and the "
                        "reference model. It is a candidate bound for one model pair, not a "
                        "general model-error certificate."),
    "exp04-replay": ("extensions", "Independent plant replay",
                     "Replays chosen controls on the public exact-discrete plant map over four "
                     "analytic histories and checks every trajectory and terminal objective. "
                     "The timings are exploratory single-adapter observations."),
    "syn06-verifier": ("verification", "Trajectory verification",
                       "Re-checks two literal two-stage integrator witnesses against the original "
                       "saved input data and confirms the published trajectories numerically."),
    "perf03-ts01": ("verification", "Process-scoped CPU profile for T-S01",
                    "A diagnostic CPU profile of the T-S01 path collected with process-scoped "
                    "sampling, exported with symbol and paired-timing tables. It is kept "
                    "separate from the published latency statistics."),
}


def stylesheet() -> str:
    return Path(__file__).with_name("landing.css").read_text(encoding="utf-8")


def family_for(report_id: str) -> str:
    """Return the longest registered family prefix of a report ID."""
    matches = [key for key in FAMILIES if report_id == key or report_id.startswith(key + "-")]
    if not matches:
        raise ValueError("no landing description for report family: " + report_id)
    return max(matches, key=len)


def collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def published_on(report_id: str) -> str:
    """Return the publication date carried by a report ID, if it has one."""
    match = re.search(r"(20\d{2})(\d{2})(\d{2})", report_id)
    return "{}-{}-{}".format(*match.groups()) if match else ""


def card(entry: dict, number: int, heading: str) -> str:
    """Render one report card from its entry data and its family description."""
    family = FAMILIES[family_for(entry["report_id"])]
    parts = ['<li><p class="eyebrow">' + escape(heading) + " &middot; " + f"{number:02}" + "</p>"]
    parts.append('<h3><a href="' + escape(entry["report_id"], quote=True) + '/index.html">'
                 + escape(family[1]) + "</a></h3>")
    parts.append('<p class="summary">' + escape(family[2]) + "</p>")
    if entry.get("scope"):
        parts.append('<p class="card-scope"><strong>What was measured.</strong> '
                     + escape(entry["scope"]) + "</p>")
    if entry.get("limits"):
        parts.append("<details><summary>Evidence limits</summary><p>" + escape(entry["limits"]) + "</p></details>")
    links = entry.get("links") or []
    if links:
        rendered = " &middot; ".join('<a href="' + escape(href, quote=True) + '">' + escape(label) + "</a>"
                                     for label, href in links)
        parts.append('<p class="card-links">' + rendered + "</p>")
    provenance = "Report ID"
    published = published_on(entry["report_id"])
    if published:
        provenance += " &middot; published " + escape(published)
    parts.append('<p class="card-provenance">' + provenance + "<code>" + escape(entry["report_id"])
                 + "</code>")
    if entry.get("commit"):
        parts.append("source commit<code>" + escape(entry["commit"]) + "</code></p></li>")
    else:
        parts.append("</p></li>")
    return "".join(parts)


def page(entries: list[dict], extras: list[tuple[str, str]] | None = None) -> str:
    """Render the complete landing page for the given report entries."""
    groups: dict[str, list[dict]] = {}
    for entry in entries:
        family = FAMILIES[family_for(entry["report_id"])]
        groups.setdefault(family[0], []).append(entry)
    cards = []
    number = 0
    for key, heading, introduction in GROUPS:
        items = groups.get(key)
        if not items:
            continue
        cards.append("<li><h2>" + escape(heading) + "</h2><p class=\"blurb\">" + escape(introduction) + "</p></li>")
        for entry in items:
            number += 1
            cards.append(card(entry, number, heading))
    extra_links = ""
    if extras:
        rendered = " &middot; ".join('<a href="' + escape(href, quote=True) + '">' + escape(label) + "</a>"
                                     for label, href in extras)
        extra_links = '<p class="hero-links" id="visual-examples-link">' + rendered + "</p>"
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            "<title>CSL algorithm reports</title><style>\n" + stylesheet() + "\n</style></head><body>"
            '<p class="eyebrow">Controlled Systems Lab &middot; research archive</p>'
            "<h1>Algorithm reports</h1>"
            '<p class="lede">This is the published archive of measured algorithm results. Every '
            "entry names the algorithm family, explains in plain language what the report "
            "measures, quotes the report&#8217;s own measured scope and evidence limits, and links "
            "to the report page, its raw records, its measured tables and its offline bundle.</p>"
            '<p class="meta">' + f"{len(entries)}" + " published reports &middot; versioned and "
            "reproducible &middot; numerical observations, not mathematical certificates</p>"
            + extra_links +
            '<div class="note"><p><strong>Read the evidence, not just the numbers.</strong> '
            "Measurements do not imply cross-method performance, application-scale results or "
            "mathematical certification. Each report states its own measured scope and its own "
            "limits; open a report before drawing a conclusion from it.</p></div>"
            '<div class="section"><h2>How to read this archive</h2><dl>'
            "<div><dt>Plain-language summary</dt><dd>What the algorithm family does and what this "
            "report measures, written for a reader who has not read the report yet.</dd></div>"
            "<div><dt>What was measured</dt><dd>The measured scope of the report, quoted from the "
            "published record so the wording stays the one the report itself carries.</dd></div>"
            "<div><dt>Evidence limits</dt><dd>What the report explicitly does not establish. These "
            "limits are part of the result, not a disclaimer attached to it.</dd></div>"
            "<div><dt>Links</dt><dd>The report page, the raw JSON record, the measured tables, the "
            "offline bundle and, where they exist, the visual examples and figures.</dd></div>"
            "<div><dt>Report ID and source commit</dt><dd>The exact published route and the source "
            "commit that produced it, so any number can be traced back to one code state.</dd></div>"
            "</dl></div>"
            '<div class="section"><div class="cards"><ul>' + "".join(cards) + "</ul></div></div>"
            '<div class="footer"><p>Controlled Systems Lab &middot; Numerical observations are '
            "not mathematical certificates.</p></div></body></html>")


class Node:
    def __init__(self, tag: str, attrs=()):
        self.tag = tag
        self.attrs = dict(attrs)
        self.children: list = []


VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}

# Separators used by the staging scripts between the parts of an index entry.
SEPARATORS = re.compile(r"^[\s\u00b7\u2014\u2013\-,;.:]+|[\s\u00b7\u2014\u2013\-,;.:]+$")


class Tree(HTMLParser):
    """Minimal HTML tree builder used to read an assembled index page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("#document")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Node(tag, attrs))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def elements(node: Node, tag: str | None = None, cls: str | None = None):
    for child in node.children:
        if isinstance(child, Node):
            if (tag is None or child.tag == tag) and (cls is None or cls in child.attrs.get("class", "").split()):
                yield child
            yield from elements(child, tag, cls)


def text(node: Node) -> str:
    parts = []
    for child in node.children:
        parts.append(child if isinstance(child, str) else text(child))
    return "".join(parts)


def entry_of(item: Node) -> dict:
    """Read one assembled index item into a landing entry."""
    anchors = [(node.attrs.get("href", ""), collapse(text(node))) for node in elements(item, "a")]
    reports = [anchor for anchor in anchors if re.fullmatch(r"[^/]+/index\.html", anchor[0])]
    if not reports:
        raise ValueError("index item without a report link")
    report_id = reports[0][0][: -len("/index.html")]
    codes = [collapse(text(node)) for node in elements(item, "code")]
    commits = [code for code in codes if re.fullmatch(r"[0-9a-f]{7,40}", code)]
    commit = commits[-1] if commits else ""
    link_items = next(iter(elements(item, "p", "card-links")), None)
    if link_items is not None:
        links = [(collapse(text(node)), node.attrs.get("href", "")) for node in elements(link_items, "a")]
    else:
        links = [(label, href) for href, label in anchors if href != reports[0][0]]
    scope_node = next(iter(elements(item, "p", "card-scope")), None)
    details = next(iter(elements(item, "details")), None)
    if scope_node is not None:
        scope = collapse(" ".join(child if isinstance(child, str) else text(child)
                                 for child in scope_node.children
                                 if not (isinstance(child, Node) and child.tag == "strong")))
        limits = collapse(" ".join(text(node) for node in elements(details, "p"))) if details is not None else ""
    else:
        parts = []
        for child in item.children:
            if isinstance(child, str):
                parts.append(child)
            elif child.tag in ("a", "code"):
                continue
            else:
                parts.append(text(child))
        description = collapse(" ".join(parts))
        description = SEPARATORS.sub("", description)
        description = re.sub(r"\s*source$", "", description)
        scope, _, limits = description.partition("; limits: ")
        limits = SEPARATORS.sub("", limits)
        if not scope and reports[0][1] and reports[0][1] != report_id:
            # Some staged routes carry their description in the link label itself.
            scope = reports[0][1]
    return {"report_id": report_id, "scope": scope, "limits": limits, "commit": commit, "links": links}


def parse_index(html: str) -> tuple[list[dict], list[tuple[str, str]]]:
    """Read an assembled index page into landing entries and extra page links."""
    tree = Tree()
    tree.feed(html)
    lists = list(elements(tree.root, "ul"))
    if not lists:
        raise ValueError("published index has no report list")
    entries = []
    for item in elements(lists[0], "li"):
        if any(isinstance(child, Node) and child.tag == "h2" for child in item.children):
            continue
        entries.append(entry_of(item))
    extras = []
    for node in elements(tree.root, "p"):
        if node.attrs.get("id") != "visual-examples-link":
            continue
        for anchor in elements(node, "a"):
            extras.append((collapse(text(anchor)), anchor.attrs.get("href", "")))
    return entries, extras


def validate(page_html: str, site: Path) -> None:
    """Reject links that leave the staged site or point at missing files."""
    tree = Tree()
    tree.feed(page_html)
    for anchor in elements(tree.root, "a"):
        href = anchor.attrs.get("href", "")
        if not href or href.startswith("#"):
            continue
        if href.startswith("https://github.com/butahlecoq/controlled-systems-lab/"):
            continue
        if href.startswith(("http://", "https://", "//")):
            raise ValueError("landing page links outside the staged site: " + href)
        target = (site / href).resolve()
        if site.resolve() not in target.parents or not target.is_file():
            raise ValueError("landing page links to a missing staged file: " + href)


def build(site: Path) -> None:
    """Replace the assembled index with the readable landing page."""
    site = Path(site)
    index = site / "index.html"
    entries, extras = parse_index(index.read_text(encoding="utf-8"))
    rendered = page(entries, extras)
    validate(rendered, site)
    index.write_text(rendered, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    build(args.site)


if __name__ == "__main__":
    main()
