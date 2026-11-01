#include <csl/optimization/finite_action_nominal.hpp>
#include <nlohmann/json.hpp>
#include "two_points_fixture.hpp"

#include <iostream>
#include <chrono>
#include <stdexcept>
#include <string>
#include <type_traits>

namespace {
using namespace csl;
using namespace csl::optimization;
using Json = nlohmann::json;

Json matrix_json(const Matrix& matrix) {
    return {{"rows", matrix.rows}, {"cols", matrix.cols}, {"values", matrix.values}};
}

Json set_vertices_json(const sets::SetData& set) {
    const auto representation = set.representation();
    const auto* vertices = std::get_if<sets::VRepresentation>(&representation);
    if(!vertices) return Json::array();
    Json result = Json::array();
    for(std::size_t row = 0; row < vertices->vertices.rows(); ++row) {
        Json point = Json::array();
        for(std::size_t column = 0; column < vertices->vertices.cols(); ++column)
            point.push_back(vertices->vertices(row, column));
        result.push_back(std::move(point));
    }
    return result;
}

Json trace_json(const NominalPlanTrace& trace) {
    return std::visit([](const auto& value) -> Json {
        using T = std::decay_t<decltype(value)>;
        Json stages = Json::array();
        if constexpr(std::is_same_v<T, reachability::FixedPlanReachable>) {
            for(const auto& stage : value.stages)
                stages.push_back({{"vertices", set_vertices_json(stage)}});
            return {{"representation", "exact_polytope"}, {"stages", std::move(stages)}};
        } else if constexpr(std::is_same_v<T, reachability::FinitePlanBoxTrace>) {
            for(const auto& stage : value.stages)
                stages.push_back({{"lower", stage.lower}, {"upper", stage.upper}});
            return {{"representation", "box"}, {"stages", std::move(stages)}};
        } else if constexpr(std::is_same_v<T, reachability::FinitePlanZonotopeTrace>) {
            for(const auto& stage : value.stages) {
                Json factors = Json::array();
                for(const auto& factor : stage.factors) factors.push_back(factor.value);
                stages.push_back({{"center", stage.center}, {"generators", matrix_json(stage.generators)},
                    {"factors", std::move(factors)}});
            }
            return {{"representation", "zonotope"}, {"stages", std::move(stages)}};
        } else if constexpr(std::is_same_v<T, reachability::FinitePlanParallelotopeTrace>) {
            for(const auto& stage : value.stages)
                stages.push_back({{"lower", stage.lower}, {"upper", stage.upper}});
            return {{"representation", "parallelotope"}, {"frame", matrix_json(value.frame)},
                {"stages", std::move(stages)}};
        } else {
            for(const auto& stage : value.stages)
                stages.push_back({{"center", stage.center}, {"radii", stage.radii}});
            return {{"representation", "ellipsoid"}, {"stages", std::move(stages)}};
        }
    }, trace);
}

Json attempt_json(const NominalPlanAttempt& attempt) {
    return std::visit([](const auto& value) -> Json {
        using T = std::decay_t<decltype(value)>;
        if constexpr(std::is_same_v<T, NominalPlanScored>)
            return {{"status", "scored"}, {"action_indices", value.action_indices},
                {"candidate_score", value.candidate_score},
                {"score_kind", value.score_kind == NominalScoreKind::exact_deterministic_objective ?
                    "exact_deterministic_objective" : "numerical_outer_enclosure_estimate"}};
        else if constexpr(std::is_same_v<T, NominalPlanRejected>)
            return {{"status", "rejected"}, {"action_indices", value.action_indices},
                {"stage", value.stage}, {"violating_state", value.violating_state}};
        else if constexpr(std::is_same_v<T, NominalPlanUnscored>)
            return {{"status", "unscored"}, {"action_indices", value.action_indices}};
        else
            return {{"status", "stopped"}, {"action_indices", value.action_indices},
                {"stop_reason", static_cast<int>(value.reason.reason)}};
    }, attempt);
}

Json track_json(const NominalProfileResult& track) {
    const auto* selected = std::get_if<NominalTrackSelected>(&track.outcome);
    if(!selected) throw std::runtime_error("nominal profile did not produce a selected replay");
    Json attempts = Json::array();
    for(const auto& attempt : selected->attempts) attempts.push_back(attempt_json(attempt));
    const auto representation = track.representation == NominalRepresentation::exact_polytope ? "exact_polytope" :
        track.representation == NominalRepresentation::box ? "box" :
        track.representation == NominalRepresentation::zonotope ? "zonotope" :
        track.representation == NominalRepresentation::parallelotope ? "parallelotope" : "ellipsoid";
    const auto coverage = selected->coverage == NominalSearchCoverage::complete ? "complete" :
        selected->coverage == NominalSearchCoverage::stopped ? "stopped" : "incomplete";
    return {{"representation", representation},
        {"coverage", coverage},
        {"attempts", std::move(attempts)},
        {"selected_attempt", selected->selected_attempt},
        {"candidate_score", selected->candidate_score},
        {"score_kind", selected->score_kind == NominalScoreKind::exact_deterministic_objective ?
            "exact_deterministic_objective" : "numerical_outer_enclosure_estimate"},
        {"replay", {{"states", selected->replay.states},
            {"controls", selected->replay.controls},
            {"disturbances", selected->replay.disturbances},
            {"terminal_objective", selected->replay.terminal_objective}}},
        {"trace", trace_json(selected->selected_trace)}};
}

Json run() {
    const auto source = csl::issue824::fixture::two_points_request("issue824-nominal-report");
    FiniteActionNominalRequest nominal{source.problem, {"issue824-nominal-report"}, source.system,
        {4.5, 0.0, 0.0, 0.0}, source.actions, {{1.0}, {1.0}, {1.0}},
        source.admissible_states, source.objective};
    const auto nominal_outcome = finite_action_nominal(nominal, {27, 1000, 100000, 1000, 0.0});
    const auto* selected = std::get_if<FiniteActionNominalResult>(&nominal_outcome);
    if(!selected) throw std::runtime_error("nominal comparison did not complete");

    const auto minimax = finite_action_minimax(source, {27, 1000, 0.0});
    const auto* robust = std::get_if<FiniteMinimaxOptimal>(&minimax);
    if(!robust) throw std::runtime_error("exact finite minimax reference did not complete");
    Json tracks = Json::array();
    for(const auto& track : selected->tracks) tracks.push_back(track_json(track));
    const auto plan = robust->minimizing_plan_indices.front();
    const auto& exact_plan = std::get<FinitePlanFeasible>(robust->plans.at(plan));
    Json minimax_controls = Json::array();
    for(const auto index : exact_plan.action_indices)
        minimax_controls.push_back(source.actions.catalogue.at(index));
    return {{"schema", "csl.issue824-two-points-nominal/1"},
        {"environment", "TwoPointsOnParallelLines"},
        {"source_identity", {{"repository", "imm-rl-lab/optimal_control/Environments"},
            {"commit", "f4d76c60f4003f50954174e96eafd8e514bd5441"}}},
        {"adaptation", {{"state_order", {"x1_position_1", "x2_velocity_1", "x3_position_2", "x4_velocity_2"}},
            {"initial_state", nominal.initial_state}, {"horizon_steps", 3}, {"step_seconds", 0.1},
            {"control_catalogue", {-2.5, 0.0, 2.5}}, {"nominal_opponent_input", {1.0, 1.0, 1.0}},
            {"minimax_disturbance_catalogue", {-1.0, 0.0, 1.0}},
            {"objective", "terminal squared position gap"},
            {"source_scope", "finite-catalogue short-horizon adaptation; not the continuous 10-second RL task"}}},
        {"nominal_tracks", std::move(tracks)},
        {"exact_finite_minimax", {{"value", robust->value},
            {"selected_action_indices", exact_plan.action_indices},
            {"selected_controls", std::move(minimax_controls)}}},
        {"assurance", "numerical"}};
}

FiniteActionNominalRequest nominal_request() {
    const auto source = csl::issue824::fixture::two_points_request("issue824-nominal-report");
    return {source.problem, {"issue824-nominal-report"}, source.system,
        {4.5, 0.0, 0.0, 0.0}, source.actions, {{1.0}, {1.0}, {1.0}},
        source.admissible_states, source.objective};
}

Json measure() {
    constexpr std::size_t warmup_calls = 1;
    constexpr std::size_t calls_per_batch = 10;
    constexpr std::size_t measured_batches = 7;
    auto request = nominal_request();
    const FiniteActionNominalLimits limits{27, 1000, 100000, 1000, 0.0};
    double checksum = 0.0;
    for(std::size_t call = 0; call < warmup_calls; ++call) {
        const auto outcome = finite_action_nominal(request, limits);
        const auto* result = std::get_if<FiniteActionNominalResult>(&outcome);
        if(!result || result->tracks.size() != 5)
            throw std::runtime_error("nominal warmup did not complete all five tracks");
        for(const auto& track : result->tracks) {
            const auto* selected = std::get_if<NominalTrackSelected>(&track.outcome);
            if(!selected || selected->coverage != NominalSearchCoverage::complete ||
               selected->attempts.size() != 27)
                throw std::runtime_error("nominal warmup produced an incomplete track");
            checksum += selected->candidate_score;
        }
    }
    Json batches = Json::array();
    for(std::size_t batch = 0; batch < measured_batches; ++batch) {
        const auto start = std::chrono::steady_clock::now();
        for(std::size_t call = 0; call < calls_per_batch; ++call) {
            const auto outcome = finite_action_nominal(request, limits);
            const auto* result = std::get_if<FiniteActionNominalResult>(&outcome);
            if(!result || result->tracks.size() != 5)
                throw std::runtime_error("measured nominal call did not complete all five tracks");
            for(const auto& track : result->tracks) {
                const auto* selected = std::get_if<NominalTrackSelected>(&track.outcome);
                if(!selected || selected->coverage != NominalSearchCoverage::complete ||
                   selected->attempts.size() != 27)
                    throw std::runtime_error("measured nominal call produced an incomplete track");
                checksum += selected->candidate_score;
            }
        }
        const auto stop = std::chrono::steady_clock::now();
        const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(stop - start).count();
        batches.push_back({{"batch", batch + 1}, {"calls", calls_per_batch},
            {"duration_ns", elapsed}, {"failures", 0}});
    }
    return {{"schema", "csl.issue824-nominal-measurement/1"},
        {"scope", "finite_action_nominal API call for all five tracks; fixture construction, minimax reference, serialization, independent checker, build and rendering excluded"},
        {"warmup_calls", warmup_calls}, {"measured_batches", measured_batches},
        {"calls_per_batch", calls_per_batch}, {"batches", std::move(batches)},
        {"parallelism", "one process; sequential measured calls; no overlapping benchmark jobs"},
        {"completed_calls", measured_batches * calls_per_batch}, {"failures", 0},
        {"completed_tracks_consumed", (warmup_calls + measured_batches * calls_per_batch) * 5},
        {"candidate_score_checksum", checksum}};
}
}

int main(int argc, char** argv) {
    try {
        if(argc > 1 && std::string(argv[1]) == "--measure") {
            std::cout << measure().dump(2) << '\n';
            return 0;
        }
        const auto result = run();
        if(argc > 1 && std::string(argv[1]) == "--smoke") {
            const auto& tracks = result.at("nominal_tracks");
            if(tracks.size() != 5 || tracks[0].at("attempts").size() != 27)
                throw std::runtime_error("nominal smoke output is incomplete");
            std::cout << "issue824 nominal smoke passed\n";
        } else {
            std::cout << result.dump(2) << '\n';
        }
        return 0;
    } catch(const std::exception& error) {
        std::cerr << "issue824 nominal report failed: " << error.what() << '\n';
        return 1;
    }
}
