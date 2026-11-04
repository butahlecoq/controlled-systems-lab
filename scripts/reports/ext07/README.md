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

Run these commands from a clean report-tools checkout. Set `<frozen-source>`
to a separate clean checkout of the measured source commit recorded in the
bundle (currently `2965baafa325550ad60ec91d44f5e3f86a832178`). The report tools
may be newer than that measured source; the collector verifies that the driver
matches the frozen commit, and the publication catalogue binds the collector,
renderer, and stager hashes.

```sh
python scripts/reports/ext07/capture.py --source <frozen-source> --capture <fresh-capture> --commit <source-commit> --cmake <cmake-executable>
python scripts/reports/ext07/ext07_collect.py --capture <fresh-capture> --source <frozen-source> --out reports/algorithm-results
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

New schema `/2` captures also report process CPU for each branch execution.
This sums all process threads during workspace creation and provider execution,
so unrelated concurrent work may contribute. It is not provider-only CPU, and
it does not measure heap use. Schema `/1` bundles remain readable and retain
their original rendered bytes.

The publication catalogue is `reports/algorithm-results/ext07-publications.json`.
The main-only report workflow stages only the allowlisted report bundle after
the catalogue, hashes, HTML links, and offline ZIP validate. The deployed URL
and live file hashes remain pending until that workflow runs on `main`.

## Two-parameter verifier evidence

The separate two-parameter bundle measures the bounded two-stage verifier on
two tied paths. Its fixture has controls `(u0,u1)` in `[0,1] x [0,1]`; one
guard restricts the first control to `[0,0.5]`, while a parallel path leaves
it in `[0,1]`. The objective is `minimize x_terminal=u0`, so both complete
minimizer families are `u0=0, 0<=u1<=1`. The standalone visual page plots the
two feasible rectangles and their shared minimizing segment.

The two-parameter driver measures full public path construction, both HiGHS
LP branches, tied face construction, and verification of both families. It
uses one excluded 10-call warmup followed by seven measured 20-call batches.
It makes no comparator or speedup claim. The source commit and every raw
per-call duration are recorded separately from the existing one-step report.
New schema `/2` records include process CPU observations for each branch and
label their process-wide scope in the report; the same provider-attribution and
heap limitations apply.

Schema `/3` captures also preserve each relation operation's kind, stage, mode
or edge, implementation identity, row and matrix deltas, wall duration,
completion state, and composing-thread CPU observation. The report summarizes
those observations per operation and keeps unavailable reasons in raw records.
This CPU scope covers only the synchronous composing thread; helper-thread CPU
is excluded, and the clock reads add measurement overhead. Schemas `/1` and
`/2` remain readable with their original rendered bytes.

Schema `/4` captures also record wall and process CPU immediately around the
synchronous `BoundWorkspace::run` provider invocation. Process CPU sums all
process threads and may include helper or unrelated work; it is not provider-
only attribution. It does not measure heap use or enforce a resource limit.
Historical schema `/1` through `/3` bundles and rendered bytes are unchanged.
The two-parameter capture may reuse a separate build tree with `--build-dir`;
its configure and build logs redact that path, and its saved capture retains a
copy of the executable. When the default capture-local build tree is used, the
driver records that executable in place.

## Capability admission and complete-path profile

`capability_driver.cpp` measures only `report_hybrid_capability`: model-profile
validation plus complete permitted-path enumeration. It does not construct
joint relations, invoke LP providers, or run optimization. Ten fixtures vary
state/control dimension (1, 2, 4, 8), horizon (1, 2, 4, 8), mode/edge catalogue
size (2/2, 4/4, 8/8), and complete path count (1 or 256). Each fixture has one
excluded 1,000-call warmup and seven 1,000-call measured batches; fixture order
is repeated each batch to limit time-order drift. A refusal, incomplete report,
or empty path count fails the capture. `capability_collect.py` checks that all
ten profiles and seven repetitions are present before it computes medians and
ranges. It has a separate CMake option and builds with the native HiGHS
adapter disabled.

Use a clean checkout of the source commit recorded in the saved report:

```sh
python scripts/reports/ext07/capability_capture.py --source <frozen-source> --capture <fresh-capture> --commit <source-commit> --cmake <cmake-executable>
python scripts/reports/ext07/capability_collect.py --raw <fresh-capture>/measure.jsonl --out <summary-directory>
```

Per-call elapsed time is descriptive for this admission/enumeration routine;
it is not a hybrid solver benchmark or a general scalability claim. See the
saved [capability scale profile](../../../docs/research/ext07-capability-profile.md)
for the source identity, raw data, host, medians, and observed limits.

```sh
python scripts/reports/ext07/two_parameter_capture.py --source <frozen-source> --capture <fresh-capture> --commit <source-commit> --cmake <cmake-executable>
python scripts/reports/ext07/two_parameter_collect.py --capture <fresh-capture> --source <frozen-source> --out reports/algorithm-results
python scripts/reports/ext07/two_parameter_render_saved.py --bundle reports/algorithm-results/<report-id>
python scripts/reports/ext07/two_parameter_render_saved.py --bundle reports/algorithm-results/<report-id> --check
python scripts/reports/stage_ext07.py --source reports/algorithm-results/ext07-hybrid-51d9ee2e89d240eb --source reports/algorithm-results/<report-id>
```

The final command emits the publication catalogue with both profile-specific
bundles. Report staging copies both immutable bundles and their distinct 2D
examples to Pages.
