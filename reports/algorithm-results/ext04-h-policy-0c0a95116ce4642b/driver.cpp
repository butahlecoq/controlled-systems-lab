#include <csl/adapters/lp/highs.hpp>
#include <csl/controllers/continuous_policy.hpp>
#include <csl/optimization/linear_program.hpp>
#include <nlohmann/json.hpp>

#include <array>
#include <chrono>
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string_view>

namespace {
using namespace csl;
using namespace csl::controllers;
using namespace csl::model;
using nlohmann::json;
using Clock = std::chrono::steady_clock;

struct Fixture {
    LinearSystem system;
    HContinuousPolicyRequest safe_request;
    HContinuousPolicyRequest violation_request;
};

template<class T>
T require_value(std::variant<T, Diagnostic>&& result, std::string_view label) {
    if (const auto* diagnostic = std::get_if<Diagnostic>(&result))
        throw std::runtime_error(std::string(label) + ": " + diagnostic->explanation);
    return std::get<T>(std::move(result));
}

numeric::MatrixView matrix_view(Matrix value) {
    auto result = numeric::snapshot(value);
    if (!std::holds_alternative<numeric::MatrixView>(result))
        throw std::runtime_error("matrix fixture rejected");
    return std::get<numeric::MatrixView>(std::move(result));
}

numeric::VectorView vector_view(Vector value) {
    auto result = numeric::snapshot_vector(value);
    if (!std::holds_alternative<numeric::VectorView>(result))
        throw std::runtime_error("vector fixture rejected");
    return std::get<numeric::VectorView>(std::move(result));
}

Fixture make_fixture() {
    SystemModel authored;
    authored.dynamics.dimensions = {1, 1, 0};
    authored.dynamics.time_domain = TimeDomain::discrete;
    authored.dynamics.stages.emplace<LinearStage>(LinearStage{
        {1, 1, {1}}, {1, 1, {1}}, {1, 0, {}}, {0}});
    Observation observation;
    observation.coefficients.emplace<ObservationStage>(ObservationStage{
        {1, 1, {1}}, {1, 1, {0}}, {1, 0, {}}, {1, 1, {1}}, {0}});
    observation.schedule.push_back({{0}, {{0}, ObservationTiming::before_decision},
        {{0}, ObservationTiming::before_decision}, std::nullopt});
    authored.observations.push_back(std::move(observation));
    auto system = require_value<LinearSystem>(snapshot(authored, Vector{0, 1}), "system");

    auto domain = require_value<sets::SetData>(sets::make_h(
        {{"h-joint-line"}, 2, {"initial-state", "measurement-error"}},
        {matrix_view({4, 2, {1,0, -1,0, 0,1, 0,-1}}),
         vector_view({1,1,0.1,0.1}),
         matrix_view({1, 2, {-0.1,1}}), vector_view({0})}), "H-domain");
    auto joint = make_joint_h_uncertainty(system, std::move(domain));
    if (!std::holds_alternative<JointHUncertainty>(joint))
        throw std::runtime_error("joint H-domain rejected");

    auto policy_result = make_affine_observation_policy(system, {
        AffineStagePolicy{{0}, {{{0}, {0}, 0}}, {1,1,{1}}, {0},
            {1,1,{0}}, {1,1,{-1}}, {0}}
    });
    if (!std::holds_alternative<AffineObservationPolicy>(policy_result))
        throw std::runtime_error("affine observation policy rejected");
    auto policy = std::get<AffineObservationPolicy>(std::move(policy_result));

    HContinuousPolicyRequest safe{{{"ext04-h-policy"}, {"correlated-safe"}},
        std::get<JointHUncertainty>(joint), policy,
        {{{2,1,{1,-1}}, {1.2,1.2}}, {{2,1,{1,-1}}, {0.2,0.2}}},
        {{{2,1,{1,-1}}, {1.2,1.2}}}, 1e-9};
    HContinuousPolicyRequest violation{{{"ext04-h-policy"}, {"correlated-violation"}},
        std::get<JointHUncertainty>(std::move(joint)), std::move(policy),
        {{{2,1,{1,-1}}, {1.2,1.2}}, {{2,1,{1,-1}}, {0.05,0.2}}},
        {{{2,1,{1,-1}}, {1.2,1.2}}}, 1e-9};
    return {std::move(system), std::move(safe), std::move(violation)};
}

auto make_workspace() {
    auto registration = adapters::lp::make_highs_registration();
    if (const auto* errors = std::get_if<Diagnostics>(&registration))
        throw std::runtime_error("HiGHS registration failed: " + errors->front().explanation);
    auto seed = optimization::make_linear_program({{{"ext04-h-policy"}, {"workspace-seed"}},
        {0.0}, 0.0, {1,1,{0,0},{},{}}, {{std::nullopt, std::nullopt}},
        {{0.0, 0.0}}});
    if (!std::holds_alternative<LinearProgram>(seed))
        throw std::runtime_error("HiGHS workspace seed rejected");
    return std::get<registry::Registration<registry::LPPort>>(std::move(registration)).factory(
        std::get<LinearProgram>(std::move(seed)));
}

json verify_safe(const HContinuousPolicyResult& result) {
    if (!std::holds_alternative<HContinuousPolicyEvidence>(result))
        throw std::runtime_error("H policy evaluation did not return evidence");
    const auto& evidence = std::get<HContinuousPolicyEvidence>(result);
    if (evidence.assurance != Assurance::numerical ||
        evidence.feasibility != NumericalFeasibility::within_tolerance ||
        !evidence.domain_witness || !evidence.domain_witness_trajectory ||
        evidence.constraints.size() != 6)
        throw std::runtime_error("H-domain safety outcome differs");
    const auto& inputs = evidence.domain_witness_trajectory->inputs;
    const auto x = inputs.initial_state[0];
    const auto error = inputs.measurement_errors[0][0][0];
    if (std::abs(error - 0.1 * x) > 1e-8 ||
        std::abs((*evidence.domain_witness)[1] - 0.1 * (*evidence.domain_witness)[0]) > 1e-8)
        throw std::runtime_error("correlation was not preserved in the H-domain witness");
    constexpr std::array<double, 6> expected_maxima{1.0, 1.0, 0.1, 0.1, 1.1, 1.1};
    json rows = json::array();
    for (std::size_t i = 0; i < evidence.constraints.size(); ++i) {
        const auto& row = evidence.constraints[i];
        if (!row.maximum_activity_upper_bound || !row.dual_primal_check ||
            std::abs(*row.maximum_activity_upper_bound - expected_maxima[i]) > 1e-7 ||
            *row.maximum_activity_upper_bound > row.upper_bound)
            throw std::runtime_error("dual support upper bound differs from the analytic value");
        rows.push_back({{"family", row.family == SafetyFamily::state ? "state" : "action"},
            {"stage", row.stage}, {"row", row.row}, {"upper_bound", row.upper_bound},
            {"support_upper_bound", *row.maximum_activity_upper_bound},
            {"dual_row_violation", row.dual_primal_check->rows.violation},
            {"dual_variable_violation", row.dual_primal_check->variables.violation}});
    }
    return {{"domain_witness", *evidence.domain_witness},
        {"initial_state", inputs.initial_state}, {"measurement_error", error},
        {"action", evidence.domain_witness_trajectory->decisions.front().action[0]},
        {"terminal_state", evidence.domain_witness_trajectory->states.back()[0]},
        {"constraints", std::move(rows)}};
}

void verify_violation(const HContinuousPolicyResult& result) {
    if (!std::holds_alternative<HContinuousPolicyEvidence>(result) ||
        std::get<HContinuousPolicyEvidence>(result).feasibility != NumericalFeasibility::violation_found)
        throw std::runtime_error("H support primal did not find the expected violation");
    const auto& rows = std::get<HContinuousPolicyEvidence>(result).constraints;
    for (const auto& row : rows)
        if (row.family == SafetyFamily::state && row.stage == 1 && row.row == 0 &&
            row.observed_activity && *row.observed_activity > row.upper_bound && row.trajectory)
            return;
    throw std::runtime_error("violating H-domain point or trajectory was not retained");
}

} // namespace

