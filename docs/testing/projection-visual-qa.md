# Fuel projection visual QA

The four-state fuel vector is ordered as oxidizer flow `x1` (kg/s), oxidizer
working-stock balance `x2` (kg), fuel flow `x3` (kg/s), and fuel working-stock
balance `x4` (kg). Two-dimensional plots select coordinates from this 4D
relation; the two figures below show the flow pair `(x1,x3)` and stock pair
`(x2,x4)`.

## Analytic reference

![Two analytic projections of a four-state fuel-like box. Negative stock
values are visible.](../examples/fuel-state-projections-illustrative.svg)

[PNG preview](../examples/fuel-state-projections-illustrative.png)

This is an illustrative bounded box, not B04 historical data. Its projection
relation is equivalent for the represented sets; binary64 arithmetic support
is unestablished. The numeric rectangle and segment oracles used by
`plot_request_contract` are recorded in
[`fuel-projection-analytic-oracles.json`](../../tests/artifacts/fixtures/fuel-projection-analytic-oracles.json).

## Saved B06 result

| Projection | Reference image | Visual check |
|---|---|---|
| Oxidizer flow vs. fuel flow | [PNG](../examples/fuel-b06-flow-projection.png), [SVG](../examples/fuel-b06-flow-projection.svg) | Coordinate names and kg/s units are visible; target is marked; 1,024 saved projected vertices are shown. |
| Oxidizer stock vs. fuel stock | [PNG](../examples/fuel-b06-stock-projection.png), [SVG](../examples/fuel-b06-stock-projection.svg) | Coordinate names and kg units are visible; target is marked; negative stock values remain visible. |

The B06 plots are terminal projections of the saved numerical V-representation
with binary64 solver assurance. They are not validated real-arithmetic
enclosures or historical reproductions. The source record, coordinate order,
relation caveat, and trajectory provenance are in
[`fuel-b06-viz03-source.json`](../examples/fuel-b06-viz03-source.json).

The independent C++ checks use the small analytic fixtures above and the
four-coordinate fuel-like relation. They compare ordered coordinate metadata,
projected membership at analytic corners/endpoints/interior points, and points
outside the expected boundary. A finite witness or support sample remains
labeled as such and is not rendered as a complete family boundary.
