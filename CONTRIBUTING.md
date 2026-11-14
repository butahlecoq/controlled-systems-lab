# Scientific review and contributions

For public API, dependency, installation, example and publication changes, record
the PR's release/package impact using the [delivery guide](docs/agents/delivery.md).
It covers GitHub Releases, when Packages is useful, and minimal Pages examples.

This repository contains a C++20 library, executable examples and published evidence. Use the current source, tests and issue-linked requirements when making changes.

Use issues for scientific corrections, reproduction reports and algorithm proposals. Cite an Lxx source identifier or a primary external reference, the formula/page, exact assumptions and a minimal example where possible. Distinguish a proven discrepancy, an interpretation question, a numerical observation and an implementation defect.

A useful reproduction report identifies the problem manifest, source version, coordinate/time convention, objective, control domain, uncertainty dependence, policy class, software/hardware versions, solver settings, residuals and result evidence. Compare like-for-like output and guarantees.

For a new algorithm, state supported assumptions, returned guarantees, complexity/representation costs, and an evaluation plan against the published baselines. A faster sampled approximation should not be described as the same result as an exact worst-case solve without qualification.

Keep historical reported numbers unchanged. Record corrected references separately with an issue explaining the change. Do not silently “repair” an article or attribute an extracted PDF formatting issue to executable source.

New curated documentation and future software should be in English. Preserve original-language quotations only when necessary for provenance and with a translation.

Original papers, listings, raw extractions and personal source metadata remain local. Source IDs and hashes are public; reviewers can cite the published counterparts and request a precise transcription through an issue. Public availability of the repository does not establish a redistribution license for archival materials. Project licensing remains an owner decision.

Changes to mathematical contracts or guarantee labels require a clear rationale and appropriate independent checks. State supported assumptions, returned guarantees, complexity and output-completeness limits in the relevant issue and pull request.

Implementation work starts from the live GitHub issue: verify its prerequisites, claim it, and agree on file ownership before parallel edits. Each module implementation ships minimum independent tests; separate test expansions and rigorous review issues provide additional gates. The issue tracker is the current source for work state.

Every algorithm that produces numerical results must follow the [published-results evidence gates](docs/architecture/published-algorithm-results.md). Link the report URL and measured source commit in the relevant pull request and issue; preserve failures, unavailable metrics and declared evidence scope.

The initial source-bound observed-state pilot has a [standalone numerical report](reports/closed-loop-pilot/closed-loop-pilot-v1/index.html) and a [minimal Lotka–Volterra 2D example](reports/closed-loop-pilot/closed-loop-pilot-v1/example-2d.html), both rendered only from saved full-episode records. They are staged through the Pages report workflow; independent review, main-only deployment, and live URL/hash verification remain pending.

Before retiring local worktrees or builds, inspect their status and preserve authored files. Keep raw records and versioned published evidence intact.

The C++ quality gate covers every maintained header under `include/csl/core`,
the outcome-evidence implementation `src/contracts/outcomes.cpp`, and the
`nominal_forward`, `nominal_predecessor` and `nominal_tube` public headers under
`include/csl/reachability` and their implementations under `src/reachability`, plus
`include/csl/numeric/data.hpp`, `src/numeric/data.cpp`,
`include/csl/sets/contracts.hpp`, `include/csl/sets/data.hpp`, and `src/sets/data.cpp`. Install
`requirements-cpp-quality.txt` in a virtual environment to use clang-format and
clang-tidy 23.1.3 with CMake 3.31.6. Run the checks from the repository root:

```sh
cmake -DCSL_CPP_QUALITY_MODE=format -P scripts/ci/check_cpp_core.cmake
cmake --preset core -B build/cpp-quality -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
cmake --build build/cpp-quality --parallel 1 \
  --target csl_contracts csl_core_header_checks csl_nominal_header_checks \
  csl_nominal_forward csl_nominal_tube csl_polyhedral \
  csl_numeric header_numeric_data_hpp numeric_tests numeric_buffer_views_tests \
  csl_sets header_sets_contracts_hpp header_sets_data_hpp sets_tests sets_public_client \
  public_headers_client public_headers_lp_first_client \
  contract_tests public_client projection_predecessor_tests projection_predecessor_public_client
cmake -DCSL_CPP_QUALITY_MODE=tidy -P scripts/ci/check_cpp_core.cmake
ctest --test-dir build/cpp-quality --output-on-failure \
  -R '^(contract_tests|public_client|projection_predecessor_tests|projection_predecessor_public_client|numeric_tests|numeric_buffer_views_tests|public_headers_client|public_headers_lp_first_client|numeric_dependency_direction|sets_tests|sets_public_client)$'
```

