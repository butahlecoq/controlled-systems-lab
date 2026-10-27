# REVIEW-06 scenario workflow audit

**Issue:** [#90](https://github.com/butahlecoq/controlled-systems-lab/issues/90)
**Reviewed snapshot:** `8ce236169df44a0dad062c5daea553c4f4581d5b` (`origin/main`, 2026-10-27)
**Scope:** scenario input and templates, CLI execution, mathematical identity, plot boundary, run artifacts, and historical B04 handling.

## Acceptance audit

| Criterion | Result | Evidence |
|---|---|---|
| Edit and run a nonfuel scenario without C++ changes; diagnose dimensions, stages, units, defaults | **Pass, scoped** | The editable JSON catalogue includes a minimal LTI template and a nonfuel double-integrator case. `scenario_cli` validates and runs the latter under `nominal_open_loop`; `examples/scenarios/README.md` documents state/control stage counts, times, units, defaults and result limits. The loader checks exact T versus T+1 stage counts and dimensions. |
| Settings preserve identity; problem data changes identity; external hashes and resolved settings persist | **Partial / fail** | `tests/unit/input/scenario_loader_tests.cpp:168-191,235-264` checks identity changes for mathematical data and stability under run/display settings. However `scenario_cli.cpp:500-504` rejects every explicit `run.methods` request. The loader rejects external descriptors without reading or binding their bytes (`src/input/scenario_loader.cpp:83-91`). CLI run JSON does not retain source provenance (`examples/scenario_cli.cpp:450-453`; see finding #2). |
| CLI, plots and adapters remain plant-independent | **Pass** | The generic loader resolves canonical `ResolvedProblem`; CLI submits it to registered strategies. The offline plotting route consumes saved records and does not implement fuel dynamics. Fuel-specific content is confined to fuel examples/reports and the historical B04 intake branch. |
| Keep historical, reproduced, and corrected B04 records distinct; unresolved B04 stays non-executable | **Pass** | `benchmarks/scenarios/b04-historical.json` states `executable: false` and unresolved restoration status. The loader returns `HistoricalScenario`, and the CLI reports its execution gate. `docs/artifacts/historical-versus-reproduced.md` separates reported values from sourced/reproduced/corrected records. |
| Schema compatibility, unsupported fields, and diagnostics | **Partial** | Strict unknown-key, schema, reserved-field and dimensional validation are documented and covered by input tests. External references intentionally fail closed under the current contract, but that conflicts with #90’s explicit persistence criterion; scope needs reconciliation. |
| Fixed-commit execution and independent review | **Evidence recorded; fixes pending** | Linux GCC Release CI for this exact snapshot (`40434206613`) passed all 144 CTests, including `scenario_file_tests` and `scenario_template_catalogue_tests`. Independent standards and specification audits are recorded below. #90 must remain open until its blocking findings are fixed and rechecked. |

## Findings

### P1 — Explicit scenario methods are accepted by input but rejected by the runner

`src/input/scenario_loader.cpp:305-310` retains `run.methods`, and `tests/unit/input/scenario_loader_tests.cpp:235-244` checks its parsed values. But `examples/scenario_cli.cpp:500-504` returns unsupported for every non-comparison request before method preparation; the later run path hard-codes the two default strategies. Thus the promised end-to-end strategy switch is not available through the authored scenario workflow, even though parsing and identity tests pass.

**Reproduction from this snapshot:** add a valid nonempty `run.methods` array to an otherwise valid executable scenario and invoke `scenario_cli --run <file>`. Loading succeeds; `run()` returns status 2 at the explicit-method guard before execution or export.

**Follow-up:** [#727](https://github.com/butahlecoq/controlled-systems-lab/issues/727).

### P2 — Exported CLI records omit source-file provenance

`examples/scenario_cli.cpp:585-589` prints the scenario source SHA-256, but the export call at `:450-453` passes no `SourceProvenance` or resolved input defaults to `application::encode_strategy_run`. The encoder (`src/application/comparison.cpp:502-505,588-595`) builds records from the resolved problem and execution/configuration data. A saved JSON record therefore cannot bind itself to the authored scenario bytes/schema without separately retaining stdout and the input file.

**Reproduction from this snapshot:** run a valid scenario with `--output-dir`; inspect the emitted strategy-run JSON. Its builder receives no source digest/schema/default record, although stdout contains `source_sha256`.

**Follow-up:** [#728](https://github.com/butahlecoq/controlled-systems-lab/issues/728).

### P1 — External-data hash requirement conflicts with the implemented input contract

Issue #90 asks for external referenced data hashes to persist. The current loader validates an external descriptor and then returns `UnsupportedInput` without opening it (`src/input/scenario_loader.cpp:83-91`); its test expects rejection (`tests/unit/input/scenario_loader_tests.cpp:312-316`). The contract explicitly says no external matrix I/O occurs (`docs/contracts/scenario-input.md:98-100,167-169`), and the design calls external references a later capability. This is fail-closed behavior, but it does not satisfy #90 as written. Implementing I/O now would need bounded path resolution, digest verification, cancellation, and canonical content bindings.

**Follow-up:** [#729](https://github.com/butahlecoq/controlled-systems-lab/issues/729) records the scope conflict and recommended decision. Keep #90 open until the criterion is met or the owner resolves the documented scope conflict.

## Independent reviews

- **Standards:** Pass at `8ce236169df44a0dad062c5daea553c4f4581d5b`. No reproducible documented-standard violations found. The reviewer checked the loader, CLI, plot adapter and offline plot path against `AGENTS.md`, `CONTRIBUTING.md` and `docs/agents/issue-tracker.md`.
- **Specification:** Three findings at the same fixed snapshot: P1 explicit method selection is rejected; P1 external content hashes cannot be persisted under the intentionally unsupported contract; P2 source digest is printed but omitted from saved records. Other reviewed criteria appear covered by the cited code/tests/docs.

Neither reviewer modified files or ran tests. The CI evidence above is the exact-snapshot run evidence. This audit does not approve closure of #90: follow-ups #727-#729 remain unresolved and no fix has been rechecked.
