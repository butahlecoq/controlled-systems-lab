#include <csl/application/comparison.hpp>
#include <csl/artifacts/h_relation_attachment.hpp>
#include <nlohmann/json.hpp>

#include <algorithm>
#include <bit>
#include <charconv>
#include <chrono>
#include <cstdint>
#include <string_view>
#include <type_traits>
#include <utility>

namespace csl::application {
namespace {
using Json = nlohmann::ordered_json;
constexpr std::array<std::string_view, 3> profiles{
    "ts01_exact_integrator", "ts02_constant_integrator", "ts03_singular_integrator"};
constexpr std::array<std::string_view, 2> strategy_order{
    "csl.synthesis.reach-back", "csl.synthesis.strategy-b"};

class CommonGuardTimer {
public:
    explicit CommonGuardTimer(ComparisonPreparationObservation* observation) noexcept
        : observation_(observation) {
        if (observation_) {
            start_ = std::chrono::steady_clock::now();
            active_ = true;
        }
    }

    void finish(PreparationObservationStatus status) noexcept {
        if (!observation_ || !active_) return;
        observation_->common_guards_ns = static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::nanoseconds>(
                std::chrono::steady_clock::now()-start_).count());
        observation_->common_guard_status = status;
        active_ = false;
    }

    ~CommonGuardTimer() {
        if (active_) finish(PreparationObservationStatus::threw);
    }

private:
    ComparisonPreparationObservation* observation_{};
    std::chrono::steady_clock::time_point start_{};
    bool active_{};
};

std::string bits(double value) {
    char buffer[16];
    const auto converted = std::to_chars(buffer, buffer + sizeof(buffer),
        std::bit_cast<std::uint64_t>(value), 16);
    std::string result(static_cast<std::size_t>(16 - (converted.ptr - buffer)), '0');
    result.append(buffer, converted.ptr);
    return result;
}

std::string_view assurance_name(Assurance value) {
    switch (value) {
    case Assurance::numerical: return "numerical";
    case Assurance::validated: return "validated";
    }
    return "unknown";
}

std::string_view termination_name(Termination value) {
    switch (value) {
    case Termination::completed: return "completed";
    case Termination::cancelled: return "cancelled";
    case Termination::deadline_expired: return "deadline_expired";
    case Termination::resource_limit: return "resource_limit";
    case Termination::numerical_failure: return "numerical_failure";
    case Termination::operation_rejected: return "operation_rejected";
    case Termination::contract_rejected: return "contract_rejected";
    }
    return "unknown";
}

std::string_view check_status_name(verification::CheckStatus value) {
    switch (value) {
    case verification::CheckStatus::not_checked: return "not_checked";
    case verification::CheckStatus::numerical_pass: return "numerical_pass";
    case verification::CheckStatus::violation: return "violation";
    case verification::CheckStatus::invalid_input: return "invalid_input";
    case verification::CheckStatus::unsupported: return "unsupported";
    }
    return "unknown";
}

std::string_view diagnostic_code_name(DiagnosticCode value) {
    switch (value) {
    case DiagnosticCode::invalid_input: return "invalid_input";
    case DiagnosticCode::unsupported: return "unsupported";
    case DiagnosticCode::evidence_mismatch: return "evidence_mismatch";
    case DiagnosticCode::invalid_claim: return "invalid_claim";
    }
    return "unknown";
}

std::string_view family_target_name(FamilyTarget value) {
    switch (value) {
    case FamilyTarget::exact_optimal_relation: return "exact_optimal_relation";
    case FamilyTarget::candidate_relaxation: return "candidate_relaxation";
    case FamilyTarget::partial_relation: return "partial_relation";
    }
    return "unknown";
}

std::string_view mathematical_outcome_name(MathematicalOutcome value) {
    switch (value) {
    case MathematicalOutcome::optimal: return "optimal";
    case MathematicalOutcome::infeasible: return "infeasible";
    case MathematicalOutcome::unbounded: return "unbounded";
    case MathematicalOutcome::infimum_not_attained: return "infimum_not_attained";
    case MathematicalOutcome::undetermined: return "undetermined";
    }
    return "unknown";
}

Json diagnostics_json(const Diagnostics& diagnostics) {
    auto result = Json::array();
    for (const auto& diagnostic : diagnostics)
        result.push_back({{"code", diagnostic_code_name(diagnostic.code)},
            {"field", diagnostic.field}, {"explanation", diagnostic.explanation}});
    return result;
}

Json provider_json(const registry::Provenance& provenance) {
    Json requested{{"id", provenance.requested.id.value},
        {"version", provenance.requested.version ? Json(*provenance.requested.version) : Json(nullptr)}};
    Json actual = nullptr;
    if (provenance.actual)
        actual = {{"id", provenance.actual->id.value}, {"version", provenance.actual->version}};
    return {{"port", provenance.port}, {"requested", std::move(requested)}, {"actual", std::move(actual)}};
}

Json vector_json(const Vector& vector) {
    auto result = Json::array();
    for (const double value : vector) result.push_back(bits(value));
    return result;
}

Json evidence_support_json(const EvidenceSupport& support) {
    return std::visit([](const auto& value) -> Json {
        using T = std::decay_t<decltype(value)>;
        if constexpr (std::is_same_v<T, Unestablished>) {
            return {{"kind", "unestablished"}};
        } else if constexpr (std::is_same_v<T, NumericalCheck>) {
            return {{"kind", "numerical_check"}, {"absolute_tolerance_bits", bits(value.absolute_tolerance)},
                {"relative_tolerance_bits", bits(value.relative_tolerance)},
                {"max_residual_bits", bits(value.max_residual)}, {"verifier", value.verifier.value}};
        } else if constexpr (std::is_same_v<T, SymbolicArgument>) {
            return {{"kind", "symbolic_argument"}, {"reference", value.reference}, {"assumptions", value.assumptions}};
        } else if constexpr (std::is_same_v<T, CertificateReference>) {
            return {{"kind", "certificate_reference"}, {"artifact", value.artifact}, {"verifier", value.verifier}};
        } else {
            const auto& certificate = value.certificate();
            return {{"kind", "exact_farkas"},
                {"subject", {{"problem_id", value.subject().problem.value},
                    {"program_id", value.subject().program.value}}},
                {"row_lower", vector_json(certificate.row_lower)}, {"row_upper", vector_json(certificate.row_upper)},
                {"variable_lower", vector_json(certificate.variable_lower)},
                {"variable_upper", vector_json(certificate.variable_upper)}};
        }
    }, support);
}

Json claim_evidence_json(const ClaimEvidence& evidence) {
    return {{"problem_id", evidence.problem.value}, {"support", evidence_support_json(evidence.support)}};
}

Json objective_evidence_json(const ObjectiveEvidence& evidence) {
    Json result{{"lower", nullptr}, {"upper", nullptr}};
    if (evidence.lower)
        result["lower"] = {{"value_bits", bits(evidence.lower->value)},
            {"evidence", claim_evidence_json(evidence.lower->evidence)}};
    if (evidence.upper)
        result["upper"] = {{"value_bits", bits(evidence.upper->value)},
            {"evidence", claim_evidence_json(evidence.upper->evidence)}};
    return result;
}

Json program_objective_evidence_json(const std::vector<ProgramObjectiveEvidence>& evidence) {
    auto result = Json::array();
    for (const auto& bounds : evidence) {
        Json item{{"lower", nullptr}, {"upper", nullptr}};
        const auto encode_bound = [](const ProgramObjectiveBound& bound) {
            auto assumptions = Json::array();
            for (const auto& assumption : bound.evidence.assumptions) assumptions.push_back(assumption);
            return Json{{"subject", {{"problem_id", bound.evidence.subject.problem.value},
                    {"program_id", bound.evidence.subject.program.value}}}, {"value_bits", bits(bound.value)},
                {"evidence", evidence_support_json(bound.evidence.support)}, {"assumptions", std::move(assumptions)}};
        };
        if (bounds.lower) item["lower"] = encode_bound(*bounds.lower);
        if (bounds.upper) item["upper"] = encode_bound(*bounds.upper);
        result.push_back(std::move(item));
    }
    return result;
}

Json synthesis_outcome_json(const SynthesisOutcomeClaim& outcome) {
    auto assumptions = Json::array();
    for (const auto& assumption : outcome.assumptions) assumptions.push_back(assumption);
    return {{"subject", outcome.subject.value}, {"value", mathematical_outcome_name(outcome.value)},
        {"support", evidence_support_json(outcome.support)}, {"assumptions", std::move(assumptions)}};
}

Json family_request_json(const FamilyRequest& request) {
    return {{"profile", request.profile}, {"objective", request.objective.value},
        {"target", family_target_name(request.target)}, {"assurance", assurance_name(request.assurance)},
        {"representation", request.representation.value},
        {"absolute_tolerance_bits", bits(request.numerical.absolute_tolerance)},
        {"relative_tolerance_bits", bits(request.numerical.relative_tolerance)},
        {"materialization_limit", request.materialization_limit
            ? Json(*request.materialization_limit) : Json(nullptr)}};
}

Json lineage_json(const std::vector<TransformStepIdentity>& lineage) {
    auto result = Json::array();
    for (const auto& step : lineage)
        result.push_back({{"request", step.request.value}, {"input", step.input.value},
            {"output", step.output.value}, {"module", step.module.value}, {"version", step.version}});
    return result;
}

Json witness_json(const Witness& witness) {
    auto states = Json::array();
    for (const auto& state : witness.states) states.push_back(vector_json(state));
    auto controls = Json::array();
    for (const auto& control : witness.controls) controls.push_back(vector_json(control));
    return {{"problem_id", witness.problem.value}, {"states", std::move(states)},
        {"controls", std::move(controls)}, {"original_objective_bits", bits(witness.original_objective)}};
}

Json report_json(const verification::TrajectoryReport& report, std::size_t witness_index) {
    Json request{{"assurance", assurance_name(report.input.assurance)},
        {"verification_assurance", assurance_name(report.verification.assurance)},
        {"absolute_tolerance_bits", bits(report.verification.numerical.absolute_tolerance)},
        {"relative_tolerance_bits", bits(report.verification.numerical.relative_tolerance)}};
    if (report.input.expected_synthesis) {
        const auto& binding = *report.input.expected_synthesis;
        request["expected_synthesis"] = {{"strategy", binding.strategy.value},
            {"strategy_version", binding.strategy_version},
            {"family_request", family_request_json(binding.request)}, {"lineage", lineage_json(binding.lineage)}};
    }
    request["limits"] = {{"residuals", report.input.limits.residuals},
        {"membership_queries", report.input.limits.membership_queries}};
    request["bounds"] = objective_evidence_json(report.input.bounds);
    request["backend_bounds"] = program_objective_evidence_json(report.input.backend_bounds);
    request["outcome"] = report.input.outcome
        ? synthesis_outcome_json(*report.input.outcome) : Json(nullptr);
    if (report.input.family) {
        const auto& identity = report.input.family->identity();
        request["family_identity"] = {{"problem_id", identity.problem.value},
            {"request", family_request_json(identity.request)},
            {"coordinates", {{"state_dimension", identity.coordinates.dimensions.state},
                {"control_dimension", identity.coordinates.dimensions.control},
                {"external_dimension", identity.coordinates.dimensions.external},
                {"horizon", identity.coordinates.horizon}}},
            {"strategy", identity.strategy.value}, {"strategy_version", identity.strategy_version},
            {"lineage", lineage_json(identity.lineage)}};
    } else {
        request["family_identity"] = nullptr;
    }
    auto residuals = Json::array();
    for (const auto& residual : report.residuals)
        residuals.push_back({{"field", residual.field}, {"violation_bits", bits(residual.measure.violation)},
            {"scale_bits", bits(residual.measure.scale)}, {"tolerance_bits", bits(residual.tolerance)},
            {"satisfied", residual.satisfied}});
    auto queries = Json::array();
    for (const auto& query : report.membership_queries) {
        queries.push_back(std::visit([](const auto& item) -> Json {
            using T = std::decay_t<decltype(item)>;
            Json encoded{{"request_problem_id", item.request.problem.value},
                {"request_program_id", item.request.program.value}};
            if constexpr (std::is_same_v<T, registry::LPQueryNotRun>) {
                encoded["kind"] = "not_run";
                encoded["reason"] = item.reason == registry::LPQueryNotRunReason::cancelled ? "cancelled" : "deadline";
                encoded["provider"] = provider_json(item.provider);
            } else if constexpr (std::is_same_v<T, registry::LPQueryRejected>) {
                encoded["kind"] = "rejected";
                encoded["diagnostics"] = diagnostics_json(item.rejection.diagnostics);
                encoded["provider"] = provider_json(item.rejection.provenance);
            } else if constexpr (std::is_same_v<T, registry::LPQuerySolverUnsupported>) {
                encoded["kind"] = "solver_unsupported";
                encoded["diagnostics"] = diagnostics_json(item.diagnostics);
                encoded["provider"] = provider_json(item.provider);
            } else if constexpr (std::is_same_v<T, registry::LPQueryCompleted>) {
                encoded["kind"] = "completed";
                encoded["returned_problem_id"] = item.returned_subject.problem.value;
                encoded["returned_program_id"] = item.returned_subject.program.value;
                encoded["outcome"] = mathematical_outcome_name(item.outcome);
                encoded["provider"] = provider_json(item.provider);
            } else {
                encoded["kind"] = "stopped";
                switch (item.reason) {
                case registry::LPQueryStopReason::cancelled: encoded["reason"] = "cancelled"; break;
                case registry::LPQueryStopReason::deadline_expired: encoded["reason"] = "deadline_expired"; break;
                case registry::LPQueryStopReason::resource_limit: encoded["reason"] = "resource_limit"; break;
                case registry::LPQueryStopReason::numerical_failure: encoded["reason"] = "numerical_failure"; break;
                }
                encoded["provider"] = provider_json(item.provider);
            }
            return encoded;
        }, query));
    }
    return {{"witness_index", witness_index}, {"problem_id", report.problem.value},
        {"witness", witness_json(report.input.witness)}, {"verifier", {{"id", report.verifier.id.value},
            {"version", report.verifier.version}}}, {"request", std::move(request)},
        {"termination", termination_name(report.termination)}, {"bindings", check_status_name(report.bindings)},
        {"feasibility", check_status_name(report.feasibility)}, {"objective", check_status_name(report.objective)},
        {"optimality", check_status_name(report.optimality)}, {"completeness", check_status_name(report.completeness)},
        {"validated", check_status_name(report.validated)},
        {"recomputed_objective_bits", report.recomputed_objective ? Json(bits(*report.recomputed_objective)) : Json(nullptr)},
        {"residuals", std::move(residuals)}, {"membership_queries", std::move(queries)},
        {"diagnostics", diagnostics_json(report.diagnostics)}};
}

artifacts::ArtifactResult<artifacts::Attachment> verification_attachment(
    const std::vector<verification::TrajectoryReport>& reports, const ProblemId& problem_id) {
    constexpr std::uint64_t max_bytes = 16 * 1024 * 1024;
    Json encoded{{"schema", "csl.trajectory-verification-reports/1"}, {"problem_id", problem_id.value}};
    auto values = Json::array();
    for (std::size_t i = 0; i < reports.size(); ++i) {
        if (reports[i].problem != problem_id || reports[i].input.witness.problem != problem_id)
            return artifacts::ArtifactError{artifacts::ArtifactErrorCode::identity,
                "run.verification[" + std::to_string(i) + "]", "Verifier report belongs to a different problem"};
        values.push_back(report_json(reports[i], i));
    }
    encoded["reports"] = std::move(values);
    const auto text = encoded.dump();
    if (text.size() > max_bytes)
        return artifacts::ArtifactError{artifacts::ArtifactErrorCode::limit, "run.verification", "Verifier report attachment exceeds 16 MiB"};
    const auto content_result = problem::snapshot_content(std::span<const std::byte>{
        reinterpret_cast<const std::byte*>(text.data()), text.size()});
    if (const auto* diagnostic = std::get_if<Diagnostic>(&content_result))
        return artifacts::ArtifactError{artifacts::ArtifactErrorCode::limit, diagnostic->field, diagnostic->explanation};
    auto content = std::get<problem::ResolvedContent>(content_result);
    return artifacts::Attachment{{"trajectory-verification-reports"}, artifacts::AttachmentRole::certificate,
        content.digest(), static_cast<std::uint64_t>(content.bytes().size()), "application/json",
        "csl.trajectory-verification-reports/1", {}, std::move(content)};
}

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
    return PreparedComparison::prepare_impl(request,registry,nullptr);
}

