# REVIEW-05 mutable-state ownership inventory

Source: clean `main` at `fd7641e6f106202eae4b5ebdf9ecc874ade0f63e`.
This is a focused static inventory of execution, lazy geometry, native solver,
and conversion ownership. It is not a complete audit of every provider or
third-party library call in the repository.

| Area | State and lifetime | Concurrency boundary / evidence |
| --- | --- | --- |
| Lazy support and ray checks | Support and ray memoization maps are local to an operation and passed by reference through recursion (`src/geometry/lazy/support.cpp:45-60`, `135-140`). | No process-wide cache appears in these paths. A caller gets a separate local map per operation. |
| Lazy materialization | Growth and row caches are local to a materialization call and threaded through recursive traversal (`src/geometry/lazy/materialize.cpp`). | Lazy handles share immutable payloads (`include/csl/sets/contracts.hpp:15`); expression payloads capture their operation snapshot. |
| LP with HiGHS | `HighsLPWorkspace` owns one `std::unique_ptr<Highs>`, loaded-model state, and an optional workspace-local warm basis (`src/adapters/lp/highs.cpp:165-174`). The provider factory constructs a fresh workspace (`:394`). | The execution contract gives each concurrent task a fresh exclusive workspace (`docs/contracts/execution.md:17-24`). Warm-basis reuse is explicit and local; failure and exception paths clear native/model/basis state. Separate workspace concurrency is exercised in `highs_lp_tests`. |
| Convex optimization with HiGHS | Each convex workspace owns separate phase-I and QP `Highs` instances (`src/adapters/convex/highs.cpp:286-288`). | The execution contract supplies exclusive workspaces. The phase-I basis is transferred to the QP within the same call; it is not shared between workspaces. Native callbacks are attached for the call and detached by RAII. |
| HiGHS callbacks and logging | Callback text and stop observations live in a stack-local `CallbackState` (`src/adapters/highs_session.hpp:11-24`). | `CallbackGuard` attaches the callback and detaches it during destruction (`:26-59`). Both adapters configure one native solver thread. No direct product `stdout`/`stderr` logging call was found under `src/` or `include/` in this pass; callback logs are captured per operation. |
| Qhull | Each conversion creates a local `NativeQhull` with its own `qhT`, temporary output/error streams, and RAII cleanup (`src/adapters/polyhedral/qhull.cpp:93-101,116-122`). | No global Qhull context is used by the adapter. Concurrent conversion calls are covered by `hv_conversion_tests` and `quickhull_2d_lp_test`. |
| Executor and batch runner | Executor overlap is rejected by an atomic busy guard (`include/csl/execution/executor.hpp:121-133`). Worker slots have single-writer result ownership; scheduler admission/reservation state is mutex-protected; dispatch joins started workers before publishing. | Existing execution and batch suites cover overlap rejection, cancellation, result ordering, and worker-local workspaces. The focused TSan run adds native adapters and timing paths. |
| Timing collector | A shared owner contains mutable slot state guarded by a mutex (`src/execution/timing_collector.cpp:103,163-178`). | `snapshot()` copies guarded slot state before composing the report; concurrent claims and worker paths are covered by `timing_collector_tests`. |
| LP test hooks | Warm-basis rejection state is `thread_local`; stop-source observation is atomic, and both exist only under `CSL_HIGHSLP_TESTING` in `src/adapters/lp/highs.cpp`. | These hooks are test-only and are not part of the production backend's shared mutable state. |

## Scope limits

- No TSan report occurred for the seven selected test executions.
- This does not test every adapter, every solver failure path, arbitrary
  application-level sharing, or every third-party runtime behavior.
- A passing dynamic sanitizer run is evidence about exercised executions, not a
  proof of whole-library thread safety.
- Native thread counts remain adapter declarations; executor admission does
  not control external global thread pools.
- The audit does not satisfy #95's remaining equal-output workload ladder,
  representation/output growth, or stronger source-level limiter profile.
