#include <csl/adapters/lp/highs.hpp>
#include <csl/geometry/hull_reducer.hpp>

#include <nlohmann/json.hpp>

#include <chrono>
#include <fstream>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <variant>

namespace {
using Json = nlohmann::json;
using Clock = std::chrono::steady_clock;

std::string compiler() {
#ifdef __VERSION__
    return __VERSION__;
#elif defined(_MSC_VER)
    return "MSVC-" + std::to_string(_MSC_VER);
#else
    return "unknown-cxx-compiler";
#endif
}

std::string operating_system() {
#ifdef _WIN32
    return "Windows";
#elif defined(__APPLE__)
    return "macOS";
#elif defined(__linux__)
    return "Linux";
#else
    return "unknown-os";
#endif
}

std::string architecture() {
#if defined(__x86_64__) || defined(_M_X64)
    return "x86_64";
#elif defined(__aarch64__) || defined(_M_ARM64)
    return "aarch64";
#else
    return "unknown-architecture";
#endif
}

std::unique_ptr<csl::LPWorkspace> make_lp(const csl::geometry::PointCloud& cloud,
        csl::registry::Registration<csl::registry::LPPort>& registration) {
    auto seed = csl::optimization::make_linear_program({{{cloud.problem.value}, {"exp06-lp-seed"}},
        {}, 0.0, {0,0,{0},{},{}}, {}, {}});
    if (!std::holds_alternative<csl::LinearProgram>(seed)) return {};
    auto adapter = csl::adapters::lp::make_highs_registration();
    if (!std::holds_alternative<csl::registry::Registration<csl::registry::LPPort>>(adapter)) return {};
    registration = std::get<csl::registry::Registration<csl::registry::LPPort>>(std::move(adapter));
    return registration.factory(std::get<csl::LinearProgram>(seed));
}

Json reduction_json(const csl::geometry::HullReduction& result) {
    Json payload{{"algorithm_status", result.status == csl::geometry::ReductionStatus::complete ?
        "completed" : "incomplete"}, {"lp_calls", result.lp_calls},
        {"retained_indices", result.retained}, {"removed_count", result.removed.size()}};
    for (const auto& certificate : result.removed)
        payload["certificates"].push_back({{"removed_index", certificate.removed},
            {"term_count", certificate.combination.size()},
            {"verifier", certificate.evidence.verifier.value}});
    if (result.itis17_a43_paper) {
        const auto& metrics = *result.itis17_a43_paper;
        payload["a43_paper_metrics"] = {{"candidate_solves", metrics.candidate_solves},
            {"phase_one_pivots", metrics.phase_one_pivots},
            {"largest_norm_tie_breaks", metrics.largest_norm_tie_breaks},
            {"basis_coordinate_checks", metrics.basis_coordinate_checks},
            {"certified_batch_removals", metrics.certified_batch_removals},
            {"final_recheck_calls", metrics.final_recheck_calls},
            {"largest_norm_tie_rule", metrics.largest_norm_tie_rule}};
    }
    if (result.itis17_a43) {
        const auto& metrics = *result.itis17_a43;
        payload["a43_adaptation_metrics"] = {{"final_recheck_calls", metrics.final_recheck_calls},
            {"largest_norm_tie_policy_applied", metrics.largest_norm_tie_policy_applied}};
    }
    if (result.itis17_a44) {
        const auto& metrics = *result.itis17_a44;
        payload["a44_metrics"] = {{"processing_order", metrics.processing_order},
            {"seeded_candidates", metrics.seeded_candidates},
            {"incremental_membership_calls", metrics.incremental_membership_calls},
            {"final_recheck_calls", metrics.final_recheck_calls},
            {"zero_width_coordinates", metrics.zero_width_coordinates},
            {"used_identity_fallback", metrics.used_identity_fallback}};
    }
    return payload;
}

csl::geometry::HullReductionResult run_method(const std::string& method,
        const csl::geometry::PointCloud& cloud, csl::LPWorkspace& lp) {
    using namespace csl::geometry;
    if (method == "csl.hull.itis17.a43-certified-basis-reuse")
        return reduce_itis17_a43_hull(cloud, lp, {});
    if (method == "csl.hull.itis17.a43-artificial-basis")
        return reduce_itis17_a43_paper_hull(cloud, lp, {}, A43PivotRule::phase_one_order);
    if (method == "csl.hull.itis17.a43-largest-norm-tie")
        return reduce_itis17_a43_paper_hull(cloud, lp, {}, A43PivotRule::largest_norm_tie);
    if (method == "csl.hull.itis17.a44-incremental-lp")
        return reduce_itis17_a44_hull(cloud, lp, {});
    throw std::invalid_argument("unknown EXP-06 LP reducer identity");
}
} // namespace

int main(int argc, char** argv) {
    try {
        if (argc != 5 || std::string(argv[1]) != "--run" || std::string(argv[3]) != "--method")
            throw std::invalid_argument("usage: csl_exp06_lp_reducer --run FIXTURE.json --method METHOD_ID");
        std::ifstream input(argv[2], std::ios::binary);
        if (!input) throw std::runtime_error("could not open fixture");
        const auto fixture = Json::parse(input);
        if (fixture.at("schema") != "csl.geometry-hull-input/1" || !fixture.at("points").is_array() ||
            fixture.at("points").empty() || fixture.at("points").size() > 64)
            throw std::invalid_argument("fixture schema or point count is invalid");
        std::vector<csl::Vector> points;
        for (const auto& row : fixture.at("points")) {
            if (!row.is_array() || row.size() != 2)
                throw std::invalid_argument("fixture must contain 2D point rows");
            points.push_back({row[0].get<double>(), row[1].get<double>()});
        }
        const csl::geometry::PointCloud cloud{{fixture.at("fixture_id").get<std::string>()}, points};
        csl::registry::Registration<csl::registry::LPPort> registration;
        auto workspace = make_lp(cloud, registration);
        if (!workspace) throw std::runtime_error("HiGHS LP workspace creation failed");
        const std::string method = argv[4];
        const auto begin = Clock::now();
        auto result = run_method(method, cloud, *workspace);
        const auto end = Clock::now();
        const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(end - begin).count();
        if (const auto* reduction = std::get_if<csl::geometry::HullReduction>(&result)) {
            std::cout << Json{{"schema", "csl.exp06-lp-reducer-result/1"},
                {"duration_ns", elapsed}, {"method", method}, {"status", "completed"},
                {"runtime", {{"language", "C++"}, {"implementation", method}, {"version", "1"},
                    {"compiler", compiler()}, {"os", operating_system()},
                    {"architecture", architecture()}, {"build_type",
#ifdef NDEBUG
                        "Release"
#else
                        "Debug"
#endif
                }}}, {"lp_provider", {{"id", registration.identity.id.value},
                    {"version", registration.identity.version}}},
                {"reduction", reduction_json(*reduction)}}.dump() << '\n';
            return 0;
        }
        const auto& diagnostics = std::get<csl::Diagnostics>(result);
        Json diagnostic_rows = Json::array();
        for (const auto& diagnostic : diagnostics)
            diagnostic_rows.push_back({{"code", static_cast<int>(diagnostic.code)},
                {"field", diagnostic.field}, {"explanation", diagnostic.explanation}});
        std::cout << Json{{"schema", "csl.exp06-lp-reducer-result/1"},
            {"duration_ns", elapsed}, {"method", method}, {"status", "failed"},
            {"diagnostics", std::move(diagnostic_rows)}}.dump() << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 2;
    }
}
