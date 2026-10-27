# Explicit MPC and set comparison: source audit and exact pilot

Date: 2026-10-27. Issue: [MPC-08 #604](https://github.com/butahlecoq/controlled-systems-lab/issues/604). This source audit and original fixture derivation preceded the runnable pilot; its preserved build and run results are in [`benchmarks/reporting/mpc08_explicit/README.md`](../../benchmarks/reporting/mpc08_explicit/README.md). Web sources were checked on this date. Local repository observations refer to base `0994a51478b4fa3aa448308bddc2e6308c37111d`.

## Recommended implementation boundary

A useful first comparison can run without adding MATLAB, MPT3, or another optimization package: implement the exact one-input, horizon-one parametric QP derived below, retain its full polyhedral parameter regions, and independently check them with rational arithmetic. Label it an **original analytic explicit-QP reference**, not an MPT3 execution or a port of the complete Bemporad algorithm. Its value, first action, feasible initial domain, invariant terminal set, and fixed-initial optimal history can all be stated exactly.

An external MPT3 or PPOPT comparison remains a separate optional adapter decision. MPT3 requires MATLAB, and its official license page declares GPL. PPOPT has an MIT package license, but its inspected installation metadata requires `gurobipy` and its default solver dictionary begins with Gurobi. Neither is a silent default dependency for this repository. See the source audit below.

## Products and valid comparisons

For a fixed model, horizon, objective, and constraint timing, save each product under a separate identity:

| Product | Definition | Valid comparison |
|---|---|---|
| Feasible initial-state domain `F_N` | Initial states for which at least one admissible horizon-`N` plan exists | The initial-state projection of the complete feasible trajectory relation with the same constraints |
| Terminal invariant set `T_K` | A set preserved by a specified feedback `u=Kx`, with state and input constraints satisfied | Whole-successor inclusion under the same feedback and disturbance quantifiers |
| Explicit value `V_N(x)` and first action `kappa_N(x)` | The optimal value and one first-action rule indexed by the initial state | Matched pointwise objective/constraint programs; a selector requires its tie rule |
| Joint optimal relation `O_N(x0)` | Every optimal state/control history for one fixed initial state | CSL's matching complete-family relation, only within a delivered completeness capability |
| Reachable terminal set `R_N(x0)` | Terminal states generated from one initial state by admissible plans | The terminal-state projection of the feasible trajectory relation |

For example, `F_N` varies the initial state; `R_N(x0)` fixes it. An explicit first-action function discards later actions and may discard tied first actions. Equality between these different products is not an acceptance condition.

## Primary result, correction, and degeneracy

The canonical paper is Bemporad, Morari, Dua and Pistikopoulos, *Automatica* 38(1), 2002, pp. 3–20, DOI [10.1016/S0005-1098(01)00174-1](https://doi.org/10.1016/S0005-1098(01)00174-1), inspected in the [author-hosted PDF](https://cse.lab.imtlucca.it/~bemporad/publications/papers/automatica-mpqp.pdf). Its Section 4 and Theorem 4 establish a continuous piecewise-affine optimizer and continuous convex piecewise-quadratic value for the stated mpQP with positive-definite Hessian. The critical-region construction uses primal feasibility and nonnegative KKT multipliers. Section 4.1.1 treats linearly dependent active rows; multiplier nonuniqueness from that degeneracy is distinct from a nonunique primal optimizer.

The [2003 corrigendum](https://cse.lab.imtlucca.it/~bemporad/publications/papers/automatica-mpqp-corrige.pdf), DOI [10.1016/S0005-1098(03)00190-0](https://doi.org/10.1016/S0005-1098(03)00190-0), corrects Example 7.1 because its terminal weight matrix `P` was miscalculated. It supplies corrected matrices and a five-region controller. A replay of that example must use the correction; the present proposed fixture is independently defined and is not that replay.

For a terminal-only multi-step objective, the control Hessian can be singular. The positive-definite theorem then cannot justify a unique complete optimizer. Adding a small control penalty changes the optimization problem and its optimal family; a regularized result must receive a different objective identity.

## External software and reproducibility audit

| Candidate and inspected identity | Source facts | Consequence for this task |
|---|---|---|
| MPT3 official documentation | The [installation page](https://www.mpt3.org/pmwiki.php/Main/Installation) requires MATLAB R2011a or later and lists accompanying toolboxes including YALMIP and low-level polyhedral/optimization packages. The [license page](https://www.mpt3.org/pmwiki.php/Main/License) says GPL but does not identify its exact version. | Keep it an optional external research environment. A run manifest must pin the actual MPT archive, MATLAB release, all solver packages, and effective solver selection. This audit does not establish a MATLAB-free installation or redistribution terms for generated code. |
| MPT3 solver selection and controller products | The [FAQ](https://www.mpt3.org/pmwiki.php/Main/FAQ) says initialization detects available solvers and can prioritize commercial ones; it provides explicit solver-selection controls. [Regulation documentation](https://www.mpt3.org/pmwiki.php/UI/RegulationProblem) constructs the online controller first and then calls `toExplicit()`. Its example adds stage state/input costs. | Freeze solver choice explicitly. Rebuild the requested terminal-only objective rather than copying the documented LQR example unchanged. A finite-horizon feasible domain and an invariant terminal set must retain separate records. |
| MPT3 source inspection | The historical `kvasnica/mpt3` default-branch snapshot inspected through GitHub is [`76d28640251c0403f2c11deac9b0b2d7ee3759d0`](https://github.com/kvasnica/mpt3/tree/76d28640251c0403f2c11deac9b0b2d7ee3759d0), commit dated 2017-10-05. Its [`mpt_init.m`](https://github.com/kvasnica/mpt3/blob/76d28640251c0403f2c11deac9b0b2d7ee3759d0/source/mpt/mpt_init.m) checks MATLAB compatibility and searches installed tools. | This is a pinned source observation, not evidence that it is the current stable distribution. The official installer remains the distribution route described by the project. |
| MPT3 exported evaluation | The [code-generation documentation](https://www.mpt3.org/pmwiki.php/UI/Codegen) distinguishes exporting the full open-loop optimizer from trimming it to the first input; it also describes tie-breaking and sequential/binary region search. | Record whether the measured online product is a full control sequence or only its first action. Offline construction, export, storage, and online location/evaluation have different timing scopes. |
| PPOPT, MIT alternative candidate | The author-group [repository](https://github.com/TAMUparametric/PPOPT) supports multiparametric programs. The inspected `main` revision is [`cdc79a31965dbf7a0139667affa5c52076c9dcae`](https://github.com/TAMUparametric/PPOPT/tree/cdc79a31965dbf7a0139667affa5c52076c9dcae), dated 2025-01-22. Its pinned [`LICENSE`](https://github.com/TAMUparametric/PPOPT/blob/cdc79a31965dbf7a0139667affa5c52076c9dcae/LICENSE) is MIT; [`setup.py`](https://github.com/TAMUparametric/PPOPT/blob/cdc79a31965dbf7a0139667affa5c52076c9dcae/setup.py) declares version 1.6.12 and includes `gurobipy` in required dependencies. Its [`solver.py`](https://github.com/TAMUparametric/PPOPT/blob/cdc79a31965dbf7a0139667affa5c52076c9dcae/src/ppopt/solver.py) supplies Gurobi defaults, with detected GLPK/quadprog replacements for LP/QP. | Promising optional Python comparator, but an MIT top-level license does not make the installed solver stack automatically free of proprietary components. A selected open solver path needs its own dependency/import/coverage audit and explicit configuration before execution. No package was installed here. |

The official MPT3 [geometry documentation](https://www.mpt3.org/pmwiki.php/Geometry/OperationsWithPolyhedra) distinguishes set containment, axis projection, point projection, and Pontryagin difference. Those operations can support comparisons only when the represented sets and quantifier order match. Their availability is not an independent correctness certificate.

## Original exact double-integrator fixture

This derivation is proposed for implementation; it is not copied from either paper's numerical example. Let `x=(p,v)` and use rational data

```text
A = [[1,1],[0,1]], B = [0,1]^T, N = 1
X = { |p| <= 3, |v| <= 2 }, U = [-1,1]
T = { |p+v| <= 1, |p+2v| <= 1 }
J = p1^2 + v1^2
x1 = A x + B u, x in X, x1 in T, u in U.
```

There is no running cost and no disturbance. The terminal set is separately certified invariant under `K=[-1,-2]`. Write `s=p+v` and `t=p+2v`. On `T`, `u=Kx=-t` respects `U`, while the successor has `s1=0` and `t1=-s`. Hence it remains in `T`; also `p=2s-t` and `v=t-s` prove `T` is contained in `X`. The closed-loop matrix is nilpotent of degree two. This establishes invariance for the stated policy; it does not assert that `T` is the maximal controlled invariant subset of `X`.

For the horizon-one program, the admissible input interval is exactly

```text
L(p,v) = max(-1, -1-p-2v, (-1-p-3v)/2)
U(p,v) = min( 1,  1-p-2v, ( 1-p-3v)/2)
F1 = { (p,v) in X : L(p,v) <= U(p,v) }.
```

The scalar control objective is `(p+v)^2+(v+u)^2`, with strictly positive control curvature. Therefore

```text
u*(p,v) = clamp(-v, L(p,v), U(p,v))
V1(p,v) = (p+v)^2 + (v+u*(p,v))^2.
```

This supports an exact polyhedral region construction. Use the free branch `u=-v`, three candidate lower-bound branches, and three candidate upper-bound branches. A lower branch is valid where its bound dominates the other lower bounds, is no larger than every upper bound, and `-v` lies below it; upper branches are symmetric. Each branch is an intersection of rational halfspaces. Empty branches are retained as construction outcomes. These closed regions cover `F1` by the interval trichotomy; overlaps caused by ties give the same input and value. The region producer should still export its actual H-representations so a separate checker can verify this result rather than relying only on this prose.

An exact independent check can construct `F1` directly by eliminating scalar `u` from all joint inequalities, enumerate each bounded 2D polygon's vertices with rational determinants, and check both set inclusions. Verify region overlap laws and scalar KKT conditions symbolically on each region. Finite state samples are then useful diagnostics, not the coverage oracle. The main 2D figure should label `X`, `T`, `F1`, every nonempty control-law region, and any infeasible part of `X`.

## Nonunique optimal histories and CSL scope

Reuse the existing [T-S01 exact profile](../contracts/ts01-exact-analytic-profile.md) for a concrete nonunique case. It fixes `x0=0`, uses a two-step scalar integrator, `u0,u1 in [0,1]`, and terminal cost `(x2-1)^2`. Its complete optimal joint relation is

```text
{ (x0,x1,x2,u0,u1)=(0,s,1,s,1-s) : 0 <= s <= 1 }.
```

A rule choosing `u0=0`, `1/2`, or `1` selects one member but does not encode the full relation. This existing capability is a better nonuniqueness check than introducing a new unreviewed family proof. The double-integrator parametric map must not inherit T-S01/T-S02/T-S03 completeness authority merely because its individual QPs are easy. Compare its analytic relation with the delivered CSL product that is actually available; report an unsupported complete-family request if necessary.

## Evidence required before reporting a comparison

Save offline region and set construction, serialized region/facet counts and storage, online point location/evaluation, and per-initial-state QP/CSL execution separately. For each attempted size/horizon, retain empty feasible domains, singular or unsupported programs, region/precision/resource caps, and solver failures. A cap outcome is not a successful timing sample.

The first pilot can establish exact coverage and objective consistency for the explicit scalar-QP fixture and show the T-S01 selector/family distinction. It cannot establish general multiparametric-QP correctness, MPT3/PPOPT speed, region-growth scalability, a broad Strategy A complete-family capability, or robust winning-set equality. Those remain separate acceptance work. Approximate set variants continue to depend on the shared #99/#100 inclusion infrastructure; this task should consume those records rather than duplicate the approximation implementation.

No disturbance is present in the proposed fixture. Introducing uncertainty requires a new declared predecessor product, such as `exists u, for all w` with whole-successor containment; replacing it by `for all w, exists u` changes the set. This note supplies no continuous robust-control claim.
