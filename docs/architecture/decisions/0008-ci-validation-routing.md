# ADR 0008: Route saved-report and presentation changes by ownership

Date: 2026-11-21
Status: Accepted

## Context

Native validation checks executable models, algorithms, and integration paths. The report pipeline validates immutable evidence, renders it, and publishes it. Treating every saved result as a native input adds unrelated builds, while broad path exemptions can bypass validation of a live producer.

## Decision

Route reviewed presentation files to report validation when they consume saved inputs and own no native build target. The exemption covers reviewed Pages shells and their tests, composition and navigation inventories, archive route preservation, and byte and hash audits. Maintain native validation for live numerical collectors, validators with native consumers, and native test drivers.

Saved-episode publication functions can read captures and contracts and check or render the records under report validation. Shared controller and record-protocol implementation used by native runs retains native validation. Enumerated saved-evidence directories may hold inert source and build snapshots. Limit the exemption to those owners because the broader reports directories can contain live drivers, build owners, and compatibility tooling. Unknown ownership requires both gates. Changes to the Python quality workflow and root TOML trigger the Python gate directly. Those files configure Ruff and ty and have no native build or test consumer.

## Verification

The ownership lists and fallback are implemented in `scripts/ci/route_changes.py`. The tests exercise mixed changes, archive paths, and Git history. The original split is tracked in [PR #488](https://github.com/butahlecoq/controlled-systems-lab/pull/488).
