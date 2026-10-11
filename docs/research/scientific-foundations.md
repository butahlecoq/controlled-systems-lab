# Scientific and algorithmic foundations

Initial reconstruction, 2026-10-11. Local evidence identifiers are defined in [source map](source-map.md). Mathematical formulations below normalize notation; they are not verbatim quotations.

## 1. Scope of the common system class

The shared nucleus is a finite-horizon, constrained, discrete-time linear time-varying controlled system. A useful affine extension is

$$
x_{t+1}=A_t x_t+B_t u_t+E_t w_t+c_t,\qquad t=0,\ldots,T-1,
$$

with state $x_t\in\mathbb R^n$, control $u_t\in\mathbb R^m$, disturbance $w_t\in\mathbb R^p$, initial set $X_0$, admissible states $X_t$, controls $U_t$, disturbance sets $W_t$, and terminal objective $\phi(x_T)$. The archive usually writes $D_t$ for the disturbance matrix; here $E_t$ distinguishes it from a generic matrix symbol. The affine offset is an extension needed for general models and linearization.

Important problem variants:

| Property | Nominal articles | Minimax articles | Proposed extension |
|---|---|---|---|
| Controls | Usually compact convex polytopes | Finite catalogues | Separate continuous, finite, and mixed-integer domains |
| Disturbances | Absent in nominal solve | Bounded convex sets | Add time dependence and temporal correlation explicitly |
| Initial state | Known state or convex initial set | Typically known singleton | Set-valued state estimation |
| Information | Open loop or measured state on replanning | Open loop, then adaptive replanning | Explicit causal policy and observation contracts |
| Objective | Convex terminal criterion | Worst-case convex terminal criterion | Stage costs, epigraphs, risk objectives via capabilities |
| Model | Linear discrete approximation | Linear approximation plus bounded error | Nonlinear adapters with a verified residual bound |

L01/L02 establish the general terminal-control setting. L11 specializes nominal control to fuel management. L04/L09/L10/L13 specialize minimax control. A finite control catalogue is not equivalent to its convex hull for synthesis.

Some historical backward constructions assume nonsingular $A_t$, and some nominal results also assume rank conditions on $B_t$. These are algorithm-specific restrictions; a projection-based predecessor can handle singular $A_t$. Compactness, attainability, and model validity must still be checked.

## 2. Continuous models and discretization

L07 is broader than the fuel application. It combines translational/angular motion, fluid slosh, elastic modes, actuators and measurements. Its pitch example uses a 16-dimensional state. The report presents a descriptor form

$$
E_c(\tau)\dot x=A_c(\tau)x+B_c(\tau)u+G_c(\tau)w,\qquad
y=C_c(\tau)x+\nu.
$$

If $E_c$ is invertible, this reduces to an ordinary LTV differential equation. A genuinely singular differential-algebraic model requires consistency and index handling; support for it is not established by the recovered archive.

For $\dot x=A_c(\tau)x+B_c(\tau)u$ with zero-order-held input on $[\tau_t,\tau_{t+1})$,

$$
A_t=\Phi(\tau_{t+1},\tau_t),\quad
B_t=\int_{\tau_t}^{\tau_{t+1}}\Phi(\tau_{t+1},s)B_c(s)\,ds.
$$

An affine drift has a corresponding integral. Disturbance discretization depends on whether the disturbance is held constant, arbitrary bounded, or parameterized over the interval. Integrating a constant disturbance channel cannot silently represent every time-varying disturbance.

L07, PDF pp. 30–41, derives state-transition integration and a vectorized reverse integration using Kronecker structure. The reported ode45 tolerances are numerical settings, not a rigorous integration enclosure.

For nonlinear $x^+=f_t(x,u)$, linearization around $(\bar x_t,\bar u_t)$ is

$$
x^+=A_t x+B_t u+c_t+r_t(x,u),\quad
c_t=f_t(\bar x_t,\bar u_t)-A_t\bar x_t-B_t\bar u_t.
$$

Equivalently, deviation coordinates eliminate $c_t$ when the reference satisfies the dynamics. State which convention is used. A guarantee for the nonlinear plant requires a justified bound on $r_t$ over the relevant state/control region. Agreement of a few trajectories does not provide that bound. L05 uses reference-trajectory linearization but does not supply a universally certified residual enclosure for its examples.

## 3. Set representations and operations

For a polytope, vertex and half-space forms are

$$
P=\operatorname{conv}\{v_1,\ldots,v_k\},\qquad
P=\{x:Hx\le h,\;Fx=g\}.
$$

Equalities are essential for singletons and lower-dimensional polytopes. Ambient dimension and affine dimension differ. Empty sets, degenerate sets, and unbounded polyhedra must have explicit representations.