The analyzer uses the actual selected implementation sources and each selected
header's standalone CMake compilation context. It refuses a missing command, a foreign
source tree or a tool-version mismatch. New core headers also need their entry
in `src/contracts/Tests.cmake`; nominal header contexts are registered in
`src/reachability/Tests.cmake`. This prevents a selected header without a real
compilation context from passing. The numeric data header uses the existing
`header_numeric_data_hpp` context in `src/contracts/Tests.cmake`. Set contracts use
the existing `header_sets_contracts_hpp` context there; the set data header uses
`header_sets_data_hpp`, registered in `src/sets/Tests.cmake`.
The focused policy enables core/C++ analyzers, selected bug-prone constructs and
portability checks, with warnings treated as errors. Formatting applies only to
the selected maintained source files; third-party code, immutable source captures
and generated scientific data are excluded. The
`C++ core, nominal reachability, numeric and set data tooling quality` workflow enforces this scope.
Other maintained C++ modules still require
coverage under [issue 993](https://github.com/butahlecoq/controlled-systems-lab/issues/993).

The Python tools under `scripts/ci` and `scripts/catalogue`, tests under
`tests/ci`, `scripts/reports/frozen_native_bundle.py`,
`scripts/reports/stage_native_model_catalogue.py`, and
`scripts/reports/stage_native_extended_models.py` use pinned Ruff linting/formatting
and ty type checking. The gate also covers `scripts/reports/site_additions.py`,
`scripts/reports/stage_app02.py`, and their tests
`tests/reporting/test_site_additions.py` and `tests/reporting/test_app02_saved.py`.
Install
`requirements-quality.txt` in a virtual environment, then run `ruff check`, `ruff format --check`, `ty check` and
`python -m unittest discover -s tests/ci -p 'test_*.py'` from the repository root.
The `Python tooling quality` workflow enforces these checks. Other Python
tools remain outside this initial gate; broader adoption and immutable-source
exclusions are tracked in
[issue 993](https://github.com/butahlecoq/controlled-systems-lab/issues/993).
The workflow also runs the site-addition and APP-02 tests with the standard
library. Run them locally with
`python -m unittest discover -s tests/reporting -p 'test_site_additions.py'` and
`python -m unittest discover -s tests/reporting -p 'test_app02_saved.py'`.

The same configured gate covers the 57 maintained Python compatibility entry
points under `reports/algorithm-results/tooling`. `pyproject.toml` defines the
scope for the default Ruff and ty commands above. The gate also covers all nine
maintained OPT07/OPT11 implementations in that tree, including their fixture,
record, collector and saved-report boundaries. Immutable report/source captures
elsewhere remain outside this gate.
Use `ruff check --show-files` to inspect Ruff's selected files. No explicit file
arguments are needed for the lint, format or type checks. The workflow triggers
on tooling-tree changes and exercises existing compatibility consumers with
`python -m unittest discover -s tests/reporting -p 'test_syn03_strategy_a_report.py'` and
`python -m unittest discover -s tests/reporting -p 'test_syn03_ts02_report.py'`.

The workflow exercises OPT07's oracle, collector and saved-report tests with
`python -m unittest discover -s tests/reporting -p 'test_opt07_*.py'`, OPT11's
publication tests with
`python -m unittest discover -s tests/reporting -p 'test_opt11_publication.py'`,
and its collector tests with
`python -m unittest discover -s reports/algorithm-results/tooling/opt11 -p 'test_collect.py'`.
These checks validate saved evidence and synthetic test records without running
algorithm measurements. The ty search path includes the maintained tooling root
so each OPT07/OPT11 namespace retains its local imports and direct CLI behavior.

The same default Ruff and ty scope covers the maintained discrete MPC 2D
stager and the visual-gallery tests. The workflow runs the gallery test, which
also verifies the example's saved native output and source-owned route entry.
