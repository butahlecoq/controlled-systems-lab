# Relevant developments and analogues, 2021–2026

Search date: 2026-10-11. Strict window: 2021-10-11 to 2026-10-11. This is a targeted initial review of primary sources, not an exhaustive systematic survey. [Bibliography and reading depth](bibliography.md).

The archived set-based approach remains useful. The strongest opportunities are richer set representations, structured feedback optimization, explicit uncertain-model estimation, and hardware-aware numerical solvers. The recommendation below is a design inference from the cited work, not a measured improvement on the supplied fuel experiments.

## 1. Scalable robust controllable sets

Vinod, Weiss and Di Cairano develop constrained-zonotope approximations for robust controllable sets under symmetric compact convex additive uncertainty. Their approach avoids certain projections and optimization solves, with exactness only under specified sufficient conditions. They report an inner approximation for a 100-dimensional, 20-step problem in under 15 seconds. This is an author-reported result for a different output and problem, not a speedup against our archive. [R01](https://www.merl.com/publications/TR2025-023).

**Proposed evaluation:** add a constrained-zonotope backend and compare robust predecessor computation against a low-dimensional exact polytope reference. Measure inclusion, conservatism, memory, generators and runtime. Preserve inner/outer status throughout the result.

## 2. Feedback optimization beyond fixed-plan enumeration

System Level Synthesis can optimize LTV feedback responses and uncertainty bounds jointly for linear systems with polytopic model uncertainty and additive disturbances. The cited method minimizes an upper bound on worst-case MPC cost. System-level tube MPC is a related abstraction. Neither is automatically an exact substitute for the archive's finite-action minimax enumeration. [R02](https://arxiv.org/abs/2203.11375v3), [R03](https://www.research-collection.ethz.ch/entities/publication/a3609de6-a49a-4e5c-b1f5-07f84896b347).

**Proposed evaluation:** make policy class explicit; compare fixed-plan, shrinking-horizon replanning, and a supported robust feedback approximation. Continuous feedback methods need an explicit discrete-actuator treatment if used with a finite throttle catalogue.

## 3. Data-driven uncertainty and state/model estimation

Noisy-data reachability represents a set of models consistent with measured data, rather than selecting one fitted matrix and ignoring its uncertainty. Constrained matrix zonotopes can trade additional computation for less conservative enclosures and incorporate prior knowledge. The first preprint predates the window, while the 2023 TAC publication/revision is within it. [R04](https://arxiv.org/abs/2105.07229v3).

A 2025 review surveys stability, robustness and constraint guarantees for behavioral data-driven MPC. A 2023 survey covers nonlinear data-driven methods with semidefinite-programming guarantees. These are useful assumption maps, not universal guarantees for arbitrary learned models. [R05](https://arxiv.org/abs/2406.04130v2), [R06](https://arxiv.org/abs/2306.16042v2).

**Proposed evaluation:** reserve an estimator module that returns state/model sets, noise assumptions and validity metadata. Keep this independent of the archive's use of “adaptive,” which mainly means measured-state replanning.

## 4. Practical robust MPC with efficient uncertainty updates

The 2024 acados zoRO work separates nominal optimization from uncertainty propagation and constraint backoff updates, with a native implementation and RTI integration. It discusses suboptimal feasible solutions at convergence under regularity and small-uncertainty conditions; a single real-time iteration is not a generic convergence certificate. Its example runtime gains are not measurements on our baselines. [R24](https://publications.syscop.de/Frey2024.pdf).

**Proposed evaluation:** compare a supported tube/backoff controller against exact low-dimensional robust checks. Document the difference between ellipsoidal horizon uncertainty and Cartesian stagewise boxes. Add preparation/update/feedback phases only when a deadline requirement emerges.

Advanced-step RTI (2024) and differentiable NMPC (2025) are further leads for reduced feedback delay and controller sensitivities. They require detailed review before adoption. [R25](https://publications.syscop.de/Frey2024a.pdf), [R26](https://arxiv.org/pdf/2505.01353).

## 5. Parallel and GPU solvers

GPU branch MPC exploits scenario-tree structure and uses parallel LQR subproblems; the current preprint reports gains on larger problems. It differs from certifying every continuous disturbance in a box and from computing exact polytopes. [R07](https://arxiv.org/abs/2506.13624v2).

CuClarabel moves conic interior-point work and linear-system solves to GPUs, including mixed-precision options. This makes conic backends worth measuring, without implying that a tiny four-state problem benefits from GPU transfer and setup overhead. [R08](https://arxiv.org/abs/2412.19027v3). CVXPY 1.7 added interfaces to GPU solver options, which can support prototypes without requiring a Python numerical core. [R18](https://www.cvxpy.org/version/1.7/updates/index.html).

**Proposed evaluation:** start with independent batches and prefix reuse on CPUs; benchmark GPU kernels only for sufficiently large structured or batched workloads. Compare objective/residual quality as well as time.

## 6. Emerging directions: explicitly provisional

| Work | Potential addition | Qualification |
|---|---|---|
| Online zonotopic recursive least squares, first submitted 2025, revised 2026 | Online LTV/model-set estimation and reachable-set updates | Abstract-level assessment; examine drift, bounded-noise and data assumptions [R09](https://arxiv.org/abs/2509.17058v2) |
| Constrained matrix convex generators, 2026 | Mixed bounded/Gaussian uncertainty with richer geometry | Confidence/probability semantics differ from deterministic bounded robustness [R10](https://arxiv.org/abs/2604.04822v1) |
| Koopman embeddings for nonlinear Lipschitz systems, 2026 | Lifted reachability with residual bounds | Guarantee claims are conditional; inspect full bounds and projection assumptions [R11](https://arxiv.org/abs/2604.00150v2) |

These were available by the assessment date. No peer-reviewed status is assumed where not verified. Learned controllers and reinforcement learning may later generate candidate policies, but the reviewed evidence does not justify replacing the deterministic robust core with an unrestricted learned policy.

## 7. Existing software analogues

| Project | Relevant responsibilities | What it does not establish for us |
|---|---|---|
| JuliaReach / LazySets | Lazy set expressions, support queries, reachability ecosystem | Automatic exact discrete minimax synthesis or archive reproduction [R14](https://juliareach.github.io/LazySets.jl/stable/) |
| CORA | Rich set types and reachability/verification tools in MATLAB | A ready-made language-neutral public library matching our API [R15](https://tumcps.github.io/CORA/) |
| pycvxset, 2025 | Polytopes, ellipsoids and constrained zonotopes; optimization/H/V integrations | All operations sharing one guarantee or low conversion cost [R13](https://www.merl.com/research/downloads/pycvxset) |
| do-mpc | Model, MPC, MHE and simulator separation; robust multistage trees | Full robustness to a continuous uncertainty set from finitely enumerated scenarios [R16](https://www.do-mpc.com/en/develop/theory_mpc.html) |
| acados | Native structured OCP, generated solvers, RTI, sensitivities and robust update hooks | A generic exact set-computation or finite-action global minimax library [R17](https://docs.acados.org/features/) |
| HiGHS / OSQP / cddlib | LP/QP/MIP and polyhedral numerical building blocks | The missing controller-level mathematical contract [R19](https://highs.dev/), [R20](https://osqp.org/), [R21](https://www.cs.mcgill.ca/~fukuda/soft/cddlibman/cddlibman.html) |

These are candidates for reuse, adapters or comparison; we have not installed or benchmarked them. Review dependency/version/license requirements when selecting integrations. pycvxset's repository license and optional commercial backends are concrete selection considerations, not a reason to exclude all Python orchestration.

ARCH-COMP25 provides common linear/hybrid verification examples and discusses CORA and JuliaReach without claiming one universal winner. External benchmark cases can complement the owner's published experiments after scenario compatibility is checked. [R12](https://portal.fis.tum.de/en/publications/arch-comp25-category-report-continuous-and-hybrid-systems-with-li/).

## 8. Recommended research order

| Priority | Work | Evidence required before adoption |
|---|---|---|
| P0 | Restore published baseline inputs and resolve criterion discrepancies | Independent recomputation; agreed historical vs corrected targets |
| P0 | Correct worst-case oracle and explicit robust containment | Small exact references and residual/certificate evidence |
| P1 | Exact polytope reference plus support/CZ alternatives | Operation contracts, inclusion/error comparisons |
| P1 | Direct sparse nominal QP/SOCP alternative | Same objective, constraints and output semantics |
| P1 | Prefix reuse, streaming search and independent batch parallelism | Same feasible plans/objective, memory/runtime measurements |
| P2 | Robust feedback/SLS/tube methods | Policy-class and uncertainty compatibility |
| P2 | State/model estimation | Noise/identifiability/model-containment assumptions |
| P3 | GPU, mixed uncertainty and nonlinear lifting | Workload evidence and proof audit appropriate to each claim |

This preserves the research lineage while making advances assessable. The open-source interface should expose assumptions and results clearly enough for scientific reviewers to challenge any individual claim.

## Set representation and architecture follow-up

The [focused representation review](../architecture/set-representations-and-ellipsoidal-toolbox.md) adds ellipsoidal software/methods, ellipsotopes, hybrid and polynomial zonotope variants, with source dates and reading depth. The [modular algorithm design](../architecture/modular-algorithms-and-solution-sets.md) separates native representations, exact conversions, inner/outer approximations, numerical backends and synthesis strategies. The first output is an optimal solution family; complete-family scope must be preserved when evaluating alternative algorithms. Architecture contracts precede benchmark implementation.