Core operations are affine maps, Minkowski sums, intersections, projections, containment, support queries, Pontryagin differences, redundancy elimination, and representation conversion.

$$
P\oplus Q=\{p+q:p\in P,q\in Q\},\qquad
P\ominus Q=\{z:z+Q\subseteq P\}.
$$

A vertex Minkowski construction generates up to $|V_P||V_Q|$ candidates before redundancy reduction. H/V conversion can dominate runtime; a compact input does not imply a small output.

The support function $h_P(d)=\sup_{x\in P}d^\top x$ permits lazy operations:

$$
h_{AP+c}(d)=h_P(A^\top d)+d^\top c,\qquad
h_{P\oplus Q}(d)=h_P(d)+h_Q(d).
$$

Intersection and projection require their own supported procedures; support values in finitely many directions generally yield an approximation, not a complete exact polytope.

A zonotope is $Z=\{c+G\xi:\|\xi\|_\infty\le1\}$. A constrained zonotope adds $F\xi=g$. Matrix zonotopes represent bounded uncertain matrices rather than uncertain state vectors. These are candidate alternatives to repeated vertex enumeration; they do not make every set operation exact or cheap. See [recent research](recent-research.md).

L03/L05/L07 describe modified candidate ordering and redundancy procedures. L05's modified numerical sets have different volumes from the baseline sets: do not treat all modifications as semantics-preserving acceleration without a proof.

## 4. Nominal reachable sets

For continuous convex controls and no disturbance, the forward recurrence is

$$
R_0=X_0\cap X_0^{\rm admissible},\qquad
R_{t+1}=(A_tR_t\oplus B_tU_t\oplus\{c_t\})\cap X_{t+1}.
$$

Here every point has an admissible history under existential choices. For finite controls,

$$
R_{t+1}=
\bigcup_{u\in U_t}\big((A_tR_t+\{B_tu+c_t\})\cap X_{t+1}\big).
$$

This union can be nonconvex. Replacing it by a convex hull relaxes the control problem and can manufacture terminal states unreachable with the discrete actuator.

The nominal predecessor of a target $S$ is

$$
\operatorname{Pre}_{\exists}(S)=
\{x\in X_t:\exists u\in U_t,\ A_tx+B_tu+c_t\in S\}.
$$

It can be formed as a projection of joint $(x,u)$ constraints. The inverse-image formula used in historical algorithms is available when its invertibility assumptions hold.

For a terminal target set $S_T$, construct $S_t=\operatorname{Pre}_{\exists}(S_{t+1})$. Intersecting forward reachable and backward controllable sets identifies states on admissible target-reaching paths. A trajectory still requires selecting controls jointly consistent with adjacent states. Independently selected per-step control lists are not a trajectory certificate.

## 5. Nominal terminal optimization

Solve $\min_{x\in R_T}\phi(x)$, then recover one or more control trajectories reaching a minimizing terminal state. L01/L02/L11/L14 supply this forward-optimize-backward-recover pattern.

A linear $\phi$ gives an LP. A convex quadratic gives a QP; a weighted norm can be represented as an SOCP epigraph. When $\phi(x)=\|L(x-x_d)\|_2$, minimizing its square preserves minimizers, but the reported objective remains the norm.

A direct sparse horizon optimization is an alternative:

$$
\min_{x_{0:T},u_{0:T-1}}\phi(x_T)
\quad\text{subject to dynamics and all state/control constraints}.
$$

It may avoid constructing the entire reachable polytope. It answers a different output request from “compute the full reachable set,” so benchmarks must distinguish them.

Multiple minimizing terminal states and multiple realizing trajectories must be allowed. A solver returning one optimizer does not establish an exhaustive description of every optimal control. Strict convexity, when applicable, establishes uniqueness of terminal state, not necessarily uniqueness of the control history.

## 6. Fixed-plan robust reachability and minimax

Fix an open-loop sequence $u_{0:T-1}$ selected before disturbances. For stagewise independent bounded disturbances,

$$
R_0^u=X_0,\qquad
R_{t+1}^u=A_tR_t^u\oplus\{B_tu_t+c_t\}\oplus E_tW_t.
$$

Robust feasibility requires $R_t^u\subseteq X_t$ for every constrained time. Intersecting with $X_t$ would discard violating disturbances and could falsely certify the plan. L10/L13 explicitly reject a plan when its generalized reachable set violates the phase constraints.

The fixed-plan cost is

$$
J(u)=\max_{x\in R_T^u}\phi(x),\qquad
J^\star=\min_{\text{robustly feasible }u}J(u).
$$

With a finite catalogue of $q$ actions and $T$ steps, exhaustive search has $q^T$ plans. L04 uses $5^4=625$; L09/L10 use $5^5=3125$; L13 uses $9^4=6561$ at the initial solve. This distinction matters for runtime comparisons.

