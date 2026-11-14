#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/optimization/history_optimizer.hpp>
#include <csl/sets/data.hpp>

using namespace csl;

namespace {
optimization::HistoryOptimizationRequest request() {
    const JointCoordinates coordinates{{1,1,0},1};
    auto set=sets::make_h({{"full-history"},3,{}},
        {std::get<numeric::MatrixView>(numeric::snapshot(Matrix{2,3,{0,0,1,0,0,-1}})),
         std::get<numeric::VectorView>(numeric::snapshot_vector(Vector{1,0})),
         std::get<numeric::MatrixView>(numeric::snapshot(Matrix{0,3,{}})),
         std::get<numeric::VectorView>(numeric::snapshot_vector(Vector{}))});
    synthesis::JointHistoryRelation histories{coordinates,std::get<sets::SetData>(std::move(set))};
    optimization::RunningControlCost running{"",0,{}};
    auto compiled=optimization::compile_history_cost(histories,LinearTerminal{{0.0},0.0},running,0);
    return {{ProblemId{"problem"}, ProgramId{"source-objective"}},
            histories,
            std::get<optimization::HistoryCostProgram>(std::move(compiled)),
            optimization::SuppliedStart{Vector{1.0, 0.0, 0.0}}};
}
struct Candidate final:optimization::HistoryOptimizerWorkspace {
    Vector candidate{0.0,0.0,0.0};
    bool bad_readback{};
    bool bad_dual_shape{};
    bool bad_dual_readback{};
    bool bad_objective{};
    bool bad_initialization_mode{};
    int calls{};
    optimization::RawHistorySolveOutcome solve_candidate(const optimization::HistoryOptimizationRequest& r,
        const ExecutionContext&) override {
        ++calls;
        optimization::RawHistoryInitializationEvidence initialization;
        if (const auto *supplied = std::get_if<optimization::SuppliedStart>(&r.start)) {
            auto initial = supplied->history;
            if (bad_readback)
                initial[0] += 1;
            Vector supplied_duals(2, 0.0), dual_readback(bad_dual_shape ? 1 : 2, 0.0);
            if (bad_dual_readback)
                dual_readback[0] = 1.0;
            initialization = optimization::SuppliedReadbacks{supplied->history, std::move(initial),
                                                             std::move(supplied_duals),
                                                             std::move(dual_readback)};
        } else if (bad_initialization_mode) {
            initialization = optimization::SuppliedReadbacks{{}, {}, {}, {}};
        } else {
            initialization = optimization::BackendColdStartEvidence{
                "test-backend", "cold-start",
                "test backend does not expose internal startup state"};
        }
        return optimization::RawHistorySolve{candidate, bad_objective ? 1.0 : 0.0,
                                             std::move(initialization), "test backend"};
    }
};
}

TEST_CASE("whole-history port checks backend output against the original cost") {
    auto r=request();
    Candidate candidate;
    const auto result=registry::HistoryOptimizerPort::run(candidate,r,ExecutionContext{});
    REQUIRE(std::holds_alternative<optimization::HistoryOptimizationResult>(result));
    const auto& checked=std::get<optimization::HistoryOptimizationResult>(result);
    CHECK(checked.identity==r.identity);
    CHECK(checked.history==Vector{0.0,0.0,0.0});
    CHECK(checked.source_cost.total==doctest::Approx(0.0));
    CHECK(std::holds_alternative<optimization::VerifiedSuppliedStart>(checked.initialization));
}

TEST_CASE("whole-history port accepts explicit cold start without fabricated readbacks") {
    auto r = request();
    r.start = optimization::ColdStart{};
    Candidate candidate;
    const auto result = registry::HistoryOptimizerPort::run(candidate, r, ExecutionContext{});
    REQUIRE(std::holds_alternative<optimization::HistoryOptimizationResult>(result));
    const auto &checked = std::get<optimization::HistoryOptimizationResult>(result);
    REQUIRE(std::holds_alternative<optimization::BackendColdStartEvidence>(checked.initialization));
    const auto &evidence = std::get<optimization::BackendColdStartEvidence>(checked.initialization);
    CHECK(evidence.backend_identity == "test-backend");
    CHECK_FALSE(evidence.readback_unavailable_reason.empty());
}

