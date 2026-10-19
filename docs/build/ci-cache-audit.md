# Native CI cache audit

Audit for [#481](https://github.com/butahlecoq/controlled-systems-lab/issues/481),
2026-10-19. Source baseline: `3cfed6cc96aa9bac4ecd0d1a936ed0575011fd6d`.
Recommend verified archive downloads on every platform and compiler caching for
Linux Ninja builds. Preserve the complete [native event/matrix policy](ci.md).
This records the design and the completed hosted cache experiment. The experiment
proves reuse in one equivalent cold/warm pair; runtime benefit remains inconclusive.

## Repeated work and coverage

The successful [Windows job 117767211466, run 39158702083](https://github.com/butahlecoq/controlled-systems-lab/actions/runs/39158702083/job/117767211466)
actually compiles isolated HiGHS and product HiGHS. Its log records
`native-probes/Release/bin/highs.lib` at 19:32:31.4398717 UTC and
`tmp/native/Release/bin/highs.lib` at 19:35:47.9261506 UTC on 2026-10-18.
The [source-backed issue comment](https://github.com/butahlecoq/controlled-systems-lab/issues/481#issuecomment-6254746064)
also records these outputs. Completion times identify work; their difference
does not measure time saved by caching. No translation-unit or cache-hit count
has been established from these observations.

| Input | Product graph | Isolated graph | Interpretation |
| --- | --- | --- | --- |
| HiGHS 1.11.0 | Private static `highs`, linked by `csl_highs_lp`, installed for final static linking | Own static `highs`, linked by `dependency_probes` | Confirmed repeated native library compilation, with different inputs: product applies the pinned HVectorBase initialization patch; probe uses upstream source |
| Contract sources | `csl_contracts` | Own `csl_contracts` from the same six source paths | Separate builds of model, problem, geometry, outcomes, execution and synthesis; log records each graph's archive |
| Qhull 8.0.2 | `csl_qhull_r` static C library | Absent | Product-only vendor compilation; the same Windows log records its archive at 19:33:10.5393886 UTC |
| Eigen 3.4.0 | Headers consumed by objectives | Headers consumed by numerical probe | Repeated acquisition and header processing, no standalone Eigen library compilation |
| nlohmann JSON 3.11.3 | Private headers, shared product FetchContent identity | Header interface target | Repeated acquisition/header processing, no standalone JSON library compilation |
| doctest 2.4.11 | Test-only headers | Test-only headers | Repeated acquisition/header processing, no separate compiled doctest library; implementations compile inside test executables |

Sources: [product contracts](../../src/contracts/Module.cmake),
[HiGHS and patch contract](../../cmake/HighsDependencies.cmake),
[Qhull](../../cmake/QhullDependencies.cmake),
[Eigen](../../cmake/ObjectivesDependencies.cmake),
[JSON](../../cmake/JsonDependencies.cmake),
[test dependencies and external project](../../cmake/Dependencies.cmake),
[isolated project](../../probes/core-01/CMakeLists.txt).
Different options, paths and the product patch prevent assuming interchangeable
HiGHS objects or predicting intra-job compiler-cache hits.

The unique direct dependency checks in
[dependency_probes.cpp](../../probes/core-01/dependency_probes.cpp) are:

| Probe | Independent check to retain |
| --- | --- |
| Eigen affine map | Row-major neutral buffer mapping, affine result and rank-one singular transition |
| HiGHS LP | Optimal objective/solution, zero-objective feasibility, infeasibility and unboundedness remain distinct |
| HiGHS convex QP | PSD residual-square minimizer, squared objective and separately reported original Euclidean norm |
| HiGHS semidefinite QP | One optimizer with a flat coordinate; explicitly does not prove a unique optimizer or family adapter |
| HiGHS instances | Separate problems, solutions and objectives across two solver instances |
| JSON | Typed authored values and malformed-syntax rejection |

The isolated graph also builds `contract_tests` and `caller_example`. The outer
`native_dependency_probes` CTest entry selects only `^dependency_probes$`;
do not describe those other executables as executed by that entry.
`BUILD_ALWAYS TRUE` invokes the nested build each time; it does not force every
up-to-date source to recompile. Keep the isolated integration graph and its test.

Product module tests, literal numeric probes and
[installed clients/examples](../../cmake/RunInstalledClient.cmake) exercise
different boundaries: staged `find_package(CSL CONFIG)` usage, public headers,
private dependency leakage, notices, exports and shipped examples. They must
continue to configure, build and run independently. The `core`/`highs` package
lanes must retain their disabled-vendor acquisition assertions. GCC ASan/UBSan
must continue executing instrumented public modules and consumers; it currently
disables isolated probes. See [workflow](../../.github/workflows/native.yml),
[presets](../../CMakePresets.json) and
[installed-test configuration](../../cmake/InstalledTests.cmake).

## Cache design

Use a dedicated archive directory containing only original pinned downloads,
separate from extracted sources and build trees. Name entries by dependency and
SHA256. Retain every declared `URL_HASH`, including when the archive URL is a
local cached path. CMake verifies matching downloaded archives before reuse;
the hash protects content integrity, while a cache key alone does not.
[ExternalProject download contract](https://cmake.org/cmake/help/v3.31/module/ExternalProject.html#download-step-options).

Both projects require CMake 3.31. Under their effective CMP0168 NEW policy,
FetchContent **ignores `DOWNLOAD_DIR`**. Merely forwarding that option cannot
implement this design. Prefer a small shared helper that acquires archives with
`file(DOWNLOAD ... EXPECTED_HASH SHA256=... TLS_VERIFY ON)` and hands the verified
local archive to FetchContent. A corrupt entry must be rejected or replaced with
a hash-verified download. Extract separately for the product and probes, so the
product patch never modifies shared cached content.
[CMP0168](https://cmake.org/cmake/help/v3.31/policy/CMP0168.html),
[file download](https://cmake.org/cmake/help/v3.31/command/file.html#download),
[FetchContent](https://cmake.org/cmake/help/v3.31/module/FetchContent.html).

Start compiler caching with Linux GCC/Clang Ninja via both
`CMAKE_C_COMPILER_LAUNCHER` and `CMAKE_CXX_COMPILER_LAUNCHER`. Caching only C++
misses Qhull and HiGHS C sources. Forward launchers and archive-directory settings
explicitly to `core01_native_probes`; ExternalProject does not inherit arbitrary
parent toolchain settings. Forward the C++ launcher through the separate
installed-client and examples configurations too.
[ExternalProject configure contract](https://cmake.org/cmake/help/v3.31/module/ExternalProject.html#configure-step-options).
The launcher property supports Ninja/Makefile generators; the current Visual
Studio 17 2022 lane cannot gain compiler caching merely by setting it. Keep
Visual Studio coverage and use archive caching there.
[CMake launcher support](https://cmake.org/cmake/help/v3.31/prop_tgt/LANG_COMPILER_LAUNCHER.html).

ccache caches compilation results, not configure, link, install or test work.
It hashes compiler identity, options, source and included content; paths can
reduce reuse. Keep default correctness checks, avoid permissive sloppiness,
use an explicit size limit and report cacheable calls, hits, misses and
uncacheable reasons. Use `compiler_check=content` if hosted compiler timestamp
changes cause misses. Separate sanitizer storage and key prefixes from Release,
with no restore fallback across that boundary. This segregation is repository
policy in addition to ccache's option hashing; never substitute Release objects
for instrumented compilation.
[ccache manual](https://ccache.dev/manual/4.10.html).

## Keys and trust

Archive keys should cover schema, runner OS/architecture and hashes of dependency
declarations, probe declarations and patch inputs. Compiler-cache compatibility
prefixes must additionally cover compiler identity/version, CMake/ccache version,
generator, configuration, sanitizer flags and backend/probe options. A suffix
such as source commit/run can allow immutable cache snapshots to accumulate new
entries; restore prefixes must retain every compatibility boundary. Include
`ApplyPinnedHighsPatch.cmake` and its contract in invalidation inputs.
Keep configured build directories, extracted source trees, install prefixes and
publication artifacts out of both caches.

GitHub permits PRs to restore base/default-branch caches, including fork PRs;
PR-created caches are scoped to the PR merge ref and cannot be restored by the
base branch. Treat cache contents as readable by contributors: store no secrets.
Use ordinary `pull_request` execution with `contents: read`, no publication
credentials and no privileged trigger running PR code. Prefer explicit
restore/save steps, with trusted main/manual saves and restore-only PR access;
release publishers should use a separate namespace or clean build.
[GitHub cache scope and trust](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching).

The initial [key generator](../../scripts/ci/cache_keys.py) and its
[CLI tests](../../tests/ci/test_cache_keys.py) implement these boundaries:
PRs compute main-compatible restore keys with saving disabled; manual runs on a
development branch use a separate branch namespace; tag runs cannot save.
Compiler prefixes include all explicit compatibility fields and dependency/patch
inputs; a source-revision suffix allows a new immutable snapshot without broadening
the compatible restore prefix. Archive snapshots also include lane/context:
each lane owns its immutable archive set, so a faster core-only job cannot
publish a partial set under a full/probe job's key. The bytes remain independently
verified even when compiler or configuration differences partition storage.

Pin cache actions to reviewed full commit SHAs. On the audit date, the official
`v6.1.0` tag resolves to `55cc8345863c7cc4c66a329aec7e433d2d1c52a9`;
check runner compatibility and its Node 24 runtime before adoption.
[Official release](https://github.com/actions/cache/releases/tag/v6.1.0),
[tag reference](https://api.github.com/repos/actions/cache/git/ref/tags/v6.1.0),
[action runtime](https://github.com/actions/cache/blob/55cc8345863c7cc4c66a329aec7e433d2d1c52a9/action.yml).

## Evidence required before closing #481

The initial [archive helper](../../cmake/DependencyArchive.cmake) and
[CMake integration tests](../../tests/cmake/test_dependency_archive.py) implement
the raw-archive part of this design. Four local tests with CMake 3.31.6 verify
fresh-extraction reuse after the original download disappears, changed-pin
separation, corrupt-byte replacement/rejection and the empty-option direct path.
Two separate Windows Visual Studio core configurations also recorded Eigen/JSON
archive misses followed by hash-verified hits in a fresh build directory.
This proves local archive behavior, not hosted compiler-cache reuse or reduced
wall-clock time. Six local CLI tests also pass for pin/patch invalidation,
incompatible compiler/configuration/options/lane keys and PR/manual trust scopes.
The additional lane-ownership regression first reproduced a shared archive key
between core and full builds, then passed after snapshots were partitioned by
the complete compatibility context.
The shared [setup action](../../.github/actions/native-cache-setup/action.yml)
and [finish action](../../.github/actions/native-cache-finish/action.yml) wire
these caches into the unchanged native coverage lanes. Linux uses ccache with a
1 GiB limit and content-based compiler checking. Windows retains Visual Studio
and records an archive-only compiler label; its actual compiler version remains
in the native configure log. Compiler caching is not enabled there. No configured
trees, extracted sources, installed packages or report bundles enter a cache.

Dispatch the native workflow on the implementation branch twice with `clean=false`
to collect cold and warm snapshots in that branch's namespace. Use `clean=true`
for full manual validation with no restore/save and empty compiler launchers.
Default PR validation is restore-only. The entire matrix remains enabled for
manual runs. Context, keys, restore results and actual compiler counters are
uploaded as `native-cache-<lane>-<attempt>` Actions artifacts with seven-day
retention; these are temporary validation evidence, not published install bundles.
The 369-test reporting suite also passed locally (six skips, no failures).
Hosted cold/warm, clean and PR-policy evidence are recorded below. Independent
Spec and Standards reviews are linked in [PR #490](https://github.com/butahlecoq/controlled-systems-lab/pull/490).

Retain hosted links, exact head SHA, tool versions, options, archive hashes,
cache keys and restore/save results for each experiment:

1. Cold run: new namespace and empty compiler/archive caches, full matrix green.
2. Warm equivalent run: fresh build directories, same inputs, restored archives
   and compiler cache; log actual verified archive reuse and ccache statistics.
   An Actions `cache-hit` alone does not prove compiler hits.
3. Pin/patch invalidation: demonstrate changed key inputs and appropriate misses;
   verify the product patch postimage and independent upstream probe remain
   correct. Show incompatible sanitizer/backend keys cannot restore each other.
4. Trust check: inspect PR restore/save policy and permissions; confirm no PR save
   enters trusted main/release scope.
5. Clean manual run: offer dispatch with both cache restore/save disabled and
   empty launchers, retaining all jobs and tests. Normal local builds must also
   work with no cache directory or launcher configured.

## Hosted experiment, exact source `bf028c6`

The [durable evidence record](ci-cache-evidence-2026-10-19.json) preserves the
actual context, full keys, restore results, raw ccache counters, run/job/selected
step timestamps, Actions artifact IDs/digests, each artifact file's SHA256 and
the source-log SHA256s. All four runs used source
`bf028c6ebc9f736e294e1dd1a5985e55b61b2d27`; the PR run used GitHub's
synthetic merge checkout, while branch dispatches built that source directly.
The hosted artifacts have seven-day retention, so the JSON retains their
provenance and observations after expiry.

| Run | Native result | Observed policy |
| --- | --- | --- |
| [PR 39168262592](https://github.com/butahlecoq/controlled-systems-lab/actions/runs/39168262592) | Six lanes and aggregate passed | Main-compatible restore scope; all six `save_allowed=false`. |
| [Cold branch dispatch 39168299468](https://github.com/butahlecoq/controlled-systems-lab/actions/runs/39168299468) | Six lanes and aggregate passed | All six archive restores and five Linux compiler restores missed; eleven new snapshots were saved in the branch namespace. |
| [Clean dispatch 39168428358](https://github.com/butahlecoq/controlled-systems-lab/actions/runs/39168428358) | Six lanes and aggregate passed | `clean=true`: no cache restore/save and disabled C/C++ launchers. |
| [Warm branch dispatch 39170021830](https://github.com/butahlecoq/controlled-systems-lab/actions/runs/39170021830) | Six lanes and aggregate passed | Same per-lane context and keys as cold; all six archive and five Linux compiler restores hit. |

The same five Linux contexts used GCC 13 or Clang 18, CMake 3.31.6 and ccache
4.9.1, with Release or sanitizer options kept in separate keys. Windows used
Visual Studio and archive-only caching. The cold and warm jobs configured fresh
build directories. The warm Release GCC log records CMake's hash-verified
archive reuse for Eigen, JSON, HiGHS, Qhull and doctest, including separate
product/probe extraction; the package-core log records verified Eigen, JSON and
doctest reuse. The raw hashes and artifact provenance are in the JSON.

| Lane | Cold ccache hits / misses | Warm ccache hits / misses | Warm archive / compiler restore |
| --- | ---: | ---: | --- |
| Release GCC 13 | 12 / 676 | 646 / 42 | hit / hit |
| Release Clang 18 | 12 / 672 | 646 / 38 | hit / hit |
| Package core | 4 / 206 | 207 / 3 | hit / hit |
| Package HiGHS | 4 / 439 | 421 / 22 | hit / hit |
| GCC sanitizers | 4 / 473 | 455 / 22 | hit / hit |
| Windows MSVC | no ccache | no ccache | hit / not enabled |

Hits are `direct_cache_hit + preprocessed_cache_hit`; misses are ccache's
`cache_miss` counter, each zeroed before that job's work. These are work counts,
not a speedup ratio. Every completed Linux lane also reported four
`compile_failed` entries in both cold and warm counters; their cause was not
established. All native tests passed. The clean core job alone passed 75 CTests
with empty archive/compiler restore fields and no launchers; the clean matrix
passed all six lane and aggregate gates. The separate [reporting PR run
39168262688](https://github.com/butahlecoq/controlled-systems-lab/actions/runs/39168262688)
also passed.

For pin/patch invalidation, the real key generator read copies of the frozen
Git inputs and the hosted core context. Its baseline keys match the uploaded
core artifact and existing cache inventory. Independently changing the HiGHS
pin (`v1.11.0` to `v1.11.1`), patch postimage (`next = nullptr;` to
`next = 0;`) or patch-contract bytes changed both archive and compiler keys;
the hosted inventory returned zero matches for the changed exact archive keys
and strict compiler prefixes. These are key/inventory misses, not executed
changed-vendor builds. The four real CMake archive tests separately checked
fresh extraction, changed-pin separation, corrupt-entry replacement/rejection
and the explicit empty-cache path. The product keeps its pinned patch while the
independent probe uses upstream HiGHS. Sanitizer and backend options have
different compatibility keys and cannot restore one another's object snapshot.

The run and step timestamps are kept separately in the JSON. One equivalent
cold/warm pair establishes reuse but does not establish a repeatable runtime
benefit. No performance benchmark or numerical algorithm benchmark was run.
Any later speedup report needs repeated equivalent hosted samples, overhead
and queue/configure/compile/link/test interval analysis before a claim.
