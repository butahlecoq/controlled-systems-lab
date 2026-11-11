# Controlled Systems Lab

Explore the [minimal 2D visual examples](https://butahlecoq.github.io/controlled-systems-lab/examples/):
convex hulls with original vertex IDs, collinear endpoints, and square/diamond
intersection. Each plot includes complete inputs, expected answers, native
reproduction instructions and links to reviewed saved reports. These educational
illustrations accompany the [numerical report archive](https://butahlecoq.github.io/controlled-systems-lab/).

C++20 library and research repository for constrained discrete-time control. The library currently provides immutable affine models and problem data, JSON scenario intake, registered LP/convex backends, phase-I feasibility, execution and numerical reporting. Start with the installed-package examples below.

Strategy A (reachability, terminal minimization and backward recovery), Strategy B (direct joint optimization), witness selection and independent trajectory verification are implemented. Complete optimal families are supported by profile-specific verifiers for T-S01/T-S02/T-S03; Strategy A also has a bounded finite-horizon nominal linear profile whose verifier checks represented binary64 inputs as exact dyadics. These checks do not certify the numerical geometry or optimization producers and do not provide generic family coverage. Trusted proof serialization remains pending.

Start with the live issue and pull request requirements. Repository instructions identify the current contribution and release guidance.

## Quick start

Requires Git, CMake/CTest 3.31 or newer and a C++20 compiler (MSVC 2022, GCC 13 or Clang 18 are CI toolchains). Put CMake on PATH; on Windows a Visual Studio developer shell with its CMake component installed provides the tools. Run from the repository root and stop on any nonzero exit. The first configure downloads the existing pinned dependencies; no Python is needed with `BUILD_TESTING=OFF`. Installation is a local development check, not a binary distribution license grant.

These commands work in PowerShell and a POSIX shell; `$PWD` supplies an absolute install prefix. `--config Release` selects Release for multi-configuration generators, and `CMAKE_BUILD_TYPE` selects it for single-configuration generators.

```sh
cmake -S . -B build/quickstart -DBUILD_TESTING=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build build/quickstart --config Release --parallel 4
cmake --install build/quickstart --config Release --prefix build/quickstart/install
cmake -S examples -B build/examples -DCMAKE_BUILD_TYPE=Release "-DCMAKE_PREFIX_PATH=$PWD/build/quickstart/install"
cmake --build build/examples --config Release --parallel 4
ctest --test-dir build/examples -C Release --output-on-failure --no-tests=error
```

The example suite covers both real feasibility backends and rejected unknown backends/missing or malformed files. [The standalone CMake project](examples/CMakeLists.txt) uses only `find_package(CSL CONFIG)` and installed public targets. The existing installed-consumer CI gate copies and builds the same examples independently of repository headers.

| Executable/source | What it actually does | Expected numerical output |
| --- | --- | --- |
| [registered_lp](examples/registered_lp.cpp) | Selects and runs registered HiGHS on a triangle LP with offset | `x=0 y=1 original_cost=5` |
| [registered_convex](examples/registered_convex.cpp) | Minimizes original `||(x-3,4)||` on `[0,2]` through the convex port | `x=2 original_cost=4.123105626 squared_cost=17` |
| [resolved_scenario](examples/resolved_scenario.cpp) | Constructs and publishes a two-stage model; evaluates stated controls | `states=0,0.25,1 controls=0.25,0.75 original_cost=0` |
| [scenario_file](examples/scenario_file.cpp) | Loads the [JSON template](examples/scenarios/two-stage-integrator.json) into the actual immutable problem and evaluates the same stated history | Same history/cost, plus mathematical identity and separate source digest |
| [scenario_cli](examples/scenario_cli.cpp) | Validates without solvers or runs the guarded paired application for supported T-S01/T-S02 profiles | validation-only result or per-strategy outcomes and witness checks |
| [backend_substitution](examples/backend_substitution.cpp) | Runs one unchanged zero-objective equality/nonnegative LP through either `csl.lp.highs` or `phase-one-bland` | Nonnegative `u0,u1`, `sum=1 original_cost=0`; the chosen witness can differ |
| [scenario_backend_substitution](examples/scenario_backend_substitution.cpp) | Reads `run.backends.lp` from two copies of the same supported two-stage integrator scenario and saves each provider's feasibility result | Same `ProblemId`, effective backend/version, and a checked `u0+u1=1` witness |

Visual Studio executables are under `build/examples/Release/<name>.exe`; single-configuration generators put them under `build/examples/<name>` (with `.exe` on Windows). For example, in PowerShell with Visual Studio:

```powershell
./build/examples/Release/registered_lp.exe
./build/examples/Release/registered_convex.exe
./build/examples/Release/resolved_scenario.exe
./build/examples/Release/scenario_file.exe examples/scenarios/two-stage-integrator.json
./build/examples/Release/scenario_cli.exe --validate-only examples/scenarios/two-stage-integrator.json
./build/examples/Release/scenario_cli.exe --run examples/scenarios/two-stage-integrator.json --profile ts01_exact_integrator --seed 31 --threads 1
./build/examples/Release/backend_substitution.exe csl.lp.highs
./build/examples/Release/backend_substitution.exe phase-one-bland
./build/examples/Release/scenario_backend_substitution.exe examples/scenarios/two-stage-integrator-highs.json build/two-stage-highs.json
./build/examples/Release/scenario_backend_substitution.exe examples/scenarios/two-stage-integrator-phase-one.json build/two-stage-phase-one.json
```

The validation-only CLI checks scenario parsing and canonical model resolution without invoking solvers. Run mode sends the same resolved problem to the installed paired application API, which admits the reach-back and direct-joint strategies, selects witnesses from complete T-S01/T-S02 families, and independently checks those witnesses against the original problem. The initial profile defaults to T-S01. The `--profile`, `--lp`, `--convex`, `--seed`, and `--threads` options override run settings. The scenario's `run.resources` sets its resource policy. Input and capability failures retain actionable diagnostics.

Use `--output-dir <directory>` to save one versioned run artifact per strategy through the artifact API after both strategies return complete-family results with completed optimal outcomes and every selected witness passes its numerical checks. The `csl.run-statistics/7` records retain complete-family claims as unverified data; decoding them does not grant proof authority. The two files are separate run records, not a paired comparison record. If either strategy or witness check fails, the CLI returns before artifact publication. Without `--output-dir`, the CLI prints results and saves no artifacts. Witness checks do not prove optimality or general family completeness.

The CLI's `--lp` and `--convex` options take registry IDs and default to HiGHS. Selection prints the chosen ID and version; an unknown ID exits with a registry diagnostic. The separate `backend_substitution` example takes its backend ID as a positional argument. `scenario_backend_substitution` instead reads the authored LP backend from each scenario and writes a JSON record per run. It accepts only the exact two-stage scalar integrator fixture: the LP checks terminal reachability `u0+u1=1` under `0<=u0,u1<=1`. Both runs report numerical feasibility only; Phase I is not presented as a general optimizer or control-synthesis strategy, and the records claim neither a certified bound nor a complete optimal family. Changed model data is rejected with a `/scenario/model` diagnostic.

The file template uses `0.5*x'Q*x + q'x + c`, here `Q=2`, `q=-2`, `c=1`, so the original terminal cost is `(x2-1)^2`. Its default comparison request is intent only: no synthesis strategy is selected or executed. The history `(u0,u1)=(0.25,0.75)` is supplied by the example, not found by a solver. This small reader is not a general scenario runner or independent constraint verifier.

The [registered synthesis comparison example](examples/registered_synthesis_comparison.cpp) provides a functional comparison bounded to the two-stage integrator and exact T-S01 request. It runs both registered strategies against the same immutable problem, selects witness histories, and reports independent checks against the original problem data. Its JSON summary identifies the shared problem/request and each strategy, outcome, selected witnesses, and original-data verification status/residuals; the example does not serialize the live optimal-family relation or proof payload. Its functional output and CTest duration are not performance evidence. The [saved paired T-S01 report](reports/algorithm-results/syn-ts01-paired-20261014-b7f1ac0/index.html) supplies HTML and raw records for this tiny fixture; its performance conclusion is inconclusive and establishes no general strategy ranking. Broader comparisons follow the [published-results policy](docs/architecture/published-algorithm-results.md).

## Current numerical reports

Open the published [reference LP report](https://butahlecoq.github.io/controlled-systems-lab/lp-20261012T000346Z-ee5e9193b7a5/index.html) and [reference convex report](https://butahlecoq.github.io/controlled-systems-lab/convex-20261012T041854Z-4d54a407c9b2/index.html), including raw records, figures and source provenance. These are single-adapter measurements on analytic fixtures. The [paired T-S01 report](reports/algorithm-results/syn-ts01-paired-20261014-b7f1ac0/index.html) records the guarded two-strategy experiment with an inconclusive performance result; it establishes no speedup or general ranking. [Repository copies and offline ZIPs](reports/algorithm-results/index.html) remain available. Example test durations, including the functional synthesis example, are not benchmarks.

## Research and contracts

Scientific corrections, reproduction reports and algorithm proposals are tracked in [GitHub issues](https://github.com/butahlecoq/controlled-systems-lab/issues). This repository preserves the implementation, published reports, machine-readable records and cited source identifiers. Original source material and local research notes are not a substitute for versioned evidence.

## Current conclusions

The reusable core represents affine discrete-time models, time-dependent constraints, uncertainty semantics, terminal objectives and set data. Each implemented algorithm has its own supported profile; representable problem data does not imply an available solver or guarantee.

The archive's finite-action minimax solver enumerates control sequences; changing language alone will not remove exponential growth. Exact polytope operations, support-function methods, constrained zonotopes, and structured optimization deserve separate backends.

Published experiments are the starting baselines, as requested by the research owner. Their numbers are recorded as reported results, not new reproductions. Several source and implementation inconsistencies must be resolved before they become acceptance criteria.

The project uses C++20 as its main implementation language and Python for independent verification. Implemented profiles state their supported inputs and guarantees; the [published-results evidence gates](docs/architecture/published-algorithm-results.md) govern numerical claims.

## Evidence and preservation

Published reports retain their own versioned evidence bundles and provenance. Historical source and local-only working notes are not presented as current project documentation.
