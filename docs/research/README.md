# Research dossier

Assessment date: 2026-10-11. Rolling literature window: 2021-10-11 through 2026-10-11. Status: initial investigation.

## Reading order

1. [Source map](source-map.md): what was supplied and how the documents relate.
2. [Scientific foundations](scientific-foundations.md): the reusable mathematics.
3. [Baselines](baselines.md) and [legacy audit](legacy-audit.md): experimental evidence and reproducibility gaps.
4. [Recent research](recent-research.md) and [bibliography](bibliography.md): what to evaluate next.
5. [Modular algorithms and optimal families](../architecture/modular-algorithms-and-solution-sets.md), [set representation review](../architecture/set-representations-and-ellipsoidal-toolbox.md), [architecture](../architecture/initial-architecture.md) and [performance](../architecture/performance-and-language.md): architecture before implementation.
6. [Glossary](glossary.md) and [open questions](open-questions.md): shared vocabulary and decisions.

## Evidence conventions

| Label | Meaning |
|---|---|
| Local source | Read from a supplied article, report, listing, or registration abstract; cited by L01–L31 and PDF page where applicable |
| Reported experiment | A number in a supplied publication; execution was not independently repeated |
| Executed characterization | A small isolated check of actual archived functions; input, limitations, and output are recorded |
| External primary source | Author paper, institutional publication record, or official project documentation; indexed in the bibliography |
| Design proposal | A recommended abstraction or experiment; not a theorem or measured improvement |
| Open issue | An ambiguity requiring a source, proof audit, or owner clarification |

Raw text is evidence for navigation, not an authoritative reconstruction of typeset mathematics. When extraction and the original disagree, the original wins. PDF page numbers mean one-based file pages, not necessarily printed journal pages.

## Coverage and limits

The inventory covers every file originally present in the workspace. Papers and the report were read for model structure, assumptions, algorithms, and numerical experiments; source listings were inspected. Selected key formulas/tables were checked in rendered PDF pages. This is not a line-by-line proof verification or a systematic exhaustive literature review.

Literature selection focused on reachability, robust controllable sets, robust/adaptive MPC, data-driven uncertainty, and parallel optimization. Abstract-level reading is explicitly marked in the bibliography. Foundational software predating the window is included as an analogue, not counted as a new discovery.

Reproduction tooling is in [tools](tools/README.md). It performs extraction, isolated characterization and an independent small discrete baseline check. The English curated documents summarize the archive; the extraction files intentionally preserve original language.

## Follow-up proof notes

[Temporal coupling](temporal-coupling.md) distinguishes reserved cross-step constraints from unchanged first archival experiments. It includes the joint convexity derivation, an exact slew-limit memory lift, a recurrence counterexample and algorithm-specific limits.

[Reachability proof audit](reachability-proof-audit.md) and [adaptive-policy proof audit](adaptive-policy-proof-audit.md) publish the reviewed conditional proofs, counterexamples and source-policy distinctions for Q04/Q05. The [reachability source correspondence](reachability-source-correspondence.md) compares L05's Table 1 claims with the archived L26/W12 listing without treating that listing as the historical experiment generator. The [provenance record](proof-audit-provenance.json) preserves the proof reports' correction/version chains; both original scientific issues remain open.

The [L05 saved-figure audit](l05-saved-figure-audit.md) recovers terminal polygons whose counts and areas match all three reported Example 1 rows, then checks exact containment of the stored binary64 hulls. It does not certify nonlinear reachability or identify the historical generator.

The [L05 linear zonotope reconstruction](l05-linear-zonotope-reconstruction.md) independently reconstructs the candidate's 60-stage affine-control reachable polygons and matches all saved general-linear stages to floating-point precision. Exact checks of saved polygons show modified-in-general inclusion at every plotted stage, while the linear and nonlinear plotted hulls cross at stages 2–54; historical generator identity and nonlinear enclosure remain open.

The [L05 four-state candidate reconstruction](l05-example2-candidate-reconstruction.md) independently enumerates the archived seven-transition, two-control model. Its full linear and nonlinear corner-history hulls match the printed Example 2 general and nonlinear count/volume rows and three saved 3D projections; the modified 4D row and historical generator remain unresolved.

The [issue #5 feedback contract follow-up](feedback-contract-followup.md) turns the reviewed policy distinctions into a bounded robust predecessor and evidence handoff without claiming an implemented feedback solver.

The [exact finite policy-class reference](finite-policy-class-reference.md) independently enumerates an authored two-step counterexample's fixed plans, executed replanning selector and globally causal value. Its three-point disturbance catalogue checks decision order but does not certify L13's continuous model or historical program.

The [GEO-02 floating-model audit](geo02-floating-model-audit.md) separates exact hull preservation for stored binary64 candidates from error relative to an intended real-valued affine image or Minkowski sum. It proves a conditional finite-V error bound and records the H-to-V coverage proof still needed for issue #40.

## Selected first benchmark

[B04 restoration](b04-restoration.md) records the owner-selected nominal scenario, its versioned historical manifest and an exact terminal-invariant audit. Source gaps and the model/result inconsistency remain explicit before implementation comparisons.

[B04 parameter cross-check](b04-parameter-crosswalk.md) evaluates the printed nonlinear flow law with exact rational arithmetic and distinguishes it from the displayed linear input data and the separate saved-run kernel.

## Larger local archive

The [targeted follow-up search](archive-followup.md) records recovered MATLAB/Pascal algorithms, B04 tables, minimax adaptive run data and the local zonotope paper. Its selected-source register supplements the initial inventory.

The [Works source follow-up](works-followup.md) and [supplemental W01–W14 register](works-selected-sources.json) record additional Python variants, embedded helpers, a separate minimax configuration and historical nonlinear notebook observations. Static inspection recovered no new fuel result or exact B04 configuration; original source identities and open scientific gaps remain unchanged.

[B04 numerical tables](b04-tables.md) transcribe the owner-identified table document and record the provisional [-1,1] control-interval recollection.

[B04 saved witnesses and replay](b04-saved-witnesses.md) curates three independently checked nominal/nonlinear pairs as a distinct evidence variant, with [machine-readable facts](evidence/b04-saved-witnesses.json) and an explicit-private-source reference checker. A [focused FIG/MAT workspace inspection](b04-saved-witnesses.md#focused-fig-workspace-inspection-2026-10-17) narrows the search for missing U rows without recovering the canonical T16 configuration. The report preserves the frozen objective mismatch and historical 99.99-second endpoint. The historical scenario remains non-executable.

[Publication-to-source version matrix](publication-source-matrix.md) compares hash-identified B04, B08 and B09 publications with nearby archived scripts, notebooks and saved runs. It records field-level matches, incompatible versions and missing canonical inputs for issues #1 and #2.

[B08 displayed-data exact audit](b08-displayed-exact-audit.md) proves the finite minimax result and three-way tie for L04's printed rational linear data. It does not reproduce the article's unrounded project or nonlinear trajectory; issue #6 stays open.

The [reviewed temporal-lift source audit](temporal-lift-source-audit.md) curates the complete-history proof, L01/L11 assumption crosswalk, corrected constrained recovery, saved-code limitations and unchanged first-manifest evidence for original #9. It distinguishes unique physical endpoints from lifted memory fibres and records the scoped independent review chain in [proof provenance](proof-audit-provenance.json). EXT-03 remains a separate implementation task.