Preparation prepare_comparison_observed(const ComparisonRequest& request,
    const registry::StrategyRegistry& registry,ComparisonPreparationObservation& observation) {
    observation = {};
    return PreparedComparison::prepare_impl(request,registry,&observation);
}

Preparation PreparedComparison::prepare_impl(const ComparisonRequest& request,
    const registry::StrategyRegistry& registry,ComparisonPreparationObservation* observation) {
    CommonGuardTimer guard_timer{observation};
    auto reject = [&](std::string field,std::string explanation) {
        guard_timer.finish(PreparationObservationStatus::rejected);
        return unsupported(std::move(field),std::move(explanation));
    };
    const bool candidate_generality =
        request.family.profile == "nominal_open_loop" &&
        request.family.target == FamilyTarget::candidate_relaxation;
    if (!candidate_generality &&
        std::find(profiles.begin(), profiles.end(), request.family.profile) == profiles.end())
        return reject("comparison.family.profile",
            "Only guarded T-S01/T-S02/T-S03 complete-family profiles and nominal-open-loop candidate generality are admitted.");
    if (request.family.objective != request.problem.identity())
        return reject("comparison.family.objective",
            "The common family request must name the supplied resolved problem.");
    if ((!candidate_generality && request.family.target != FamilyTarget::exact_optimal_relation) ||
        (candidate_generality && request.family.target != FamilyTarget::candidate_relaxation) ||
        request.family.assurance != Assurance::numerical ||
        !admitted_representation(request.family.representation))
        return reject("comparison.family",
            "The initial paired workflow requires a numerical exact relation in csl.polyhedron.h.");

    for (std::size_t index = 0; index < request.strategies.size(); ++index) {
        if (request.strategies[index].strategy.value != strategy_order[index])
            return reject("comparison.strategies[" + std::to_string(index) + "]",
                "The first paired workflow requires reach-back followed by direct joint synthesis.");
        if (request.strategies[index].representation != request.family.representation)
            return reject("comparison.strategies[" + std::to_string(index) + "].representation",
                "Both strategies must use the common family representation.");
    }
    guard_timer.finish(PreparationObservationStatus::passed);

    std::array<std::optional<registry::PreparedStrategy>, 2> prepared;
    std::vector<registry::Rejection> rejections;
    std::vector<std::size_t> rejected_indices;
    for (std::size_t index = 0; index < request.strategies.size(); ++index) {
        const registry::StrategyRequest strategy_request{
            request.problem, request.strategies[index], request.family, {}, {}};
        registry::Requirements requirements;
        requirements.output.representation = request.family.representation;
        requirements.output.family = request.family.target;
        requirements.output.completeness = candidate_generality ?
            registry::Completeness::unestablished : registry::Completeness::established;
        auto result = observation ? registry.prepare_observed(strategy_request,requirements,{},
            observation->registry_attempts[index]) : registry.prepare(strategy_request, requirements);
        if (auto* rejection = std::get_if<registry::Rejection>(&result)) {
            rejections.push_back(std::move(*rejection));
            rejected_indices.push_back(index);
        }
        else
            prepared[index].emplace(std::get<registry::PreparedStrategy>(std::move(result)));
    }
    if (!rejections.empty())
        return RejectedComparison{std::move(rejections), std::move(rejected_indices)};

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
    const auto* selected = std::get_if<WitnessSelection>(&execution.selection);
    if ((selected && execution.verification.size() > selected->batch.witnesses.size()) ||
        (!selected && !execution.verification.empty()))
        return artifacts::ArtifactError{artifacts::ArtifactErrorCode::identity, "run.verification",
            "Verifier reports must bind an ordered prefix of the selected witness batch"};
    for (std::size_t i = 0; selected && i < execution.verification.size(); ++i) {
        const auto& witness = selected->batch.witnesses[i];
        const auto& report = execution.verification[i];
        const auto& report_witness = report.input.witness;
        if (report_witness.problem != witness.problem || report_witness.states != witness.states ||
            report_witness.controls != witness.controls ||
            std::bit_cast<std::uint64_t>(report_witness.original_objective) !=
                std::bit_cast<std::uint64_t>(witness.original_objective))
            return artifacts::ArtifactError{artifacts::ArtifactErrorCode::identity,
                "run.verification[" + std::to_string(i) + "].witness",
                "Verifier report is not bound to the selected witness at the same index"};

        const auto* synthesis = std::get_if<SynthesisResult>(&execution.outcome);
        const auto* projected = std::get_if<artifacts::SynthesisFinal>(&execution.final_projection);
        if (!synthesis || !synthesis->family || !projected || !projected->family ||
            !report.input.family || !report.input.expected_synthesis || !report.input.outcome)
            return artifacts::ArtifactError{artifacts::ArtifactErrorCode::identity,
                "run.verification[" + std::to_string(i) + "].context",
                "A selected-witness report must retain its synthesis family, expectation, and outcome"};

        const auto& identity = synthesis->family->identity();
        const auto& expectation = *report.input.expected_synthesis;
        const auto& configuration_input = configuration.description();
        const auto strategy_module = std::find_if(configuration_input.modules.begin(),
            configuration_input.modules.end(), [](const auto& module) { return module.role == "strategy"; });
        if (report.input.family->identity() != identity || projected->family->family.identity() != identity ||
            report.input.outcome->subject != synthesis->outcome.subject ||
            synthesis_outcome_json(*report.input.outcome) != synthesis_outcome_json(synthesis->outcome) ||
            objective_evidence_json(report.input.bounds) != objective_evidence_json(synthesis->objective) ||
            expectation.strategy != identity.strategy || expectation.strategy_version != identity.strategy_version ||
            expectation.request != identity.request || expectation.lineage != identity.lineage ||
            configuration_input.strategy.strategy != identity.strategy ||
            strategy_module == configuration_input.modules.end() ||
            strategy_module->implementation.id != identity.strategy ||
            strategy_module->implementation.version != identity.strategy_version ||
            configuration_input.output.assurance != identity.request.assurance ||
            configuration_input.output.family != identity.request.target ||
            configuration_input.output.representation != identity.request.representation ||
            configuration_input.numerical != identity.request.numerical ||
            report.input.assurance != identity.request.assurance)
            return artifacts::ArtifactError{artifacts::ArtifactErrorCode::identity,
                "run.verification[" + std::to_string(i) + "].context",
                "Verifier family, outcome, bounds, or strategy configuration disagrees with the saved run"};
    }
    if (!execution.verification.empty()) {
        auto attachment = verification_attachment(execution.verification, problem.identity());
        if (const auto* error = std::get_if<artifacts::ArtifactError>(&attachment)) return *error;
        attachments.push_back(std::get<artifacts::Attachment>(std::move(attachment)));
    }
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
