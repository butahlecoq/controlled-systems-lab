#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/optimization/finite_action_nominal.hpp>
#include "two_points_fixture.hpp"

#include <cmath>
#include <algorithm>
#include <limits>

using namespace csl;
using namespace csl::optimization;

namespace {
template<class T> T take_nominal(std::variant<T, Diagnostic> result) {
    REQUIRE(std::holds_alternative<T>(result));
    return std::get<T>(std::move(result));
}
}

TEST_CASE("legacy nominal aggregate requests leave candidate filtering unset") {
    const auto source = csl::issue824::fixture::two_points_request("nominal-legacy-source");
    const FiniteActionNominalRequest legacy{
        source.problem, {"nominal-legacy"}, source.system, {4.5, 0.0, 0.0, 0.0},
        source.actions, {{1.0}, {1.0}, {1.0}}, source.admissible_states,
        source.objective, {}, 0};
    CHECK_FALSE(legacy.candidate_action_indices.has_value());
}

TEST_CASE("nominal finite-plan comparison keeps exact and enclosure scores distinct") {
    const auto source = csl::issue824::fixture::two_points_request("nominal-test-source");
    FiniteActionNominalRequest request{
        source.problem,
        {"nominal-test"},
        source.system,
        {4.5, 0.0, 0.0, 0.0},
        source.actions,
        {{1.0}, {1.0}, {1.0}},
        source.admissible_states,
        source.objective,
    };

    const auto outcome = finite_action_nominal(request, {27, 1000, 100000, 1000, 0.0});
    REQUIRE(std::holds_alternative<FiniteActionNominalResult>(outcome));
    const auto& result = std::get<FiniteActionNominalResult>(outcome);
    CHECK(result.problem == source.problem);
    CHECK(result.request == request.request);
    REQUIRE(result.tracks.size() == 5);
    for(std::size_t index = 0; index < result.tracks.size(); ++index) {
        const auto& track = result.tracks[index];
        REQUIRE(std::holds_alternative<NominalTrackSelected>(track.outcome));
        const auto& selected = std::get<NominalTrackSelected>(track.outcome);
        REQUIRE(selected.attempts.size() == 27);
        CHECK(selected.coverage == NominalSearchCoverage::complete);
        CHECK(selected.selected_attempt < selected.attempts.size());
        CHECK(selected.replay.states.size() == 4);
        CHECK(selected.replay.states.back()[2] > 0.0);
        CHECK(selected.replay.states.back()[3] == doctest::Approx(0.3));
        CHECK(selected.replay.controls.size() == 3);
        CHECK(selected.replay.disturbances == request.nominal_disturbances);
        CHECK(std::isfinite(selected.replay.terminal_objective));
        if(index == 0) {
            CHECK(selected.score_kind == NominalScoreKind::exact_deterministic_objective);
            CHECK(selected.candidate_score == doctest::Approx(selected.replay.terminal_objective));
        } else {
            CHECK(selected.score_kind == NominalScoreKind::numerical_outer_enclosure_estimate);
        }
    }
}

