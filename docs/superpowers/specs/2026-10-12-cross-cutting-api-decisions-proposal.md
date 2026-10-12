# Cross-cutting API decisions (proposal)

**Status: proposed defaults for owner review.** These choices make the class map implementable without closing any scientific-profile, assurance, or resource-policy decision on the owner's behalf. They refine the seams in the [class-level architecture](2026-10-12-class-level-system-architecture.md); they do not authorize implementation or change existing ticket scope.

## 1. Optimal-family result and evidence

**Proposed default:** represent family results with a closed outcome variant, not an envelope whose target and evidence fields can be freely combined:

```cpp
struct CompleteOptimalFamily {
  JointRelation relation;
  OptimumEvidence optimum;
  CompletenessEvidence completeness;
};
struct PartialOptimalFamily {
  JointRelation relation;
  OptimumEvidence optimum;
  CoverageScope known_scope;
};
using FamilyRelationToTarget = std::variant<OuterCandidateEvidence,
    InnerSubsetEvidence, HeuristicRelationEvidence>;
struct CandidateFamily {
  JointRelation relation;
  FamilyRelationToTarget relation_to_target;
};
using OptimalFamilyOutcome = std::variant<CompleteOptimalFamily,
    PartialOptimalFamily, CandidateFamily>;
```

The complete variant therefore always carries a relation, optimum evidence, and completeness evidence. Partial results state their known coverage; candidate results state the relation to the true target. A witness query may return a witness and feasibility evidence, but cannot upgrade the family outcome or completeness claim. Evidence is bound to the resolved-problem digest, objective digest, request/profile digest, ordered relation coordinates, strategy and version, and every transformation used to obtain the relation. Those identities are immutable values, not display labels. Evidence uses the class-map assurance vocabulary: `NumericalToleranceSupport` records arithmetic, tolerances, coverage procedure, and diagnostics supporting a numerical claim; `ValidatedCompletenessCertificate` is reserved for a checked certificate under an explicitly supported validated arithmetic/model profile. Numerical tolerance support is not exact set equality or validated completeness, and cannot satisfy a request requiring a `ValidatedCompletenessCertificate`. Any future certified or exact mechanism must map explicitly to one of these assurance levels and be checked by a supported verifier; it does not add a competing `ValidatedClaim` or `CertifiedClaim` variant.

The API should make mismatched bindings difficult to construct: use typed `ProblemIdentity`, `ObjectiveIdentity`, `FamilyRequestIdentity`, `CoordinateSchema`, `StrategyIdentity`, and `TransformationTrace` fields in an evidence object. At the result boundary, require exact identity and coordinate agreement with the owning `PreparedStrategy` and request, and require the trace to compose from that strategy's resolved problem. The independent verifier checks numerical-support claims against the original resolved problem. Type shape and digest binding make provenance auditable; neither alone proves the mathematical claim. A complete tag means complete relative to the declared profile and guarantee, and may only be issued by a strategy/verifier path that supplies a checkable coverage argument. A numerical tolerance check is evidence for that numerical contract, not proof of exact completeness.

Keep the relation payload behind `JointRelationPayload`; add query capabilities through typed relation adapters rather than exposing representation-specific storage through `OptimalFamilyOutcome`. Reject unsupported queries and unsupported completeness claims explicitly. Numerical support remains numerical evidence; it must not be labelled validated or certified.