TEST_CASE("whole-history port rejects initialization evidence from the wrong mode") {
    auto r = request();
    r.start = optimization::ColdStart{};
    Candidate candidate;
    candidate.bad_initialization_mode = true;
    const auto result = registry::HistoryOptimizerPort::run(candidate, r, ExecutionContext{});
    REQUIRE(std::holds_alternative<Diagnostic>(result));
    CHECK(std::get<Diagnostic>(result).field == "history.backend.cold_start");
}

TEST_CASE("whole-history port rejects false initialization readback") {
    auto r=request();
    Candidate candidate; candidate.bad_readback=true;
    const auto result=registry::HistoryOptimizerPort::run(candidate,r,ExecutionContext{});
    REQUIRE(std::holds_alternative<Diagnostic>(result));
    CHECK(std::get<Diagnostic>(result).field=="history.backend.readback");
}

TEST_CASE("whole-history port rejects false zero-dual readback") {
    auto r=request();
    Candidate candidate; candidate.bad_dual_readback=true;
    const auto result=registry::HistoryOptimizerPort::run(candidate,r,ExecutionContext{});
    REQUIRE(std::holds_alternative<Diagnostic>(result));
    CHECK(std::get<Diagnostic>(result).field=="history.backend.readback");
}

TEST_CASE("whole-history port rejects mismatched supplied and read-back dual vectors") {
    auto r=request();
    Candidate candidate; candidate.bad_dual_shape=true;
    const auto result=registry::HistoryOptimizerPort::run(candidate,r,ExecutionContext{});
    REQUIRE(std::holds_alternative<Diagnostic>(result));
    CHECK(std::get<Diagnostic>(result).field=="history.backend.readback");
}

TEST_CASE("whole-history port rejects a compiled polynomial inconsistent with source formulas") {
    auto r=request(); r.source_cost.quadratic.offset+=1.0;
    Candidate candidate;
    const auto result=registry::HistoryOptimizerPort::run(candidate,r,ExecutionContext{});
    REQUIRE(std::holds_alternative<Diagnostic>(result));
    CHECK(std::get<Diagnostic>(result).field=="history.cost");
    CHECK(candidate.calls==0);
}

TEST_CASE("whole-history port rejects a backend objective that differs from source J") {
    auto r=request();
    Candidate candidate; candidate.bad_objective=true;
    const auto result=registry::HistoryOptimizerPort::run(candidate,r,ExecutionContext{});
    REQUIRE(std::holds_alternative<Diagnostic>(result));
    CHECK(std::get<Diagnostic>(result).field=="history.backend.objective");
}

TEST_CASE("whole-history port checks every returned full-domain inequality") {
    auto r=request();
    Candidate candidate; candidate.candidate={0.0,0.0,2.0};
    const auto result=registry::HistoryOptimizerPort::run(candidate,r,ExecutionContext{});
    REQUIRE(std::holds_alternative<Diagnostic>(result));
    CHECK(std::get<Diagnostic>(result).field=="history.backend.feasibility");
}

TEST_CASE("whole-history port rejects an infeasible initial history before calling the backend") {
    auto r = request();
    std::get<optimization::SuppliedStart>(r.start).history[2] = 2.0;
    Candidate candidate;
    const auto result=registry::HistoryOptimizerPort::run(candidate,r,ExecutionContext{});
    REQUIRE(std::holds_alternative<Diagnostic>(result));
    CHECK(std::get<Diagnostic>(result).field=="history.initial");
    CHECK(candidate.calls==0);
}