TEST_CASE("selected parallelotope MPC profile scores planar terminal corners") {
    const SystemModel authored{{{2,1,0}, TimeDomain::discrete,
        LinearStage{{2,2,{1,0,0,1}}, {2,1,{1,0}}, {2,0,{}}, {0,0}}}, {}};
    const auto system = take_nominal(model::snapshot(authored, Vector{0,1}));
    const auto safe = take_nominal(sets::make_universal({{"parallelotope-2d-safe"},2,{"x","y"}}));
    const auto objective = std::get<Objective>(snapshot(QuadraticTerminal{
        Matrix{2,2,{2,0,0,2}}, {0,0}, 0}));
    FiniteActionNominalRequest request{
        {"parallelotope-2d-mpc"}, {"parallelotope-2d-mpc-query"}, system, {0,0},
        {1, {{0},{1}}}, {{}}, {safe,safe}, objective};
    const auto outcome = finite_action_nominal_profile(request,
        {2, 32, 32, 32, 0.0}, NominalRepresentation::parallelotope);
    REQUIRE(std::holds_alternative<FiniteActionNominalResult>(outcome));
    const auto& result = std::get<FiniteActionNominalResult>(outcome);
    REQUIRE(result.tracks.size() == 1);
    const auto* selected = std::get_if<NominalTrackSelected>(&result.tracks.front().outcome);
    REQUIRE(selected);
    CHECK(selected->coverage == NominalSearchCoverage::complete);
    CHECK((selected->replay.controls == std::vector<Vector>{{0}}));
    CHECK(selected->replay.terminal_objective == doctest::Approx(0.0));
    const auto* trace = std::get_if<reachability::FinitePlanParallelotopeTrace>(&selected->selected_trace);
    REQUIRE(trace);
    CHECK(trace->frame.rows == 2);
    CHECK(trace->frame.cols == 2);
    CHECK(selected->candidate_score == doctest::Approx(0.0));
}

TEST_CASE("nominal profiles honor a restricted full-horizon source action history") {
    const SystemModel authored{{{2,1,0}, TimeDomain::discrete,
        LinearStage{{2,2,{1,0,0,1}}, {2,1,{1,0}}, {2,0,{}}, {0,0}}}, {}};
    const auto system_snapshot = model::snapshot(authored, Vector{0,1,2});
    if(const auto* diagnostic = std::get_if<Diagnostic>(&system_snapshot)) {
        INFO(diagnostic->field << ": " << diagnostic->explanation);
    }
    REQUIRE(std::holds_alternative<model::LinearSystem>(system_snapshot));
    const auto system = std::get<model::LinearSystem>(system_snapshot);
    const auto safe = take_nominal(sets::make_universal({{"candidate-history-safe"},2,{"x","y"}}));
    const auto objective = std::get<Objective>(snapshot(LinearTerminal{{-1,0}, 0.0}));
    FiniteActionNominalRequest request{
        {"candidate-history-source"}, {"candidate-history-query"}, system, {0,0},
        {1, {{0}, {1}}}, {{}, {}}, {safe,safe,safe}, objective};
    request.running_cost = {"source-euclidean-control-cost/1", 2, {
        {0, {EuclideanControlPenalty{{1,1,{1}}, {0}, 0.25}}}}};
    request.candidate_action_indices = {{1,0}, {0,0}};

    for(const auto representation : {NominalRepresentation::exact_polytope,
            NominalRepresentation::box, NominalRepresentation::zonotope,
            NominalRepresentation::parallelotope, NominalRepresentation::ellipsoid}) {
        const auto outcome = finite_action_nominal_profile(request,
            {4, 64, 64, 64, 0.0}, representation);
        REQUIRE(std::holds_alternative<FiniteActionNominalResult>(outcome));
        const auto& result = std::get<FiniteActionNominalResult>(outcome);
        REQUIRE(result.tracks.size() == 1);
        INFO("representation: " << static_cast<int>(representation));
        INFO("track outcome alternative: " << result.tracks.front().outcome.index());
        const auto* selected = std::get_if<NominalTrackSelected>(&result.tracks.front().outcome);
        REQUIRE(selected);
        CHECK(selected->coverage == NominalSearchCoverage::incomplete);
        CHECK(selected->replay.controls == std::vector<Vector>{{1},{0}});
        CHECK(selected->replay.states == std::vector<Vector>{{0,0},{1,0},{1,0}});
        CHECK(selected->replay.running_objective == doctest::Approx(0.25));
        CHECK(selected->replay.terminal_objective == doctest::Approx(-1.0));
        CHECK(selected->replay.total_objective == doctest::Approx(-0.75));
        REQUIRE(selected->attempts.size() == 2);
        const auto* scored = std::get_if<NominalPlanScored>(&selected->attempts[selected->selected_attempt]);
        REQUIRE(scored);
        CHECK(scored->action_indices == std::vector<std::size_t>{1,0});
        CHECK(scored->exact_running_cost == doctest::Approx(0.25));
    }

    auto empty_catalogue = request;
    empty_catalogue.candidate_action_indices = std::vector<std::vector<std::size_t>>{};
    const auto rejected = finite_action_nominal_profile(empty_catalogue,
        {4, 64, 64, 64, 0.0}, NominalRepresentation::exact_polytope);
    REQUIRE(std::holds_alternative<Unsupported>(rejected));
    CHECK(std::get<Unsupported>(rejected).diagnostics.front().field == "finite_nominal.candidate_plans");
}

