#include <csl/artifacts/plot_request.hpp>

#include <algorithm>
#include <chrono>
#include <set>

namespace csl::artifacts {
namespace {
ArtifactError artifact_error(ArtifactErrorCode code, std::string path, std::string message) {
    return {code, std::move(path), std::move(message)};
}

Diagnostics diagnostic(DiagnosticCode code, std::string field, std::string explanation) {
    return {{code, std::move(field), std::move(explanation)}};
}

Unsupported unsupported(std::string field, std::string explanation) {
    return {diagnostic(DiagnosticCode::unsupported, std::move(field), std::move(explanation))};
}

PlotRequestFailure failure(std::optional<GeometryRequestIdentity> identity,
    std::optional<registry::Provenance> provider,
    std::variant<registry::Rejection, Unsupported, OperationStopped, ArtifactError> cause,
    std::optional<PlotQueryCost> cost = {}) {
    return {std::move(identity), std::move(provider), std::move(cost), std::move(cause)};
}

std::optional<ArtifactError> validate_coordinate_map(const StateRelationCoordinates& map,
    std::size_t stages, std::size_t state_dimension, std::size_t relation_dimension,
    const std::string& path) {
    if (map.by_stage.size() != stages)
        return artifact_error(ArtifactErrorCode::invalid_input, path, "coordinate map must contain one row for each state stage");
    for (std::size_t stage = 0; stage < map.by_stage.size(); ++stage) {
        const auto& row = map.by_stage[stage];
        if (row.size() != state_dimension)
            return artifact_error(ArtifactErrorCode::invalid_input,
                path + "[" + std::to_string(stage) + "]", "coordinate map row does not match the state dimension");
        std::set<std::size_t> unique;
        for (const auto index : row) {
            if (index >= relation_dimension)
                return artifact_error(ArtifactErrorCode::invalid_input,
                    path + "[" + std::to_string(stage) + "]", "coordinate map index is outside the source relation");
            if (!unique.insert(index).second)
                return artifact_error(ArtifactErrorCode::invalid_input,
                    path + "[" + std::to_string(stage) + "]", "state coordinates must map to distinct relation coordinates");
        }
    }
    return {};
}

std::optional<ArtifactError> validate_pair(CoordinatePair pair, std::size_t dimension,
    const std::string& path) {
    if (pair.first >= dimension || pair.second >= dimension)
        return artifact_error(ArtifactErrorCode::invalid_input, path, "coordinate index is outside the state dimension");
    if (pair.first == pair.second)
        return artifact_error(ArtifactErrorCode::invalid_input, path, "coordinate pair must contain two distinct state coordinates");
    return {};
}

PlotOutcome trajectory_plot(const PlotData& data, CoordinatePair pair) {
    const auto dimension = data.states.coordinates.size();
    if (const auto problem = validate_pair(pair, dimension, "request.coordinates"))
        return failure({}, {}, *problem);
    const auto stages = data.state_axis.points.size();
    PlotTrajectoryPair result{data.problem, data.state_axis,
        {data.states.coordinates[pair.first], data.states.coordinates[pair.second]}, {}, {},
        PlotSampleKind::selected_witnesses};
    result.paths.reserve(data.paths.size());
    result.terminal_samples.reserve(data.paths.size());
    for (const auto& path : data.paths) {
        if (path.states.size() != stages)
            return failure({}, {}, artifact_error(ArtifactErrorCode::invalid_input,
                "paths[" + std::to_string(path.source_ordinal) + "].states", "state history does not match the plot state axis"));
        PlotTrajectoryPath plotted{path.run, path.source_ordinal, path.strategy,
            path.strategy_version, path.objective, path.evidence, {}};
        plotted.points.reserve(path.states.size());
        for (std::size_t stage = 0; stage < path.states.size(); ++stage) {
            const auto& state = path.states[stage];
            if (pair.first >= state.size() || pair.second >= state.size())
                return failure({}, {}, artifact_error(ArtifactErrorCode::invalid_input,
                    "paths[" + std::to_string(path.source_ordinal) + "].states[" + std::to_string(stage) + "]",
                    "state coordinates do not contain the requested pair"));
            plotted.points.push_back({state[pair.first], state[pair.second]});
        }
        if (!plotted.points.empty())
            result.terminal_samples.push_back({path.run, path.source_ordinal, plotted.points.back()});
        result.paths.push_back(std::move(plotted));
    }
    return result;
}

PlotOutcome project_plot(const PlotData& data, const SetProjectionRequest& request,
    const registry::PreparedProvider<registry::GeometryPort>& provider,
    const ExecutionContext& context) {
    if (!request.source)
        return failure({}, provider.provenance(), artifact_error(ArtifactErrorCode::invalid_input,
            "request.source", "set projection requires a live projection source"));
    const auto& source = *request.source;
    const std::optional<GeometryRequestIdentity> identity = GeometryRequestIdentity{
        data.problem, request.request, request.ideal_output};
    if (source.owner().problem != data.problem)
        return failure(identity, provider.provenance(), artifact_error(ArtifactErrorCode::identity,
            "request.source.problem", "projection source belongs to a different problem"));
    if (const auto problem = validate_pair(request.coordinates, data.states.coordinates.size(), "request.coordinates"))
        return failure(identity, provider.provenance(), *problem);
    if (request.stage.value >= data.state_axis.points.size())
        return failure(identity, provider.provenance(), artifact_error(ArtifactErrorCode::invalid_input,
            "request.stage", "state stage is outside the plot horizon"));

    const auto relation_dimension = source.relation().metadata.dimension;
    if (const auto problem = validate_coordinate_map(source.coordinates(), data.state_axis.points.size(),
            data.states.coordinates.size(), relation_dimension, "request.source.coordinates"))
        return failure(identity, provider.provenance(), *problem);

    const auto& mapped = source.coordinates().by_stage[request.stage.value];
    const std::vector<std::size_t> selected{mapped[request.coordinates.first], mapped[request.coordinates.second]};
    const auto actual = provider.provenance().actual;
    if (!actual)
        return failure(identity, provider.provenance(), unsupported("request.provider", "selected geometry provider has no resolved implementation identity"));
    OperationRequest operation{*identity, actual->id,
        Projection{source.relation(), selected}, request.required_relation, request.assurance};

    auto admission = provider.prepare(operation);
    if (const auto* rejected = std::get_if<registry::Rejection>(&admission))
        return failure(identity, rejected->provenance, *rejected);
    auto prepared = std::get<registry::PreparedPipeline<registry::GeometryPort>>(std::move(admission));
    const auto operation_provider = prepared.provenance().front();
    auto [workspace] = prepared.create();
    const auto started = std::chrono::steady_clock::now();
    auto outcome = workspace->run(context);
    const PlotQueryCost cost{std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now() - started)};
    if (const auto* stopped = std::get_if<OperationStopped>(&outcome))
        return failure(identity, operation_provider, *stopped, cost);
    if (const auto* rejected = std::get_if<Unsupported>(&outcome))
        return failure(identity, operation_provider, *rejected, cost);
    if (!std::holds_alternative<OperationResult>(outcome))
        return failure(identity, operation_provider, unsupported("projection.outcome", "geometry provider returned a non-projection result"), cost);

