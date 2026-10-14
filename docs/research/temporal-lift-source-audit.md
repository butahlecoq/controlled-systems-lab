# Reviewed temporal-lift source and compatibility audit

Date: 2026-10-11. Status: curation of an independently reviewed source-backed mathematical audit; **not implementation approval**. Scope: nominal finite-horizon open-loop affine dynamics, continuous controls, fixed physical initial state and specified previous input. No robust/adaptive, finite/hybrid, arbitrary temporal-memory, performance or validated floating-point claim. The original scientific issue is [#9](https://github.com/butahlecoq/controlled-systems-lab/issues/9). The separate [EXT-03 implementation](../superpowers/plans/tickets/EXT-03.md) remains future work.

## Disposition

The feasible-history bijection in [temporal-coupling.md](temporal-coupling.md) §4 is correct for its stated one-step slew relation. Its next-state input index is correct: `S[t+1] = X[t+1] × U[t]`. Neither invertibility nor convexity is required for that algebraic bijection. They are additional hypotheses of particular algorithms and set representations.

The note does **not** establish unchanged compatibility of L01 or an archived solver. L01 is explicitly time invariant with fixed A, B, P and a linear terminal objective; intermediate state bounds are absent. L11 supplies the appropriate stage-state intersections in Figure 1, but its model and stated objective are four-state/scalar-input and physical Euclidean distance. Its displayed backward definition/algorithm has indexing inconsistencies. The finite-dimensional generalization and corrected exact recovery are proved below as authored extensions, not relabelled as a theorem already proved in L11.

Saved L14/L26 and A03/A35 routines have concrete barriers: single-terminal-point optimization, selected witness recovery, time-indexing/global-variable problems or fixed constraints. No saved implementation audited here is certified for complete lifted optimal families.

## Evidence and provenance

This public report curates private authored findings with final SHA-256 `47776944c48f7b6953cba4880e7479db4752c7863f51288770fd1ee8a5a5b38f`. That digest identifies the private antecedent, not this Markdown file. The [machine-readable provenance](proof-audit-provenance.json) separately identifies original bytes, navigation extracts, authored antecedent versions, review artifacts and current public report UTF-8 bytes with line endings normalized to LF. Only curated public-report hashes normalize CRLF/CR to LF, matching committed LF blobs and allowing platform checkout conversion. Original-source, navigation-extract, private antecedent and review-artifact hashes remain raw byte identities. Public report hashes do not include the provenance file itself or the generated verification snapshot.

Physical PDF pages are used throughout; L01 printed pages equal physical pages +114. Original sources remain local. Curation recomputed all seven original hashes against the unchanged [inventory](inventory.json) and [selected-source register](archive-selected-sources.json). No new source was registered or renumbered.

| ID | Source / scope | Original SHA-256 |
|---|---|---|
| L01 | 1993 terminal-control paper; pp.1–10 | `b468f67e7464256a3212552f72588c223e295f70f40867894afb841387449872` |
| L11 | Nominal fuel-control draft; pp.6–12,14,16,20 | `e04c2f1609e2580c8878ab7fb91bc41151ccc8e0cf1f5deac4cef9fd860ce147` |
| L14 | Saved optimal-control PDF listing; pp.2–3 | `8c91da3e15213e1f83c077de52c13ea607946e7d00bda70440109cd9ba6fe6b6` |
| L26 | Saved Python reachable-set source; lines4–32 | `98aa51db7995a25eeb52c30e360f47a197b42a7cd5ed974fd5fe809666cedc4e` |
| A03 | Saved nominal MATLAB optimization; lines13–38,51–65,76–110 | `e55761fae07a5934206b195d6e986db29e0287cc9b2833fc05ff8d8276ba5bcb` |
| A35 | Saved MATLAB witness stitching; lines1–22 | `1f0b2e8264712c3e562fd52d1cb478482121717959a83810edbc0fe70924fef2` |
| A06 | Saved Pascal module; interfaces5–26, REACH41–71, OBREACH215–244 | `06fa90d5977ab49174abbf866899000f511fad46eac4a1e72388bbe27090a442` |

Stable anchor groups are L01-01/02 (existing) and L01-03/04 (backward/family and conversion), L11-01…06 (model, definitions, recovery, marginal coverage, reference identity, Figure1), L14-01, L26-01, A03-01…03, A35-01 and A06-01…03. Their page/line ranges and owning hashes are in the provenance file. Extracts serve navigation only. The antecedent audit and independent review inspected typeset originals; their evidence included L01 pp.1,2,4,6–10; L11 pp.6–9,11,12,14,16,20; and L14 pp.2–3. Curation preserves that evidence scope and does not claim a fresh whole-source visual audit.

### Reviewed clarification

The original independent review found no blocking mathematical or source-attribution finding. Its single nonblocking clarification, now `R9-C1`, separates the unique physical nearest point from the potentially non-singleton lifted memory fibre, and marginal coverage from the complete transition relation. The author amended four passages and made the examples' compact domains explicit. The scoped recheck marked the clarification addressed, with no new breakage in those passages; it did not re-audit unchanged proofs, run a solver or approve an implementation.

| Ordered event | Version identified | Artifact SHA-256 |
|---|---|---|
| Independent review | Initial `e5a014756c41f4e0df519e073cfce7890efe0037cf53f58d8a5fdd2980dd3641` | `792ab34cae829e695c5dcd437f03c4d69315166edaf14eee1696f5cdb4ea6e0a` |
| Author fix, round1 | Initial → final `47776944c48f7b6953cba4880e7479db4752c7863f51288770fd1ee8a5a5b38f` | `51cdd2d5c08e42a5671d4d213c6263721aa566f89bbfc9ebe93884675cb79975` |
| Scoped recheck, round1 | Final only; four amendments and their immediate context | `fb40028e52c35a4804dbbe88746edba0c9d7b529abb0cfdb4e7078a4650d4993` |

Private review transcripts, original listings, extracts, page images and source data are not republished. The public report contains authored mathematics and curated source observations. Source hashes identify evidence without establishing redistribution rights.

## 1. Exact formulation and independently checked proof

Let t=0,...,T−1, T finite; x in R^n, u in R^m. Original histories obey

```
x[0] = x0 in X[0]
x[t+1] = A[t] x[t] + B[t] u[t] + a[t]
x[t+1] in X[t+1], u[t] in U[t]
u[t] - u[t-1] in D[t], with u[-1] = p0 fixed.
```

Here S denotes the augmented admissible stage domain, explicitly differing from the general glossary target-set shorthand. Use z[t]=(x[t],p[t]), z[0]=(x0,p0), v[t]=u[t]−p[t], and

```
Ahat[t] = [[A[t], B[t]], [0, I_m]]
Bhat[t] = [[B[t]], [I_m]]
ahat[t] = (a[t],0)
z[t+1] = Ahat[t] z[t] + Bhat[t] v[t] + ahat[t]
v[t] in D[t], z[t+1] in S[t+1] := X[t+1] × U[t].
```

The initial admissible set is the singleton `{(x0,p0)}` (or its intersection with the physical initial constraint). No `U[-1]` is needed. A separately required historical bound on p0 is a separate assumption, not `p0 in U[0]`. Imposing that latter bound can wrongly exclude an initially out-of-range actuator which must move into the permitted range at t=0.

**Forward map:** for each original complete history, put p[t]=u[t−1], v[t]=u[t]−u[t−1]. The second block is p[t+1]=p[t]+v[t]=u[t]; the first block equals the original recurrence. The successor product constraint gives the original state bound and the current absolute input bound. Thus the lifted history is feasible.

**Reverse map:** given a lifted history, recover u[t]=p[t]+v[t]=p[t+1]. Starting from p[0]=u[−1]=p0, induction gives p[t]=u[t−1]. Therefore every original slew, absolute-control, state and dynamics constraint holds. Applying one map after the other gives the identical *complete* history, not merely the same terminal state. Costs `phi(x[T])` and `phi(P_x z[T])` agree, hence optimal histories correspond bijectively whenever minimizers exist. Empty feasible relations also correspond exactly. This proof requires no rank, invertibility, convexity, boundedness or interior assumption.

If the first slew bound starts only at t=1, choose and record any fixed bookkeeping p0 and replace the first increment domain by `D[0]=U[0]−p0`. Then the t=0 control is unrestricted beyond its original absolute bound. This is exact and compact/polyhedral whenever U[0] is. It is a **stage-specific** increment set, which does not automatically meet L01's common-P assumption. An unknown prior input with a t=0 slew condition changes the problem unless its admissible relation/quantifier is explicitly supplied; selecting p0 or optimizing it silently is invalid.

For physical rate r over elapsed time h[t]>0, encode the intended increment set using that duration (e.g. `D[t]=h[t] R[t]`). A rate penalty does not impose this hard relation. Official [do-mpc LQR source documentation, `set_rterm`](https://www.do-mpc.com/en/latest/_modules/do_mpc/controller/_lqr.html) (rendered documentation version 5.1.2, retrieved 2026-10-11) shows the same block matrices for input-rate penalization and describes changing the objective. It is a structural comparison only; it supplies no hard-slew or complete-family proof here.

## 2. Algebraic, geometric and affine hypotheses

**Nonsingularity and rank.** Block triangularity gives `det(Ahat[t])=det(A[t])`, with inverse

```
Ahat[t]^-1 = [[A[t]^-1, -A[t]^-1 B[t]], [0,I_m]].
```

`rank(Bhat[t])=m` because its bottom block is I_m, even if B[t]=0. This is not a controllability assertion. L01 p4 expressly imposes no restrictive hypothesis on B; L11 (1.6), p6, imposes sizes but no B-rank condition. Requiring B to be square/invertible or full row rank would therefore be an adapter restriction, not inherited source theory. Neither the bijection nor the forward recurrence needs invertible A. When original A is singular the inverse-based L01/L11 routes are unavailable; a projection-based predecessor is a different supported algorithm. The direct-input memory lift `diag(A,0)` is singular even when A is invertible, unlike this increment lift.

**Geometry.** Products of compact convex polytopes are compact convex polytopes; linear images, Minkowski sums and intersections preserve that class (allowing empty sets). Hence compact polyhedral X[t],U[t],D[t] make each S[t] and each nonempty reachable/predecessor set a polytope. If X[t] is unbounded or absent, `X[t]×U[t−1]` need not be compact, although the reachable tube from fixed x0 and bounded controls is compact. That distinction matters for L11's literal compact-state-domain hypothesis. One can derive finite-horizon outer boxes containing all trajectories under U[t] and intersect X[t] with those boxes without changing feasible histories; that is an explicit authored preprocessing argument, not evidence that an unbounded supplied domain already meets L11.

For the joint formulation, fixed finite coefficients, fixed x0, bounded U[t], closed polyhedral constraints and finite T yield a compact feasible relation if nonempty, because the affine recurrence bounds states. Continuous phi then attains a minimum. Convexity of phi gives a convex optimal relation; linear phi gives a polyhedral optimal face. A general convex phi need not yield a polyhedral minimizer set, so a V/H-only terminal-set interface needs an additional representability assumption. Convexity alone is not a proof of a runnable polyhedral recovery implementation.

**Lower dimension.** Neither L01's polytope hypotheses (pp1–2) nor L11's Assumptions 1–2 (pp6–7) state nonempty ambient interior. L11 explicitly starts at a point. L01 Algorithm 2 step8, p9, retains equations `C x_tilde=0` in its H/V construction; it should not be described as purely full-dimensional facets. The lift begins at a singleton in R^(n+m); at the first step its reachable dimension is at most m. Full-column-rank Bhat does not make that reachable set full dimensional. All equalities, affine hulls, singleton/segment sets and empty intersections must survive conversion; perturbing them into thick sets changes the exact problem.

**Affine offsets.** Both source dynamics are homogeneous in state/input: L01 (1), p1; L11 (1.6), p6. Nonzero a[t] is outside their formulas as printed, despite the exact affine lift. A homogeneous augmentation is possible:

```
y[t]=(x[t],p[t],q[t]), q[0]=1
Atilde[t]=[[A[t],B[t],a[t]],[0,I_m,0],[0,0,1]]
Btilde[t]=[[B[t]],[I_m],[0]]
S_tilde[t+1]=X[t+1] × U[t] × {1}.
```

It preserves determinant det(A[t]), input column rank m and the history bijection. The fixed q=1 slice is compact when the other factors are, convex and polyhedral, but always lower dimensional in the enlarged ambient space. Allowing q to vary or using an unbounded homogenizing ray changes the feasible control problem. An alternative exact translation is x[t]=y[t]+r[t], r[0]=0, r[t+1]=A[t]r[t]+a[t], with shifted X[t] and shifted terminal objective; this avoids an extra dimension but typically produces time-dependent constraints. Neither construction removes L01's other restrictions or validates code handling the new dimensions. Homogeneous augmentation of an LTV model remains LTV.

## 3. Explicit theorem/formulation crosswalk

References in this table use the verified hashes in the provenance table; no unnumbered L11 claim is presented as a numbered theorem.

| Hypothesis or conclusion | L01 owning source | L11 owning source | Lift disposition |
|---|---|---|---|
| Time dependence | (1)–(3), pp1–2, fixed A,B,P; Algorithms 1–2 take those fixed data, pp7–8 | (1.6)–(1.8), pp6–7, A(t),B(t),X(t),U(t) | LTV/stage-varying lift is outside literal L01; compatible with generalized L11 recurrence structure |
| State/input sizes | p1, arbitrary positive n,p; p8 says practical size limited by computing resources | (1.6), p6, explicitly n=4,m=1; Definitions 1–2 also R^4 | n+m is mathematically harmless for L01's set operations; ordinary L11 fuel lift is 5-state,1-input, outside its literal model. Generalization requires the dimension-independent proof, not a claim L11 stated it |
| A invertible | p1 assumption; Lemmas1/3, pp3/6; (8), p5; Theorem2, p6 | p6 assumption; Definition2, p9; Figure1, p20 | Preserved iff original A invertible. Singular-A joint/forward formulation still exact; inverse algorithm rejected |
| B rank | p4 explicitly no restrictive B assumptions; Lemmas2/4 | p6 specifies 4×1, no rank condition | Full-column Bhat automatic; no source need to invert B |
| Initial condition/quantifier | (2),(5), p2, minimizes jointly over pairs x(0)∈X0 and admissible controls | Assumption1 p6 and §3 p11, fixed x0 | Fixed lifted singleton allowed by convex-polytope mathematics. L01's variable initial state is existential optimization, not a robustness theorem. Fix memory, do not turn it into another optimized prior command |
| Compact convex polyhedral sets | pp1–2 for X0,P; Theorems1–2 pp4/6 | Assumptions1–2 pp6–7 for X(t),U(t) | S[t+1]=X[t+1]×U[t], v∈D[t] meets geometry if all factors compact convex polyhedral; unrestricted X requires explicit reduction or extended proof |
| Intermediate state bounds | No X_t admissibility in (1)–(3) or forward definition p3 | (1.7) pp6–7; Definition1 p8; Figure1 p20 clips forward X(t+1), backward X(t) | Essential absolute U becomes a state bound in lift. Unchanged L01 forward algorithm is generally wrong; L11-style clipping is the appropriate operation |
| Lower-dimensional sets | No full-interior hypothesis; Algorithm2 step8 p9 uses rank/equalities | Fixed initial point p6; H-representation p9 and V/H operations p10 | Mathematically allowed; implementation must prove equality/degeneracy support, especially fixed p0 and q=1 |
| Offset | No a in (1), p1 | No a in (1.6), p6 | Native affine identity exact; source adaptation needs homogeneous augmentation or translated coordinates as above |
| Terminal objective | (4),(5), p2 and Algorithm2 step5 p8, linear cᵀx | (1.9), p7 and §3 step2 p11, physical Euclidean norm; convex language around it; specific fuel criterion later differs | Linear pullback stays linear for L01. Physical-distance pullback stays convex but ignores memory; it is not full Euclidean distance in R^(n+m). Do not add a memory penalty or presume a unique augmented minimizer |
| Forward construction | Lemmas1–2 pp3–4; Theorem1 p4; Algorithm1 pp7–8 | Definition1 p8, semigroup discussion p10, Figure1 p20 | L01 vertex-pair image/Minkowski identity applies to each step before clipping; full lifted reachable tube needs stage intersection and correct time |
| Backward construction | (7),(8) p5; Lemmas3–4 and Theorem2 p6 | Definition2 p9; §3 steps3–4 p11; Figure1 p20 | Inverse affine predecessor followed by current-stage clipping/intersection is exact; source typo corrections and complete target set are required |
| Complete family | Theorem3 pp6–7 retains dynamics, control admissibility and all optimal-stage memberships; Algorithm2 step12 p10 | §3 step5 p11 and all-controls assertion p12 | Retain joint transition relation and all terminal minimizers. One LP solution or all marginal vertices does not imply all histories |

**Literal L01 compatible special case.** With constant A,B,D, zero offset (or a separately justified constant homogeneous augmentation), linear cost, and every augmented intermediate bound provably redundant on the unconstrained lifted reachable tube, the problem reduces to L01's stated setting with initial singleton and P=D. This is a conditional compatible case, not typical hard-slew-plus-absolute-bounds behavior. Stage-varying D[0], active absolute U[t], active X[t], varying matrices or a general convex cost each prevents an unchanged literal substitution. Theorem1/2 algebra can still be reused locally inside a newly proved constrained algorithm.

**L11 compatible mathematical extension.** For arbitrary finite n,m, nonempty feasible compact convex polytopes, known lifted initial point, invertible Ahat, physical convex terminal cost with an exactly representable minimizer relation, and correct stage intersections, the recurrence/recovery proof below establishes the natural extension. This is stronger than L11's literal dimensions and corrects its notation. It does not identify a tested saved program or prove arbitrary terminal objectives are V/H-representable.

## 4. Source inconsistencies that must not enter an adapter

1. L11 (1.10), p8, prints controls indexed 1,...,T−1 and dimension 1×(T−1), while (1.6),(1.8), Definition1 and §3 step5 use actions 0,...,T−1. Adopt T actions from 0 through T−1; mark the discrepancy, do not drop u0. No previous command or t=0 slew is supplied by this typo.
2. L11 Definition2, p9, prints a descending recurrence range starting at the terminal index ϑ, which would use x(ϑ+1) and A(ϑ), while its target is at ϑ. It also omits intermediate x(t)∈X(t) bounds. For a constrained backward reachable set the range must start at ϑ−1, and state bounds must be enforced at each predecessor. Figure1 p20 does clip by X(t), so it is not identical to the literal Definition2 set.
3. Figure1 p20 initializes its backward set at index 0 to x^(e)(T), while the first loop step reads the set at T. Correct initialization is at T. For L11's literal Euclidean-distance objective, the physical terminal minimizer is unique, so singleton terminal initialization is sufficient and is not itself a completeness defect. After lifting, the target must retain the full optimal memory fibre over that physical endpoint; see §5. The printed index error and the lifted target-set requirement are separate matters.
4. L11 p9 attributes compact polyhedral constrained reachable sets to reference [5]=L01. L01 does not itself include intermediate X(t) constraints; the extension follows from intersection closure and the induction below, not the literal L01 theorem statement.
5. L11 p9's explanation that discretization ensures nonsingular A must not be generalized to all numerical discretizations. Exact exponential discretization has invertible transition, but Euler can produce zero for xdot=−x with step1. The required adapter hypothesis is supplied discrete A invertibility, not merely a claim that a model was discretized.

These are literal source notation/scope observations. They are not claims of a published erratum, a failed numerical experiment or defects in the lift proof.

## 5. Correct forward/backward recovery with proof

Let R[0]={z0}. Define for t=0,...,T−1

```
R[t+1] = (Ahat[t] R[t] ⊕ Bhat[t] D[t] + ahat[t]) ∩ S[t+1].
K[T] = argmin { phi(P_x z): z in R[T] }.
K[t] = R[t] ∩ Ahat[t]^-1(K[t+1] ⊕ (-Bhat[t] D[t]) - ahat[t])
       for t=T−1,...,0.
E[t] = { (z,v,z_next): z∈K[t], v∈D[t], z_next∈K[t+1],
                          z_next=Ahat[t]z+Bhat[t]v+ahat[t] }.
```

Set subtraction here means addition of a reflected set, never Pontryagin difference. At t=0, R[0] supplies the fixed prior input, so no fictional previous absolute-bound stage is introduced. Equivalently, the inverse formula takes a successor `(x_next,p_next)` and increment v to

```
x = A[t]^-1 (x_next - B[t] p_next - a[t])
p = p_next - v.
```

The forward induction holds because a successor exists iff there is a feasible prefix ending at some z∈R[t] and v∈D[t] generating it and satisfying S[t+1]. For the backward induction, assume K[t+1] consists exactly of reachable states with an optimal continuation. Membership in K[t] supplies a reachable prefix and at least one increment reaching K[t+1]. The Markov state includes p, so these concatenate consistently. Conversely any optimal history has its next state in K[t+1] and current state in R[t], hence current state in K[t]. Base case is the full K[T]. Thus K[t] is the marginal set of states lying on some optimal history.

The **family itself** is the set of all paths through the E[t] relations starting at z0; recovery is u[t]=p[t+1]. Every such path has an optimal endpoint and satisfies all original constraints; every original optimal history maps into it. Independent Cartesian choices from K[t] are insufficient. In a polyhedral case one may keep the complete stacked affine/inequality relation without enumerating all paths. These proofs justify arbitrary finite dimensions and time variation; their validity is independent of the success of any numerical LP.

**Original endpoint uniqueness versus lifted memory.** L11 p7 (1.9) and p11 step2 minimize Euclidean distance to a fixed point over a nonempty compact convex reachable set. Squared Euclidean distance has the same minimizers and is strictly convex: for distinct x,y and 0<lambda<1, its value at lambda*x+(1−lambda)*y equals the weighted sum of the endpoint values minus lambda*(1−lambda)*||x−y||². Thus the physical minimizer is unique. Singleton terminal initialization is sufficient for that original objective; it does not alone certify the subsequent recovery implementation. The lifted objective ignores memory, so the optimal augmented target is the entire reachable fibre over the unique physical minimizer and may contain many points. The objections below concern losing that fibre or relying on marginal-vertex coverage. They do not refute L11 pp11–12's complete transition-relation characterization.

Two concrete completeness checks:

- Let scalar x[t+1]=x[t]+u[t], T=2, x0=p0=0, X[t]=[−t,t] for t=0,...,T, U[t]=[−1,1], D[t]=[−2,2], and phi=x[T]^2. These state domains are compact convex polytopes and contain all trajectories allowed by the absolute input bounds. Every pair `(a,−a)`, a∈[−1,1], is feasible and optimal. The augmented terminal states are `(0,−a)`. Selecting only `(0,0)` leaves only a=0 and loses all other optimal controls, although the physical optimal terminal state is unique. This directly blocks a single-terminal-point lifted use of L14/A03 for complete-family output; it is not an objection to using the unique physical endpoint in L11's original problem.
- Even without lifting, take the same scalar integrator with T=3, x0=0, X[t]=[−t,t] for t=0,...,T, U[t]=[−1,1], and phi=x[T]^2. The optimal endpoint is x3=0, and the optimal state marginals are K1=K2=[−1,1]. Witness controls `(1,0,−1)` and `(−1,0,1)` cover both vertices of both marginals, with state pairs `(x1,x2)=(1,1)` and `(−1,−1)`. Their convex hull forces x1=x2 and omits the optimal controls `(1,−1,0)`, whose state pair is `(1,0)`. Thus the p14 marginal-vertex-coverage assertion is not by itself a completeness certificate; this example does not refute the full transition-relation characterization on L11 pp11–12. A valid convex combination means nonnegative weights summing to one, not arbitrary linear combinations.

Both examples admit a four-state, scalar-input embedding with A=I_4, B=(1,0,0,0)^T, initial state zero and state domains [−t,t]×{0}³. The extra coordinates remain zero. Euclidean distance to the zero target then equals |x1[T]|, which has exactly the same minimizers as x1[T]^2. This matches L11's literal dimension and Euclidean objective for the mathematical examples; it is not a claim about its particular fuel-model coefficients or published numerical run. The embedding preserves both the lifted memory-fibre example and the marginal-coverage example without changing the valid transition-relation characterization.

## 6. Saved implementation crosswalk

These are read-only static dispositions, not reported run failures or benchmark outcomes. The module inventory supplied navigation; the antecedent audit's direct source inspection supplied the observations below. Curation preserves those scoped static findings.

| Saved source | Compatible structural elements | Concrete limitations / disposition |
|---|---|---|
| L14 pp2–3, `OpenLoopControl`, `ConvexProgram`, `Snatch`, `LPControl` | Shape-derived matrices, callback cost, H/equality data, two convex-combination LPs for one-step recovery; B need not be invertible | `ConvexProgram` returns one `result.x`, and backward initialization is that singleton. It does not return all augmented terminal minimizers. `Snatch` returns finitely selected paths. Visually printed additional-vertex branch uses undefined `t` in A[t:]/B[t:]/U1[t:] and contains indentation issues. No complete-family lifted compatibility; standalone OpenLoopControl.py was not recovered in the supplied inventory |
| L26 `ReachableSet.py:4–32` | LTV arrays, inverse-A backward path, stage H intersection, equality arrays from DDM | Signature takes U1 but line22 uses U, a nonlocal name, instead. Line27 uses X1[i−1+d] in both directions. Forward i=k+1 needs S[k+1] but reads X1[k]; backward i=k needs S[k] but reads the same X1[k]. A single general time-varying stage array cannot satisfy both interpretations; caller must pass direction-specific arrays or implementation must correct the index. This especially affects shifted U bounds in lift. Backward branch mutates supplied B. No offset input and no independent empty/rank/geometry validation shown. Not safe unchanged |
| A03 `OpenLoopControl.m:13–38,51–65,76–110`, A35 `Snatch.m:1–22` | A is indexed by stage; linear-image/Minkowski hull, state intersections, H equalities, one-step LP witness stitching | B, P and D (here D is the fixed state H-constraint matrix, not the slew increment domain) are fixed. Terminal objective explicitly references physical components1–4; fmincon returns one Z and backward target is {Z}. Later extra-witness pass is commented out. General stage-varying U/D, offset support and all optimal memory fibres are absent. Five-state arrays alone would not repair these semantics. Selected witnesses only; numerical family completeness unproved |
| A06 `btulshor.pas` interface lines5–26; `REACH:41–71`, `OBREACH:215–244` | Dimension parameters, affine-free vertex propagation and inverse dynamics as elementary routines | Missing external type units BIBTUSH/DIALOGS/term/funfnx mean actual dimension/storage capacity and full executable compatibility are unestablished. REACH's interface contains no stage-state constraint parameter; composing a clip would be added orchestration. No claim that this saved unit is the exact 1993 released executable or that its arbitrary-size arguments establish a working lifted solver |
| Current native [nominal-profile guard](../../src/contracts/problem.cpp) | Explicit capability rejection | Nonempty temporal joint_map is rejected; inverse-required profile is also rejected because no invertibility proof is supplied in revision1. This audit changes neither guard and is no authorization to bypass it |

Full column rank Bhat resolves no lower-dimensional conversion, stale array indexing, terminal minimizer, witness coverage or numerical certification issue. Generic LP feasibility and successful example replay cannot settle those separate obligations.

## 7. Capability review and first-experiment preservation

The [native contract](../contracts/core-interfaces.md), [modular capability policy](../architecture/modular-algorithms-and-solution-sets.md), [representation review](../architecture/set-representations-and-ellipsoidal-toolbox.md), [module inventory](algorithm-module-inventory.md) and current `check_nominal_profile` were examined for this curation. The guard rejects nonempty temporal `joint_map` rows and every inverse-required profile, because revision1 supplies no invertibility proof. It also rejects unknown initial-state sets, nonnominal information, external-input semantics, finite/mixed controls and set handles not declared convex/polyhedral. Passing that structural guard does not prove compactness, exact representation or compatibility of a numerical adapter. The curation changes no declaration, guard or solver module and enables no lift.

Ordinary zonotopes are not closed under the stage intersections required here: intersecting the square [−1,1]^2 with a+b≤0 gives a triangle, which is not centrally symmetric. A compatible polyhedral/constrained representation or an explicitly labelled enclosure is required. A general convex terminal minimizer set may also fall outside a finite V/H representation. These are separate questions from the history bijection. Robust/adaptive information patterns, finite/hybrid controls, arbitrary temporal relations and general bounded-memory realizations remain outside the proof.

The preservation base is `34fbb1410a53686198ed9dd8841241cf4cd745fd`. At that base the only tracked first-experiment manifest is [B04-historical](../../benchmarks/scenarios/b04-historical.json). Its exact Windows-worktree-byte SHA-256 before and after this curation is `167f836bd07c19df67ce9159b06b7b3ecb7396875ce53f2fdd3b76910994f278`. The baseline committed LF blob has SHA-256 `92900c07ac4b1ce2f889a99023809e789110e77d7416cd192facc3ffc89d072d`; this distinguishes Git checkout conversion from a source-data change. Semantic inspection confirms its original identity `B04-historical`, `executable: false`, unresolved `controls.stage_sets: null`, stagewise state bounds and `new_temporal_constraints: []`. Its missing inputs and historical inconsistency remain recorded. Hash preservation does not turn it into an executable or reproduced benchmark. No new scenario is introduced here. Every future constrained variant needs a separate scenario ID, compatible algorithm and its own evidence.

### Original issue 9 acceptance coverage

| Original acceptance criterion | Curated evidence and boundary |
|---|---|
| Audit both directions, previous input and absolute-bound index | §1 proves inverse maps on complete histories, fixed p0, no U[−1], no forced p0∈U[0], and S[t+1]=X[t+1]×U[t]; first-step exception and recorded elapsed time are explicit |
| Check L01 pp.1–4 and L11 pp.6–9 assumptions | §§2–4 and the owning-source crosswalk distinguish fixed A/B/P, linear versus Euclidean objectives, literal dimensions, compact domains, equality support, offsets and inverse assumptions; supplementary pages own recovery observations |
| Distinguish hard slew from do-mpc penalty | §1 identifies the hard feasible relation and limits the official set_rterm reference to its input-rate penalty and matrix structure |
| Review capability declarations and unsupported cases | §6 saved-code crosswalk and this section inspect current declarations/guards, preserve their rejection and exclude unsupported nominal-to-robust, arbitrary-memory and representation claims |
| Preserve first manifests; separate future constrained IDs | The exact baseline hash and manifest semantics above are preserved; a future constrained scenario must have a distinct identity |

This evidence covers the original theory/source/capability/preservation audit. The current issue status in provenance is a dated curation snapshot, not a live tracker assertion or automatic closure. A controller's final acceptance review owns issue closure. The independent antecedent recheck alone did not close it. EXT-03 is a separate implementation obligation and is not an additional requirement for completing this audit.

Before enabling a selected EXT-03 adapter, establish exact coordinate/time mapping and initial-memory provenance; empty/infeasible behavior; any required rank/invertibility evidence; stage indexing in both directions; affine offset or fixed-one slice handling; equality/degeneracy and intersection/conversion correctness; the whole terminal minimizer set; complete transition-relation recovery and physical reconstruction; and arithmetic/tolerance/assurance limits. Exact short-horizon relation oracles should include varying U[t], a first-stage exception, nonzero p0/a[t] and multiple terminal memory coordinates. Such tests validate that selected implementation against the proof, not every legacy algorithm.

## 8. Exact reference checks and limits

[check_temporal_lift.py](tools/check_temporal_lift.py) runs nine standard-library checks with `fractions.Fraction`, including under `python -O`. It writes no files and executes no archived code. Comparisons use independent literal outcomes; equality between two implementations is not the oracle.

The two affine LTV stages from the [original note](temporal-coupling.md) produce physical states `(2/5,−8/7)` and `(1/2,−31/70)`, memory coordinates `1/5` and `−1/10`, and increments `9/20` and `−3/10` from p0=−1/4. Direct dynamics, block lifting and the fixed-one homogeneous form each meet those literals. Inverse recovery returns `(2/3,−4/5,−1/4)` then `(2/5,−8/7,1/5)`.

A stage-index check uses p0=2, U[0]=[0,1], U[1]=[−1/2,0], no first-step slew and D[1]=[−1,1]. D[0]=[−2,−1] admits u0=1/2; the next increment −3/4 gives u1=−1/4. Both current absolute bounds hold, while imposing U[0] on the second action or p0 would reject valid data. Positive durations 1/2 and 2 with physical rates [−1/4,1/4] give increment sets [−1/8,1/8] and [−1/2,1/2].

The other literals reproduce terminal intervals [7/4,2] versus [0,2], squared minima 49/16 versus zero, the terminal memory fibres at a=−1,0,1, the omitted optimal witness with (x1,x2)=(1,0), and the four-state embedding. Finite point checks do not certify entire intervals, all optima, convex geometry or a continuum maximum; the analytic proofs in §§1–5 own those conclusions. No historical run, product optimizer, floating-point certification, performance result or published experiment failure is claimed.
