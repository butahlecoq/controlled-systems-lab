#include <csl/artifacts/stage_projection_request.hpp>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <set>

namespace csl::artifacts {
namespace {

ArtifactError invalid(std::string path, std::string message) {
    return {ArtifactErrorCode::invalid_input, std::move(path), std::move(message)};
}

Unsupported unsupported(std::string field, std::string explanation) {
    return {{{DiagnosticCode::unsupported, std::move(field), std::move(explanation)}}};
}

std::optional<ArtifactError> resolve_coordinate(const StateCoordinate& coordinate,
    const std::vector<CoordinateAnnotation>& metadata, std::size_t& resolved,
    const std::string& path) {
    if (const auto* ordinal = std::get_if<CoordinateOrdinal>(&coordinate)) {
        if (ordinal->value >= metadata.size())
            return invalid(path, "coordinate ordinal is outside the stage state dimension");
        resolved = ordinal->value;
        return {};
    }
    const auto& name = std::get<CoordinateName>(coordinate).value;
    if (name.empty()) return invalid(path, "coordinate name must not be empty");
    std::optional<std::size_t> match;
    for (std::size_t i = 0; i < metadata.size(); ++i) {
        if (!metadata[i].label || *metadata[i].label != name) continue;
        if (match) return invalid(path, "coordinate name is ambiguous in the stage metadata");
        match = i;
    }
    if (!match) return invalid(path, "coordinate name is not present in the stage metadata");
    resolved = *match;
    return {};
}

std::string identity_suffix(std::size_t pair, StageIndex stage) {
    return "/pair/" + std::to_string(pair) + "/stage/" + std::to_string(stage.value);
}

StageProjectionFailure failed(const GeometryRequestIdentity& identity,
    std::optional<registry::Provenance> selected_provider,
    std::variant<registry::Rejection, Unsupported, OperationStopped, ArtifactError> cause,
    std::optional<PlotQueryCost> cost = {}) {
    return {identity, std::move(selected_provider), std::move(cost), std::move(cause)};
}

} // namespace

StageProjectionCaptureOutcome capture_stage_projections(
    const StageProjectionCaptureRequest& request,
    const registry::PreparedProvider<registry::GeometryPort>& provider,
    const ExecutionContext& context) {
    if (request.problem.value.empty() || request.request.value.empty())
        return invalid("request.identity", "problem and request identities must not be empty");
    if (request.coordinate_pairs.empty())
        return invalid("request.coordinate_pairs", "at least one coordinate pair is required");
    if (request.stages.empty())
        return invalid("request.stages", "at least one expected stage is required");
    if (!provider.provenance().actual)
        return unsupported("request.provider", "selected geometry provider has no resolved implementation identity");
    if (request.coordinate_pairs.size() > std::vector<StageProjectionRecord>{}.max_size() /
            request.stages.size())
        return invalid("request", "pair-by-stage result grid exceeds the supported container size");

    std::vector<std::vector<ResolvedStageProjectionPair>> resolved(request.stages.size());
    for (std::size_t s = 0; s < request.stages.size(); ++s) {
        const auto& stage = request.stages[s];
        if (stage.stage.value != s)
            return invalid("request.stages", "expected stages must be contiguous and start at R0");
        if (stage.physical_time && !std::isfinite(*stage.physical_time))
            return invalid("request.stages[" + std::to_string(s) + "].physical_time",
                "physical time must be finite");
        if (const auto* gap = std::get_if<StageProjectionGap>(&stage.source)) {
            if (gap->explanation.empty())
                return invalid("request.stages[" + std::to_string(s) + "].source.explanation",
                    "a stage gap requires an explanation");
            if ((gap->kind == StageProjectionGap::Kind::stopped) != gap->stop.has_value())
                return invalid("request.stages[" + std::to_string(s) + "].source.stop",
                    "only stopped stage gaps must carry a stop reason");
        }
        if (const auto* source = std::get_if<StageProjectionSet>(&stage.source)) {
            if (source->owner.problem.value.empty() || source->relation.id.value.empty())
                return invalid("request.stages[" + std::to_string(s) + "].source.identity",
                    "stage source problem and relation identities must not be empty");
            if (source->relation.metadata.dimension == 0)
                return invalid("request.stages[" + std::to_string(s) + "].source.relation",
                    "stage source relation must have a positive dimension");
            if (const auto* set_id = std::get_if<SetId>(&source->owner.identity);
                set_id && *set_id != source->relation.id)
                return ArtifactError{ArtifactErrorCode::identity,
                    "request.stages[" + std::to_string(s) + "].source.owner",
                    "stage source owner does not identify its relation set"};
        }
        resolved[s].reserve(request.coordinate_pairs.size());
        for (std::size_t p = 0; p < request.coordinate_pairs.size(); ++p) {
            if (const auto* source = std::get_if<StageProjectionSet>(&stage.source)) {
                const auto dimension = source->state_coordinates.size();
                if (source->relation_coordinates.size() != dimension)
                    return invalid("request.stages[" + std::to_string(s) + "].relation_coordinates",
                        "coordinate map must contain one relation coordinate per state coordinate");
                for (const auto index : source->relation_coordinates)
                    if (index >= source->relation.metadata.dimension)
                        return invalid("request.stages[" + std::to_string(s) + "].relation_coordinates",
                            "coordinate map index is outside the source relation");
                std::size_t first{}, second{};
                const auto& pair = request.coordinate_pairs[p];
                if (const auto error = resolve_coordinate(pair.first, source->state_coordinates,
                        first, "request.coordinate_pairs[" + std::to_string(p) + "].first")) return *error;
                if (const auto error = resolve_coordinate(pair.second, source->state_coordinates,
                        second, "request.coordinate_pairs[" + std::to_string(p) + "].second")) return *error;
                if (first == second)
                    return invalid("request.coordinate_pairs[" + std::to_string(p) + "]",
                        "a projection pair must contain two distinct state coordinates");
                resolved[s].push_back({first, second,
                    {source->state_coordinates[first], source->state_coordinates[second]}});
            } else {
                // A missing stage has no local labels; ordinals still resolve against
                // the first available stage below, while names need route metadata.
                resolved[s].push_back({});
            }
        }
    }

    for (std::size_t s = 0; s < request.stages.size(); ++s) {
        if (!std::holds_alternative<StageProjectionSet>(request.stages[s].source)) continue;
        std::set<std::pair<std::size_t, std::size_t>> unique;
        for (std::size_t p = 0; p < resolved[s].size(); ++p)
            if (!unique.insert({resolved[s][p].first, resolved[s][p].second}).second)
                return invalid("request.coordinate_pairs[" + std::to_string(p) + "]",
                    "duplicate ordered coordinate pairs are not allowed");
    }

    // Resolve missing-stage requests from a declared stage so every expected
    // pair/stage can be represented without inventing coordinates.
    const auto metadata_stage = std::find_if(request.stages.begin(), request.stages.end(),
        [](const auto& stage) { return std::holds_alternative<StageProjectionSet>(stage.source); });
    for (std::size_t s = 0; s < request.stages.size(); ++s) {
        const auto* source = std::get_if<StageProjectionSet>(&request.stages[s].source);
        if (source) continue;
        if (metadata_stage == request.stages.end())
            return invalid("request.stages", "at least one available stage is required to resolve coordinate references");
        const auto& metadata = std::get<StageProjectionSet>(metadata_stage->source).state_coordinates;
        for (std::size_t p = 0; p < request.coordinate_pairs.size(); ++p) {
            std::size_t first{}, second{};
            const auto& pair = request.coordinate_pairs[p];
            if (const auto error = resolve_coordinate(pair.first, metadata, first,
                    "request.coordinate_pairs[" + std::to_string(p) + "].first")) return *error;
            if (const auto error = resolve_coordinate(pair.second, metadata, second,
                    "request.coordinate_pairs[" + std::to_string(p) + "].second")) return *error;
            if (first == second)
                return invalid("request.coordinate_pairs[" + std::to_string(p) + "]",
                    "a projection pair must contain two distinct state coordinates");
            resolved[s][p] = {first, second, {metadata[first], metadata[second]}};
        }
    }

    StageProjectionBatchCapture batch{request.problem, request.request,
        request.required_relation, request.assurance, {}};
    batch.records.reserve(request.stages.size() * request.coordinate_pairs.size());
    for (std::size_t s = 0; s < request.stages.size(); ++s) {
        const auto& input = request.stages[s];
        const auto* source = std::get_if<StageProjectionSet>(&input.source);
        for (std::size_t p = 0; p < request.coordinate_pairs.size(); ++p) {
            const auto pair = resolved[s][p];
            if (!source) {
                const auto& gap = std::get<StageProjectionGap>(input.source);
                batch.records.push_back({input.stage, input.physical_time, pair, {},
                    StageProjectionUnavailable{gap.kind, gap.explanation, gap.stop}});
                continue;
            }
            const auto suffix = identity_suffix(p, input.stage);
            GeometryRequestIdentity identity{request.problem,
                {request.request.value + suffix}, {"stage-projection" + suffix}};
            if (source->owner.problem != request.problem) {
                batch.records.push_back({input.stage, input.physical_time, pair, source->assurance,
                    failed(identity, provider.provenance(),
                        ArtifactError{ArtifactErrorCode::identity, "request.stages.source.owner",
                            "stage source belongs to a different problem"})});
                continue;
            }
            std::vector<std::size_t> selected{
                source->relation_coordinates[pair.first], source->relation_coordinates[pair.second]};
            OperationRequest operation{identity, provider.provenance().actual->id,
                Projection{source->relation, std::move(selected)}, request.required_relation,
                request.assurance};
            if (source->relation_claim != request.required_relation) {
                batch.records.push_back({input.stage, input.physical_time, pair, source->assurance,
                    failed(identity, provider.provenance(), unsupported("request.required_relation",
                        "source stage does not satisfy the requested relation claim"))});
                continue;
            }
            if (const auto errors = check_operation_shape(operation); !errors.empty()) {
                batch.records.push_back({input.stage, input.physical_time, pair, source->assurance,
                    failed(identity, provider.provenance(), Unsupported{errors})});
                continue;
            }
            auto admission = provider.prepare(operation);
            if (const auto* rejected = std::get_if<registry::Rejection>(&admission)) {
                batch.records.push_back({input.stage, input.physical_time, pair, source->assurance,
                    failed(identity, rejected->provenance, *rejected)});
                continue;
            }
            auto prepared = std::get<registry::PreparedPipeline<registry::GeometryPort>>(std::move(admission));
            auto [workspace] = prepared.create();
            const auto started = std::chrono::steady_clock::now();
            auto outcome = workspace->run(context);
            const PlotQueryCost cost{std::chrono::duration_cast<std::chrono::nanoseconds>(
                std::chrono::steady_clock::now() - started)};
            if (const auto* stopped = std::get_if<OperationStopped>(&outcome)) {
                batch.records.push_back({input.stage, input.physical_time, pair, source->assurance,
                    failed(identity, prepared.provenance().front(), *stopped, cost)});
                continue;
            }
            if (const auto* rejected = std::get_if<Unsupported>(&outcome)) {
                batch.records.push_back({input.stage, input.physical_time, pair, source->assurance,
                    failed(identity, prepared.provenance().front(), *rejected, cost)});
                continue;
            }
            const auto* projection = std::get_if<OperationResult>(&outcome);
            if (!projection) {
                batch.records.push_back({input.stage, input.physical_time, pair, source->assurance,
                    failed(identity, prepared.provenance().front(), unsupported("projection.outcome",
                        "geometry provider returned a non-projection result"), cost)});
                continue;
            }
            if (projection->relation != request.required_relation) {
                batch.records.push_back({input.stage, input.physical_time, pair, source->assurance,
                    failed(identity, prepared.provenance().front(), unsupported("projection.relation",
                        "geometry provider returned a different relation guarantee"), cost)});
                continue;
            }
            if (const auto errors = check_geometry_evidence(projection->evidence, operation); !errors.empty()) {
                batch.records.push_back({input.stage, input.physical_time, pair, source->assurance,
                    failed(identity, prepared.provenance().front(), Unsupported{errors}, cost)});
                continue;
            }
            if (projection->output.metadata.dimension != 2) {
                batch.records.push_back({input.stage, input.physical_time, pair, source->assurance,
                    failed(identity, prepared.provenance().front(), unsupported("projection.dimension",
                        "geometry provider did not return two coordinates"), cost)});
                continue;
            }
            batch.records.push_back({input.stage, input.physical_time, pair, source->assurance,
                PlotSetProjection{request.problem, source->owner, input.stage,
                    projection->evidence.reference, projection->output,
                    {source->state_coordinates[pair.first], source->state_coordinates[pair.second]},
                    projection->relation, projection->evidence.support, projection->evidence.assumptions,
                    prepared.provenance().front(), {}, cost}});
        }
    }
    return batch;
}

} // namespace csl::artifacts
