#include <csl/geometry/legacy_btulshor.hpp>
#include <csl/geometry/quickhull_2d.hpp>
#include <csl/geometry/hull_reducer.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <csl/registry/provider.hpp>

#include <nlohmann/json.hpp>

#include <fstream>
#include <chrono>
#include <algorithm>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <variant>

namespace {
using Json = nlohmann::json;
using namespace csl::geometry::legacy_btulshor;

std::vector<csl::Vector> vectors(const Json& rows) {
    if (!rows.is_array()) throw std::invalid_argument("expected an array of vectors");
    std::vector<csl::Vector> result;
    for (const auto& row : rows) {
        if (!row.is_array()) throw std::invalid_argument("vector must be an array");
        result.emplace_back(row.get<csl::Vector>());
    }
    return result;
}

Json vector_json(const csl::Vector& values) { return Json(values); }
Json points_json(const std::vector<csl::Vector>& points) {
    Json out = Json::array();
    for (const auto& point : points) out.push_back(vector_json(point));
    return out;
}

std::string stop_name(StopReason reason) {
    switch (reason) {
    case StopReason::invalid_input: return "invalid_input";
    case StopReason::capacity_limit: return "capacity_limit";
    case StopReason::pivot_limit: return "pivot_limit";
    case StopReason::non_finite_arithmetic: return "non_finite_arithmetic";
    case StopReason::invalid_dependency_result: return "invalid_dependency_result";
    case StopReason::cancelled: return "cancelled";
    case StopReason::deadline_expired: return "deadline_expired";
    }
    return "unknown";
}

std::string membership_name(csl::geometry::MembershipOutcome outcome) {
    using csl::geometry::MembershipOutcome;
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

Json modif_json(const Json& input) {
    const auto rows = input.at("rows").get<std::size_t>();
    const auto cols = input.at("cols").get<std::size_t>();
    const auto& flat = input.at("a");
    if (flat.size() != rows * cols) throw std::invalid_argument("a length must equal rows*cols");
    csl::Vector values;
    values.reserve(flat.size());
    for (const auto& value : flat) values.push_back(value.get<double>());
    csl::Matrix a{rows, cols, std::move(values)};
    ModifRequest request{std::move(a), input.at("x").get<csl::Vector>(),
        input.value("epsilon", 1e-5), input.value("initial_status", 0)};
    auto output = modif(request);
    Json result{{"schema", "csl.btulshor-raw-case/1"}, {"case_id", input.value("id", "unnamed")},
        {"operation", "modif"}, {"method_id", "csl.legacy.btulshor.modif.source-v1"}};
    if (auto* value = std::get_if<ModifResult>(&output)) {
        result.update({{"status", "completed"}, {"original_status", value->original_status},
            {"x", vector_json(value->x)}, {"basis", value->basis}, {"pivot_count", value->pivots}});
    } else {
        const auto& stopped = std::get<Stopped>(output);
        result.update({{"status", "stopped"}, {"stop_reason", stop_name(stopped.reason)},
            {"message", stopped.message}});
    }
    return result;
}

Json kpabep_json(const Json& input) {
    const auto points = vectors(input.at("points"));
    auto output = kpabep(points);
    Json result{{"schema", "csl.btulshor-raw-case/1"}, {"case_id", input.value("id", "unnamed")},
        {"operation", "kpabep"}, {"method_id", "csl.legacy.btulshor.kpabep.source-v1"},
        {"input_count", points.size()}};
    if (auto* value = std::get_if<KpabepResult>(&output)) {
        Json trace = Json::array();
        for (const auto& item : value->candidate_trace)
            trace.push_back({{"candidate_index", item.candidate_index},
                {"original_status", item.original_status}, {"pivot_count", item.pivots}});
        result.update({{"status", "completed"}, {"points", points_json(value->points)},
            {"retained_indices", value->retained_indices}, {"retained_count", value->points.size()},
            {"modif_calls", value->modif_calls}, {"pivot_count", value->pivots},
            {"candidate_trace", trace}, {"trace_truncated", value->trace_truncated}});
    } else {
        const auto& stopped = std::get<Stopped>(output);
        result.update({{"status", "stopped"}, {"stop_reason", stop_name(stopped.reason)},
            {"message", stopped.message}});
    }
    return result;
}

Json reach_json(const Json& input) {
    const auto matrix = [](const Json& rows) {
        if (!rows.is_array()) throw std::invalid_argument("matrix must be an array of rows");
        const std::size_t row_count = rows.size();
        const std::size_t col_count = row_count == 0 ? 0 : rows.at(0).size();
        csl::Vector values;
        for (const auto& row : rows) {
            if (!row.is_array() || row.size() != col_count)
                throw std::invalid_argument("matrix rows must have equal lengths");
            for (const auto& value : row) values.push_back(value.get<double>());
        }
        return csl::Matrix{row_count, col_count, std::move(values)};
    };
    ReachRequest request{matrix(input.at("a")), matrix(input.at("b")),
        vectors(input.at("initial_points")), vectors(input.at("control_points"))};
    auto output = reach(request);
    Json result{{"schema", "csl.btulshor-raw-case/1"}, {"case_id", input.value("id", "unnamed")},
        {"operation", "reach"}, {"method_id", "csl.legacy.btulshor.reach.source-v1"}};
    if (auto* value = std::get_if<ReachResult>(&output)) {
        Json sources = Json::array();
        for (const auto& source : value->source_vertices)
            sources.push_back({source.initial_point_index, source.control_point_index});
        result.update({{"status", "completed"}, {"points", points_json(value->points)},
            {"source_vertices", sources}, {"point_count", value->points.size()},
            {"kpabep_calls", value->kpabep_calls}, {"modif_calls", value->modif_calls},
            {"pivot_count", value->pivots}});
    } else {
        const auto& stopped = std::get<Stopped>(output);
        result.update({{"status", "stopped"}, {"stop_reason", stop_name(stopped.reason)},
            {"message", stopped.message}});
    }
    return result;
}

Json run_case(const Json& input) {
    const std::string operation = input.at("operation").get<std::string>();
    if (operation == "modif") return modif_json(input);
    if (operation == "kpabep") return kpabep_json(input);
    if (operation == "reach") return reach_json(input);
    throw std::invalid_argument("operation must be modif, kpabep, or reach");
}

Json comparison(const Json& fixture) {
    Json input = fixture;
    if (!input.contains("points")) {
        const auto id = input.value("fixture_id", std::string("square-interior"));
        static const std::map<std::string, std::vector<csl::Vector>> fixtures{
            {"square", {{0,0},{2,0},{2,2},{0,2}}},
            {"interior", {{0,0},{2,0},{2,2},{0,2},{1,1}}},
            {"edge", {{0,0},{2,0},{2,2},{0,2},{1,0}}},
            {"duplicate", {{0,0},{2,0},{2,2},{0,2},{0,0}}},
            {"seeded-cloud", {{-3,1},{-2,-2},{0,-3},{3,-1},{4,2},{2,4},{-1,3},{0,0},{1,1}}},
            {"near-tolerance", {{0,0},{1,0},{1,1},{0,1},{.5,1.00000001}}},
            {"simplex-3d", {{0,0,0},{1,0,0},{0,1,0},{0,0,1},{.1,.1,.1}}},
            {"simplex-4d", {{0,0,0,0},{1,0,0,0},{0,1,0,0},{0,0,1,0},{0,0,0,1},{.1,.1,.1,.1}}}
        };
        const auto found = fixtures.find(id);
        if (found == fixtures.end()) throw std::invalid_argument("unknown deterministic fixture_id");
        input["points"] = points_json(found->second);
    }
    input["operation"] = "kpabep";
    const auto points = vectors(input.at("points"));
    Json result{{"schema", "csl.btulshor-comparison/1"},
        {"fixture_id", input.value("fixture_id", "unnamed")},
        {"dimension", points.empty() ? 0 : points.front().size()},
        {"input_points", points_json(points)}, {"input_count", points.size()}};
    result["providers"] = Json::array();
    using Clock = std::chrono::steady_clock;
    Json raw_kpabep;
    const auto run_kpabep = [&] {
        const auto begin = Clock::now();
        const auto output = kpabep(points);
        const auto end = Clock::now();
        Json provider{{"method_id", "csl.legacy.btulshor.kpabep.source-v1"},
            {"elapsed_ns", std::chrono::duration_cast<std::chrono::nanoseconds>(end - begin).count()},
            {"interval", "kpabep call only; input parsing and JSON serialization excluded"},
            {"input_count", points.size()}};
        if (const auto* value = std::get_if<KpabepResult>(&output)) {
            provider.update({{"status", "completed"}, {"retained_indices", value->retained_indices},
                {"retained_points", points_json(value->points)}, {"retained_count", value->points.size()},
                {"modif_calls", value->modif_calls}, {"pivot_count", value->pivots}});
        } else {
            const auto& stopped = std::get<Stopped>(output);
            provider.update({{"status", "stopped"}, {"stop_reason", stop_name(stopped.reason)},
                {"reason", stopped.message}});
        }
        raw_kpabep = provider;
        result["providers"].push_back(std::move(provider));
    };
    const auto run_quickhull = [&] {
        Json provider{{"method_id", "csl.geometry.quickhull-2d"}};
        if (result["dimension"] != 2) {
            provider["status"] = "unsupported_dimension";
        } else {
        const auto begin = Clock::now();
        const auto timed_quick = csl::geometry::quickhull_2d(points);
        const auto end = Clock::now();
        provider["elapsed_ns"] = std::chrono::duration_cast<std::chrono::nanoseconds>(end - begin).count();
        provider["interval"] = "QuickHull2D call only; input parsing and JSON serialization excluded";
        if (const auto* hull = std::get_if<csl::geometry::QuickHull2D>(&timed_quick)) {
            provider["status"] = "completed";
            provider["retained_indices"] = hull->vertex_indices;
        } else {
            provider["status"] = "refused";
            provider["reason"] = "QuickHull2D returned diagnostics";
        }
        }
        result["providers"].push_back(std::move(provider));
    };
    const auto run_reducer = [&](const std::string& method_id, int which) {
        using namespace csl;
        using namespace csl::registry;
        Json provider{{"method_id", method_id}};
        auto lp_registration = adapters::lp::make_highs_registration();
        auto* lp_entry = std::get_if<Registration<LPPort>>(&lp_registration);
        if (!lp_entry) {
            provider["status"] = "unavailable";
            provider["reason"] = "HiGHS registration refused";
            return provider;
        }
        Requirements lp_requirements;
        lp_requirements.output.representation = {"csl.program-result.v1"};
        Registry<LPPort> lp_registry;
        if (lp_registry.add(std::move(*lp_entry))) {
            provider["status"] = "unavailable";
            provider["reason"] = "HiGHS registration conflict";
            return provider;
        }
        auto prepared_lp = prepare_provider(select_provider(lp_registry,
            Method{{"csl.lp.highs"}, std::nullopt}, lp_requirements));
        auto* lp = std::get_if<PreparedProvider<LPPort>>(&prepared_lp);
        if (!lp) {
            provider["status"] = "unavailable";
            provider["reason"] = "HiGHS provider preparation refused";
            return provider;
        }
        RegisteredLPQueryRunner runner(std::move(*lp));
        const geometry::PointCloud cloud{{"btulshor-comparison"}, points};
        const ExecutionContext context{{}, {}, {}, {1e-8, 1e-8}, "btulshor-report", {}};
        geometry::HullReductionResult reduction = Diagnostics{};
        Clock::time_point begin;
        Clock::time_point end;
        if (which == 0) {
            Registry<HullReducerPort> reducers;
            if (reducers.add(geometry::make_lp_hull_reducer_registration())) {
                provider["status"] = "unavailable";
                provider["reason"] = "generic LP reducer registration conflict";
                return provider;
            }
            auto prepared = prepare_pipeline(select(reducers,
                Method{{"csl.hull.lp-membership"}, std::nullopt}, cloud));
            auto* pipeline = std::get_if<PreparedPipeline<HullReducerPort>>(&prepared);
            if (!pipeline) {
                provider["status"] = "refused";
                provider["reason"] = "generic LP reducer preparation refused";
                return provider;
            }
            auto workspaces = pipeline->create();
            begin = Clock::now();
            reduction = std::get<0>(workspaces)->run_with(context, runner);
            end = Clock::now();
        } else if (which == 1 || which == 3) {
            begin = Clock::now();
            reduction = geometry::reduce_itis17_a43_paper_hull(cloud, runner, context,
                which == 1 ? geometry::A43PivotRule::phase_one_order :
                    geometry::A43PivotRule::largest_norm_tie);
            end = Clock::now();
        } else {
            begin = Clock::now();
            reduction = geometry::reduce_itis17_a44_hull(cloud, runner, context);
            end = Clock::now();
        }
        provider["elapsed_ns"] = std::chrono::duration_cast<std::chrono::nanoseconds>(end - begin).count();
        provider["interval"] = "reducer invocation with prepared LP workspace; JSON serialization excluded";
        if (const auto* value = std::get_if<geometry::HullReduction>(&reduction)) {
            Json indices = value->retained;
            Json attempts = Json::array();
            for (const auto& attempt : value->attempts)
                attempts.push_back({{"candidate_index", attempt.candidate},
                    {"outcome", membership_name(attempt.outcome)}});
            provider.update({{"status", value->status == geometry::ReductionStatus::complete ?
                "completed" : "incomplete"}, {"retained_indices", indices},
                {"retained_points", Json::array()}, {"lp_calls", value->lp_calls},
                {"input_count", points.size()}, {"retained_count", value->retained.size()},
                {"attempt_count", value->attempts.size()}, {"attempts", attempts}});
            if (value->itis17_a43_paper)
                provider["a43_metrics"] = {{"candidate_solves", value->itis17_a43_paper->candidate_solves},
                    {"phase_one_pivots", value->itis17_a43_paper->phase_one_pivots},
                    {"largest_norm_tie_breaks", value->itis17_a43_paper->largest_norm_tie_breaks}};
            for (const auto index : value->retained)
                provider["retained_points"].push_back(vector_json(points.at(index)));
        } else {
            provider["status"] = "failed";
            provider["diagnostics"] = "reducer returned diagnostics";
        }
        return provider;
    };
    const bool reverse = input.value("reverse_order", false);
    std::vector<std::string> provider_order{"legacy", "quickhull", "lp", "a43", "a43-largest-norm", "a44"};
    if (reverse) std::reverse(provider_order.begin(), provider_order.end());
    for (const auto& provider : provider_order) {
        if (provider == "legacy") run_kpabep();
        else if (provider == "quickhull") run_quickhull();
        else if (provider == "lp") result["providers"].push_back(run_reducer("csl.hull.lp-membership", 0));
        else if (provider == "a43") result["providers"].push_back(
            run_reducer("csl.hull.itis17.a43-artificial-basis", 1));
        else if (provider == "a43-largest-norm") result["providers"].push_back(
            run_reducer("csl.hull.itis17.a43-largest-norm-tie", 3));
        else if (provider == "a44") result["providers"].push_back(
            run_reducer("csl.hull.itis17.a44-paper-farthest-incremental-lp", 2));
    }
    if (!raw_kpabep.is_null()) {
        result["status"] = raw_kpabep.at("status");
        for (const auto key : {"retained_indices", "retained_points", "retained_count", "modif_calls", "pivot_count"})
            if (raw_kpabep.contains(key)) result[key] = raw_kpabep.at(key);
    }
    result["provider_order"] = Json::array();
    for (const auto& provider : result["providers"])
        result["provider_order"].push_back(provider.at("method_id"));
    result["comparison_scope"] = "method outputs are preserved; no equality is inferred from vertex counts";
    result["provenance"] = {{"driver_id", "csl.btulshor.compare-driver.v1"},
        {"source_commit", CSL_SOURCE_COMMIT}, {"compiler_id", CSL_COMPILER_ID},
        {"compiler_version", CSL_COMPILER_VERSION}, {"build_config", CSL_BUILD_CONFIG},
        {"raw_method_ids", {"csl.legacy.btulshor.reach.source-v1",
            "csl.legacy.btulshor.kpabep.source-v1", "csl.legacy.btulshor.modif.source-v1"}}};
    result["schema"] = "csl.btulshor-comparison/1";
    return result;
}
} // namespace

int main(int argc, char** argv) {
    try {
        if (argc != 3 || (std::string(argv[1]) != "--case" && std::string(argv[1]) != "--run"))
            throw std::invalid_argument("usage: csl_btulshor_compare (--case|--run) INPUT.json");
        std::ifstream input(argv[2], std::ios::binary);
        if (!input) throw std::runtime_error("could not open input file");
        auto document = Json::parse(input);
        Json output;
        if (std::string(argv[1]) == "--case") {
            if (document.contains("case")) document = document.at("case");
            output = run_case(document);
            output["provenance"] = {{"driver_id", "csl.btulshor.compare-driver.v1"},
                {"source_commit", CSL_SOURCE_COMMIT}, {"compiler_id", CSL_COMPILER_ID},
                {"compiler_version", CSL_COMPILER_VERSION}, {"build_config", CSL_BUILD_CONFIG}};
        } else {
            output = comparison(document);
        }
        std::cout << output.dump() << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 2;
    }
}
