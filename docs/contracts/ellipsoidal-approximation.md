# Directional ellipsoidal approximation (APP-04)

Include `<csl/geometry/approximation.hpp>` and `<csl/geometry/ellipsoidal.hpp>` and link `CSL::approximation`. Register `make_directional_ellipsoid_registration(method, output_id, orientation_rows)` on `ApproximationPort`, then call `run_registered`. The method ID identifies the orientation; use different IDs for different orientations. The output representation is `csl.ellipsoid.directional2d` with `SetRelation::outer`, numerical assurance and a budget of at least one primitive.

The input must be a native, nonempty, bounded planar V set with no rays. The `2×2` orientation matrix `B` must contain finite stored binary64 values and have a nonzero exact determinant. The adapter chooses coordinate midpoint `c`, computes an outward binary64 bound `m_i` on every stored vertex projection `|B_i(v-c)|`, and stores a nonnegative radius `r_i` satisfying the exact stored-value inequality `r_i² ≥ 2m_i²`. A zero bound has zero radius. An unrepresentable bound or radius refuses.

The output set is

```text
E = {x : sum over r_i>0 of (B_i(x-c)/r_i)^2 <= 1,
         B_i(x-c)=0 for each r_i=0}.
```

Its real-arithmetic shape `Q=B^-1 diag(r_i²) B^-T` is positive semidefinite, including line and point degeneracies. Every source vertex contributes at most one half to each squared normalized term, so convexity encloses the V hull. The independent approximation policy imports the immutable native payload and checks every vertex against its stored projected bound before returning `StructuralBasis::v_ellipsoid_containment`. A provider claim alone cannot establish the relation. `EllipsoidSet::support` returns a numerical value or a diagnostic if finite evaluation is unavailable; it is not a validated-rounding claim.

`run_ellipsoid_family` runs each method through that policy. A nonempty finite family of reviewed outer members denotes their **intersection**; a reviewed inner family would denote their **union**. The family retains each separate ellipsoid and evidence and does not expose a single ellipsoid or infer support of the intersection from member supports. APP-04 supplies no native inner producer, so inner requests refuse through the available registrations. Mixed or unreviewed members cannot enter a family.

These enclosures concern mathematical sets defined by the stored binary64 coefficients. They do not give a global error bound, validated rounding of earlier model computations, a minimum-volume ellipsoid, or a verified result from MATLAB or the Ellipsoidal Toolbox. The [source audit](../research/ellipsoidal-comparison.md) distinguishes the archived example from this native route.
