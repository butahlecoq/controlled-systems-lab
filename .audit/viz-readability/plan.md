# VIZ-06 report plot readability plan

## Definition of done

- [ ] A versioned shared static plotting policy gives numeric axes legible ticks, distinct formatted labels, aligned major grids, explicit aspect/scaling, and accessible text alternatives.
- [ ] Fuel-related visual tasks include a labeled 2D projection of the saved 4D model/set when supported, plus stage-aligned history or other relevant saved visual evidence.
- [ ] New report and gallery figures use that policy or an inventoried, justified diagram exception. Tests fail when an emitted plot omits required numerical or textual structure.
- [ ] A new B06 companion view renders the saved flow and stock projection records with before/after figures. It adds a representative trajectory/stage view and timing view from saved records. It preserves the source commit, exact values, method identity, evidence labels, targets/bounds, and the #668 erratum link.
- [ ] A machine-readable inventory covers every discovered report and gallery plot producer and publication route. Each route is marked adopted, justified exception, or deferred with its follow-up issue. Original reports, manifests, checksums, archives, and URLs remain byte-identical.
- [ ] Saved-value tables and descriptions expose exact values. Standalone SVG/PNG and offline HTML work without a CDN. Desktop, narrow viewport, zoom, and print views have been visually inspected.
- [ ] The reporting test suite validates numeric labels, narrow ranges, offsets, small/large/negative values, degenerate ranges, accessible descriptions, local assets, and immutable publication behavior. The main-only Pages deployment passes and live companion assets return HTTP 200.
- [ ] No solver, geometry operation, numerical experiment, benchmark, or new runtime dependency is used.

## Scope estimate and constraints

The initial source scan found 192 Python files under `scripts/reports`, 62 files containing an SVG or savefig signal, and 44 with SVG literals. The deterministic inventory scans both `scripts/reports/**/*.py` and `benchmarks/reporting/**/*.py`; it records 82 source candidates, 53 frozen report routes with figures, and the gallery route. Of the source candidates, 53 family-specific renderers remain deferred and now link to scoped follow-ups #684–#687 (13 approximation/extension, 12 geometry/optimization, 17 control/witness, and 11 historical/benchmark candidates). Frozen report routes are explicit immutable-evidence exceptions with additive-companion treatment. Row-by-row role and disposition review remains open under #669. The first wave has a new B06 flow/stock projection companion, one trajectory/stage chart, one timing chart, accessible exact-value data, and a byte-identical old figure for comparison.

The task has high rigor because it changes publication presentation, can mislead readers about scientific data, and spans many producers. Saved records and manifests are immutable evidence. B06 remains affected by issue #668 and must link its correction/erratum. B04 is not canonical and must remain restoration-labelled. Frozen report bundles cannot be rewritten, but each route remains pending a readability review and a decision about an additive companion under #669.

## Phases

1. **Frame and baseline.** Read the live issue, delivery and publication policies. Capture the current B06 and representative plot sources, HTML dimensions, metadata, and browser-visible baseline before edits. Record source hashes and route responses.
2. **Inventory lever.** Build a deterministic audit tool that enumerates report/gallery producers, generated assets, publication registrations, and mutable versus frozen destinations. Store a route manifest; this slice verifies known B06 producers, the mutable gallery route, and frozen-route discovery. Full row-by-row role/disposition review remains open.
3. **Shared static plot policy.** Prototype the saved-data shape and tick/aspect formatting contract. Extend the existing pinned Matplotlib path only where appropriate. Preserve hand-authored SVG for simple diagrams under the same output checks. Add fixture-driven behavior tests before migrating callers.
4. **Representative migration.** Render new, versioned B06 flow/stock companions from saved geometry and source values. Migrate one trajectory/stage and one timing plot. Add raw-value tables, text descriptions, source/evidence notes, and responsive/offline HTML. Do not replace existing report bytes or routes.
5. **Remaining coverage and follow-ups.** Scoped issues #684–#687 now own the deferred family migration candidates. Classify every inventoried route, migrate safe current generators that share the selected adapter, and link companions from the mutable gallery/index.
6. **End-to-end verification.** Run focused and full reporting checks. Compare source hashes and original publication IDs before and after. Inspect screenshots at desktop, 320/375 px, browser zoom, print, SVG/PNG, and offline HTML. Deploy only through the existing main-only workflow; verify the new live routes and unchanged old URLs.
7. **Review and delivery.** Review the exact base/head against standards and #669 criteria. Record release/package impact, each inventory disposition, visual evidence, and follow-ups. Close #669 only when its stated done conditions are satisfied.

## Throughput checkpoint

- **Blocking first steps:** baseline publication/source inventory and plot-data boundary audit. These prove where the common policy can attach without changing evidence.
- **Independent workstreams:** initially none. The adapter, tests, B06 companions, and route inventory share output contracts and require one owner to keep labels and provenance aligned. Reassess after the inventory manifest is stable.
- **Shared mutable state:** this worktree owns the feature branch. The dirty main worktree and published report bundles are read-only inputs. Each new companion gets a new versioned path.
- **Smallest safe decomposition:** one owner, ordered by inventory tool, style/tests, representative companions, then route migration. That keeps rendering, saved-value tables, manifests, and gallery links on one reviewed head.

## Todo

- [x] Read the Principles section of the poteto-mode skill.
- [x] Capture the pre-change B06 and representative plot baselines.
- [x] Build the route inventory tool and validate known B06 producers, gallery route, and frozen-route discovery; full row-by-row disposition review remains open.
- [x] Define and test the shared saved-data plotting contract for Matplotlib control and timing plots.
- [x] Generate B06 flow/stock, trajectory and timing figures from saved records; inspect desktop, mobile, standalone SVG/PNG, offline HTML and print. Browser zoom remains to verify.
- [x] Open four scoped follow-up issues covering all 53 deferred source candidates; the route-by-route role/disposition audit remains open.
- [ ] Classify the full route inventory.
- [ ] Run reporting tests, visual QA, and unchanged-artifact checks.
- [ ] Merge, deploy, verify live routes, and update #669.
