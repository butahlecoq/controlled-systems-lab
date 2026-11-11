# Pages report retirement audit

Audit date: 2026-11-11. Source baseline: `ed2dda1`. Research only: no solver, benchmark, report regeneration, build, publication or deletion was run.

## Finding

There are genuinely bare report pages in the current public archive, but “old HTML”, “no illustration”, “only a numerical plot” and “no educational example” are different predicates. The current visual inventory cannot safely determine which HTML should be deleted. The recommended change is to remove bare and superseded reports from the primary reading experience while retaining immutable evidence and their existing download URLs. Establish a new learning route as the primary entry point. A deliberate decision to break public evidence URLs requires an explicit exception to the present publication contract.

## Inventory and limitations

Counts below were computed by read-only Python filesystem/JSON scans at the baseline:

| Inventory | Count | Meaning |
|---|---:|---|
| `reports/algorithm-results/**/*.html` | 198 | All committed HTML, including nested evidence and non-index examples |
| `reports/algorithm-results/**/index.html` | 171 | Includes archive root and rejected/superseded/internal reports |
| Index pages with no `<img>`, `<svg>`, `<canvas>` or `<object>` tag | 16 | Syntactic candidate filter, not a quality assessment |
| Schema-3 catalogue rows / distinct kinds | 33 / 32 | Does not include every separately staged publication family |
| Visual inventory source signal candidates | 244 | Producers, collectors, staging code, validators and shared utilities mixed together |
| Visual inventory frozen routes | 150 | Only index pages with SVG/PNG files immediately beside the HTML |
| Frozen routes with deferred readability disposition | 148 | Not a declaration that these lack figures or educational examples |
| Frozen routes with an explicit companion mapping | 22 | Some map only to `examples/index.html`, not a specific lesson |
| Coverage-map families | 26 | Algorithm family coverage, not exhaustive module lessons |

Primary sources: [catalogue](../../reports/algorithm-results/catalog.json), [visual inventory](../../scripts/reports/visual-route-inventory.json), [inventory algorithm](../../scripts/reports/audit_visual_routes.py), [coverage map](../../scripts/reports/algorithm_visual_coverage.json).

`audit_visual_routes.py:frozen_routes` recurses over index pages but accepts a route only when its directory contains an immediate `.svg` or `.png`. It misses inline SVG and figures in subdirectories. Its source scan searches textual visual signals and classifies 101 sources as publication validation/frozen routes and 35 as deferred family migration; these are not 244 independent HTML generators. Its route name `frozen_published_routes` also includes rejected/nested repository evidence: inclusion does not prove deployment. This inventory is suitable for its plotting-policy migration purpose, not as a deletion allowlist.

The 16 local tag-free index pages have these preliminary dispositions. These are source-directory identities, not assumed public URLs.

| Source directory | Preliminary disposition |
|---|---|
| `finite-feedback-a6e96fd96c7ac7cc` | Bare native source; preserve, archive public wrapper, retain timing companion |
| `geo02-20261012T235755Z-6b1f504ad3db` | Bare native source; preserve, map published report to analytic lesson |
| `geo02-20261013T061151Z-338ff7d1d63c` | Bare native source; preserve, map published report to analytic lesson |
| `geo06-b010fb3df212604b` | Native source snapshot; keep; public adapter adds illustration |
| `.` | Navigation index; keep, not a numerical report |
| `issue3-finite-catalogue-b4632ce76510aa4f` | Bare native source; preserve, use existing explicit control walkthrough |
| `perf03-ts01-single-process-correlation-20261014` | Bare profiling evidence; archive public wrapper, preserve bytes |
| `rejected/finite-feedback-bee7e6d32c88451d` | Rejected evidence; preserve, exclude learner navigation |
| `review05-build-phases-20261110-468cc0eb` | Internal/historical evidence; preserve; current aggregate has graphics |
| `review05-horizon-match-20261031` | Internal/historical evidence; preserve; current aggregate has graphics |
| `review05-horizon-paired-20261103` | Internal/historical evidence; preserve; current aggregate has graphics |
| `review05-horizon-phase-20261104` | Internal/historical evidence; preserve; current aggregate has graphics |
| `review05-horizon-phase-providers-20261104` | Internal/historical evidence; preserve; current aggregate has graphics |
| `review05-horizon-resource-20261104` | Internal/historical evidence; preserve; current aggregate has graphics |
| `review05-horizon01-20261030` | Internal/historical evidence; preserve; current aggregate has graphics |
| `review05-horizon01-34bc9fdf-20261031` | Internal/historical evidence; preserve; current aggregate has graphics |

Conversely, some source pages contain a graphic tag but the published adapter does not retain that drawing. Local source checks cannot substitute for checking the actual publication. For example, GEO-05 appears in the public no-graphics list below although its source has a graphic tag. GEO-06 is the opposite: its source has no drawing, but [the publication adapter](../../scripts/reports/geo06_registered_reports.py) explicitly injects an inline square-hull illustration.

