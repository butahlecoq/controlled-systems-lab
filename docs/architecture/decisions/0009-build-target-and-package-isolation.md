# ADR 0009: Build module and installed package boundaries

Date: 2026-11-21
Status: Accepted

## Context

The Lab builds native modules as well as research reports and package consumers. Each needs the right dependency visibility so a source-tree success also means something for an installed consumer.

## Decision

Modules own source membership and dependencies in `Module.cmake` and their tests in `Tests.cmake`. The root includes those declarations in project scope and uses the same module order for tests. Dependency pins and package configuration are therefore shared. The module policy centralizes target mechanics. The shared test helper adds no product include paths. Consumer-facing tests obtain public requirements by linking targets. Tests of implementation details declare their private include paths in their own registrations.

Measurement executables are private reporting targets and can require an explicitly enabled adapter. The test verifier catalogue contains test-only authorities and stays outside the package exports.

The MPC-11 nonlinear replay is an optional standalone consumer of the existing
`CSL::simulation` target. The REVIEW-05 build-phase probe is injected into the
repository configure with `CMAKE_PROJECT_CSL_INCLUDE`, allowing the probe and
tests to reuse one build tree. Contract headers are checked in separate
translation units so one header cannot gain undeclared dependencies through
include order; the core-header subset remains a dedicated build target.

The installed-client check stages the curated consumer project and all of its translation units in a separate source tree. It resolves CSL via `find_package(CSL CONFIG)` against the installed prefix. Staging all consumer sources keeps a new curated target from silently losing its source during the package check. A second isolated consumer builds the README examples from their public sources and templates. The install audit checks the exported targets, headers and applicable dependency notices. Working Markdown stays in the repository and is excluded from the installed package.

## Verification

The build uses the root module list, `cmake/ModulePolicy.cmake`, `cmake/TestCatalog.cmake`, and `cmake/RunInstalledClient.cmake`. ADR 0002 records the corresponding native dependency boundaries.
