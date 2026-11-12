# Complete scalar family and witness queries

This ladder measures the complete nominal exact-H profiles and the actual
registered direction-LP selector at scalar horizons T=2,4,8. It is separate from
the unchanged candidate-relaxation horizon driver. The implementation is stacked
on the Strategy B exact-profile and horizon-aware selector commits; the task-3
branch starts at `5db36395` and additionally requires B selector acceptance
`89066ac8` (cherry-picked as `495fb7de`).

The literal plant is `x[t+1]=x[t]+u[t]`, `x[0]=0`, `0<=u[t]<=1`.
The original `horizon01-t*.json` fixtures minimize `x[T]`, whose unique optimum is
the all-zero history, and request one witness. The separate
`family-query-flat-t*.json` fixtures have constant objective zero. They request
2T observations over positive/negative control basis directions, exercising
all supplied directions. Distinctness shortfalls remain explicit and do not
prove uniqueness. No generic family membership or slice API is introduced.

The checker interprets saved finite binary64 values as exact dyadic rationals.
For target-to-emitted-family inclusion, it checks the literal optimizer vertices:
the all-zero history for HORIZON-01, or all vertices of the affine unit-control
cube for the constant objective. For emitted-to-target inclusion it checks
infeasibility of each strict violation of the literal dynamics, initial, control
and optimum constraints, using Gaussian equality substitution and bounded
Fourier–Motzkin elimination. Limits are 100,000 generated rows, five million
coefficient operations and 8,192-bit rational numerators/denominators; exhaustion
is inconclusive. This is an independent, fixture-specific check, not generic
validated-numerics assurance. The registered compiled verifier remains the
library's complete-family authority.

Each retained query history is independently checked against literal initial,
dynamics, control and original-objective data. Its direction dot product must
attain the exact cube minimum `sum(min(0,d_i))` for a flat fixture, or zero for the
singleton HORIZON-01 optimizer. Zero direction coordinates permit ties. The
checker associates successful observations with their actual planned LP program
identity, query index and input/output widths when the collector is enabled.

## Build and reproduce

Use CMake 3.31+ with the pinned production dependencies and a Release compiler:

```sh
cmake -S benchmarks/reporting/review05 -B build/review05-family-query \
  -DCSL_SOURCE_ROOT="$PWD" -DCMAKE_BUILD_TYPE=Release \
  -DCSL_DEPENDENCY_PROBES=OFF
cmake --build build/review05-family-query --target csl_review05_family_query -j2
python3 -m unittest tests.reporting.test_review05_family_query
python3 benchmarks/reporting/review05/run_family_query.py \
  --driver build/review05-family-query/csl_review05_family_query \
  --build-cache build/review05-family-query/CMakeCache.txt \
  --output /absolute/new/capture-directory
python3 benchmarks/reporting/review05/check_family_query.py /absolute/new/capture-directory
python3 benchmarks/reporting/review05/render_family_query.py /absolute/new/capture-directory
```

The Linux capture runner requires a clean source worktree and a new output
path. It retains one excluded warmup pair and six measured pairs per fixture
and collector mode, alternates AB/BA and rotates fixture/mode order. Each
attempt uses a fresh process. The process has 300 CPU seconds, a 150-second
wall timeout and an 8 GiB address-space limit; the library context has a
120-second deadline and one requested outer/backend thread. `wait4` supplies
per-child CPU and peak RSS. Hard native heap budgeting remains unsupported.
Every stdout/stderr stream and refusal/stop remains saved even when verification
cannot establish a mathematical result. Deliberate materialization-limit probes
are excluded from timing groups, not erased.

`registered_synthesis_ns` includes library strategy execution, compiled verifier
and registry validation. Strategy phases are actual library timing spans.
`selector_ns` measures the selector call; `selector.lp.direction-query` spans
come from its real registered LP runner calls and include runner validation.
They are not driver helper timers or isolated native solver times. Literal C++
replay and independent exact Python replay/family verification have separately
named intervals. Isolated verifier timing is unavailable because the registry
has no separate span; no outer-minus-strategy residual is labelled verifier time.
Collector on/off groups quantify this capture's OBS-mode differences. Native
clock instrumentation overhead remains a separate #95 gate.

The renderer uses saved records only, with the report-only pinned Matplotlib 3.11.2 environment and shared quantitative axis policy. Its T=2 illustration labels scalar state
dimension one, the complete `(u0,u1)` control-square projection, selected query
points and scalar state paths. There is no performance ranking or complexity,
real-time, nonlinear, generic family-query or publication claim. Source-level
limiter attribution remains inconclusive until the separate profile supports it.

This is research tooling with no required dependency or package layout change;
no standalone library release is needed. Selector behavior delivery, installed
consumer/platform checks, independent reviews and Pages publication remain
integration gates. Issue #95 stays open for its remaining acceptance criteria.

## Separate limiter diagnostic

After the primary capture, configure the same source with
`-DCSL_REVIEW05_PROFILE_DRIVER=ON` and rebuild only
`csl_review05_family_query`. The driver compile/link gains `-pg`; unchanged
static library symbols can receive CPU histogram samples, but their call graph
is incomplete. Run `profile_family_query.py --driver <profile-binary> --build-cache
<profile-build>/CMakeCache.txt --bundle <capture-directory>`, then render again. The separate profile keeps its binary
hash, individual raw outputs/resources and all gmon files. It samples the whole
command process, including setup and serialization, and never supplies primary
timing distributions. Sparse or unresolved samples yield an inconclusive limiter
assessment. This is not isolated compiled-verifier profiling.