TEST_CASE("nominal box track preserves a scored plan before a later stopped plan") {
    const SystemModel authored{{{1,1,1}, TimeDomain::discrete,
        LinearStage{{1,1,{1}}, {1,1,{1e308}}, {1,1,{0}}, {0}}}, {}};
    const auto system = take_nominal(model::snapshot(authored, Vector{0,1}));
    const auto safe = take_nominal(sets::make_universal({{"nominal-overflow-safe"},1,{"x"}}));
    const auto objective = std::get<Objective>(snapshot(LinearTerminal{{1}, 0}));
    FiniteActionNominalRequest request{
        {"nominal-box-partial"}, {"nominal-box-partial-run"}, system, {0},
        {1, {{0}, {10}}}, {{0}}, {safe, safe}, objective};
    const auto outcome = finite_action_nominal(request, {2, 4, 2, 8, 0.0});
    REQUIRE(std::holds_alternative<FiniteActionNominalResult>(outcome));
    const auto& result = std::get<FiniteActionNominalResult>(outcome);
    REQUIRE(result.tracks.size() == 5);
    CHECK(result.objective_id == request.running_cost.objective_id);
    CHECK(result.original_horizon == request.running_cost.original_horizon);
    CHECK(result.absolute_stage_offset == 0);
    CHECK(result.objective_id == request.running_cost.objective_id);
    CHECK(result.original_horizon == request.running_cost.original_horizon);
    CHECK(result.absolute_stage_offset == 0);
    const auto& box = result.tracks[1].outcome;
    const auto* selected = std::get_if<NominalTrackSelected>(&box);
    REQUIRE(selected);
    CHECK(selected->coverage == NominalSearchCoverage::incomplete);
    REQUIRE(selected->attempts.size() == 2);
    CHECK(std::holds_alternative<NominalPlanScored>(selected->attempts[0]));
    CHECK(std::holds_alternative<NominalPlanStopped>(selected->attempts[1]));
    CHECK(selected->selected_attempt == 0);
    CHECK(selected->replay.terminal_objective == 0.0);
}

TEST_CASE("nominal running-cost schedule rejects wrong full-horizon normalization") {
    const auto source = csl::issue824::fixture::two_points_request("nominal-bad-cost-source");
    FiniteActionNominalRequest request{
        source.problem, {"nominal-bad-cost-run"}, source.system, {4.5, 0.0, 0.0, 0.0},
        source.actions, {{1.0}, {1.0}, {1.0}}, source.admissible_states, source.objective};
    request.running_cost = {"source-cost/1", 3, {
        {1, {QuadraticControlPenalty{{0.0}, {1.0}, {1.0}, 1.0, 2}}}}};
    const auto outcome = finite_action_nominal(request, {27, 1000, 100000, 1000, 0.0});
    REQUIRE(std::holds_alternative<Unsupported>(outcome));
    CHECK(std::get<Unsupported>(outcome).diagnostics.front().code == DiagnosticCode::unsupported);
    CHECK(std::get<Unsupported>(outcome).diagnostics.front().field ==
        "finite_nominal.running_cost.quadratic");
}

