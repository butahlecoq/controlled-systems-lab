# REVIEW-01 implementation audit

## Scope and evidence

This is an implementation audit of foundations, model, problem publication, and public execution ports at main commit `389f542d658201b93355d579d7df95271fc9969d`. It addresses the REVIEW-01 plan and master-design requirements MOD-01..09, ALG-07, RUN-01/02. Claims are limited to code and tests at that snapshot. No future-class support or scalability result is inferred from design documents alone.

The implementation substitution exercise is supplied separately by PR #416, currently at `231357b99ed618286e983d09789b710258efaca4`. That test change is evidence about the added fixture only and does not alter the audited production snapshot. At the time this report was drafted, hosted CI for the fixed snapshot (`39033066079`) and PR #416 (`39033424707`, `39033428456`) was still running; final disposition waits for terminal results.

## Dependency and contract boundaries

- `src/model/Module.cmake` links `CSL::model` publicly only to `CSL::numeric`. `src/problem/Module.cmake` layers `CSL::problem` over model and sets, resolved core over problem/objectives, and resolved publication over registry. This graph keeps model/problem descriptions independent of solver implementations, fuel physics, and plotting modules.
- `include/csl/model/contracts.hpp` separates affine dynamics from observation maps/schedules and timing. `include/csl/problem/contracts.hpp` composes control/state domains, initial data, external inputs, temporal constraints, objective, and information pattern as separate values. Backend registries are reached at strategy preparation rather than included into model contracts.
- The native ownership guidance in `docs/testing/native-ownership.md` records public-header and installed-client checks. The inspected model/problem public contracts use product-owned values and immutable snapshots; backend and third-party implementation types do not appear in these public model/problem interfaces.
- Observation snapshot validation checks event timing, causality, and absent-input feedthrough (`src/model/linear_system.cpp`, `freeze_channel` and timing helpers). Supplied discrete transitions are used directly; continuous-time publication returns explicit `unsupported` from `src/problem/resolved.cpp` and is not silently discretized.

## Generality and solver restrictions

- Singular affine dynamics are representable. The contract test `tests/contract/registry/registry_tests.cpp:1106` exercises a singular stage, confirms forward feasibility, and confirms inverse-only admission rejects the unsupported assumption. This is a deliberate boundary between mathematical model and algorithm capability.
- Continuous control-set values distinguish singleton, universal, empty, and represented sets. Finite/mixed domains and coupled temporal constraints remain capability-limited; request validation reports unsupported cases instead of converting them to a different mathematical quantifier or claiming infeasibility. Continuous-time input is explicitly unsupported in the current publication path.
- `src/problem/resolved.cpp` distinguishes malformed input (`invalid_input`) from unsupported uncertainty structure or continuous time (`unsupported`). Registry/strategy tests cover unsupported versus infeasible/feasible outcomes; rejection occurs before workspace creation in the tested paths.
- The first-release assumptions remain narrow: known initial point and nominal open-loop strategy are supported; initial-set/policy semantics are not inferred as existential or robust defaults. Evidence from this audit must not be generalized to arbitrary uncertain policies, continuous-time models, or finite/mixed solver support.

## Substitution exercise

At the audited snapshot, the endpoint-a/endpoint-b unit test registered the same `FixedControl` class for both IDs and used a trivial one-stage scalar case. Independent reviewers correctly found this insufficient for REVIEW-01's second-provider acceptance. PR #416 adds a distinct bound-reading provider and runs a nonfuel affine scenario (`A=2`, `B=1`, offset `1`, `x0=2`, singleton `u=3`) through resolve, strategy preparation, workspace creation, and witness evaluation. The assertions check selected provider provenance, retained mathematical identity, `x: 2 -> 8`, objective `8`, and no complete-family claim. Both independent rechecks at `231357b99ed618286e983d09789b710258efaca4` found no remaining acceptance issue. The providers are test fixtures and the fixture LP is fixed; this demonstrates public strategy plumbing substitution, not production solver equivalence or automatic derivation of an LP formulation from arbitrary affine scenarios.

