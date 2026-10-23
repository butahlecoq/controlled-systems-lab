# Scenario JSON v1 and v2

`v1.schema.json` and `v2.schema.json` are JSON Schema 2020-12 authoring aids for
executable `csl.scenario/1` and `csl.scenario/2` documents. Their `$id` values
name the schemas; loading a scenario does not fetch those URLs. The native
boundary is `CSL::input` and its contract is
[scenario-input.md](../../docs/contracts/scenario-input.md). The independent
examples are [minimal integrator](../../tests/fixtures/input/minimal-integrator.json)
and [affine LTV](../../tests/fixtures/input/affine-ltv.json); the v2
[slew-limited integrator](../../examples/scenarios/temporal-slew-integrator.json)
demonstrates full-history rows.

Required root fields are schema, horizon, model, initial_state, controls and
objective. Other documented fields are optional. Unknown executable keys reject,
including nested keys. The only profile string is `nominal_discrete_v1`; omitted
profile means that same profile. Explicit null never means omission.

The schema does not replace native validation. In particular JSON Schema treats
`2.0` as an integer, whereas counts require unsigned integer JSON tokens. Native
validation also enforces UTF-8 without BOM, duplicate decoded-key rejection,
byte and allocation limits, exact matrix sizes, finite binary64 conversion,
integer coefficient magnitude at most 2^53, and nonzero-decimal underflow
rejection. Schema string lengths count characters; native quotas count decoded
UTF-8 bytes. The native boundary decides whether input is admitted.

Cross-field rules include square A, compatible B/offset, consistent dimensions,
T dynamics/control stages, T+1 times/state sets, strictly increasing times,
matching objective/set dimensions, empty indexed T=0 providers requiring explicit
dimensions, PSD/symmetry policy, and a resource policy that fits its total thread
budget. A row-array `[]` is exactly 0x0; use rows/cols/values to retain 0xn.

Defaults revision `csl.scenario-defaults/1` supplies index times 0..T, universal
states, absent external/temporal structures, no observations, zero offsets for
linear kinds or omitted objective offsets, empty display metadata, and a
comparison *request*. Initial values, control bounds and objective targets are
never guessed. Scenario v2 retains those defaults under
`csl.scenario-defaults/2` and adds optional canonical full-history temporal rows.
V1 continues to reject a present temporal field. The loader does not
reinterpret unknown schema/profile versions.

The reserved continuous model kinds, finite/mixed controls, sum/mixed objectives,
future root structures and well-formed external matrix descriptors return
UnsupportedInput as documented. They are deliberately not executable schema
instances. The separate B04 historical intake preserves non-executable archival
data and cannot publish a ResolvedProblem.
