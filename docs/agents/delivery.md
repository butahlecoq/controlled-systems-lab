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

## Prepare a release candidate

1. Identify the exact reviewed source commit and proposed version/tag. Describe
   supported profiles, API/package compatibility, dependency and migration
   changes, known limitations and links to the relevant issues. Do not infer a
   stable API promise from the current `0.1.0` project version.
2. Check the [development commands](../build/development.md) for every advertised
   platform and enabled-backend configuration. Verify an external installed
   `find_package(CSL CONFIG)` consumer and the shipped examples. Record compiler,
   architecture, Release configuration, dependency pins/patches and options.
   Reuse reviewed CI outputs from the exact candidate when their provenance and
   retention permit; rebuild when source/configuration differs or artifacts
   cannot be verified. Documentation publication alone needs no native matrix.
3. Stage only the intended install tree and public sources. Include required
   dependency notices, checksums and a manifest mapping each archive to its
   source commit, configuration and validation run. Inspect archives for local
   paths, credentials and private research materials. Keep platform/toolchain
   incompatibilities explicit; an MSVC static library is not a portable binary.
4. Preserve the existing owner decision on project licensing. Before publishing
   the first distributable binary, resolve project distribution terms and check
   third-party redistribution obligations. An installed dependency notice does
   not supply a license for CSL. Candidate preparation may proceed with this
   gate recorded; it does not authorize inventing a project license.
5. Publish only after the issue's tests and independent review pass. Link the
   [GitHub Release](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases),
   exact tag/commit, checksums, example commands and verified Pages URLs. Check
   that public downloads work and that a clean installed consumer can use the
   published archive. Record the evidence in the release issue/PR.

PR validation uses read permissions and receives no release credentials. Scope
`contents: write` to a release publisher, and `packages: write` only to an actual
registry publisher. Pin workflow dependencies and follow the existing main-only
Pages deployment and stale-head checks. Check registry visibility and
[package access permissions](https://docs.github.com/en/packages/learn-github-packages/about-permissions-for-github-packages)
before describing an image as publicly usable.

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

The [published algorithm results policy](../architecture/published-algorithm-results.md)
and [record contract](../contracts/algorithm-report-records.md) still govern
measurements and scientific claims. Functional example/CI durations do not become
performance evidence. Verify local links and responsive plots, then open the
deployed example before reporting it as published.