A convex function on a compact polytope attains a maximum at at least one extreme point. With a complete exact vertex list, checking all vertices is therefore a valid worst-case oracle. Maximizing a convex function over a polytope is generally not a convex minimization problem. Negating the function and calling a local optimizer does not certify a global maximum.

~~~text
best = none
for each finite control plan:
    propagate its full disturbance reachable sets
    if any set fails robust containment: reject the plan
    otherwise compute a globally justified worst-case terminal cost
    update the incumbent, retaining ties according to a stated tolerance
return best plan(s), status, objective bound, feasibility evidence
~~~

Prefix reuse and early infeasibility pruning avoid redundant propagation. Branch-and-bound requires a valid lower bound on the best completion of each prefix; an arbitrary heuristic score is insufficient for safe pruning.

## 7. Robust feedback and information patterns

For control chosen before the disturbance at each step,

$$
\operatorname{Pre}_{\exists\forall}(S)=
\{x\in X_t:\exists u\in U_t,\ \forall w\in W_t,\ A_tx+B_tu+E_tw+c_t\in S\}.
$$

For independent additive $W_t$, this is equivalent to requiring $A_tx+B_tu+c_t\in S\ominus E_tW_t$. Quantifier order is part of the problem; $\forall w\,\exists u$ permits disturbance-dependent action and describes a different information pattern.

A full-state feedback minimax value satisfies the Bellman form

$$
V_t(x)=\min_{u\in U_t}\max_{w\in W_t}
V_{t+1}(A_tx+B_tu+E_tw+c_t),\qquad V_T=\phi,
$$

with admissibility encoded in the recursion. An open-loop sequence, a causal feedback policy, a disturbance-feedback policy, and a finite scenario tree are different policy classes.

L08/L13 use “adaptive” for shrinking-horizon replanning from measured state:

~~~text
observe the current state
solve an open-loop terminal problem over the remaining horizon
apply only the first action
advance the plant and observe again
repeat until the terminal time
~~~

This is closely related to receding-horizon control. It does not by itself identify model parameters. Nor does repeated open-loop minimax solving establish equality to the globally optimal feedback dynamic game. Any such claim requires the precise theorem and assumptions.

With output measurements $y=C_tx+\nu$, replace the known state by an estimate or consistent state set. Do not plug a noisy measurement directly into a full-state guarantee.

## 8. Fuel-management adapter

In L11/L13, the state interleaves oxidizer/fuel flow rates and remaining masses:

$$
x=(\dot m_o,M_o,\dot m_f,M_f)^\top,\qquad
M_{i,t+1}=M_{i,t}-\Delta\tau_t\,\dot m_{i,t}.
$$

For this approximation, the mass diagonal entries in $A_t$ must equal one. L28's uniform-grid branch does not satisfy this identity; the characterization is in [audit](legacy-audit.md).

The scalar action is a throttle-mixture adjustment; finite catalogues and continuous admissible intervals occur in different papers. The terminal objective may combine flow deviations, remaining masses, and synchronization of the two components. Preserve each paper's exact weights and units.

Some reported residual masses are negative. L04 explicitly interprets this as use of reserved propellant relative to a working-stock reference. A real application must define whether the coordinate is total physical mass, deviation, or working-stock balance. Nonnegativity constraints cannot be silently added to a historical reproduction or silently omitted from a physical deployment.

## 9. Required guarantee vocabulary

Every result should specify the model, policy class, uncertainty semantics, and numerical evidence.

| Category | What can be claimed |
|---|---|
| Exact mathematical construction | The stated set identity or optimum under stated assumptions; floating implementation still needs numerical qualification |
| Exact arithmetic computation | Rational/symbolic result for supported rational data and operations |
| Validated enclosure | Proven inclusion with numerical rounding/integration error accounted for |
| Floating-point numerical result | Residuals and solver status meet reported tolerances; not automatically a formal enclosure |
| Sampled or statistical result | Empirical coverage or probability/confidence under stated sampling assumptions |
| Heuristic approximation | Useful candidate without the missing inclusion/global-optimality proof |

Inner/outer approximations must state the reference set and inclusion direction. Volume alone does not prove containment. Safety certification needs an outer enclosure of all possible future states contained in the safe set, or a sound inner approximation of a robust controllable set with a realizing policy. An outer controllable approximation can contain falsely feasible initial states.

## 10. Extension priorities

Preserve the archived exact low-dimensional methods as a reproducible baseline. Add support-function and constrained-zonotope backends; compare direct structured optimization with full-set construction; introduce explicit feedback policy interfaces; then investigate estimation and data-driven model sets.

Nonlinear, hybrid, chance-constrained, descriptor, and learned-model methods should be optional capabilities with separate assumptions. Generality means clear extension contracts, not one solver promising all these cases.
