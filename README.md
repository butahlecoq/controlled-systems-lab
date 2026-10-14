# Controlled Systems Lab

C++20 library and research repository for constrained discrete-time control. The library currently provides immutable affine models and problem data, JSON scenario intake, registered LP/convex backends, phase-I feasibility, execution and numerical reporting. Start with the installed-package examples below.

Both registered synthesis strategies now publish complete optimal-family results for the tightly guarded analytic T-S01 and T-S02 profiles. These exact-fixture paths do not yet provide the general nominal workflow, arbitrary supported constraints, reusable numerical family-coverage procedure, or a paired comparison and saved synthesis report. See the [current framework composition](docs/architecture/framework-composition.md) for the implemented module map and remaining integration work.

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

Expected: **12/12 example tests pass**, including both real feasibility backends and rejected unknown backends/missing or malformed files. [The standalone CMake project](examples/CMakeLists.txt) uses only `find_package(CSL CONFIG)` and installed public targets. The existing installed-consumer CI gate copies and builds the same examples independently of repository headers.

| Executable/source | What it actually does | Expected numerical output |
| --- | --- | --- |
| [registered_lp](examples/registered_lp.cpp) | Selects and runs registered HiGHS on a triangle LP with offset | `x=0 y=1 original_cost=5` |
| [registered_convex](examples/registered_convex.cpp) | Minimizes original `||(x-3,4)||` on `[0,2]` through the convex port | `x=2 original_cost=4.123105626 squared_cost=17` |
| [resolved_scenario](examples/resolved_scenario.cpp) | Constructs and publishes a two-stage model; evaluates stated controls | `states=0,0.25,1 controls=0.25,0.75 original_cost=0` |
| [scenario_file](examples/scenario_file.cpp) | Loads the [JSON template](examples/scenarios/two-stage-integrator.json) into the actual immutable problem and evaluates the same stated history | Same history/cost, plus mathematical identity and separate source digest |
| [backend_substitution](examples/backend_substitution.cpp) | Runs one unchanged zero-objective equality/nonnegative LP through either `csl.lp.highs` or `phase-one-bland` | Nonnegative `u0,u1`, `sum=1 original_cost=0`; the chosen witness can differ |

Visual Studio executables are under `build/examples/Release/<name>.exe`; single-configuration generators put them under `build/examples/<name>` (with `.exe` on Windows). For example, in PowerShell with Visual Studio:

```powershell
./build/examples/Release/registered_lp.exe
./build/examples/Release/registered_convex.exe
./build/examples/Release/resolved_scenario.exe
./build/examples/Release/scenario_file.exe examples/scenarios/two-stage-integrator.json
./build/examples/Release/backend_substitution.exe csl.lp.highs
./build/examples/Release/backend_substitution.exe phase-one-bland
```

Backend IDs are positional arguments, with HiGHS defaults in the first two examples. Selection prints the actual registered ID/version; an unknown ID exits with a registry diagnostic. Phase I supports the demonstrated feasibility profile, not general nonzero-objective optimization or a second control-synthesis strategy. Numerical outcomes retain **unestablished evidence** and do not supply certified bounds or an optimal family.

The file template uses `0.5*x'Q*x + q'x + c`, here `Q=2`, `q=-2`, `c=1`, so the original terminal cost is `(x2-1)^2`. Its default comparison request is intent only: no synthesis strategy is selected or executed. The history `(u0,u1)=(0.25,0.75)` is supplied by the example, not found by a solver. This small reader is not a general scenario runner or independent constraint verifier.

