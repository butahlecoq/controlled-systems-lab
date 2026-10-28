#include <csl/adapters/convex/highs.hpp>
#include <csl/input/scenario_loader.hpp>
#include <csl/problem/temporal_lifts.hpp>
#include <csl/registry/provider.hpp>
#include <csl/synthesis/strategy_b/direct_joint.hpp>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <fstream>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string>

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

sets::SetData interval(double lower, double upper) {
    const auto h = take(numeric::snapshot(Matrix{2, 1, {1, -1}}), "interval matrix snapshot failed");
    const auto b = take(numeric::snapshot_vector(Vector{upper, -lower}), "interval bounds snapshot failed");
    const auto e = take(numeric::snapshot(Matrix{0, 1, {}}), "interval equality snapshot failed");
    const auto f = take(numeric::snapshot_vector(Vector{}), "interval equality-values snapshot failed");
    return take(sets::make_h({{"mpc02-slew-increment"}, 1, {"delta-u"}}, {h, b, e, f}),
        "interval construction failed");
}

struct ProgramCase {
    std::string name;
    problem::ResolvedProblem resolved;
    std::vector<std::size_t> control_indices;
    std::optional<Problem> stage_only_for_lift;
};

struct TimedResult {
    std::uint64_t formulation_transform_ns{};
    std::uint64_t assembly_ns{};
    std::uint64_t prepare_create_ns{};
    std::uint64_t solve_ns{};
    std::size_t variables{};
    std::size_t rows{};
    Vector controls;
    double objective{};
    double max_residual{};
};

std::uint64_t elapsed(Clock::time_point start, Clock::time_point end) {
    return static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(end - start).count());
}

TimedResult run_case(const ProgramCase& test_case,
    const PreparedProvider<ConvexPort>& provider, const ExecutionContext& context,
    const std::vector<double>& expected_controls, double expected_objective) {
    auto resolved = test_case.resolved;
    auto control_indices = test_case.control_indices;
    std::uint64_t formulation_transform_ns = 0;
    if (test_case.stage_only_for_lift) {
        const auto transform_start = Clock::now();
        const auto transformed = take(problem::lift_one_step_slew(*test_case.stage_only_for_lift,
            {problem::UnconstrainedFirstAction{}, {interval(-0.25, 0.25).as_handle()}}),
            "exact slew lift construction failed");
        resolved = take(problem::resolve(transformed.problem,
            {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}}),
            "lifted problem resolution failed");
        control_indices = transformed.coordinates.original_control_to_lifted_memory;
        formulation_transform_ns = elapsed(transform_start, Clock::now());
    }
    const FamilyRequest request{"nominal_open_loop", resolved.identity(),
        FamilyTarget::candidate_relaxation, context.numerical, Assurance::numerical, {"csl.polyhedron.h"}, {}};
    const auto assembly_start = Clock::now();
    auto joint = take(synthesis::strategy_b::build_joint_program(resolved, request),
        "joint program construction failed");
    const auto assembly_end = Clock::now();
    const auto* convex = std::get_if<ConvexProgram>(&joint.program);
    if (!convex) throw std::runtime_error("case did not construct a convex quadratic program");

    const auto prepare_start = Clock::now();
    auto pipeline = take(provider.prepare(*convex), "HiGHS convex capability preparation failed");
    auto [workspace] = pipeline.create();
    const auto prepare_end = Clock::now();

    const auto solve_start = Clock::now();
    const auto outcome = workspace->run(context);
    const auto solve_end = Clock::now();
    const auto* result = std::get_if<ProgramResult>(&outcome);
    if (!result) throw std::runtime_error("HiGHS returned unsupported for a convex program");
    if (result->termination != Termination::completed || result->outcome.value != MathematicalOutcome::optimal || !result->primal)
        throw std::runtime_error("HiGHS did not return a completed optimal primal result");
    if (!optimization::check_program_result(*result, *convex, Assurance::numerical).empty())
        throw std::runtime_error("program result failed the solver-program numerical checker");
    const auto primal_outcome = optimization::evaluate_primal(
        *convex, *result->primal, request.numerical, {{"mpc02-independent-primal-check"}, "1"});
    const auto* primal_check = std::get_if<optimization::ConvexPrimalEvaluation>(&primal_outcome);
    if (!primal_check) throw std::runtime_error("independent primal evaluation failed");

    Vector controls;
    controls.reserve(control_indices.size());
    for (const auto index : control_indices) {
        if (index >= result->primal->size()) throw std::runtime_error("control map exceeds returned primal dimension");
        controls.push_back((*result->primal)[index]);
    }
    if (controls.size() != expected_controls.size()) throw std::runtime_error("control map has an unexpected size");
    for (std::size_t index = 0; index < controls.size(); ++index)
        if (std::abs(controls[index] - expected_controls[index]) > 2e-7)
            throw std::runtime_error("numerical controls disagree with the exact rational oracle");
    if (std::abs(primal_check->original_objective - expected_objective) > 2e-7)
        throw std::runtime_error("numerical objective disagrees with the exact rational oracle");
    const double slew = controls[1] - controls[0];
    if (std::abs(slew) > 0.25 + 2e-7) throw std::runtime_error("recovered physical controls violate the original slew row");
    const double physical_cost = (controls[0] - 0.5) * (controls[0] - 0.5) + controls[1] * controls[1];
    if (std::abs(physical_cost - expected_objective) > 2e-7)
        throw std::runtime_error("independent physical objective evaluation disagrees with the exact oracle");

    double max_residual = 0.0;
    if (result->residuals.primal) {
        max_residual = std::max(result->residuals.primal->rows.violation, result->residuals.primal->variables.violation);
    }
    return {formulation_transform_ns, elapsed(assembly_start, assembly_end), elapsed(prepare_start, prepare_end),
        elapsed(solve_start, solve_end), convex->quadratic_program().variables().size(),
        convex->quadratic_program().rows().size(), std::move(controls), primal_check->original_objective, max_residual};
}

