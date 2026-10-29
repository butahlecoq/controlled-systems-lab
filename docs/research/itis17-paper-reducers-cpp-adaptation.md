# ITIS'17 paper-derived reducer adaptations

This note documents the separate A43 and A44 implementation identities used by
the follow-up EXP-06 fixture. The authoritative method descriptions and source
hashes remain in [the comparison research note](itis17-hull-methods-quickhull-comparison.md)
and the local source register. These implementations are source-derived C++
adaptations, not faithful ports of a recovered historical implementation.

## A43 (Bulaev–Shorikov)

`csl.hull.itis17.a43-artificial-basis` performs one Phase-I solve for each
candidate point against the currently retained other points. It maps the
resulting feasible basis back to source point indices, then tests nonbasic
points against the same basis coordinates. A point is removed only after an
exact dyadic convex-combination certificate succeeds. The final retained set
also passes the generic LP reducer's complete membership recheck.

`csl.hull.itis17.a43-largest-norm-tie` uses the same candidate/basis flow, but
assigns priority to structural columns by the Euclidean norm of their
homogeneous point `(x, 1)`. The Phase-I implementation uses this priority only
when two eligible structural columns have exactly equal computed reduced
costs. It records the number of times the priority selected a tie. The
comparison must inspect that counter before claiming this fixture exercised
the tie rule.

Deviations and limits: this re-expression uses CSL's binary64 Phase-I
implementation, its numerical tolerances, exact-dyadic deletion certificates,
and a final independent LP recheck. The paper's claim that its modified pivot
rule makes all basis points extreme is not relied upon. The certificate gate
and final recheck are safety additions. The implementation does not reproduce
an unspecified historical tableau/pivot schedule, and the paper does not give
a general degeneracy proof for its tie rule.

## A44 (Goranov–Shorikov)

`csl.hull.itis17.a44-incremental-lp` retains the existing explicit adaptation:
box-center normalized Euclidean distance, farthest-first ordering, a `k+1`
seed, incremental membership checks, and a final full recheck. The source's
conflicting increasing-distance/most-distant prose is unresolved; this run
uses the farthest-first interpretation and does not present it as settled
historical behavior.

## Comparison boundary

All methods receive the same nine-point square manifest, and retained source
indices are checked by the independent exact binary64 hull oracle. Incomplete
solver outcomes remain incomplete even when the returned retained points pass
the hull check. The A29 Python port and the native C++ methods have different
runtime and timing intervals, so this capture is a correctness and algorithm
evidence pilot; it does not support speed rankings. The original Pascal
implementations were not found in the registered papers, repository history,
or available source files, so no Pascal runtime row is fabricated.
