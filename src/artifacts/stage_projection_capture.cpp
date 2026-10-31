#include <csl/artifacts/stage_projection_capture.hpp>

#include <chrono>

namespace csl::artifacts {
namespace {

Unsupported unsupported(std::string field, std::string explanation) {
    return {{{DiagnosticCode::unsupported, std::move(field), std::move(explanation)}}};
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

void append_failure(StageProjectionBatchCapture& batch, const StageProjectionInput& input,
    const ResolvedStageProjectionPair& pair, Assurance source_assurance,
    const std::vector<StageProjectionSourceEvidence>& source_evidence,
    const GeometryRequestIdentity& identity,
    std::optional<registry::Provenance> selected_provider,
    std::variant<registry::Rejection, Unsupported, OperationStopped, ArtifactError> cause,
    std::optional<PlotQueryCost> cost = {}) {
    batch.records.push_back({input.stage, input.physical_time, pair, source_assurance, source_evidence,
        failed(identity, std::move(selected_provider), std::move(cause), std::move(cost))});
}

} // namespace

StageProjectionCaptureOutcome capture_stage_projections(
    const StageProjectionCaptureRequest& request,
    const registry::PreparedProvider<registry::GeometryPort>& provider,
    const ExecutionContext& context) {
    auto validation = validate_stage_projection_request(request);
    if (const auto* error = std::get_if<ArtifactError>(&validation)) return *error;
    if (!provider.provenance().actual)
        return unsupported("request.provider", "selected geometry provider has no resolved implementation identity");

    const auto& pairs = std::get<ValidatedStageProjectionRequest>(validation).coordinate_pairs;
    if (pairs.size() > std::vector<StageProjectionRecord>{}.max_size() / request.stages.size())
        return ArtifactError{ArtifactErrorCode::invalid_input, "request",
            "pair-by-stage result grid exceeds the supported container size"};

    StageProjectionBatchCapture batch{request.problem, request.request,
        request.required_relation, request.assurance, {}};
    batch.records.reserve(request.stages.size() * pairs.size());
    for (std::size_t s = 0; s < request.stages.size(); ++s) {
        const auto& input = request.stages[s];
        const auto* source = std::get_if<StageProjectionSet>(&input.source);
        for (std::size_t p = 0; p < pairs.size(); ++p) {
            const auto& pair = pairs[p];
            if (!source) {
                const auto& gap = std::get<StageProjectionGap>(input.source);
                batch.records.push_back({input.stage, input.physical_time, pair, {}, {},
                    StageProjectionUnavailable{gap.kind, gap.explanation, gap.stop}});
                continue;
            }

            const auto suffix = identity_suffix(p, input.stage);
            const GeometryRequestIdentity identity{request.problem,
                {request.request.value + suffix}, {"stage-projection" + suffix}};
            const auto selected_provider = provider.provenance();
            if (source->owner.problem != request.problem) {
                append_failure(batch, input, pair, source->assurance, source->evidence,
                    identity, selected_provider,
                    ArtifactError{ArtifactErrorCode::identity, "request.stages.source.owner",
                        "stage source belongs to a different problem"});
                continue;
            }
            if (source->relation_claim != request.required_relation) {
                append_failure(batch, input, pair, source->assurance, source->evidence,
                    identity, selected_provider,
                    unsupported("request.required_relation",
                        "source stage does not satisfy the requested relation claim"));
                continue;
            }

            std::vector<std::size_t> selected{
                source->relation_coordinates[pair.first], source->relation_coordinates[pair.second]};
            OperationRequest operation{identity, provider.provenance().actual->id,
                Projection{source->relation, std::move(selected)}, request.required_relation,
                request.assurance};
            if (const auto errors = check_operation_shape(operation); !errors.empty()) {
                append_failure(batch, input, pair, source->assurance, source->evidence,
                    identity, selected_provider,
                    Unsupported{errors});
                continue;
            }

            auto admission = provider.prepare(operation);
            if (const auto* rejected = std::get_if<registry::Rejection>(&admission)) {
                append_failure(batch, input, pair, source->assurance, source->evidence, identity,
                    rejected->provenance, *rejected);
                continue;
            }
            auto prepared = std::get<registry::PreparedPipeline<registry::GeometryPort>>(std::move(admission));
            auto [workspace] = prepared.create();
            const auto started = std::chrono::steady_clock::now();
            auto outcome = workspace->run(context);
            const PlotQueryCost cost{std::chrono::duration_cast<std::chrono::nanoseconds>(
                std::chrono::steady_clock::now() - started)};
            const auto operation_provider = prepared.provenance().front();
            if (const auto* stopped = std::get_if<OperationStopped>(&outcome)) {
                append_failure(batch, input, pair, source->assurance, source->evidence, identity,
                    operation_provider, *stopped, cost);
                continue;
            }
            if (const auto* rejected = std::get_if<Unsupported>(&outcome)) {
                append_failure(batch, input, pair, source->assurance, source->evidence, identity,
                    operation_provider, *rejected, cost);
                continue;
            }
            const auto* projection = std::get_if<OperationResult>(&outcome);
            if (!projection) {
                append_failure(batch, input, pair, source->assurance, source->evidence, identity,
                    operation_provider, unsupported("projection.outcome",
                        "geometry provider returned a non-projection result"), cost);
                continue;
            }
            if (projection->relation != request.required_relation) {
                append_failure(batch, input, pair, source->assurance, source->evidence, identity,
                    operation_provider, unsupported("projection.relation",
                        "geometry provider returned a different relation guarantee"), cost);
                continue;
            }
            if (const auto errors = check_geometry_evidence(projection->evidence, operation); !errors.empty()) {
                append_failure(batch, input, pair, source->assurance, source->evidence, identity,
                    operation_provider, Unsupported{errors}, cost);
                continue;
            }
            if (projection->output.metadata.dimension != 2) {
                append_failure(batch, input, pair, source->assurance, source->evidence, identity,
                    operation_provider, unsupported("projection.dimension",
                        "geometry provider did not return two coordinates"), cost);
                continue;
            }
            batch.records.push_back({input.stage, input.physical_time, pair, source->assurance,
                source->evidence, StageProjectionSuccess{PlotSetProjection{request.problem,
                    source->owner, input.stage,
                    projection->evidence.reference, projection->output, pair.coordinates,
                    projection->relation, projection->evidence.support,
                    projection->evidence.assumptions, operation_provider, {}, cost},
                    projection->evidence.error_bound, {}, {}, {}}});
        }
    }
    return batch;
}

} // namespace csl::artifacts
