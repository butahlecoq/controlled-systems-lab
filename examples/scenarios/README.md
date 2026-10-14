# Editable scenario templates

These executable examples use the strict `csl.scenario/1` JSON format and the
public file loader. They demonstrate a minimal LTI model, stage-specific state
constraints, an LTV model, and the supported linear, quadratic and residual-norm
terminal objective forms. The loader validates and publishes problem data; it
does not run an optimizer or claim that the illustrative histories are optimal.

| File | Model and feature | Illustrative controls | State history | Original terminal objective |
| --- | --- | --- | --- | --- |
| `minimal-lti-linear.json` | Scalar LTI, unconstrained states | `(0.5)` | `(0, 0.5)` | `x = 0.5` |
| `state-constrained-quadratic.json` | Scalar LTI, box state set at all three time indices | `(0.25, 0.75)` | `(0, 0.25, 1)` | `x² - 2x + 1 = 0` at `x = 1` |
| `ltv-residual-norm.json` | Scalar two-stage LTV | `(1, 0)` | `(1, 2, 4)` | `||(x - 5, 0)||₂ = 1` at `x = 4` |

The histories and objective values in the table are hand-derived examples used
as independent loader/model/evaluator oracles. They are not solver output,
feasibility certificates for any future semantics, or optimality claims. The
quadratic convention is `0.5 xᵀQx + qᵀx + c`; a residual-norm objective is
`||Lx - target||₂` and is not squared. Dynamics use `x[t+1] = A[t]x[t] +
B[t]u[t]` once per discrete transition.

The incomplete archival record `benchmarks/scenarios/b04-historical.json` is
intentionally separate and non-executable. Do not copy unresolved historical
values into executable templates or treat the archived objective as replayed.
See [the scenario input contract](../../docs/contracts/scenario-input.md) and
[the schema notes](../../schemas/scenario/README.md) for the full grammar,
defaults and rejection rules.
