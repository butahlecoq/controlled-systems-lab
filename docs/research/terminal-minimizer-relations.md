# Terminal minimizer relations (SYN-02)

This note derives the relation independently of the optimizer implementation. Let C be a nonempty convex feasible terminal set and a in C an attained finite global minimizer. Exact statements below assume exact arithmetic and the stated convexity conditions. Closed polyhedral C is the implemented representation; nonpolyhedral data is rejected rather than approximated.

For a linear objective c'x+b, the entire argmin is C intersect {x: c'x=c'a}. This includes c=0: the equality 0=0 adds no restriction, so every feasible terminal point remains.

For f(x)=1/2 x'Hx+q'x+b with symmetric positive semidefinite H, write d=x-a. Expansion gives f(x)-f(a)=(Ha+q)'d+1/2 d'Hd. Optimality of a over convex C implies (Ha+q)'d>=0 for every x in C (differentiate along the feasible segment at a). Both terms are nonnegative. Equality holds precisely when Hd=0 and (Ha+q)'d=0. Since Hd=0 implies a'Hd=0, the second condition is q'd=0. Therefore the entire argmin is

    C intersect {x: Hx=Ha, q'x=q'a}.

No inverse or numerical rank decision is required. Every nullspace direction compatible with C and the linear equality remains. The q equality is essential: take C=[0,1]^2, H=diag(0,2), q=(1,0), a=(0,0). Hx=Ha alone erroneously admits (1,0). For nonsymmetric authored Q the scalar quadratic uses H=(Q+Q')/2; the immutable objective validator checks this symmetric part for PSD without rewriting authored data. Its binary64 tolerance-based check is not an exact PSD proof.

For f(x)=||Lx-r||_2, squaring preserves minimizers. The image D={Lx-r: x in C} is convex. Squared norm is strictly convex on D, so two optimal residuals must coincide: if y1!=y2, the midpoint has squared norm (||y1||^2+||y2||^2)/2-||y1-y2||^2/4, strictly smaller. Thus the entire argmin is C intersect {x: Lx=La}, for rectangular and rank-deficient L alike. A zero map retains C. An unattained infimum supplies no a and this characterization must not be applied.

## Executable independent checks

Dedicated synthesis tests use literal box membership expectations. Independently derived registered analytic fixture providers exercise the characterization for boundary and target-shift cases; these are not claims of HiGHS coverage. Separate real HiGHS integration cases cover a linear face, a zero-linear-term semidefinite quadratic, and a zero-target residual map. A target-shift degenerate residual case records the real adapter returning undetermined with stationarity diagnostics and no relation. They check both endpoints and an interior point on a linear face, a constant-objective box, quadratic boundary/nullspace cases (including the necessary q restriction), a rectangular residual map and a zero residual map. These expected relations follow the derivations above, not a second evaluation of the implementation formula.

## Numerical and publication boundary

The implementation admits a generated optimization request through an already selected prepared provider, validates returned request identity and typed result metadata, and preserves original-objective bounds, raw diagnostics and execution termination. Residual objectives use the existing norm-square reformulation and retain original norm units in reported evidence. The immutable resolved objective and effective request identity are used throughout. ProgramResult preserves program-scoped evidence verbatim. Lifted OptimumEvidence keeps bound values but marks support Unestablished because the supplied slice has no proof of being the entire feasible terminal set; the construction record names its SetId.

Conditionally on the anchor being a true global optimizer, the affine characterization gives the entire argmin in exact arithmetic. The implementation does not establish that premise or numerical coverage: a binary64 optimizer point anchors an affine candidate relation. A solver status, matching objective bounds, primal residuals and numerical PSD screening do not establish coverage or exact optimality of every point in that relation. Construction support is always Unestablished. Nonfinite arithmetic is rejected; no rank cutoffs or new numerical thresholds are introduced. Tolerances are supplied by the effective request and are used only for independent candidate feasibility checks.

The output is a terminal-state relation, not an OptimalFamily. The consuming strategy must preserve lineage while joining it to joint histories, carry the retained optimum evidence, and publish through FamilyPublisher. This module has no route to CompleteOptimalFamily. A later scientifically reviewed coverage procedure or certificate is required for such publication. Numerical HTML/raw-record publication after fixed-code review remains an issue-closure gate; these functional tests establish no performance or scalability result.
