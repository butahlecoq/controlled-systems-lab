#include <csl/adapters/lp/highs.hpp>
#include <csl/geometry/hull_reducer.hpp>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <exception>
#include <iostream>
#include <memory>
#include <numeric>
#include <string>
#include <variant>
#include <vector>

namespace {
using namespace csl;

struct Case { std::size_t side; std::string id; };
constexpr Case cases[]{{5, "grid-25"}, {9, "grid-81"}, {13, "grid-169"}};
constexpr std::size_t repetitions = 7;
struct RunOutcome { std::int64_t elapsed_ns; std::size_t lp_calls; bool verified; };

geometry::PointCloud make_cloud(const Case& test_case) {
    geometry::PointCloud cloud{{"opt05-" + test_case.id}, {}};
    cloud.points.reserve(test_case.side * test_case.side);
    for (std::size_t y = 0; y < test_case.side; ++y)
        for (std::size_t x = 0; x < test_case.side; ++x)
            cloud.points.push_back({static_cast<double>(x) / static_cast<double>(test_case.side - 1),
                                    static_cast<double>(y) / static_cast<double>(test_case.side - 1)});
    return cloud;
}

bool expected_square_result(const geometry::PointCloud& cloud, const geometry::HullReduction& result) {
    // Row-major point identities for the four unit-square corners.
    const auto side = static_cast<std::size_t>(std::llround(std::sqrt(static_cast<double>(cloud.points.size()))));
    if (side * side != cloud.points.size()) return false;
    const std::vector<std::size_t> corners{0, side - 1, side * (side - 1), side * side - 1};
    if (result.status != geometry::ReductionStatus::complete || result.retained != corners ||
        result.lp_calls != cloud.points.size() || result.attempts.size() != cloud.points.size() ||
        result.removed.size() + result.retained.size() != cloud.points.size()) return false;

    for (const auto& point : cloud.points)
        if (point[0] < 0 || point[0] > 1 || point[1] < 0 || point[1] > 1) return false;
    for (const auto& removal : result.removed) {
        double total = 0;
        Vector reconstructed(2, 0);
        for (const auto& term : removal.combination) {
            if (term.point >= cloud.points.size() || !std::isfinite(term.weight) || term.weight < 0) return false;
            total += term.weight;
            reconstructed[0] += term.weight * cloud.points[term.point][0];
            reconstructed[1] += term.weight * cloud.points[term.point][1];
        }
        if (std::abs(total - 1.0) > 1e-8 ||
            std::abs(reconstructed[0] - cloud.points[removal.removed][0]) > 1e-8 ||
            std::abs(reconstructed[1] - cloud.points[removal.removed][1]) > 1e-8) return false;
    }
    return std::all_of(result.attempts.begin(), result.attempts.end(), [](const auto& attempt) {
        return attempt.outcome == geometry::MembershipOutcome::feasible ||
               attempt.outcome == geometry::MembershipOutcome::infeasible;
    });
}

const char* result_status(const geometry::HullReductionResult& outcome) {
    if (std::holds_alternative<Diagnostics>(outcome)) return "diagnostics";
    const auto& result = std::get<geometry::HullReduction>(outcome);
    return result.status == geometry::ReductionStatus::complete ? "complete" : "incomplete";
}

RunOutcome emit(std::size_t round, const Case& test_case, bool warmup, bool quiet = false) {
    const auto cloud = make_cloud(test_case);
    auto registration = adapters::lp::make_highs_registration();
    if (!std::holds_alternative<registry::Registration<registry::LPPort>>(registration))
        throw std::runtime_error("HiGHS LP registration failed");
    auto adapter = std::get<registry::Registration<registry::LPPort>>(std::move(registration));
    auto seed = optimization::make_linear_program({{{"opt05"}, {"workspace-seed"}}, {}, 0,
        {0, 0, {0}, {}, {}}, {}, {}});
    if (!std::holds_alternative<LinearProgram>(seed)) throw std::runtime_error("LP workspace seed failed");
    auto workspace = adapter.factory(std::get<LinearProgram>(seed));
    if (!workspace) throw std::runtime_error("LP workspace factory returned null");

    const auto start = std::chrono::steady_clock::now();
    const auto outcome = geometry::reduce_hull(cloud, *workspace, {});
    const auto stop = std::chrono::steady_clock::now();
    const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(stop - start).count();
    const bool verified = std::holds_alternative<geometry::HullReduction>(outcome) &&
        (quiet ? std::get<geometry::HullReduction>(outcome).status == geometry::ReductionStatus::complete :
         expected_square_result(cloud, std::get<geometry::HullReduction>(outcome)));
    std::size_t lp_calls = 0, attempts = 0, removed = 0, retained = 0;
    std::size_t feasible = 0, infeasible = 0, unsupported = 0, stopped = 0, numerical = 0, malformed = 0;
    if (std::holds_alternative<geometry::HullReduction>(outcome)) {
        const auto& result = std::get<geometry::HullReduction>(outcome);
        lp_calls = result.lp_calls; attempts = result.attempts.size();
        removed = result.removed.size(); retained = result.retained.size();
        for (const auto& attempt : result.attempts) switch (attempt.outcome) {
            case geometry::MembershipOutcome::feasible: ++feasible; break;
            case geometry::MembershipOutcome::infeasible: ++infeasible; break;
            case geometry::MembershipOutcome::unsupported: ++unsupported; break;
            case geometry::MembershipOutcome::stopped: ++stopped; break;
            case geometry::MembershipOutcome::numerical_failure: ++numerical; break;
            case geometry::MembershipOutcome::malformed_result: ++malformed; break;
        }
    }
    if (!quiet) std::cout << "{\"round\":" << round << ",\"case_id\":\"" << test_case.id
        << "\",\"points\":" << cloud.points.size() << ",\"warmup\":" << (warmup ? "true" : "false")
        << ",\"elapsed_ns\":" << elapsed << ",\"status\":\"" << result_status(outcome)
        << "\",\"verified\":" << (verified ? "true" : "false") << ",\"lp_calls\":" << lp_calls
        << ",\"attempts\":" << attempts << ",\"removed\":" << removed << ",\"retained\":" << retained
        << ",\"outcomes\":{\"feasible\":" << feasible << ",\"infeasible\":" << infeasible
        << ",\"unsupported\":" << unsupported << ",\"stopped\":" << stopped
        << ",\"numerical_failure\":" << numerical << ",\"malformed_result\":" << malformed << "}}\n";
    if (!quiet) std::cout.flush();
    if (!verified) throw std::runtime_error("unexpected/incomplete reduction; raw failure row retained");
    return {elapsed, lp_calls, verified};
}
} // namespace

