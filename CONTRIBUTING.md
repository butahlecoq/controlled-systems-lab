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
compiler warnings, installed clients and sanitizer CI are retained. First-party
tests link the compiled `doctest::doctest_with_main` target; custom entry points
link `csl_doctest_runtime`. Do not define `DOCTEST_CONFIG_IMPLEMENT` or
`DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN` in maintained sources or compiler flags.
The gate rejects that ownership regression with the required target names. The
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
`requirements-quality.txt` and `scripts/reports/requirements.txt` in a virtual environment, then run `ruff check`, `ruff format --check`, `ty check` and
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

The shared publication spine also uses the default Ruff and ty gate: report data,
source identity, publication policies and registrations, collection, rendering,
site staging, page design, landing pages, the gallery, the learning book, and
figure styling/plotting. The B04-C source-owner adapter and its snapshot tests
are included. Run the matching saved-data and malformed-input consumers with:

```sh
python -m unittest tests.reporting.test_report_data tests.reporting.test_render \
  tests.reporting.test_publication_policy tests.reporting.test_report_source_identity \
  tests.reporting.test_registered_kinds tests.reporting.test_landing \
  tests.reporting.test_learning_book tests.reporting.test_plot \
  tests.reporting.test_b04_publication_source_snapshot \
  tests.reporting.test_publication_spine_boundaries
```

The reporting requirements add the pinned Matplotlib producer and JSON Schema
validator to the quality environment. These tests validate saved inputs and
render reports; they do not launch benchmarks. Frozen evidence source capsules
remain outside the maintained-file formatting/type scope. In particular, B04-C
publication checks select its authenticated, versioned historical source bytes;
formatting a maintained helper does not change the execution source of an old
capture. The EXT04 observed-replay, finite-feedback and three GEO07 publication owners
use the same exact inventory and archive checks for retained routes and join
the default quality scope. Use `ruff check --show-files` for the current selected paths; broader Python
adoption remains tracked in issue 993.

The workflow additionally exercises the saved convex/collector/gallery consumers,
publication lifecycle tests, and the EXT04, finite-feedback and GEO07 owner
families. Publisher-byte identity checks apply to unpinned publications; retained
historical routes require both their exact source inventory and the exact
regenerated archive. Repacking a native evidence ZIP changes its identity bytes
and cannot reuse a historical route.

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
stager and the focused discrete-MPC stager tests. The workflow runs the gallery test, which
also verifies the example's saved native output and source-owned route entry.
