# REVIEW-05 constraint-row ladder

This saved run holds a scalar integrator at state/control dimension 1 and
horizon 2 fixed while the authored state H-row count grows from 2 to 4 to 8
per stage. The three input files describe the same interval `[-2,2]`; the
additional inequalities are redundant bounds.

The capture contains one excluded warmup and six alternating measured pairs
for each case. All 42 attempts completed and passed the independent exact
fixture checker. The checker proves the zero optimum only for these three
finite fixtures. Timings cover `SynthesisWorkspace::run()` and are descriptive
single-host observations; they do not establish a winner, speedup, memory
scaling, internal phase cost, source-level limiter, or general complexity.

The malformed-JSON preflight and unavailable `perf` diagnostic are preserved
under `diagnostics/` and excluded from the accepted measurements.
