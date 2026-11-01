#include <csl/optimization/finite_action_box_minimax.hpp>
#include <csl/optimization/finite_action_ellipsoid_minimax.hpp>
#include <csl/optimization/finite_action_minimax.hpp>
#include <csl/optimization/finite_action_parallelotope_minimax.hpp>
#include <csl/optimization/finite_action_zonotope_minimax.hpp>
#include "two_points_fixture.hpp"
#include <nlohmann/json.hpp>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace {
using namespace csl::optimization;
using Json = nlohmann::json;
constexpr std::array<std::string_view, 5> names{
    "exact_polytope", "box", "zonotope", "parallelotope", "ellipsoid"};

struct MethodOutcome {
    std::size_t candidate_plans;
    std::vector<std::size_t> selected_action_indices;
    double replayed_worst_value;
    double reported_optimum{std::numeric_limits<double>::quiet_NaN()};
    double candidate_score{std::numeric_limits<double>::quiet_NaN()};
};

Json outcome_json(const MethodOutcome& outcome) {
    Json result{{"status", "completed"}, {"candidate_plans", outcome.candidate_plans},
        {"selected_action_indices", outcome.selected_action_indices},
        {"replayed_worst_value", outcome.replayed_worst_value}};
    if(std::isfinite(outcome.reported_optimum)) result["reported_optimum"] = outcome.reported_optimum;
    if(std::isfinite(outcome.candidate_score)) result["candidate_score"] = outcome.candidate_score;
    return result;
}

MethodOutcome solve(std::size_t method, const FiniteActionMinimaxRequest& request) {
    if(method == 0) {
        const auto outcome = finite_action_minimax(request, {27, 27, 0.0});
        const auto* result = std::get_if<FiniteMinimaxOptimal>(&outcome);
        if(!result) throw std::runtime_error("exact finite minimax did not complete");
        if(result->plans.size() != 27 || result->minimizing_plan_indices.empty())
            throw std::runtime_error("exact minimax did not enumerate all 27 control plans");
        const auto& plan = std::get<FinitePlanFeasible>(
            result->plans.at(result->minimizing_plan_indices.front()));
        return {result->plans.size(), plan.action_indices, plan.worst_value, result->value};
    }
    if(method == 1) {
        const auto outcome = finite_action_box_minimax(request, {27, 27, 27, 16});
        const auto* result = std::get_if<FiniteActionBoxMinimaxResult>(&outcome);
        if(!result || result->candidate_search != CandidateSearchCoverage::complete ||
           result->plan_attempts.size() != 27)
            throw std::runtime_error("box selector did not score all 27 plans");
        const auto* selected = std::get_if<BoxPlanSelected>(&result->selection);
        if(!selected) throw std::runtime_error("box selector did not replay a selected plan");
        const auto& plan = std::get<BoxPlanScored>(result->plan_attempts.at(
            selected->candidate_attempt_index));
        return {result->plan_attempts.size(), plan.action_indices,
            selected->replay.worst_value, std::numeric_limits<double>::quiet_NaN(),
            plan.terminal_box_maximum};
    }
    if(method == 2) {
        const auto outcome = finite_action_zonotope_minimax(request, {27, 27, 27, 64, 32768});
        const auto* result = std::get_if<FiniteActionZonotopeMinimaxResult>(&outcome);
        if(!result || result->candidate_search != CandidateSearchCoverage::complete ||
           result->plan_attempts.size() != 27)
            throw std::runtime_error("zonotope selector did not score all 27 plans");
        const auto* selected = std::get_if<ZonotopePlanSelected>(&result->selection);
        if(!selected) throw std::runtime_error("zonotope selector did not replay a selected plan");
        const auto& plan = std::get<ZonotopePlanScored>(result->plan_attempts.at(
            selected->candidate_attempt_index));
        return {result->plan_attempts.size(), plan.action_indices,
            selected->replay.worst_value, std::numeric_limits<double>::quiet_NaN(),
            plan.score.terminal_factor_corner_maximum};
    }
    if(method == 3) {
        const auto outcome = finite_action_parallelotope_minimax(request, {27, 27, 27});
        const auto* result = std::get_if<FiniteActionParallelotopeMinimaxResult>(&outcome);
        if(!result || result->candidate_search != CandidateSearchCoverage::complete ||
           result->plan_attempts.size() != 27)
            throw std::runtime_error("parallelotope selector did not score all 27 plans");
        const auto* selected = std::get_if<ParallelotopePlanSelected>(&result->selection);
        if(!selected) throw std::runtime_error("parallelotope selector did not replay a selected plan");
        const auto& plan = std::get<ParallelotopePlanScored>(result->plan_attempts.at(
            selected->candidate_attempt_index));
        return {result->plan_attempts.size(), plan.action_indices,
            selected->replay.worst_value, std::numeric_limits<double>::quiet_NaN(),
            plan.score.terminal_frame_box_corner_maximum};
    }
    const auto outcome = finite_action_ellipsoid_minimax(request, {27, 27, 27});
    const auto* result = std::get_if<FiniteActionEllipsoidMinimaxResult>(&outcome);
    if(!result || result->candidate_search != CandidateSearchCoverage::complete ||
       result->plan_attempts.size() != 27)
        throw std::runtime_error("ellipsoid selector did not score all 27 plans");
    const auto* selected = std::get_if<EllipsoidPlanSelected>(&result->selection);
    if(!selected) throw std::runtime_error("ellipsoid selector did not replay a selected plan");
    const auto& plan = std::get<EllipsoidPlanScored>(result->plan_attempts.at(
        selected->candidate_attempt_index));
    return {result->plan_attempts.size(), plan.action_indices,
        selected->replay.worst_value, std::numeric_limits<double>::quiet_NaN(),
        plan.score.terminal_support_estimate};
}

