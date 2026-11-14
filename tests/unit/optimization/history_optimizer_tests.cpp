#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include <csl/optimization/history_optimizer.hpp>
#include <csl/sets/data.hpp>

#include <limits>

using namespace csl;

namespace {
problem::ResolvedProblem source_problem() {
    Problem source{{"history-profile-problem"},
                   std::make_shared<const SystemModel>(SystemModel{
                       Dynamics{{1, 1, 0},
                                TimeDomain::discrete,
                                LinearStage{{1, 1, {1.0}}, {1, 1, {1.0}}, {1, 0, {}}, {0.0}}},
                       {}}),
                   {0.0, 1.0},
                   KnownInitial{{0.0}},
                   ContinuousDomain{{UniversalSet{1}}},
                   {UniversalSet{1}, UniversalSet{1}},
                   {},
                   {},
                   InformationPattern::nominal_open_loop,
                   LinearTerminal{{1.0}, 0.0}};
    const auto resolved =
        problem::resolve(source, {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}});
    if (!std::holds_alternative<problem::ResolvedProblem>(resolved))
        throw std::logic_error("history profile fixture must resolve");
    return std::get<problem::ResolvedProblem>(resolved);
}
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
            {histories, {}},
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
    bool bad_witness_readback{};
    std::vector<optimization::HistoryMembershipWitness> candidate_memberships;
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
            auto witness_readback = supplied->membership_witnesses;
            if (bad_witness_readback && !witness_readback.empty())
                witness_readback.pop_back();
            initialization = optimization::SuppliedReadbacks{supplied->history, std::move(initial),
                                                             std::move(supplied_duals),
                                                             std::move(dual_readback),
                                                             supplied->membership_witnesses,
                                                             std::move(witness_readback)};
        } else if (bad_initialization_mode) {
            initialization = optimization::SuppliedReadbacks{{}, {}, {}, {}};
        } else {
            initialization = optimization::BackendColdStartEvidence{
                "test-backend", "cold-start",
                "test backend does not expose internal startup state"};
        }
        return optimization::RawHistorySolve{candidate, bad_objective ? 1.0 : 0.0,
                                             std::move(initialization), "test backend",
                                             candidate_memberships};
    }
};
}

TEST_CASE(
    "strategy profile binds authored running cost to the resolved terminal objective and full history") {
    const auto problem = source_problem();
    const auto existing = request();
    optimization::StrategyHistoryOptimizationProfile profile{
        ProgramId{"strategy-profile-run"},
        {"separately-authored-running-cost",
         1,
         {{0, {optimization::QuadraticControlPenalty{{0.0}, {1.0}, {1.0}, 2.0, 1}}}}},
        0,
        "state",
        {},
        optimization::ColdStart{}};

    const auto compiled = optimization::compile_strategy_history_optimization_request(
        problem, existing.domain.original, profile);
    REQUIRE(std::holds_alternative<optimization::HistoryOptimizationRequest>(compiled));
    const auto &result = std::get<optimization::HistoryOptimizationRequest>(compiled);
    CHECK((result.identity ==
           ProgramIdentity{problem.identity(), ProgramId{"strategy-profile-run"}}));
    CHECK(result.domain.original.coordinates == existing.domain.original.coordinates);
    CHECK(result.domain.original.relation.metadata()->id ==
          existing.domain.original.relation.metadata()->id);
    CHECK(result.source_cost.running_source.objective_id == "separately-authored-running-cost");
    CHECK(result.source_cost.absolute_stage_offset == 0);
    CHECK(result.source_cost.quadratic.Q.values.back() == doctest::Approx(4.0));
    CHECK(std::holds_alternative<optimization::ColdStart>(result.start));
}

TEST_CASE("strategy profile refuses a missing immutable problem or program identity") {
    const auto problem = source_problem();
    const auto existing = request();
    optimization::StrategyHistoryOptimizationProfile profile{
        {}, {"running", 1, {}}, 0, "state", {}, optimization::ColdStart{}};
    const auto compiled = optimization::compile_strategy_history_optimization_request(
        problem, existing.domain.original, profile);
    REQUIRE(std::holds_alternative<Diagnostics>(compiled));
    CHECK(std::get<Diagnostics>(compiled).front().field == "history.profile.identity");
}

