#include <csl/adapters/lp/highs.hpp>
#include <csl/geometry/basis_reuse_reducer.hpp>
#include <csl/geometry/bounded_hull_checker.hpp>
#include <csl/geometry/hull_reducer.hpp>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string>
#include <variant>
#include <vector>

using namespace csl;
namespace {

enum class Method { baseline, basis_reuse, ordered, a43, a44, quickhull_unsupported };
struct MethodInfo { Method method; const char* name; const char* identity; const char* version; };
constexpr std::array<MethodInfo, 6> methods{{
    {Method::baseline, "lp-membership-baseline", "csl.hull.lp-membership", "1.0.0"},
    {Method::basis_reuse, "basis-reuse-related-to-A43", "csl.hull.phase-one-basis-bulk", "1.0.0"},
    {Method::ordered, "ordered-membership-related-to-A44", "csl.hull.ordered-membership", "1.0.0"},
    {Method::a43, "A43-certificate-safe-basis-adaptation", "csl.hull.itis17.a43-certified-basis-reuse", "1.0.0"},
    {Method::a44, "A44-incremental-LP-farthest-seed", "csl.hull.itis17.a44-incremental-lp", "2.0.0"},
    {Method::quickhull_unsupported, "geometric-quickhull", "csl.geometry.quickhull-2d", "1.0.0"},
}};
constexpr std::array<Method, 5> lp_methods{
    Method::baseline, Method::basis_reuse, Method::ordered, Method::a43, Method::a44};

const MethodInfo& info(Method method) {
    const auto found = std::find_if(methods.begin(), methods.end(),
        [method](const auto& item) { return item.method == method; });
    if (found == methods.end()) throw std::invalid_argument("unknown method");
    return *found;
}

double halton(std::uint64_t index, std::uint32_t base) {
    double value = 0.0;
    double fraction = 1.0 / static_cast<double>(base);
    while (index) {
        value += static_cast<double>(index % base) * fraction;
        index /= base;
        fraction /= static_cast<double>(base);
    }
    return value;
}

geometry::PointCloud fixture() {
    geometry::PointCloud cloud{{"exp02-simplex-halton-interior-3d-n250"},
        {{0, 0, 0}, {1, 0, 0}, {0, 1, 0}, {0, 0, 1}}};
    cloud.points.reserve(250);
    for (std::uint64_t index = 1; cloud.points.size() < 250; ++index) {
        const auto w1 = 1U + static_cast<std::uint32_t>(std::floor(5.0 * halton(index, 2)));
        const auto w2 = 1U + static_cast<std::uint32_t>(std::floor(5.0 * halton(index, 3)));
        const auto w3 = 1U + static_cast<std::uint32_t>(std::floor(5.0 * halton(index, 5)));
        if (w1 + w2 + w3 > 7U) continue;
        cloud.points.push_back({static_cast<double>(w1) / 8.0,
                                static_cast<double>(w2) / 8.0,
                                static_cast<double>(w3) / 8.0});
    }
    return cloud;
}

std::unique_ptr<LPWorkspace> workspace(const geometry::PointCloud& cloud) {
    auto registration = adapters::lp::make_highs_registration();
    if (!std::holds_alternative<registry::Registration<registry::LPPort>>(registration)) return {};
    auto adapter = std::get<registry::Registration<registry::LPPort>>(std::move(registration));
    auto seed = optimization::make_linear_program({{{cloud.problem.value}, {"seed"}}, {}, 0,
        {0, 0, {0}, {}, {}}, {}, {}});
    if (!std::holds_alternative<LinearProgram>(seed)) return {};
    return adapter.factory(std::get<LinearProgram>(seed));
}

struct Outcome {
    std::string outcome{"failed"};
    std::optional<bool> reducer_complete;
    long long elapsed_ns{};
    std::size_t retained{}, removed{}, lp_calls{};
    std::vector<std::size_t> retained_ids;
    std::vector<geometry::RemovalCertificate> certificates;
};

Outcome run(const geometry::PointCloud& cloud, Method method) {
    if (method == Method::quickhull_unsupported)
        return {"unsupported_dimension", {}, 0, 0, 0, 0, {}, {}};
    auto lp = workspace(cloud);
    if (!lp) throw std::runtime_error("HiGHS workspace creation failed");
    const auto begin = std::chrono::steady_clock::now();
    geometry::HullReductionResult result;
    switch (method) {
    case Method::baseline: result = geometry::reduce_hull(cloud, *lp, {}); break;
    case Method::basis_reuse: result = geometry::reduce_hull_basis_reuse(cloud, *lp, {}); break;
    case Method::ordered: result = geometry::reduce_ordered_hull(cloud, *lp, {}); break;
    case Method::a43: result = geometry::reduce_itis17_a43_hull(cloud, *lp, {}); break;
    case Method::a44: result = geometry::reduce_itis17_a44_hull(cloud, *lp, {}); break;
    case Method::quickhull_unsupported: break;
    }
    const auto end = std::chrono::steady_clock::now();
    Outcome out;
    out.elapsed_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(end - begin).count();
    if (!std::holds_alternative<geometry::HullReduction>(result)) {
        out.outcome = "diagnostics";
        return out;
    }
    const auto& reduction = std::get<geometry::HullReduction>(result);
    out.reducer_complete = reduction.status == geometry::ReductionStatus::complete;
    out.retained = reduction.retained.size();
    out.removed = reduction.removed.size();
    out.lp_calls = reduction.lp_calls;
    out.retained_ids = reduction.retained;
    out.certificates = reduction.removed;
    out.outcome = "reducer_returned";
    return out;
}

void print(const geometry::PointCloud& cloud, Method method, bool warmup, int round,
           const Outcome& outcome) {
    const auto digest = geometry::digest_hull_input(cloud.points);
    if (!std::holds_alternative<geometry::HullInputDigest>(digest))
        throw std::runtime_error("input digest could not be computed");
    std::cout << "{\"schema\":\"csl.exp02-hull-3d-row/1\",\"source_commit\":\""
              << CSL_SOURCE_COMMIT << "\",\"fixture\":\"exp02-simplex-halton-interior-3d-n250\",\"dimension\":3"
              << ",\"input_points\":" << cloud.points.size() << ",\"input_sha256\":\""
              << problem::hex(std::get<geometry::HullInputDigest>(digest))
              << "\",\"method\":\"" << info(method).name << "\",\"method_identity\":\""
              << info(method).identity << "\",\"method_version\":\"" << info(method).version
              << "\",\"lp_provider\":\"HiGHS/1.11.0\",\"warmup\":"
              << (warmup ? "true" : "false") << ",\"round\":" << round
              << ",\"outcome\":\"" << outcome.outcome << "\",\"reducer_status_complete\":";
    if (outcome.reducer_complete) std::cout << (*outcome.reducer_complete ? "true" : "false");
    else std::cout << "null";
    std::cout << ",\"elapsed_ns\":" << outcome.elapsed_ns << ",\"retained\":" << outcome.retained
              << ",\"removed\":" << outcome.removed << ",\"lp_calls\":" << outcome.lp_calls
              << ",\"retained_ids\":[";
    bool first = true;
    for (const auto id : outcome.retained_ids) {
        if (!first) std::cout << ',';
        first = false;
        std::cout << id;
    }
    std::cout << "],\"removal_certificates\":[";
    for (std::size_t i = 0; i < outcome.certificates.size(); ++i) {
        if (i) std::cout << ',';
        const auto& certificate = outcome.certificates[i];
        std::cout << "{\"removed\":" << certificate.removed << ",\"terms\":[";
        for (std::size_t j = 0; j < certificate.combination.size(); ++j) {
            if (j) std::cout << ',';
            const auto& term = certificate.combination[j];
            std::cout << "[" << term.point << ",\"" << std::hexfloat << term.weight
                      << std::defaultfloat << "\"]";
        }
        std::cout << "]}";
    }
    std::cout << "]}\n" << std::flush;
}

} // namespace