ProgramCase make_direct_case(const input::LoadedScenario& scenario) {
    const auto resolved = scenario.problem();
    const auto problem = resolved.description();
    if (!problem || !problem->temporal.has_value()) throw std::runtime_error("expected a slew-constrained source scenario");
    const std::size_t state_width = problem->model->dynamics.dimensions.state;
    const std::size_t horizon = problem->times.size() - 1;
    const std::size_t first_control = (horizon + 1) * state_width;
    return {"direct_full_history", resolved,
        {first_control, first_control + 1}, {}};
}

ProgramCase make_lifted_case(const input::LoadedScenario& scenario) {
    const auto resolved = scenario.problem();
    const auto description = resolved.description();
    if (!description) throw std::runtime_error("resolved scenario has no source problem description");
    Problem stage_only = *description;
    stage_only.temporal.reset();
    return {"exact_slew_memory_lift", resolved, {}, std::move(stage_only)};
}

std::string quote(const std::string& value) {
    std::string result = "\"";
    for (const char ch : value) {
        if (ch == '\\' || ch == '"') result.push_back('\\');
        if (ch == '\n') result += "\\n";
        else result.push_back(ch);
    }
    result.push_back('"');
    return result;
}

} // namespace

int main(int argc, char** argv) try {
    using namespace csl;
    if (argc < 2 || argc > 3) {
        std::cerr << "Usage: mpc02_slew_direct_vs_lift <scenario.json> [new-output-directory]\n";
        return 2;
    }
    const auto loaded = input::load_scenario_file(argv[1]);
    const auto* scenario = std::get_if<input::LoadedScenario>(&loaded);
    if (!scenario || scenario->metadata()->id != "mpc02-slew-2d-v1")
        throw std::runtime_error("expected the mpc02-slew-2d-v1 resolved scenario");

    std::ofstream file;
    if (argc == 3) {
        std::error_code error;
        const bool created = std::filesystem::create_directory(argv[2], error);
        if (!created || error) throw std::runtime_error("output directory already exists or cannot be created");
        file.open(std::filesystem::path(argv[2]) / "events.jsonl", std::ios::out | std::ios::binary);
        if (!file) throw std::runtime_error("could not create events.jsonl in the new output directory");
    }
    auto emit = [&](const std::string& line) {
        std::cout << line << '\n';
        if (file) file << line << '\n';
        if (!std::cout || (file && !file)) throw std::runtime_error("event output write failed");
    };

    const auto direct = make_direct_case(*scenario);
    const auto source_digest = problem::hex(scenario->source()->content.digest());
    auto registration = take(adapters::convex::make_highs_registration(), "HiGHS convex registration failed");
    const auto provider_id = registration.identity.id;
    Registry<ConvexPort> registry;
    if (registry.add(std::move(registration))) throw std::runtime_error("HiGHS convex registration rejected");
    Requirements requirements;
    requirements.output.representation = {"csl.program-result.v1"};
    auto provider = take(prepare_provider(select_provider(registry, Method{provider_id, {}}, requirements)),
        "HiGHS convex provider preparation failed");
    const auto provenance = provider.provenance();
    const auto provider_identity = provenance.actual ? provenance.actual->id.value + "@" + provenance.actual->version : "unknown";
    ExecutionContext context;
    context.numerical = {1e-8, 1e-8};
    context.resources = std::make_shared<const ResourcePolicy>(ResourcePolicy{1, 1, 1, {}});

    const auto lifted = make_lifted_case(*scenario);
    constexpr double exact_optimum = 1.0 / 32.0;
    const Vector exact_controls{3.0 / 8.0, 1.0 / 8.0};

    emit("{\"schema\":\"csl.mpc02-slew-formulation-measurement/1\",\"event\":\"header\",\"case\":\"mpc02-slew-2d-v1\",\"source_commit\":"
        + quote(CSL_SOURCE_COMMIT) + ",\"build_type\":" + quote(CSL_BUILD_TYPE)
        + ",\"compiler_id\":" + quote(CSL_COMPILER_ID) + ",\"compiler_version\":" + quote(CSL_COMPILER_VERSION)
        + ",\"source_sha256\":"
        + quote(source_digest) + ",\"backend\":" + quote(provider_identity)
        + ",\"backend_claim\":\"same HiGHS QP adapter on direct and exactly lifted joint formulations\",\"units\":\"nanoseconds\",\"resources\":{\"workers\":1,\"native_threads\":1,\"parallelism\":1},\"solver_tolerance\":1e-8,\"exact_oracle\":{\"controls\":[0.375,0.125],\"objective\":0.03125,\"derivation\":\"strictly convex projection of (1/2,0) onto active u0-u1=1/4\"},\"claim_limit\":\"one tiny fixture; numerical solver formulation comparison only; no general speed winner\"}");

    int failures = 0;
    constexpr int warmups = 1;
    constexpr int repetitions = 7;
    for (int repetition = -warmups; repetition < repetitions; ++repetition) {
        const bool warmup = repetition < 0;
        for (int side = 0; side < 2; ++side) {
            const bool reversed = (std::max(repetition, 0) % 2) != 0;
            const bool use_lift = (side == 0) == reversed;
            const auto& test_case = use_lift ? lifted : direct;
            TimedResult observation;
            bool passed = true;
            std::string error;
            try { observation = run_case(test_case, provider, context, exact_controls, exact_optimum); }
            catch (const std::exception& exception) { passed = false; error = exception.what(); ++failures; }
            std::ostringstream event;
            event << std::setprecision(17)
                << "{\"schema\":\"csl.mpc02-slew-formulation-measurement/1\",\"event\":\"attempt\",\"case\":\"mpc02-slew-2d-v1\",\"side\":"
                << quote(test_case.name) << ",\"pair\":" << (warmup ? 0 : repetition + 1)
                << ",\"warmup\":" << (warmup ? "true" : "false") << ",\"order_reversed\":" << (reversed ? "true" : "false")
                << ",\"status\":" << quote(passed ? "passed" : "failed")
                << ",\"formulation_transform_and_resolve_ns\":" << observation.formulation_transform_ns
                << ",\"assembly_ns\":" << observation.assembly_ns
                << ",\"provider_prepare_and_workspace_ns\":" << observation.prepare_create_ns << ",\"solve_ns\":" << observation.solve_ns
                << ",\"variables\":" << observation.variables << ",\"rows\":" << observation.rows << ",\"controls\":[";
            for (std::size_t index = 0; index < observation.controls.size(); ++index) {
                if (index) event << ',';
                event << observation.controls[index];
            }
            event << "],\"objective\":" << observation.objective << ",\"max_residual\":" << observation.max_residual
                << ",\"error\":" << quote(error) << '}';
            emit(event.str());
        }
    }
    emit("{\"schema\":\"csl.mpc02-slew-formulation-measurement/1\",\"event\":\"summary\",\"attempts\":"
        + std::to_string((warmups + repetitions) * 2) + ",\"failures\":" + std::to_string(failures) + "}");
    return failures == 0 ? 0 : 1;
} catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
}
