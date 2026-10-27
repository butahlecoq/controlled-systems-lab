# Issue #727 method-selection design

## Problem

The scenario loader accepts an ordered `run.methods` list with optional versions, while the application only executes a fixed reach-back/strategy-B pair. The application owns important shared behavior: family admission, admission before workspace creation, complete-family witness selection, independent verification against the original problem, and run-record encoding. Method-list support must use that policy while preserving the existing paired API and `ProblemId` semantics.

## Caller view

The CLI maps each scenario method to a strategy configuration and keeps the optional version beside it:

```cpp
SelectedMethods::make(std::move(methods)); // rejects an empty list
SelectedRunRequest request{problem, family, std::get<SelectedMethods>(...) };
auto prepared = prepare_selected_run(request, strategies);
auto result = run_selected(std::get<PreparedSelection>(prepared), selectors,
    selector, witnesses, selector_requirements, context, membership);
```

Existing pair callers keep `ComparisonRequest`, `prepare_comparison`, and `run_comparison`. Those functions become adapters over the selected-run engine and retain their exact two-slot result and ordered-pair guard.

## Shape

`SelectedMethod` contains a `StrategyConfiguration` and an optional requested strategy version. The configuration type itself remains unchanged; `prepare_selected_run` passes the optional version to `StrategyRegistry::prepare`. A `SelectedMethods` value owns an ordered vector and can only be constructed through a checked factory, so an empty selection cannot reach preparation.

`PreparedSelection` owns the resolved problem and family plus one `PreparedStrategy` per input method. Preparation validates the shared family/profile/representation constraints and attempts all requested admissions, retaining each rejection with its input index. It creates no workspace unless all admissions succeed. Only then may `run_selected` create every workspace and execute in authored order.

A single private execution loop owns result projection, complete-family selection, and lineage-bound witness verification against the original `ResolvedProblem`. The existing pair API delegates to this loop and adapts its two results back to the existing array-shaped `ComparisonExecution`. This keeps pair cardinality explicit for old callers while leaving one implementation of execution policy.

The CLI reports method errors with `/run/methods/<index>/id` or `/run/methods/<index>/version`. It persists one `csl.run-statistics/7` record per method with resolved strategy/backend versions and effective run settings. Existing output naming for the pair remains unchanged; method-list outputs use deterministic names derived from the method ID plus input index to handle duplicates. Existing transactional no-overwrite publication remains in force. Backend requests not supported by the CLI receive field-specific unsupported diagnostics. Method selection and execution settings remain outside `ProblemId`; changes to mathematical data continue to change it.

## Synthesis decision

Candidate B is the base: selected methods use one canonical application admission and execution path. Candidate A contributed its strongest constraint: preserve the current public pair API and its compile-time two-slot result. The pair functions remain thin semantic adapters over the selected-run engine, not a second execution implementation. Candidate A's unresolved strategy-version representation was replaced with Candidate B's explicit optional version alongside `StrategyConfiguration`, matching the current registry request shape. The design rejects Candidate B's unnecessary source migration for existing pair callers and rejects a wholly separate batch engine because two orchestration paths invite policy drift.

The cross-judge scored Candidate A 10/12 and Candidate B 11/12. It recommended B for one canonical execution path, while identifying A's fixed-pair compatibility as the strongest graft. Both designs require the empty-list invariant and version flow to be explicit; this synthesis encodes both.

## Tradeoffs accepted

- We accept a small selected-run API plus compatibility adapters in exchange for one owner of admission, selection, and verification behavior.
- We accept indexed runtime rejection aggregation for arbitrary method IDs in exchange for useful diagnostics and no workspace creation on partial admission.
- We accept sequential execution in authored order for this initial implementation; a method list does not imply parallel execution.
- We accept deterministic per-entry filenames for method-list artifacts so duplicate methods remain distinct and publication stays transactional.

## Alternatives considered

- Add an independent method-batch engine beside the pair engine. Rejected because it would create two orchestration paths and allow selection or verification policy to diverge.
- Replace the paired API outright with a vector-only API. Rejected because it forces unnecessary source migration and weakens the existing compile-time pair result for current callers.
- Run methods directly from the CLI through `StrategyRegistry`. Rejected because it would move family admission, workspace ordering, witness verification, and artifact behavior into command code.

## Delivery impact

This adds an application-facing API and changes the scenario executable behavior. The PR will follow `docs/agents/delivery.md`, document source/package impact, and record **no release needed** for an ordinary merge because no published package workflow is attached to this repository change. The project version alone is not evidence of a published package.

## Next implementation step

Add the selected-method domain types and shared application execution path, then route both scenario selections through it while retaining the existing pair API as an adapter.
