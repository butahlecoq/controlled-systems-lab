# Performance, parallelism and language evaluation

Date: 2026-10-11. Initial comparison framework with updated owner direction; no new performance benchmark has been run.

Updated owner direction: prefer C++ or Rust for the main implementation, with Python acceptable for initial verification and references. C++ is proposed as the working target; the owner has not expressed a C++ versus Rust preference. Mathematical performance remains a priority. Historical implementation languages include professor's Pascal, MATLAB experiments and archived Python listings. None constrains the new stack.

## What will determine performance

The main structural costs are finite-action search (q^T plans), polytope vertex growth, H/V conversion, redundancy LPs, repeated matrix integration, and horizon/scenario optimization. A compiled implementation can reduce overhead but cannot remove exponential output or search complexity.

The published low-dimensional fuel cases and reachability experiments are initial workload anchors. They do not yet establish whether the target is one large solve, many simultaneous experiments, or a deadline-bound feedback loop.

The selected first output is an optimal solution family. Measure useful output: full joint families, exact reachable sets, projections, a selected trajectory, or a robust feasible policy are different tasks. Returning a projection faster than computing a full polytope is not a direct implementation speedup.

## Working architecture before benchmarking

Use the concrete [C++20 modular design](modular-algorithms-and-solution-sets.md) now: native library API, algorithm/backend ports, explicit set conversions and family-preserving outputs. Benchmarks evaluate these choices and alternative ecosystems; they are not a prerequisite for architecture.

## Language/system candidates

| Candidate | Why evaluate it | Questions to resolve |
|---|---|---|
| Julia with JuliaReach/numerical libraries | Existing set/reachability ecosystem and a compiled scientific workflow | Compilation latency, type stability, allocations, packaging, deployment and reviewer familiarity |
| C++ numerical core with optional bindings | Explicit memory/layout control and access to established native solvers | Build complexity, cross-platform distribution, extensibility and scientific iteration speed |
| Rust orchestration/core with numerical FFI | Ownership and concurrency can make state separation explicit | Availability/maintenance of required geometry and optimization integrations; FFI costs |
| Python interface with native/JIT kernels and external solvers | Accessible experiments and mature integrations; actual kernels need not be interpreted Python | Remaining Python loops, process/data-transfer overhead, native backend coverage and deployment |

This table is a proposal, not a measured ranking. Python with native numerical work and pure-Python nested loops are materially different architectures. Likewise, Julia requires performance-conscious type/allocation behavior. [Julia performance documentation](https://docs.julialang.org/en/v1/manual/performance-tips/).

JuliaReach, pycvxset and acados provide concrete ecosystems worth evaluating; acados' native generated solvers and high-level interfaces demonstrate that interface language and numerical-kernel language can differ. [JuliaReach](https://github.com/JuliaReach/ReachabilityAnalysis.jl), [pycvxset](https://www.merl.com/research/downloads/pycvxset), [acados](https://docs.acados.org/features/).

Do not choose a language from a single syntax microbenchmark. Compare the same mathematics, representations, solver backend, tolerances and requested output. A superior library algorithm may outweigh small language overhead differences.

## Parallelism levels

| Level | Candidate work | Limits |
|---|---|---|
| Independent jobs | Parameter sweeps, random seeds, baseline variants | Memory and I/O; easiest initial parallelism |
| Search tasks | Independent prefix subtrees and fixed-plan evaluations | Variable cost, shared incumbent, valid bounds, load balancing |
| Set queries | Support directions, independent LPs, candidate tests | Backend thread safety and task granularity |
| Numerical kernels | Sparse/dense factorizations, matrix products, conic kernels | Library threading, matrix sizes and memory bandwidth |
| Horizon/scenario structure | Structured tree solves and associative affine scans | Applicable factorization/recurrence assumptions |
| Distributed jobs | Coarse independent experiments/subtrees | Serialization, checkpoint consistency and transfer cost |
| GPU | Large/batched matrices, structured conic/tree solvers | Setup/transfer, device memory, precision and workload size |

Affine maps compose associatively as (A2,c2) after (A1,c1) = (A2*A1,A2*c1+c2), enabling scans for appropriate unconstrained recurrences. Intersections, state-dependent control and robust pruning generally break the naive scan formulation.

Use prefix sharing and streaming before materializing q^T complete controls. For disturbances, exploit support functions or structured generators when exactness/approximation permits; do not enumerate temporal disturbance vertices blindly.

## Resource policy

Outer workers and inner BLAS/solver threads share one resource budget. Start with one numerical-library thread per many small outer workers, then measure alternatives. Prevent nested oversubscription. acados exposes relevant OpenMP/batch settings; verify the selected build and configuration. [Official installation guidance](https://docs.acados.org/installation/index.html).

Workers own mutable solver workspaces. Reuse native buffers; avoid full set copies between stages/workers and avoid scalar-by-scalar FFI calls. Use coarse native calls and explicit representation conversion boundaries.

Cancellation should preserve an incumbent and its evidence. Checkpoint long searches at coarse intervals. Cache keys include inputs, numerical tolerance and backend version. Record deterministic tie handling and seeds; parallel floating reductions may change final bits.

Hard real-time control would require separate requirements for deadlines, allocation, compilation/warmup, worst-case timing and fallback control. The current study does not establish such requirements or any hard real-time guarantee.

## Proposed benchmark sequence

The architecture contract and requested optimal-family semantics are defined first. The following sequence validates implementations.

1. Restore B04 and one small minimax case (B07 or B08), resolving criterion/data ambiguities.
2. Establish a mathematically transparent low-dimensional reference, including vertex worst-case checks.
3. Compare the historical set method with a direct sparse nominal optimization and a compatible structured set method.
4. Profile before rewriting kernels: propagation, conversion, reduction, optimization, orchestration and plotting separately.
5. Compare candidate implementations with the same backend where possible; also report complete ecosystem alternatives separately.
6. Vary dimensions/horizon/action count/generators/constraints/sparsity to locate memory and time limits.
7. Test independent-job and subtree parallelism, then GPU/distributed execution if the workload justifies them.

Report cold and warm runs, median/tail runtime, peak memory, actual workers/threads, failures, numerical residuals, bound gaps and representation size. Pin environment and hardware information. Store raw results and scenario hashes.

Validate the proposed C++ stack through correctness and representative end-to-end profiling. Keep small Python mathematical references as independent oracles. Rust remains an alternative if owner preference or integration evidence favors it. See the [linear-system contract](linear-system-contract.md).
