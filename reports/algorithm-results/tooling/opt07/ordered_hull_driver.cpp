#include <csl/adapters/lp/highs.hpp>
#include <csl/geometry/hull_reducer.hpp>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <limits>
#include <memory>
#include <numeric>
#include <stdexcept>
#include <string>
#include <tuple>
#include <variant>

namespace {
using namespace csl;
using Port = registry::HullReducerPort;

struct Case {
    const char* id;
    geometry::PointCloud cloud;
    std::vector<std::size_t> order;
    std::size_t zero_width;
    std::size_t vertices;
    std::vector<Vector> directions;
    Vector expected_support;
};

std::vector<Case> cases() {
    return {
        {"signed-score", {{"opt07-signed-score"},
            {{-1.0, -1.0}, {1.0, 1.0}, {-1.0, 1.0}, {1.0, -1.0},
             {-1.0, 0.25}, {0.75, -0.75}}},
            {0, 1, 2, 3, 5, 4}, 0, 4,
            {{1, 0}, {-1, 0}, {0, 1}, {0, -1}, {1, 1}}, {1, 1, 1, 1, 2}},
        {"zero-width-duplicate", {{"opt07-zero-width-duplicate"},
            {{-2.0, 3.0}, {2.0, 3.0}, {0.0, 3.0}, {-2.0, 3.0}}},
            {0, 1, 3, 2}, 1, 2,
            {{1, 0}, {-1, 0}, {0, 1}, {0, -1}}, {2, 2, 3, -3}},
        {"late-outside", {{"opt07-late-outside"},
            {{0.0}, {0.5}, {0.25}, {1.0}}},
            {0, 3, 2, 1}, 0, 2,
            {{1}, {-1}}, {1, 0}},
    };
}

std::unique_ptr<LPWorkspace> make_lp(
        const registry::Registration<registry::LPPort>& adapter) {
    auto seed = optimization::make_linear_program({
        {{"opt07-report"}, {"workspace-seed"}}, {}, 0,
        {0, 0, {0}, {}, {}}, {}, {}});
    if (!std::holds_alternative<LinearProgram>(seed))
        throw std::runtime_error("LP workspace seed rejected");
    auto workspace = adapter.factory(std::get<LinearProgram>(seed));
    if (!workspace) throw std::runtime_error("LP workspace factory returned null");
    return workspace;
}

struct Resources {
    std::unique_ptr<registry::BoundWorkspace<Port>> reducer;
    std::unique_ptr<LPWorkspace> lp;
};

std::vector<Resources> prepare(const Case& fixture, std::size_t count) {
    registry::Registry<Port> registry;
    if (registry.add(geometry::make_ordered_hull_reducer_registration()))
        throw std::runtime_error("ordered reducer registration rejected");
    auto selected = registry::prepare_pipeline(registry::select(registry,
        registry::Method{{"csl.hull.ordered-membership"}, "1.0.0"}, fixture.cloud));
    if (!std::holds_alternative<registry::PreparedPipeline<Port>>(selected))
        throw std::runtime_error("ordered reducer selection rejected");
    const auto prepared = std::get<registry::PreparedPipeline<Port>>(std::move(selected));
    const auto provenance = prepared.provenance();
    if (!provenance[0].actual || provenance[0].actual->id.value != "csl.hull.ordered-membership")
        throw std::runtime_error("ordered reducer provenance mismatch");

    auto lp_registration = adapters::lp::make_highs_registration();
    if (!std::holds_alternative<registry::Registration<registry::LPPort>>(lp_registration))
        throw std::runtime_error("HiGHS LP registration rejected");
    const auto adapter = std::get<registry::Registration<registry::LPPort>>(std::move(lp_registration));
    std::vector<Resources> resources;
    resources.reserve(count);
    for (std::size_t index = 0; index < count; ++index) {
        auto owned = prepared.create();
        resources.push_back({std::move(std::get<0>(owned)), make_lp(adapter)});
    }
    return resources;
}

const char* outcome_name(geometry::MembershipOutcome value) {
    using geometry::MembershipOutcome;
    switch (value) {
    case MembershipOutcome::feasible: return "feasible";
    case MembershipOutcome::infeasible: return "infeasible";
    case MembershipOutcome::unsupported: return "unsupported";
    case MembershipOutcome::stopped: return "stopped";
    case MembershipOutcome::numerical_failure: return "numerical_failure";
    case MembershipOutcome::malformed_result: return "malformed_result";
    }
    return "unknown";
}

Vector support_values(const Case& fixture, const geometry::HullReduction& result) {
    Vector values;
    for (const auto& direction : fixture.directions) {
        double maximum = -std::numeric_limits<double>::infinity();
        for (const auto id : result.retained) {
            double value = 0.0;
            for (std::size_t coordinate = 0; coordinate < direction.size(); ++coordinate)
                value += fixture.cloud.points[id][coordinate] * direction[coordinate];
            maximum = std::max(maximum, value);
        }
        values.push_back(maximum);
    }
    return values;
}

bool check_result(const Case& fixture, const geometry::HullReductionResult& outcome) {
    if (!std::holds_alternative<geometry::HullReduction>(outcome)) return false;
    const auto& result = std::get<geometry::HullReduction>(outcome);
    const auto count = fixture.cloud.points.size();
    if (result.status != geometry::ReductionStatus::complete || !result.ordered ||
        result.ordered->processing_order != fixture.order ||
        result.ordered->ordered_candidates != count ||
        result.ordered->zero_width_coordinates != fixture.zero_width ||
        result.ordered->used_identity_fallback || result.retained.size() != fixture.vertices ||
        result.retained.size() + result.removed.size() != count ||
        result.lp_calls != count || result.attempts.size() != count ||
        support_values(fixture, result) != fixture.expected_support)
        return false;
    std::vector<bool> seen(count, false);
    for (const auto id : result.retained) {
        if (id >= count || seen[id]) return false;
        seen[id] = true;
    }
    for (const auto& removal : result.removed) {
        if (removal.removed >= count || seen[removal.removed] ||
            removal.program.problem != fixture.cloud.problem ||
            removal.program.program.value != "hull-membership-" + std::to_string(removal.removed))
            return false;
        seen[removal.removed] = true;
        for (const auto& term : removal.combination)
            if (term.point >= count || !std::isfinite(term.weight) || term.weight < 0) return false;
    }
    for (std::size_t index = 0; index < count; ++index) {
        if (!seen[index] || result.attempts[index].candidate != fixture.order[index]) return false;
        const auto candidate = result.attempts[index].candidate;
        const bool removed = std::any_of(result.removed.begin(), result.removed.end(),
            [candidate](const auto& certificate) { return certificate.removed == candidate; });
        if (result.attempts[index].outcome != (removed ? geometry::MembershipOutcome::feasible :
                                               geometry::MembershipOutcome::infeasible)) return false;
    }
    return true;
}

template<class T> void print_numbers(const T& values) {
    std::cout << '[';
    for (std::size_t index = 0; index < values.size(); ++index) {
        if (index) std::cout << ',';
        std::cout << values[index];
    }
    std::cout << ']';
}

void print_call(const Case& fixture, const geometry::HullReductionResult& outcome,
        const char* purpose, std::size_t round, bool warmup, std::size_t ordinal, bool verified) {
    std::cout << "{\"kind\":\"call\",\"purpose\":\"" << purpose
              << "\",\"case_id\":\"" << fixture.id << "\",\"problem\":\""
              << fixture.cloud.problem.value << "\",\"round\":" << round
              << ",\"warmup\":" << warmup << ",\"ordinal\":" << ordinal
              << ",\"points\":[";
    for (std::size_t index = 0; index < fixture.cloud.points.size(); ++index) {
        if (index) std::cout << ',';
        print_numbers(fixture.cloud.points[index]);
    }
    std::cout << "],\"verified\":" << verified;
    if (!std::holds_alternative<geometry::HullReduction>(outcome)) {
        std::cout << ",\"status\":\"diagnostics\"}\n";
        return;
    }
    const auto& result = std::get<geometry::HullReduction>(outcome);
    std::cout << ",\"status\":\"" << (result.status == geometry::ReductionStatus::complete ? "complete" : "incomplete")
              << "\",\"retained\":";
    print_numbers(result.retained);
    std::cout << ",\"removed\":[";
    for (std::size_t index = 0; index < result.removed.size(); ++index) {
        if (index) std::cout << ',';
        const auto& removed = result.removed[index];
        std::cout << "{\"point\":" << removed.removed << ",\"program_problem\":\""
                  << removed.program.problem.value << "\",\"program\":\""
                  << removed.program.program.value << "\",\"terms\":[";
        for (std::size_t term = 0; term < removed.combination.size(); ++term) {
            if (term) std::cout << ',';
            std::cout << '[' << removed.combination[term].point << ','
                      << removed.combination[term].weight << ']';
        }
        std::cout << "]}";
    }
    std::cout << "],\"order\":";
    print_numbers(result.ordered ? result.ordered->processing_order : std::vector<std::size_t>{});
    std::cout << ",\"ordered_candidates\":" << (result.ordered ? result.ordered->ordered_candidates : 0)
              << ",\"zero_width_coordinates\":" << (result.ordered ? result.ordered->zero_width_coordinates : 0)
              << ",\"identity_fallback\":" << (result.ordered ? result.ordered->used_identity_fallback : false)
              << ",\"lp_calls\":" << result.lp_calls << ",\"attempts\":[";
    for (std::size_t index = 0; index < result.attempts.size(); ++index) {
        if (index) std::cout << ',';
        std::cout << '[' << result.attempts[index].candidate << ",\""
                  << outcome_name(result.attempts[index].outcome) << "\"]";
    }
    std::cout << "],\"support\":";
    print_numbers(support_values(fixture, result));
    std::cout << "}\n";
}

bool run_batch(const Case& fixture, const char* purpose, std::size_t round,
        bool warmup, std::size_t calls) {
    auto resources = prepare(fixture, calls);
    std::vector<geometry::HullReductionResult> outputs;
    outputs.reserve(calls);
    const auto started = std::chrono::steady_clock::now();
    for (auto& resource : resources)
        outputs.push_back(resource.reducer->run_with(ExecutionContext{}, *resource.lp));
    const auto finished = std::chrono::steady_clock::now();
    const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(finished - started).count();
    std::size_t verified = 0;
    for (std::size_t index = 0; index < outputs.size(); ++index) {
        const bool good = check_result(fixture, outputs[index]);
        verified += good;
        print_call(fixture, outputs[index], purpose, round, warmup, index, good);
    }
    std::cout << "{\"kind\":\"batch\",\"purpose\":\"" << purpose
              << "\",\"case_id\":\"" << fixture.id << "\",\"round\":" << round
              << ",\"warmup\":" << warmup << ",\"calls\":" << calls
              << ",\"verified_calls\":" << verified << ",\"elapsed_ns\":" << elapsed << "}\n";
    std::cout.flush();
    return verified == calls;
}

void describe() {
#ifdef _MSC_VER
    constexpr long cxx_standard = _MSVC_LANG;
#else
    constexpr long cxx_standard = __cplusplus;
#endif
    std::cout << "{\"kind\":\"describe\",\"source_commit\":\"" << CSL_OPT07_SOURCE_COMMIT
              << "\",\"harness_sha256\":\"" << CSL_OPT07_HARNESS_SHA256
              << "\",\"configuration\":\"" << CSL_OPT07_CONFIG
              << "\",\"cxx_standard\":" << cxx_standard
#ifdef NDEBUG
              << ",\"ndebug\":true";
#else
              << ",\"ndebug\":false";
#endif
    std::cout << ",\"batch_calls\":100,\"repetitions\":7}\n";
}
} // namespace

