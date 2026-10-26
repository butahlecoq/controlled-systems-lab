# VIZ-10: historical and benchmark plot audit

Date: 2026-10-26. Scope: [issue #687](https://github.com/butahlecoq/controlled-systems-lab/issues/687).

The audit refreshed the 11 candidates from current `main` and records a role and
disposition for each in
[`visual-route-inventory.json`](../../scripts/reports/visual-route-inventory.json).
The original bundles, manifests, checksums, archives, and report URLs remain
unchanged. New figures are companions rendered only from saved records using
`csl-report-quantitative-v1`. Their per-figure export receipts carry source,
style, and output hashes.

| Source candidate | Role and disposition | Companion or reason |
| --- | --- | --- |
| `benchmarks/reporting/approximation_pilot/summarize.py` | Static authored diagram, exception | It draws a fixed analytic diamond and approximation shapes from authored fixture definitions, not saved run geometry. |
| `benchmarks/reporting/issue6/b07_render_projection.py` | Frozen report renderer with companion | Eight saved four-state cases are projected onto flow `(x₁,x₃)` and stock `(x₂,x₄)` coordinates; the plot shows stored terminal rows only. |
| `benchmarks/reporting/issue6/b09_render_projection.py` | Frozen report renderer with companion | Two saved four-state cases show terminal V rows and the two nonlinear replay endpoints as separate marks. The companion does not recompute the projected hull. |
| `scripts/reports/b08_exact_report.py` | Saved timing plot producer with companion | The chart reads the frozen B08 durations and marks the excluded warmup separately from measured processes. |
| `scripts/reports/exp04/render_saved.py` | Saved trajectory plot producer with companion | Two literal replay paths retain physical coordinates and disclose independent units/scales. |
| `scripts/reports/issue3/render_saved.py` | Saved timing plot producer with companion | The chart shows saved batch medians and min–max values; it does not recollect runs. |
| `scripts/reports/issue3/validated_saved.py` | Validated fixture illustration with companion | Two authored plan endpoints and the saved objective target are shown as a fixture diagram, not a solver trace. |
| `scripts/reports/issue422/build_bundle.py` | Route and bundle composer | It copies the pre-existing fixed-plan illustration; it does not create or transform its plot data. |
| `scripts/reports/issue4_volterra/render.py` | Frozen certificate renderer with companion | Saved interval endpoints are drawn as boxes. The companion does not invoke the certificate checker. |
| `scripts/reports/issue6/render.py` | Frozen B06 report renderer with companion | Existing VIZ-03 assets already provide shared-style x₁/x₃ flow and x₂/x₄ stock projections. |
| `scripts/reports/render.py` | Publication exporter/validator | It validates and copies an externally supplied saved plot; it is not a plot producer. |

The new gallery is [`docs/examples/viz10/index.html`](../examples/viz10/index.html).
It links to the immutable report sources and identifies the saved inputs in the
export receipts. B07 and B09 state coordinates are 4D model coordinates; the
two displayed panels are projections and do not imply a filled projection
boundary or preserve all cross-coordinate dependencies. Replay endpoints are
not presented as robust-set vertices.

No solver, hull, geometry, numerical experiment, or benchmark ran to make these
figures. The change affects report presentation only; it adds no API,
dependency, installation, or package changes, so no release is needed.
