# HTML-01: Publish reproducible algorithm result and performance reports

GitHub: [#123](https://github.com/butahlecoq/controlled-systems-lab/issues/123).

## Purpose and scope

Owner requirement (2026-10-12): when an implemented algorithm can produce results, create an English HTML artifact with numerical results and performance figures, publish it at an accessible URL, and link it for owner review. Start with the reference LP adapter's supported analytic cases; do not wait for the complete two-strategy application. Keep later comparison/plot modules independently replaceable.

## Acceptance criteria

- [ ] Generate a standalone HTML report from saved versioned result/measurement records, including algorithm/backend/code identity, scenario/input hashes, objective/residual/status/evidence, supported assumptions and numerical/reference comparison. A point is not a complete optimizer family; historical values remain separate from reproduced values.
- [ ] Include actual release-build performance numbers with units and timed-work definitions, raw repetitions, median/range, failure counts, environment/compiler/build/scalar/tolerance/seed metadata, requested/actual workers/native threads, cold/warm and workspace-reuse policy. Show setup/solve/verification/export phases where measured, and mark unavailable submodule metrics explicitly. Do not treat CTest duration as algorithm runtime or overlapping parallel work as additive latency.
- [ ] For comparative performance claims, alternate at least five tuned repetitions per side and keep a separate limiter profile; identify inconclusive results honestly. Preserve failed/unsupported/cancelled runs and available evidence. Initial single-adapter reports need no invented competitor or speedup.
- [ ] Publish a navigable GitHub Pages index and immutable versioned report URL, with a repository fallback download plus raw JSON/CSV and figure assets. Link the actual accessible report and source commit from the algorithm PR/issue. No legacy private source files are redistributed.
- [ ] First report executes the real registered reference LP adapter on independent analytic fixtures and verifies expected objective/residual/status before accepting timings. Document regeneration command; validate report/data consistency, missing/error states and deployment links; visually inspect the rendered HTML.
- [ ] Keep measurement, saved-record schema, HTML rendering and publication outside solver logic. Define an adapter path for future OBS-04/OBS-05/VIZ artifacts without introducing a second authoritative scientific result schema. Update the master specification and developer workflow so each subsequent executable algorithm delivery produces or explicitly updates its published report.

## Dependencies

The first actual LP report requires OPT-03 #21. This does not change any original backlog dependencies, nor make future comparison/visualization tickets prerequisites for the first report. OBS-04 #83, OBS-05 #86 and VIZ-03 #96 supply later richer data/export modules.

## Delivery and review

Use an isolated worktree and one owner for GitHub publication. Return implementation, measurement commands/raw records, limits, rendered artifact and actual public URL. Independent review covers mathematical evidence labels, benchmark validity, schema/module boundaries and reproducible publication. Hosted CI or a source link alone is not evidence that the HTML URL renders the intended report. GitHub Pages setup is authorized by the owner; publish after the artifact is concrete and reviewed.