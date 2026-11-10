# MPC-07 bounded policy intersection

Authorized follow-up to issue603's research audit; no author implementation is
copied or adopted. Use the existing reviewed Release public-CSL ConvexPort bridge
from affine-pilot-b3978a98, whose binary digest and original build receipt are
retained separately from the new generator/checker source. No new native build,
core API, required dependency or publication wiring is planned.

1. Build exact box-support LPs for two-state position/velocity dynamics,
   x0=0, u0=0, scalar continuous |u|<=1, independent additive eta per stage,
   T=2/4/8. Compare fixed plans, prescribed state gain, optimized affine past-
   disturbance feedback, and explicit causal state-response variables. The two
   optimized formulations use the same policy class and objective. Prove robust
   counterparts, causality and terminal-absolute-value epigraph semantics.
2. Keep the additive known-A/B profile separate from an uncertain-A profile:
   q_next=(1+delta)q+u+w, |delta|<=1/64, |w|<=1, |q|<=16. Its fixed filter
   eta=delta*q+w in [-5/4,5/4] is sound by induction. This is a conservative
   fixed-filter restriction, not Chen's jointly optimized filter implementation.
   Full uncertain-B and joint-filter SLS optimization remain residual criteria.
3. Test exact tiny oracles, missing/future disturbance access, malformed widths,
   changed response coordinates and violation rejection before native captures.
   Rationally reconstruct returned policies, then independently replay exact
   affine recurrences and supports; raw native numbers are never rewritten.
4. Run bounded native correctness pilots, then five alternating repetitions
   with all unsuccessful outcomes retained. Save full inputs/stdout/stderr,
   source/binary/environment identities and actual native setup/run clocks.
   Include a separate diagnostic profile. Treat timing as inconclusive absent
   a supported native limiter, tuning study and scope-matched measurements.
5. Generate a saved-data 2D terminal-policy/uncertainty-filter illustration,
   complete inputs, raw/hash provenance and offline checker/report. Do not
   claim recursive feasibility, generic causal capability or publication.
   Independent review and root-owned integration remain required.
