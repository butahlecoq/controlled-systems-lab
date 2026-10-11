# Reachability construction and nonlinear guarantee audit for original issue #4

2026-10-11. Curated authored evidence for [original issue #4](https://github.com/butahlecoq/controlled-systems-lab/issues/4), delivered by [curation issue #109](https://github.com/butahlecoq/controlled-systems-lab/issues/109). The initial independent review and two scoped correction rounds are complete; original issue #4 remains open. The final round checked one sentence, not the whole report again.

## Result

The exact affine/polyhedral recurrence is justified by the owning forward theorem in **L01, PDF p.4 / printed p.118, Theorem 1**, and by the proof below. With exact stage intersections and independent convex controls, deletion of candidate points followed by their convex hull produces an **inner reachable set for that affine model**, even if deletion is aggressive. At a step, equality of the pre-intersection finite candidate hull and retained hull holds if and only if every discarded point has a convex-combination certificate in the retained hull. Such certificates suffice for equality after state-constraint clipping, but are not necessary there: clipping can remove all lost points. This statement includes witness realizability, not just geometric containment.

The related Goranov/Shorikov primary paper **A44, PDF pp.6-7, section 4** gives a precise incremental membership rule for which hull equality can be reconstructed rigorously. **L05, PDF pp.7-8**, instead states a support-hyperplane predicate without specifying its operational LP or the hyperplanes being tested. Its final equality to the full reachable set does not follow from subset retention alone. A44 is useful source-specific evidence, but is not established here as L05's exact cited reference [5] or [6], nor as the generator of Table 1. Do not silently replace L05's predicate with A44's.

Neither the exact linear construction nor its inner reduction has an established inclusion direction relative to the nonlinear reachable set in the reviewed L05/L07 sources. A smooth one-step counterexample below shows that reference linearization can give neither an inner nor an outer set. L07 and its cited discretization paper A45 provide exact linear transition formulas under piecewise constant inputs, but do not complete a validated nonlinear remainder plus numerical integration enclosure chain.

## Source authority and review disposition

The [provenance record](proof-audit-provenance.json) identifies original-byte hashes, navigation-extract hashes and the distinct private authored-version chain. Its final antecedent digest is **not** the digest of this curated report. Source files remain local-only; their original bytes and typeset formulas own the source claims. PDF pages below are one-based file pages; printed pages are separately marked. L03 uses section/paragraph anchors.

The prior audit inspected the source formulas and relevant rendered pages; this delivery curates that reviewed evidence and performs no new theorem audit or historical program execution. Navigation extracts never replace typeset authority. The antecedent records a malformed 65-character L07 navigation hash; provenance retains that text as an unverified metadata note, not a SHA-256 identity. The registered original L07 digest remains the source authority. A43/A44/A45 are the permanent supplementary IDs for the prior audit aliases RP01/RP02/RP03; published A39–A42 retain their earlier identities.

| ID | Original relative filename | SHA-256 | Relevant anchor |
|---|---|---|---|
| L01 | `papers/1993 АиТ Алгоритм решения задачи терминального управления для ЛДС.pdf` | `b468f67e7464256a3212552f72588c223e295f70f40867894afb841387449872` | pp.1-2 fixed nonsingular A, compact convex X0/P; pp.3-4 Lemmas 1-2 and Theorem 1; p.4 vertex-feasibility problem |
| L03 | `papers/pardalos.docx` | `4350cf20a2e458a9bd3cdb95e3ea8e306549b4b65d80fc5e3c5b89712d20dafb` | sections 3.1-3.4; section 3.4 paragraphs beginning with the two outcomes of the LP, and Steps 2.2/3 |
| L05 | `papers/АППРОКСИМАЦИЯ ОБЛАСТЕЙ ДОСТИЖИМОСТИ .pdf` | `dfc76d4d33dad578567f851ae8169a44af290d2e17ea826cec46271dde2d311d` | p.3 Eq.(1)-(4); p.4 Eq.(5)-(7); pp.5-6 Eq.(8)-(9), recurrence; pp.7-8 candidate procedure; pp.8-11 Eq.(10)-(11), Table 1 and figures; p.12 bibliography |
| L07 | `papers/Пояснительная записка.pdf` | `6bc149e7e1c63d1cff262ffd861898d528a3eee2b1c0b591aebde91c607f89fc` | pp.14-15 small-deviation assumption and dropped higher-order terms; pp.30-38 discretization; p.39 numerical comparison; pp.44-51 Eq.(3.1)-(3.8) and hull algorithm; pp.59-60 references |
| A43 | `Публикации/statyi dlya shiryaeva/Булаев В.В. Шориков А.Ф. ИТИС17.pdf` | `a90a3e404807238886122dfdfc91a5f18697949137a8d9744af7180508de848a` | *Modification of the general recurrent algebraic method for constructing reachability regions of linear discrete controlled systems*; pp.3-4 recurrence/LP; pp.5-7 basis-point modification and its own counterexample |
| A44 | `Публикации/statyi dlya shiryaeva/Горанов А.Ю. Шориков А.Ф. ИТИС17.pdf` | `493917da7d8ac669a470a978780a2ca269ce9da1b594365f49c6ebd572388fd7` | *Modified recurrent method for constructing the reachability region of a linear discrete dynamic system*; pp.4-5 Eq.(7), pp.6-7 exact incremental test and final recheck; p.10 references |
| A45 | `Публикации/statyi dlya shiryaeva/Булаев В.В., Шориков А.Ф. Пермь.pdf` | `ce651337929ca727e8210bec8267a7ba543bd2e7fe6a8fc27fba598df6cbdef8` | Bulaev/Shorikov, *Method of discretization of linear dynamic systems*, 2016, DOI printed as `10.17072/1993-0550-2016-2-67-73`; pp.2-5 Eq.(1.1)-(4.1), especially p.3 piecewise constant inputs and Eq.(3.1)-(3.2); p.6 figures |

### Reviewed corrections

- **R4-C1:** Retained-hull certificates are necessary and sufficient for unclipped hull equality, but only sufficient after clipping. Round 1 corrected this and added the scalar counterexample.
- **R4-C2:** The support-gap formula uses the dual-norm unit sphere for the stated primal Hausdorff metric.
- **R4-C3:** The finite candidate set itself is not called convex; its hull and the specified initial/control/constraint sets are compact convex polytopes. The final scoped round approved this single wording correction.

The initial review found one medium and one low issue. Round 1 addressed both and raised the candidate-set wording issue; round 2 fixed it and the final scoped recheck approved it, with no outstanding correction. These gates do not certify historical code or close #4. Full ordered dispositions and reviewed-version digests are in the provenance record.

L05 p.12 explicitly cites: [2] Shorikov's 1997 book; [3] Tyulyukin/Shorikov's 1988 paper; [4] the 1993 paper L01; [5] Shorikov/Goranov's 2017 *Method of approximation of the reachability region of a nonlinear controlled dynamic system*, pp.112-121; [6] Bulaev's 2017 simplex/polyhedra conference item, pp.397-399. This audit inspected L01 as the available owning forward theorem. It did not retrieve the exact [5]/[6] texts; A43/A44 are related locally recovered primary papers with different titles/authorship and cannot be identified with those references by inference. Their proofs/algorithms are credited only to their own hashes. Exact [5]/[6] recovery and any implementation correspondence remain source gaps.

## Notation and reference sets

Following the [glossary](glossary.md), $X_t$ denotes admissible states, $R_t$ reachable sets, $S_t$ target/predecessor sets, $U_t$ controls and $W_t$ disturbances or bounded residuals. The discrete disturbance channel is $E_t$. This translates the antecedent's stage constraint $K_t$ to $X_t$, initial set $S_0$ to $X_{\mathrm{init}}$, and error tube $E_t$ to $Z_t$. Local finite candidate sets $S,C$ and generator lists $V,G$ are distinct from time-indexed sets. Source-specific symbols are described as such.

## Construction matrix

Use distinct notation to avoid L05's reuse of X for a constraint, a reachable polytope and a finite vertex list. Let X_t be the stage state constraint; U_t the independent stage control polytope; X_init the allowed initial set. For a fixed initial state set X_init={x0}; for initial uncertainty use the whole supplied polytope. With specified affine dynamics `x_(t+1)=A_t x_t+B_t u_t+c_t`, define

`R_t^lin = {x_t : there exists a complete history x_0,...,x_t,u_0,...,u_(t-1), with x_0 in X_init cap X_0, u_j in U_j, x_j in X_j, and the stated dynamics at every j}`.

The nonlinear reference `R_t^f` replaces the recurrence with the exact specified map `x_(t+1)=f_t(x_t,u_t)`, in the same physical coordinates and under the same initial, control and state constraints. It need not be convex. The continuous reference additionally specifies the admissible within-step input/disturbance function class and any constraints between sample times. A discrete sample-time set is not automatically a continuous-time safety tube.

| Construction | Reference and assumptions | Demonstrated mathematical contract | Historical/source limitation |
|---|---|---|---|
| L01 Theorem 1 full pairwise image and exact hull | Linear reachable set; finite horizon, convex compact polytopes, independent controls, all generating vertices; source uses constant nonsingular A, arbitrary B | Equivalent one-step and by induction equivalent horizon set | The printed theorem does not include L05's state clipping or its approximate filter; those require the reconstructed extensions below |
| L05 pp.5-6 unmodified recurrence with full hull, exact H/V conversion and exact X intersection | R^lin; source A_t nonsingular, compact convex X_t/U_t; fixed x0 initialization | Equivalent, if the clipped output is used on the next step | Vertex-list versus hull notation and feedback of the clipped set must be made explicit; general Xinit requires all Xinit vertices |
| A44 pp.6-7 incremental LP membership plus final exact hull | Hull of the supplied finite point set; then exact affine recurrence if used there | Equivalent; proof below covers ties, redundant seeds and lower dimension without a simplex assumption | Sorting direction wording is inconsistent with “most distant first”; seed-vertex assumption is unnecessary for equality, provided final exact recheck/hull occurs |
| L05 pp.7-8 subset retention plus final hull | Hull of its supplied feasible candidate points; R^lin if used in the proper constrained recurrence | Inner, possibly equivalent, with the hypotheses below; not outer except the equality case | Support-hyperplane predicate lacks a precise LP/facet/separation definition; equality is not established for the Table 1 implementation |
| L07 pp.49-51 / A43 pp.5-7 batched deletion certified by a retained basis simplex | Hull of a finite set, then affine reachable set | Equivalent hull if each deletion has a nonnegative normalized representation in retained points | “Basis points are vertices” is a stronger claim requiring its own pivot/tie proof; A43 explicitly demonstrates failure for its classical rule. Exact hull and minimal vertex-list correctness are different contracts |
| L03 sections 3.1-3.4 | Affine polyhedral reachable set and proposed LP/group filtering | Full hull rule is reconstructibly exact; subset-only group hull is inner if realizable; equality requires the correct deletion predicate | Extracted Step 2.2/3 prose reverses the feasibility/action association relative to its earlier two-outcome paragraph. Formula loss prevents identifying the intended precise LP here; do not silently repair or claim a verified implementation |
| Linearization using either full or reduced linear hull, L05 pp.3,8-11 | R^f of the nonlinear physical model | Heuristic approximation as a nonlinear guarantee; no inclusion established | Nonlinear-to-linear correspondence, region remainder and exact experimental construction unresolved |
| A45 exact transition/integral formulas | Continuous **linear** system sampled under piecewise constant u and disturbance | Equivalent sample-time dynamics when Phi/Psi/Gamma are mathematically exact | Numerical approximations to these matrices require independent bounds; arbitrary varying controls/disturbances are a different reference set |
| Finite nonlinear trajectories or their hull / plotted projections | Exact nonlinear endpoints for their specified feasible histories | Actual points are witnesses; their hull can be outside R^f | No complete coverage/enclosure from finite samples; projected pictures lose correlations |

## Reconstructed affine proofs and conditions

### 1. Exact recurrence and witnesses

Under independent convex U_t and convex X_t, the exact recurrence is

`R_0^lin=X_init cap X_0`,

`R_(t+1)^lin=(A_t R_t^lin + B_t U_t + {c_t}) cap X_(t+1)`.

Both inclusions follow directly. Every feasible history maps into the right side. Conversely, a point on the right has some predecessor r in R_t^lin and admissible u; the predecessor has a feasible history, so appending u gives a feasible history ending at that point. Compactness gives compact projected sets; polyhedrality follows by affine projection of the finite joint linear constraints. If a constraint destroys feasibility, the correct set is empty. Nonsingularity is not needed for this forward proof, although L01/L05 impose it and L01 uses it to identify vertices of the free image.

For finite generating lists V and G,

`A conv(V)+B conv(G)+{c}=conv{Av+Bw+c : v in V,w in G}`.

For the forward inclusion, products of convex weights generate the pairwise convex combination. For the reverse inclusion, a combination of pair images gives predecessor and control combinations by marginalizing the pair weights. L01 Theorem 1 p.4 proves this identity in its own notation. Repeating it and applying exact X intersection proves the extended L05 contract. Affine c terms do not change the argument.

All points of R_t^lin have realizable histories, not merely vertex witnesses. Given convex weights over finitely many feasible histories, use the same weights for each state and control at every step. Affine dynamics commute with that combination; convex X_j/U_j preserve feasibility. This fails for nonconvex/finite controls, nonconvex state constraints, nonlinear dynamics or an omitted history constraint. Temporal constraints require a complete history relation or a sufficient memory lift; physical-state-only independent propagation is not justified for them.

### 2. Inner recurrence after deletion

Let H_0 subseteq R_0^lin be convex and generated by feasible initial points. At a step form the full pair list from generators of H_t and U_t, keep any subset C_t, and set

`H_(t+1)=conv(C_t) cap X_(t+1)`.

Then `H_(t+1) subseteq (A_t H_t+B_t U_t+{c_t}) cap X_(t+1) subseteq R_(t+1)^lin`. If deletion occurs after exact clipping instead, keep a subset of that clipped polytope's generators; the same conclusion follows. Thus H_t is inner by induction, and each point has a feasible affine history by the preceding argument. This proof does not require that sorting is useful or that retained points are genuine vertices. It requires that actual retained points are feasible generated points, hull/conversion/intersection are exact, and the clipped H_(t+1) is fed forward. It says nothing about floating computations or the nonlinear plant.

L05 p.6 visibly calls a vertex list a set X-bar, then converts to an H-description. The coherent geometric reading is the hull of that list, not literal intersection of a finite point set with X. The loop must carry the clipped output; L05 does not explicitly spell out that assignment. These are necessary mathematical interpretations to state, rather than proof of the historical implementation.

### 3. Equality for certified deletion and A44

If q in conv(C), discarding q preserves the hull of C union {q}. If q notin conv(C), retaining it expands the hull exactly as required. For a finite candidate set S and retained subset C, `conv(C)=conv(S)` if and only if every point in S minus C lies in conv(C). Sufficiency follows by taking the hull of those membership certificates; necessity follows because each omitted point belongs to conv(S). This iff concerns the pre-intersection hull. With a state constraint X, it is sufficient but not necessary for `conv(C) cap X=conv(S) cap X`: for x0=0, A=B=1, U0=[0,2], S={0,2}, C={0} and X1={0}, both constrained sets equal {0}, while discarded 2 is outside conv(C). The initial, control and state-constraint sets, and both candidate hulls, are compact convex polytopes; A is nonsingular. Starting with any nonempty seed subset and applying the incremental rules gives the invariant

`conv(C_after_k)=conv(all points processed through k)`.

A44 p.6 retains q if it is a vertex of the hull after adjoining q. After deduplication, this is precisely q notin conv(C): an exterior new point must be a vertex of the enlarged hull, since otherwise it would be a combination of old points. Its final p.7 recheck removes redundant candidate points without changing the hull. This is an exact finite-set proof; no claim that the initial farthest k+1 points are true final vertices is needed. The proof also works for an arbitrary processing order. Boundary points may be discarded when represented by retained points; “nonvertex” is not synonymous with strict interior.

For batched simplex deletion, if each discarded point q has coefficients lambda>=0, sum(lambda)=1 in retained basis points B, all deleted points lie in conv(B). Keeping B and all other undeleted points preserves the hull. The L07 p.50 Eq.(3.8) transformed-column conditions have this geometric content if they are genuine barycentric coefficients for original retained point columns. B can include nonvertices without damaging hull equality. A final exact reduction is still needed if output promises all and only extreme vertices.

Deleting multiple points using certificates that refer to one another is unsafe unless retained certificate supports or sequential hull preservation is enforced. Duplicate coordinates must be merged or at least one representative retained: two duplicate extreme columns each appear representable by the other; deleting both from an original-list parallel test loses the extreme point.

### 4. Support-hyperplane wording: scoped counterexample, not an unconditional attribution

L05 p.7 visually says to test whether the new point belongs to an extreme supporting hyperplane of the **current** candidate hull, retain if so and discard otherwise. It gives no exact LP in this paragraph. If this is implemented as equality to one of the current facet hyperplanes, it does **not** imply exact hull preservation.

Take S={(-2,-2),(2,2),(2,-2),(-1,1)} in R^2. The bounding-box center is (0,0); the first three points are equally farthest in Euclidean distance. Their seed hull C is the triangle with facets x=2, y=-2 and y=x. The remaining q=(-1,1) is outside it, satisfies none of those facet equalities, and is an extreme point of conv(S). A facet-equality implementation discards q, leaving a strict subset. This is a valid one-step affine instance with x0=0, A=B=I_2, U0=conv(S) and X1=[-3,3]^2; all source convexity/compactness and nonsingularity assumptions hold. A separating direction d=(-1,1) gives h_C(d)=0 and d dot q=2, an exact inclusion-loss witness.

The counterexample targets that specified operational reading. “A supporting hyperplane” can also mean any tangent support plane, or the author may mean the enlarged-hull vertex LP of A44. These readings are different: for this example a support line of C through q is possible, and A44 explicitly retains q. The PDF image resolves the actual printed words, not the unprinted operational definition. Therefore this audit does not conclude that the intended L05 method or Table 1 code necessarily executes the faulty facet test. Resolve the exact predicate/source/code before extending the attribution.

### 5. Degeneracy and intersections

Full-dimensional simplex seeding is not guaranteed by “take n+1 farthest points.” A singleton initial state, rank-deficient B, collinear images, ties and clipping can yield fewer than n+1 distinct points or affine dependence. Membership in a finite convex hull remains well defined in the actual affine dimension; inversion of an assumed square basis and normalization by zero bounding-box widths do not. The source does not supply a complete handling contract for all these cases. Any exact implementation must handle empty input, duplicate points, zero-width coordinates and lower-dimensional polytopes explicitly.

L07 p.50 claims basis-point extremality for the named gradient rule. A43 pp.6-7 explicitly gives a classical-rule example with A=(1,1), B=(2,2), C=(0,3/2), D=(1,1/2), E=(3,1), F=(1,3), G=(-1,0), where a feasible basis uses B,C,D, although these are not extreme points of the full hull. It proposes a largest-norm tie rule and illustrates E,F,G for this example. This settles the generic BFS inference adversely, but one example and a higher-dimensional analogy do not supply a general pivot/degeneracy proof for the refined rule. The safe deletion/hull proof above does not depend on auto-declaring B extreme.

Stage intersection must operate on the hull/polyhedron, including newly created intersection vertices. For example the square [-1,1]^2 intersected with |x1|<=1/2 is nonempty and has four new vertices, although none of the square's original four vertices survives. Filtering only original vertices is inner at best and can return an empty set. L05 p.6's H-intersection then V-conversion is the correct mathematical operation when implemented exactly.

Linear projection preserves an already proved inclusion: P H subseteq P R; it also preserves exact hull construction. Projected agreement cannot establish full-state inclusion or feasible joint histories. Two diagonal line segments {(s,s):|s|<=1} and {(s,-s):|s|<=1} have identical coordinate projections but differ as joint sets. L05 p.11's lower-dimensional pictures are evidence about the depicted projections only.

## Nonlinear and numerical transfer

### What the reviewed sources actually provide

L05 p.3 Eq.(1) assumes f is continuously differentiable in state/control, then explicitly omits linearization and assumes a corresponding linear approximation has already been supplied. Eq.(2) has no affine offset. In a proper deviation model, `delta x_(t+1)=D_x f delta x_t+D_u f delta u_t+r_t`; in physical coordinates an affine offset is generally needed. Thus one must define the reference trajectory, control shift, state shift, transformed constraints and residual before identifying the linear set with an approximation of physical nonlinear states.

L05's visual pp.8-10 show differing initial vectors for the nonlinear and displayed linear examples: nonlinear example 1 starts (410,300) while the linear display states (1,2); nonlinear example 2 starts (1,1,1,1) while the linear display states (1,-1,1,1). These are printed observations, not a conclusion that the model is erroneous: a deviation/coordinate convention may be intended. The exact mapping is not given in the reviewed equations and must be recovered before a common-set comparison or error bound. Visual inspection also confirms absolute-value control bounds, |u|<=0.3 and |u1|,|u2|<=1, rather than the one-sided inequalities suggested by poor extraction.

L07 pp.14-15 assumes deviations remain small and discards second-order small terms. It does not quantify a remainder or prove all admissible trajectories stay in the region of that approximation. L07 pp.30-38 and its cited A45 provide a correct *linear* sample-time identity in terms of the exact fundamental matrix. A45 p.3 Eq.(3.1)-(3.2) explicitly assumes controls and disturbances constant during a step:

`Phi_k=Phi(t_(k+1),t_k)`,

`Psi_k=integral_(t_k)^(t_(k+1)) Phi(t_(k+1),s) B(s) ds`,

and the analogous Gamma integral for disturbances. Under that input class and exact matrices, there is no discretization approximation of the linear sampled flow. This is a useful exact chain segment. It does not prove equivalence to all continuous input functions or enforce intersample state constraints.

L07 p.32 calls the numerical solvers guaranteed-accuracy methods; p.39 reports ode45 absolute/relative parameters 1e-12/1e-6 and plots close trajectories. A45 p.6 also discusses close graphs. The reviewed material supplies no outward-rounded matrix intervals, truncation remainder, stability propagation or total reachable-tube bound derived from those solver settings. This conclusion is limited to the cited reviewed pages, not an assertion that no such theorem exists anywhere in the archive.

### Smooth counterexample to a nonlinear inclusion inference

Let x in R^2, x0=(0,0), U0=[-1,1], X1=[-2,2]^2, and `f(x,u)=x+(u,u^2)`. Linearize along the zero reference trajectory/control. Then A=I_2 is nonsingular, B=(1,0)^T and the exact linear reachable set is `{(u,0):|u|<=1}`. The nonlinear reachable set is `{(u,u^2):|u|<=1}`. The linear point (1,0) is not nonlinear reachable; the nonlinear point (1,1) is not linear reachable. Neither set contains the other, despite smooth f, convex compact controls/state constraints and an exact linear hull. Convex-hulling the two nonlinear endpoints gives (0,1), also not on the nonlinear curve. Therefore affine witness mixing and hull containment do not transfer to nonlinear witness realizability.

### Exact missing hypotheses and proof obligations for an enclosure

1. **Model and coordinates:** fix exact f or continuous g, reference trajectory/control, affine/deviation transformation and offsets, initial error, control/disturbance classes, units and all constraints. Include approximation of parameters or forcing, if present.
2. **Justified region:** certify a state/input tube D_t containing all trajectories quantified by the desired claim. Bounds merely measured around one nominal trajectory do not justify using D_t; prove self-consistency/invariance step by step.
3. **Remainder bound:** certify `f_t(x,u)-(A_t x+B_t u+c_t) in W_t` throughout D_t times U_t. C1 on a compact region can support a certified derivative modulus and integral Taylor remainder; a certified Hessian bound with C2 is a convenient sufficient alternative, not a necessary universal assumption. State the actual norm, radius, control deviation and bound. None is provided for L05's examples in the reviewed chain.
4. **Propagation:** for the same controls, `e_(t+1)=A_t e_t+r_t`, so a valid outer error tube satisfies `Z_(t+1) superset A_t Z_t+W_t`, or `eps_(t+1)>=||A_t|| eps_t+rho_t`. For continuous nonlinear flow, derive the analogous time-dependent Lipschitz/variation-of-constants bound and prove its domain hypotheses.
5. **Geometry loss:** an inner reduced H_t plus a nonlinear remainder tube is not an outer nonlinear enclosure unless the lost linear states are themselves bounded. Add a certified directed geometric error for R_t^lin versus H_t, or propagate an outer linear reference instead.
6. **Constraint correspondence:** a feasible nonlinear trajectory's same-control linear surrogate may violate the unrelaxed X_t. Therefore `R_t^f subseteq R_t^lin+Z_t` for two separately constrained systems does not follow just from same-control tracking. Use an unconstrained/appropriately relaxed linear tube for an outer proof and intersect the actual nonlinear X_t during the certified recurrence, or establish a valid constraint-margin correspondence. For an inner nonlinear claim, certify actual nonlinear feasible witnesses/sets; convex hull of sampled witnesses is insufficient.
7. **Discretization/integration:** if the plant is already the exact discrete map L05 Eq.(1), no continuous integrator error is intrinsic to that reference. If it is a continuous plant, state hold assumptions, account for any hold/model discretization discrepancy, certify Phi/Psi/Gamma computation error and roundoff, and propagate it over the entire relevant state/input region. Also enclose nonlinear witness integration, not just linear transition integration. Intersample safety needs interval flow tubes.

For example, if matrices are numerically approximated and exact matrices are known within operator bounds alpha_t,beta_t,gamma_t, a one-step additive residual bound must include `alpha_t sup||x||+beta_t sup||u||+gamma_t sup||w||` and any affine-term/quadrature error. This is an obligation template, not a bound computed for the historical runs.

### Reconstructed sufficient finite-horizon error lemma

This lemma is authored mathematics under explicit hypotheses. It is not a theorem recovered from L05/L07, and none of its constants has been evaluated or certified for a historical scenario.

Let the two discrete maps in common coordinates be `x_(j+1)=F_j(x_j,u_j)` and `y_(j+1)=G_j(y_j,u_j)`, for j=0,...,T-1. F can be the nonlinear plant and G an affine or numerically approximated map. Use the same admissible input history u and the same norm in both systems. For each j, supply a justified domain D_j containing both compared states, and finite constants L_j>=0 and eta_j>=0 such that

`||F_j(a,u)-F_j(b,u)||<=L_j ||a-b||` for all a,b in D_j and all u in U_j,

`||F_j(b,u)-G_j(b,u)||<=eta_j` for all b in D_j and all u in U_j.

Assume existence of both trajectories on the entire horizon, membership in D_j at every step, and `||x_0-y_0||<=eps_0`. These domain/continuation hypotheses must be proved, for example by a validated forward tube or self-consistent inductive enclosure. They cannot be inferred from the bound's desired conclusion. A Lipschitz bound for G with the mismatch evaluated at x gives the symmetric variant by the same argument.

Then set `eps_(j+1)=L_j eps_j+eta_j`. At every stage,

`||x_t-y_t||<=eps_t=(product_(j=0)^(t-1) L_j) eps_0 + sum_(k=0)^(t-1) [(product_(j=k+1)^(t-1) L_j) eta_k]`,

where an empty product is 1. This formula permits zero L_j and does not divide by any Lipschitz constant. The proof is the triangle inequality:

`||F_j(x_j,u_j)-G_j(y_j,u_j)|| <= ||F_j(x_j,u_j)-F_j(y_j,u_j)|| + ||F_j(y_j,u_j)-G_j(y_j,u_j)|| <= L_j ||x_j-y_j||+eta_j`.

Induction gives the recurrence; expanding it gives the accumulated bound. More generally, if a numerical G includes integration error, eta_j must bound the **entire** same-input map mismatch in common coordinates, including model approximation, integration, coefficient approximation and roundoff. Solver tolerances by themselves do not supply eta_j. Local bounds of the displayed type are sufficient only on the proved comparison domains.

The set consequences require separate history-coverage hypotheses:

- **Unconstrained directional inclusion:** if every initial x_0 in S_F has some y_0 in S_G within eps_0, and every admissible F input history is also an admissible G input history with the proved domain hypotheses, then `R_t^F subseteq R_t^G + Ball(eps_t)` for the unconstrained endpoint references. This follows by applying the trajectory estimate to each F history. The converse requires coverage in the other direction; shared notation for inputs is not itself a coverage proof.
- **Two-sided/Hausdorff result:** if the initial matching relation covers both initial sets, the two systems have the same admissible input histories, both compared trajectories stay in the proved domains, and endpoints are taken over all those histories without incompatible path constraints, the same estimate works in both directions. Consequently their Hausdorff distance is at most eps_t (for nonempty compact endpoint sets). Nonconvexity does not invalidate this pairwise-history proof; it does invalidate replacing the endpoint sets by hulls without a separate claim.
- **Constrained outer direction through a relaxed surrogate:** suppose a feasible F history obeys x_j in X_j. Its matched y_j lies in `X_j + Ball(eps_j)`. If G's reference uses these relaxed stage constraints, then every feasible F endpoint lies within eps_t of a feasible endpoint of the relaxed G system: `R_t^(F,X) subseteq R_t^(G,X+eps) + Ball(eps_t)`. This is a one-sided outer bound, conditional on the initial matching, common input and domain hypotheses. Using the unrelaxed constrained G reachable set in its place is not justified.
- **Unrelaxed constrained directions and margins:** to get `R_t^(F,X) subseteq R_t^(G,X)+Ball(eps_t)`, every feasible F history must have a matched G history that is also feasible. A sufficient, stronger condition is that every such x_j has its entire eps_j-ball inside X_j, with appropriate initial matching. For the reverse direction, require the same coverage for each feasible G history; a sufficient condition is `y_j+Ball(eps_j) subseteq X_j` at every stage for all these histories. Such uniform margin assumptions may fail at boundary-optimal paths. A proven feasible-history relation can replace margins. Two-sided constrained Hausdorff bounds require both coverage directions, not just the unconstrained tracking estimate.
- **Tightened-surrogate witnesses:** if G is planned with the tightened constraints `X_j minus Ball(eps_j)={y:y+Ball(eps_j) subseteq X_j}`, its matched F history is feasible. This certifies actual F endpoints within eps_t of those surrogate endpoints. It does not assert that the surrogate endpoints themselves belong to the nonlinear reachable set. A nonlinear inner-set claim still needs actual endpoint/set realizability.

The same stagewise margins and relaxation logic applies to all modeled path inequalities after specifying their Lipschitz/coordinate error. Continuous-time path safety additionally requires the bound between sample times. This lemma completes a sufficient conditional proof template; supplying verified domains and constants, historical coordinate correspondence, input-class identity and constraint-history coverage remains work required by issue #4.

## Metrics and the Table 1 discrepancy

Specify a metric against the named exact reference, in fixed coordinates and units. For compact convex affine sets the support function `h_S(d)=sup_(x in S) d dot x` gives inclusion H subseteq R iff `h_H(d)<=h_R(d)` for all d. For polytopes, verified membership of every H generator in an exact H-description of R is a finite inclusion certificate; reverse inclusion requires corresponding complete R generators or a valid global support bound. Testing finitely many arbitrary directions is incomplete unless the chosen finite family is proved sufficient. For nonlinear nonconvex R, support functions identify only its closed convex hull, so support equality does not imply exact nonlinear set equality.

The directed distance `delta(R,H)=sup_(r in R) inf_(h in H)||r-h||` measures states lost by an inner approximation; `delta(H,R)` measures false states introduced by an outer one. For nonempty compact convex sets, the Hausdorff distance induced by the primal norm ||.|| is `sup_(||d||_*=1) |h_R(d)-h_H(d)|`, where `||d||_*=sup_(||z||<=1) d dot z` is the dual norm. Euclidean unit directions are appropriate when the chosen primal norm is Euclidean. A certified global bound requires the whole dual-unit-sphere optimization or a justified finite discretization bound. Volumes, vertex counts and floating LP residuals have separate roles and do not replace these certificates. Full ambient volume is zero for lower-dimensional sets, so it can completely conceal loss; choose the relevant affine-hull dimension if volume is reported as a descriptive metric.

L05 Table 1 p.10, visually checked, gives linear full/modified volumes 4.62/4.34 and 40808.17/34764.47, and vertex counts 120/16 and 756/153. Two exact constructions of the same final affine polytope must have the same volume and the same distinct extreme vertices. These unequal reported quantities therefore cannot simultaneously be equality evidence for the same exact reference under the same data/metric. Possible explanations include deliberate reduction, different inputs, geometric/numerical approximations, coordinate differences or reporting error; the available table does not select one. The same table's nonlinear numbers and figures do not establish complete nonlinear enumeration or validated enclosure. No reported runtime claim was independently measured in this audit.

## Remaining original issue #4 obligations

| Acceptance part | Established here | Still needed before closure |
|---|---|---|
| Exact/inner/outer/heuristic contracts | Source-specific matrix; exact full affine proof; affine inner deletion/witness proof; exact A44 incremental proof; no automatic nonlinear inclusion | Resolve L05's precise support predicate and code/run correspondence; separately classify any actual tolerance/truncation variant and L03's formula-defined grouping rule |
| Relevant proofs | L01 owning theorem followed; precise A44 rule reconstructed; L07/A43 basis claim separated from safe deletion; degeneracy, constraints and projection covered | Recover exact L05 references [5]/[6] or document their unresolved scope; general proof or validated replacement of basis auto-extremality/pivot tie claims; prove actual implementation meets contract |
| Reference sets and error metrics | Physical nonlinear, affine constrained and continuous/held-input references defined; directed inclusion/support/distance metrics specified | Fix historical reference coordinates, exact input/state sets, construction identity and volume conventions; produce certified metrics against those references where an approximation guarantee is claimed |
| Tolerances/samples versus validated enclosure | Smooth noninclusion counterexample; exact discretization chain segment identified; named error-chain obligations | Establish and compute a justified nonlinear remainder/integration tube for any plant guarantee, including constraints and geometry loss; otherwise retain explicit heuristic/sampled-only scope |

This report advances the theorem audit and settles several conditional claims. It does not close original issue #4, reconstruct the Table 1 generator, certify a nonlinear plant or establish archival implementation correctness. Smaller volumes and successful replay cannot fill the remaining proof obligations.

## Exact literal reference checks

[check_proof_counterexamples.py](tools/check_proof_counterexamples.py) checks the unclipped loss/equal clipped sets (R4-C1), support values 0 and 2 for the conditional facet reading, and incompatible nonlinear endpoints exactly. It requires only Python's standard library and remains active under `python -O`. The affine and continuum error claims are proved above; finitely many arithmetic checks do not certify them. The provenance record links each check to its report section.
