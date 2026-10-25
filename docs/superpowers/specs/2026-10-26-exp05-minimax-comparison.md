# EXP-05 finite fixed-plan minimax comparison

## Problem

Issue #422 joins two existing capabilities that have separate owners: finite fixed-plan minimax solvers and an inert comparison-record codec. The synthesis comparison runner cannot represent finite action catalogues. `ResolvedProblem` also cannot identify the ordered finite controls and disturbances that define this request. The comparison must therefore own a canonical minimax request and bind both algorithm attempts to its exact bytes.

## Usage

```cpp
const auto request = make_finite_minimax_comparison_request(
    shared_case_bytes, methods, independent_oracle, resource_policy);
const auto result = run_finite_minimax_comparison(request, context);
const auto archive = record_finite_minimax_comparison(request, result);
```

The returned archive is an inert `csl.comparison-record/1` artifact. Reopening it validates recorded evidence but never executes a solver.

## Shape

- `FiniteMinimaxCase` owns one canonical request: model, initial set, ordered finite action catalogue, per-stage disturbances and admissible states, terminal objective, and explicit limits. Its canonical bytes and digest are the shared input identity; no solver-specific conversion may silently change the action or disturbance domain.
- `FiniteMinimaxMethod` declares a supported implementation and its effective configuration. The first pair is the numerical enumerator and the validated interval implementation on a case admitted by both. Unsupported admission remains an explicit attempt.
- `FiniteMinimaxAttempt` keeps lifecycle status, termination, mathematical outcome, evidence scope, measurement, and source/configuration identity as separate fields. A lossless versioned outcome attachment retains every per-plan witness, rejected plan, interval bound, or unresolved overlap.
- `FixedPlanMinimaxOracle` consumes the canonical case independently of either solver's evaluation helpers. It enumerates all action plans and disturbance histories, checks every constrained stage and terminal objective, and returns `verified`, `incorrect`, or `inconclusive` with a bounded scope and retained evidence.
- The application layer executes methods and oracle. The run-artifact layer records each actual attempt. The existing comparison codec binds ordered attempts, run references, configurations, and the common manifest hash into the comparison record. `ComparisonAttempt` remains a reference boundary; it does not gain minimax-specific duplicate fields.

This is a domain-specific comparison seam, not an extension of the synthesis comparison runner. It exposes one request/result path, while keeping the comparison wire format behind the existing artifact codec. Validate bytes and compatibility at request preparation; keep solver and oracle evaluation pure over the owned case. (boundary discipline, minimize reader load)

## Synthesis decision

Candidate A is the base because it represents pre-result refusal, cancellation, and failure without inventing a mathematical answer. Candidate B's stronger oracle contract is incorporated: independent case input, separate evaluator, exhaustive plan/history enumeration, stage checks, terminal scoring, a bounded budget, and three-way evidence status. The cross-judge rejected `ResolvedProblem` as the finite case identity because it does not own the finite action and disturbance catalogues.

## Tradeoffs accepted

- We accept a minimax-specific run-final arm and a versioned outcome attachment so minimax meaning stays typed and full replay evidence stays available.
- We accept a dedicated bounded oracle rather than treating one solver as its own checker.
- We accept an explicit unsupported or inconclusive row when a method or oracle cannot cover the shared case.
- We accept that run-artifact and comparison-codec evolution must preserve existing schema readers; no historical result is rewritten.

## Alternatives considered

- **Reuse the synthesis comparison runner:** loses because finite action/disturbance inputs do not fit its continuous-control `ResolvedProblem` path and synthesis-family output. It hides extra conversion behind a smaller call but weakens input truthfulness.
- **Store minimax data only in `ComparisonAttempt.measurement_payload`:** loses because it bypasses run-artifact outcome validation and duplicates identity/lifecycle semantics in an opaque payload.
- **Use a generic LP `ProgramFinal` as the minimax result:** loses because a finite robust plan is not an LP solve. Although the generic outcome enum can say “optimal,” its primal/bounds do not preserve per-plan evidence or assurance without an app-specific parser.
- **Use the second solver as the independent oracle:** loses because implementation agreement does not independently establish global worst case.

## Risks to resolve during implementation

- How the finite request is bound to a `RunRecord` without fabricating a `ResolvedProblem`.
- How timeout, cancellation, refusal, unsupported, resource exhaustion, failure, and mathematical infeasibility map through both run-final and comparison-attempt status schemas.
- Which numerical and validated methods share an admissible fixture and comparable request semantics.
- How oracle identity, independence, bounded work, and exact result attachment are verified.
- The run schema change is public. Record package/release impact in the PR and keep old run-statistics versions decodable.

## Alternatives reviewed

The independent candidates converged on a typed minimax run outcome, a dedicated application path, and reuse of the existing content-addressed comparison record. Candidate A's optional-result/lifecycle distinction was kept. Candidate B's explicit oracle mechanics were grafted in. A's proposed use of `ResolvedProblem` was removed after code inspection. The cross-judge agreed with this base and flagged the schema/status mapping as implementation gates.

## Next implementation step

Add a single versioned minimax run-final and identity-recorded run input path, with codec tests for completed, unsupported, stopped, and failed outcomes before wiring the paired runner.
