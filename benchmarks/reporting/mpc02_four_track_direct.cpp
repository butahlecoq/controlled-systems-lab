#include <csl/adapters/convex/highs.hpp>
#include <csl/input/scenario_loader.hpp>
#include <csl/registry/provider.hpp>
#include <csl/synthesis/strategy_b/direct_joint.hpp>

#include <chrono>
#include <cmath>
#include <algorithm>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#if !defined(NDEBUG) || defined(_DEBUG)
#error "The MPC-02 measurement executable must be compiled as a Release target"
#endif
#ifndef CSL_SOURCE_COMMIT
#define CSL_SOURCE_COMMIT "unknown"
#endif
#ifndef CSL_BUILD_TYPE
#define CSL_BUILD_TYPE "unknown"
#endif
#ifndef CSL_COMPILER_ID
#define CSL_COMPILER_ID "unknown"
#endif
#ifndef CSL_COMPILER_VERSION
#define CSL_COMPILER_VERSION "unknown"
#endif

namespace {
using namespace csl;
using namespace csl::registry;
using Clock = std::chrono::steady_clock;

template<class T, class... R>
T take(std::variant<T, R...> value, const char* where) {
    if (!std::holds_alternative<T>(value)) throw std::runtime_error(where);
    return std::get<T>(std::move(value));
}

struct Track {
    const char* id;
    std::vector<double> controls;
    double objective;
};

struct MeasurementObservation {
    std::uint64_t assembly_ns{};
    std::uint64_t prepare_ns{};
    std::uint64_t solve_ns{};
    std::size_t variables{};
    std::size_t rows{};
    double max_residual{};
};

std::uint64_t elapsed(Clock::time_point start, Clock::time_point end) {
    return static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(end - start).count());
}

std::string quote(const std::string& value) {
    std::string result = "\"";
    for (const char ch : value) {
        if (ch == '\\' || ch == '\"') result.push_back('\\');
        if (ch == '\n') result += "\\n";
        else result.push_back(ch);
    }
    result.push_back('\"');
    return result;
}

MeasurementObservation run_direct(const input::LoadedScenario& scenario, const Track& track,
    const PreparedProvider<ConvexPort>& provider, const ExecutionContext& context) {
    const auto resolved = scenario.problem();
    const FamilyRequest request{"nominal_open_loop", resolved.identity(),
        FamilyTarget::candidate_relaxation, context.numerical, Assurance::numerical,
        {"csl.polyhedron.h"}, {}};
    const auto assembly_start = Clock::now();
    const auto joint = take(synthesis::strategy_b::build_joint_program(resolved, request),
        "direct joint program construction failed");
    const auto assembly_end = Clock::now();
    const auto* convex = std::get_if<ConvexProgram>(&joint.program);
    if (!convex) throw std::runtime_error("scenario did not construct a convex quadratic program");

    const auto prepare_start = Clock::now();
    auto pipeline = take(provider.prepare(*convex), "HiGHS preparation failed");
    auto [workspace] = pipeline.create();
    const auto prepare_end = Clock::now();
    const auto solve_start = Clock::now();
    const auto outcome = workspace->run(context);
    const auto solve_end = Clock::now();
    const auto* result = std::get_if<ProgramResult>(&outcome);
    if (!result || result->termination != Termination::completed ||
        result->outcome.value != MathematicalOutcome::optimal || !result->primal)
        throw std::runtime_error("HiGHS did not return a completed optimal primal result");
    if (!optimization::check_program_result(*result, *convex, Assurance::numerical).empty())
        throw std::runtime_error("solver result failed the numerical checker");
    const auto primal = optimization::evaluate_primal(*convex, *result->primal,
        request.numerical, {{"mpc02-four-track-independent-primal-check"}, "1"});
    const auto* check = std::get_if<optimization::ConvexPrimalEvaluation>(&primal);
    if (!check) throw std::runtime_error("independent primal evaluation failed");
    const auto description = resolved.description();
    if (!description) throw std::runtime_error("resolved scenario has no description");
    const auto state_width = description->model->dynamics.dimensions.state;
    const auto horizon = description->times.size() - 1;
    const auto first_control = (horizon + 1) * state_width;
    if (first_control + track.controls.size() > result->primal->size())
        throw std::runtime_error("control coordinate map exceeds primal dimension");
    for (std::size_t i = 0; i < track.controls.size(); ++i)
        if (std::abs((*result->primal)[first_control + i] - track.controls[i]) > 2e-7)
            throw std::runtime_error("numerical witness disagrees with exact oracle");
    if (std::abs(check->original_objective - track.objective) > 2e-7)
        throw std::runtime_error("numerical objective disagrees with exact oracle");
    double residual = 0.0;
    if (result->residuals.primal)
        residual = std::max(result->residuals.primal->rows.violation,
            result->residuals.primal->variables.violation);
    return {elapsed(assembly_start, assembly_end), elapsed(prepare_start, prepare_end),
        elapsed(solve_start, solve_end), convex->quadratic_program().variables().size(),
        convex->quadratic_program().rows().size(), residual};
}

} // namespace

