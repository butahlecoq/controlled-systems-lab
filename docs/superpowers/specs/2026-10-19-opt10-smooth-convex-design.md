# OPT-10 declared smooth-convex feasible directions

## Intent and scope

Issue #50 asks for an executable optimizer for caller-declared differentiable convex objectives over the existing linear row and variable interval contract. It extends the reviewed OPT-09 projection primitive. The output is one numerical point and its evidence; it is not a complete optimal family or a validated convexity certificate. The historical A06 `ALOWER` routine remains an archival reference, not an implementation identity.

## Public contract

`csl::optimization::feasible_directions::minimize` receives a checked `LinearProgram` solely as its feasible-set description, a supplied feasible start, a `SmoothObjective` with a stable ID, value and analytic-gradient callbacks, an explicit `declared_convex` property, a caller-owned `LPWorkspace`, `ExecutionContext`, and a bounded policy. The objective declaration is an assertion by the caller. Unspecified or nonconvex objectives are `Unsupported`; no runtime sampling upgrades that assertion to a proof. Dimension, callback presence, policy ranges, and start feasibility are boundary checks. An infeasible start returns a field-specific diagnostic and is never repaired silently.

`SmoothStationary` owns the final point, value, gradient, projected-gradient residual, iteration and evaluation counts, and a reason distinguishing a zero projected direction from a tolerance stop. Its evidence label is numerical stationarity conditional on the declared convexity and the original linear feasible set. It carries no global-optimum or validated-assurance claim. `SmoothStopped` owns the last feasible point, its last finite value when available, counts, and a reason including cancellation, deadline, resource limit, callback failure, numerical failure, and line-search stall. `Diagnostics` and `Unsupported` remain separate alternatives. A late failure never returns a success claim.

## Algorithm

At feasible `x`, evaluate finite `f(x)` and analytic `g(x)` with the declared dimension. Project `x-g(x)` onto the supplied polyhedron using OPT-09 and the injected LP workspace. Its displacement `d=p-x` is the projected feasible direction. A vanishing `d` is numerical first-order stationarity; a nonzero direction must have a negative finite slope `g·d`. The projected endpoint and every accepted iterate are checked against the original constraints. Backtracking starts at `alpha=1` and stays in `(0,1]`; it accepts only finite feasible candidates satisfying `f(x+alpha d) <= f(x)+c alpha g·d`, with `0<c<1`. Stop with a distinct stall if the bounded search reaches its count or minimum step. Cancellation, deadline, projection stop, objective failure, and iteration cap retain the last accepted feasible point. The projection solver's numerical tolerance and finite arithmetic limit the stationarity evidence; no convergence rate or error bound is inferred.

## Cost and baseline evaluation

The projected-step stopping threshold is `absolute_tolerance +
relative_tolerance` in step units, independent of coordinate origin. Each
outer iteration requests one bounded projection, one gradient, and at most
`max_backtracks` extra objective values; at most `max_iterations` outer
iterations run. The sparse linear model, one backend workspace, and a constant
number of length-`n` vectors are retained. Backend memory and arithmetic cost
depend on the chosen solver and are not bounded by iteration caps alone.

A published-baseline evaluation requires a reviewed restoration of the
historical A06 objective, constraints, numeric settings, and output convention.
The first comparison would check like-for-like feasibility and objective
values, then identify analytic-gradient versus finite-difference and guarantee
differences before timing. Those inputs are unavailable for this ticket, so
the saved analytic fixture is not presented as an A06 performance comparison.

## Tests and evidence

Tests call the public API using analytic 1D and 2D convex quadratics, compare the final point and value with literal answers and an independent HiGHS convex QP solve, and check feasibility at every accepted point via a callback recorder. Cover an interior optimum, active box corner, equality face, zero direction, infeasible start, unsupported declaration, bad callback shape/nonfinite value, cancellation, bounded iteration, and a deliberately inconsistent callback that stalls Armijo. A standalone installed client checks package export. A separate saved-report harness will execute a supported two-dimensional analytic case through the public adapter, check its literal answer on every call, retain raw attempts/build provenance, and render a labelled 2D example and immutable HTML/ZIP bundle. Timings are descriptive single-adapter observations without comparator or speedup.

## Delivery boundaries

The new public header and static CMake target are additive; no dependency is introduced. The PR records installed-package impact, explicitly distinguishes the method from finite-difference `ALOWER`/`VERLIM`, and preserves the existing OPT-09 projection API. Release publication is a separate delivery decision subject to the repository's licensing gate. Report publication requires independent review, main-only deployment, and live-byte verification.
