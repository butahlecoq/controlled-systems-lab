# Ellipsoidal comparison: archived example and independent oracle

Date: 2026-10-17; updated 2026-10-19. Scope: archived source audit and an independent analytic oracle for [APP-04](../superpowers/plans/tickets/APP-04.md). The native implementation uses a separate planar V-to-ellipsoid route; no Ellipsoidal Toolbox (ET) result has been recorded.

## Archived A05 example

The [selected-source register](archive-selected-sources.json) identifies A05 as `Scientific Research/ELL_OD.m`, 1,313 bytes, SHA-256 `779042de1ee4a920f523a8e2e4d8282d6c49c923c5917693bf3d0185b725b47f`. A read-only SHA-256 check of the private original matched that digest on 2026-10-17. The observations below come from static inspection of that exact file; neither it nor its dependencies were executed. Line numbers refer to the registered original.

| A05 lines | Active source behavior | Limit of the observation |
|---|---|---|
| 4–12 | Set `N=3`; construct a two-dimensional initial vertex set, `Polyhedron` `P(1)`, and `ell_enclose(P(1).V')`. Construct a control segment `U` from the input row and scalar amplitude. | No `ell_enclose` implementation, version, or returned shape is identified by the source. |
| 13–17 | Transform `P(1)` vertices and form `P(2)` by adding `U`; call `ell_enclose` on `P(2)` vertices. | The source supplies no independently checked enclosure relation. |
| 23–30 | For the only loop iteration (`i=2`), transform `P(2)` vertices to `P(3)` without adding `U` again. | This is not a repeated-control propagation model for all stages. |
| 31–43 | Commented ET-style `ell_unitball`, `linsys`, `ellipsoid`, `reach`, and `cut` statements are inactive. The active loop calls `ell_enclose(P(i).V')` for all three polytopes and plots those results. | The plotted objects are not an executed ET reachability comparison or a saved numerical result. |

The [archive follow-up](archive-followup.md) reports that the executable ellipsoidal library dependency was not located in its targeted scan. A05 has no pinned `ell_enclose` source, environment, output record, or inclusion certificate in the selected archive. Its function name cannot by itself establish outer inclusion, minimality, PSD handling, or equivalence with ET. It is evidence of a historical enclosure *attempt* and display workflow, not a reproducible native benchmark. The broader [representation review](../architecture/set-representations-and-ellipsoidal-toolbox.md) also records that a separate ET distribution was absent from the supplied inventory.

## Independent analytic T-G02 oracle

This fixture is authored here, separate from A05's coordinates and historical calculations. Let `S = [-1,1] × [-1,1]` and define `E(c,Q) = {c + Q^(1/2) z : ||z||₂ ≤ 1}` for symmetric positive-semidefinite `Q`. Candidate enclosures are the unit disk `E_in = E(0,I)`, radius-`√2` disk `E_out = E(0,2I)`, and degenerate horizontal segment `E_seg = E(0,diag(1,0))`. All three shape matrices are PSD, including the rank-one shape of `E_seg`.

For every direction `l=(l₁,l₂)`, their support functions and the square's support obey

~~~text
h_E_seg(l) = |l₁| ≤ h_E_in(l) = √(l₁²+l₂²)
            ≤ h_S(l) = |l₁|+|l₂|
            ≤ h_E_out(l) = √2 √(l₁²+l₂²).
~~~

The middle inequality is immediate from nonnegative cross terms; the last is Cauchy–Schwarz. Support order for compact convex sets gives `E_seg ⊆ E_in ⊆ S ⊆ E_out`. This proves the expected *direction* for a literal low-dimensional test, including a degenerate input; it does not select a unique approximation algorithm or prescribe these exact shapes for every adapter. A future T-G02 test should query the implemented public approximation path, require its stated input class and PSD/degeneracy policy, and independently check the returned relation rather than trusting a direction label. A finite intersection of certified outer ellipsoids remains outer and a finite union of certified inner ellipsoids remains inner; neither operation generally returns one ellipsoid, as the [representation review](../architecture/set-representations-and-ellipsoidal-toolbox.md) explains.

## Current APP-04 boundary

The native adapter takes a bounded nonempty planar V set and computes a directional outer ellipsoid with exact stored-binary64 vertex inclusion checks. It handles zero-width directions and keeps finite outer intersections as families. The square above is its independent low-dimensional oracle. The native route is not the archived `ell_enclose` implementation, and no ET or MATLAB comparison has been run. An optional external adapter would first need an identified ET version, pinned input and actual saved output. No missing dependency is treated as verified.
