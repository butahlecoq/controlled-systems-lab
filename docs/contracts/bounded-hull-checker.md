# Bounded source-index hull checker (TEST-25)

`<csl/geometry/bounded_hull_checker.hpp>` and `CSL::bounded_hull_checker`
provide an independent exact oracle for a finite 2D source-index hull. The
checker is for completed outputs, after algorithm timing. It does not run an
LP, use QuickHull's hull construction, compare vertex lists, approximate by
volume, or sample support directions.

`digest_hull_input` hashes a versioned byte manifest: point count, each row's
dimension, and every binary64 coordinate bit pattern, in input order and
little-endian encoding. Source indices are positions in that exact manifest.
The checker recomputes its digest and rejects a different output digest,
duplicate indices, and out-of-range indices. It checks **every input point**
against the hull of the reported source points. Permuting inputs or changing
even an interior coordinate changes the digest. The digest identifies supplied
binary64 values; it does not certify pre-rounded real-world measurements.

The oracle enumerates reported points, pairs, and triples. Exact expanded
orientation signs establish point-in-segment and point-in-triangle membership
over the represented dyadic coordinates. By Carathéodory's theorem in two
dimensions, a point lies in a finite convex hull exactly when one such subset
contains it. This is independent of the compared hull algorithm. Redundant
interior and non-extreme edge points are accepted. An omitted extreme corner
produces the first uncovered input index as a concrete counterexample. Empty
input with empty output is verified; a nonempty input with empty output is
incorrect.

`HullCheckBudget` defaults to five seconds and 64 points. Both wall time and
point capacity are configurable. The checker tests the deadline during
enumeration and reports elapsed time, requested budget, status, reason, and
the evidence scope `exact represented binary64 2D finite hull`. A deadline,
capacity limit, unsupported dimension, nonfinite input, arithmetic failure,
or checker exception yields `inconclusive`. `incorrect` requires a concrete
digest/index mismatch or uncovered input point. A `verified` claim covers only
finite 2D source-index hull equality for the bound input manifest; it says
nothing about minimality or vertex ordering. Wall-time checks are cooperative
within this in-process bounded oracle; a supervising comparison worker must
enforce its own hard wall/memory cap when those are required.

`record_bounded_hull_attempt` retains an algorithm failure separately from
checker status; an algorithm without a hull cannot become verified. The
`run_bounded_square_smoke` path uses a deterministic dyadic square with four
corners, an interior point, and four non-extreme boundary points. It exercises
modern QuickHull2D only. It is **not** a legacy-versus-modern comparison,
benchmark, performance claim, or historical reproduction.

`<csl/artifacts/bounded_hull_check.hpp>` serializes the checker observation as
canonical `csl.bounded-hull-check/1` JSON under
`docs/artifacts/schemas/bounded-hull-check-v1.schema.json`. The codec tests all
three statuses and rejects inconsistent or malformed fields. Imported checker
records are inert observations; decoding `verified` does not rerun the proof.
`csl.comparison/1` currently has no checker field, so attaching this observation
to a paired comparison requires a later comparison-record revision. This
bounded checker does not close EXP-06 #423, OBS-04 #83, OPT-13 #424, or the
broader algorithm differential suite TEST-19 #57.
