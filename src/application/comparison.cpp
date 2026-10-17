#include <csl/application/comparison.hpp>
#include <csl/artifacts/h_relation_attachment.hpp>

#include <algorithm>
#include <string_view>
#include <type_traits>
#include <utility>

namespace csl::application {
namespace {
constexpr std::array<std::string_view, 2> profiles{
    "ts01_exact_integrator", "ts02_constant_integrator"};
constexpr std::array<std::string_view, 2> strategies{
    "csl.synthesis.reach-back", "csl.synthesis.strategy-b"};

bool admitted_representation(const RepresentationId& representation) {
    return representation.value == "csl.polyhedron.h";
}

UnsupportedComparison unsupported(std::string field, std::string explanation) {
    return {{{DiagnosticCode::unsupported, std::move(field), std::move(explanation)}}};
}

artifacts::FinalOutcome project(const SynthesisOutcome& outcome) {
    return std::visit([](const auto& value) -> artifacts::FinalOutcome {
        using T = std::decay_t<decltype(value)>;
        if constexpr (std::is_same_v<T, SynthesisResult>) return artifacts::project_final(value);
        else return artifacts::UnsupportedFinal{value.diagnostics};
    }, outcome);
}
}

Preparation prepare_comparison(const ComparisonRequest& request,
    const registry::StrategyRegistry& registry) {
    if (std::find(profiles.begin(), profiles.end(), request.family.profile) == profiles.end())
        return unsupported("comparison.family.profile",
            "Only the guarded T-S01 and T-S02 complete-family profiles are admitted.");
    if (request.family.objective != request.problem.identity())
        return unsupported("comparison.family.objective",
            "The common family request must name the supplied resolved problem.");
    if (request.family.target != FamilyTarget::exact_optimal_relation ||
        request.family.assurance != Assurance::numerical ||
        !admitted_representation(request.family.representation))
        return unsupported("comparison.family",
            "The initial paired workflow requires a numerical exact relation in csl.polyhedron.h.");

    for (std::size_t index = 0; index < strategies.size(); ++index) {
        if (request.strategies[index].strategy.value != strategies[index])
            return unsupported("comparison.strategies[" + std::to_string(index) + "]",
                "The first paired workflow requires reach-back followed by direct joint synthesis.");
        if (request.strategies[index].representation != request.family.representation)
            return unsupported("comparison.strategies[" + std::to_string(index) + "].representation",
                "Both strategies must use the common family representation.");
    }

    std::array<std::optional<registry::PreparedStrategy>, 2> prepared;
    std::vector<registry::Rejection> rejections;
    for (std::size_t index = 0; index < request.strategies.size(); ++index) {
        const registry::StrategyRequest strategy_request{
            request.problem, request.strategies[index], request.family, {}, {}};
        registry::Requirements requirements;
        requirements.output.representation = request.family.representation;
        requirements.output.family = request.family.target;
        requirements.output.completeness = registry::Completeness::established;
        auto result = registry.prepare(strategy_request, requirements);
        if (auto* rejection = std::get_if<registry::Rejection>(&result))
            rejections.push_back(std::move(*rejection));
        else
            prepared[index].emplace(std::get<registry::PreparedStrategy>(std::move(result)));
    }
    if (!rejections.empty()) return RejectedComparison{std::move(rejections)};

    return PreparedComparison{request.problem, request.family, request.strategies,
        {std::move(*prepared[0]), std::move(*prepared[1])}};
}

std::array<std::unique_ptr<registry::BoundWorkspace<registry::StrategyPort>>, 2>
PreparedComparison::create() const {
    return {prepared_[0].create(), prepared_[1].create()};
}

ComparisonExecution run_comparison(const PreparedComparison& prepared,
    const registry::Registry<registry::SelectorPort>& selectors, registry::Method selector,
    const WitnessRequest& witness_request, const registry::Requirements& selector_requirements,
    const ExecutionContext& context,
    std::optional<registry::PreparedProvider<registry::LPPort>> membership_provider) {
    auto workspaces = prepared.create();
    auto effective_context = context;
    effective_context.numerical = prepared.family().numerical;
    ComparisonExecution execution{};
    for (std::size_t index = 0; index < workspaces.size(); ++index) {
        auto outcome = workspaces[index]->run(effective_context);
        auto projection = project(outcome);
        SelectionOutcome selection;
        std::vector<verification::TrajectoryReport> reports;

        const auto* result = std::get_if<SynthesisResult>(&outcome);
        if (result && result->family &&
            std::holds_alternative<CompleteOptimalFamily>(result->family->outcome())) {
            const registry::SelectorRequest query{*result->family, witness_request};
            auto prepared_selector = registry::prepare_pipeline(registry::select(
                selectors, selector, query, selector_requirements));
            if (auto* rejection = std::get_if<registry::Rejection>(&prepared_selector)) {
                selection = std::move(*rejection);
            } else {
                auto selector_workspaces = std::get<registry::PreparedPipeline<registry::SelectorPort>>(
                    std::move(prepared_selector)).create();
                auto selected = std::get<0>(selector_workspaces)->run(effective_context);
                if (auto* unsupported_selection = std::get_if<Unsupported>(&selected)) {
                    selection = std::move(*unsupported_selection);
                } else {
                    auto selected_result = std::get<WitnessSelection>(std::move(selected));
                    const auto expected = prepared.expected_synthesis_identity(index);
                    if (!expected.lineage) {
                        selection = Unsupported{{Diagnostic{DiagnosticCode::unsupported,
                            "comparison.verification.lineage",
                            "The prepared strategy did not provide an expected transformation lineage; "
                            "the selected witnesses were not independently verified."}}};
                    } else {
                        for (const auto& witness : selected_result.batch.witnesses) {
                            verification::TrajectoryRequest request;
                            request.witness = witness;
                            request.assurance = expected.request.assurance;
                            request.outcome = result->outcome;
                            request.family = result->family;
                            request.bounds = result->objective;
                            request.expected_synthesis = verification::ExpectedSynthesisBinding{
                                expected.request, expected.strategy, expected.strategy_version,
                                *expected.lineage};
                            reports.push_back(verification::verify_trajectory(prepared.problem(), request,
                                effective_context, membership_provider));
                        }
                        selection = std::move(selected_result);
                    }
                }
            }
        }
        execution.strategies[index] = {std::move(outcome), std::move(projection),
            std::move(selection), std::move(reports)};
    }
    return execution;
}

artifacts::ArtifactResult<std::string> encode_strategy_run(
    const problem::ResolvedProblem& problem, const StrategyExecution& execution,
    artifacts::ResolvedConfiguration configuration, artifacts::RunId run,
    artifacts::CollectedStatistics statistics, artifacts::ResourceObservation resources) {
    const auto description = problem.description();
    std::optional<WitnessSelection> selection;
    if (const auto* selected = std::get_if<WitnessSelection>(&execution.selection))
        selection = *selected;
    auto final=execution.final_projection;
    std::vector<artifacts::Attachment> attachments;
    if(auto* synthesis=std::get_if<artifacts::SynthesisFinal>(&final);synthesis&&synthesis->family) {
        auto& family=*synthesis->family;
        const auto* complete=std::get_if<CompleteOptimalFamily>(&family.family.outcome());
        if(complete&&std::holds_alternative<RegisteredCompletenessEvidence>(complete->completeness.support)) {
            if(!family.family.registry_verified())
                return artifacts::ArtifactError{artifacts::ArtifactErrorCode::unsupported,"run.final.family",
                    "Only a current-process registry-verified family can be exported"};
            const auto* relation=std::visit([](const auto& value)->const JointRelation*{return &value.relation;},family.family.outcome());
            const auto* data=relation->payload?relation->payload->h_relation_for_recording():nullptr;
            if(!data)
                return artifacts::ArtifactError{artifacts::ArtifactErrorCode::unsupported,"run.final.family.attachment",
                    "The concrete family relation has no H-relation recording exporter"};
            auto encoded=artifacts::encode_h_relation_attachment(*data,{16*1024*1024,100000,1000000,1024*1024});
            if(const auto* error=std::get_if<artifacts::ArtifactError>(&encoded))return *error;
            const auto content=std::get<problem::ResolvedContent>(std::move(encoded));
            const artifacts::AttachmentId attachment_id{"family-relation"};
            attachments.push_back({attachment_id,artifacts::AttachmentRole::family,content.digest(),
                static_cast<std::uint64_t>(content.bytes().size()),"application/vnd.csl.h-relation+json",
                "csl.h-relation-attachment/1",{},content});
            family.payload=artifacts::ExternalFamilyPayload{attachment_id};
        }
    }
    artifacts::RunRecord record{problem.identity(), description->model->dynamics.dimensions,
        static_cast<std::uint64_t>(description->times.size() - 1), std::move(configuration),
        std::move(run), std::move(final), std::move(statistics), std::move(resources),
        {}, std::move(attachments), artifacts::ProblemProvenance::problem_revalidated, std::move(selection)};
    auto published = artifacts::publish_run({problem, std::move(record)});
    if (auto* error = std::get_if<artifacts::ArtifactError>(&published)) return *error;
    auto encoded=artifacts::encode_recorded_run(std::get<artifacts::RunStatistics>(published));
    if(const auto* error=std::get_if<artifacts::ArtifactError>(&encoded))return *error;
    const auto& bytes=std::get<artifacts::RecordedRunArtifact>(encoded).content().bytes();
    std::string text;text.reserve(bytes.size());
    for(const auto byte:bytes)text.push_back(static_cast<char>(std::to_integer<unsigned char>(byte)));
    return text;
}
} // namespace csl::application