## Live deployment sample covering the root archive

Read-only HTTP GETs fetched the [public root](https://butahlecoq.github.io/controlled-systems-lab/) and all 120 distinct relative `*/index.html` links present there. All 120 returned HTTP 200. Eleven returned HTML without any of the four graphic tags above. This is exhaustive for that root-link set at observation time, not for every deployed file or every gallery subpage. A separate [gallery GET](https://butahlecoq.github.io/controlled-systems-lab/examples/index.html) returned 200 and graphic tags. The root itself has no graphic tags because it is a reading index, which is not a report defect.

Root HTML: 176,366 bytes, SHA-256 `29376974f806ad83816be9b42bda19fbeccaebc9a7ca79c291ed3d9ea3d522d2`. Gallery: 121,555 bytes, SHA-256 `50c11b02e03856b4ce15821caa5da5d15584f378b0354b48bab028d0d8e7960b`.

The following are concrete candidates to unlist from the primary report view pending classification and lesson mapping. The tag test establishes absence of embedded graphics, not absence of linked gallery examples.

| Public route stem (`/index.html`) | Owning publication/producer seam | Disposition to assess |
|---|---|---|
| `finite-feedback-registered-f874133e442eb0fb884b8813a06591cc0f077063ee75ddf627de74656fc11c0f` | `stage_finite_feedback.py`, `finite_feedback/render_saved.py`, custom publication catalogue | Bare report; retain finite-feedback timing companion separately |
| `geo02-20261012T235755Z-7275580339899c6ac27496fc2b05cb040d9fec14f8ec7f8bf219cc299c55eefc` | `geo02_registered_reports.py`, `geo02/render.py` | Bare older measurement; map to authored Minkowski lesson |
| `geo02-20261013T061151Z-449f188d2de1f50164a55a7b3b3931132dfa8384306ac3c93d5fb3a958cbd754` | Same GEO-02 publication seam | Bare follow-up measurement; avoid duplicate main reading cards |
| `geo03-20261012-30157d9ac59269cc26a2ca24dfd1744297971b435a8bba13dcb68f2a1dbcd104` | `geo03_registered_reports.py`, `geo03/build_report.py` | Bare publication; retain distinct H/V analytic example |
| `geo05-8918ad3ac4b0b3d1ff9c8b807d6b509f324ef3e9b11716be496c8e6e437f6795` | `geo05_registered_reports.py`, `geo05/render.py` | Bare published scalar report; authored 2D illustration is not a measured 2D run |
| `issue3-finite-catalogue-388b4be3a35ac10c9b42bf8f92ac5ae06b2120049dc6003791bc6487628478de` | `issue3_registered_reports.py`, `issue3/render_saved.py` | Bare finite-catalogue result; reuse saved timing and explicit control walkthrough |
| `opt04-20261013T172839Z-bf1844fdf81c94c82ca91aadbd9d0988c7367093c5cf70269c2d0e0ca7d44b2f` | `opt04_registered_reports.py`, `opt04/render.py` | Bare publication; analytic simplex-slice example already exists |
| `opt05-hull-20261012-d6d3282081d5ea90d8a0c440ccc1ec774d40221e209a01d8207ebd06a551dbf5` | Schema-3 `site.py` registration and OPT-05 adapter | Bare report; classify operation lesson separately from hull figure availability |
| `opt06-basis-reuse-20261014-ef70e8c5-57c666a4f82b1f7c84d3507fbad32982a7928129c18f80348ea2c9ad457b3a8d` | Schema-3 `site.py` registration and OPT-06 adapter | Bare solver-reuse measurement; a timing chart is still not a control lesson |
| `perf03-ts01-single-process-correlation-20261014-365f6e659e316219` | `stage_perf03.py` | Bare immutable profiling evidence; archive, do not manufacture a geometry lesson |
| `syn02-1b07970d73d90c79c4bba2c65d429ba05bd798751d885146cb21d8a876a067c3` | Schema-3 `site.py` registration and SYN-02 adapter | Bare terminal-synthesis result; map an educational control example |

All route stems above are appended to `https://butahlecoq.github.io/controlled-systems-lab/`. Representative fetched HTML SHA-256 values: finite feedback `f1ea91785a505993b4e14bbff199a210c5c96ade6654eb6f74774e0ad0ffbd02`; GEO-02 first `61f29ca4c2bd4d793d975e8808369494654b8d70f298dc3c00b4600bf0942c0e`; GEO-05 `9cf29bd3fb45f6796d89a6b2875b3b486ddd8939186b79548ee4d17ad04dad9a`; ISSUE-3 `0827c87958005ea9be02d5b41d1fa770875bfec096c97f7c12d9d2c34cb234bd`; PERF-03 `11053008684a14ba29041426dff02f18ffb7e7279059607576d222af0ab3e27d`.

The corresponding native finite-feedback source URL returned 404, as did `review05-horizon01-20261030/index.html`. The currently linked REVIEW-05 aggregate `review05-family-query-d6af180b0e398d78ebd2/index.html` returned 200 and contains graphics. These observations demonstrate why removing raw source directories solely because they look old would target evidence rather than the current public presentation.

## Classification contract for the retirement work

Record three independent fields for each public route:

1. **Illustration presence:** none; analytic diagram; saved numerical state/set/control plot; timing/resource plot. Mark invalid/broken assets separately. A file next to a page does not prove that page embeds it.
2. **Educational completeness:** inputs/model, objective, constraints, method choice, intermediate sets/steps, computed result, replay/controller behavior, limitations and reproducible saved-data path. A numerical plot without these is not a complete educational example.
3. **Evidence/publication role:** current registered result; immutable source snapshot; superseded/rejected research evidence; archive index; lesson; download. Rejected evidence must not become a successful result merely because it has an attractive graphic.

The existing [analytic illustration producer](../../scripts/reports/visual_illustrations.py) explicitly distinguishes authored formulas from saved measurements: GEO-05's 2D box predecessor illustration is not a 2D solver result, and OPT-04's barycentric slice is not a solver trace. The [gallery assembler](../../scripts/reports/visual_examples.py) also contains saved timing companions, geometry sections, family coverage and an explicit ISSUE-3 control walkthrough. These should become reusable lesson content with clear authority labels rather than being counted as interchangeable “examples”.

## Producers and publication seams to change

The current website has multiple writers. [site.py](../../scripts/reports/site.py) validates the schema-3 catalogue, builds adapter-generated publication artifacts and ZIPs, and also preserves pinned legacy sources. [visual_examples.py](../../scripts/reports/visual_examples.py) composes the gallery. [landing.py](../../scripts/reports/landing.py) reconstructs the root from the catalogue and links appended by family staging scripts; it requires every published family to have a human-readable description. [algorithm-reports.yml](../../.github/workflows/algorithm-reports.yml) stages custom families in addition to the 33-row catalogue, then stages the gallery and landing. Its later MPC staging steps can append links after landing rendering. [augment_pages_bundle.py](../../scripts/reports/augment_pages_bundle.py) and [the augmentation aggregation workflow](../../.github/workflows/pages-augmentation-aggregation.yml) add further verified routes to the downloaded base Pages artifact.

A root-filter-only fix will drift if these writers can re-add old report cards. Introduce one route registry covering catalogue adapters, family staging and augmentation, with explicit visibility (`learning`, `archive`, `hidden-evidence`), replacement lesson and immutable artifact identity. Make every writer consume it, and validate the final upload artifact, after all augmentation. Inventory the uploaded artifact rather than assuming the 33 catalogue rows are the complete website.

Recent source history reinforces the distinction: `c71c111b` supports nested report records; `ffa0a835` registers source comparisons while preserving publication provenance; `0a21e87a` publishes the B04-C dossier as research-only evidence. The report-content evidence role must survive the navigation consolidation.

## Safe retirement sequence and acceptance gates

1. Create an exhaustive route manifest from the final composed Pages artifact, joined to source bundles, producer, source commit, catalogue row/custom family, references and hashes. Include nested files, inline/subdirectory figures, ZIP members and redirect routes. Save current live HTTP/hash evidence before modifications.
2. Build the unified learning landing and explicit archive index from that registry. Remove bare/superseded report cards from primary navigation and move their reader-facing role to a lesson or archive entry. Keep a single consistent navigation between learning material, examples and evidence.
3. Preserve byte-identical evidence at existing immutable URLs and in version control. Do not rewrite historical `index.html` or ZIPs to add lessons, new styles, redirects or changed claims. Add new versioned lesson/companion routes and link to original evidence. Existing stable, non-evidence navigation aliases may redirect; any proposed replacement at an immutable evidence URL needs a documented contract exception and migration/retrieval policy first.
4. Delete only generated duplicate presentation output whose route is neither referenced nor an immutable evidence artifact. Stop staging obsolete presentation wrappers; do not remove their underlying saved records. Historical unregistered evidence can remain in Git without being listed in the learner navigation. User-authored research, failed runs and private historical archives are not disposable build output.
5. Verify final artifact routes, all learning/archive links, figure references, offline ZIP contents and exact hashes for retained evidence. Compare final navigation to the registry so augmentation cannot restore retired cards. Visually inspect representative pages and fetch deployed routes/downloads before marking publication complete.

These are constraints of [published algorithm results](../architecture/published-algorithm-results.md), especially its artifact/publication and final regeneration guidance: immutable destinations, raw failures retained, allowlisted reviewed files, independently replaceable measurement/rendering/publication, and actual deployed URL/hash checks. [legacy-publications.json](../../reports/algorithm-results/legacy-publications.json) pins LP/convex bytes, while `site.py` enforces that pinned sources match the staged legacy inventory. Removing catalogue entries without updating the model of archive retention can therefore violate validation as well as break links.

## Proposed scoped follow-up issues

These are issue scopes, not claims that live tickets are already actionable. Follow [live issue/dependency discovery](../agents/issue-tracker.md) before opening or claiming implementation work.

- **Complete publication inventory and retirement policy.** Produce the final-artifact route registry, classify all learner-visible reports with the three fields above, and approve the exact unlist/archive/delete/redirect matrix. Initial candidate set: the 11 live bare report routes listed above, plus plot-only and duplicate/superseded routes discovered by content review. No benchmark execution is needed.
- **Unify learning entry, gallery and evidence archive.** Consume the registry in root landing, book navigation, gallery, custom staging and augmentation; enforce one primary learning route with consistent links and explicit archive access. Preserve evidence bytes and offline downloads. Verify final Pages artifact and deployed URLs.
- **Port saved illustrative examples into teaching modules.** Reuse the analytic/saved-data geometry/control examples with inputs, assumptions, intermediate sets, outputs and failure explanations. Track timing-only examples as such. Acceptance requires an explicit per-module coverage matrix, not “26 families have links”.
- **Lotka–Volterra, Earth-orbit and fuel closed-loop modules.** Use the other planning investigation to define the supported single-player plant/control profiles, controller replay and exhaustive module coverage. Existing saved report illustrations are inputs to these modules, not evidence that the requested end-to-end teaching sequence already exists. Keep new numerical runs and benchmarks separately authorized and evidence-gated.

## Reproducing the local counts

Run from the source baseline; this reads files only and does not execute report producers:

```sh
python - <<'PY'
import collections, json, pathlib, re
root = pathlib.Path("reports/algorithm-results")
html = list(root.rglob("*.html"))
indexes = list(root.rglob("index.html"))
no_graphic = [p for p in indexes if not re.search(
    r"<(?:svg|canvas|img|object)\b", p.read_text(), re.I)]
catalog = json.loads((root / "catalog.json").read_text())["reports"]
visual = json.loads(pathlib.Path(
    "scripts/reports/visual-route-inventory.json").read_text())
print("html", len(html), "index", len(indexes), "no_graphic", len(no_graphic))
print("catalog", len(catalog), "kinds", len({r["report_kind"] for r in catalog}))
print("sources", len(visual["producers_and_routes"]),
      "frozen", len(visual["frozen_published_routes"]))
for p in sorted(no_graphic):
    print(p.relative_to(root))
PY
```

The live scan used the root HTML's `href="..."` attributes, deduplicated paths ending in `/index.html`, and excluded absolute HTTP paths, `/` paths and `../` paths. Each resulting URL was fetched with `urllib.request.urlopen` and the same case-insensitive tag regex, recording HTTP status, byte length and SHA-256. It did not crawl every hyperlink recursively or follow lesson pages named other than `index.html`. Subsequent inventory tooling should report a separate exhaustive local-link/image-reference analysis rather than silently changing this historical count definition.

The exact live-link scan can be rerun as follows. Its results are time-dependent: the recorded 120/11 result was observed on 2026-11-11 and is not a permanent assertion about later deployments.

```sh
python - <<'PY'
import concurrent.futures, hashlib, re, urllib.request
base = "https://butahlecoq.github.io/controlled-systems-lab/"
root_bytes = urllib.request.urlopen(base, timeout=20).read()
root = root_bytes.decode("utf-8")
paths = sorted({p for p in re.findall(r'href="([^"]+)"', root)
                if p.endswith("/index.html")
                and not p.startswith(("http", "../", "/"))})
def fetch(path):
    try:
        with urllib.request.urlopen(base + path, timeout=20) as response:
            body = response.read()
            graphic = bool(re.search(rb"<(?:svg|canvas|img|object)\b", body, re.I))
            return (path, response.status, len(body),
                    hashlib.sha256(body).hexdigest(), graphic)
    except Exception as error:
        return (path, str(error))
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
    rows = list(pool.map(fetch, paths))
print("root_sha256", hashlib.sha256(root_bytes).hexdigest())
print("fetched", len(rows), "http200", sum(r[1] == 200 for r in rows),
      "no_graphic", sum(len(r) == 5 and not r[4] for r in rows))
for row in rows:
    if len(row) != 5 or not row[4]:
        print(*row)
PY
```

Both snippets are lexical filters: comments containing graphic-looking tags can produce false positives, CSS background images and embedded external documents can be missed, and a timing image counts as a graphic without establishing an educational explanation. Content review remains required before retirement decisions.
