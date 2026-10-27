# Stage projection demonstration bundle v1

These files are illustrative model demonstrations, not benchmark results or
claims about optimal control. The fuel example is a 4D affine open-loop system
with an independent scalar control in `[-1,1]` at five stages and zero
disturbance.
Its four paired projections are stored in source-bound stage batches and
rendered offline. A separate native `reachability.nominal_forward` batch records
the available prefix and explicit unavailable stages. The nonfuel example uses
the analytic demonstration adapter.

## Fuel figures

- [Flow/flow: oxidizer flow x1 vs fuel flow x3 (PNG)](fuel-four-state-figures/projection-01-x0-x2.png) · [SVG](fuel-four-state-figures/projection-01-x0-x2.svg)
- [Stock/stock: oxidizer stock x2 vs fuel stock x4 (PNG)](fuel-four-state-figures/projection-02-x1-x3.png) · [SVG](fuel-four-state-figures/projection-02-x1-x3.svg)
- [Oxidizer flow x1 vs fuel stock x4 (PNG)](fuel-four-state-figures/projection-03-x0-x3.png) · [SVG](fuel-four-state-figures/projection-03-x0-x3.svg)
- [Oxidizer stock x2 vs fuel flow x3 (PNG)](fuel-four-state-figures/projection-04-x1-x2.png) · [SVG](fuel-four-state-figures/projection-04-x1-x2.svg)
- [Fuel offline HTML index](fuel-four-state-figures/index.html)
- [Native nominal-forward capture (two available stages; explicit later gaps)](fuel-four-state.nominal-forward.stage-projection-batch.json)
- [Native route evidence sidecar](fuel-four-state.nominal-forward.stage-projection-batch.json.evidence.json)

The native route evidence sidecar retains each available marginal's geometry
evidence, H-to-V conversion evidence, and provider identities under the same
source hash as its batch, with its own content hash. The offline figure panels
show the full analytic demo's projected vertices for
R0 through R5. The separate native route batch keeps only route-produced stages
and marks unavailable stages with the provider's affine-rank diagnostic. It is
not used to fill the figure. The dashed
green path is the fixed `u=1` illustrative control history. Negative fuel
stock values are retained. No hull boundary is reconstructed from the stored
points.

## Nonfuel figure

- [Planar integrator projection (PNG)](nonfuel-integrator-figures/projection-01-x0-x1.png) · [SVG](nonfuel-integrator-figures/projection-01-x0-x1.svg)
- [Nonfuel offline HTML index](nonfuel-integrator-figures/index.html)

The source-bound batches, rendering manifests, bundle manifest, and
`SHA256SUMS` are included beside these figures. Regenerate with the command in
[`README.md`](../README.md).
