#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/adapters/nlp/casadi_superscs_history_optimizer.hpp>
#include <csl/sets/data.hpp>
#include <cmath>
#include <stdexcept>
#include <utility>

using namespace csl;

namespace {
template <class T, class... E> T take(std::variant<T, E...> result) {
    REQUIRE(std::holds_alternative<T>(result));
    return std::get<T>(std::move(result));
}
optimization::HistoryOptimizationRequest integrator_request(double running_weight) {
    constexpr std::size_t n = 8;
    Matrix inequalities{4, n, {0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, -1, 0,
                               0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0,  -1}};
    Vector upper{1, 0, 1, 0};
    Matrix equalities{6, n, {1,  0, 0,  0, 0, 0, 0,  0, 0, 1,  0, 0,  0, 0, 0, 0,
                             -1, 0, 1,  0, 0, 0, -1, 0, 0, -1, 0, 1,  0, 0, 0, 0,
                             0,  0, -1, 0, 1, 0, 0,  0, 0, 0,  0, -1, 0, 1, 0, -1}};
    Vector rhs(6, 0.0);
    auto set = take(
        sets::make_h({{"two-step-integrator"}, n, {}},
                     {take(numeric::snapshot(inequalities)), take(numeric::snapshot_vector(upper)),
                      take(numeric::snapshot(equalities)), take(numeric::snapshot_vector(rhs))}));
    synthesis::JointHistoryRelation histories{{{2, 1, 0}, 2}, std::move(set)};
    TerminalObjective terminal = ResidualNormTerminal{{2, 2, {1, 0, 0, 1}}, {1, 1}, {1, 1}};
    optimization::RunningControlCost running{
        "half-l1-control",
        2,
        {{0, {optimization::EuclideanControlPenalty{{1, 1, {1}}, {0}, running_weight}}},
         {1, {optimization::EuclideanControlPenalty{{1, 1, {1}}, {0}, running_weight}}}}};
    const auto compiled = optimization::compile_history_cost(histories, terminal, running, 0);
    if (!std::holds_alternative<optimization::HistoryCostProgram>(compiled))
        throw std::runtime_error("2D integrator source cost did not compile");
    return {{ProblemId{"2d-integrator"}, ProgramId{"terminal-l2-plus-running-l1"}},
            {histories, {}},
            std::get<optimization::HistoryCostProgram>(compiled),
            optimization::ColdStart{}};
}
optimization::HistoryOptimizationResult solve(double running_weight) {
    auto request = integrator_request(running_weight);
    auto registration = adapters::nlp::make_casadi_superscs_history_optimizer_registration();
    auto workspace = registration.factory(request);
    const auto result =
        registry::HistoryOptimizerPort::run(*workspace, request, ExecutionContext{});
    if (!std::holds_alternative<optimization::HistoryOptimizationResult>(result))
        throw std::runtime_error(std::get<Diagnostic>(result).explanation);
    return std::get<optimization::HistoryOptimizationResult>(result);
}
}

TEST_CASE("SuperSCS solves the original sum of source norms at a vector cone apex") {
    const auto solved = solve(0.5);
    CHECK(solved.source_cost.total == doctest::Approx(1.0).epsilon(1e-7));
    CHECK(solved.history[6] == doctest::Approx(1.0).epsilon(1e-7));
    CHECK(solved.history[7] == doctest::Approx(1.0).epsilon(1e-7));
    REQUIRE(std::holds_alternative<optimization::BackendColdStartEvidence>(solved.initialization));
    const auto &cold = std::get<optimization::BackendColdStartEvidence>(solved.initialization);
    CHECK(cold.backend_identity == "csl.conic.superscs.history-cost@1");
    CHECK_FALSE(cold.readback_unavailable_reason.empty());
}

TEST_CASE(
    "SuperSCS preserves separate source norms when the running cost changes the optimal history") {
    const auto solved = solve(2.0);
    CHECK(solved.source_cost.total == doctest::Approx(std::sqrt(2.0)).epsilon(1e-7));
    CHECK(solved.history[6] == doctest::Approx(0.0).epsilon(1e-7));
    CHECK(solved.history[7] == doctest::Approx(0.0).epsilon(1e-7));
}

TEST_CASE("SuperSCS refuses a supplied start instead of silently converting it to a cold start") {
    auto request = integrator_request(0.5);
    request.start = optimization::SuppliedStart{{0, 0, 0.5, 0, 0.5, 0.5, 0.5, 0.5}};
    auto registration = adapters::nlp::make_casadi_superscs_history_optimizer_registration();
    const auto capability = registration.capabilities(request, registry::Requirements{});
    REQUIRE(std::holds_alternative<Diagnostics>(capability));
    CHECK(std::get<Diagnostics>(capability).front().field == "history.start");
}
