# QuickHull and ITIS17-related LP hull pilot (preliminary)

Open the [standalone result report](index.html) for the measured summary and
labelled fixture geometry ([SVG source](fixture-geometry.svg)).

## Result

This exploratory run is **inconclusive as a performance comparison**. It ran
QuickHull, a per-point LP membership reducer, a basis-reuse reducer related to
Bulaev–Shorikov (A43), and an ordered LP reducer related to Goranov–Shorikov
(A44) on three tiny, literal 2D square clouds. Seven interleaved measured calls
per method and cloud passed the independent fixture checks. QuickHull medians
were 4,819–15,085 ns, the per-point LP medians were 620,478–1,188,713 ns, the
basis-reuse medians were 40,927–49,657 ns, and the ordered LP medians were
631,303–1,189,412 ns. See [`summary.csv`](summary.csv) for each median and
range, and [`raw-rows.jsonl`](raw-rows.jsonl) for all calls including warmups.

These are not winner or scalability results. The clouds have only 5–10 points;
there is no separate limiter profile or realistic end-to-end workload. The
timed interval covers the reducer/QuickHull call; LP workspace construction
and output checking are outside it. The LP reducers share injected workspace
construction policy, while QuickHull has no LP workspace. The host was lightly
loaded by the recorded before/after `uptime` snapshots, but that does not
identify a source-level limiter.

## Algorithms and paper correspondence

The two papers describe LP-based finite-point hull reduction, not geometric
QuickHull. The C++ comparison here uses existing reducers as explicitly
**related variants**, not faithful paper implementations:

| Run label | Implementation | Relation and limit |
|---|---|---|
| `geometric-quickhull` | `CSL::quickhull_2d` | Geometric 2D baseline; returns original point indices. |
| `lp-membership-baseline` | `reduce_hull` | Generic per-point convex-membership LP baseline. |
| `basis-reuse-related-to-A43` | `reduce_hull_basis_reuse` | Related to A43 basis-column reuse; not a reproduction of its largest-norm tie rule or basis-extremality claim. |
| `ordered-membership-related-to-A44` | `reduce_ordered_hull` | Related to A44 ordered filtering and final LP checks; not a paper-faithful port. |

The source PDFs are A43, Bulaev V.V. and Shorikov A.F., SHA-256
`a90a3e404807238886122dfdfc91a5f18697949137a8d9744af7180508de848a`, and A44,
Goranov A.Yu. and Shorikov A.F., SHA-256
`493917da7d8ac669a470a978780a2ca269ce9da1b594365f49c6ebd572388fd7`.
Their algorithm mapping and caveats are summarized above. No Pascal source for
either ITIS17 method was found.
The old `btulshor.pas` routine is a separate A06 method and was not run; these
numbers do not compare against an original Pascal implementation.

## Fixtures and correctness evidence

All three fixtures are subsets of the literal square `[0,2] × [0,2]`; the
four square corners are the expected extreme vertices. They cover a permuted
interior/edge-heavy cloud (10 points), duplicates and collinear edge points
(7 points), and one interior point (5 points). The reducer oracle checks
complete accounting of original IDs, unique/in-range retained and removed
IDs, exact-binary64 convex-combination verifier IDs for deletions, that every
input lies in the known rectangle, and that every expected corner remains.
The QuickHull oracle checks exact equality of returned vertex coordinates to
the four literal corners. All fixture coordinates are exactly representable
dyadic rationals, and rectangle containment makes the hull checks exact for
these inputs. Basis reuse may retain
additional redundant points; that is allowed by hull equality and is visible
in the raw `retained` counts.

The harness ran one warmup for each of 12 fixture/method pairs, then seven
interleaved rounds (84 measured calls). All 96 output rows passed and the
process exited 0. Durations are nanoseconds. The captured Release build used
GCC 16.2.1, C++20, HiGHS 1.11.0 and Linux x86_64. The build log, host snapshots,
executable hash, raw rows and summary are retained here. CMake source is under
`benchmarks/reporting/it17_hull/`; run `summarize.py` to regenerate the raw-row
copy and summary CSV from a capture.

This is an exploratory, unregistered report bundle. Its standalone HTML and
SVG are versioned offline artifacts, not a deployed Pages report. It does not
satisfy or close comparison-program issue #423, whose shared-record and other
prerequisites remain separate gates.
