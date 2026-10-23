# Preliminary approximation pilot record mapping

This page is a migration plan for the unregistered pilot, not an instance of
`csl.comparison-record/1`. The raw capture remains immutable in
`raw-rows.jsonl`; `request-identities.json` adds the exact request identity,
source representation, requested relation and output budget for each method.
The shared input descriptor is `input.txt` with SHA-256
`bf23229be76bfeaa7bb6a9965c90a53a32580eeba6a7cdb07be905152dac3d9c`.

| Pilot data | Future comparison record field | Migration rule and limit |
|---|---|---|
| Bundle fixture `diamond`, input descriptor hash | `ComparisonSpecId` and `shared_input_manifest_hash` | Freeze the exact V or equivalent generator input and output request in a reviewed spec; the present text descriptor hash is not itself a canonical binary input manifest. |
| Row `method`, source commit, `request-identities.json` entry | Side `AlgorithmIdentity`, resolved backend/configuration and effective request | Preserve the exact method name and map every request identity, source representation, `outer`/`exact` relation, output budget and assurance. Do not collapse V and generator representations even though they encode the same diamond. |
| `round`, `warmup`, `elapsed_ns` | `ComparisonRunId`, repetition index, attempt status and named timing span | The current elapsed value covers each existing call path; it is not an equivalent cross-method latency metric. No attempt timestamp or independent run-record reference exists in this pilot. |
| `area`, `area_ratio`, `evidence`, `passed` | Mathematical outcome and claim-scoped checker evidence | Preserve these as fixture-specific diagnostics. `passed=true` does not become globally `verified`; each method needs an independent relation-direction proof under the future checker contract. |
| `summary.csv`, `comparison.svg`, `index.html` | Derived report assets | Regenerate from saved rows only. They are not authoritative records and cannot replace raw attempts. |

Before importing this run, #83/#84 must approve the record shape and migration,
and #99/#100 must determine whether this fixture/request meets their comparison
scope. The missing canonical input manifest, attempt timestamps and immutable
run-record references must be supplied or explicitly represented as
unavailable. Do not manufacture a complete comparison record from this pilot.
