# REVIEW-05 ownership delta at 7243ed35

Baseline: `fd7641e6f106202eae4b5ebdf9ecc874ade0f63e`. Reviewed source: `7243ed353cbfdde3c897572c58cc6d6a244194ea`.

The independent reviewer inspected state sites across all 85 changed product paths, then checked workspace, callback, payload and resource lifetimes. `changed-product-paths.txt` records the scope. `state-sites.txt` is a discovery aid, not proof. No actionable ownership or synchronization finding remained in this scope.

| Area | State and lifetime | Boundary and source evidence |
| --- | --- | --- |
| HiGHS clock capture | The diagnostic index is an atomic uint64; snapshots and JSON streams are call-local. | `src/adapters/lp/highs.cpp:33,102,388`: relaxed identity allocation, synchronized CSL stderr events and snapshot after the workspace-owned native run. `cmake/ApplyPinnedHighsClockSnapshotPatch.cmake:16` returns value records from that Highs instance. |
| Native workspaces and warm bases | LP basis/model state stays in its exclusive workspace. Convex phase-I/QP instances remain workspace-owned. | Fresh factories remain in `src/adapters/lp/highs.cpp:504` and `src/adapters/convex/highs.cpp:287,422`. New immutable admission envelopes introduce no cache. |
| Compiled verifiers | Static shared verifier instances and identity strings are const; generic A/B verifier identity is fixed at construction. | `src/registry/compiled_verifiers.cpp:591-602`, `src/registry/nominal_linear_exact_verifier.cpp:412-418`. Reconstructed rows and limits are per invocation. |
| Exact-family payloads | Reconstruction budgets are local; published payloads have const ownership. | `src/registry/b04_c_exact_verifier.cpp:479,503`; `src/synthesis/exact_rational.hpp:23`; no shared arithmetic counter or memoization. |
| Instrumented B builder | Public and registered routes share the same private builder. The context pointer is borrowed for the synchronous call only. | `src/synthesis/strategy_b/direct_joint.cpp:220,300,446`: only optional observer scopes differ; no retained context pointer. |
| Strategy and selector state | Runtime receipts and selector dependencies belong to exclusive workspaces. Relations are immutable shared payloads. | `src/synthesis/strategy_a/strategy.cpp:191`, `src/synthesis/strategy_b/direct_joint.cpp:390`, `src/synthesis/witness_selector.cpp:187`. |
| Finite search and propagation | Attempts, traces, recursive replay paths and arithmetic buffers are operation-local or result-owned. Mixed-branch cursor continuation belongs to that cursor. | New finite-action/finite-plan source files and `src/synthesis/finite_search/mixed_branch.cpp`; local recursive callback at `src/optimization/finite_action_replay.cpp:73` does not escape. |
| Hybrid preparation | Frozen admission/preparation storage owns programs, prepared pipelines and unique staged reachability operations. | `src/synthesis/hybrid_path_program.cpp:435,1922`; `src/synthesis/hybrid_projected_reachability.cpp:157` creates fresh workers during synchronous execution. |
| Hybrid observers | Each branch/path/verifier gets a fresh atomic observer; only the reported maximum merges into the caller aggregate. Cancellation/deadline/resource values are copied. | `src/synthesis/hybrid_path_program.cpp:1601,1799,2098`; `include/csl/execution/contracts.hpp:20`. |
| Thread CPU observation | The noncopyable timer owns its callback or borrows a reader for one synchronous operation. Built-in readers carry no mutable shared state. | `include/csl/model/hybrid_system.hpp:112`; `src/model/hybrid_system.cpp:21`; `src/synthesis/hybrid_operation_cpu.hpp:19`. Reader errors remain unavailable observations. |
| Scenario/artifact data | External file streams and reader counters are local; resolved matrices/objective weights and published materialization handles retain owned snapshots. | `src/input/scenario_loader.cpp:45,87`; `src/optimization/objective_reformulation.cpp:121`; `include/csl/artifacts/stage_projection_capture.hpp:24`. |

The baseline lazy support/materialization, Qhull context/streams, HiGHS callback guard, executor, batch runner and timing collector paths are unchanged. Their earlier ownership inventory remains applicable. No process-wide mutable cache or new unsynchronized product logging site appeared in this delta.

## Limits

- The nine selected suites passed with TSan and native clock capture enabled. They cover exercised executions, not all schedules, every numerical module or arbitrary sharing by callers.
- The fixed environment is part of the capture procedure. Concurrent mutation of process environment variables was not tested.
- CSL stderr records use osyncstream. Vendor timer stdout remains mixed native diagnostic output; concurrent per-call attribution is not established.
- B04-C exact construction is bounded by two million arithmetic operations but does not poll an execution context. Do not infer generic exact-H cancellation support for this path.
- Requested native widths and memory accounting remain distinct from enforcement. No universal BLAS-pool, heap, RSS or deadline-on-return guarantee is added.
- Thread CPU callbacks are synchronous and must satisfy the existing caller callback contracts. User callbacks with external mutable state are outside this built-in ownership verdict.
- This audit does not sign off all mathematics, benchmark comparisons, publication or the full issue #95 checklist.
