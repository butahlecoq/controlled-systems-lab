# Issue 942 module composition catalogue

## Definition of done

The native catalogue command emits a deterministic machine-readable inventory of the four module groups and every finite candidate graph. It marks each graph admitted, incompatible, implementation_missing, backend_unavailable, or excluded, with an affected tuple and first unmet requirement when admission fails. It canonicalizes inactive slots as `not_used`. Every admitted row is checked through the compiled provider's concrete `prepare` path, and the command exits nonzero if the inventory is incomplete or a provider selection resolves to a different module. Behavioral checks catch an omitted admitted row, wrong dimension for QuickHull2D, an optimizer presented as a vertex hull LP, and hidden backend substitution.

## Scope and grounding

This is one cross-cutting catalogue and native admission tool, not a benchmark runner. The four groups include real registrations and public functions, with public functions named as functions rather than assigned invented registry IDs. Current fixed-plan support, feedback routes, controller semantics, assurance, dimensions, build requirements, operations, limitations, and specific acados exclusion remain explicit. Candidate coverage is finite and versioned. The research audit lists ten registered hull reducers plus public geometric methods; validation is focused on small concrete requests and does not run scientific benchmarks.

Live issue 942 is open and assigned to `butahlecoq`; its blocked-by dependency list and open PR search are empty. The worktree is isolated at `feat/module-composition-catalogue-942`. No changes to immutable report bundles or other worktrees are in scope.

## Data shape

`ModuleRecord` describes one actual registry registration or named public function. It records stable identity and version when registered, build condition, group and role, input/output representation, dimension limits, model/action/objective scope, required operations, assurance, set relation, numerical limits, and source evidence. `CandidateGraph` names the active modules and finite request profile. Inactive roles are `not_used`. Canonical graph identity is computed from the active modules and request profile. `AdmissionRow` records the graph, one of the five required statuses, actual provider identities, resolved preparation result, and first unmet requirement.

## Candidate approaches

1. A checked-in JSON inventory plus a scripting-only Cartesian expander is easy to inspect, but it can drift from compiled registrations and cannot prove concrete provider admission.
2. A native executable with an explicit source-owned inventory, a domain-specific candidate generator, compiled providers, and concrete prepare calls keeps the finite catalogue reviewable and resolves admissions through real provider code. It requires more native wiring but gives the required evidence.

Choose the second approach. Use JSON as the command output, not as the authority for provider availability. Do not pretend every point in continuous parameter spaces is finite coverage. Provide deterministic rows for missing adapters and excluded modules as well as admitted modules.

## Phases

1. Ground: finish live issue and dependency checks, read delivery guidance and research contract, map provider registration, build-option, and native test ownership.
2. Sketch: define the candidate and admission records, candidate canonicalization, source inventory ownership, and the smallest concrete request probes for each provider role.
3. Probe the geometry/vertex-provider slice: register the audited reducers and LP providers, resolve each through concrete prepared requests, and check requested/actual identity and QuickHull2D dimension rejection.
4. Probe the representation/controller slice separately: record actual fixed-plan functions, strategy providers, controller formulations, and operation dependencies, with missing adapters and unavailable external backends explicitly classified.
5. Build the candidate resolver and coverage verifier: add behavior assertions for canonical inactivity, exhaustive row coverage, requested/actual provider identity, and optimizer/hull role separation.
6. Add the reusable JSON CLI output and source/contract documentation. Keep build conditions and scientific limits visible in every relevant record.
7. Verify focused native targets and the CLI against the real compiled artifact, inspect output and coverage, then run relevant tests. No benchmark is authorized or required.
8. Review the diff, record consumer/package impact, commit, push, and open a PR. Keep issue 942 open pending root's independent reviews and merge authorization.

## Decisions

The catalogue is a native tool because static data alone cannot resolve providers. Candidate classification and compiled availability/admission receipts are separate fields. Registry-based candidate resolution is a reusable public library seam for a subsequent runner, not a CLI-only probe. Current unavailable modules receive candidate rows and reasons rather than fabricated capabilities. Orbit and synthetic LV/fuel scope is reported from the research audit; issue 942 does not define new physical experiments. Existing acados prohibition remains active. The required design exploration used two source-grounded alternatives. Model-panel spawning is omitted because the coordinator explicitly prohibited agents from spawning.

## Risks and limits

Provider registries are assembled by owning modules rather than a single application-wide registrar. The CLI therefore must identify its source-owned registry builders and avoid claiming all build profiles unless it compiles and probes them. Some algorithms are public functions rather than provider registrations. They need explicit function identity and direct contract checks. A missing adapter is `implementation_missing`, while a compiled-out dependency is `backend_unavailable`.

## Todo

