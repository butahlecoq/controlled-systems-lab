#include <csl/artifacts/stage_projection_request.hpp>

#include <cmath>
#include <set>

namespace csl::artifacts {
namespace {

ArtifactError invalid(std::string path, std::string message) {
    return {ArtifactErrorCode::invalid_input, std::move(path), std::move(message)};
}

std::optional<ArtifactError> resolve_coordinate(const StateCoordinate& coordinate,
    const std::vector<CoordinateAnnotation>& metadata, std::size_t& resolved,
    const std::string& path) {
    if (const auto* ordinal = std::get_if<CoordinateOrdinal>(&coordinate)) {
        if (ordinal->value >= metadata.size())
            return invalid(path, "coordinate ordinal is outside the route state dimension");
        resolved = ordinal->value;
        return {};
    }
    const auto& name = std::get<CoordinateName>(coordinate).value;
    if (name.empty()) return invalid(path, "coordinate name must not be empty");
    std::optional<std::size_t> match;
    for (std::size_t i = 0; i < metadata.size(); ++i) {
        if (!metadata[i].label || *metadata[i].label != name) continue;
        if (match) return invalid(path, "coordinate name is ambiguous in the route metadata");
        match = i;
    }
    if (!match) return invalid(path, "coordinate name is not present in the route metadata");
    resolved = *match;
    return {};
}

} // namespace

StageProjectionRequestValidation validate_stage_projection_request(
    const StageProjectionCaptureRequest& request) {
    if (request.problem.value.empty() || request.request.value.empty())
        return invalid("request.identity", "problem and request identities must not be empty");
    if (request.state_coordinates.size() < 2)
        return invalid("request.state_coordinates", "route metadata must declare at least two state coordinates");
    if (request.coordinate_pairs.empty())
        return invalid("request.coordinate_pairs", "at least one coordinate pair is required");
    if (request.stages.empty())
        return invalid("request.stages", "at least one expected stage is required");
    if (request.coordinate_pairs.size() > std::vector<ResolvedStageProjectionPair>{}.max_size())
        return invalid("request.coordinate_pairs", "coordinate-pair list exceeds the supported container size");

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
            if (const auto* set_id = std::get_if<SetId>(&source->owner.identity);
                set_id && *set_id != source->relation.id)
                return ArtifactError{ArtifactErrorCode::identity,
                    "request.stages[" + std::to_string(s) + "].source.owner",
                    "stage source owner does not identify its relation set"};
            if (source->relation.metadata.dimension == 0)
                return invalid("request.stages[" + std::to_string(s) + "].source.relation",
                    "stage source relation must have a positive dimension");
            for (const auto& item : source->evidence) {
                if (item.stage.value != stage.stage.value || item.source_set != source->relation.id ||
                    item.evidence.reference.identity.problem != source->owner.problem ||
                    item.evidence.reference.identity.ideal_output.value != source->relation.id.value ||
                    item.evidence.scope != GeometryClaimScope::set_relation)
                    return ArtifactError{ArtifactErrorCode::identity,
                        "request.stages[" + std::to_string(s) + "].source.evidence",
                        "source evidence must identify this stage, relation set, problem, and set-relation claim"};
            }
            if (source->relation_coordinates.size() != request.state_coordinates.size())
                return invalid("request.stages[" + std::to_string(s) + "].source.relation_coordinates",
                    "coordinate map must contain one relation coordinate per route state coordinate");
            for (const auto index : source->relation_coordinates)
                if (index >= source->relation.metadata.dimension)
                    return invalid("request.stages[" + std::to_string(s) + "].source.relation_coordinates",
                        "coordinate map index is outside the source relation");
        }
    }

    ValidatedStageProjectionRequest result;
    result.coordinate_pairs.reserve(request.coordinate_pairs.size());
    std::set<std::pair<std::size_t, std::size_t>> unique;
    for (std::size_t p = 0; p < request.coordinate_pairs.size(); ++p) {
        std::size_t first{}, second{};
        const auto& pair = request.coordinate_pairs[p];
        if (const auto error = resolve_coordinate(pair.first, request.state_coordinates, first,
                "request.coordinate_pairs[" + std::to_string(p) + "].first")) return *error;
        if (const auto error = resolve_coordinate(pair.second, request.state_coordinates, second,
                "request.coordinate_pairs[" + std::to_string(p) + "].second")) return *error;
        if (first == second)
            return invalid("request.coordinate_pairs[" + std::to_string(p) + "]",
                "a projection pair must contain two distinct state coordinates");
        if (!unique.insert({first, second}).second)
            return invalid("request.coordinate_pairs[" + std::to_string(p) + "]",
                "duplicate ordered coordinate pairs are not allowed");
        result.coordinate_pairs.push_back({first, second,
            {request.state_coordinates[first], request.state_coordinates[second]}});
    }
    return result;
}

} // namespace csl::artifacts
