# Temporal coupling: preserved theory and algorithm boundaries

Date: 2026-10-11. Status: mathematical design note with self-contained derivations; no new control benchmark or product implementation. Scope: nominal finite-horizon affine discrete dynamics, continuous controls, known initial state.

## Owner decision

Reserve temporal constraints in the problem contract. Do not introduce new cross-step constraints into the first archival reproduction/comparison experiments. Those experiments retain the original stagewise constraints and objective. A future constrained variant must have a separate scenario identity, compatible algorithm and its own evidence.

The derivations below justify specific extensions. They do not establish every historical theorem, implementation, robust game or set representation as automatically compatible.

## 1. What the inspected sources assume

L01, PDF pages 1–4, specifies nonsingular A and compact convex polyhedral initial/control sets, with a separate admissibility condition u_t in P at each stage. Its original setup does not supply a general temporal-constraint operator or intermediate state-constraint treatment.

L11, PDF pages 6–9, specifies affine-free linear discrete dynamics, nonsingular A_t, compact convex stagewise polyhedra X_t and U_t, and a convex terminal objective. Its forward definition enforces the next-state constraint. Its inverse-based backward construction uses A_t^{-1}. These pages do not specify a constraint coupling u_t and u_{t-1}. The phrase about adjacent controls on page 6 defines elapsed discretization time, not a slew bound.

This is a focused assumptions check, not proof of absence of every temporal relation in every archive file. The source variable u also needs a physical interpretation before imposing actuator-rate limits: a command increment and an absolute actuator position are different coordinates.

## 2. Linear temporal constraints preserve the joint convex problem

Let z collect all states x_0,...,x_T and controls u_0,...,u_{T-1}. Assume:

- x_{t+1}=A_t x_t+B_t u_t+a_t, with fixed coefficients and initial state;
- X_t and U_t are closed convex polyhedra;
- extra cross-step constraints have the form Gz<=h and Hz=k;
- the feasible relation is nonempty, and U_t are bounded;
- the terminal objective phi is continuous and convex on the reachable terminal states.

**Derivation.** Dynamics and cross-step equalities define affine sets. All stated inequalities and stage constraints define polyhedra. Their intersection F is therefore a convex closed polyhedron. At finite horizon, bounded controls and fixed initial state imply bounded states by the affine recurrence. Hence F is compact. Continuity implies an attained finite minimum v*. Projection of F onto any selected state/control coordinates is again a convex polyhedron.

For any two optimal feasible points z_1,z_2 and theta in [0,1], their convex combination is feasible and

~~~math
\phi(\theta x_{T,1}+(1-\theta)x_{T,2})
\le \theta v^*+(1-\theta)v^*=v^*.
~~~

The definition of v* supplies the opposite inequality, so the combination is also optimal. Thus the optimal solution family remains convex. A linear objective exposes a polyhedral optimal face. A general convex objective can yield an implicit convex minimizer set; it need not have a polyhedral representation.