TEST_CASE("nominal scoring skips zero-weight overflow coordinates and rejects non-finite combined scores") {
    const auto source = csl::issue824::fixture::two_points_request("nominal-running-overflow-source");
    auto request = FiniteActionNominalRequest{source.problem, {"nominal-zero-weight"}, source.system,
        {4.5, 0.0, 0.0, 0.0}, source.actions, {{1.0}, {1.0}, {1.0}},
        source.admissible_states, source.objective,
        {"source-cost/zero-weight", 3, {{0, {QuadraticControlPenalty{{0.0}, {1e-309}, {0.0}, 1.0, 3}}}}}};
    auto outcome = finite_action_nominal_profile(request, {27,1000,100000,1000,0.0},
        NominalRepresentation::exact_polytope);
    REQUIRE(std::holds_alternative<FiniteActionNominalResult>(outcome));
    REQUIRE(std::holds_alternative<NominalTrackSelected>(std::get<FiniteActionNominalResult>(outcome).tracks.front().outcome));
    CHECK(std::isfinite(std::get<NominalTrackSelected>(std::get<FiniteActionNominalResult>(outcome).tracks.front().outcome).candidate_score));

    request.running_cost = {"source-cost/overflow", 3, {{0, {QuadraticControlPenalty{{0.0}, {1e-309}, {1.0}, 1.0, 3}}}}};
    outcome = finite_action_nominal_profile(request, {27,1000,100000,1000,0.0},
        NominalRepresentation::exact_polytope);
    REQUIRE(std::holds_alternative<FiniteActionNominalResult>(outcome));
    CHECK(std::holds_alternative<NominalTrackUnsupported>(std::get<FiniteActionNominalResult>(outcome).tracks.front().outcome));
}

TEST_CASE("nominal selection preserves a positive quadratic cost when coefficient division underflows") {
    const SystemModel authored{{{1,1,0}, TimeDomain::discrete,
        LinearStage{{1,1,{1}}, {1,1,{0}}, {1,0,{}}, {0}}}, {}};
    const auto system = take_nominal(model::snapshot(authored, Vector{0,1}));
    const Matrix inequalities{2,1,{1,-1}};
    const Vector upper_bounds{10,10};
    const Matrix equalities{0,1,{}};
    const Vector equality_values{};
    const auto av = numeric::snapshot(inequalities);
    const auto bv = numeric::snapshot_vector(upper_bounds);
    const auto ev = numeric::snapshot(equalities);
    const auto fv = numeric::snapshot_vector(equality_values);
    REQUIRE(std::holds_alternative<numeric::MatrixView>(av));
    REQUIRE(std::holds_alternative<numeric::VectorView>(bv));
    REQUIRE(std::holds_alternative<numeric::MatrixView>(ev));
    REQUIRE(std::holds_alternative<numeric::VectorView>(fv));
    const auto safe = take_nominal(sets::make_h({{"tiny-nominal-safe"},1,{"x"}},
        {std::get<numeric::MatrixView>(av),std::get<numeric::VectorView>(bv),
         std::get<numeric::MatrixView>(ev),std::get<numeric::VectorView>(fv)}));
    const auto objective = std::get<Objective>(snapshot(LinearTerminal{{0},0}));
    FiniteActionNominalRequest request{{"tiny-cost-nominal"},{"tiny-cost-nominal-run"},system,
        {0}, {1, {{1},{0}}}, {{}}, {safe,safe}, objective,
        {"tiny-cost-objective",2,{{0, {QuadraticControlPenalty{{0},{1e-150},{1},
            std::numeric_limits<double>::denorm_min(),2}}}}}};
    const auto result = finite_action_nominal_profile(request,{4,16,100,16,0.0},
        NominalRepresentation::exact_polytope);
    REQUIRE(std::holds_alternative<FiniteActionNominalResult>(result));
    const auto& track = std::get<FiniteActionNominalResult>(result).tracks.front().outcome;
    REQUIRE(std::holds_alternative<NominalTrackSelected>(track));
    const auto& selected = std::get<NominalTrackSelected>(track);
    CHECK(selected.replay.controls.front()[0] == 0.0);
    CHECK(selected.candidate_score == 0.0);
    const auto costly = std::find_if(selected.attempts.begin(),selected.attempts.end(),[](const auto& attempt) {
        const auto* scored = std::get_if<NominalPlanScored>(&attempt);
        return scored && !scored->action_indices.empty() && scored->action_indices.front() == 0;
    });
    REQUIRE(costly != selected.attempts.end());
    const auto exact_running_cost=std::get<NominalPlanScored>(*costly).exact_running_cost;
    CHECK(exact_running_cost > 0.0);
    CHECK(exact_running_cost ==
        doctest::Approx(2.4703282292062326e-24).epsilon(1e-15));
    CHECK(exact_running_cost / 2.4703282292062326e-24 ==
        doctest::Approx(1.0).epsilon(1e-15).scale(0.0));
}