TEST_CASE("strategy preparation snapshots the authored history profile") {
    const auto resolved = source_problem();
    auto authored = std::make_shared<optimization::StrategyHistoryOptimizationProfile>(
        optimization::StrategyHistoryOptimizationProfile{ProgramId{"frozen-profile"},
                                                         {"running", 1, {}},
                                                         0,
                                                         "state",
                                                         {},
                                                         optimization::ColdStart{}});
    registry::StrategyRequest request{resolved, {}, {}, "strategy-1", {}, authored};

    const auto snapshot = registry::StrategyPort::snapshot(request);
    authored->running_cost.objective_id = "mutated-after-prepare";
    REQUIRE(snapshot.history_optimization);
    CHECK(snapshot.history_optimization.get() != authored.get());
    CHECK(snapshot.history_optimization->running_cost.objective_id == "running");
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

TEST_CASE("whole-history port rejects invalid numerical policies before backend execution") {
    for (const auto policy : {
             NumericalPolicy{std::numeric_limits<double>::quiet_NaN(), 0.0},
             NumericalPolicy{0.0, -1.0},
             NumericalPolicy{std::numeric_limits<double>::infinity(), 0.0}}) {
        auto r = request();
        Candidate candidate;
        ExecutionContext context;
        context.numerical = policy;
        const auto result = registry::HistoryOptimizerPort::run(candidate, r, context);
        REQUIRE(std::holds_alternative<Diagnostic>(result));
        CHECK(std::get<Diagnostic>(result).field == "history.numerical_policy");
        CHECK(candidate.calls == 0);
    }
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

TEST_CASE("whole-history memberships check real latent witnesses and retain the original H domain") {
    auto r = request();
    r.domain.state_frame = "physical-state-frame";
    auto &start = std::get<optimization::SuppliedStart>(r.start);
    start.history = {1.0, 0.5, 0.0};
    Candidate candidate;
    candidate.candidate = {0.0, 0.5, 0.0};
    using namespace optimization;
    const auto origin = [](HistorySetFamily family, const char *selected) {
        return HistoryMembershipOrigin{{selected}, {selected}, family,
                                       SetRelation::inner, "physical-state-frame", {1}};
    };
    auto h = std::get<sets::SetData>(sets::make_h({{"h-region"}, 1, {}},
        {std::get<numeric::MatrixView>(numeric::snapshot(Matrix{2, 1, {1, -1}})),
         std::get<numeric::VectorView>(numeric::snapshot_vector(Vector{1, 0})),
         std::get<numeric::MatrixView>(numeric::snapshot(Matrix{0, 1, {}})),
         std::get<numeric::VectorView>(numeric::snapshot_vector(Vector{}))}));
    const auto make_polytope_source = [&](const char *id) {
        const auto representation = std::get<sets::HRepresentation>(h.representation());
        return std::get<sets::SetData>(sets::make_h({{id}, 1, {}}, representation));
    };
    auto v = std::get<sets::SetData>(sets::make_v({{"v-region"}, 1, {}},
        {std::get<numeric::MatrixView>(numeric::snapshot(Matrix{2, 1, {0, 1}})),
         std::get<numeric::MatrixView>(numeric::snapshot(Matrix{0, 1, {}}))}));
    r.domain.memberships = {
        {{1}, origin(HistorySetFamily::polytope, "h-region"), HistoryHMembership{h}},
        {{1}, origin(HistorySetFamily::zonotope, "z-region"),
         HistoryZonotopeMembership{{0}, {1, 2, {1, 1}}}},
        {{1}, origin(HistorySetFamily::box, "b-region"),
         HistoryAxisBoxMembership{{0}, {1}}},
        {{1}, origin(HistorySetFamily::parallelotope, "p-region"),
         HistoryParallelotopeMembership{{0}, {1, 1, {1}}, {-1}, {1}}},
        {{1}, origin(HistorySetFamily::ellipsoid, "e-region"),
         HistoryBallFactorMembership{{{0}, {1, 2, {1, 0}}}}},
        {{1}, origin(HistorySetFamily::polytope, "v-region"), HistoryVSimplexMembership{v}}};
    for (auto &member : r.domain.memberships)
        member.origin.source =
            HistorySourceGeometry{member.origin.reference, member.origin.selected_family, member.shape};
    start.membership_witnesses = {HistoryHWitness{}, HistoryZonotopeWitness{{0.25, 0.25}},
        HistoryAxisBoxWitness{{0.5}}, HistoryParallelotopeWitness{{0.5}},
        HistoryBallFactorWitness{{0.5, 0}}, HistoryVSimplexWitness{{0.5, 0.5}}};
    candidate.candidate_memberships = start.membership_witnesses;
    const auto run = [&]() { return registry::HistoryOptimizerPort::run(candidate, r, ExecutionContext{}); };
    REQUIRE(std::holds_alternative<HistoryOptimizationResult>(run()));
    SUBCASE("polytope source can qualify zonotope and box selected memberships") {
        auto &zonotope = r.domain.memberships[1];
        zonotope.origin.reference = {"polytope-source-for-zonotope"};
        zonotope.origin.source = HistorySourceGeometry{
            zonotope.origin.reference, HistorySetFamily::polytope,
            HistoryHMembership{make_polytope_source("polytope-source-for-zonotope")}};

        auto &box = r.domain.memberships[2];
        box.origin.reference = {"polytope-source-for-box"};
        box.origin.source = HistorySourceGeometry{
            box.origin.reference, HistorySetFamily::polytope,
            HistoryHMembership{make_polytope_source("polytope-source-for-box")}};

        CHECK(std::holds_alternative<HistoryOptimizationResult>(run()));
    }
    SUBCASE("missing output witness is rejected") {
        candidate.candidate_memberships.pop_back();
        CHECK(std::holds_alternative<Diagnostic>(run()));
    }
    SUBCASE("wrong witness kind is rejected") {
        candidate.candidate_memberships[1] = HistoryBallFactorWitness{{0.25, 0.25}};
        CHECK(std::holds_alternative<Diagnostic>(run()));
    }
    SUBCASE("invalid generator reconstruction is rejected") {
        candidate.candidate_memberships[1] = HistoryZonotopeWitness{{0.1, 0.1}};
        CHECK(std::holds_alternative<Diagnostic>(run()));
    }
    SUBCASE("invalid ball norm is rejected even with a null generator") {
        candidate.candidate_memberships[4] = HistoryBallFactorWitness{{0.5, 2.0}};
        CHECK(std::holds_alternative<Diagnostic>(run()));
    }
    SUBCASE("invalid simplex is rejected despite reconstructing the state") {
        candidate.candidate_memberships[5] = HistoryVSimplexWitness{{0.7, 0.5}};
        CHECK(std::holds_alternative<Diagnostic>(run()));
    }
    SUBCASE("original full-history H remains mandatory") {
        candidate.candidate[2] = 2.0;
        CHECK(std::holds_alternative<Diagnostic>(run()));
    }
    SUBCASE("false selected-set provenance is rejected before the backend") {
        r.domain.memberships[0].origin.selected = {"different-id"};
        const auto before = candidate.calls;
        CHECK(std::holds_alternative<Diagnostic>(run()));
        CHECK(candidate.calls == before);
    }
    SUBCASE("an invalid start witness is rejected before the backend") {
        start.membership_witnesses[1] = HistoryZonotopeWitness{{2.0, -1.5}};
        const auto before = candidate.calls;
        CHECK(std::holds_alternative<Diagnostic>(run()));
        CHECK(candidate.calls == before);
    }
    SUBCASE("false start witness readback is rejected") {
        candidate.bad_witness_readback = true;
        CHECK(std::holds_alternative<Diagnostic>(run()));
    }
    SUBCASE("a singular parallelotope frame is rejected") {
        std::get<HistoryParallelotopeMembership>(r.domain.memberships[3].shape).frame.values[0] = 0;
        const auto before = candidate.calls;
        CHECK(std::holds_alternative<Diagnostic>(run()));
        CHECK(candidate.calls == before);
    }
    SUBCASE("a full-rank frame permits a singleton coordinate interval") {
        auto &region = std::get<HistoryParallelotopeMembership>(r.domain.memberships[3].shape);
        region.lower[0] = region.upper[0] = 0.5;
        auto &source_region = std::get<HistoryParallelotopeMembership>(
            r.domain.memberships[3].origin.source->geometry);
        source_region.lower[0] = source_region.upper[0] = 0.5;
        CHECK(std::holds_alternative<HistoryOptimizationResult>(run()));
    }
    SUBCASE("family and shape cannot be relabeled") {
        r.domain.memberships[1].origin.selected_family = HistorySetFamily::box;
        const auto before = candidate.calls;
        CHECK(std::holds_alternative<Diagnostic>(run()));
        CHECK(candidate.calls == before);
    }
    SUBCASE("H-representation approximation remains a polytope membership") {
        r.domain.memberships[0].origin.selected_family = HistorySetFamily::ellipsoid;
        const auto before = candidate.calls;
        CHECK(std::holds_alternative<Diagnostic>(run()));
        CHECK(candidate.calls == before);
    }
    SUBCASE("V-simplex approximation remains a polytope membership") {
        r.domain.memberships[5].origin.selected_family = HistorySetFamily::box;
        const auto before = candidate.calls;
        CHECK(std::holds_alternative<Diagnostic>(run()));
        CHECK(candidate.calls == before);
    }
    SUBCASE("missing reference identity is rejected") {
        r.domain.memberships[1].origin.reference = {""};
        const auto before = candidate.calls;
        CHECK(std::holds_alternative<Diagnostic>(run()));
        CHECK(candidate.calls == before);
    }
    SUBCASE("missing source geometry is rejected") {
        r.domain.memberships[1].origin.source.reset();
        const auto before = candidate.calls;
        CHECK(std::holds_alternative<Diagnostic>(run()));
        CHECK(candidate.calls == before);
    }
    SUBCASE("source family mismatch is rejected") {
        r.domain.memberships[1].origin.source->family = HistorySetFamily::box;
        const auto before = candidate.calls;
        CHECK(std::holds_alternative<Diagnostic>(run()));
        CHECK(candidate.calls == before);
    }
    SUBCASE("source geometry must match its independently declared family") {
        auto &source = r.domain.memberships[1].origin.source.value();
        source.family = HistorySetFamily::polytope;
        const auto before = candidate.calls;
        CHECK(std::holds_alternative<Diagnostic>(run()));
        CHECK(candidate.calls == before);
    }
    SUBCASE("source geometry dimension mismatch is rejected") {
        auto &source =
            std::get<HistoryZonotopeMembership>(r.domain.memberships[1].origin.source->geometry);
        source.center.push_back(0.0);
        const auto before = candidate.calls;
        CHECK(std::holds_alternative<Diagnostic>(run()));
        CHECK(candidate.calls == before);
    }
    SUBCASE("source identity mismatch is rejected") {
        r.domain.memberships[1].origin.source->id = {"another-source"};
        const auto before = candidate.calls;
        CHECK(std::holds_alternative<Diagnostic>(run()));
        CHECK(candidate.calls == before);
    }
    SUBCASE("native source payload identity mismatch is rejected") {
        r.domain.memberships[0].origin.source->id = {"another-h-source"};
        r.domain.memberships[0].origin.reference = {"another-h-source"};
        const auto before = candidate.calls;
        CHECK(std::holds_alternative<Diagnostic>(run()));
        CHECK(candidate.calls == before);
    }
    SUBCASE("reused set identity cannot bind contradictory zonotope payloads") {
        auto &member = r.domain.memberships[1];
        auto &source = std::get<HistoryZonotopeMembership>(member.origin.source->geometry);
        source.generators.values[0] = 2.0;
        const auto before = candidate.calls;
        CHECK(std::holds_alternative<Diagnostic>(run()));
        CHECK(candidate.calls == before);
    }
    SUBCASE("set identity cannot bind contradictory payloads across memberships") {
        auto duplicate = r.domain.memberships[2];
        auto &selected = std::get<HistoryAxisBoxMembership>(duplicate.shape);
        selected.center[0] = 0.25;
        duplicate.origin.source->geometry = duplicate.shape;
        r.domain.memberships.push_back(std::move(duplicate));
        const auto before = candidate.calls;
        CHECK(std::holds_alternative<Diagnostic>(run()));
        CHECK(candidate.calls == before);
    }
    SUBCASE("a mismatched coordinate frame is rejected") {
        r.domain.memberships[1].origin.coordinate_frame = "other-frame";
        const auto before = candidate.calls;
        CHECK(std::holds_alternative<Diagnostic>(run()));
        CHECK(candidate.calls == before);
    }
    SUBCASE("a wrong canonical state binding is rejected") {
        r.domain.memberships[1].origin.canonical_state_indices[0] = 0;
        const auto before = candidate.calls;
        CHECK(std::holds_alternative<Diagnostic>(run()));
        CHECK(candidate.calls == before);
    }
    SUBCASE("named selected coordinates must agree with the original state block") {
        const auto original = std::get<sets::HRepresentation>(r.domain.original.relation.representation());
        r.domain.original.relation = std::get<sets::SetData>(
            sets::make_h({{"full-history"}, 3, {"x0", "x1", "u0"}}, original));
        const auto selected = std::get<sets::HRepresentation>(h.representation());
        r.domain.memberships[0].shape = HistoryHMembership{std::get<sets::SetData>(
            sets::make_h({{"h-region"}, 1, {"x0"}}, selected))};
        const auto before = candidate.calls;
        CHECK(std::holds_alternative<Diagnostic>(run()));
        CHECK(candidate.calls == before);
    }
}
