# B08 comparison-record bridge

The B08 bundle is frozen evidence from one saved SCIP capture per formulation. The comparison bridge reads its saved scenario, solver output, exact oracle, and 2D disturbance-tube figure, then derives a separate `csl.comparison-record/1` archive through the production run and comparison codecs. It never invokes SCIP or rewrites the source bundle.

The record uses `csl.comparison-spec/2`. The capture has zero warmups, while the validated `/3` environment contract requires one warmup; assigning `/3` would misstate the evidence. Both arms share the same displayed L04 case and request identity. The continuous-control QCP is explicitly a relaxation with a different feasible set, so its solver lower bound is retained separately and its mathematical outcome remains undetermined. The finite-action MIQCP result is paired with the exact rational enumeration of the displayed decimal data.

The record is not a timing comparison. It retains one elapsed-time capture per arm, external SCIP provenance, unavailable instrumentation facts, and links to the exact source evidence. The existing `(x1,x3)` disturbance tube remains the visualization source; the comparison adapter embeds its bytes in both run records so the figure stays attached to the evidence.

The comparison codec now accepts `csl.mpc03-b08-case/1` as an input-manifest source and requires an attached certificate with the same schema and digest. Its manifest shape is documented in [the B08 input schema](../artifacts/schemas/mpc03-b08-case-v1.schema.json). This extends input-manifest typing without relaxing identity or attachment checks for existing records.