**Class-map seam:** `OptimalFamily`, `JointRelation`, `JointRelationPayload`, `FamilyTarget`, `FamilyEvidence`, `Witness`, and the independent verifier. **Tickets:** [SYN-02 #61](https://github.com/butahlecoq/controlled-systems-lab/issues/61), [SYN-03 #66](https://github.com/butahlecoq/controlled-systems-lab/issues/66), [SYN-04 #67](https://github.com/butahlecoq/controlled-systems-lab/issues/67), [SYN-06 #43](https://github.com/butahlecoq/controlled-systems-lab/issues/43).

## 2. Nested execution control and provider lifetime

**Proposed default:** one outer-executor-owned `ExecutionContext` supplies cancellation, deadline, numerical policy, and the single `ResourcePolicy` for a strategy and all generated requests. It tracks a shared thread/worker budget and, only if strategies need internal fan-out, lends scoped permits from that same budget; no nested executor or independently reset budget is allowed. The policy records requested and effective worker counts, backend thread settings, and measured/admitted resource use. Before execution, backend adapters must either apply a supported thread limit or report that the limit is unenforced; comparison records cannot claim a hard cap when a linked numerical backend can create unaccounted threads. Memory limits likewise distinguish enforced admission/accounting from advisory estimates, and report actual/peak values only when measured. These are observable contracts; exact caps and mechanisms remain owner choices.

A prepared provider is owned by the prepared strategy/workspace; it cannot outlive that execution or expose a raw native workspace. Every generated request passes the provider's frozen capability/requirement admission before snapshot or native workspace creation, and retains provider provenance. Adapters check stop/deadline at documented operation boundaries and propagate termination/resource-limit outcomes without turning partial work into a complete-family claim. Each mutable workspace has one task owner. Parallel strategies initially return independent generated work to the outer executor; optional internal work must acquire shared permits and use separate workspaces.

This selects execution ownership and truthful accounting without choosing the owner's worker count, memory cap, deadlines, or whether any strategy uses internal permits.

**Class-map seam:** `ExecutionContext`, `ResourcePolicy`, `PreparedStrategy`, `SynthesisWorkspace`, `PreparedProvider`, and generated-request admission. Provider admission is implemented by [merged PR #143](https://github.com/butahlecoq/controlled-systems-lab/pull/143); its per-query hull composition is integrated by [merged PR #144](https://github.com/butahlecoq/controlled-systems-lab/pull/144). This hull path does not by itself provide generated-request composition for either full synthesis strategy. **Tickets:** [TEST-15 #78](https://github.com/butahlecoq/controlled-systems-lab/issues/78), plus strategy implementation coverage in [SYN-03 #66](https://github.com/butahlecoq/controlled-systems-lab/issues/66) and [SYN-04 #67](https://github.com/butahlecoq/controlled-systems-lab/issues/67).

## 3. Geometry planning, guarantees, and materialization

**Proposed default:** `GeometryOperationPlanner` composes the existing operation, conversion, and approximation registrations. A `GeometryOperationRequest` states the operation, ordered input representations, optional requested output representation, required guarantee/relation, and capabilities. Guarantee composition is defined per operation and ordered operands: conversion preserves or changes a representation without silently strengthening its set claim; intersection, projection, image/preimage, and optimization each declare their own soundness and completeness transfer rules. There is no universal “strongest guarantee wins” rule. Planning returns a `PreparedGeometryPlan` with each registered step, intermediate representation, guarantee, assumptions, and provenance. Planning is side-effect free; missing capability, incompatible representation, or insufficient composed guarantee rejects before workspace creation.

Prefer exact/equivalent operations when requested. A weaker inner, outer, or heuristic result is admissible only when the request explicitly allows that relation; fallback must preserve the requested guarantee. Keep expressions/lazy results where the selected adapter supports the required queries. Full representation conversion is an explicit materialization step, subject to the caller's size/resource budget and cancellation, with representation-growth and evidence reported. Sampled support directions remain samples or declared enclosures, never an exact-set claim. Do not create a second operation registry unless concrete composition requirements cannot be expressed by the typed registrations.

For a complete-optimal-family request, the planner must reject any operation plan whose composed geometry guarantee cannot support the requested coverage claim; an inner/outer/heuristic relation may produce a candidate or partial outcome, never be relabelled complete. Each composed step carries the input evidence identity and emits its own scoped output evidence, so a later verifier can audit the chain.

**Class-map seam:** `GeometryPort`, `ConversionPort`, `ApproximationPort`, their request/outcome types, `GeometryOperationPlanner`, and `PreparedGeometryPlan`. **Tickets:** [GEO-02 #40](https://github.com/butahlecoq/controlled-systems-lab/issues/40), [GEO-04 #41](https://github.com/butahlecoq/controlled-systems-lab/issues/41), [GEO-08 #52](https://github.com/butahlecoq/controlled-systems-lab/issues/52), [GEO-03 #31](https://github.com/butahlecoq/controlled-systems-lab/issues/31).

## 4. Immutable comparison definition and run identity

**Proposed default:** separate a caller-authored `ComparisonSpec` from the executed `ComparisonRun`. The spec identifies the resolved problem by content digest, the solver profile/request, output/family target, numerical tolerances, requested resource policy, repetition protocol, and the strategy/backend pairings. Its canonical serialization produces a stable `ComparisonSpecId`; edits create a new identity. It cannot be mutated after execution begins.

Each individual strategy execution/repetition produces an immutable, content-addressed `RunRecordRef` that binds the same resolved-problem digest and request/profile identity to the strategy and version, backend identities and versions, effective configuration (including effective thread settings), outcome, evidence, timings, resource observations, and raw repetition payload. The comparison stores references to all run records, including failed, unsupported, cancelled, and superseded attempts; it never overwrites a run when a rerun differs. The executed `ComparisonRunId` is derived from the `ComparisonSpecId`, the ordered individual `RunRecordRef` identities, and the comparison schema version. Thus equal source commits with different measured payloads cannot reuse a report/comparison identity.

Validate before pairing that both runs share the same problem, objective, profile/request, tolerances, output target, and requested policy. Record effective backend/config differences explicitly; a required matched-backend comparison rejects mismatches, while a permitted exception becomes a separately labelled comparison. Repetition rows remain individually addressable and the report derives summaries from the stored rows. Content addressing is over a versioned canonical record encoding; storage may embed the run records or reference an immutable store, but references must resolve and verify their digest before rendering.

**Class-map seam:** `ComparisonSpec`, `ComparisonSpecId`, `RunRecordRef`, `ComparisonRun`, and `ComparisonRunId`, plus the saved-record renderer. This API shape refines the class-map comparison artifact decision; it does not decide storage location or publication host. **Tickets:** [OBS-04 #83](https://github.com/butahlecoq/controlled-systems-lab/issues/83), [EXP-02 #94](https://github.com/butahlecoq/controlled-systems-lab/issues/94), and the end-to-end comparison in [SYN-05 #71](https://github.com/butahlecoq/controlled-systems-lab/issues/71).

## Decisions that remain open for the owner

- Confirm the first solver profile and its admitted model/objective forms; this proposal does not enable feedback, uncertain initial-state quantifiers, hybrid dynamics, or nonempty temporal coupling.
- Choose assurance fields and exactly which evidence, if any, may later satisfy validated assurance. Nothing here turns numerical evidence into a certificate.
- Choose concrete initial geometry operations, representations, and capacity fixtures; the planner contract does not imply universal H/V support or an exact capability that an adapter does not provide.
- Set execution defaults such as worker counts, deadlines, memory/thread limits, and whether a future strategy may request bounded internal permits. The shared-budget rule is proposed; values and enforcement remain explicit owner decisions.
- Review the concrete family payload/evidence types and validation ownership before implementation tickets freeze. The result distinctions above are proposed semantics, not a claim that the current opaque payload already enforces them.
- Choose which evidence checks are available in v1 and whether any future validated-completeness assurance is in scope. Numerical tolerance support is explicitly not exact proof; any later certified/exact mechanism must map explicitly to the class-map assurance vocabulary.
- Choose the versioned canonical encoding and persistence adapter for immutable comparison/run identities; embedding versus an immutable external store remains open, but mutable references and source-commit-only report IDs are excluded by the proposed contract.
- Confirm which operations have reviewed guarantee-composition rules and which resource controls can be enforced by each selected backend; unsupported plans or unenforced limits must remain visible in outcomes and records.