The [registered synthesis comparison example](examples/registered_synthesis_comparison.cpp) provides a functional comparison bounded to the two-stage integrator and exact T-S01 request. It runs both registered strategies against the same immutable problem, selects witness histories, and reports independent checks against the original problem data. Its JSON summary identifies the shared problem/request and each strategy, outcome, selected witnesses, and original-data verification status/residuals; the example does not serialize the live optimal-family relation or proof payload. Its functional output and CTest duration are not performance evidence. A measured, reproducible paired report with HTML and raw records remains outstanding under [OBS-04 #83](https://github.com/butahlecoq/controlled-systems-lab/issues/83) and the [published-results policy](docs/architecture/published-algorithm-results.md).

## Current numerical reports

Open the published [reference LP report](https://butahlecoq.github.io/controlled-systems-lab/lp-20261012T000346Z-ee5e9193b7a5/index.html) and [reference convex report](https://butahlecoq.github.io/controlled-systems-lab/convex-20261012T041854Z-4d54a407c9b2/index.html), including raw records, figures and source provenance. These are single-adapter measurements on analytic fixtures, not a two-strategy control comparison or speedup claim. [Repository copies and offline ZIPs](reports/algorithm-results/index.html) remain available. Example test durations, including the functional synthesis example, are not benchmarks.

## Research and contracts

Scientific review starts with [review issues](https://github.com/butahlecoq/controlled-systems-lab/issues) and [contribution conventions](CONTRIBUTING.md). The initial research assessment is dated 11 October 2026. Documentation is in English; source artifacts retain their original language.

The archive supports reachable-set computation, terminal optimization and minimax control. Aerospace fuel management is a domain adapter, not the definition of the mathematical core. Its historical restoration remains unresolved. The accompanying research also covers flight dynamics, slosh, elastic modes and model discretization.

| Document | Purpose |
|---|---|
| [Research index](docs/research/README.md) | Scope, evidence levels, and reading order |
| [Source map](docs/research/source-map.md) | All 31 original files, relationships, and extraction limitations |
| [Scientific foundations](docs/research/scientific-foundations.md) | Equations, assumptions, algorithm descriptions, and guarantee boundaries |
| [Published baselines](docs/research/baselines.md) | Numerical experiments to reproduce and compare |
| [Legacy implementation audit](docs/research/legacy-audit.md) | Source findings and isolated executable checks |
| [Research developments, 2021–2026](docs/research/recent-research.md) | Relevant recent methods and software analogues |
| [Implementation backlog](docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md) | Dependency-ordered GitHub tickets, separate unit-test expansions, review gates and proposed ownership |
| [Algorithm inventory](docs/research/algorithm-module-inventory.md) | Archival LP/hull variants, Pascal Zoutendijk, exact operations and implementation assumptions |
| [Skill routing](docs/agents/skill-routing.md) | Roles for Matt Pocock, Superpowers and selectively installed pstack skills |
| [Consolidated specification](docs/superpowers/specs/2026-10-11-controlled-systems-master-design.md) | Conversation decisions, requirement IDs, acceptance tests and future subagent work breakdown |
| [C++ core contracts](docs/superpowers/specs/2026-10-11-cpp-core-contracts-design.md) | Draft native interfaces, ownership, extension boundaries and first usage scenarios |
| [Native build and installed client](docs/build/native.md) | Repeatable C++20 configure/build/test/install, dependency pins and platform evidence |
| [Scenario-file design](docs/superpowers/specs/2026-10-11-scenario-files-design.md) | Simple user-authored inputs, templates, validation and optional run settings |
| [Language decision](docs/architecture/decisions/0001-cpp20-core.md) | Accepted C++ direction and its consequences |
| [Modular algorithms and optimal families](docs/architecture/modular-algorithms-and-solution-sets.md) | Concrete C++20 ports, interchangeable solvers/geometry, complete solution relations |
| [Set representations and Ellipsoidal Toolbox](docs/architecture/set-representations-and-ellipsoidal-toolbox.md) | Ellipsoidal methods, newer representations, recovered owner-authored zonotope paper |
| [Initial architecture](docs/architecture/initial-architecture.md) | Broader modules, contracts, and workflows |
| [Performance and language](docs/architecture/performance-and-language.md) | Parallelism, complexity, and language evaluation |
| [Glossary](docs/research/glossary.md) | Shared mathematical and software vocabulary |
| [Open questions](docs/research/open-questions.md) | Interview agenda and next research steps |
| [Bibliography](docs/research/bibliography.md) | Primary sources and reading depth |

## Current conclusions

The reusable core represents affine discrete-time models, time-dependent constraints, uncertainty semantics, terminal objectives and set data. Each implemented algorithm has its own supported profile; representable problem data does not imply an available solver or guarantee.

The archive's finite-action minimax solver enumerates control sequences; changing language alone will not remove exponential growth. Exact polytope operations, support-function methods, constrained zonotopes, and structured optimization deserve separate backends.

Published experiments are the starting baselines, as requested by the research owner. Their numbers are recorded as reported results, not new reproductions. Several source and implementation inconsistencies must be resolved before they become acceptance criteria.

Owner decision: use C++ as the main implementation language, with C++20 as the working standard and Python for independent verification/reference computations. The general first user workflow must return an optimal solution family for nominal planning with continuous actions and without process disturbances; the model contract retains disturbance/adversarial and observation channels. See the [linear-system contract](docs/architecture/linear-system-contract.md) and [implementation backlog](docs/superpowers/plans/2026-10-11-controlled-systems-backlog.md). The required comparison is reachability/terminal minimization/backward recovery versus direct joint-trajectory optimization on the same immutable problem. The T-S01/T-S02 registered profiles are bounded analytic cases, not general workflow completion; single witnesses, two backend calls or sampled endpoints do not fulfill the full-family requirement. The [composition map](docs/architecture/framework-composition.md) distinguishes delivered components from remaining work.

## Evidence and preservation

Original files were inventoried with SHA-256 hashes and left unchanged. Thirty content-bearing artifacts were extracted; one file is an Office lock file. Raw extraction lives in the local-only docs/research/extracted directory and may contain OCR errors, original Russian text, equation fragments, and personal information already present in the source files.

All 21 PDFs (226 pages in total; see the inventory for authoritative counts) were text-extracted. Selected mathematical and numerical pages were also visually inspected. Embedded Equation Editor objects in the two legacy Word files were not decoded. The full historical MATLAB/Pascal workflows have not been reproduced.

See [machine-readable inventory](docs/research/inventory.json), [characterization results](docs/research/legacy-characterization.json), and [verification record](docs/research/verification.md).