int main(int argc, char** argv) try {
    using namespace csl;
    if (argc != 6) {
        std::cerr << "Usage: mpc02_four_track_direct <output-dir> <unconstrained.json> "
                     "<stage-box.json> <slew.json> <l1-budget.json>\n";
        return 2;
    }
    const std::vector<Track> tracks{
        {"mpc02-unconstrained-2d-v1", {0.5, 0.0}, 0.0},
        {"mpc02-stage-box-2d-v1", {0.5, 0.0}, 0.0},
        {"mpc02-slew-2d-v1", {0.375, 0.125}, 1.0 / 32.0},
        {"mpc02-l1-budget-2d-v1", {0.25, 0.0}, 1.0 / 16.0},
    };
    std::vector<input::LoadedScenario> scenarios;
    scenarios.reserve(tracks.size());
    for (int i = 0; i < 4; ++i) {
        const auto loaded = input::load_scenario_file(argv[i + 2]);
        const auto* scenario = std::get_if<input::LoadedScenario>(&loaded);
        if (!scenario || scenario->metadata()->id != tracks[static_cast<std::size_t>(i)].id)
            throw std::runtime_error("scenario path/id does not match the typed MPC-02 track table");
        scenarios.push_back(*scenario);
    }
    std::error_code error;
    if (!std::filesystem::create_directory(argv[1], error) || error)
        throw std::runtime_error("output directory already exists or cannot be created");
    std::ofstream file(std::filesystem::path(argv[1]) / "events.jsonl", std::ios::binary);
    if (!file) throw std::runtime_error("could not create events.jsonl");
    auto emit = [&](const std::string& line) { std::cout << line << '\n'; file << line << '\n'; };

    auto registration = take(adapters::convex::make_highs_registration(), "HiGHS registration failed");
    const auto provider_id = registration.identity.id;
    Registry<ConvexPort> registry;
    if (registry.add(std::move(registration))) throw std::runtime_error("HiGHS registration rejected");
    Requirements requirements;
    requirements.output.representation = {"csl.program-result.v1"};
    auto provider = take(prepare_provider(select_provider(registry, Method{provider_id, {}}, requirements)),
        "HiGHS provider preparation failed");
    const auto provenance = provider.provenance();
    const auto backend = provenance.actual ? provenance.actual->id.value + "@" + provenance.actual->version : "unknown";
    ExecutionContext context;
    context.numerical = {1e-8, 1e-8};
    context.resources = std::make_shared<const ResourcePolicy>(ResourcePolicy{1, 1, 1, {}});
    emit("{\"schema\":\"csl.mpc02-four-track-direct-measurement/1\",\"event\":\"header\",\"source_commit\":"
        + quote(CSL_SOURCE_COMMIT) + ",\"build_type\":" + quote(CSL_BUILD_TYPE)
        + ",\"compiler_id\":" + quote(CSL_COMPILER_ID) + ",\"compiler_version\":" + quote(CSL_COMPILER_VERSION)
        + ",\"backend\":" + quote(backend)
        + ",\"claim_limit\":\"four tiny direct-joint fixtures; descriptive formulation comparison only\"}");

    constexpr int warmups = 1;
    constexpr int repetitions = 7;
    int failures = 0;
    for (std::size_t track_index = 0; track_index < tracks.size(); ++track_index) {
        const auto& track = tracks[track_index];
        for (int repetition = -warmups; repetition < repetitions; ++repetition) {
            const bool warmup = repetition < 0;
            bool passed = true;
            MeasurementObservation observation;
            std::string failure;
            try { observation = run_direct(scenarios[track_index], track, provider, context); }
            catch (const std::exception& exception) { passed = false; failure = exception.what(); ++failures; }
            std::ostringstream event;
            event << std::setprecision(17)
                << "{\"schema\":\"csl.mpc02-four-track-direct-measurement/1\",\"event\":\"attempt\",\"case\":"
                << quote(track.id) << ",\"pair\":" << (warmup ? 0 : repetition + 1)
                << ",\"warmup\":" << (warmup ? "true" : "false")
                << ",\"status\":" << quote(passed ? "passed" : "failed")
                << ",\"assembly_ns\":" << observation.assembly_ns << ",\"provider_prepare_and_workspace_ns\":"
                << observation.prepare_ns << ",\"solve_ns\":" << observation.solve_ns
                << ",\"variables\":" << observation.variables << ",\"rows\":" << observation.rows
                << ",\"max_residual\":" << observation.max_residual << ",\"error\":" << quote(failure) << '}';
            emit(event.str());
        }
    }
    emit("{\"schema\":\"csl.mpc02-four-track-direct-measurement/1\",\"event\":\"summary\",\"tracks\":4,\"attempts_per_track\":8,\"failures\":"
        + std::to_string(failures) + "}");
    return failures == 0 ? 0 : 1;
} catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
}
