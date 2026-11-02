# REVIEW-05 source profile: horizon-eight scalar integrator

## Question and conclusion

This diagnostic asks whether a single source function dominates the two nominal
strategies on the pinned HORIZON-01 T=8 case. The decision rule was: pursue a
focused optimization only if the same function takes at least 15% of sampled
CPU for a strategy; otherwise keep the limiter conclusion inconclusive.

The profile does not identify one dominant limiter. Reach-back samples are
spread across HiGHS option/workspace lifecycle, LP solving, geometry conversion,
and exact witness checks. Strategy B's most sampled functions each account for
three 10 ms ticks or fewer. This points to several small contributors, not a
defensible single optimization target. The profile is one scalar case and does
not generalize to larger horizons, state dimensions, or other representations.

No speed, ranking, scaling, or memory claim follows from this artifact. The
instrumented build and repeated capture are for source attribution only.

## Workload and capture

The pinned fixture is `horizon01-t08.json`:

```text
x[t+1] = x[t] + u[t], x[0] = 0, 0 <= u[t] <= 1, minimize x[8]
```

The analytic checker proves that each candidate relation equals the unique
zero history. Three process groups alternated strategy order. Each process ran
1,000 calls with a fresh strategy workspace per call and the same prepared
strategy snapshot. Every result was retained in the process's raw stdout and
checked against the exact fixture oracle. Process CPU was capped at 300 seconds,
address space at 8 GiB, and wall time at 300 seconds.

All 6,000 strategy outputs passed the exact checker. The offline verifier
re-parses the raw stdout, checks each result and scenario identity, validates
stdout/stderr/profile hashes, and confirms the captured verdicts. There were no
failed, rejected, timed-out, or unavailable attempts.

The sampler uses a 10 ms timer tick. It accumulated 20.05 sampled seconds for
reach-back and 0.47 sampled seconds for Strategy B. In the reach-back profile,
the largest individual entries were `OptionRecordString::~OptionRecordString`
(4.89%), the `Highs::callSolveQp` closure manager (4.74%), `Highs::~Highs`
(2.64%), and `HighsOptions::initRecords` (2.04%). CSL entries included
`exact_convex_combination` (2.04%) and
`HighsLPWorkspace::solve_native` (1.40%). No one entry reached the 15% decision
threshold.

Strategy B had only 47 sampled ticks in total. Its largest entries were
`HFactor::ftranL` (6.38%), `solveLpSimplex` (4.26%),
`OptionRecordString::~OptionRecordString` (4.26%), and the
`Highs::callSolveQp` closure manager (4.26%). These percentages are coarse
diagnostics, not precise cost estimates.

## Source mapping

The flat profiles list symbols. The debug build maps representative symbols to
the following code:

| Sampled symbol | Source location |
| --- | --- |
| `HighsLPWorkspace::solve_native` | `src/adapters/lp/highs.cpp:178` |
| `AffineSumWorkspace::apply_supported` | `src/geometry/affine_sum.cpp:338` |
| `exact_convex_combination` | `src/geometry/exact_convex_combination.hpp:12` |
| `Check::residual` | `src/verification/trajectory.cpp:51` |
| `OptionRecordString::~OptionRecordString` | Pinned HiGHS 1.11.0, `highs/lp_data/HighsOptions.h:124` |
| `HighsOptions::initRecords` | Pinned HiGHS 1.11.0, `highs/lp_data/HighsOptions.h:662` |
| `HFactor::ftranL` / `HFactor::btranFT` | Pinned HiGHS 1.11.0, `highs/util/HFactor.cpp` |
| `solveLpSimplex` | Pinned HiGHS 1.11.0, `highs/simplex/HApp.h:77` |

HiGHS source is fetched by the pinned CMake dependency and its version is
recorded in `build-provenance.json`. `addr2line` and `nm -C` resolved the
symbols against the exact instrumented executable.

## Limits

- The sampled CPU profile includes process setup and output serialization;
  output serialization is outside `strategy_run_ns`. The small `gprof` driver
  overhead and 10 ms sampling interval also limit attribution.
- CSL and HiGHS libraries were built with Release optimization and debug
  symbols. Only the profile driver was compiled with `-pg`. This keeps
  instrumentation overhead out of dependency calls while retaining flat
  function samples; it does not provide a call graph.
- An earlier fully call-instrumented probe produced very large call-graph data
  and was not used. The final flat profiles are reproducible from the retained
  raw `gmon` files.
- `gprof` recorded total samples after capture; a load average immediately
  before the run was not retained. No performance conclusion depends on this
  capture.

## Reproduction

From the repository root, set `BUILD` to a disposable directory on a filesystem
with adequate temporary space. The repository's normal CMake shim may require
the installed CMake 3.31.6 binary.

```sh
cmake -S benchmarks/reporting/review05 -B "$BUILD" \
  -DCSL_SOURCE_ROOT="$PWD" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CXX_FLAGS_RELEASE='-O3 -DNDEBUG -g' \
  -DCMAKE_EXE_LINKER_FLAGS=-pg \
  -DCSL_REVIEW05_PROFILE_DRIVER=ON -G Ninja
cmake --build "$BUILD" --target csl_review05_horizon_ladder --parallel 4
python3 benchmarks/reporting/review05/capture_source_profile.py \
  --driver "$BUILD/csl_review05_horizon_ladder" \
  --scenario benchmarks/reporting/review05/scenarios/horizon01-t08.json \
  --output reports/algorithm-results/review05-source-profile-final-20261102 \
  --process-groups 3 --repeats-per-process 1000
python3 benchmarks/reporting/review05/verify_source_profile.py \
  --bundle reports/algorithm-results/review05-source-profile-final-20261102
```

To regenerate the flat profiles, run the recorded `profile-commands.txt` after
substituting the driver path from `build-provenance.json`. `SHA256SUMS` covers
the retained attempt records, raw outputs, raw profile files, and reports.
