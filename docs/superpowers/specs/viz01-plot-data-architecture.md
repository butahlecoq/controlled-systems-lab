# VIZ-01 plot-data architecture

## Problem

VIZ-01 needs to turn saved strategy-run artifacts and independently checked witnesses into backend-neutral state and control series. The output must keep stage indexing, coordinate meaning, evidence, and fuel metadata attached to each plotted path. The existing run record stores selected witnesses and claims, while the trajectory verifier returns typed reports in the live comparison flow. Decoding a saved family claim does not restore runtime verifier authority. The adapter must preserve that distinction and must not invoke a solver, selector, geometry operation, or renderer.

## Usage

The caller decodes each saved strategy run against the resolved problem, keeps the matching trajectory reports from its run, and asks the artifact module to prepare plot data.

```cpp
auto run = artifacts::decode_run(saved_run, problem);
if (const auto* error = std::get_if<artifacts::ArtifactError>(&run)) {
    report(error->path, error->message);
} else {
    auto plot = artifacts::prepare_plot_data(
        problem, std::get<artifacts::RunStatistics>(run), reports, metadata);
    if (const auto* plot_error = std::get_if<artifacts::ArtifactError>(&plot)) {
        report(plot_error->path, plot_error->message);
    } else {
        consume_plot_data(std::get<artifacts::PlotData>(plot));
    }
}
```

Call once for each strategy run. A renderer can overlay the returned data because each result binds to the same problem identity and derives axes from the same resolved model.

When no physical stage times or time unit are present, the result exposes stage indices. It never substitutes execution timings for physical time.

## Shape

`PlotData` is a value projection of one `RunStatistics` record. It contains the source run and strategy identities, state-point and control-interval axes, ordered coordinate metadata, selected witness paths, selection counts, and typed evidence statuses.

The public builder accepts the resolved problem, a decoded run, the verifier reports associated with that run, and optional source annotations:

```cpp
ArtifactResult<PlotData> prepare_plot_data(
    const problem::ResolvedProblem&,
    const RunStatistics&,
    std::span<const verification::TrajectoryReport>,
    const PlotMetadata& = {});
```

Each path identifies a witness by `(RunId, source ordinal)`. That identity remains stable within the immutable run record. The path also carries the strategy ID and version from the resolved configuration. It preserves the witness's original objective and the matching verifier residuals. It does not invent a persistent witness ID that the source record lacks.

The state axis has `T+1` points. The control axis has `T` intervals. If the resolved model supplies `T+1` times and the metadata supplies a time unit, the builder emits physical state times and left-held control intervals `[t_i, t_{i+1})`. Otherwise it emits stage indices. It does not discretize dynamics or infer timestamps.

`PlotMetadata` carries optional labels, units, source targets, and coordinate bounds in the original state and control order. Every supplied target or bound includes a source reference. Missing metadata remains absent. This preserves fuel coordinates such as oxidizer flow, oxidizer stock balance, fuel flow, and fuel stock balance without assuming names, units, targets, or nonnegative stock. The output copies signed witness values unchanged.

For each witness, the builder checks the problem ID, run selection order, history lengths, coordinate dimensions, report bindings, and finite values. It rejects a mismatched problem or malformed shape with `ArtifactError`. A report with failed or unsupported checks remains visible as an unverified or invalid path; it cannot become an optimality claim. The data keeps trajectory feasibility, objective, family completeness, and validated status separate. In particular, a selected sample never represents the full optimal family.

Requested count, returned count, distinct count, distinctness tolerance, and selector diagnostics come from `WitnessBatch`. The adapter reports the existing ordered-greedy distinctness result and the number of duplicate observations. It does not deduplicate plotted paths.

The artifact module owns run decoding and the new adapter. The adapter reads `RunStatistics` and `TrajectoryReport` domain types. It does not parse JSON itself. Mathematical set projection remains an explicit geometry request in #91. SVG, HTML, and raster rendering remain downstream work in #96.

## Synthesis decision

Candidate A is the base because it keeps state points and control intervals distinct, allows separate physical coordinates, and preserves optional metadata and evidence references. The cross-judge scored both candidates poorly on fit with existing interfaces. The synthesized shape removes their invented import types and uses `ResolvedProblem`, `RunStatistics`, `TrajectoryReport`, and `WitnessBatch` already present in the code. It adopts candidate B's typed `ArtifactError` path for malformed input. Neither candidate's universal status field is retained. The output preserves individual evidence statuses rather than merging them into one `verified` flag.

## Tradeoffs accepted

- The caller passes the resolved problem and typed verifier reports alongside the decoded run because the archive decoder does not create verification authority.
- The witness identity uses the run and source ordinal because the persisted witness schema has no dedicated witness ID.
- The builder handles one strategy run at a time so it can reuse the existing immutable run and selection types. Common axes follow from the shared resolved problem.
- Source targets and bounds remain optional because current scenario metadata does not contain those values for every problem.
- Physical control times are intervals with a left-hold convention. The builder does not guess interval midpoints.

## Alternatives considered

- **A renderer-facing visitor over opaque comparison artifacts:** rejected because each renderer would repeat artifact traversal and evidence-label rules. It also mixes rendering with storage schemas.
- **A universal imported `VerifiedFamilyWitnesses` type:** rejected because no such import or verifier record exists. Defining it here would claim a trust boundary the repository has not implemented.
- **A comparison-wide scene graph with projected sets:** rejected because it mixes trajectory data, mathematical set projection, and image layout. #91 and #96 own those operations.

## Open questions and risks

- The saved trajectory-report attachment currently has no typed decoder. The builder accepts reports from the live run or another caller that has independently produced typed reports. A future saved-report consumer needs a versioned decoder owned by the artifact boundary.
- Current problem and scenario records do not provide fuel targets and bounds for every historical source. The builder preserves supplied annotations and reports absent values as unavailable.
- `TrajectoryReport` records numerical witness checks. Its current contract does not verify complete-family coverage or validated arithmetic. Plot labels must state these limits.

## Verification record

The public API and builder are implemented in `include/csl/artifacts/plot_data.hpp` and `src/artifacts/final_plot_data.cpp`. The two-step analytic contract fixture lives in `tests/artifacts/final_plot_data.cpp`; installed header and link use is covered by `tests/installed/plot_data_client.cpp`.
