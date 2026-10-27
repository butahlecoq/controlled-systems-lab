# Maintained numerical reporting

Collection, validation, saved-data rendering and publication tooling live here.
Native drivers and native report tests live in `benchmarks/reporting/<kind>`.
`reports/algorithm-results` contains immutable scientific bundles and catalogues;
its `tooling/<kind>` files are compatibility entry points to maintained code.
The kinds are geo02, geo03, geo04, geo05, opt04, syn01, syn02, syn03,
syn03_ts02, syn04, syn04_ts02, syn06, syn_ts01_paired and ts01. Their READMEs and schema files
are maintained alongside the Python code. Historical paths inside saved evidence,
source delta policies and pinned CMake insertions describe the original source;
they are retained literally and do not claim to describe today's layout.

## Lifecycle ownership

`collector_common.py` owns process capture (exit, launch error and timeout),
durable capture/validation diagnostics, redaction, actual Release File API graph
and physical artifact ownership, build-log path safety and the fresh clean verbose
rebuild mechanism. GEO-04 and GEO-05 both use these operations. Their collectors
retain CSV/JSONL parsing, fixture oracles, scientific source-delta admission,
mathematical schemas, trial ordering and timing rules. Same-commit current
source/harness collection requires the clean checkout and actual fresh rebuild;
separately pinned historical source/harness collection still requires its original
exact source/CMake delta proof. A source mismatch never becomes a build bypass.

`registered_reports.py` owns native inventory/path/hash validation and publication
page/envelope/manifest assembly shared by GEO-04/GEO-05, plus deterministic ZIP
and publication manifest validation used by the other adapters. Each kind's
adapter retains its scientific validation and typed page rendering. Rendering
and staging read saved data and never execute numerical collectors.

## Schema-v3 publication adapters

`publication_policy.py` is the staging seam for the 27 schema-v3 non-LP/convex
report kinds loaded by `schema3_publication_policies.py`. Each adapter's policy
binds its report kind to the publisher, source-directory identity rule,
catalogue links, and staging checks such as SVG validation or a committed
archive comparison. The publisher continues to own scientific validation,
report identity, rendering, and archive construction. Registration rejects
duplicate kinds; catalogue staging rejects unsupported kinds. The shared
`registered_reports.py` adapter owns its three policies together. Add or change
an adapter by updating its policy module and the import list in
`schema3_publication_policies.py`, the adapter's scientific checks as needed,
and `tests/reporting/test_publication_policy.py` plus the relevant adapter
test. Full-catalog staging is checked by `tests/reporting/test_registered_kinds.py`.

GEO-04, GEO-05 and B09 keep their policy declarations next to, but outside,
their publisher source files. Those publishers bind their own source bytes into
public report IDs. Moving policy declarations into those files would change
historical IDs even when rendered report bytes stayed the same. Policy wiring
therefore lives in separate files and the full-catalog tests compare report
IDs, page bytes, archive bytes, hashes and URLs against the saved catalogue.
This staging refactor has no C++ API, dependency, install-tree or package
release impact; publication behavior remains gated on exact saved-output
checks and independent review.

`site_additions.py` owns the common file-staging lifecycle for the educational
gallery and versioned report additions such as APP-02. Callers render all
intended bytes, validate their scientific and link inventories, then prepare a
plan that checks normalized paths, symlinks, destination types, freshness
requirements and existing-file fingerprints. No site path is created or written
until preparation succeeds. Gallery rebuilds may replace only files named in
their plan; APP-02 requires its report and example routes to be fresh. Existing
report bundles are read-only inputs. APP-02's published catalog retains its
historical stager fingerprint; newly generated catalog entries use the current
stager fingerprint.

Validation or preparation failures leave all pre-existing site bytes and paths
unchanged. During commit, route data and nested index pages are written before
the site-root `index.html`. A commit-time I/O error may leave some new or
replaced route files behind; the stager does not promise rollback. The root
index remains unchanged unless its final write succeeds. This guarantee does
not cover process crashes or concurrent writers. Gallery rebuilds intentionally
keep their existing route and can therefore be partially visible after a
commit-time failure. Re-run the gallery build to converge its generated files.

The explicit historical publication pins bind **both** the complete native
source inventory, any sibling archive used by the adapter identity, and the exact offline ZIP output. Current validation always
runs first. A changed source file or changed generated output cannot reuse a
historical route; the current content-bound identity applies. These pins preserve
existing IDs and bytes across mechanical moves, without extending scientific
admission to unreviewed sources. Published files and catalogue hashes are never
regenerated by this refactor.

## The published archive index

`site.py` renders the catalogue index and the per-family `stage_*.py` scripts
append their own entries to that same list. `landing.py` then reads the
assembled index and renders the published landing page: the reports are grouped
by topic, each one gets a plain-language title and summary, the scope and the
evidence limits recorded with that report, and links to its report page, raw
records, measured tables and offline bundle. The page reuses the dark
appearance of the saved APP-02, APP-03, EXP-04 and GEO-08 report pages.

`FAMILIES` in `landing.py` holds one description per report family together
with the pattern that matches its published routes. A route that matches no
registered family is an error, so a newly published report cannot reach the
archive unexplained, and a new route shape has to be registered on purpose.

## Figure readability policy

New quantitative SVG/PNG report figures use the pinned Matplotlib 3.11.2
renderer and the versioned `csl-report-quantitative-v1` axis policy in
`figure_style.py`. It positions major ticks, formats neighboring values
distinctly (including narrow ranges and small magnitudes), and draws a quiet
major grid. Use equal data scaling when both axes describe commensurate
geometric coordinates; label stages, units and independent scales explicitly.
Figures published as external images also need useful HTML alternatives and
reader-facing exact values or a linked saved-value table/record. A raw download
does not replace a concise description of what the figure shows.

Hand-authored SVG remains appropriate for small explanatory diagrams with
literal geometry. Keep those routes in the reviewed inventory and provide
labelled scales, accessible `<title>`/`<desc>`, and text values when the diagram
is quantitative. Do not rewrite a published evidence bundle to update its
presentation: add a separately versioned companion and link it from the mutable
gallery.

Regenerate the producer/route inventory with
`python scripts/reports/audit_visual_routes.py`. Its source scan deliberately
includes candidate producers and validators so contributors can review the
role instead of silently omitting a route; each frozen report route records its
existing image assets and page digest.

The scope and the limits on a card are read from the report's own staged
bundle - its publication envelope or its saved record - and not from the
wording of the script that staged it. The renderer only reads the assembled
index and the staged bundles; it never rewrites an immutable evidence bundle.

## Focused checks

```text
python -m unittest discover -s scripts/reports/geo05 -p "test_*.py"
python -m unittest discover -s scripts/reports/geo04 -p "test_*.py"
python -m unittest discover -s tests/reporting -p "test_*.py"
```

The same legacy tooling discovery commands remain supported. Native tests require
the configured report targets. Functional checks are not accepted measurements;
review, allocation and publication gates remain in
`docs/contracts/algorithm-report-records.md`.