    auto result = std::get<OperationResult>(std::move(outcome));
    if (result.relation != request.required_relation)
        return failure(identity, operation_provider, unsupported("projection.relation", "geometry provider returned a different relation guarantee"), cost);
    if (const auto errors = check_geometry_evidence(result.evidence, operation); !errors.empty())
        return failure(identity, operation_provider, Unsupported{errors}, cost);
    if (result.output.metadata.dimension != 2)
        return failure(identity, operation_provider, unsupported("projection.dimension", "geometry provider did not return the requested two-dimensional projection"), cost);
    const auto set_data = sets::from_handle(result.output);
    if (const auto* error = std::get_if<Diagnostic>(&set_data))
        return failure(identity, operation_provider, Unsupported{{*error}}, cost);

    return PlotSetProjection{data.problem, source.owner(), request.stage, result.evidence.reference,
        result.output,
        {data.states.coordinates[request.coordinates.first], data.states.coordinates[request.coordinates.second]},
        result.relation, result.evidence.support, result.evidence.assumptions, operation_provider,
        source.family_evidence(), cost};
}
}

PlotProjectionSource::PlotProjectionSource(SetHandle relation, PlotSourceOwner owner,
    StateRelationCoordinates coordinates, std::optional<FamilySourceEvidence> family_evidence)
    : relation_(std::move(relation)), owner_(std::move(owner)), coordinates_(std::move(coordinates)),
      family_evidence_(std::move(family_evidence)) {}