The exercise requires no production-core edits when adding another in-process provider: register an implementation at the LP port and select it through strategy configuration. This is a narrow demonstration, not proof that every strategy or backend supports every representation. No closed production switch was identified in the inspected core/model/problem boundaries; profile-specific restrictions are explicit admission checks with diagnostics.

## Ownership, lifetime, caches, exceptions, and failures

- Numeric matrix/vector snapshots own immutable backing storage (`include/csl/numeric/data.hpp`); resolved problems own frozen model, domain, objective, and identity values. Borrowed descriptors are synchronous views whose lifetime is tied to an owning view. Tests in `docs/testing/native-ownership.md` and associated public clients exercise retained ownership, producer mutation, empty dimensions, and installed-header use.
- Zero-dimensional ports have explicit contracts and tests: empty control/external inputs remain valid and are not conflated with absent/universal/empty sets. No raw coefficient access is needed for empty dimensions in numeric operations.
- No shared mutable cache was found in the inspected model/problem/public-port path. Snapshot-local derived data is owned by immutable values; backend mutable solve state is workspace-local. The report does not claim all downstream adapters are free of private caches; their ownership contracts are documented separately.
- Exceptions at allocation/container boundaries propagate as standard C++ exceptions, while expected validation/capability outcomes use typed results/diagnostics. `docs/contracts/linear-model.md`, `resolved-problems.md`, and backend contracts document this split. This means allocation failure is not translated into mathematical infeasibility.
- `ResourcePolicy.memory_bytes` is described in `include/csl/execution/contracts.hpp:12` as admission/accounting only, not enforced by this revision. Treating it as a hard runtime cap would be incorrect. This is a known limitation for resource guarantees, not evidence of memory-bound scalability.

## Modularity, scalability, and recommendations

Modularity is strong at the inspected seams: immutable model/problem values, separately represented observations and information, solver capability admission, and private backend workspaces. Diagnostics preserve the distinction between invalid, unsupported, and mathematical outcomes. Provider substitution at the public port is now evidenced by the PR #416 fixture.

Scalability is unmeasured by this audit. The representation is stage-indexed and immutable, but neither this audit nor the substitution fixture measures memory growth, solve time, output-family growth, or concurrent throughput. The master design's RUN-04 requirement calls for declared dimensions, representation size, memory, backend versions, and output scope before making such claims. The unenforced memory budget is especially relevant to future resource guarantees.

Recommendations: retain immutable public value boundaries; keep capability restrictions explicit and diagnostic; keep cache and workspace ownership local to the adapter that owns the relevant state; and add measured resource evidence before describing the architecture as scalable. No blocking production interface change was identified in this review slice. The medium substitution evidence gap is addressed by PR #416, subject to its CI.

## Independent review record and disposition

- Fixed implementation snapshot: `389f542d658201b93355d579d7df95271fc9969d`.
- Spec audit reviewer: `/root/review01_spec_audit`; confirmed dependency separation and explicit semantics, identified the inadequate same-provider substitution test. That test gap is addressed by PR #416 and was independently rechecked at `231357b` with no spec finding.
- Standards audit reviewer: `/root/review01_standards_audit`; no confirmed standards defect in the assigned foundations/model/problem/public-port slice; identified the same substitution evidence gap and asked that cache, exception, and resource-limit claims be precisely scoped.
- PR #416 spec and standards reviewers: `/root/review_substitution_spec` and `/root/review_substitution_standards`; at exact head `231357b99ed618286e983d09789b710258efaca4`, both cleared the change. The standards reviewer confirmed the finite singleton bound guard resolved its only robustness finding.
- Reproduction: run the `validator_tests` target's test case named `nonfuel affine problem substitutes independent LP providers through the public strategy path` on PR #416. Hosted CI is the authoritative compiler/test gate because CMake/compiler tooling is unavailable in the local environment.
- Severity/disposition: one medium evidence gap in the original tests; fixed by PR #416. No blocking production API finding. CI and final independent report review remain required before closing issue #59.
