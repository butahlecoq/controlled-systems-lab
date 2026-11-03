# EXT-07 per-operation thread CPU observations

## Problem

Hybrid relation records already own the canonical operation identity, row and matrix deltas, wall duration, and completion state. EXT-07 separately measures process CPU around whole reachability, provider, and verification intervals. Issue #156 still lacks a CPU observation attached to each mode or transition operation. The model layer must not call operating-system clocks or depend on the higher execution layer.

## Usage

Existing model callers can compose relations without collecting CPU:

```cpp
auto result = model::compose_hybrid_path_relation_with_report(
    system, request, path, limits, cancellation);
```

The built-in hybrid adapter supplies a synchronous callback for current-thread CPU readings. Every attempted operation returns its CPU duration or an explicit unavailable reason in the same record as its operation identity and partial work. Consumers read one canonical operation trace; they do not join a second resource sidecar.

## Shape

`model::HybridRelationOperationRecord` remains the single owner of each operation observation. Add `HybridOperationThreadCpuObservation`, a sum type with a measured nanosecond duration and unavailable reasons (`not_requested`, `unsupported_platform`, `read_failed`, `clock_regressed`). Add one optional callback in `HybridRelationInstrumentation`; it returns a model-owned raw thread CPU reading or an unavailable reason. The model samples it synchronously before and after each operation and stores the delta in the operation record. A missing callback produces `not_requested`.

The synthesis adapter owns POSIX `CLOCK_THREAD_CPUTIME_ID` and Windows `GetThreadTimes` readers in a private helper, alongside its existing process CPU reader. The model receives only a synchronous callback and model-owned readings; it does not depend on the execution timing library. The built-in projected adapter and general relation composer use the same operation timer so successful, refused, stopped, and partially completed operations follow the same rules. Reading failures are observational only and cannot change mathematical outcomes. This reports CPU on the composing thread; it excludes other threads and does not enforce a CPU budget.

The existing per-operation identity fields remain the stable join key for saved data: kind, stage, optional mode, and optional edge. The operation vector order is preserved. A separate ordinal and CPU sidecar would duplicate identity and require an extra alignment invariant without improving the inline result shape.

The EXT-07 saved reports add these operation records under a new schema version. Existing schema `/1` and `/2` report bundles stay immutable and renderable. Current reports retain process CPU as a distinct whole-process measure.

## Synthesis decision

Two independent sketches were compared against these criteria: one canonical record per operation; no model dependency on execution or OS APIs; explicit unavailable and partial-operation evidence; coverage of both general and projected composers; minimal caller coordination and report compatibility.

| Candidate | Canonical record | Layering | Partial evidence | Both composers | Reader complexity |
| --- | ---: | ---: | ---: | ---: | ---: |
| Inline model record with injected reader | 5 | 4 | 5 | 4 | 5 |
| Execution-owned sidecar keyed to operation | 2 | 4 | 4 | 4 | 2 |

The inline record is the base. It matches the model layer's ownership of operation provenance and keeps resource evidence beside structural deltas and completion. The sidecar's typed key and explicit one-to-one validation were considered; they were not adopted because they create a second trace that must remain synchronized. A build confirmed that the synthesis target does not link the execution timing library, so platform clock reads stay in a private synthesis helper. The configured cross-judge pool contained only the runner family, so the arena cross-judge was skipped.

## Tradeoffs accepted

- We accept a narrow synchronous callback in the model API in exchange for keeping operating-system code outside the model and avoiding a model dependency on the execution library.
- We accept current-thread-only CPU accounting in exchange for attributing the measure to the exact composer operation; helper-thread CPU and provider-specific CPU remain unmeasured.
- We accept best-effort unavailable observations in exchange for keeping clock failures separate from relation success or failure.
- We accept a new saved-report schema version in exchange for preserving older report bundles byte-for-byte.

## Alternatives considered

- A synthesis sidecar keyed by `(path, operation)` keeps the model record smaller, but exposes two traces to callers and adds key and ordering validation at every consumer.
- Passing `ExecutionContext` or `TimingClock` into model composition reuses existing timing machinery, but couples the lower-level model API to execution-layer policy and introduces a forbidden library dependency.
- Reading process CPU per operation would include helper threads but also unrelated concurrent process work, weakening operation attribution.

## Open questions and risks

- Does the user want resource enforcement in addition to the evidence profile? This observation is not an enforceable CPU cap.
- Do supported hybrid adapters create helper threads during model relation composition? The built-in composer is synchronous; custom adapters need to label their clock scope accurately.

## Next implementation step

Add the typed observation and optional reader to the model operation recorder, then wire the platform readers, tests, and versioned EXT-07 report serialization through the built-in adapters.