TEST_CASE("selected nominal profile executes one representation route") {
    const auto source = csl::issue824::fixture::two_points_request("nominal-profile-source");
    FiniteActionNominalRequest request{source.problem, {"nominal-profile-run"}, source.system,
        {4.5, 0.0, 0.0, 0.0}, source.actions, {{1.0}, {1.0}, {1.0}},
        source.admissible_states, source.objective};
    const auto outcome = finite_action_nominal_profile(request,
        {27, 1000, 100000, 1000, 0.0}, NominalRepresentation::exact_polytope);
    REQUIRE(std::holds_alternative<FiniteActionNominalResult>(outcome));
    const auto& result = std::get<FiniteActionNominalResult>(outcome);
    REQUIRE(result.tracks.size() == 1);
    CHECK(result.tracks.front().representation == NominalRepresentation::exact_polytope);
    CHECK(std::holds_alternative<NominalTrackSelected>(result.tracks.front().outcome));
}

TEST_CASE("nominal exact route optimizes the complete source objective") {
    const SystemModel authored{{{1, 1, 0}, TimeDomain::discrete,
        LinearStage{{1, 1, {1}}, {1, 1, {1}}, {1, 0, {}}, {0}}}, {}};
    const auto system = take_nominal(model::snapshot(authored, Vector{0.0, 1.0}));
    const auto safe = take_nominal(sets::make_universal({{"complete-cost-safe"}, 1, {"x"}}));
    const auto objective = std::get<Objective>(snapshot(
        QuadraticTerminal{{1, 1, {2}}, {0}, 0}));
    FiniteActionNominalRequest request{{"complete-cost"}, {"complete-cost-run"}, system,
        {1}, {1, {{-1}, {0}, {1}}}, {{ }}, {safe, safe}, objective};

    const auto terminal_only = finite_action_nominal(request, {3, 4, 100, 4, 0.0});
    REQUIRE(std::holds_alternative<FiniteActionNominalResult>(terminal_only));
    const auto& terminal_track = std::get<NominalTrackSelected>(
        std::get<FiniteActionNominalResult>(terminal_only).tracks.front().outcome);
    REQUIRE(terminal_track.replay.controls.size() == 1);
    CHECK(terminal_track.replay.controls.front().front() == -1.0);

    request.running_cost = {"source-cost/1", 1, {
        {0, {QuadraticControlPenalty{{1}, {1}, {1}, 5.0, 1}}}}};
    const auto complete = finite_action_nominal(request, {3, 4, 100, 4, 0.0});
    REQUIRE(std::holds_alternative<FiniteActionNominalResult>(complete));
    const auto& result = std::get<FiniteActionNominalResult>(complete);
    const auto& selected = std::get<NominalTrackSelected>(result.tracks.front().outcome);
    REQUIRE(selected.replay.controls.size() == 1);
    CHECK(selected.replay.controls.front().front() == 1.0);
    CHECK(selected.replay.terminal_objective == 4.0);
    CHECK(selected.replay.running_objective == 0.0);
    CHECK(selected.replay.total_objective == 4.0);
    CHECK(selected.candidate_score == 4.0);

    request.absolute_stage_offset = 1;
    request.running_cost = {"source-cost/absolute-grid/1", 2, {
        {0, {QuadraticControlPenalty{{-1}, {1}, {1}, 100.0, 2}}},
        {1, {QuadraticControlPenalty{{1}, {1}, {1}, 4.0, 2}}}}};
    const auto tail = finite_action_nominal(request, {3, 4, 100, 4, 0.0});
    REQUIRE(std::holds_alternative<FiniteActionNominalResult>(tail));
    const auto& tail_result = std::get<FiniteActionNominalResult>(tail);
    const auto& tail_selected = std::get<NominalTrackSelected>(tail_result.tracks.front().outcome);
    REQUIRE(tail_selected.replay.controls.size() == 1);
    CHECK(tail_result.original_horizon == 2);
    CHECK(tail_result.absolute_stage_offset == 1);
    CHECK(tail_selected.replay.controls.front().front() == 0.0);
    CHECK(tail_selected.replay.running_objective == 2.0);
    CHECK(tail_selected.replay.total_objective == 3.0);
}

