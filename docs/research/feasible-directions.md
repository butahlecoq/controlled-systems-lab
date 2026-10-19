# Declared smooth-convex feasible directions

## Contract and interpretation

OPT-10 uses the checked linear row and variable intervals of `LinearProgram` as a feasible set. The LP objective is ignored. A caller supplies a finite feasible start and a stable objective ID, dimension, value callback, analytic-gradient callback, and explicit differentiable-convex declaration. The declaration and gradient implementation are caller assertions; no finite set of callback evaluations can certify global convexity or gradient correctness. Unspecified and declared nonconvex callbacks are unsupported. Nonlinear constraints are outside this adapter's feasible-set type.

The result `SmoothStationary` is **numerical projected-gradient stationarity, conditional on those assertions**. It reports the point, objective, gradient, projected displacement norm, reason, counts and evidence label. It is one point, not a complete optimal family, a global numerical error bound, or a validated optimum certificate. In exact convex analysis, a zero projected-gradient displacement at a feasible point implies the first-order inequality and hence global minimality for a differentiable convex objective on a convex set. This floating implementation only tests a tolerance on an approximate projected displacement. It cannot establish that exact condition. `SmoothStopped`, `Diagnostics`, and `Unsupported` preserve distinct failure scopes and do not acquire a success label.

## Direction and line search

The reviewed OPT-09 adapter projects `x-g(x)` onto the original linear feasible set using a caller-owned LP workspace. The direction `d=P_C(x-g)-x` points to a feasible endpoint. Convexity of the feasible set makes every exact segment point `x+alpha d`, `0<=alpha<=1`, feasible. The implementation checks the endpoint and accepted candidates against the original rows and variable intervals under the declared numerical policy. It rejects a nonzero direction with nonnegative slope as numerical failure.

The line search begins at `alpha=1`, contracts by a factor strictly between zero and one, and accepts only finite strict objective decrease satisfying the Armijo condition `f(x+alpha d) <= f(x)+c alpha g(x)^T d` with `0<c<1`. The backtrack count and minimum step are explicit. Exhausting either returns `line_search_stall` with the last accepted feasible iterate. Cancellation, deadline, projection resource/operation stops, callback failures and iteration cap also preserve the last accepted point. A nonfinite initial objective is never retained as a valid `last_objective`.

## Relation to A06 and evidence limits

The A06 inventory identifies `ALOWER:617–764` as a finite-difference projected-gradient routine using `APGRAD`, `VERLIM`, external `FUNF`, and step policies a/b/c. This adapter requires an analytic gradient, calls the modern OPT-09 projection, and uses an explicit bounded Armijo search. It is a related modern method, not a line-by-line Pascal port or a reproduction of the archive's step policies, tolerances, runtime, or historical result. The archived objective implementation is not restored here. The independent HiGHS convex-QP comparisons and analytic examples check the supported fixtures; they do not certify arbitrary callbacks or a convergence rate.
