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

The initial C++ quality gate covers every maintained header under `include/csl/core`
and the outcome-evidence implementation `src/contracts/outcomes.cpp`. Install
`requirements-cpp-quality.txt` in a virtual environment to use clang-format and
clang-tidy 23.1.3 with CMake 3.31.6. Run the checks from the repository root:

```sh
cmake -DCSL_CPP_QUALITY_MODE=format -P scripts/ci/check_cpp_core.cmake
cmake --preset core -B build/cpp-quality -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
cmake --build build/cpp-quality --parallel 1 \
  --target csl_contracts csl_core_header_checks contract_tests public_client
cmake -DCSL_CPP_QUALITY_MODE=tidy -P scripts/ci/check_cpp_core.cmake
ctest --test-dir build/cpp-quality --output-on-failure -R '^(contract_tests|public_client)$'
```

The analyzer uses the actual outcome source and each core header's existing
standalone CMake compilation context. It refuses a missing command, a foreign
source tree or a tool-version mismatch. New core headers also need their entry
in `src/contracts/Tests.cmake`; this prevents an unanalysed header from passing.
The focused policy enables core/C++ analyzers, selected bug-prone constructs and
portability checks, with warnings treated as errors. Formatting applies only to
the selected maintained source files; third-party code, immutable source captures
and generated scientific data are excluded. The `C++ core tooling quality`
workflow enforces this initial gate. Other maintained C++ modules still require
coverage under [issue 993](https://github.com/butahlecoq/controlled-systems-lab/issues/993).
