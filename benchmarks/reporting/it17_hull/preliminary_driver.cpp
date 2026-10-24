#include <csl/adapters/lp/highs.hpp>
#include <csl/geometry/basis_reuse_reducer.hpp>
#include <csl/geometry/bounded_hull_checker.hpp>
#include <csl/geometry/hull_reducer.hpp>
#include <csl/geometry/quickhull_2d.hpp>

#include <algorithm>
#include <array>
#include <chrono>
#include <iostream>
#include <memory>
#include <set>
#include <stdexcept>
#include <string>
#include <variant>

using namespace csl;

namespace {

enum class Method { quickhull, lp_baseline, basis_reuse, ordered_lp, a43_safe, a44_incremental };
constexpr std::array<Method, 6> methods{Method::quickhull, Method::lp_baseline,
    Method::basis_reuse, Method::ordered_lp, Method::a43_safe, Method::a44_incremental};

const char* name(Method method) {
    switch (method) {
    case Method::quickhull: return "geometric-quickhull";
    case Method::lp_baseline: return "lp-membership-baseline";
    case Method::basis_reuse: return "basis-reuse-related-to-A43";
    case Method::ordered_lp: return "ordered-membership-related-to-A44";
    case Method::a43_safe: return "A43-certificate-safe-basis-adaptation";
    case Method::a44_incremental: return "A44-incremental-LP-paper-adaptation";
    }
    return "invalid";
}

const char* identity(Method method) {
    switch (method) {
    case Method::quickhull: return "csl.geometry.quickhull-2d";
    case Method::lp_baseline: return "csl.hull.lp-membership";
    case Method::basis_reuse: return "csl.hull.phase-one-basis-bulk";
    case Method::ordered_lp: return "csl.hull.ordered-membership";
    case Method::a43_safe: return "csl.hull.itis17.a43-certified-basis-reuse";
    case Method::a44_incremental: return "csl.hull.itis17.a44-incremental-lp";
    }
    return "invalid";
}

struct Fixture {
    std::string id;
    geometry::PointCloud cloud;
    std::vector<Vector> expected_vertices;
};

std::vector<Fixture> fixtures() {
    return {
        {"permuted", geometry::PointCloud{{"it17-permuted"},
            {{0,0},{1,1},{2,0},{0,2},{2,2},{1,0},{1,2},{0,1},{2,1},{1,1.5}}},
            {{0,0},{2,0},{2,2},{0,2}}},
        {"degenerate", geometry::PointCloud{{"it17-degenerate"},
            {{0,0},{2,0},{2,2},{0,2},{0,0},{1,0},{1,2}}},
            {{0,0},{2,0},{2,2},{0,2}}},
        {"interior-basis", geometry::PointCloud{{"it17-interior-basis"},
            {{1,1},{0,0},{2,0},{2,2},{0,2}}},
            {{0,0},{2,0},{2,2},{0,2}}}
    };
}

std::unique_ptr<LPWorkspace> workspace(const geometry::PointCloud& cloud) {
    auto registration = adapters::lp::make_highs_registration();
    if (!std::holds_alternative<registry::Registration<registry::LPPort>>(registration)) return {};
    auto adapter = std::get<registry::Registration<registry::LPPort>>(std::move(registration));
    auto seed = optimization::make_linear_program({{{cloud.problem.value}, {"seed"}}, {}, 0,
        {0,0,{0},{},{}}, {}, {}});
    if (!std::holds_alternative<LinearProgram>(seed)) return {};
    return adapter.factory(std::get<LinearProgram>(seed));
}

bool valid_reduction(const Fixture& fixture, const geometry::HullReduction& result) {
    if (result.status != geometry::ReductionStatus::complete ||
        result.retained.empty() || result.retained.size() + result.removed.size() !=
                                   fixture.cloud.points.size()) return false;
    std::set<std::size_t> accounted;
    for (const auto id : result.retained) {
        if (id >= fixture.cloud.points.size() || !accounted.insert(id).second) return false;
    }
    for (const auto& certificate : result.removed) {
        if (certificate.removed >= fixture.cloud.points.size() ||
            !accounted.insert(certificate.removed).second ||
            !certificate.evidence.verifier.value.ends_with(
                "exact-binary64-convex-combination"))
            return false;
    }
    if (accounted.size() != fixture.cloud.points.size()) return false;
    const auto digest = geometry::digest_hull_input(fixture.cloud.points);
    if (!std::holds_alternative<geometry::HullInputDigest>(digest)) return false;
    const auto checked = geometry::check_source_index_hull(fixture.cloud.points,
        {std::get<geometry::HullInputDigest>(digest), result.retained});
    if (checked.status != geometry::HullCheckStatus::verified) return false;
    const auto [min_x, max_x] = std::minmax_element(fixture.expected_vertices.begin(),
        fixture.expected_vertices.end(), [](const Vector& a, const Vector& b) {
            return a[0] < b[0];
        });
    const auto min_y = std::min_element(fixture.expected_vertices.begin(),
        fixture.expected_vertices.end(), [](const Vector& a, const Vector& b) {
            return a[1] < b[1];
        });
    const auto max_y = std::max_element(fixture.expected_vertices.begin(),
        fixture.expected_vertices.end(), [](const Vector& a, const Vector& b) {
            return a[1] < b[1];
        });
    for (const auto& point : fixture.cloud.points)
        if (point[0] < (*min_x)[0] || point[0] > (*max_x)[0] ||
            point[1] < (*min_y)[1] || point[1] > (*max_y)[1]) return false;
    for (const auto& vertex : fixture.expected_vertices) {
        const auto found = std::find_if(result.retained.begin(), result.retained.end(),
            [&](std::size_t id) { return fixture.cloud.points[id] == vertex; });
        if (found == result.retained.end()) return false;
    }
    return true;
}

struct Outcome {
    bool passed{};
    long long elapsed_ns{};
    std::size_t retained{}, removed{}, lp_calls{}, basis_solves{}, bulk_removals{},
                ordered_candidates{};
    std::size_t a43_final_rechecks{}, a44_incremental_queries{}, a44_final_rechecks{};
};

Outcome run(const Fixture& fixture, Method method) {
    if (method == Method::quickhull) {
        const auto begin = std::chrono::steady_clock::now();
        auto result = geometry::quickhull_2d(fixture.cloud.points);
        const auto end = std::chrono::steady_clock::now();
        if (!std::holds_alternative<geometry::QuickHull2D>(result)) return {};
        const auto& hull = std::get<geometry::QuickHull2D>(result);
        std::vector<Vector> coordinates;
        for (const auto id : hull.vertex_indices) {
            if (id >= fixture.cloud.points.size()) return {};
            coordinates.push_back(fixture.cloud.points[id]);
        }
        std::sort(coordinates.begin(), coordinates.end());
        auto expected = fixture.expected_vertices;
        std::sort(expected.begin(), expected.end());
        const auto digest = geometry::digest_hull_input(fixture.cloud.points);
        const bool checked = std::holds_alternative<geometry::HullInputDigest>(digest) &&
            geometry::check_source_index_hull(fixture.cloud.points,
                {std::get<geometry::HullInputDigest>(digest), hull.vertex_indices}).status ==
                    geometry::HullCheckStatus::verified;
        return {coordinates == expected && checked,
            std::chrono::duration_cast<std::chrono::nanoseconds>(end-begin).count(),
            hull.vertex_indices.size(), 0, 0, 0, 0, 0};
    }

    auto lp = workspace(fixture.cloud);
    if (!lp) throw std::runtime_error("HiGHS workspace creation failed");
    const auto begin = std::chrono::steady_clock::now();
    geometry::HullReductionResult result;
    if (method == Method::lp_baseline)
        result = geometry::reduce_hull(fixture.cloud, *lp, {});
    else if (method == Method::basis_reuse)
        result = geometry::reduce_hull_basis_reuse(fixture.cloud, *lp, {});
    else if (method == Method::ordered_lp)
        result = geometry::reduce_ordered_hull(fixture.cloud, *lp, {});
    else if (method == Method::a43_safe)
        result = geometry::reduce_itis17_a43_hull(fixture.cloud, *lp, {});
    else
        result = geometry::reduce_itis17_a44_hull(fixture.cloud, *lp, {});
    const auto end = std::chrono::steady_clock::now();
    Outcome outcome;
    outcome.elapsed_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(end-begin).count();
    if (!std::holds_alternative<geometry::HullReduction>(result)) return outcome;
    const auto& reduction = std::get<geometry::HullReduction>(result);
    outcome.passed = valid_reduction(fixture, reduction);
    if (!outcome.passed) {
        std::cerr << "validation failure method=" << name(method)
                  << " status=" << static_cast<int>(reduction.status)
                  << " retained=" << reduction.retained.size()
                  << " removed=" << reduction.removed.size()
                  << " accounted=" << reduction.retained.size()+reduction.removed.size()
                  << " expected=" << fixture.cloud.points.size();
        for (const auto& certificate : reduction.removed)
            std::cerr << " verifier=" << certificate.evidence.verifier.value;
        std::cerr << '\n';
        for (const auto id : reduction.retained)
            std::cerr << " retained-point=" << id << ':' << fixture.cloud.points[id][0]
                      << ',' << fixture.cloud.points[id][1] << '\n';
    }
    outcome.retained = reduction.retained.size();
    outcome.removed = reduction.removed.size();
    outcome.lp_calls = reduction.lp_calls;
    if (reduction.basis_reuse) {
        outcome.basis_solves = reduction.basis_reuse->basis_solves;
        outcome.bulk_removals = reduction.basis_reuse->bulk_removals;
    }
    if (reduction.ordered) outcome.ordered_candidates = reduction.ordered->ordered_candidates;
    if (reduction.itis17_a43)
        outcome.a43_final_rechecks = reduction.itis17_a43->final_recheck_calls;
    if (reduction.itis17_a44) {
        outcome.a44_incremental_queries = reduction.itis17_a44->incremental_membership_calls;
        outcome.a44_final_rechecks = reduction.itis17_a44->final_recheck_calls;
    }
    return outcome;
}

void print(const Fixture& fixture, Method method, bool warmup, int round,
           const Outcome& outcome) {
    const auto digest = geometry::digest_hull_input(fixture.cloud.points);
    if (!std::holds_alternative<geometry::HullInputDigest>(digest))
        throw std::runtime_error("input digest could not be computed");
    std::cout << "{\"schema\":\"csl.it17-hull-paper-adaptation-row/1\",\"source_commit\":\""
              << CSL_SOURCE_COMMIT << "\",\"fixture\":\"" << fixture.id
              << "\",\"input_sha256\":\"" << problem::hex(std::get<geometry::HullInputDigest>(digest))
              << "\",\"method\":\"" << name(method) << "\",\"method_identity\":\""
              << identity(method) << "\",\"method_version\":\"1.0.0\",\"lp_provider\":\"HiGHS/1.11.0\",\"warmup\":"
              << (warmup ? "true" : "false") << ",\"round\":" << round
              << ",\"elapsed_ns\":" << outcome.elapsed_ns << ",\"passed\":"
              << (outcome.passed ? "true" : "false") << ",\"input_points\":"
              << fixture.cloud.points.size() << ",\"retained\":" << outcome.retained
              << ",\"removed\":" << outcome.removed << ",\"lp_calls\":"
              << outcome.lp_calls << ",\"basis_solves\":" << outcome.basis_solves
              << ",\"bulk_removals\":" << outcome.bulk_removals
              << ",\"ordered_candidates\":" << outcome.ordered_candidates
              << ",\"a43_final_rechecks\":" << outcome.a43_final_rechecks
              << ",\"a44_incremental_queries\":" << outcome.a44_incremental_queries
              << ",\"a44_final_rechecks\":" << outcome.a44_final_rechecks << "}\n";
}

} // namespace

int main(int argc, char** argv) {
    int repetitions = 7;
    if (argc == 3 && std::string(argv[1]) == "--measure")
        repetitions = std::stoi(argv[2]);
    else if (argc != 1) {
        std::cerr << "usage: csl_it17_hull_preliminary [--measure repetitions]\n";
        return 2;
    }
    if (repetitions < 1) return 2;
    try {
        const auto data = fixtures();
        for (const auto& fixture : data) for (const auto method : methods) {
            const auto result = run(fixture, method);
            print(fixture, method, true, 0, result);
            if (!result.passed) throw std::runtime_error("warmup oracle failed");
        }
        for (int round = 1; round <= repetitions; ++round) {
            for (std::size_t f = 0; f < data.size(); ++f) {
                for (std::size_t i = 0; i < methods.size(); ++i) {
                    const auto method = methods[(i + f + round - 1) % methods.size()];
                    const auto result = run(data[f], method);
                    print(data[f], method, false, round, result);
                    if (!result.passed) throw std::runtime_error("measured output oracle failed");
                }
            }
        }
    } catch (const std::exception& error) {
        std::cerr << "measurement failed: " << error.what() << '\n';
        return 1;
    }
    return 0;
}
