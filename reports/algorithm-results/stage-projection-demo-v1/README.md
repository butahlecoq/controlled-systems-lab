# Stage projection demonstration bundle v1

These files are illustrative model demonstrations, not benchmark results or
claims about optimal control. The fuel example is a 4D affine open-loop system
with independent controls in `[-1,1]` at five stages and zero disturbance.
Its four paired projections are stored in source-bound stage batches and
rendered offline from those batches.

## Fuel figures

- [Flow/flow: oxidizer flow x1 vs fuel flow x3 (PNG)](fuel-four-state-figures/projection-01-x0-x2.png) · [SVG](fuel-four-state-figures/projection-01-x0-x2.svg)
- [Stock/stock: oxidizer stock x2 vs fuel stock x4 (PNG)](fuel-four-state-figures/projection-02-x1-x3.png) · [SVG](fuel-four-state-figures/projection-02-x1-x3.svg)
- [Oxidizer flow x1 vs fuel stock x4 (PNG)](fuel-four-state-figures/projection-03-x0-x3.png) · [SVG](fuel-four-state-figures/projection-03-x0-x3.svg)
- [Oxidizer stock x2 vs fuel flow x3 (PNG)](fuel-four-state-figures/projection-04-x1-x2.png) · [SVG](fuel-four-state-figures/projection-04-x1-x2.svg)
- [Fuel offline HTML index](fuel-four-state-figures/index.html)

Each panel shows stored projected V generators for R0 through R5. The dashed
green path is the fixed `u=1` illustrative control history. Negative fuel
stock values are retained. No hull boundary is reconstructed from the stored
points.

## Nonfuel figure

- [Planar integrator projection (PNG)](nonfuel-integrator-figures/projection-01-x0-x1.png) · [SVG](nonfuel-integrator-figures/projection-01-x0-x1.svg)
- [Nonfuel offline HTML index](nonfuel-integrator-figures/index.html)

The source-bound batches, rendering manifests, bundle manifest, and
`SHA256SUMS` are included beside these figures. Regenerate with the command in
[`benchmarks/reporting/stage-projection/README.md`](../../../benchmarks/reporting/stage-projection/README.md).
