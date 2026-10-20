# acados integration review

Review date: 2026-10-19; primary-source spot-check: 2026-10-20. Repository base: `bdfcc6c02b158905d35374d740d4fd0391871c82`.
Scope: the acados v0.6.0 release, license and build identity; the problem classes,
algorithms and interfaces it exposes; and its fit as a CSL backend/component or
external comparison side. This is a research record for
[issue #512](https://github.com/butahlecoq/controlled-systems-lab/issues/512), not
build approval, benchmark authorization, or a claim that acados was executed.

## Source and release identity

The selected stable release is
[v0.6.0](https://github.com/acados/acados/releases/tag/v0.6.0), published 2026-08-06
and resolved directly to commit `503364817c872d474ab5bed219c26760ac267769`. Its
[tagged LICENSE](https://github.com/acados/acados/blob/v0.6.0/LICENSE) is explicitly
the **2-Clause BSD License**. The build is a CMake project enabling C and C++
([`CMakeLists.txt:37`](https://github.com/acados/acados/blob/v0.6.0/CMakeLists.txt#L37));
Windows defaults to static libraries, elsewhere to shared, and OpenMP is off by
default (lines 64-71); MSVC Release uses `/MT` (lines 128-130); HPMPC and QORE
are disabled under MSVC when enabled (lines 213-233).

| Component | v0.6.0 identity | License |
|---|---|---|
| acados core | tag commit `503364817c872d474ab5bed219c26760ac267769` | BSD-2-Clause |
| HPIPM (default QP) | submodule `e3a56c1caddd7f12d125d84f337b9a9e5c186271` | BSD-2-Clause |
| BLASFEO (default LA) | submodule `d6251233923c9b475fe894fb729fb63ab693e301` | BSD-2-Clause |
| qpOASES, OSQP, DAQP, Clarabel (selected optional solvers) | pinned submodules at v0.6.0 | LGPL-2.1, Apache-2.0, MIT, Apache-2.0 |
| qpDUNES and CMake-only optional solvers (HPMPC, QORE, OOQP) | outside this selected audit | not assessed |
| CasADi (Python/MATLAB) | pip-resolved and unpinned by `setup.py` | not established for the resolved version |

This is a top-level and selected-dependency check, not a complete notice or
distribution audit. The default core path uses HPIPM and BLASFEO; an optional QP
solver changes the obligation set. qpDUNES is exposed in the Python options but
its license was not reviewed here; HPMPC, QORE and OOQP are also outside this
selected license inventory. CasADi's resolved version and license must be
captured for any use; the upstream `main` license URL is mutable. The Python
package declares `numpy`, `scipy`,
`casadi`, `matplotlib`, `cython` and `Deprecated` as install requirements
([`setup.py`](https://github.com/acados/acados/blob/v0.6.0/interfaces/acados_template/setup.py)).
The companion paper is [arXiv:1910.13753v3](https://arxiv.org/abs/1910.13753v3),
submitted 2019-10-30 and revised 2020-11-26, describing the then-current C core,
BLASFEO, HPIPM, MATLAB/Python interfaces, CasADi compatibility and a design
that does not rely on automatic code generation. It predates current
globalization, sensitivity, zoRO and template-interface work; the tagged source
and docs govern this review.

## What acados solves

acados targets optimal-control-structured nonlinear programs (OCP-NLPs) and their
QP subproblems, using multiple shooting and stage-wise problem data. It supports
continuous or discrete dynamics, DAE models, bounds, linear and nonlinear
constraints, slacks, multi-phase problems and MHE; a general NLP can be posed as a
zero-horizon OCP ([Problem Formulation](https://docs.acados.org/problem_formulation/index.html),
[Features: general nonlinear programs](https://docs.acados.org/features/index.html#general-nonlinear-programs)).

| Capability | v0.6.0 evidence | Relevance to CSL |
|---|---|---|
| NLP algorithms | `SQP`, `SQP_WITH_FEASIBLE_QP`, `SQP_RTI`, `DDP` ([header:47-64](https://github.com/acados/acados/blob/v0.6.0/interfaces/acados_c/ocp_nlp_interface.h#L47-L64)) | Nominal single-solution OCP; DDP is unconstrained only |
| QP subproblems | HPIPM interior point by default; Python options also expose qpOASES, qpDUNES, OSQP, Clarabel, DAQP ([options:161-176](https://github.com/acados/acados/blob/v0.6.0/interfaces/acados_template/acados_template/acados_ocp_options.py#L161-L176)) | One final NLP iterate per solve call, with potentially multiple QP subproblems internally; no public basis or optimal-face API |
| Integrators | ERK, IRK, GNSF-IRK, lifted IRK, discrete ([options:37](https://github.com/acados/acados/blob/v0.6.0/interfaces/acados_template/acados_template/acados_ocp_options.py#L37); [paper §3.4](https://arxiv.org/abs/1910.13753v3)) | Affine discrete models map directly; continuous models add discretization choices |
| Costs and constraints | Linear/nonlinear least squares, convex-over-nonlinear, external costs; bounds, linear and nonlinear constraints, slacks | A matched quadratic terminal objective is representable, but the algebra must be proven |
| MHE and sensitivities | MHE documented and exemplified; forward/adjoint solution sensitivities and differentiable MPC ([Features](https://docs.acados.org/features/index.html)) | No CSL estimator contract; not needed for the current family request |
| Robustness | zoRO backoff/covariance update, documented as a heuristic with limitations ([`zoro_description.py:42-56`](https://github.com/acados/acados/blob/v0.6.0/interfaces/acados_template/acados_template/zoro_description.py#L42-L56)) | Not exact robust set computation or minimax |
| Parallelism | OpenMP optional and off by default; batch solvers documented; `ACADOS_NUM_THREADS=1` advised when batching ([Installation](https://docs.acados.org/installation/index.html)) | Usable for a one-thread comparison, with explicit configuration |

**The central mismatch is output scope.** `ocp_nlp_solve` fills one output iterate
and returns a status; `ocp_nlp_get` exposes `status`, residuals and timings
([solve API](https://github.com/acados/acados/blob/v0.6.0/interfaces/acados_c/ocp_nlp_interface.h#L352-L358),
[full interface](https://github.com/acados/acados/blob/v0.6.0/interfaces/acados_c/ocp_nlp_interface.h)).
`store_iterates` retains solver iterates, not alternative optima. I found no public
API, documentation or result field in v0.6.0 for an argmin set, complete optimal
family, control projection family, reachable sets, set operations, or an exact
family/coverage certificate. This is an absence-of-evidence finding, not a proof
that no user could enumerate solutions by repeated solves.

## Interfaces, code generation and platform support

| Surface | What v0.6.0 provides | Integration consequence |
|---|---|---|
| C API | Native structs and headers under `interfaces/acados_c`; one solver object per problem | Callable from C++, but not a CSL value/port boundary; needs a wrapper |
| Python | `acados_template` with ctypes/Cython; generates and compiles problem-specific C code | Requires CasADi and a compiler; setup/codegen must be separated from solve timing |
| MATLAB/Octave/Simulink and embedded | Supported interfaces, S-Functions and generated self-contained C for dSPACE/STM32 ([Embedded Workflow](https://docs.acados.org/embedded_workflow/index.html)) | Deployment capability, not a composable CSL module |
| Windows native | Python path uses CMake/MSVC ([Python Interface](https://docs.acados.org/python_interface/index.html)); MATLAB path is MinGW-first | MSVC is the relevant x64 gate, not a documented default |
| Windows MSVC | "preliminary and not thoroughly tested"; tested once with MSVC 2017/2019 in May 2021 ([Installation](https://docs.acados.org/installation/index.html)) | Highest adoption risk; build and test before any comparison |
| Upstream CI | Core and full builds run on `ubuntu-22.04` only ([core_build.yml](https://github.com/acados/acados/blob/v0.6.0/.github/workflows/core_build.yml), [full_build.yml](https://github.com/acados/acados/blob/v0.6.0/.github/workflows/full_build.yml)) | No upstream Windows evidence to inherit |

Windows x64/MSVC support is **plausible but unproven for this use**. A native build
with the selected static profile and the C API smoke path are mandatory gates; a
WSL-only result is a different environment and must be labeled as such. Concurrency
is bounded too: OpenMP is off by default, batching advises one thread per solve, and
no general claim was found that one solver workspace is safe for concurrent calls.

## Fit with CSL's current contracts

CSL's target is the complete optimal family `Z* = {z in F : phi(x_T) = v*}` and its
control projection `U*` for affine discrete-time, finite-horizon problems, with
independent verification. Strategy A composes forward reachability, terminal
minimization and backward recovery; Strategy B builds a direct joint program. Exact
complete-family assurance is restricted to the reviewed T-S01/T-S02 predicates; the
general A/B paths produce numerical candidate relations. Stage 4 is a finite-action
fixed-plan minimax with `exists u, forall w`, and finite feedback is a finite
transition game. See [modular algorithms](../architecture/modular-algorithms-and-solution-sets.md),
[framework composition](../architecture/framework-composition.md) and the
[comparison program](../architecture/comparison-program.md).

| CSL stage / request | acados contribution | Decision |
|---|---|---|
| Parallel 1 hull, vertex, LP/basis reuse (#391, #396) | No LP API, basis diagnostics or hull operation; an LP-as-QP gives one point | Not eligible |
| Stage 2 set approximation (#393, #99/#100) | No public set types or operations; zoRO covariance recursion is internal to a controller | Not eligible |
| Stage 3 Strategy A reachability/recovery (#66, #392) | No forward reachable sets, predecessor relation or control fiber | Not eligible |
| Stage 3 Strategy B nominal joint OCP (#67, #392) | Can represent one affine discrete OCP with polytope constraints and return one feasible/optimal candidate | Research baseline only |
| Stage 3 complete family `Z*`/`U*` and T-S01/T-S02 | One witness; no complete relation, projection or coverage evidence | Not eligible |
| Stage 4 fixed-plan minimax (#394, #404, #422) | Deterministic OCP; no `forall w` maximization or finite-plan certificate | Not eligible |
| Adaptive/feedback (#395, #397, #5) | NMPC re-solving; no observation semantics or finite feedback table game | Not eligible |
| LP/convex backend contract (#22, #7) | HPIPM can solve a single QP, but exposes no CSL outcome/evidence contract and no family | Not a drop-in backend |

Nominal trajectory optimization is not robust set computation, reachability,
finite-action minimax, or complete-family output. **A single optimizer is not a
family, and acados supplies no exact reachable-set or complete-family certificate.**
Even a correct acados T-S01 solve would be one point on `(0,s,1,s,1-s)`, not the
continuum itself.

## Decision: backend or component

**Do not adopt acados as a CSL backend or component in the current architecture.**
It is not an LP/convex backend with CSL's immutable request, workspace, outcome and
evidence contracts, and it cannot answer the complete-family request that motivates
the synthesis path. A production adapter would translate the problem, map statuses
and tolerances, own generated-code builds, carry CasADi or hand-written C functions
and preserve proof/evidence boundaries, which the current capability overlap does not
justify. The only conceivable seam is a research-only nominal OCP witness adapter
for Strategy B on matched convex cases, as an external wrapper rather than a
`ConvexPort` or `StrategyPort`, not a production dependency before the gates
below pass.

## Decision: external comparison side

**Qualified yes, for one narrow track:** add acados as an external, single-witness
baseline for Stage 3 nominal open-loop OCPs on matched affine/polytope cases, where
its output is compared with a CSL Strategy B witness on feasibility and the original
objective. This is a witness-quality baseline, not a complete-family side. It
may also serve as an adapter correctness smoke test on T-S01/T-S02, where CSL
can independently check membership in the known family.

It is **not** eligible for Parallel 1, Stage 2 set approximations, Strategy A
reachability, complete-family claims, Stage 4 minimax, adaptive/feedback synthesis,
or an estimator/MHE comparison. It should not substitute for the Strategy A/B pair;
if used in Stage 3 it is a third side with a different output scope. No speed or
quality winner may be claimed from different scopes, and no "optimal" claim follows
from acados's solver status alone.

## Fairness and evidence gates

1. **Identity and input.** Pin v0.6.0 and its submodule commits, compiler, generator,
   BLASFEO/HPIPM targets, thread settings, Python/CasADi versions and build options;
   record any patch and the generated-code directory. Hash the canonical CSL problem
   and the translated acados problem, preserving dimensions, stage indexing, time
   steps, bounds and initial state; no silent clipping or regularization.
2. **Objective algebra.** Map CSL's `0.5 x'Qx + q'x + c` terminal objective to a
   supported acados cost form and prove factor, reference, offset and terminal-
   versus-stage placement. A zero stage cost and singular `Q` need explicit treatment.
   acados stage costs are scaled by `cost_scaling`, defaulting to `time_steps` with
   terminal value one
   ([`acados_ocp.py:1233-1234`](https://github.com/acados/acados/blob/v0.6.0/interfaces/acados_template/acados_template/acados_ocp.py#L1233-L1234)),
   so unit time steps are the simplest admissible case. Report the objective with
   CSL's original-coordinate evaluator, not acados's cost output.
3. **Dynamics, constraints and tolerances.** Use `DISCRETE` dynamics with the exact
   `A`/`B`, map the H-representation row by row, enforce the initial state as an
   equality, and add no slacks unless the CSL problem has them. Set acados NLP/QP
   tolerances at least as tight as the CSL verification target, report both, and
   classify statuses without promoting "solved" to "verified".
4. **Independent oracle and output scope.** Recompute residuals, violations and the
   original objective with CSL's verifier; use exact T-S01/T-S02 membership where
   applicable. On general convex cases, compare feasible incumbents but assert no
   optimality without an independent bound or certificate. Retain that acados returns
   one candidate and a status; report family evidence separately and do not infer
   uniqueness or completeness from a singleton or repeated runs.
5. **Timing and resources.** Use tuned Release builds, one thread, no batch, at least
   five alternating repetitions, and separate code generation, compilation, setup and
   solve. Report median, range, memory and the limiter profile; retain failures and
   timeouts as outcomes.
6. **Licenses and platform.** Carry the BSD-2-Clause core, HPIPM/BLASFEO and any
   reviewed optional LGPL/Apache/MIT notices as a partial engineering inventory,
   not legal approval. qpDUNES, HPMPC, QORE and OOQP are outside the inventory;
   CasADi's resolved version/license also remains unverified.
   Require a native Windows x64 MSVC build and smoke test, or record WSL as a
   different platform.

No gate here authorizes benchmark execution. The five-run comparison is a
separate possible future effort, not a continuation or deliverable of this
research spike. Any Stage-3 comparison still requires the comparison-record and
fixture prerequisites (#83/#94/#402), a new scope decision and separate owner
approval.

## Recommended next steps and scope

| Step | Work and acceptance | Estimate |
|---|---|---|
| 0 | Record release/tag/submodule/license identity and the exact build recipe; no code changes. | 0.5 day |
| 1 | Build v0.6.0 natively on Windows x64 MSVC in the static one-thread profile; run an upstream minimal OCP example and a C API smoke solve. Pass only if reproducible, with logs and notices captured. | 1–2 days; high risk |
| 2 | Prove the algebraic mapping for one matched affine/polytope Stage 3 case (terminal quadratic, zero stage cost, unit steps); build a throwaway adapter and check the witness with CSL's verifier. Pass only if objective and constraints match independently. | 3–5 days |
| 3 | Separate future benchmark/comparison scope, outside this research spike: only after #83/#94/#402, a new scope decision and explicit authorization, consider a comparison record with five alternating repetitions and all outcomes. | Not authorized or estimated by this review |

The research-only Steps 0–2 total roughly **4.5–7.5 engineering days**, with the
largest uncertainty in the MSVC build and objective/constraint mapping. The
separate future comparison is not included in this estimate. Stop if the native build
fails, if objective equivalence cannot be proven, or if only a single witness is
available while the question requires a family.

## Sources

Sources initially accessed 2026-10-19; key tagged-source claims were spot-checked 2026-10-20. Core: [release v0.6.0](https://github.com/acados/acados/releases/tag/v0.6.0), [tag commit](https://github.com/acados/acados/commit/503364817c872d474ab5bed219c26760ac267769), [LICENSE](https://github.com/acados/acados/blob/v0.6.0/LICENSE), [CMakeLists.txt](https://github.com/acados/acados/blob/v0.6.0/CMakeLists.txt), [.gitmodules](https://github.com/acados/acados/blob/v0.6.0/.gitmodules),
[ocp_nlp_interface.h](https://github.com/acados/acados/blob/v0.6.0/interfaces/acados_c/ocp_nlp_interface.h), [acados_ocp_options.py](https://github.com/acados/acados/blob/v0.6.0/interfaces/acados_template/acados_template/acados_ocp_options.py), [setup.py](https://github.com/acados/acados/blob/v0.6.0/interfaces/acados_template/setup.py), [zoro_description.py](https://github.com/acados/acados/blob/v0.6.0/interfaces/acados_template/acados_template/zoro_description.py), [core_build.yml](https://github.com/acados/acados/blob/v0.6.0/.github/workflows/core_build.yml), [full_build.yml](https://github.com/acados/acados/blob/v0.6.0/.github/workflows/full_build.yml).
Docs: [home](https://docs.acados.org/index.html), [installation](https://docs.acados.org/installation/index.html), [problem formulation](https://docs.acados.org/problem_formulation/index.html), [features](https://docs.acados.org/features/index.html), [Python interface](https://docs.acados.org/python_interface/index.html), [embedded workflow](https://docs.acados.org/embedded_workflow/index.html). Paper: [arXiv:1910.13753v3](https://arxiv.org/abs/1910.13753v3), §2.4, §3.2, §3.4, §4–§6.
Selected dependency licenses: [HPIPM](https://github.com/giaf/hpipm/blob/e3a56c1caddd7f12d125d84f337b9a9e5c186271/LICENSE.txt), [BLASFEO](https://github.com/giaf/blasfeo/blob/d6251233923c9b475fe894fb729fb63ab693e301/LICENSE.txt), [qpOASES](https://github.com/acados/qpOASES/blob/125e94fa638f00350608871fc165789b1d1762f1/LICENSE.txt), [OSQP](https://github.com/osqp/osqp/blob/0dd00a578cf1c2691c5c379965d504c75bf6cfad/LICENSE), [DAQP](https://github.com/darnstrom/daqp/blob/dc13508052b658b97c672a8c223029fd9c0d42b5/LICENSE), [Clarabel.cpp](https://github.com/acados/Clarabel.cpp/blob/c73eb64352f17fc18bc10fe3c082fcbf9a3c0487/LICENSE.md). CasADi's unpinned license was not established; the upstream [license file](https://github.com/casadi/casadi/blob/main/LICENSE.txt) is mutable.
Context: [issue #512](https://github.com/butahlecoq/controlled-systems-lab/issues/512), [Frey et al., ECC 2024](https://publications.syscop.de/Frey2024.pdf), [recent research note](recent-research.md), [comparison program](../architecture/comparison-program.md), [framework composition](../architecture/framework-composition.md),
[modular algorithms](../architecture/modular-algorithms-and-solution-sets.md), [convex programs](../contracts/convex-programs.md), [finite-action minimax](../contracts/finite-action-minimax.md), [published-results evidence](../architecture/published-algorithm-results.md).

## Claims not established

- No acados install, build, test, benchmark, or Windows x64/MSVC run was performed.
- No independent verification of the paper's performance, platform or comparison
  claims; it is a 2019/2020 snapshot, not a v0.6.0 capability statement.
- No legal conclusion or complete dependency/notice audit; qpDUNES, HPMPC, QORE
  and OOQP were not assessed, and CasADi is unpinned by the Python package metadata.
- No proof that acados cannot be extended to enumerate optimal families; this review
  establishes the absence of a documented v0.6.0 family/reachability certificate,
  not a mathematical impossibility.
- No claim of general thread safety, deterministic timing, hard real-time behavior
  or arbitrary batch concurrency, and no comparative quality or speed result.
- No claim that one matched case generalizes to CSL's ladders or historical
  fixtures, or that zoRO is an exact robust or minimax method.
- No claim that MHE, sensitivities, code generation or embedded deployment satisfy a
  current CSL contract, and no authorization for benchmark execution or production
  integration; those need separate tickets and owner approval.
