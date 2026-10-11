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