TEST_CASE("nominal tracks preserve absolute quadratic and Euclidean running costs") {
    const auto source = csl::issue824::fixture::two_points_request("nominal-cost-source");
    FiniteActionNominalRequest request{
        source.problem, {"nominal-cost-run"}, source.system, {4.5, 0.0, 0.0, 0.0},
        source.actions, {{1.0}, {1.0}, {1.0}}, source.admissible_states, source.objective};
    request.running_cost = {"test.source-cost/1", 3, {
        {0, {QuadraticControlPenalty{{-0.25}, {2.0}, {1.0}, 0.75, 3}}},
        {1, {QuadraticControlPenalty{{0.5}, {2.0}, {1.0}, 0.75, 3}}},
        {2, {QuadraticControlPenalty{{-0.1}, {2.0}, {1.0}, 0.75, 3},
                EuclideanControlPenalty{{1, 1, {1.0}}, {0.0}, 0.2}}},
    }};

    const auto outcome = finite_action_nominal(request, {27, 1000, 100000, 1000, 0.0});
    REQUIRE(std::holds_alternative<FiniteActionNominalResult>(outcome));
    const auto& result = std::get<FiniteActionNominalResult>(outcome);
    REQUIRE(result.tracks.size() == 5);
    for(std::size_t i = 0; i < result.tracks.size(); ++i) {
        const auto* selected = std::get_if<NominalTrackSelected>(&result.tracks[i].outcome);
        REQUIRE(selected);
        double expected_running = 0.0;
        for(std::size_t k = 0; k < selected->replay.controls.size(); ++k) {
            const double ref = std::array{-0.25, 0.5, -0.1}[k];
            const double residual = (selected->replay.controls[k][0] - ref) / 2.0;
            expected_running += 0.25 * residual * residual;
            if(k == 2) expected_running += 0.2 * std::abs(selected->replay.controls[k][0]);
        }
        CHECK(selected->replay.running_objective == doctest::Approx(expected_running));
        CHECK(selected->replay.total_objective == doctest::Approx(
            selected->replay.terminal_objective + expected_running));
        const auto* scored = std::get_if<NominalPlanScored>(&selected->attempts[selected->selected_attempt]);
        REQUIRE(scored);
        CHECK(scored->candidate_score == doctest::Approx(scored->terminal_score + expected_running));
        CHECK(selected->candidate_score == doctest::Approx(scored->candidate_score));
        if(i == 0)
            CHECK(selected->score_kind == NominalScoreKind::exact_deterministic_objective);
        else
            CHECK(selected->score_kind == NominalScoreKind::numerical_outer_estimate_plus_exact_running_cost);
    }
}
