#include <csl/adapters/lp/highs.hpp>
#include <csl/geometry/basis_reuse_reducer.hpp>
#include <csl/geometry/bounded_hull_checker.hpp>
#include <csl/geometry/hull_reducer.hpp>
#include <csl/geometry/quickhull_2d.hpp>

#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <memory>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <variant>

using namespace csl;

namespace {

enum class Method { quickhull, lp_baseline, basis_reuse, ordered_lp, a43_safe, a44_incremental };
struct MethodInfo {
    Method method;
    const char* name;
    const char* identity;
    const char* version;
};

constexpr std::array<MethodInfo, 6> method_info{{
    {Method::quickhull, "geometric-quickhull", "csl.geometry.quickhull-2d", "1.0.0"},
    {Method::lp_baseline, "lp-membership-baseline", "csl.hull.lp-membership", "1.0.0"},
    {Method::basis_reuse, "basis-reuse-related-to-A43", "csl.hull.phase-one-basis-bulk", "1.0.0"},
    {Method::ordered_lp, "ordered-membership-related-to-A44", "csl.hull.ordered-membership", "1.0.0"},
    {Method::a43_safe, "A43-certificate-safe-basis-adaptation",
        "csl.hull.itis17.a43-certified-basis-reuse", "1.0.0"},
    {Method::a44_incremental, "A44-incremental-LP-farthest-seed",
        "csl.hull.itis17.a44-incremental-lp", "2.0.0"},
}};
constexpr std::array<Method, method_info.size()> methods{
    Method::quickhull, Method::lp_baseline, Method::basis_reuse,
    Method::ordered_lp, Method::a43_safe, Method::a44_incremental};

const MethodInfo& info(Method method) {
    const auto found = std::find_if(method_info.begin(), method_info.end(),
        [method](const MethodInfo& entry) { return entry.method == method; });
    if (found == method_info.end()) throw std::invalid_argument("unknown hull method");
    return *found;
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

double halton(std::uint64_t index, std::uint32_t base) {
    double value=0.0;
    double fraction=1.0/static_cast<double>(base);
    while(index) {
        value+=static_cast<double>(index%base)*fraction;
        index/=base;
        fraction/=static_cast<double>(base);
    }
    return value;
}

Fixture halton_square(std::size_t count) {
    if(count<4)throw std::invalid_argument("Halton square needs at least four points");
    geometry::PointCloud cloud{{"it17-halton-square-n"+std::to_string(count)},
        {{0,0},{1,0},{1,1},{0,1}}};
    cloud.points.reserve(count);
    for(std::uint64_t index=1;cloud.points.size()<count;++index)
        cloud.points.push_back({halton(index,2),halton(index,3)});
    return {"halton-square-n"+std::to_string(count),std::move(cloud),
        {{0,0},{1,0},{1,1},{0,1}}};
}

Fixture dyadic_interior_square(std::size_t count) {
    if (count < 4 || count > 900)
        throw std::invalid_argument("dyadic square needs 4..900 points");
    geometry::PointCloud cloud{{"it17-dyadic-square-n" + std::to_string(count)},
        {{0,0},{1,0},{1,1},{0,1}}};
    cloud.points.reserve(count);
    std::set<std::pair<std::uint32_t, std::uint32_t>> used;
    std::uint32_t state = UINT32_C(0x6d2b79f5);
    while (cloud.points.size() < count) {
        state = state * UINT32_C(1664525) + UINT32_C(1013904223);
        const auto x = UINT32_C(1) + state % UINT32_C(31);
        state = state * UINT32_C(1664525) + UINT32_C(1013904223);
        const auto y = UINT32_C(1) + state % UINT32_C(31);
        if (used.emplace(x, y).second)
            cloud.points.push_back({static_cast<double>(x) / 32.0,
                                    static_cast<double>(y) / 32.0});
    }
    return {"dyadic-square-n" + std::to_string(count), std::move(cloud),
        {{0,0},{1,0},{1,1},{0,1}}};
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

struct Outcome {
    bool passed{}; // accounting, expected vertices and independent exact hull check passed
    std::optional<bool> reducer_status_complete;
    long long elapsed_ns{};
    std::size_t retained{}, removed{}, lp_calls{}, basis_solves{}, bulk_removals{},
                ordered_candidates{};
    std::size_t a43_final_rechecks{}, a44_incremental_queries{}, a44_final_rechecks{};
    bool accounting_valid{};
    bool expected_vertices_retained{};
    std::optional<geometry::HullCheckRecord> checker;
};

geometry::HullCheckRecord check_hull(const Fixture& fixture,
                                     const std::vector<std::size_t>& retained) {
    const auto digest = geometry::digest_hull_input(fixture.cloud.points);
    if (!std::holds_alternative<geometry::HullInputDigest>(digest)) {
        geometry::HullCheckRecord record;
        record.reason = "input digest could not be computed";
        record.budget.max_points = fixture.cloud.points.size();
        return record;
    }
    return geometry::check_source_index_hull(fixture.cloud.points,
        {std::get<geometry::HullInputDigest>(digest), retained},
        {std::chrono::seconds{5}, fixture.cloud.points.size()});
}

bool expected_vertices_present(const Fixture& fixture,
                               const std::vector<std::size_t>& retained) {
    for (const auto& vertex : fixture.expected_vertices) {
        if (std::none_of(retained.begin(), retained.end(), [&](std::size_t id) {
                return id < fixture.cloud.points.size() && fixture.cloud.points[id] == vertex;
            })) return false;
    }
    return true;
}

bool accounting_valid(const Fixture& fixture, const geometry::HullReduction& result) {
    if (result.retained.empty() || result.retained.size() + result.removed.size() !=
                                   fixture.cloud.points.size()) return false;
    std::set<std::size_t> accounted;
    for (const auto id : result.retained) {
        if (id >= fixture.cloud.points.size() || !accounted.insert(id).second) return false;
    }
    for (const auto& certificate : result.removed) {
        if (certificate.removed >= fixture.cloud.points.size() ||
            !accounted.insert(certificate.removed).second ||
            !certificate.evidence.verifier.value.ends_with(
                "exact-binary64-convex-combination")) return false;
    }
    return accounted.size() == fixture.cloud.points.size();
}

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
        const auto checker = check_hull(fixture, hull.vertex_indices);
        const bool checked = checker.status == geometry::HullCheckStatus::verified;
        if (coordinates != expected || !checked) {
            std::cerr << "quickhull validation failure coordinates=" << coordinates.size()
                      << " expected=" << expected.size() << " checked=" << checked << '\n';
            for (const auto& point : coordinates)
                std::cerr << " quickhull-point=" << point[0] << ',' << point[1] << '\n';
        }
        Outcome outcome;
        outcome.passed = coordinates == expected && checked;
        outcome.elapsed_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(end-begin).count();
        outcome.retained = hull.vertex_indices.size();
        outcome.removed = fixture.cloud.points.size()-hull.vertex_indices.size();
        outcome.accounting_valid = hull.vertex_indices.size() + outcome.removed ==
                                   fixture.cloud.points.size();
        outcome.expected_vertices_retained = coordinates == expected;
        outcome.checker = checker;
        return outcome;
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
    outcome.accounting_valid = accounting_valid(fixture, reduction);
    outcome.expected_vertices_retained = expected_vertices_present(fixture, reduction.retained);
    outcome.checker = check_hull(fixture, reduction.retained);
    outcome.passed = outcome.accounting_valid && outcome.expected_vertices_retained &&
        outcome.checker->status == geometry::HullCheckStatus::verified;
    outcome.reducer_status_complete = reduction.status == geometry::ReductionStatus::complete;
    if (!outcome.passed) {
        std::cerr << "validation failure method=" << info(method).name
                  << " status=" << static_cast<int>(reduction.status)
                  << " retained=" << reduction.retained.size()
                  << " removed=" << reduction.removed.size()
                  << " accounted=" << reduction.retained.size()+reduction.removed.size()
                  << " expected=" << fixture.cloud.points.size();
        for (const auto& certificate : reduction.removed)
            std::cerr << " verifier=" << certificate.evidence.verifier.value;
        std::cerr << '\n';
        std::size_t shown = 0;
        for (const auto id : reduction.retained) {
            if (shown++ == 16) { std::cerr << " retained-point=...\n"; break; }
            std::cerr << " retained-point=" << id << ':' << fixture.cloud.points[id][0]
                      << ',' << fixture.cloud.points[id][1] << '\n';
        }
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
    std::cout << "{\"schema\":\"csl.it17-hull-paper-adaptation-row/4\",\"source_commit\":\""
              << CSL_SOURCE_COMMIT << "\",\"fixture\":\"" << fixture.id
              << "\",\"input_sha256\":\"" << problem::hex(std::get<geometry::HullInputDigest>(digest))
              << "\",\"method\":\"" << info(method).name << "\",\"method_identity\":\""
              << info(method).identity << "\",\"method_version\":\"" << info(method).version
              << "\",\"lp_provider\":\"HiGHS/1.11.0\",\"warmup\":"
              << (warmup ? "true" : "false") << ",\"round\":" << round
              << ",\"reducer_status_complete\":";
    if (outcome.reducer_status_complete)
        std::cout << (*outcome.reducer_status_complete ? "true" : "false");
    else
        std::cout << "null";
    std::cout
              << ",\"elapsed_ns\":" << outcome.elapsed_ns << ",\"passed\":"
              << (outcome.passed ? "true" : "false") << ",\"input_points\":"
              << fixture.cloud.points.size() << ",\"retained\":" << outcome.retained
              << ",\"removed\":" << outcome.removed << ",\"lp_calls\":"
              << outcome.lp_calls << ",\"basis_solves\":" << outcome.basis_solves
              << ",\"bulk_removals\":" << outcome.bulk_removals
              << ",\"ordered_candidates\":" << outcome.ordered_candidates
              << ",\"a43_final_rechecks\":" << outcome.a43_final_rechecks
              << ",\"a44_incremental_queries\":" << outcome.a44_incremental_queries
              << ",\"a44_final_rechecks\":" << outcome.a44_final_rechecks
              << ",\"accounting_valid\":" << (outcome.accounting_valid ? "true" : "false")
              << ",\"expected_vertices_retained\":"
              << (outcome.expected_vertices_retained ? "true" : "false")
              << ",\"checker\":";
    if (!outcome.checker) {
        std::cout << "null";
    } else {
        const auto& checker = *outcome.checker;
        const char* status = checker.status == geometry::HullCheckStatus::verified ? "verified" :
            checker.status == geometry::HullCheckStatus::incorrect ? "incorrect" : "inconclusive";
        std::cout << "{\"status\":\"" << status << "\",\"elapsed_ns\":"
                  << checker.elapsed.count() << ",\"budget_wall_ns\":"
                  << std::chrono::duration_cast<std::chrono::nanoseconds>(checker.budget.wall).count()
                  << ",\"budget_max_points\":" << checker.budget.max_points
                  << ",\"evidence_scope\":\"" << checker.evidence_scope
                  << "\",\"reason\":\"" << checker.reason << "\",\"counterexample_index\":";
        if (checker.counterexample_index) std::cout << *checker.counterexample_index;
        else std::cout << "null";
        std::cout << "}";
    }
    std::cout << "}\n" << std::flush;
}

} // namespace

int main(int argc, char** argv) {
    int repetitions = 7;
    int first_round = 1;
    std::optional<std::size_t> ladder_size;
    std::optional<std::size_t> dyadic_size;
    for(int i=1;i<argc;++i) {
        const std::string argument{argv[i]};
        if(argument=="--measure"&&i+1<argc)repetitions=std::stoi(argv[++i]);
        else if(argument=="--from-round"&&i+1<argc)first_round=std::stoi(argv[++i]);
        else if(argument=="--ladder-size"&&i+1<argc)ladder_size=std::stoull(argv[++i]);
        else if(argument=="--dyadic-size"&&i+1<argc)dyadic_size=std::stoull(argv[++i]);
        else {
            std::cerr << "usage: csl_it17_hull_preliminary [--measure repetitions] [--from-round N] [--ladder-size 250|1000|5000] [--dyadic-size 4..900]\n";
            return 2;
        }
    }
    if (repetitions < 1 || first_round < 1 || first_round > repetitions ||
        (ladder_size && dyadic_size) ||
        (ladder_size&&*ladder_size!=250&&*ladder_size!=1000&&*ladder_size!=5000)) return 2;
    try {
        auto data=ladder_size?std::vector<Fixture>{halton_square(*ladder_size)}:
            dyadic_size?std::vector<Fixture>{dyadic_interior_square(*dyadic_size)}:fixtures();
        if (first_round == 1) {
            for (const auto& fixture : data) for (const auto method : methods) {
                const auto result = run(fixture, method);
                print(fixture, method, true, 0, result);
            }
        }
        for (int round = first_round; round <= repetitions; ++round) {
            for (std::size_t f = 0; f < data.size(); ++f) {
                for (std::size_t i = 0; i < methods.size(); ++i) {
                    const auto method = methods[(i + f + round - 1) % methods.size()];
                    const auto result = run(data[f], method);
                    print(data[f], method, false, round, result);
                }
            }
        }
    } catch (const std::exception& error) {
        std::cerr << "measurement failed: " << error.what() << '\n';
        return 1;
    }
    return 0;
}