PlotSourceResult make_reachable_set_source(SetHandle relation, ProblemId problem,
    StateRelationCoordinates coordinates) {
    if (problem.value.empty() || relation.id.value.empty())
        return diagnostic(DiagnosticCode::invalid_input, "plot.source.identity", "problem and set identities are required");
    if (coordinates.by_stage.empty())
        return diagnostic(DiagnosticCode::invalid_input, "plot.source.coordinates", "state-to-relation coordinate map cannot be empty");
    if (coordinates.by_stage.front().empty())
        return diagnostic(DiagnosticCode::invalid_input, "plot.source.coordinates", "state-to-relation coordinate map must include state coordinates");
    if (const auto error = validate_coordinate_map(coordinates, coordinates.by_stage.size(),
            coordinates.by_stage.front().size(), relation.metadata.dimension, "plot.source.coordinates"))
        return diagnostic(DiagnosticCode::invalid_input, error->path, error->message);
    PlotSourceOwner owner{std::move(problem), relation.id};
    return std::shared_ptr<const PlotProjectionSource>{new PlotProjectionSource(
        std::move(relation), std::move(owner), std::move(coordinates), {})};
}

PlotSourceResult make_optimal_family_source(const OptimalFamily& family,
    StateRelationCoordinates coordinates) {
    if (!family.registry_verified() || family.target() != FamilyTarget::exact_optimal_relation)
        return diagnostic(DiagnosticCode::unsupported, "plot.source.family", "only a live registry-verified complete optimal family can be projected as an optimal family");
    const auto* complete = std::get_if<CompleteOptimalFamily>(&family.outcome());
    if (!complete || !complete->relation.payload)
        return diagnostic(DiagnosticCode::unsupported, "plot.source.family", "family has no live relation payload");
    const auto* relation = complete->relation.payload->h_relation_for_recording();
    if (!relation)
        return diagnostic(DiagnosticCode::unsupported, "plot.source.family.relation", "family payload does not expose a projectable native set relation");
    const auto handle = relation->as_handle();
    const auto& identity = family.identity();
    if (coordinates.by_stage.size() != identity.coordinates.horizon + 1)
        return diagnostic(DiagnosticCode::invalid_input, "plot.source.coordinates", "coordinate map must contain one row for every family state stage");
    if (const auto error = validate_coordinate_map(coordinates, identity.coordinates.horizon + 1,
            identity.coordinates.dimensions.state, handle.metadata.dimension, "plot.source.coordinates"))
        return diagnostic(DiagnosticCode::invalid_input, error->path, error->message);
    PlotSourceOwner owner{identity.problem, identity};
    FamilySourceEvidence evidence{identity, complete->completeness.support, family.registry_verified()};
    return std::shared_ptr<const PlotProjectionSource>{new PlotProjectionSource(
        handle, std::move(owner), std::move(coordinates), std::move(evidence))};
}

PlotRequest PlotRequest::trajectory_pair(CoordinatePair coordinates) {
    return {TrajectoryPairRequest{coordinates}};
}

PlotRequest PlotRequest::set_projection(std::shared_ptr<const PlotProjectionSource> source,
    StageIndex stage, CoordinatePair coordinates, SetRelation relation, Assurance assurance,
    RequestId request, ReferenceId ideal_output) {
    return {SetProjectionRequest{std::move(source), stage, coordinates, relation, assurance,
        std::move(request), std::move(ideal_output)}};
}

PlotOutcome make_plot(const PlotData& data, const PlotRequest& request) {
    if (const auto* trajectory = std::get_if<TrajectoryPairRequest>(&request.source))
        return trajectory_plot(data, trajectory->coordinates);
    const auto& projection = std::get<SetProjectionRequest>(request.source);
    const std::optional<GeometryRequestIdentity> identity =
        GeometryRequestIdentity{data.problem, projection.request, projection.ideal_output};
    return failure(identity, {}, unsupported("plot.provider",
        "explicit set projection requires a prepared GeometryPort provider"));
}

PlotOutcome make_plot(const PlotData& data, const PlotRequest& request,
    const registry::PreparedProvider<registry::GeometryPort>& provider,
    const ExecutionContext& context) {
    if (const auto* trajectory = std::get_if<TrajectoryPairRequest>(&request.source))
        return trajectory_plot(data, trajectory->coordinates);
    return project_plot(data, std::get<SetProjectionRequest>(request.source), provider, context);
}

}