int main(int argc, char** argv) {
    try {
        if (argc != 2 || (std::string(argv[1]) != "measure" && std::string(argv[1]) != "profile")) {
            std::cerr << "usage: csl_hull_measure measure|profile\n";
            return 2;
        }
        if (std::string(argv[1]) == "measure") {
            for (const auto& test_case : cases) emit(0, test_case, true);
            for (std::size_t round = 0; round < repetitions; ++round) {
                for (std::size_t offset = 0; offset < 3; ++offset)
                    emit(round, cases[(round + offset) % 3], false);
            }
        } else {
            // Separate source-mapping profile: same deterministic inputs and solver settings,
            // repeated enough to sample candidate-LP work without contaminating timing records.
            std::int64_t elapsed_ns[3]{};
            std::size_t lp_calls[3]{};
            constexpr std::size_t profile_rounds = 300;
            for (std::size_t round = 0; round < profile_rounds; ++round) {
                const auto index = round % 3;
                const auto result = emit(round, cases[index], false, true);
                elapsed_ns[index] += result.elapsed_ns;
                lp_calls[index] += result.lp_calls;
            }
            for (std::size_t index = 0; index < 3; ++index)
                std::cout << "{\"profile_case\":\"" << cases[index].id << "\",\"invocations\":"
                    << profile_rounds / 3 << ",\"reducer_ns_total\":" << elapsed_ns[index]
                    << ",\"lp_calls_total\":" << lp_calls[index] << ",\"verified\":true}\n";
        }
    } catch (const std::exception& error) {
        std::cerr << "hull measurement failed: " << error.what() << '\n';
        return 1;
    }
    return 0;
}