int main(int argc, char** argv) {
    try {
        if (argc != 2) throw std::runtime_error("usage: csl_opt07_measure describe|smoke|measure");
        const std::string mode = argv[1];
        if (mode == "describe") {
            describe();
            return 0;
        }
        std::cout << std::setprecision(std::numeric_limits<double>::max_digits10) << std::boolalpha;
        const auto fixtures = cases();
        if (mode == "smoke") {
            bool valid = true;
            for (const auto& fixture : fixtures)
                valid = run_batch(fixture, "smoke", 0, true, 1) && valid;
            return valid ? 0 : 1;
        }
        if (mode == "measure") {
            constexpr std::size_t calls_per_batch = 100;
            bool valid = true;
            for (const auto& fixture : fixtures)
                valid = run_batch(fixture, "measurement", 0, true, calls_per_batch) && valid;
            for (std::size_t round = 0; round < 7; ++round)
                for (std::size_t offset = 0; offset < fixtures.size(); ++offset)
                    valid = run_batch(fixtures[(round + offset) % fixtures.size()], "measurement",
                        round + 1, false, calls_per_batch) && valid;
            return valid ? 0 : 1;
        }
        throw std::runtime_error("usage: csl_opt07_measure describe|smoke|measure");
    } catch (const std::exception& error) {
        std::cerr << "OPT-07 harness failed: " << error.what() << '\n';
        return 1;
    }
}