These are elementary consequences of convex-set operations and optimization, consistent with [Boyd and Vandenberghe, Convex Optimization](https://web.stanford.edu/~boyd/cvxbook/), chapters 2 and 4. The problem-specific derivation here is our own. No conclusion about computational cost, numerical conditioning or a particular legacy implementation follows from convexity alone. Adding constraints can make the problem infeasible or change its optimum.

## 3. Why physical-state-only propagation can fail

Consider the scalar system x_{t+1}=x_t+u_t, x_0=0, T=2, u_0,u_1 in [-1,1], with the stage constraint x_1=1. Add |u_1-u_0|<=1/4.

The stage constraint forces u_0=1. Therefore u_1 lies in [3/4,1] and the true terminal reachable set is [7/4,2]. A recurrence retaining only R_1={1} and using the independent domain U_1=[-1,1] instead produces [0,2]. It incorrectly admits u=(1,-1), which violates the slew constraint.

For phi(x_2)=x_2^2, the true minimum is 49/16; the uncoupled recurrence falsely permits zero. This counterexample uses continuous actions, nonsingular A=1 and convex polyhedral constraints. The defect is loss of history needed for admissibility, not nonconvexity.

For a direct memory example without the x_1=1 constraint, the feasible prefixes (u_0,u_1)=(1/8,-1/8) and (-1/8,1/8) both reach x_2=0 under the same 1/4 slew bound. Their next-control intervals are [-3/8,1/8] and [-1/8,3/8], respectively. The physical state alone does not distinguish these conditional choices.

More generally, two histories ending at the same physical state can have different admissible next controls. Storing previous-control dependencies or a full joint trajectory relation is necessary when that information affects future choices.

## 4. Exact slew-constraint lifting that preserves nonsingularity

Assume u_t-u_{t-1} in D_t, where D_t is a specified compact convex polyhedron, alongside u_t in U_t. Introduce p_t=u_{t-1}, the increment v_t=u_t-p_t and the augmented state z_t=(x_t,p_t). Then u_t=p_t+v_t and

~~~math
z_{t+1}=
\underbrace{\begin{bmatrix}A_t&B_t\\0&I_m\end{bmatrix}}_{\widehat A_t}z_t+
\underbrace{\begin{bmatrix}B_t\\I_m\end{bmatrix}}_{\widehat B_t}v_t+
\begin{bmatrix}a_t\\0\end{bmatrix}.
~~~

Use the independent input domain v_t in D_t and the next-state constraint

~~~math
z_{t+1}\in X_{t+1}\times U_t.
~~~

The second block of z_{t+1} is p_{t+1}=u_t, so this state constraint enforces the original absolute control bounds. It avoids treating those bounds as an independent unconstrained increment interval. The terminal objective is phi(P_x z_T), where P_x extracts the physical state.

**Forward equivalence.** Given an original admissible trajectory/control sequence and initial previous control p_0, set p_t=u_{t-1} and v_t=u_t-p_t. Substituting gives the augmented dynamics. The slew constraint implies v_t in D_t; state and absolute input bounds imply z_{t+1} in X_{t+1} times U_t. The objective is unchanged.

**Reverse equivalence.** Given an augmented feasible trajectory and increments, recover u_t=p_t+v_t=p_{t+1}. The augmented first block gives the original dynamics. The next-state constraint gives x_{t+1} in X_{t+1} and u_t in U_t. Since p_t=u_{t-1} by induction from p_0, v_t in D_t gives the original slew constraint. These maps are inverse, including all feasible histories, and preserve the objective. They therefore give a bijection of the optimal solution families.

The block-triangular matrix satisfies det(widehat A_t)=det(A_t). Thus nonsingularity is preserved. The new state dimension is n+m; widehat B_t has full column rank because of its identity block. Compact convex polyhedral input and augmented state domains preserve the corresponding mathematical class. The initial previous control must be specified if the rate bound applies at t=0. If it applies only from t=1, choose a fixed bookkeeping p_0 and D_0=U_0-p_0, so the first action receives no new slew restriction.

For nonuniform sampling, distinguish a per-step increment bound from a physical rate bound: the latter scales the allowed increment by elapsed time between commands. Do not silently infer that time or a previous command from missing data.

The same increment-state matrix appears in [do-mpc's documented LQR reformulation](https://www.do-mpc.com/en/latest/_modules/do_mpc/controller/_lqr.html). That implementation concerns an input-rate penalty; it is an independent structural reference, not proof of hard-constraint handling or complete optimal-family recovery. The equivalence proof for hard constraints is the derivation above.

An alternative lift using u_t directly has state matrix diag(A_t,0), which is singular. That alternative cannot be passed unchanged to an inverse-based method. The increment formulation above avoids this particular obstacle, while still requiring stagewise state-constraint support.

## 5. Exact Markov recurrence after the lift

With a known augmented initial state and the increment formulation, the nominal forward recurrence is

~~~math
\widehat R_{t+1}=
\left(\widehat A_t\widehat R_t\oplus\widehat B_t D_t+
\begin{bmatrix}a_t\\0\end{bmatrix}\right)
\cap (X_{t+1}\times U_t).
~~~

This is exact as a set identity: each feasible predecessor and independently admissible increment generates one augmented successor, and the intersection retains exactly those satisfying original state/control bounds. The augmented state contains the memory needed for the next increment constraint. Physical reachable sets are its projections; the optimal joint history relation is still needed for complete solution recovery.

For terminal-only cost, the augmented terminal minimizer set may have many possible previous-control coordinates even when its physical-state projection is unique. Keep all compatible coordinates when recovering histories.

## 6. Algorithm and representation consequences

| Method | Consequence of temporal constraints |
|---|---|
| Joint affine/polyhedral feasibility with convex objective | Linear coupling adds constraints; convexity is preserved. Supported objective class still determines LP/QP/conic/general convex backend |
| Physical-state-only independent-control recurrence | Can overapproximate admissibility; counterexample above. Requires dependency tracking or a valid lift |
| Stage-constrained polyhedral forward/backward strategy | Increment lift preserves linearity/polyhedral constraints and nonsingularity when original A is nonsingular. Audit all algorithm hypotheses and dimension support before claiming legacy compatibility |
| L01 setup without intermediate state constraints | Not automatically covered: the lift encodes absolute control limits in augmented state constraints |
| Pure zonotope affine/Minkowski propagation | Those operations remain exact, but the added intersections need not remain ordinary zonotopes |
| Floating-point implementation | Algebraic equivalence does not guarantee stable conversion, tolerances, performance or certified completeness |

For example, a square [-1,1]^2 intersected with a+b<=0 becomes a triangle. Ordinary zonotopes are centrally symmetric; this triangle is not. Thus an arbitrary linear cross-step constraint on two control coordinates can leave the zonotope class while remaining a convex polytope. Use a compatible polyhedral/CZ representation or an explicitly labeled approximation; a rate-specific special case might retain simpler geometry, but this is not a general guarantee.

The slew lifting proves an exact formulation for one-step control memory. General linear horizon constraints remain representable in the joint relation; they need not admit a fixed-size, cheap memory lift. Nonlinear temporal constraints, discrete modes, disturbances, partial observations and robust quantifiers are outside this proof.

## 7. Contract and experimental policy

- Preserve StageConstraints separately from optional TemporalLinearConstraints, including involved stages/coordinates, units and provenance.
- A MemoryLift adapter records auxiliary state layout, original-to-lifted mappings, initial memory and reconstruction of physical trajectories/controls.
- Algorithms declare stagewise-only, joint-linear or supported memory-lift capability. The first baseline pipeline uses stagewise constraints and rejects unsupported temporal constraints explicitly.
- Baseline manifests do not acquire rate limits or other coupled constraints by default. Future variants use separate IDs and retain their exact original data for comparison.
- Validate the lift and feasible-history correspondence before running a new variant. Review numerical cost and geometry separately from the algebraic proof.

The first experiments therefore stay within the inspected original setting. Reserving a well-defined optional constraint type in the architecture does not change those experiments or assert that every plugin supports it.

## Executed arithmetic characterization

An inline Python fractions.Fraction calculation checked the affine LTV lifting in two stages with nonzero offsets and nonzero initial previous control, recovering the original controls and physical states exactly. An exact rational check also confirmed terminal intervals [7/4,2] versus [0,2] and squared-cost minima 49/16 versus the falsely admitted zero. These checks support the worked algebra/counterexample; they do not replace the general proof or reproduce an archival benchmark.

The following standalone characterization reproduces the executed arithmetic checks; it is not a baseline solver:

~~~python
from fractions import Fraction as Q
import json

def mm(a, v):
    return [sum((q*x for q,x in zip(row,v)), Q(0)) for row in a]

def add(*vectors):
    return [sum(parts, Q(0)) for parts in zip(*vectors)]

models = [
    ([[Q(1),Q(1)],[Q(0),Q(2)]], [Q(1),Q(3)], [Q(1,3),Q(-1,7)]),
    ([[Q(2),Q(0)],[Q(1),Q(1)]], [Q(-2),Q(1)], [Q(-1,2),Q(2,5)])
]
x = [Q(2,3),Q(-4,5)]
p = Q(-1,4)
steps = []
for stage, ((a,b,offset),u) in enumerate(zip(models,[Q(1,5),Q(-1,10)])):
    delta = u-p
    original = add(mm(a,x),[q*u for q in b],offset)
    ahat = [row+[q] for row,q in zip(a,b)] + [[Q(0),Q(0),Q(1)]]
    lifted = add(mm(ahat,x+[p]),[q*delta for q in b+[Q(1)]],offset+[Q(0)])
    assert lifted[:-1] == original and lifted[-1] == u
    assert p+delta == u
    steps.append({'stage':stage,'physical_state':[str(q) for q in original],
                  'recovered_control':str(p+delta),'exact_lift_match':True})
    x,p = original,u
lo,hi = Q(1)-Q(1,4),Q(1)
true_terminal = [Q(1)+lo,Q(1)+hi]
naive_terminal = [Q(0),Q(2)]
assert true_terminal == [Q(7,4),Q(2)]
assert true_terminal[0]**2 == Q(49,16)
assert abs(Q(-1)-Q(1)) > Q(1,4)
print(json.dumps({'arithmetic':'exact rational','affine_ltv_lift_checks':steps,
    'counterexample_true_terminal':[str(q) for q in true_terminal],
    'counterexample_uncoupled_terminal':[str(q) for q in naive_terminal],
    'counterexample_true_squared_cost':str(Q(49,16)),
    'counterexample_uncoupled_false_squared_cost':'0'},indent=2))
~~~
