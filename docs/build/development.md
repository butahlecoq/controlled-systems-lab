# Development entry point

Use the canonical [glossary](../research/glossary.md), [current module composition](../architecture/framework-composition.md)
and [live issue tracker](../agents/issue-tracker.md). Read the live issue and its
closed prerequisites before choosing a module. Mathematical data support does not
imply that every strategy accepts that data.

## Configure once, check the module

Requires CMake/CTest 3.31+, a C++20 compiler and Git. Run from the repository root,
checking each exit code. `dev` uses Ninja Release; on Windows run it from a Visual
Studio developer shell with Ninja and CMake on PATH. `dev-windows` uses Visual
Studio 2022 x64 and Release. `core` uses Ninja Release with the HiGHS and Qhull
adapters disabled. First configure may acquire pinned production dependencies;
`core` avoids those two adapter vendors, not every dependency.

```sh
cmake --preset dev
cmake --build --preset dev
ctest --preset dev
```

Substitute `dev-windows` or `core` consistently for another configuration. Focused
presets build and test a module in the `dev` tree after `cmake --preset dev`:

| Task | Owning code / public seam | Focused commands |
| --- | --- | --- |
| Numeric values and storage | `src/numeric`, `include/csl/numeric` | `cmake --build --preset numeric`, then `ctest --preset numeric` |
| Polyhedral operations and conversions | `src/geometry`, `src/adapters/polyhedral` | `cmake --build --preset geometry`, then `ctest --preset geometry` |
| Report lifecycle and mathematical adapters | `scripts/reports`, `benchmarks/reporting` | `cmake --build --preset reporting`, then `ctest --preset reporting` |
| Model, scenario and identity changes | `src/model`, `src/problem`, `src/input` | Full build/test preset above; [scenario contract](../contracts/scenario-input.md) |
| Synthesis, selection and verification | `src/synthesis`, `src/verification`, `src/registry` | Full build/test preset above; [supported profiles](../architecture/framework-composition.md#supported-synthesis-profiles) |

Focused presets retain `--no-tests=error` behavior; they are local feedback, while
full native, installed-consumer and sanitizer checks remain integration gates.
Do not infer a performance improvement from test duration.

The [README installed examples](../../README.md#quick-start) use an external
`find_package(CSL CONFIG)` project. They demonstrate registered LP/convex solves,
scenario intake and LP backend substitution. They do not execute synthesis.
[PR #250](https://github.com/butahlecoq/controlled-systems-lab/pull/250) owns the
installed T-S01 Strategy A/B comparison and is open at this documentation baseline;
use its final integrated example after merge. No comparison source is claimed here.

For installation, use `cmake --install <configured-build-directory> --config Release
--prefix <absolute-install-directory>`, then the README external example commands
with that prefix. Determine the build directory from `CMakePresets.json` rather
than reusing a cache created by another generator. [Native build notes](native.md)
preserve prior platform evidence and the historical CORE-02 checks.

## Inventory and safe retirement

D: was reported full during the #251 audit. This documentation change performs no
deletion. Space pressure is a reason to inventory ownership before cleanup.

1. Run `git worktree list --porcelain` from the intended repository. For every
   candidate, resolve its exact absolute path (`Resolve-Path -LiteralPath <path>`
   in PowerShell), confirm its repository and branch, and inspect
   `git -C <path> status --short`, including untracked files.
2. Fetch current remote state when space permits. Compare the candidate commit to
   the intended integrated branch with `git merge-base --is-ancestor <candidate>
   origin/main`; inspect unique commits and PR merge state. A closed issue or PR
   alone does not establish that local commits are preserved.
3. Inventory ignored build outputs separately. Inspect `CMakeCache.txt` for source
   and binary directories, generator and options. Check whether records, failure
   captures, offline bundles or research artifacts inside the directory are the
   only retained evidence. Preserve them and their source/environment metadata
   in an agreed archive before considering the tree disposable.
4. Retire only a clean, preserved, merged worktree using `git worktree remove
   <exact-path>` without `--force`. Keep its branch until its commits are accounted
   for. Never delete the worktree directory behind Git's back.
5. For disposable build directories, resolve and inspect each exact absolute
   target again; confirm it is inside the intended workspace/build root and is
   neither the repository nor an archive. On Windows use native PowerShell
   `Remove-Item -LiteralPath <verified-build-path> -Recurse` only after these checks.
   Do not generate broad recursive deletion commands from directory listings.

Keep original research files, extracted sources, hashes, published bundles and
archival tooling intact. Record retired paths and retained evidence locations so
another contributor can understand what was removed.