int main(int argc, char** argv) try {
    if (argc != 2 || (std::string_view(argv[1]) != "smoke" &&
                     std::string_view(argv[1]) != "measure"))
        throw std::runtime_error("expected smoke or measure");
    const bool smoke = std::string_view(argv[1]) == "smoke";
    auto fixture = make_fixture();
    auto workspace = make_workspace();
    if (smoke) {
        verify_safe(evaluate_h_continuous_policy(fixture.system, fixture.safe_request, *workspace, {}));
        verify_violation(evaluate_h_continuous_policy(fixture.system, fixture.violation_request, *workspace, {}));
        std::cout << "H-policy smoke passed: correlated safe bounds and violating replay checked\n";
        return 0;
    }

    constexpr int repetitions = 7;
    constexpr int batch = 100;
    constexpr double absolute_tolerance = 1e-8;
    constexpr double relative_tolerance = 1e-8;
    ExecutionContext context;
    context.numerical = {absolute_tolerance, relative_tolerance};
    for (int round = -1; round < repetitions; ++round) {
        json outcome;
        const auto start = Clock::now();
        for (int call = 0; call < batch; ++call)
            outcome = verify_safe(evaluate_h_continuous_policy(
                fixture.system, fixture.safe_request, *workspace, context));
        const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(
            Clock::now() - start).count();
        json record{{"schema", "csl.ext04-h-policy-trial/1"}, {"round", round + 1},
            {"warmup", round == -1}, {"batch", batch}, {"elapsed_ns", elapsed},
            {"status", "passed"}, {"assurance", "numerical"},
            {"feasibility", "within_tolerance"}, {"safety_rows", 6},
            {"lp_solves_per_call", 7}, {"absolute_tolerance", absolute_tolerance},
            {"relative_tolerance", relative_tolerance}, {"workspace_reused", true},
            {"outer_workers", 1},
            {"timing_scope", "public H-domain policy evaluator, seven HiGHS LP solves, and literal correlation, dual-residual, support-bound, and status checks; fixture creation and JSON serialization excluded"},
            {"result", std::move(outcome)}};
        std::cout << record.dump() << '\n';
    }
} catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
}
