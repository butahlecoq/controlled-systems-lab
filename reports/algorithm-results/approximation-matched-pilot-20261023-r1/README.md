# Matched approximation pilot: exact diamond input

## Finding

On one exact 2D diamond with area 8, the rotated parallelotope preserved the
exact set (area ratio 1). The axis box and zonotope axis cover both had area
ratio 2. The directional ellipsoid had area ratio π. The exact QuickHull
polygon matched the four literal diamond vertices. These are fixture-specific
geometric observations, not guarantees about other inputs.

The seven-call median timings were 4,750 ns for QuickHull, 12,991 ns for the
axis box, 21,023 ns for the rotated parallelotope, 14,876 ns for the zonotope
axis cover, and 17,042 ns for the directional ellipsoid. See
[`summary.csv`](summary.csv) for ranges. Timing is descriptive and does not
support a winner: QuickHull times its public hull function, while approximation
calls include provider preparation and workspace creation. No source-mapped
limiter profile was collected.

Open [`index.html`](index.html) for the standalone figure and measurement table.
All 40 captured rows passed: five one-call warmups and seven interleaved
measured rounds for each of five methods. [`raw-rows.jsonl`](raw-rows.jsonl)
preserves every call.

[`request-identities.json`](request-identities.json) records the shared input
descriptor hash and the method-specific request, relation, source
representation and output budget. [`comparison-record-migration.md`](comparison-record-migration.md)
maps these fields toward the future #83/#84 record while naming the missing
fields and verification gates. The mapping is proposed only; no comparison
record is synthesized from this pilot.

## Fixture and checks

The common point input is `[(0,2),(2,0),(0,-2),(-2,0)]`, whose exact hull is
`|x|+|y| <= 2` and whose area is exactly 8. The zonotope side uses the
equivalent generator representation centered at `(0,0)` with independent
generators `(0.5,0.5)`, `(0.5,0.5)`, and `(1,-1)`. Splitting the first
generator into two half-length factors preserves its represented set; an
output budget of two forces the axis-cover reducer to use the remaining-factor
cover. Complete input details are in [`input.txt`](input.txt).

The exact polygon side verifies that QuickHull returns exactly the four
literal corners. The axis-box and parallelotope sides verify exact returned H
rows plus `run_registered`'s exact stored-binary64 V-to-H containment check.
The parallelotope rows `±(x+y) <= 2` and `±(x-y) <= 2` define the same diamond.
The zonotope side checks the admitted exact generator-axis cover, centered
origin, axis-aligned two-generator output, and area 16. The ellipsoid side
checks exact dyadic projection bounds and radius admission; its displayed area
uses the standard analytic formula `π r₁ r₂` for the returned identity-oriented
ellipse. The independent admission checks concern only this bounded finite
input and these native output forms.

## Measurement environment

The capture used a GCC 16.2.1 / C++20 Release build, CMake 3.31.6, Linux
x86_64 kernel `7.2.5-3-omarchy`, and one process on an 8-core host. The load
average before capture was 0.64, 0.66, 0.72. Each method ran in an interleaved
order after one excluded warmup. Set construction and output checks were
outside the timed interval. Provider selection, preparation and workspace
creation were inside each `run_registered` interval; the QuickHull interval
covers only `quickhull_2d`. Timings therefore are not a fair speed ranking.

The source code under `benchmarks/reporting/approximation_pilot/`, accepted
build log, before/after host snapshots, exit status, executable SHA-256 and
per-file checksums are retained with this bundle. Two failed driver-compilation
attempts and their dispositions are kept under `rejected/`; they produced no
measurement rows. `source-identities.sha256` preserves the capture-time input,
driver, build configuration, and renderer identities. The separate
`reporting-source-identities.sha256` records the current report renderer; that
renderer regenerates derived artifacts but did not produce the timed rows.
`summarize.py` validates schemas, warmup/round counts, outputs and geometric
ratios before regenerating the raw-row copy, CSV, SVG, and HTML.

This preliminary bundle does not satisfy or close comparison-program issue
#100, which still requires its configured producers and full independent
comparison contract. It is not registered in the publication catalogue and
has not been deployed to Pages. Its `passed` rows are fixture-check outcomes,
not globally verified inclusion results.
