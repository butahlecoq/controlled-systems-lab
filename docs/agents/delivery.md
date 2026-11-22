# Delivery through GitHub

When a delivery or publication uses a corrected or inferred scientific source
variant, follow the [source-variant evidence standard](../architecture/decisions/0004-source-variant-evidence-standard.md).
Keep historical records and published values immutable, identify the reference
variant, and preserve owner-only decisions and run authorization as explicit
gates.

Use this guide when changing public APIs, dependency pins, installation, executable
examples or publication workflows. In the PR, record the effect on consumers and
choose a delivery outcome: no release needed, release candidate preparation, or
an update to an existing release/package workflow. Include the reason and any
remaining gates. A CMake project version is not evidence of a published release.

The issue 966 documentation migration removes Markdown working documents from
installed package trees. Installed consumers use public headers, JSON schemas
and executable behavior; package checks must not require Markdown under
`share/CSL` or `share/doc/CSL`. Record this removal in package impact notes
because existing consumers may have linked to those paths.

The installed `schemas/model/continuous-v1.schema.json` is an authoring aid for
`input::load_continuous_model`. The loader accepts continuous affine rates
`x'=Ax+Bu+Ew+a` with zero-order-held inputs on a strictly increasing T+1 time
grid. LTI coefficients stay constant; LTV endpoint pairs interpolate linearly
within each interval. Call `model::discretize` explicitly before using a
discrete `SystemModel` in later builders. Its RK4 step-doubling difference is a
local estimate, not a certified global error bound; failed or exhausted
integration returns no discrete model. The native loader additionally checks
duplicate keys, finite binary64 values, exact integers, dimensions, quotas,
matrix shapes and the time grid. Descriptor mass matrices, nonlinear dynamics
and alternate holds require separate capabilities.

## Choose the artifact

| Consumer need | Delivery |
| --- | --- |
| Inspect a PR's test/build output | Actions artifact with explicit retention; link the run and exact commit |
| Install a reviewed C++ version | GitHub Release with source/tag and, when justified, platform-specific CMake install archives |
| Read numerical results or learn an algorithm | Versioned Pages reports, raw records and minimal visual examples |
| Pull an executable environment through a registry | GitHub Packages only when a concrete supported-client need exists, for example a GHCR container |

