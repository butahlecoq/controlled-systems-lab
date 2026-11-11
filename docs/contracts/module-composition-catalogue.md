# Four-group module composition catalogue

The machine-readable source inventory is [module-composition-inventory-v1.json](../catalogue/module-composition-inventory-v1.json). Its module identities are tied to source paths and exported symbols. Registered providers use the IDs and versions in their registration source. Public functions and representation types use their declared C++ symbols and have no invented registry ID or module version.

The inventory is a source map, not a compiled-admission receipt. The native `csl_module_composition_catalogue` executable emits a build-specific JSON document with concrete provider admission and execution records for its finite probe profiles. It currently resolves every compiled vertex reducer against each compiled LP registration on a 2D square with one strict interior point, and resolves/re-prepares the registered TS01 analytic controller on its two-step scalar-integrator profile. The Strategy A and Strategy B concrete preparation paths are covered by `application_comparison_integration_tests`. These are functional probes, not benchmark runs.

## Reproduce

Configure and build with the repository's pinned CMake dependencies. For the common build with HiGHS and Qhull enabled:

```sh
cmake -S . -B build/catalogue -G Ninja \
  -DCSL_ENABLE_HIGHS=ON -DCSL_ENABLE_QHULL=ON -DBUILD_TESTING=ON
cmake --build build/catalogue --target csl_module_composition_catalogue -j4
build/catalogue/csl_module_composition_catalogue \
  --inventory docs/catalogue/module-composition-inventory-v1.json \
  > build/catalogue/module-composition-output.json
```

The output records compiled backend flags, each canonical candidate tuple, requested and actual provider identities/versions, first admission diagnostic, execution result, outer LP-runner call records, and reducer-specific internal counters. Outer runner records are deliberately separate from captured child-workspace calls reported through reducer metrics. A selected provider being prepared does not prove it was invoked.

Run the focused checks with:

```sh
ctest --test-dir build/catalogue --output-on-failure \
  -R '^(module_composition_inventory_source_check|module_composition_catalogue_cli|composition_catalogue_tests|registry_tests|application_comparison_integration_tests)$'
```

The source check verifies all inventory paths, provider IDs/versions and public symbols against the source snapshot, and compares the ten hull registrations with an independently authored set. The CLI check parses native JSON and verifies every emitted tuple, actual identity, exact square outcome, LP membership calls, and TS01 controller re-preparation.

## Candidate statuses

- `admitted`: the concrete request was accepted by its owning provider or strategy registry. A controller row records the complete selected strategy preparation; a component-only probe does not stand in for a composed controller receipt.
- `incompatible`: the concrete request was rejected by a source-backed dimension, representation, objective, or assurance requirement. Preserve the first diagnostic and full requested tuple.
- `implementation_missing`: the requested typed adapter or common route does not exist yet. This describes an implementation gap, not a mathematical impossibility.
- `backend_unavailable`: the exact build omitted a required optional backend. The output records enabled backends; do not infer availability from the inventory.
- `excluded`: an existing scoped policy prohibits the candidate, including acados execution and installation.

Inactive axes use `not_used` and do not create a second graph. A vertex LP provider and a terminal optimizer are different roles even if they share a backend. QuickHull2D is a public geometric reference function rather than a registered HullReducerPort provider; its 2D input guard is tested separately.

## Scope and limits

The inventory covers source-supported polytope H/V encodings, fixed-plan box/zonotope/parallelotope/ellipsoid tracks, the reachable-set and joint-trajectory strategy registrations, the finite-action and finite-table controllers, MPC11's external nominal NLP route, selected set operations, conversion providers, and optimizer roles. Faithful BTULSHOR MODIF/KPABEP/REACH functions link to the immutable source-faithful report manifest. The separate known-candidate rows retain incompatible, missing-adapter, and excluded outcomes. Finite continuous parameters are not expanded without a pinned profile.

The native CLI's dynamic rows are intentionally limited to the compiled vertex-provider cross and one registered controller profile. It does not claim that every static inventory record has a runtime admission receipt. Later runners must re-prepare each concrete generated request and separately record actual operation invocations; strategy preparation alone does not prove that execution called every declared dependency. The existing nonlinear MPC11 evidence is local numerical optimization with independent replay, not a global feedback-optimality claim. No immutable report bundle is edited.

## Delivery impact

This change adds public candidate-enumeration and hull-catalogue APIs, adds source-declared active configuration slots to strategy registration, and adds a local catalogue CLI. Exported include trees and link targets carry the additive APIs. The CLI is built from the source tree and is not installed as a package executable. Existing package consumers remain source-compatible; consumers using strategy catalogue APIs should use the two-argument overload to derive output representation/assurance from the family or provide explicit requirements. No dependency or benchmark profile is added. The installed-package hull client is expected to compile against exported package targets and execute the same concrete square/LP path.
