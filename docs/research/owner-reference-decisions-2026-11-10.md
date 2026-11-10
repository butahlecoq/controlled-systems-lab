# Owner-selected working references

Date: 2026-11-10. Status: accepted by the repository owner in the blocker interview, including the final complete summary. These choices supersede historical-reproduction acceptance gates for issues [1](https://github.com/butahlecoq/controlled-systems-lab/issues/1), [2](https://github.com/butahlecoq/controlled-systems-lab/issues/2), [6](https://github.com/butahlecoq/controlled-systems-lab/issues/6), [8](https://github.com/butahlecoq/controlled-systems-lab/issues/8) and [10](https://github.com/butahlecoq/controlled-systems-lab/issues/10). They do not establish which source revision generated an old publication table.

## Acceptance and historical records

A complete, explicitly selected working model with independently checked results is sufficient. Unproved historical source-to-run correspondence remains documented but does not block implementation, comparisons or issue closure. Keep published values, private originals and immutable report bundles unchanged. Do not relabel a working reference as a historical reproduction.

This is an explicit owner scope decision, not a conclusion inferred from numerical agreement. Existing run authorization remains in force. Issue closure still requires the selected model, applicable checks, implementation and report deliverables; this note alone does not complete unfinished software.

## Selected models

| Case | Primary working reference | Other evidence and limits |
| --- | --- | --- |
| B04 | `B04-SOURCE-COMMENTED-X0-V1`: initial state `(1220.28265395983,119500,440.005764648976,45300)`, exact input slopes `(2208/110,0,-1152/110,0)`, sixteen controls in `[-1,1]`, and the full source-defined constraints and five-term objective. Exact minimum `30.89913603001161343…`. | `B04-SOURCE-ACTIVE-X0-V1`, minimum `31.12140945050040042…`, is a separate rounding-sensitivity case. Neither designation asserts the old generating revision. See the [complete models and proofs](b04-source-moment-reconstruction.md). |
| R29 | `R29-corrected-scalar-reference`: scalar `u(t)∈[-1,1]`, input image through the printed `B`, and the article's initial zonotope. | The owner accepts the explicit dimensional/center correction as a working model. The original four-component control data and `Ac2` expression remain transcribed in the [source audit](zonotope-paper-input-audit.md). This is a reachability example, not an unspecified terminal optimization problem. See the [exact reference](r29-corrected-scalar-reference.md). |
| L04 / B08 | Use the Euclidean terminal objective `sqrt((x1-1200)^2+x2^2+(x3-450)^2+x4^2)`. Existing displayed-data inputs retain their distinct identity. | The owner explicitly dropped `14.048` as a target or acceptance condition. Do not fit a criterion or inputs to recover it. The [exact displayed-data audit](b08-displayed-exact-audit.md) and [source-version trace](issue1-source-version-trace.md) retain their scopes. |
| L13 / B09 | Use `sqrt((x1-60)^2+x2^2+(x3-24)^2+x4^2+(x2-2.5*x4)^2)`. This is the `lambda=1` objective in `b09-a08-source-revision-reference-v1`. | Every deviation term is squared. The unsquared source reporting expression is not the adopted objective. `22.657` is not a reproduction target. The existing `lambda=0` comparison remains separate. See the [versioned source-reference inputs](../../benchmarks/scenarios/b09-a08-source-revision-reference.json) and [saved-criterion trace](l13-a10-saved-criterion-trace.md). |

The B04 source model has exact constrained global minima and complete 14-dimensional joint optimal control families, with all-stage state lifts. Its [live report](https://butahlecoq.github.io/controlled-systems-lab/b04-source-moments-11fb3cd7d83f868d3c3d/index.html) is already published and verified. Selecting it does not alter its saved figures, proof packet or immutable source anchor.

The R29 reference propagates the full affine factors through all seventeen stages. Its exact construction remains distinct from the historical timing and plot claims. The L04 and L13 working objective choices likewise do not promote archived candidate runs to publication-generating runs.

## Faithful legacy C++ modules

The owner requests extractable historical algorithms as separately selectable C++ modules for direct comparison. Preserve the operation order, entering and leaving pivot choices, phases, tolerances and status codes. Do not optimize the arithmetic or substitute a modern solver inside the source-faithful implementation. Technical storage and interface adaptation is permitted.

Recovered `BTULSHOR` procedure bodies provide a concrete source for this work: `REACH`, `KPABEP` and `MODIF`, source SHA-256 `06fa90d5977ab49174abbf866899000f511fad46eac4a1e72388bbe27090a442`. The [body-recovery record](btulshor-original-body-recovery.md) pins their source anchors. This is distinct from the paper-derived ITIS17 adaptations and does not establish that A06 is their original implementation.

Missing dependencies of the complete old project do not block an extractable module. Record numerical representation choices, source preconditions and every technical departure. Preserve raw legacy outputs and failure statuses; independent correctness checks must not silently repair the algorithm. Compare the faithful module with existing implementations on common inputs. Retain inconclusive or incorrect outcomes as observations rather than changing the source algorithm to pass the comparison.

Issue #2 remains implementation work until the modules and their applicable verification are delivered. Issue #6 retains the associated comparison and publication work. The owner has delegated the remaining technical implementation and review decisions, including use of implementation agents and independent mattpocock specification and standards reviews.

## Delivery impact

This decision record changes acceptance and reference selection only. It does not modify APIs, dependencies, installation, immutable manifests or executable algorithms, and needs no release. A later legacy-module change must record its own API, validation, numerical-report and package impact.
