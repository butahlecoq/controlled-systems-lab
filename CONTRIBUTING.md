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

The native quality gate discovers every retained C/C++ source under `include`,
`src`, `tests` and `examples`, including new files. At main `9a81334f` this is
565 mutable paths and all 136 public headers. Two exact B06 measured-source
fixtures remain immutable, verified against their named captured owner; four
installed forge probes retain their checked compiler refusals. Benchmark/report
drivers, native tools/probes and compatibility sources remain required adoption
queues under [issue 993](https://github.com/butahlecoq/controlled-systems-lab/issues/993);
this scope does not claim whole-repository completion.

Install `requirements-cpp-quality.txt` for clang-format/clang-tidy 23.1.3 and
CMake 3.31.6. The canonical entry point is `scripts/ci/check_cpp_quality.py`.
For the core profile, run:

```sh
python scripts/ci/check_cpp_quality.py format
cmake --preset core -B build/quality-core \
  -DCSL_CPP_QUALITY=ON -DCSL_CPP_QUALITY_PROFILE=core
cmake --build build/quality-core --parallel 1
ctest --test-dir build/quality-core --output-on-failure -R '^installed_public_client$'
python scripts/ci/check_cpp_quality.py analyze --build build/quality-core \
  --receipt build/quality-core/cpp-quality-receipt.json
```

The complete gate also requires actual HiGHS+Qhull and CasADi profiles. Use
`CSL_CPP_QUALITY_PROFILE=highs` with both native adapters enabled, and
`CSL_CPP_QUALITY_PROFILE=casadi` with CasADi enabled and HiGHS/Qhull disabled.
Both require `BUILD_TESTING=ON`; the CasADi profile needs a matching native
`casadi_DIR` and its existing installed-consumer check. The workflow contains the
complete configure/install commands. Reconcile the three successful receipts:

```sh
python scripts/ci/check_cpp_quality.py coverage \
  --receipt build/quality-core/cpp-quality-receipt.json \
  --receipt build/quality-highs/cpp-quality-receipt.json \
  --receipt build/quality-casadi/cpp-quality-receipt.json
```

CMake generates standalone public-header targets and records exact input bytes.
The gate validates actual target ownership, compilation databases and built Ninja
dependency records, including current-byte SDK source/header copies. Installed
header contexts match each profile's actual install manifest; their three-profile
union must cover every public header, including the optional CasADi adapter. It rejects
foreign or stale profiles, missing contexts, missing optional profiles, and
uncovered new sources or private/test/example headers. Reconfigure and build
after changing native or quality configuration inputs. Quality/exported SDK
contexts use explicit configuration: source/configuration hashes reject stale
ownership before Ninja checks for any pending compile or link action. Normal
native profiles retain automatic CMake regeneration. JSON receipts from other
CI jobs can be reconciled only against identical native and quality inputs;
their compilation databases are never reused in another checkout.

The existing analyzer, portability and strict warning policy remains enforced;
compiler warnings, installed clients and sanitizer CI are retained. The
`Maintained native tooling quality` workflow enforces this complete retained-root
scope. Its artifacts contain context/coverage JSON, with 14-day retention,
without native binaries or scientific capture rewrites.

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
scope for the default Ruff and ty commands above. The nine real OPT07/OPT11
implementations in that tree remain excluded and require separate quality
adoption; immutable report/source captures elsewhere are also outside this gate.
Use `ruff check --show-files` to inspect Ruff's selected files. No explicit file
arguments are needed for the lint, format or type checks. The workflow triggers
on tooling-tree changes and exercises existing compatibility consumers with
`python -m unittest discover -s tests/reporting -p 'test_syn03_strategy_a_report.py'` and
`python -m unittest discover -s tests/reporting -p 'test_syn03_ts02_report.py'`.
