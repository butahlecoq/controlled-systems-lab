# EXT-07 hybrid profile report

The report driver exercises one complete public path through bounded path
enumeration, joint H-relation construction, registered HiGHS LP execution,
and the independent `OneStepScalarIntervalHybridFamilyVerifier`. Its fixture
has two scalar modes, one edge, interval control and guard, identity reset, and
the linear terminal objective `minimize x1`. The literal feasible relation is
`x0=0, x_pre1=u0, x1=u0, 0<=u0<=0.5`; the complete minimizer family is the
point `(x0,u0,x_pre1,x1)=(0,0,0,0)`.

This is numerical binary64 evidence for the verifier's one-step scalar domain.
It does not cover multi-stage continuous families, validated arithmetic,
general polyhedral dimensions, or application-scale performance. There is no
comparator or speedup claim. The 2D example uses control and terminal state as
axes and labels the underlying system as scalar.

From a clean checkout at the frozen source commit:

```sh
python scripts/reports/ext07/capture.py --source <clean-source> --capture <fresh-capture> --commit <source-commit> --cmake <cmake-executable>
python scripts/reports/ext07/ext07_collect.py --capture <fresh-capture> --source <clean-source> --out reports/algorithm-results
python scripts/reports/ext07/render_saved.py --bundle reports/algorithm-results/<report-id>
python scripts/reports/ext07/render_saved.py --bundle reports/algorithm-results/<report-id> --check
python scripts/reports/stage_ext07.py --source reports/algorithm-results/<report-id>
```

Capture builds a clean Release executable with the pinned HiGHS LP and convex
adapters, retains source and executable hashes, redacted configure/build logs,
compiler/host receipts, a smoke run, one excluded 10-call warmup, and seven
measured 20-call batches. The collector validates every raw row against the
analytic result and records unavailable objective bounds and solver counters
as unavailable. Rendering reads saved records only; it never runs the solver.
The 140 measured calls are sequential and use fresh registered providers and
workspaces. Phase durations are accumulated separately within each batch; their
medians are computed independently and are not additive to the end-to-end
median. End-to-end timing includes setup, enumeration, relation assembly, solve,
and verification, while output and rendering are excluded.

The publication catalogue is `reports/algorithm-results/ext07-publications.json`.
The main-only report workflow stages only the allowlisted report bundle after
the catalogue, hashes, HTML links, and offline ZIP validate. The deployed URL
and live file hashes remain pending until that workflow runs on `main`.
