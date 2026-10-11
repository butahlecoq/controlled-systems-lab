# Original issue #5: adaptive minimax policy and proof audit

2026-10-11. Curated authored evidence for [original issue #5](https://github.com/butahlecoq/controlled-systems-lab/issues/5), delivered by [curation issue #109](https://github.com/butahlecoq/controlled-systems-lab/issues/109). The initial independent review and scoped amendment recheck are complete; original issue #5 remains open.

## Disposition

L02 is a **nominal deterministic** optimal-control article. Its Theorem 4.3 cannot be imported as a minimax feedback theorem. L04, L09 and L10 optimize **fixed control sequences** against a full disturbance sequence. L13 Eq. (18) and Algorithm 3 prescribe **remaining-horizon fixed-plan minimax first-action selection followed by observation and replanning**. They do not contain an optimization over all causal policies. The independently proved relationship, under the hypotheses below, is

$$
V_t^{\rm causal}(x)\leq J_t^{\rm replan}(x)\leq J_t^{\rm fixed}(x).
$$

The second inequality supports L13's stated 'no worse than program control' claim for the exact discrete model, robust admissibility and exact solves. The first inequality may be strict: the explicit linear two-step example below gives causal value 1 and replanning value sqrt(2). Therefore identifying L13's procedure with globally optimal causal feedback is false under the general linear/finite-action/compact-disturbance/convex-terminal-cost assumptions alone. This example does not assert that the particular published rocket numerical example has a strict gap.

L13 Eq. (20) evaluates a last-stage minimax value at a state reached under an earlier disturbance history. Calling that single history-conditioned value an initial guaranteed minimax result does not supply the missing supremum over earlier histories. Algorithm 3's nonlinear simulation or sensor update also requires a model-error/information bridge before a theorem for the linear surrogate can guarantee the physical nonlinear plant. Issue #5 remains open for implementation-level contracts and source-specific remaining obligations listed below.

## Source authority and review disposition

The [provenance record](proof-audit-provenance.json) identifies original-byte hashes, separate navigation-extract hashes, source anchors and the ordered private authored-version/review chain. The final antecedent digest does not identify this curated report's bytes. Original files and extracts remain local-only. Pages below are one-based PDF pages; A08/A09 anchors refer to original source line numbers. This delivery curates the prior reviewed source checks without executing historical programs or reopening a theorem audit.

| Source ID | Original relative filename | SHA-256 |
|---|---|---|
| L02 | `papers/1997 Алгоритм решения задачи оптимального терминального управления в ЛДДС.pdf` | `cb2fe68b9fc3321f8009cb0b1a444aaceb9b614f9a94e1af671711b38d58c300` |
| L04 | `papers/Shorikov_Kalev_AиT_New.pdf` | `6e07c9a2fac2d112885a495c9fe7f13acec9d990d947017b1701a4b95538cd5f` |
| L09 | `papers/Шориков АФ, Калев ВИ статья в Косм. иссл..pdf` | `bb32b230e600fd0871322768dbf42d181fa7a0a288b97c717659a6448e3b72aa` |
| L10 | `papers/Шориков, Калев, статья.pdf` | `146ec36e96be4c779158541420eac1e242825262b5981d47b61ba86a9e2126a8` |
| L13 | `papers/Электронная версия_статьи.pdf` | `4556046bb893a9a7a8c7b8489673dc95315d8ea49bf37e787a59d897c8a7a70e` |
| A08 | `Публикации/Минимакс/Adaptive_Samara/Minmaxclosedloop.m` | `06c2f750a2c7deb01dbc457185378b440f8ba134216d7ab0762b8b28229ba2d9` |
| A09 | Same directory, `Minmaxopenloop.m` | `59daeacc7727cb7ff5e0090368d76e401fa4d0c874ef359a97d6acb722467aa6` |

### Reviewed corrections

- **R5-C1:** The predecessor closedness and ordered feasibility-selector proof now requires closed safe/target sets, a fixed finite action catalog, fixed nonempty compact disturbances and continuous transition. General state-dependent domains and value-minimizing selectors retain separate obligations.
- **R5-C2:** The reviewer withdrew the claimed L09 quantifier inconsistency after inspecting the registered source again. L09 PDF p.7 Eq.(3.2) prints distinct `min_u max_w` operators. This was a reviewer's misreading, **not a historical erratum**. The author, controller and reviewer checked the same registered original hash; the original review is retained privately with its withdrawal disposition.

The initial review requested two medium corrections. The author fixed R5-C1 and disputed R5-C2 using the owning source. The reviewer withdrew R5-C2, then the scoped recheck passed the amended paragraphs with no outstanding item. That recheck did not audit unchanged proofs or implementation dependencies again. Full version digests and gate scopes are in the provenance record.

L13 cites Shorikov's 1997, 242-page monograph as reference [4], but gives no owning theorem/page for its adaptive assertion. The prior bounded search found bibliographic metadata, not an inspected theorem. The monograph proof remains unaudited; this is not an archive-wide absence claim. A different-title dissertation is not a substitute for that monograph.

## Notation

The [glossary](glossary.md) convention is $X_t$ for admissible states, $R_t$ for reachable sets, $S_t$ for target/predecessor sets, $U_t$ for controls, $W_t$ for disturbance domains and $E_t$ for the disturbance channel. The antecedent's disturbance $v$/$V_t$/$D_t$ becomes $w$/$W_t$/$E_t$ below; its winning set $K$ becomes $S$. The fixed-plan value is $J_t^{\rm fixed}$, the executed replanning value $J_t^{\rm replan}$, and the unrestricted causal value $V_t^{\rm causal}$. Historical equation descriptions retain their source-specific notation.

## Source-by-source theorem and policy matrix

| Source and owning anchors | Policy/quantifiers actually defined | Information, assumptions and attainment | Supported result and limitation |
|---|---|---|---|
| **L02**, pp.4-5 Eqs.(2.1)-(2.2); pp.8-9 Eqs.(3.3)-(3.4); p.10 Eqs.(3.5)-(3.6); pp.17-18 Theorem 4.2; pp.19-20 Eqs.(4.11)-(4.14), Theorem 4.3 | Nominal `x[t+1]=A[t]x[t]+B[t]u[t]`, with no disturbance variable. Program problem minimizes a linear terminal functional over a control sequence. Adaptive strategy is a set-valued map from time/state to permitted actions. Eq.(3.6) is `min_strategy min_terminal-in-its-bundle gamma`, not `min_strategy max_disturbance` and not worst selection within the bundle. | All A[t] nonsingular; rank B[t]=p<=n; U1 nonempty compact convex polytope, same at every stage. Known model; initial state and realized control history measured/remembered (p.5). The current state is exactly reconstructible from this nominal history. No observation noise, estimator uncertainty or adversary appears. Finite-horizon control product compact, trajectory affine, linear cost continuous; minimum attained. Linear minimizer face of a reachable polytope supports the terminal-set construction. | Theorem 4.2 characterizes optimal sequences through forward/backward reachable intersections and a terminal minimizing face. Theorem 4.3 constructs first actions of remaining-horizon optimal sequences along nominal optimal paths, with U1 elsewhere. Nominal suffix replacement preserves the optimum, as proved below. It supplies no robust game theorem. The general 'any realization' statement in Eq.(3.7) is stronger than the bundle-minimum definition justifies. |
| **L04**, pp.6-7 Eqs.(10)-(15), assumptions 1-2; p.8 Eq.(17); pp.9-11 Eq.(18), Eq.(21), algorithm steps 1-5 | `min_{u sequence} max_{w sequence} norm(x[T]-xd)`; finite program catalog. Generalized reachable set is for a **fixed** program and all stagewise disturbances. No causal policy optimization or adaptive update rule in this formulation. | Known x0 and surrogate model; finite U1[t]; W1[t] described as a polyhedron ('многогранник'). This local assumption does not explicitly spell out nonempty/closed/bounded as L09/L10 do. For finite attained maxima, require nonempty compact W1[t]; convexity follows for convex polyhedral operands. Norm continuous and convex. No full-state feedback measurement hypothesis is needed to apply the fixed plan. | Exact fixed-plan reachable propagation plus an exact global maximum and finite minimum solves the fixed-plan problem. A claim based merely on a local optimizer is weaker. L04's 'adaptive' keyword is not a theorem changing Eq.(17)'s quantifier order. This variant has no stagewise X1 restriction in Eqs.(10)-(14); do not import L10/L13 restrictions. |
| **L09**, pp.5-6 Eqs.(2.6)-(2.11), Assumption 1; pp.6-7 minimization prose, Eqs.(3.1)-(3.2); pp.8-10 Eq.(4.1), algorithm step 4/Eq.(4.3), final finite minimum | Fixed finite program sequences: the registered PDF p.7 Eq.(3.2) visibly prints `min_{u(.) in U(0,T)} max_{w(.) in W(0,T)} Phi(x0,u(.),w(.))`, consistent with the preceding minimization prose and p.10 final algorithm minimum. No map u_t=pi_t(observations) is optimized. | U1[t] finite; W1[t] explicitly convex closed bounded polyhedra with finitely many vertices. Need nonemptiness for a nonempty game. Norm continuous convex; finite nonempty program catalog and compact disturbance product give attained maxima/minimum. Model x0 known; no feedback sensor/noise model. | Same conditional fixed-plan theorem as L04, under clearer disturbance compactness. Article's maximal norm is a global maximization requirement. This source's constraints (2.7)-(2.10) do not include L10's stagewise X1[t]. The single-maximum review claim was withdrawn; see R5-C2 above. |
| **L10**, pp.5-6 Eqs.(6)-(12), Condition 1; p.7 Eq.(14); p.9 algorithm steps 2-5/Eq.(18); p.10 step 6 | Fixed finite programs; max over V(0,T)=product V1[t]. The operational admissible catalog is filtered by rejecting a whole fixed plan if a reachable set violates a phase constraint at **at least one** time. | X1[t] and V1[t] explicitly convex closed bounded polyhedra with finitely many vertices. Finite U1[t]; known x0. Whole reachable sets at every stage must lie inside X1[t]. An empty surviving catalog means no fixed-plan solution; finiteness alone does not guarantee robust feasibility. No measurement model or adaptive theorem. | Exhaustive filtered enumeration plus exact global maxima solves the **robustly feasible fixed-plan** problem. The p.9 reference to phase restriction '(8)' is a printed numbering inconsistency: X1 is Eq.(7), while Eq.(8) is the action restriction. Preserve the printed reference while identifying the actual phase operand. |
| **L13**, pp.4-6 Eqs.(10)-(17); p.7 Eqs.(18)-(19); p.8 Eq.(20), Task 2; pp.9-10 Algorithms 1-3 | Eq.(17): remaining-horizon `min_fixed-plan max_disturbance`. Eq.(18): admissible adaptive actions are the projection of this optimal-program set onto its first action. Eq.(19): full U1[t] assigned outside W[t]. Algorithm 3 step 4 chooses **any** action in Eq.(18), then observes/recomputes. Task 2 asks for this specifically defined rule, not an explicit `inf_pi sup_w` game optimization. | Full t-position (time and four-state x[t]) explicitly available before u[t] (p.6, text after Eq.(17)); v[t] acts during the transition, next position obtained afterward. U1[t] finite; X1[t], V1[t] called polyhedra. For exact robust theorem impose nonempty compact V1[t], nonempty exact robustly feasible remaining program set at every reached state, continuous terminal norm, rectangular disturbance sequence set, exact state/model/solves. Eq.(18)'s set-valued mapping must have nonempty values to choose an action. | Proved here: arbitrary exact first-action selectors of robust optimal fixed plans have worst-case cost <= initial optimal fixed-plan value. Not proved by the article: equality with globally optimal causal feedback. Eq.(20) fixes the reached penultimate state and optimizes only the last stage; earlier histories still matter. Algorithm 3 step 5 uses the original nonlinear system or sensors, so the exact surrogate-model proof does not automatically transfer to that update. |

The L13 state contains oxidizer flow, oxidizer mass, fuel flow and fuel mass (four quantities). Algorithm 3 step 5 mentions processing level and flowmeter sensors, but neither gives a measurement equation/noise set nor proves exact recovery of those four quantities or their correspondence to surrogate coordinates. Thus 'full position is the mathematical input' is established; 'a physical sensor implementation supplies an exact full position at every decision time' is not.

## Exact mathematical statements and independent proofs

### Fixed-plan minimax

Let `f_t(x,u,w)=A_t x+B_t u+E_t w+c_t`, terminal cost phi continuous, and W_t nonempty compact. Assume rectangular stagewise uncertainty: any sequence with w_t in W_t is allowed, with no hidden temporal constraint. A fixed plan p=(u_t,...,u_{T-1}) is chosen before all its future disturbances. Define its uncut reachable sets

$$
R_t=\{x\},\qquad R_{s+1}=A_sR_s\oplus\{B_sp_s+c_s\}\oplus E_s W_s.
$$

Its robust admissibility means `R_s subset X_s` at **every** required state-constraint stage and p_s in U_s. Let P_t(x) be the catalog of such admissible plans. With a finite nonempty catalog,

$$
J_t^{\rm fixed}(x)=\min_{p\in P_t(x)}\max_{w_{t:T-1}\in\prod_s W_s}\phi(x_T(p,w))
$$

is attained. Compactness gives the inner maximum; finiteness gives the outer minimum. For a fixed plan and complete compact polytope terminal set, convex phi satisfies `max_R phi = max_{z in vertices(R)} phi(z)`: express any point as a convex combination of vertices and apply convexity. This independently justifies complete vertex enumeration for fixed-plan norms. It does **not** turn maximizing a convex function into a standard convex minimization, nor establish the globality of a local nonlinear solve.

### Nominal suffix theorem, and the limitation in L02 Eq.(3.7)

Set W_t={0} and remove uncertainty. Every feasible deterministic causal policy realization produces a feasible control sequence, so no policy realization can improve the global sequence minimum. Conversely a fixed optimal sequence is a causal policy. At a current state take the first action of any remaining-horizon minimizing sequence. If its successor had a suffix with strictly lower terminal cost, substituting that suffix would contradict the original sequence's optimality. Thus the successor's minimum equals the current minimum. Induction proves that repeated exact optimal first-action selection reaches the original optimal value. This supplies the nominal principle underlying L02 Theorem 4.3 without importing a disturbance theorem.

However, L02 Eq.(3.6) minimizes **over trajectories inside a set-valued policy bundle**. Under this definition a policy allowing both good and bad branches can be optimal. The p.11 Eq.(3.7) claim for any realization of any strategy optimal under Eq.(3.6) is false as written: T=1, x0=0, A=B=1, U1=[-1,1], gamma(x1)=x1. The policy allowing every u in [-1,1] has bundle minimum -1, hence is optimal by Eq.(3.6), yet the allowed realization u=1 has cost +1, not <= -1. All local rank/compactness/linearity assumptions hold. The first-action-optimal construction restricts choices to u=-1 in this example and avoids this defect; it is essential to distinguish that constructed strategy from the larger set of bundle-minimum optimal strategies. Under the nominal problem, global program and best attainable policy-bundle minima are equal, not a source of strict feedback improvement.

### Replanning guarantee

Define H_t(x) as first actions of all minimizers in P_t(x). Choose a deterministic causal selector h_t(x) in H_t(x) and repeat until T. Assume every propagation and solve is exact and constraints are enforced by whole-set containment. Let p* be a minimizing plan whose first action is h_t(x). For **each** possible current disturbance w_t, the remaining suffix of p* is robustly admissible from y=f_t(x,h_t(x),w_t): all its future trajectories were already trajectories of the original robustly admissible plan. Therefore

$$
J_{t+1}^{\rm fixed}(y)\leq\max_{w_{t+1:T-1}}\phi(x_T(y,p^*_{t+1:T-1},w))\leq J_t^{\rm fixed}(x).
$$

In particular P_{t+1}(y) is nonempty, so recursive feasibility is preserved. With $J_T^{\rm fixed}=\phi$, pathwise induction yields $\phi(x_T)\leq J_t^{\rm fixed}(x)$, and taking the supremum over all disturbance histories yields $J_t^h(x)\leq J_t^{\rm fixed}(x)$. The proof holds for every first-action tie selector, including history-dependent tie resolution, provided each selected action belongs to H_t at the actual current state.

This proves an upper guarantee relative to the fixed-plan value. It does not prove h minimizes J over all causal policies, or even select the best policy among all H-constrained tie selectors. Model mismatch, insufficient observations, approximate global solves or clipping invalidate the premises; those cases need their own residual/information analysis.

### Causal-game value and strict counterexample

For full exact state observed before each control, the deterministic causal policy class is `u_t=pi_t(x_0,...,x_t,u_0,...,u_{t-1})`; no dependence on current or future unobserved disturbance is allowed. Against each fixed deterministic policy every admissible disturbance trajectory is included in the supremum. With rectangular uncertainty, an adversary adapting to the state/action yields the same worst value: each resulting trajectory is in the same product set. For this finite perfect-information horizon, Markov selectors suffice when the current state contains all relevant memory and minima/selectors exist. The Bellman value is

$$
V_T(x)=\phi(x),\qquad
V_t(x)=\min_{u\in U_t(x)}\sup_{w\in W_t(x,u)}V_{t+1}(f_t(x,u,w)),
$$

with unsafe successors given +infinity. Nested order is `min_u0 sup_w0 min_u1(observed x1) sup_w1 ...`, versus `min_(u0,u1,...) sup_(w0,w1,...)` for a fixed plan. This is not a saddle-point interchange; neither convexity of the terminal norm nor compact polytopes authorizes swapping these operators. A causal policy that can observe w_t **before** choosing u_t would instead have `sup_w min_u`, a different problem.

Here is a constant-matrix example with nonsingular A, rank-one B, compact convex stagewise disturbances, finite actions and a Euclidean terminal cost:

$$
T=2,\quad x_0=(0,0),\quad
A=\begin{pmatrix}1&0\\1&1\end{pmatrix},\quad
B=\binom10,\quad E=\binom1{-1},\quad
U_0=\{0,1\},\quad U_1=\{-1,1\},\quad
W_0=[-1,1],\quad W_1=\{0\},\quad \phi(x_2)=\|x_2\|_2.
$$

Controls precede disturbances. Use safe boxes X0=X1=X2=[-4,4]^2; they contain every listed transition and introduce no hidden infeasibility. Direct substitution gives

$$
x_1=(u_0+w_0,-w_0),\qquad x_2=(u_0+w_0+u_1,u_0).
$$

| Fixed (u0,u1) | Worst terminal norm over w0 in [-1,1] |
|---|---|
| (0,-1) or (0,+1) | 2 |
| (1,-1) | sqrt(2) |
| (1,+1) | sqrt(10) |

Consequently the unique initial fixed-plan optimum is (1,-1), its first-action projection is H0={(1)}, and its initial fixed-plan value $J_0^{\rm fixed}$ is $\sqrt{2}$. This is the initial solve, not yet an evaluation of the executed replanning policy. After its first action u0=1 and observed state x1=(1+w0,-w0), the last-stage reoptimization compares

$$
\phi(x_2\mid u_1=-1)=\sqrt{w_0^2+1},\qquad
\phi(x_2\mid u_1=+1)=\sqrt{(w_0+2)^2+1}.
$$

Their squared-cost difference is 4(w0+1)>=0. Thus H1={-1} for w0>-1 and H1={-1,+1} at w0=-1. Execute any of those selectors. The adversary can choose w0=+1 after the root control: the observed x1 is (2,-1), reoptimization uniquely chooses u1=-1, w1=0, and the actual x2 is (1,1), giving cost sqrt(2). For every other w0 the selected last-stage cost is sqrt(w0^2+1)<=sqrt(2); at w0=-1 either tie action yields x2=(+/-1,1) and the same sqrt(2). These literal calculations prove that the **executed whole-horizon replanning policy** has worst-case value J0=sqrt(2), independently of merely reading its initial fixed-plan value.

An unrestricted causal controller instead chooses u0=0. After observing x1=(w0,-w0), choose u1=-1 for w0>=0 and +1 for w0<0. Its terminal norm is `1-|w0|`, whose worst value is 1 at w0=0. Any causal policy beginning with u0=0 has cost at least 1 at w0=0, since only u1=+/-1 are allowed. Any beginning with u0=1 has cost at least sqrt(2) at w0=1. Thus the global causal optimum is exactly 1, strictly below the executed replanning value sqrt(2).

The example has nonsingular constant A (determinant 1), scalar finite controls, rank-one constant B, constant E, convex compact state boxes and convex compact disturbance sets, with a continuous convex Euclidean terminal norm. To match L13's 4-state/2-disturbance dimensions, append two zero state coordinates, use A4=diag(A,I2), B4=(1,0,0,0), and E4 with first column (1,-1,0,0) and second column zero; use W0=[-1,1] x {0}, W1={(0,0)}, X_t=[-4,4]^4 and desired terminal state zero. All calculations and values are unchanged. It matches these structural minimax hypotheses, including degenerately lower-dimensional compact polytopes; it does not match the specific rocket coefficients or prove a gap for that benchmark. L02 instead assumes convex continuous U1 with no disturbance; this finite-action minimax counterexample is not offered as a counterexample to its constructed nominal Theorem 4.3.

This also exposes the Eq.(20) issue: after the replanning first action, the last-stage optimum is sqrt(1+w0^2), which varies from 1 to sqrt(2) with the earlier disturbance. A last-stage maximizer at w1=0 does not maximize over w0. An initial guarantee must take the supremum over the **whole** disturbance history and policy's state-dependent responses.

Finally, the causal continuation function need not be convex even though phi is convex. In the u0=0 branch above, the last-stage optimized norm `min{|w0-1|,|w0+1|}` equals zero at both disturbance vertices and one at the interior w0=0. Checking only disturbance vertices in a causal Bellman maximum would miss the worst case. The complete-vertex reduction proved for a fixed affine plan cannot be reused without proof for the optimized feedback continuation.

## Robust predecessor and supported feedback operands

For a full-state control-before-disturbance system, define the winning relation and predecessor using an explicit current safe set X_t, admissible action set U_t(x), disturbance set W_t(x,u), transition f_t, and future winning set S:

$$
Q_t(S)=\{(x,u):x\in X_t,\ u\in U_t(x),\ \forall w\in W_t(x,u),\ f_t(x,u,w)\in S\},
\qquad \operatorname{Pre}_t(S)=\{x:\exists u,\ (x,u)\in Q_t(S)\}.
$$

Equivalently the entire successor uncertainty set F_t(x,u)={f_t(x,u,w):w in W_t(x,u)} must satisfy `F_t(x,u) subset S`. For affine independent additive uncertainty it is `{A_t x+B_t u+c_t} (+) E_t W_t`, a translated uncertainty image, not a joint union over every candidate u. A particular u must work for every current w; different actions chosen after seeing that same w are not permitted. Define S_T=X_T intersect G and S_t=X_t intersect Pre_t(S_{t+1}); selectors from Q_t(S_{t+1}) prove robust safety/terminal arrival by induction. Conversely a causal policy ensuring arrival from x must have a first action whose every successor admits a winning suffix, so x is in this predecessor. This supplies the exact feasibility recursion and policy witness, independently of fixed-plan reachable intersection constructions.

The **supported sufficient closedness and feasibility-selector contract** here is narrower than the preceding general definition: X_t and S are closed subsets of Euclidean state space; U_t(x)=C_t={a_1,...,a_m} is a fixed ordered finite action catalog, independent of x; W_t(x,u)=W_t is a fixed nonempty compact disturbance set, independent of x and u; and f_t is continuous on the state/action/disturbance domain. Define

$$
P_i=X_t\cap\bigcap_{w\in W_t}\{x:f_t(x,a_i,w)\in S\}.
$$

For each fixed w, continuity and closed S make the set in braces closed. Its arbitrary intersection with closed X_t is closed, so every P_i is closed and `Pre_t(S)=union_{i=1}^m P_i` is a finite union of closed sets. These facts establish Borel feasible-state fibers, rather than presuming them from ambient Borelness. On Pre_t(S), the first feasible action selector has fiber `P_i minus union_{j<i} P_j`, a Borel set, and hence is Borel measurable for the finite action codomain. An empty predecessor has no selector obligation. Compactness and nonemptiness of W_t belong to the supported contract; compactness is not needed for this particular closed-set-intersection argument.

This theorem does **not** extend here to general state-dependent U_t(x), W_t(x,u). Nonempty compact disturbance values alone are insufficient. The reviewer's example has X=R, U={0}, f(x,0,w)=w, S={0}, W(x)={0} for x!=0 and W(0)=[0,1]. Every disturbance value is nonempty compact convex and f is continuous, but the feasible-state set is R minus {0}, which is not closed. Any future state-dependent extension must independently establish the required closedness/Borel properties of its feasible fibers and admissibility/uncertainty mappings before a measurable selector is claimed.

For a **value-minimization** claim, separately require finite/supported values, well-defined suprema, attained action minima and a measurable minimizing selector; the safety-feasibility selector proof does not establish those value-selector properties. Finite action catalogs give attained minima among finitely many finite suprema; compactness plus continuity of the function being maximized gives an attained maximum. A finite action minimum can destroy convexity or continuity properties needed by a later vertex or optimizer shortcut; these must be proved separately rather than presumed from phi.

For uncertain observations y_t, replace x with the information set I_t consistent with the initial set, known chosen controls and all observations/noise bounds. One action must work for **all x in I_t** and all admissible w before the next observation; subsequent decisions may branch on the next observation. An exact information-state transition must include that observation-conditioning step. Independent application of a state-feedback action at every possible x allows different actions before x has been distinguished and is unsound. The reviewed rocket sources/A08 do not supply such a belief/information-set game contract.

Clipping is not robust feasibility. Example: x1=u0+w0, x0=0, U0={0}, W0=[-1,1], target/safe next set S={0}. The uncut successor set is [-1,1], and its intersection with S is {0}; nonempty clipped propagation would suggest a possible safe outcome. Yet w0=1 violates S, so the robust predecessor is empty. Likewise checking vertices of a successor polytope suffices for containment in a convex target, but not in a nonconvex future winning set: both endpoints of [-1,1] belong to S={-1,+1}, while its interior does not. Finite-action feedback predecessors can generate nonconvex sets.

For approximate geometry, a proved outer transition enclosure Fhat with `F subset Fhat` and a proved inner winning set Shat with `Shat subset S` yield sound feasibility from `Fhat subset Shat`. Merely intersecting an enclosure with a safe set proves neither containment nor the original inclusion direction. Results must name ideal operands, representation/inclusion direction, arithmetic/residual evidence, action selector, information/timing convention and policy class. A sampled trajectory is a witness for its particular disturbance/measurement history, not a policy-wide guarantee. A robust safety policy need not be terminal-cost optimal.

## Recovered implementation evidence: A08/A09

**A08** is a distinct adaptive minimax driver, not the duplicated nominal Python listing. Lines 44-45 initialize the four-state `position`; lines 47-49 trigger a remaining-horizon A09 solve; lines 51-52 apply its first action and accumulate it in the physical throttle variable; lines 57-65 propagate the deterministic nonlinear formulas and record four simulated state quantities before the next solve. Thus its actual loop is observation/reconstruction from simulated full state, solve, apply, evolve, observe. No observation-noise/estimator model or adversarial disturbance-history search appears in that loop. A08 stores actuator accumulation `u=u+U(1)` as additional implementation memory; correspondence between incremental linear actions, absolute throttle setting and full-state nonlinear dynamics needs explicit modeling before a physical feedback theorem. Lines 81 and 136 report a cost with an unsquared fuel-flow deviation and a stock synchronization residual, whereas A09 line 32 squares both flow deviations. These are materially different criteria, not evidence that Eq.(16)'s Euclidean cost was used throughout.

**A09** line 4 forms a remaining program catalog from the supplied full catalog. Lines 8-15 propagate fixed-action uncertainty images using P1 and `ConvSM_mod`; line 16 rejects a program unless **all retained vertices** satisfy all X1 inequalities at every step. This is a whole-set containment check if the returned hull is complete/exact and X1 is its convex half-space target. It does not clip the reachable set. That logical pattern is compatible with the robust fixed-plan proof, but depends on hull correctness, complete disturbance vertices, floating errors and catalog indexing; this audit did not execute or certify those dependencies.

A09 lines 32-43 maximize a convex augmented norm by minimizing its negative with fmincon and then compare with every retained terminal vertex. The complete-vertex safeguard is mathematically appropriate for this fixed-plan convex norm if the geometry is complete and exact; fmincon alone is not a global certificate. The `eps` comparison and all-NaN/infeasible catalog behavior need an implementation audit before guaranteed outputs. Lines 48-50 return one argmin sequence, with no full tie family. A08 consequently implements one selector of the remaining fixed-plan solve, not a globally optimized feedback policy tree. Saved nonlinear histories cannot establish the supremum of its realized policy over all disturbance histories.

## Precise remaining issue #5 obligations

1. **Maintain source-specific policy authority.** Accept L02 as nominal Theorem 4.3 and L04/L09/L10 as fixed-plan results. Describe L13 Eq.(18) as an H-constrained replanning rule; attach the proof of `J_replan<=J_fixed` only under the stated exact-model, rectangular-disturbance, robust-containment, attainment and information hypotheses. Preserve the counterexample if any broader causal-optimality identification is proposed. A referenced monograph theorem must be recovered with its exact page/hypotheses before being credited; its general existence must not override the counterexample to the broader identification.
2. **Resolve L13's value/status reporting.** An actual realized terminal cost, a last-stage conditional minimax cost, an initial fixed-plan upper guarantee, a policy's whole-history worst case and a global causal optimum are different quantities. Eq.(20) must not be silently used as the last two. State whether the intended supported output is one selector, all H selectors, the best H selector, or a globally minimizing causal policy; Algorithm 3's arbitrary tie rule establishes none of the latter optimization/completeness claims.
3. **Bind physical observations and transitions to the theorem.** Specify decision/measurement timing, exact vs bounded-error observations, four-state reconstruction, incremental-action/actuator memory, linear-surrogate coordinate interpretation, and a proved disturbance enclosure for nonlinear/model/discretization error over the reached region. L13's sensor sentence and A08's simulated state are insufficient. Unsupported partial-observation or nonlinear guarantees should remain explicitly unsupported, not be assigned exact-state theorem status.
4. **Implement/review a bounded supported feedback contract later.** This report performs no implementation. The future contract must name X/U/W/f/S operands, nonempty admissibility, existential-control/universal-disturbance order, rectangular versus coupled uncertainty, selector measurability/causality, whole-set containment, recurrence and evidence direction. Current fixed-plan containment is distinct from a predecessor/global-feedback implementation.
5. **Independently verify the actual supported behavior.** Required transparent cases include the two-step strict-gap example, its interior feedback worst case, the clipping counterexample, tie selectors, all-infeasible programs, a nominal equality case and any declared observation-noise model. Global feedback evaluation cannot rely on fixed-plan vertex convexity without an additional continuation-value proof. Recheck A08/A09 geometry/catalog/optimizer dependencies and use of the criterion before calling that implementation guaranteed; published-run identity/objective recovery belongs jointly to #1/#2/#6 and is not completed here.

These are scoped obligations within the reviewed evidence. This report supplies an authored theorem-policy reconstruction and explicit proofs/counterexamples; it does not close issue #5, reproduce L13's published numerical run, audit every monograph proof, certify floating geometry, or establish a nonlinear sensor implementation.

## Exact literal reference checks

[check_proof_counterexamples.py](tools/check_proof_counterexamples.py) computes the four finite plans' squared worst costs 4, 4, 2, 10; replanning costs at disturbances -1, 0, 1; both tie actions at -1; and causal vertex/interior costs. The checked replanning maximum is squared cost 2, the causal maximum is 1, and feedback disturbance-vertex costs are 0 while the interior cost is 1. These exact literal checks run with the standard library under `python -O`. The continuum upper/lower bounds and tie analysis are the analytic proof above, not a claim of certification from samples.
