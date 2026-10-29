# TEST-22 replay residual contract

## Problem

Replay currently executes a declared exact discrete transition map, so it has no integration residual to compute. Numerical tolerances are declaration metadata: they do not change the callback output or certify its accuracy. VIZ-04 keeps linear residual evidence separate but drops replay numerical metadata and has no field stating whether an integration residual applies. The contract must preserve that distinction, save the existing plant/version/units and tolerance metadata, and migrate old artifacts without inferring evidence that their records do not establish.

## Usage (caller's view)

```cpp
const auto replay = simulation::replay(plant, controls, context);
if (std::holds_alternative<IntegrationResidualNotApplicable>(replay.integration_residual)) {
    show_label("Integration residual not applicable");
} else if (const auto* missing = std::get_if<IntegrationResidualUnavailable>(
               &replay.integration_residual)) {
    show_label("Integration residual unavailable");
    log(missing->reason);
} else {
    const auto& available = std::get<AvailableIntegrationResidual>(replay.integration_residual);
    show_residual(available.measurements);
}
```

A VIZ-04 reader continues to use the existing codec. It accepts v1 and v2, while new output is v2:

```cpp
auto saved = experiments::encode_replay_comparison(comparison); // emits v2
// decode_replay_comparison accepts either supported version
```

Linear verification residuals remain read from their existing linear evidence field. The replay's declared numerical policy, plant identity/version, state/control units, and integration residual evidence are read from their separate replay fields.

## Shape

The replay domain owns a closed sum type for integration-residual evidence. It makes the three states distinct and keeps unavailable reasons separate from numeric values:

```cpp
enum class IntegrationResidualUnavailableReason { legacy_artifact, not_recorded };
struct IntegrationResidualNotApplicable {};
struct IntegrationResidualUnavailable {
    IntegrationResidualUnavailableReason reason{IntegrationResidualUnavailableReason::not_recorded};
};
struct IntegrationResidualMeasurement {
    std::string name;
    double value;
    std::string unit;
};
struct AvailableIntegrationResidual {
    std::string definition;
    std::vector<IntegrationResidualMeasurement> measurements;
};
using IntegrationResidualEvidence = std::variant<IntegrationResidualNotApplicable,
    IntegrationResidualUnavailable, AvailableIntegrationResidual>;
```

`ReplayRecord` receives one `integration_residual` value. Replay explicitly assigns `not_applicable` for `exact_discrete_map`; no residual number is inferred. `available` carries named values and their units so a future supported method can persist the residual it actually computes without conflating it with policy tolerances. `unavailable` is used only when a residual could apply but was not recorded. If a method has no mathematical residual notion, it is `not_applicable`.

The VIZ-04 encoder writes `csl.viz04-replay-comparison/2`. Each replay gets a required `integration_residual` discriminated object and a separate `numerical_policy` object (absolute and relative tolerance) or `null`. Existing plant name/version/source and state/control/time/objective units remain in their existing declaration fields; they are not duplicated into the residual. Available residual measurements each carry their own unit and a definition. The linear evidence format is unchanged.

The decoder accepts v1 and v2 but returns the original validated content bytes; it does not construct a `ReplayRecord`. A v1 consumer can interpret an explicitly saved `integration: "exact_discrete_map"` as not applicable. If the method is absent/null, the missing evidence is legacy-unavailable. No other historical status is inferred. V2 requires and validates the discriminant, state-specific keys, finite measurement values, unique names, nonempty units/definition, and the separate optional numerical-policy tolerances. Unknown statuses and malformed records fail closed. V2 is the only emitted format. The encoder also rejects an available residual attached to an exact-discrete-map replay. JSON version checks remain inside the existing VIZ-04 codec; evidence ownership stays on the replay domain record.

The numerical policy is explicitly named as a policy, not an applied integration limit. On the current exact-map path it does not alter or bound the transition callback. This preserves the metadata while respecting `docs/contracts/nonlinear-replay.md`.

## Synthesis decision

Candidate 1 is the base for its conservative legacy semantics and state-specific validation. Candidate 2's explicit producer assignment is retained: replay chooses not-applicable for its exact map; future methods must choose deliberately. The cross-judge identified that both candidates omitted units and tolerance metadata. Accordingly, there is no `no_independent_reference` unavailable reason: no residual notion means `not_applicable`; unavailable means an applicable quantity was not recorded. Available measurements carry named values, units, and a definition; the artifact separately preserves the replay's existing plant/version/units and adds the declared numerical policy. The VIZ-04 decoder accepts v1 as unchanged legacy content; a consumer can interpret its recorded method when it materializes evidence, but this codec does not create a `ReplayRecord`. V2 output requires an explicit residual state. No additional candidate graft was needed beyond Candidate 2's explicit producer assignment.

Rubric scores (cross-judge; 1–5):

| Criterion | Candidate 1 | Candidate 2 |
|---|---:|---:|
| Truthful applicability states | 3 | 4 |
| Units, plant/version, policy metadata | 1 | 1 |
| V1 migration and v2 validation | 4 | 2 |
| API depth and evidence ownership | 4 | 4 |
| Implementability and caller burden | 3 | 3 |

Both candidates omitted the metadata requirement; the selected shape adds it explicitly. Neither score is treated as evidence that integration residuals are currently computed.

## Tradeoffs accepted

- We accept a public replay-record field and a schema v2 migration to make applicability explicit at the source and in saved evidence.
- We accept decode-only compatibility for v1 in favor of a single canonical v2 output.
- We accept named measurement definitions instead of prescribing a scientific residual formula that the exact-map replay cannot compute.
- We retain declared tolerances as policy metadata but do not call them integration limits or error bounds.

## Alternatives considered

- `optional<double>` was rejected because it makes not-applicable indistinguishable from missing evidence and provides no unit or measurement definition.
- Putting nonlinear residuals beside linear residuals in VIZ-04 was rejected because replay determines applicability; visualization only associates and persists the evidence.
- Rewriting v1 bytes during decode was rejected because `decode_replay_comparison` returns an immutable content snapshot, not a domain object. V1 remains readable without rewriting; new encoding uses v2.

## Open questions and risks

- TEST-22 remains open for computed nonlinear residual values: the current exact-map method has no integration residual to calculate, and the current tests only exercise the v2 `available` decoder shape.
- The `available` measurements intentionally preserve producer-defined named quantities. A future numerical method must specify the residual formula and provenance in its `definition`; this contract does not certify the scientific validity of that calculation.
- Public API and raw-JSON consumers require compatibility review before delivery.

## Next implementation step

Specify and implement an independent residual-producing integration method, then add an encoder round-trip test for measurements computed by that method before closing TEST-22.