- [x] Read the Principles section of the poteto-mode skill.
- [x] Phase A: Frame.
- [x] Phase B: Design the workflow.
- [x] Phase C: Run the first native component loop (geometry/vertex provider slice).
- [x] Phase D: Keep the audit trail and component checkpoint PR.
- [x] Phase E: Verify, expand the complete graph universe, and hand back.
- [ ] Ground actual compiled inventory and choose concrete test requests.
- [x] Add and verify geometry/vertex provider probes.
- [x] Add native finite provider/controller probe output and source-grounded four-group inventory.
- [x] Add StrategyRegistry candidate/re-prepare seam with source-owned active configuration slots.
- [x] Document catalogue semantics, current limits, reproduction command, and delivery impact.
- [x] Run focused test suite and inspect native JSON output (5 focused tests passed).
- [x] Expand native finite candidate rows to representation, controller, and supporting-operation profiles; enumerate priority-tie Phase-I and explicit backend-unavailable cases.
- [x] Add/verify full candidate coverage against the independent four-group universe.
- [x] Install this branch and run hull/registry/strategy clients from exported package targets without source include overrides.
- [x] Commit, push, and open draft PR #952 without merging or closing issue 942.
- [ ] Send the final exact-head evidence to root for independent review; keep PR #952 draft and issue 942 open until review authorization.

## Historical component checkpoint evidence

Focused command passed in `build/dev-clean`: `ctest --test-dir build/dev-clean --output-on-failure -R '^(module_composition_inventory_source_check|module_composition_catalogue_cli|composition_catalogue_tests|registry_tests|application_comparison_integration_tests)$'`. The native CLI emitted 20 admitted reducer/LP tuples (ten reducers crossed with HiGHS and Bland Phase I), and one admitted/re-prepared TS01 analytic strategy profile. The square fixture retained indices 0–3 and removed the strict interior point. `lp-membership` produced completed calls through the outer registered runner. Reducer-specific metrics separately report captured child-solver work where exposed. Strategy A and B were concretely prepared/re-prepared in the integration test.

The inventory source check validated 46 records, ten registered hull IDs, and three source-faithful BTULSHOR public symbols against the pinned repository base plus cited research audit. The full all-target compile completed in `build/dev-clean`. CTest passed the five focused catalogue/registry/strategy checks. The branch was installed to `build/issue942-install`; three external consumer programs compiled against its exported targets with no source include override, and the hull execution receipt, registry client, and TS01 strategy re-prepare client passed.

This was a partial component checkpoint. The following full-catalogue section records the later expansion and verification. No active build/test process remains from this historical checkpoint.

## Full catalogue expansion evidence

The native CLI now includes the concrete priority-tie Phase-I LP profile, backend-unavailable rows conditional on build flags, Qhull conversion, box outer approximation, terminal HiGHS optimization, generator affine-image and V-conversion operations, QuickHull2D dimensional rejection, and source-faithful BTULSHOR runs. `scripts/catalogue/check_output.py` independently checks the ten reducer IDs, provider identities, square result, LP invocation evidence, role separation, generator outputs and dimensions.

The source-backed controller candidate universe contains 3,318 unique task/action/module tuples across nine public or registered routes. It expands Strategy A over ten reducers and its three LP-provider roles, Strategy B over its three configured LP providers, nominal_forward over its reducer and nested LP/converter dependencies, and the finite nominal route over five representations. Forty-five additional predecessor/recovery tuples cross five representation routes with the three actual terminal LP providers. A further 24 full-task group-one rows cover QuickHull2D and actual source-faithful MODIF/KPABEP/REACH symbols, including the coupled KPABEP/MODIF dependencies. Twelve task-scoped rows cover the two public polyhedral operations that no delivered controller registration consumes. The native CLI calls `TerminalOptimizer::solve` with actual HiGHS LP and convex providers on the TS01 terminal slice. Two external MPC11 prepares are admitted only after `load_task` and `validate_source_binding`; a negative checker mutates task model, objective, and scenario source and verifies rejection. The exact finite catalogue is independently checked by `scripts/catalogue/check_full_catalogue.py`.

Latest verification passed the full wrapper/checker (`3,318 controller tuples`, `45 predecessor/representation/terminal-LP tuples`, 24 full-task reference tuples, two source-bound external prepares), the native CLI checker, Python byte compilation, and the five focused CTest tests. Strategy A/B and nominal-forward complete controller graphs remain `implementation_missing` because no source-bound nonlinear/discrete-affine model adapter is delivered; their active dependency axes remain present. QuickHull2D full-task rows are `incompatible` for the four-state tasks and `implementation_missing` for the two-state task because it lacks a HullReducerPort adapter. The LV parallelotope predecessor tuple is `incompatible` at the documented four-state dimension. No episode, benchmark, or NLP solve was run. Historical component checkpoint evidence above remains as recorded; the current expanded native CLI has also been rebuilt in `build/dev-clean`.
