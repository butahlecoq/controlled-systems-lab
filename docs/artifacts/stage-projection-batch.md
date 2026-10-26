# Saved stage projection batches

`csl.stage-projection-batch/1` stores 2D reachable-set projections for each
requested coordinate pair and route stage. Its JSON schema is installed with
the other artifact schemas. The C++ codec writes batches; the Python reader
validates them for offline renderers. This wire format does not change
`PlotData` or `csl.plot-document/1`.

Each record has a stage ordinal and a pair ordinal. The pair list retains the
requested order, including reversed pairs. A successful record contains the
relation and assurance claim, provider identity, evidence, and one or more
geometry components. A component using a V representation means
`conv(vertices) + cone(rays)`; the vertices are not assumed to be cyclically
ordered. Empty geometry has no vertices; its rays are retained when supplied
by the source representation. Unbounded geometry has a finite base vertex and
at least one nonzero recession ray. Zero-image rays are retained for bounded
geometry. Point, segment and polygon distinguish numerical affine dimensions
zero, one and two using the shared binary64 determinant predicate. Multiple components
remain separate so renderers do not fill the gaps by convexifying them.
Redundant V vertices are preserved, including duplicate point vertices and
interior collinear segment vertices; readers validate affine dimension rather
than requiring a minimal vertex list. Stage and physical-time axes are
nonempty and strictly increasing.

Unavailable outcomes identify missing, unsupported, or stopped stages.
Stopped outcomes preserve their stop reason and diagnostics. Failures retain
the failure class and diagnostics, including stop details when applicable.
Optional trajectory series are stored in their own top-level field and never
imply reachable-set geometry.

The document binds to a source run, problem, request, route and source-record
SHA-256. `content_sha256` is SHA-256 over the UTF-8 canonical JSON document
with `content_sha256` omitted, sorted object keys, and no insignificant
whitespace. Readers must also compare the source identity with the trusted run
manifest; the content hash detects edits but does not authenticate a producer.

```python
from pathlib import Path
from scripts.reports.stage_projection_data import read_stage_projection_batch

batch = read_stage_projection_batch(
    Path("stage-projections.json"),
    expected_run_id="run-17",
    expected_problem_id="fuel-v1",
    expected_request_id="projection-request-2",
    expected_route_id="direct-minimax",
expected_record_schema="csl.run-statistics/7",
    expected_source_sha256="a" * 64,
)
```