Json benchmark() {
    const auto request = csl::issue824::fixture::two_points_request(
        "issue824-two-points-matched-minimax-v1");
    Json warmups = Json::array();
    for(std::size_t method = 0; method < names.size(); ++method) {
        const auto value = solve(method, request);
        warmups.push_back({{"method", names[method]}, {"outcome", outcome_json(value)}});
    }

    constexpr std::size_t repetitions = 5;
    Json samples = Json::array();
    std::array<std::vector<std::int64_t>, names.size()> durations;
    std::array<std::size_t, names.size()> failures{};
    for(std::size_t repetition = 0; repetition < repetitions; ++repetition) {
        for(std::size_t offset = 0; offset < names.size(); ++offset) {
            const auto method = (repetition + offset) % names.size();
            const auto start = std::chrono::steady_clock::now();
            try {
                const auto result = solve(method, request);
                const auto stop = std::chrono::steady_clock::now();
                const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(stop - start).count();
                durations[method].push_back(elapsed);
                samples.push_back({{"repetition", repetition + 1}, {"order_in_repetition", offset + 1},
                    {"method", names[method]}, {"elapsed_ns", elapsed},
                    {"outcome", outcome_json(result)}});
            } catch(const std::exception& error) {
                const auto stop = std::chrono::steady_clock::now();
                ++failures[method];
                const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(stop - start).count();
                samples.push_back({{"repetition", repetition + 1}, {"order_in_repetition", offset + 1},
                    {"method", names[method]}, {"elapsed_ns", elapsed}, {"status", "failed"},
                    {"error", error.what()}});
            }
        }
    }

    Json summaries = Json::array();
    for(std::size_t method = 0; method < names.size(); ++method) {
        auto sorted = durations[method];
        std::sort(sorted.begin(), sorted.end());
        Json summary{{"method", names[method]}, {"requested_repetitions", repetitions},
            {"successful_repetitions", sorted.size()}, {"failures", failures[method]}};
        if(!sorted.empty()) summary.update({{"minimum_ns", sorted.front()},
            {"median_ns", sorted[sorted.size() / 2]}, {"maximum_ns", sorted.back()}});
        summaries.push_back(std::move(summary));
    }
    return {{"schema", "csl.issue824.matched-minimax-benchmark/1"},
        {"fixture", {{"environment", "TwoPointsOnParallelLines"},
            {"source_repository", "imm-rl-lab/optimal_control/Environments"},
            {"source_commit", "f4d76c60f4003f50954174e96eafd8e514bd5441"},
            {"state_order", {"x1", "x2", "x3", "x4"}},
            {"initial_state", {4.5, 0.0, 0.0, 0.0}}, {"horizon_steps", 3},
            {"step_seconds", 0.1}, {"control_catalogue", {-2.5, 0.0, 2.5}},
            {"disturbance_catalogue", {-1.0, 0.0, 1.0}},
            {"discrete_state_map", {"x1_next=x1+0.01*x2+0.09*u", "x2_next=u",
                "x3_next=x3+0.1*x4+0.0045*v", "x4_next=x4+0.1*v"}},
            {"objective", "minimum worst-case terminal squared position gap"},
            {"information_pattern", "open-loop control plan, then all finite disturbance histories"},
            {"scope", "finite-catalog adaptation; not the upstream continuous-action 10-second RL task"}}},
        {"methods", {"exact_polytope", "box", "zonotope", "parallelotope", "ellipsoid"}},
        {"measurement", {{"repetitions_per_method", repetitions},
            {"warmups_per_method", 1}, {"order", "five methods rotate order across five rounds"},
            {"timed_region", "complete public algorithm call and scalar/vector witness extraction"},
            {"excluded", "request construction, fixture construction, JSON serialization, build, and independent check"},
            {"workers", 1}, {"arithmetic", "binary64"}, {"seed", "none; deterministic finite catalogs"},
            {"assertion", "all 27 control plans scored; approximate selected plans replayed over all 27 disturbance histories"}}},
        {"warmups", std::move(warmups)}, {"summaries", std::move(summaries)},
        {"samples", std::move(samples)}};
}
}

int main(int argc, char** argv) {
    try {
        if(argc == 1) {
            std::cout << benchmark().dump(2) << '\n';
            return 0;
        }
        if(argc == 4 && std::string_view(argv[1]) == "--profile") {
            const std::string_view requested = argv[2];
            std::size_t method = names.size();
            for(std::size_t i = 0; i < names.size(); ++i)
                if(names[i] == requested) method = i;
            if(method == names.size()) throw std::runtime_error("unknown profile method");
            const auto calls = static_cast<std::size_t>(std::stoull(argv[3]));
            const auto request = csl::issue824::fixture::two_points_request(
                "issue824-two-points-matched-minimax-profile");
            double checksum = 0.0;
            for(std::size_t i = 0; i < calls; ++i)
                checksum += solve(method, request).replayed_worst_value;
            std::cout << "profile calls completed: " << calls << ", checksum: " << checksum << '\n';
            return 0;
        }
        throw std::runtime_error("usage: csl_issue824_matched_minimax_report [--profile METHOD CALLS]");
    } catch(const std::exception& error) {
        std::cerr << "issue824 matched minimax benchmark failed: " << error.what() << '\n';
        return 1;
    }
}
