# Class-level architecture synthesis

Status: proposed ticket defaults; scientific gates remain open. This note accompanies the [class-level architecture](2026-10-12-class-level-system-architecture.md), grounded in main `d45b0114282045bf6ba96a9d196261f66a9a8372` and the existing architecture branch.

## Base and review evidence

Candidate B is the base for the synthesis. It owns each strategy's derivation inside one workspace, retains a common joint-history relation, and gives one `FamilyPublisher` authority over claim construction/binding. These choices hide representation and coverage bookkeeping from callers. The existing document's status map, source caveats, and ticket links remain in place.

Candidate A dropped out and supplied no viable final design package. This is a provisional choice supported by the available candidate and independent review, not a two-candidate consensus. No agreement or score is attributed to Candidate A.

The cross-judge scorecard for Candidate B was:

| Criterion | Score |
|---|---|
| Scientific full-family semantics | 4/5 |
| Ownership and interface depth | 5/5 |
| Result and evidence semantics | 4/5 |
| Ticket-ready interfaces | 2/5 |
| Decision and scope truthfulness | 4/5 |

The review verdict was "provisional base, not yet ticket-ready." The revisions supply the missing callable contracts; they do not convert numerical support into scientific approval or validated completeness.

## Grafted findings

- Keep one coordinated migration of `SynthesisResult`, `SynthesisOutcome`, `SynthesisWorkspace`, and `StrategyPort`. Preserve termination, mathematical outcome, bounds, and incumbents independently; do not create a parallel `FamilySolve` interface.
- Keep `FamilyPublisher` as the sole claimed-family constructor. Distinguish a known-optimal incomplete subset from a feasible candidate whose optimality is unproved. Stopped results retain only scoped partial/candidate products and valid existing evidence.
- Specify resolved-problem/effective-request preparation, canonical sparse history rows, A's joined backward fibers, B's direct program/extraction, and bound coordinate/row/transformation maps.
- Use the existing `SelectorPort` for witnesses and `GeometryPort` for mathematical projections. Carry source identity, counts, query status/stop evidence, and provenance without upgrading family claims.
- Prepare operation plans over the existing geometry/conversion/approximation registries and owning frozen `PreparedProvider` values. Check each operation-specific guarantee transfer; no new registry or generic guarantee ranking is introduced.
- Reuse versioned `artifacts::RunRecord` publication/encoding for every attempt. Add typed comparison spec/run/reference records and offline report projection/HTML export with explicit size-limit omissions.
- Gate numerical completeness on a coordinated `check_family_evidence` migration and independent T-V02/#157 public-interface tests. Samples, residuals, solver status, and paired objective agreement do not establish coverage.
- Apply the owner-approved `u ∈ [-1,1]` only to new baselines, preserve archival B04 and the existing T-S01 oracle, and correct the stale #143/#144 draft-status self-review.

## Remaining gates and next step

The first-workflow gates are scientific numerical-coverage policy and the exact-operation/capacity fixture. Historical B04 restoration is a separate archival task and does not block newly authored nominal-baseline experiments. The nominal solver profile is confirmed. Future feedback, uncertainty, hybrid/discrete, approximation, and validated profiles remain separate work.

First implement the coordinated #155/#157 public contract and tests, then the private relation/publisher path against T-S01/02/03 and the admitted #53/#51 operations. T-V01/02, T-X01, and T-X02 connect that work to independent verification, two-strategy acceptance, and saved artifacts. No interface is declared implemented by this synthesis.
