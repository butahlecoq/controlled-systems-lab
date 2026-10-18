#include <csl/adapters/lp/highs.hpp>
#include <csl/geometry/hull_reducer.hpp>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <limits>
#include <memory>
#include <string_view>
#include <stdexcept>
#include <string>
#include <variant>

namespace {
using namespace csl;
using Port = registry::HullReducerPort;
struct Fixture { const char* id; geometry::PointCloud cloud; };

std::vector<Fixture> fixtures() {
    Fixture signed_cloud{"signed-grid", {{"opt11-signed-grid"}, {}}};
    const std::vector<Vector> signed_base{{-4,-4},{-4,0},{-4,4},{0,-4},{0,4},{4,-4},{4,0},{4,4}};
    for (std::size_t i = 0; i < 33; ++i)
        signed_cloud.cloud.points.push_back(signed_base[(i * 3) % signed_base.size()]);
    Fixture collinear{"duplicate-collinear", {{"opt11-duplicate-collinear"}, {}}};
    for (int i = 0; i < 33; ++i) {
        const double x = i % 3 == 0 ? -16.0 : (i % 3 == 1 ? 0.0 : 16.0);
        collinear.cloud.points.push_back({x, 2.0 * x});
    }
    Fixture rank_one{"rank-one-offset", {{"opt11-rank-one-offset"}, {}}};
    for (int i = 0; i < 33; ++i) {
        const double x = i % 3 == 0 ? -8.0 : (i % 3 == 1 ? 0.0 : 8.0);
        rank_one.cloud.points.push_back({x, 3.0 * x + 2.0});
    }
    return {std::move(signed_cloud), std::move(collinear), std::move(rank_one)};
}

std::unique_ptr<LPWorkspace> make_lp(const registry::Registration<registry::LPPort>& adapter) {
    auto request = optimization::make_linear_program({{{"opt11-report"}, {"workspace-seed"}}, {}, 0,
        {0, 0, {0}, {}, {}}, {}, {}});
    if (!std::holds_alternative<LinearProgram>(request)) throw std::runtime_error("LP seed rejected");
    auto result = adapter.factory(std::get<LinearProgram>(request));
    if (!result) throw std::runtime_error("LP workspace factory returned null");
    return result;
}

std::unique_ptr<registry::BoundWorkspace<Port>> make_reducer(
        const registry::Registration<Port>& registration, const geometry::PointCloud& cloud) {
    registry::Registry<Port> registry;
    if (registry.add(registration)) throw std::runtime_error("reducer registration rejected");
    auto selection = registry::select(registry,
        registry::Method{registration.identity.id, registration.identity.version}, cloud);
    auto prepared = registry::prepare_pipeline(std::move(selection));
    if (!std::holds_alternative<registry::PreparedPipeline<Port>>(prepared))
        throw std::runtime_error("reducer preparation rejected");
    auto owned = std::get<registry::PreparedPipeline<Port>>(std::move(prepared)).create();
    return std::move(std::get<0>(owned));
}

template<class T> void nums(const T& values) {
    std::cout << '[';
    for (std::size_t i = 0; i < values.size(); ++i) { if (i) std::cout << ','; std::cout << values[i]; }
    std::cout << ']';
}
void json_string(std::string_view value) {
    std::cout << '"';
    for (const unsigned char ch : value) {
        switch (ch) {
        case '"': std::cout << "\\\""; break;
        case '\\': std::cout << "\\\\"; break;
        case '\b': std::cout << "\\b"; break;
        case '\f': std::cout << "\\f"; break;
        case '\n': std::cout << "\\n"; break;
        case '\r': std::cout << "\\r"; break;
        case '\t': std::cout << "\\t"; break;
        default:
            if (ch < 0x20) std::cout << "\\u00" << std::hex << std::setw(2)
                                     << std::setfill('0') << static_cast<int>(ch) << std::dec;
            else std::cout << ch;
        }
    }
    std::cout << '"';
}
void points(const geometry::PointCloud& cloud) {
    std::cout << '[';
    for (std::size_t i = 0; i < cloud.points.size(); ++i) {
        if (i) std::cout << ','; nums(cloud.points[i]);
    }
    std::cout << ']';
}
const char* status(const geometry::HullReductionResult& result) {
    if (!std::holds_alternative<geometry::HullReduction>(result)) return "diagnostics";
    return std::get<geometry::HullReduction>(result).status == geometry::ReductionStatus::complete ? "complete" : "incomplete";
}
const char* attempt_name(geometry::MembershipOutcome outcome) {
    using geometry::MembershipOutcome;
    switch (outcome) {
    case MembershipOutcome::feasible: return "feasible";
    case MembershipOutcome::infeasible: return "infeasible";
    case MembershipOutcome::unsupported: return "unsupported";
    case MembershipOutcome::stopped: return "stopped";
    case MembershipOutcome::numerical_failure: return "numerical_failure";
    case MembershipOutcome::malformed_result: return "malformed_result";
    }
    return "unknown";
}
void emit_call(const Fixture& f, int round, bool warmup, const char* purpose, const char* method, long long ns,
        const geometry::HullReductionResult& outcome) {
    std::cout << std::setprecision(17) << "{\"kind\":\"call\",\"purpose\":\"" << purpose << "\",\"fixture\":\""
        << f.id << "\",\"round\":" << round << ",\"warmup\":" << (warmup ? "true" : "false")
        << ",\"problem\":\"" << f.cloud.problem.value << "\",\"method\":\"" << method
        << "\",\"elapsed_ns\":" << ns << ",\"points\":";
    points(f.cloud);
    if (!std::holds_alternative<geometry::HullReduction>(outcome)) {
        std::cout << ",\"status\":\"diagnostics\",\"diagnostics\":[";
        const auto& diagnostics = std::get<Diagnostics>(outcome);
        for (std::size_t i = 0; i < diagnostics.size(); ++i) {
            if (i) std::cout << ',';
            std::cout << "{\"field\":";
            json_string(diagnostics[i].field);
            std::cout << ",\"explanation\":";
            json_string(diagnostics[i].explanation);
            std::cout << '}';
        }
        std::cout << "],\"retained\":[],\"removed\":[],\"lp_calls\":0,\"attempts\":[],\"recursive\":null}\n";
        return;
    }
    const auto& r = std::get<geometry::HullReduction>(outcome);
    std::cout << ",\"status\":\"" << status(outcome) << "\",\"retained\":"; nums(r.retained);
    std::cout << ",\"support\":[";
    const double directions[6][2] = {{1,0},{-1,0},{0,1},{0,-1},{1,1},{-1,-1}};
    for (std::size_t d = 0; d < 6; ++d) {
        if (d) std::cout << ',';
        double maximum = -std::numeric_limits<double>::infinity();
        for (const auto id : r.retained) {
            const auto& p = f.cloud.points[id];
            maximum = std::max(maximum, directions[d][0] * p[0] + directions[d][1] * p[1]);
        }
        std::cout << maximum;
    }
    std::cout << ']';
    std::cout << ",\"removed\":[";
    for (std::size_t i = 0; i < r.removed.size(); ++i) {
        if (i) std::cout << ',';
        const auto& cert = r.removed[i];
        std::cout << "{\"point\":" << cert.removed << ",\"program_problem\":\"" << cert.program.problem.value
                  << "\",\"program\":\"" << cert.program.program.value << "\",\"terms\":[";
        for (std::size_t j = 0; j < cert.combination.size(); ++j) {
            if (j) std::cout << ',';
            std::cout << '[' << cert.combination[j].point << ',' << cert.combination[j].weight << ']';
        }
        std::cout << "]}";
    }
    std::cout << "],\"lp_calls\":" << r.lp_calls << ",\"attempts\":[";
    for (std::size_t i = 0; i < r.attempts.size(); ++i) {
        if (i) std::cout << ',';
        std::cout << '[' << r.attempts[i].candidate << ",\"" << attempt_name(r.attempts[i].outcome) << "\"]";
    }
    std::cout << ']';
    if (r.recursive) {
        const auto& m = *r.recursive;
        std::cout << ",\"recursive\":{\"leaf_nodes\":" << m.leaf_nodes << ",\"merge_nodes\":" << m.merge_nodes
            << ",\"leaf_lp_calls\":" << m.leaf_lp_calls << ",\"merge_lp_calls\":" << m.merge_lp_calls
            << ",\"peak_merge_points\":" << m.peak_merge_points << ",\"concurrent_child_subtrees\":"
            << m.concurrent_child_subtrees << ",\"parallel_overhead_microseconds\":" << m.parallel_overhead_microseconds << '}';
    } else std::cout << ",\"recursive\":null";
    std::cout << "}\n";
}

void describe() {
#ifdef _MSVC_LANG
    constexpr long standard = _MSVC_LANG;
#else
    constexpr long standard = __cplusplus;
#endif
    auto lp_result = adapters::lp::make_highs_registration();
    if (!std::holds_alternative<registry::Registration<registry::LPPort>>(lp_result))
        throw std::runtime_error("HiGHS registration unavailable while describing executable");
    const auto& lp = std::get<registry::Registration<registry::LPPort>>(lp_result);
    std::cout << "{\"kind\":\"describe\",\"source_commit\":\"" << CSL_OPT11_SOURCE_COMMIT
        << "\",\"harness_sha256\":\"" << CSL_OPT11_HARNESS_SHA256 << "\",\"configuration\":\""
        << CSL_OPT11_CONFIG << "\",\"cxx_standard\":" << standard << ",\"ndebug\":"
#ifdef NDEBUG
        << "true";
#else
        << "false";
#endif
    std::cout << ",\"backend\":{\"method\":";
    json_string(lp.identity.id.value);
    std::cout << ",\"version\":";
    json_string(lp.identity.version);
    std::cout << "},\"warmups_per_fixture\":1,\"measured_pairs_per_fixture\":6}\n";
}

void measure(const char* purpose) {
    if (std::string(purpose) != "measurement" && std::string(purpose) != "smoke")
        throw std::runtime_error("purpose must be measurement or smoke");
    auto high_result = adapters::lp::make_highs_registration();
    if (!std::holds_alternative<registry::Registration<registry::LPPort>>(high_result))
        throw std::runtime_error("HiGHS registration rejected");
    auto lp_provider = std::get<registry::Registration<registry::LPPort>>(std::move(high_result));
    auto recursive_registration = geometry::make_recursive_hull_reducer_registration(lp_provider);
    auto baseline_registration = geometry::make_lp_hull_reducer_registration();
    auto all = fixtures();
    for (std::size_t fi = 0; fi < all.size(); ++fi) {
        const auto rounds = std::string(purpose) == "smoke" ? 1 : 7;
        for (int round = 0; round < rounds; ++round) {
            const bool warmup = round == 0;
            auto baseline = make_reducer(baseline_registration, all[fi].cloud);
            auto recursive = make_reducer(recursive_registration, all[fi].cloud);
            auto baseline_lp = make_lp(lp_provider);
            auto injected_lp = make_lp(lp_provider);
            ExecutionContext context;
            if (std::string(purpose) == "measurement")
                context.resources = std::make_shared<const ResourcePolicy>(ResourcePolicy{2, 2, 1, {}});
            auto run = [&](const char* method) {
                auto& reducer = std::string(method) == "baseline" ? baseline : recursive;
                auto& lp = std::string(method) == "baseline" ? baseline_lp : injected_lp;
                const auto started = std::chrono::steady_clock::now();
                geometry::HullReductionResult result = reducer->run_with(context, *lp);
                const auto ended = std::chrono::steady_clock::now();
                const auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(ended - started).count();
                emit_call(all[fi], round, warmup, purpose, method, ns, result);
            };
            const bool recursive_first = (round + static_cast<int>(fi)) % 2 == 1;
            if (recursive_first) { run("recursive"); run("baseline"); }
            else { run("baseline"); run("recursive"); }
            std::cout << "{\"kind\":\"pair\",\"purpose\":\"" << purpose << "\",\"fixture\":\""
                << all[fi].id << "\",\"round\":" << round << ",\"warmup\":" << (warmup ? "true" : "false")
                << ",\"recursive_first\":" << (recursive_first ? "true" : "false") << "}\n";
        }
    }
    std::cout.flush();
}
}

int main(int argc, char** argv) {
    try {
        if (argc == 2 && std::string(argv[1]) == "describe") describe();
        else if (argc == 3 && std::string(argv[1]) == "run") measure(argv[2]);
        else { std::cerr << "usage: csl_opt11_measure describe | run <smoke|measurement>\n"; return 2; }
        return 0;
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
