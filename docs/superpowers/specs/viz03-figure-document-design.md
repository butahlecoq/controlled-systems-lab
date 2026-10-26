# VIZ-03 saved figure document

## Problem

VIZ-03 needs figures that can be regenerated from saved records without starting
a solver or geometry provider. The C++ `PlotData` and `PlotOutcome` types already
distinguish selected witnesses, mathematical projections, and support samples,
but are not persisted. The existing Python plotting adapter consumes a separate
LP/convex timing schema. B06 and B07 contain real saved 4D fuel terminal-set
projections, but not stage histories; the exporter must not infer histories from
those projected sets.

## Usage

```sh
python scripts/reports/control_figures.py \
  --input reports/algorithm-results/b06-owner-confirmed-7df01ba3af5e4c46/figure-data.json \
  --style scripts/reports/styles/control-v1.json \
  --out build/fuel-figures
```

Capture code persists selected witness trajectories or already materialized
projection points into a `csl.plot-document/1`. Offline adapters convert saved
B06/B07 records into the same document. Rendering loads, validates, and formats
that document only.

The current document does not represent a sequence of reachable-set marginals.
Witness traces may have one state point per stage, but that does not supply set
geometry for those stages. Issue #708 defines an additive, versioned batch for
R0 through RT and leaves the trajectory semantics and reader contract here
unchanged.

## Shape

The JSON document is a closed, versioned report boundary with source-record
hashes, scenario/method identity, ordered coordinate schema, evidence and
assumption labels, and a list of series variants: stage-aligned witness traces,
2D projections of already-persisted points, support samples, and performance
timing. Timing values retain metric kind, availability, and inclusive/exclusive
semantics. Unknown variants, nonfinite coordinates, missing source bindings,
invalid stage lengths, or projections without coordinate bindings fail at load
time. Unsupported set encodings fail closed; the renderer has no native geometry
or solver dependency.

SVG and PNG output use the pinned Matplotlib adapter and versioned style config.
An export receipt records input/style hashes, tool versions, output hashes, and
export wall duration separately from solve/query measurements. B06/B07 figures
retain their distinct source assumptions and numerical assurance labels. A
separate trajectory fixture validates stage-aligned control steps and negative
stock visibility; it is not presented as a B06/B07 result.

This boundary hides file-format parsing, chart dispatch, formatting, and export
metadata from callers. Callers still bind source identity, coordinates, method,
and evidence because those are scientific facts the renderer cannot infer.

## Synthesis decision

Candidate 2 (`Persisted PlotDocument`) is the base: it gives a compact
language-neutral saved-data boundary, explicit provenance, and fail-closed
handling for unsupported representations. The independent judge agreed with
that choice. Candidate 1's explicit timing panel and its clear separation of
trajectory, projection, and support-sample series are included. Candidate 1's
additional public C++ codec surface is deferred because the current repository
has no persistence bridge for `PlotOutcome` and a generic `SetHandle` encoder
would overstate supported geometry. Report-specific B06/B07 adapters consume
validated saved records instead. Extending the LP/convex report schema was
rejected because it represents a different domain.

## Tradeoffs accepted

- We accept a report-specific versioned schema in exchange for an offline
  renderer that cannot call geometry or a solver.
- We accept explicit unsupported-data errors in exchange for never drawing
  incomplete sets as complete projections.
- We accept separate saved trajectory fixtures when source bundles contain only
  terminal projections, rather than reconstructing unavailable histories.

## Verification

Integration tests compare validated figure series with analytic fixture values,
inspect exported SVG/PNG content and metadata, and document a human visual check
for clipping, overlap, legends, and negative balances. Exact-pixel assertions
are not used.
