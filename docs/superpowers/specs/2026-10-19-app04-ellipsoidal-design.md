# APP-04 directional ellipsoidal approximation

Status: implementation design for [APP-04 #34](https://github.com/butahlecoq/controlled-systems-lab/issues/34). The live blockers APP-01 #24 and OPT-08 #22 are closed. This design does not authorize a performance or historical reproduction claim.

## Intended result

Give a bounded native two-dimensional V polytope an explicit, independently admitted outer ellipsoid. Let callers select finite orientation rows and combine several reviewed outer ellipsoids as a finite intersection. Expose the dual rule that a finite union of reviewed inner ellipsoids is inner, while leaving inner production to a separately supported route. Keep numerical and mathematical evidence distinct. The installed public API, a small visual example, and a saved numerical report must be usable without MATLAB or ET.

## Native route and formula

The admitted input is a nonempty native V set in dimension two with no rays. A registration owns a unique method ID, a nonempty output ID and a finite `2×2` orientation matrix `B` with nonzero exact stored-binary64 determinant. Distinct method IDs let one registry select multiple orientations. It offers only an outer relation with numerical assurance and one output primitive. Empty, unbounded, H, wrong-dimensional, singular-orientation, validated, and insufficient-budget requests refuse explicitly.

For vertices `v`, choose the binary64 center `c` by separately averaging each coordinate's minimum and maximum as `low/2 + high/2`. Define `m_i` as an outward binary64 upper bound on `max_v |B_i(v-c)|`, using exact dyadic products and sums of the stored coefficients. Define `r_i` as the least finite binary64 value found by upward adjustment with `r_i² ≥ 2m_i²` checked in exact dyadic arithmetic; `r_i=0` when `m_i=0`. The output is

```text
E(c,B,r) = {x : sum over i with r_i>0 of (B_i(x-c)/r_i)^2 <= 1,
                 and B_i(x-c)=0 whenever r_i=0 }.
```

Because `B` is invertible, its shape is `Q = B^-1 diag(r_1²,r_2²) B^-T`, which is symmetric positive semidefinite, including point and line degeneracies. Each stored vertex satisfies `|B_i(v-c)|≤m_i`; for each nonzero radius, its squared normalized contribution is at most one half. The vertex is therefore in `E`, and convexity includes the entire V polytope. Different `B` values can give different enclosures. The claim concerns the exact sets defined by stored binary64 data; no validated rounding or global approximation-error bound is asserted.

The immutable ellipsoid payload stores `c`, `B`, `m`, `r`, source coordinate labels and ID. Its `SetHandle` envelope is checked on import. The public accessor exposes the implicit quadratic representation and a numerical support formula with explicit refusal on nonfinite computation. It does not call a nonlinear solver.

## Admission and finite families

`CSL::approximation` registers an `ApproximationPort` for the directional V-to-ellipsoid route. `run_registered` independently imports the native source and output payload, verifies each vertex against the stored `m`, verifies `r_i²≥2m_i²`, checks shape and budget, and returns a new structural inclusion basis. It never promotes a provider's asserted relation by itself.

An immutable finite-family result records the common reference identity, member ellipsoids and relation. Its set semantics are **intersection** for outer members and **union** for inner members. A family builder runs each member request through `run_registered` and requires an enclosed result with matching reference, dimension, labels and direction. A finite outer intersection retains outer inclusion; a finite inner union retains inner inclusion. Empty families and mixed relations refuse. The family is not a single ellipsoid, and its support is not the minimum or maximum of member supports by assertion. This ticket registers no inner ellipsoid producer, so it makes no inner-result claim.

## Verification and delivery

Independent planar oracles include the square `[-1,1]²`: identity orientation yields `E(0,2I)` and support `√2‖l‖₂`, while the square has support `|l_x|+|l_y|`. Exact vertex inclusion checks establish the complete convex-hull relation; direction samples are only diagnostics. Tests cover a rotated orientation, rank-one and point degeneracy, invalid PSD/shape and forged-envelope attempts, an unbounded input, budgets, cancellation and unsupported assurance. An external installed `find_package(CSL CONFIG)` consumer exercises the public route.

A saved Release driver records the complete input, selected provider, literal output and independent oracle observations, raw per-repetition rows, failures, timing scope, host/build/source receipts, HTML, labelled 2D SVG, manifest and offline ZIP. It makes no competitor or speedup claim. A reviewed allowlisted adapter stages the immutable bundle to Pages, and deployment is verified against committed bytes.

The archived A05 source calls an unidentified `ell_enclose` and does not furnish its implementation or a verified ET result. The [ET 2.0.1 calculus manual](https://systemanalysisdpt-cmc-msu.github.io/ellipsoids/doc/chap_ellcalc.html) documents PSD ellipsoids, affine images and directional sum families; those formulas are background, not evidence that this native V-polytope route reproduces ET. No MATLAB dependency or ET comparison is required for the native package. The source dossier belongs in `docs/research/ellipsoidal-comparison.md` with the optional external adapter explicitly deferred.