int main(int argc, char** argv) {
    int repetitions = 5;
    int first_round = 1;
    for (int i = 1; i < argc; ++i) {
        const std::string arg{argv[i]};
        if (arg == "--measure" && i + 1 < argc) repetitions = std::stoi(argv[++i]);
        else if (arg == "--from-round" && i + 1 < argc) first_round = std::stoi(argv[++i]);
        else {
            std::cerr << "usage: csl_it17_hull_3d_report [--measure repetitions] [--from-round N]\n";
            return 2;
        }
    }
    if (repetitions < 1 || first_round < 1 || first_round > repetitions) return 2;
    const auto cloud = fixture();
    try {
        for (const auto method : lp_methods) {
            const auto result = run(cloud, method);
            print(cloud, method, true, 0, result);
        }
        const auto unsupported = run(cloud, Method::quickhull_unsupported);
        print(cloud, Method::quickhull_unsupported, true, 0, unsupported);
        for (int round = first_round; round <= repetitions; ++round) {
            for (std::size_t i = 0; i < lp_methods.size(); ++i) {
                const auto method = lp_methods[(i + static_cast<std::size_t>(round - 1)) % lp_methods.size()];
                const auto result = run(cloud, method);
                print(cloud, method, false, round, result);
            }
            print(cloud, Method::quickhull_unsupported, false, round, unsupported);
        }
    } catch (const std::exception& error) {
        std::cerr << "benchmark attempt failed: " << error.what() << '\n';
        return 1;
    }
}
