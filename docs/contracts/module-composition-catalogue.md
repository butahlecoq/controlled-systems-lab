# Four-group module composition catalogue

The machine-readable source inventory is [module-composition-inventory-v1.json](../catalogue/module-composition-inventory-v1.json). Its module identities are tied to source paths and exported symbols. Registered providers use the IDs and versions in their registration source. Public functions and representation types use their declared C++ symbols and have no invented registry ID or module version.

The inventory is a source map, not a compiled-admission receipt. The native `csl_module_composition_catalogue` executable emits build-specific JSON with concrete receipts for its finite profiles: every compiled hull reducer and LP-provider tuple on a 2D square; the Phase-I priority-tie profile; five actual finite-action representation tracks; Qhull H-to-V conversion; registered box outer approximation; QuickHull2D and its 4D rejection; source-faithful BTULSHOR KPABEP/REACH routes; and TS01 strategy preparation/re-preparation. Strategy A and Strategy B preparation paths are also covered by `application_comparison_integration_tests`.

`full_catalogue.py` adds the exact three 941 task contracts and enumerates nine source-backed controller/function routes over each task's separate continuous and finite action profiles. Its 3,318 rows expand Strategy A's reducer and three LP-provider roles, Strategy B's configured LP role, the nominal forward operation's reducer and nested LP/converter roles, and the five finite nominal output representations. It also emits 45 fixed-plan representation and terminal-LP tuples, 24 full-task QuickHull and source-faithful MODIF/KPABEP/REACH candidate rows, and 12 task-scoped polyhedral-function rows. Missing model adapters preserve their active module choices. Structural `not_used` roles are reserved for operations that bypass them. The native CLI runs the actual `TerminalOptimizer::solve` on the TS01 terminal slice `[0,1]` and records both the terminal LP and convex provider. The wrapper invokes `qualify_mpc11_routes.py` with the caller-selected MPC11 environment; that script validates task/source binding and constructs each existing LV/fuel do-mpc controller and CasADi `IpoptInterface` without solving an NLP. The output pins task/scenario hashes and retains orbit, nonlinear affine-adapter, and feedback predecessor gaps with their first unmet fields. This is a finite catalogue, not a claim that future controller adapters work.

These are functional admission and source-preparation probes. They do not run episodes or benchmarks.

## Reproduce

Configure and build with the repository's pinned CMake dependencies. For the common build with HiGHS and Qhull enabled:

```sh
cmake -S . -B build/catalogue -G Ninja \
  -DCSL_ENABLE_HIGHS=ON -DCSL_ENABLE_QHULL=ON -DBUILD_TESTING=ON
cmake --build build/catalogue --target csl_module_composition_catalogue -j4
build/catalogue/csl_module_composition_catalogue \
  --inventory docs/catalogue/module-composition-inventory-v1.json \
  > build/catalogue/module-composition-output.json

scripts/catalogue/full_catalogue.py \
  --native-cli build/catalogue/csl_module_composition_catalogue \
  --mpc11-python <MPC11_CONTROLLER_ENV>/bin/python \
  > build/catalogue/full-module-composition-output.json
python3 scripts/catalogue/check_full_catalogue.py \
  build/catalogue/full-module-composition-output.json .
```

The output records compiled backend flags, each canonical candidate tuple, requested and actual provider identities/versions, first admission diagnostic, execution result, outer LP-runner call records, and reducer-specific internal counters. Outer runner records are deliberately separate from captured child-workspace calls reported through reducer metrics. A selected provider being prepared does not prove it was invoked.

Run the focused checks with:

```sh
ctest --test-dir build/catalogue --output-on-failure \
  -R '^(module_composition_inventory_source_check|module_composition_catalogue_cli|composition_catalogue_tests|registry_tests|application_comparison_integration_tests)$'
```

The source check verifies inventory paths, provider IDs/versions and public symbols against source and compares the ten hull registrations with an independently authored set. `check_output.py` verifies native component tuples, actual identities, exact square result, completed LP membership calls, all five representation executions, priority-tie diagnostics, Qhull/box and generator operation admission, geometric reference calls, the actual terminal optimizer result, and TS01 re-preparation. `check_full_catalogue.py` independently constructs the Strategy A/B and nominal-forward module cross-products, checks all five nominal representations and predecessor/terminal-LP combinations, validates task/action identities and dimensions, rejects mutated task/source bindings, validates external prepare receipts, distinguishes fixed-plan support from missing predecessor adapters, checks full-task source-faithful/QuickHull choices, and verifies every supporting-operation identity is represented in the finite output.

## Candidate statuses

- `admitted`: the concrete request was accepted by its owning provider or strategy registry. A controller row records the complete selected strategy preparation; a component-only probe does not stand in for a composed controller receipt.
- `incompatible`: the concrete request was rejected by a source-backed dimension, representation, objective, or assurance requirement. Preserve the first diagnostic and full requested tuple.
- `implementation_missing`: the requested typed adapter or common route does not exist yet. This describes an implementation gap, not a mathematical impossibility.
- `backend_unavailable`: the exact build omitted a required optional backend. The output records enabled backends; do not infer availability from the inventory.
- `excluded`: an existing scoped policy prohibits the candidate, including acados execution and installation.

Inactive axes use `not_used` and do not create a second graph. A vertex LP provider and a terminal optimizer are different roles even if they share a backend. QuickHull2D is a public geometric reference function rather than a registered HullReducerPort provider; its 2D input guard is tested separately.

## Scope and limits

The inventory covers source-supported polytope H/V encodings, fixed-plan box/zonotope/parallelotope/ellipsoid tracks, the reachable-set and joint-trajectory strategy registrations, the finite-action and finite-table controllers, MPC11's external nominal NLP route, selected set operations, conversion providers, and optimizer roles. Faithful BTULSHOR MODIF/KPABEP/REACH functions link to the immutable source-faithful report manifest. The separate known-candidate rows retain incompatible, missing-adapter, and excluded outcomes. Finite continuous parameters are not expanded without a pinned profile.

The native CLI probes compiled component operations and selected controller routes; the wrapper enumerates the finite controller/task/module cross product and reports whether a complete graph can be prepared. Strategy preparation does not prove every prepared dependency was invoked, and fixed-plan propagation does not prove predecessor or feedback recovery. The MPC11 rows mean only that the source-defined controller/NLP was constructed in the selected environment after task/source binding validation; no episode or solver iteration was performed. Existing nonlinear MPC11 numerical evidence is local optimization with independent replay, not a global feedback-optimality claim. No immutable report bundle is edited.

## Delivery impact

This change adds public candidate-enumeration and hull-catalogue APIs, source-declared active strategy configuration slots, and a local catalogue tool. The native tool links the already delivered nominal, approximation, QuickHull, source-faithful geometry, generator-operation, and optional Qhull targets. The tool and wrapper are source-tree utilities and are not installed as package executables. Existing package consumers remain source-compatible; the additive API is installed through the normal header/target exports. No dependency or benchmark profile is added. Installed package clients verify the exported APIs separately from the native source-tree CLI.
