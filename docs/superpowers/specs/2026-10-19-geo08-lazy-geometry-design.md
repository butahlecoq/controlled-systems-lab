# GEO-08 lazy geometry design

## Purpose

Allow callers to retain immutable affine-image, coordinate-projection, and independent Minkowski-sum expressions over native V polyhedra and empty sets. A caller can query support without forming Cartesian-product vertices, or explicitly request a budgeted V materialization. This is a numerical geometry route, not a validated-arithmetic or complete-family proof.

## Public route

`csl.geometry.lazy-expression` is a `GeometryPort` registration for `AffineImage`, `Projection`, and `MinkowskiSum`. It snapshots the full typed operands in a private immutable `SetPayload`, binds the result to the operation identity and ordered source IDs, and advertises `csl.geometry.lazy-v`. Nested lazy handles are accepted. Other operation variants, unsupported leaf representations, mismatched dimensions and labels, incomplete identities, or non-equivalent/validated requests reject during provider admission before workspace creation. A lazy result records the set relation and unestablished numerical evidence; mathematical closure does not certify binary64 rounding.

`csl.geometry.lazy-support` is a `GeometryPort` registration for `SupportQuery` on those handles. A V leaf maximizes vertices and checks rays; affine and projection nodes transform the query direction; an independent sum adds child support values. Empty and unbounded support retain their distinct variants. The result includes a maximizing point when finite, the full query reference, and a stated binary64 arithmetic limitation. A finite direction list produces labelled support samples, never a complete set or containment certificate.

`csl.geometry.lazy-materializer` is a `ConversionPort` registration whose caller supplies mandatory `max_vertices` and `max_rays` limits. It admits only a lazy handle and a native V output request, then visits the graph with cancellation/deadline checks. It computes row-count growth with overflow checks before allocating each intermediate, rejects a limit breach, and never publishes a partial set. A wrapper returns requested limits, estimated and realized row counts, selected provider provenance, expression lineage, and the ordinary conversion result or stop/rejection. It does not implicitly select H/V conversion or a fallback approximator.

## Numerical and ownership boundary

Native leaves use the existing immutable `SetData` payload. Nodes retain child handles by value; graph inspection verifies envelope metadata and identity against the payload. Matrices, offsets, and coordinate indices are copied into nodes. Floating arithmetic must reject nonfinite results. Support values are numerical samples with `Unestablished` support evidence because transformed directions and summed values are rounded; neither the sample nor materialized vertices prove validated inclusion. Native V rays, empty leaves, zero-dimensional coordinates, and singular affine maps remain distinct.

## Verification

Independent 1D and 2D literals check support of affine images, projections, and sums against analytic values and the existing polyhedral V support provider. Tests check the Cartesian-product vertex count, ray preservation, empty/unbounded outcomes, copied-operand lifetime, altered envelopes, preflight rejection, budget exhaustion, overflow, cancellation, and deadline. An external `find_package(CSL CONFIG)` client verifies the installed route. A discoverable labelled 2D example shows source corners, an affine/projection expression, a support direction and answer, and the explicit materialization limit without claiming a performance result.

## Delivery

The public headers and CMake target are additive. The PR records package impact and that no release is needed until project distribution terms and a release candidate are reviewed. No benchmark or historical comparison is part of GEO-08.
