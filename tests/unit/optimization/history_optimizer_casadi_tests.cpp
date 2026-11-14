#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/adapters/nlp/casadi_history_optimizer.hpp>
#include <csl/sets/data.hpp>
#include <cmath>
#include <stdexcept>
#include <utility>

using namespace csl;

namespace {
template<class T,class... E> T take(std::variant<T,E...> result) {
    REQUIRE(std::holds_alternative<T>(result)); return std::get<T>(std::move(result));
}
optimization::HistoryOptimizationRequest integrator_request(double running_weight) {
    constexpr std::size_t n=8;
    Matrix inequalities{4,n,{0,0,0,0,0,0,1,0, 0,0,0,0,0,0,-1,0,
        0,0,0,0,0,0,0,1, 0,0,0,0,0,0,0,-1}};
    Vector upper{1,0,1,0};
    Matrix equalities{6,n,{1,0,0,0,0,0,0,0, 0,1,0,0,0,0,0,0,
        -1,0,1,0,0,0,-1,0, 0,-1,0,1,0,0,0,0,
        0,0,-1,0,1,0,0,0, 0,0,0,-1,0,1,0,-1}};
    Vector rhs(6,0.0);
    auto set=take(sets::make_h({{"two-step-integrator"},n,{}},
        {take(numeric::snapshot(inequalities)),take(numeric::snapshot_vector(upper)),
         take(numeric::snapshot(equalities)),take(numeric::snapshot_vector(rhs))}));
    synthesis::JointHistoryRelation histories{{{2,1,0},2},std::move(set)};
    TerminalObjective terminal=ResidualNormTerminal{{2,2,{1,0,0,1}},
        {1,1},{1,1}};
    optimization::RunningControlCost running{"half-l1-control",2,{
        {0,{optimization::EuclideanControlPenalty{{1,1,{1}},{0},running_weight}}},
        {1,{optimization::EuclideanControlPenalty{{1,1,{1}},{0},running_weight}}}}};
    const auto compiled=optimization::compile_history_cost(histories,terminal,running,0);
    if(!std::holds_alternative<optimization::HistoryCostProgram>(compiled))
        throw std::runtime_error("2D integrator source cost did not compile");
    return {{ProblemId{"2d-integrator"}, ProgramId{"terminal-l2-plus-running-l1"}},
            histories,
            std::get<optimization::HistoryCostProgram>(compiled),
            optimization::SuppliedStart{{0, 0, 0.5, 0, 0.5, 0.5, 0.5, 0.5}}};
}
}

TEST_CASE("CasADi/IPOPT requires a supplied feasible full-history start") {
    auto request=integrator_request(0.5);
    request.start = optimization::ColdStart{};
    auto registration=adapters::nlp::make_casadi_history_optimizer_registration();
    auto workspace = registration.factory(request);
    const auto result =
        registry::HistoryOptimizerPort::run(*workspace, request, ExecutionContext{});
    REQUIRE(std::holds_alternative<Diagnostic>(result));
    CHECK(std::get<Diagnostic>(result).field == "history.start");
}

TEST_CASE("running cost can choose a different history from the terminal-only minimizer") {
    auto request=integrator_request(2.0);
    auto registration=adapters::nlp::make_casadi_history_optimizer_registration();
    auto workspace=registration.factory(request);
    const auto result=registry::HistoryOptimizerPort::run(*workspace,request,ExecutionContext{});
    if (const auto *diagnostic = std::get_if<Diagnostic>(&result)) {
        INFO(diagnostic->field);
        FAIL_CHECK(diagnostic->explanation);
    }
    REQUIRE(std::holds_alternative<optimization::HistoryOptimizationResult>(result));
    const auto& solved=std::get<optimization::HistoryOptimizationResult>(result);
    CHECK(solved.source_cost.total==doctest::Approx(std::sqrt(2.0)).epsilon(1e-6));
    CHECK(solved.history[6]==doctest::Approx(0.0).epsilon(1e-6));
    CHECK(solved.history[7]==doctest::Approx(0.0).epsilon(1e-6));
}
