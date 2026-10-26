# Saved control figure data

The offline exporter consumes `csl.plot-document/1`, a closed JSON document
that separates saved numerical values from presentation. Its input boundary is
validated by `scripts/reports/control_figure_data.py`. Rendering imports only
saved values and the pinned Matplotlib adapter; it has no solver, selector, or
geometry-provider path.

`encode_plot_document_json` converts validated C++ `PlotData` trajectories,
already-selected 2D witness paths, completed finite `PlotSetProjection`
outcomes, and directional support samples into this document. The encoder
accepts only bounded finite V-representations and singletons for set-valued
outcomes, and retains support values and any finite maximizing points,
including explicit empty/unbounded outcomes. It never invokes a geometry
provider. Unsupported representations fail explicitly. Its caller supplies the source
record schema and SHA-256 so the encoded figure input remains bound to the
saved run. The document binds each
series to a source ID and method identity; projections also bind to two named
coordinates, relation/evidence text, objective context, and limitations.
Selected trajectories carry T+1 states and T controls, with explicit axes and
control interval ends. A trajectory is one selected witness, never a claim of
the full feasible or optimal family. Projection points are persisted values;
the renderer does not compute hulls or infer missing coordinates. Completed
projection and support-query durations remain separate wall-time rows. Finite support
samples have their own series kind. Timing observations retain metric kind,
availability, and inclusive/exclusive semantics; operation rows are drawn
separately and are not summed.

Versioned style settings live in `scripts/reports/styles/control-v1.json`.
Every export writes SVG and PNG assets plus `export.json`, with input and style
hashes, tool version, artifact hashes, and rendering wall duration. That duration
is separate from saved solve and query durations.

For fuel projections, `scripts/reports/adapt_fuel_record.py` adapts saved B06 or
B07 bundles. It projects the recorded four-coordinate terminal vertices onto
flow and stock pairs without recomputing geometry. B06 records include the
minimizing fixed plan. Its adapter derives one zero-disturbance history in
binary64 from the saved initial state and control catalogue plus the hashed
versioned B06 source-driver transition, and binds the scenario and driver
hashes into its trajectory provenance. The scenario has a known malformed
15-entry 4-by-4 transition matrix. The adapter verifies any supplied matrix
against the hashed driver model and does not rewrite the saved record. This is
a single derived feasible history, not a captured stage history, complete
family, or the worst-case trajectory. B07
saved records do not contain stage histories, so the B07 adapter does not
reconstruct them. The B06 figures and
reproduction commands are in
[`docs/examples/fuel-b06-viz03.html`](../examples/fuel-b06-viz03.html).

The encoder serializes selected witness paths, finite `PlotSetProjection`
outcomes, and directional support samples as a separate series kind. It does
not materialize lazy, unbounded, H-represented, empty, or universal sets.
Report adapters cover the saved B06 and B07 finite V-representations. Saved OBS-05 tables can be attached with the
`--obs05-tables` option; they are validated against their raw-record hash, and
overlapping inclusive module spans are plotted as separate rows rather than
summed.