Prefer Release downloads for the current CMake library. GitHub Packages supports
specific [registry clients and formats](https://docs.github.com/en/packages/learn-github-packages/introduction-to-github-packages),
and does not provide a generic CMake/C++ package registry. Do not add a container
or another ecosystem solely to populate the Packages tab. Actions artifacts are
temporary CI outputs, not stable release URLs.

## SDK and evidence release identities

- **SDK releases** are published in [csl-sdk](https://github.com/butahlecoq/csl-sdk/releases). The first release, [v0.1.0](https://github.com/butahlecoq/controlled-systems-lab/releases/tag/v0.1.0), stays at its original address. Use the tag and title `vMAJOR.MINOR.PATCH`, with all three
  numbers matching `project(CSL VERSION ...)` in the tagged `CMakeLists.txt`.
  Choose the next version before preparing the candidate. Keep initial
  development releases in the `0.x` series until the public API is declared
  stable.
- **Evidence releases** in the research repository retain their `evidence/` tags and descriptive titles.
  Preserve existing download URLs. Set new evidence releases to
  `--latest=false` so the latest SDK release remains the entry point for
  library users.

After the gates below pass, create an annotated tag from the SDK checkout at the reviewed commit on
`main` and push only that tag. Verify that the remote tag resolves to the
reviewed commit before creating the GitHub Release. Publish the source release
with the tag as its title and the reviewed release notes. Set `tag` to the
verified tag and `release_notes` to the notes file.

```sh
gh release create "$tag" --repo butahlecoq/csl-sdk --verify-tag \
  --title "$tag" --notes-file "$release_notes" --latest
```

Each version identifies one commit. Use a new version for a source correction.

For a source release, GitHub supplies the tag's source archive. Include the
source commit, tested profiles, validation links, and the README Quick start
at that tag in the release notes. Apply the distribution gate below before
adding install archives or other binaries.

## Prepare a release candidate

1. Identify the exact reviewed source commit and proposed version/tag. Describe
   supported profiles, API/package compatibility, dependency and migration
   changes, known limitations and links to the relevant issues. Do not infer a
   stable API promise from the early `0.x` version series.
2. Check the [SDK native CI workflow](https://github.com/butahlecoq/csl-sdk/blob/main/.github/workflows/native.yml) for every
   advertised platform and enabled-backend configuration. Use the
   [SDK quick start](https://github.com/butahlecoq/csl-sdk#quick-start) to verify an external installed
   `find_package(CSL CONFIG)` consumer and the shipped examples. Record compiler,
   architecture, Release configuration, dependency pins/patches and options.
   Reuse reviewed CI outputs from the exact candidate when their provenance and
   retention permit; rebuild when source/configuration differs or artifacts
   cannot be verified. Documentation publication alone needs no native matrix.
3. When shipping install archives, stage only the intended install tree and
   public sources. Include required dependency notices, checksums and a
   manifest mapping each archive to its source commit, configuration and
   validation run. Inspect archives for local
   paths, credentials and private research materials. Keep platform/toolchain
   incompatibilities explicit; an MSVC static library is not a portable binary.
4. Preserve the existing owner decision on project licensing. Before publishing
   the first distributable binary, resolve project distribution terms and check
   third-party redistribution obligations. An installed dependency notice does
   not supply a license for CSL. Candidate preparation may proceed with this
   gate recorded; it does not authorize inventing a project license.
5. Publish only after the issue's tests and independent review pass. Link the
   [GitHub Release](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases),
   exact tag/commit, install archive checksums if applicable, example commands
   and verified Pages URLs. Check that public downloads work. For a source
   release, build and install from the downloaded source and run the external
   consumer against that installation. For an install archive, run the consumer
   against the extracted package. Record the evidence in the release issue/PR.

PR validation uses read permissions and receives no release credentials. Scope
`contents: write` to a release publisher, and `packages: write` only to an actual
registry publisher. Pin workflow dependencies and follow the existing main-only
Pages deployment and stale-head checks. Check registry visibility and
[package access permissions](https://docs.github.com/en/packages/learn-github-packages/about-permissions-for-github-packages)
before describing an image as publicly usable.

## Main branch merge gates

Both repositories protect `main` with pull-request-only updates, administrator
enforcement, no force pushes or branch deletion, and required validation checks.
The active settings and their verification evidence are tracked in
[#1263](https://github.com/butahlecoq/controlled-systems-lab/issues/1263).

| Repository | Required status contexts |
| --- | --- |
| `controlled-systems-lab` | `Native validation`, `Reporting validation`, `Python quality validation`, `Research SDK validation`, `C++ core quality validation` |
| `csl-sdk` | `SDK validation`, `Native quality / complete retained scope` |

Each context is a stable aggregate. A path-scoped check publishes a successful
skip only after the shared router confirms its inputs are unchanged; a routing
failure or a failed required check fails the aggregate. Thus unrelated changes
retain the report-only and local development paths without leaving a required
status absent. The SDK aggregate covers the install/research consumer, every
compiler profile, and both real-IPOPT strategy runs.

Emergency recovery requires a temporary, narrowly scoped change to the affected
repository's protection settings by its owner. Record the reason, repository,
affected commit, and validation evidence in #1263 (or a linked incident issue),
then restore and verify the original required contexts immediately after the
recovery merge. Do not force-push or delete `main`.

## Visual examples accompany numerical algorithms

When an implemented algorithm has a supported small 2D case, add or extend a
discoverable Pages example alongside its numerical report. Show complete minimal
inputs, a labelled plot, an independently checkable answer, reproduction commands
and the source commit/raw record links. Hull examples retain original point IDs
and distinguish hull vertices from interior, edge and duplicate points. Control
examples identify state dimension, time stages, coordinates and the actual
supported strategy; a scalar system plotted in two control coordinates is still
a scalar system.

Use the existing Omarchy report appearance. Keep educational pages separate from
immutable evidence bundles and preserve their manifests, archives and URLs. Saved
outputs can support a new illustration without rerunning a benchmark. Label an
explanatory construction as an illustration unless it replays recorded algorithm
steps. If no supported low-dimensional case exists, record that limitation and
the follow-up issue rather than fabricating a result.

Maintained Python report publishers and their publication tests belong in the
configured Ruff and ty scopes in `pyproject.toml`. Add their paths and the
report payloads they validate to the Python quality workflow filters so edits run
lint, formatting, type and focused publication checks.

The [published algorithm results policy](../architecture/published-algorithm-results.md)
governs measurements and scientific claims. Report record readers and publication
checks live in [`scripts/reports`](../../scripts/reports/) and are exercised by
[`tests/reporting`](../../tests/reporting/). Functional example/CI durations do
not become performance evidence. Verify local links and responsive plots, then
open the deployed example before reporting it as published.
