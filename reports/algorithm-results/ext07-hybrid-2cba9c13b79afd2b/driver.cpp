#include <csl/adapters/convex/highs.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <csl/synthesis/hybrid_path_program.hpp>

#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstddef>
#include <iomanip>
#include <iostream>
#include <limits>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string>
#include <string>
#include <variant>

namespace {
using namespace csl;
using namespace csl::model;
using Clock = std::chrono::steady_clock;

template<class T, class... U>
T take(std::variant<T, U...> value) {
    if(!std::holds_alternative<T>(value)) throw std::runtime_error("EXT-07 public operation rejected the fixture");
    return std::get<T>(std::move(value));
}

numeric::MatrixView matrix(Matrix value) { return take(numeric::snapshot(std::move(value))); }
numeric::VectorView vector(Vector value) { return take(numeric::snapshot_vector(std::move(value))); }

SetHandle interval(std::string id, double lower, double upper) {
    auto data = take(sets::make_h({{std::move(id)}, 1, {"x"}},
        {matrix({2, 1, {1, -1}}), vector({upper, -lower}),
         matrix({0, 1, {}}), vector({})}));
    return data.as_handle();
}

SetHandle identity_reset() {
    auto data = take(sets::make_h({{"ext07-report-identity-reset"}, 2, {"pre", "post"}},
        {matrix({0, 2, {}}), vector({}), matrix({1, 2, {1, -1}}), vector({0})}));
    return data.as_handle();
}

std::pair<HybridSystem, HybridRequest> fixture() {
    HybridMode source{{"coast"}, 1, 1, {"x"}, {"u"}};
    source.flow = LinearStage{Matrix{1, 1, {1}}, Matrix{1, 1, {1}}, Matrix{1, 0, {}}, Vector{0}};
    source.control_sets = {interval("ext07-report-control", 0, 1)};
    source.invariants = {UniversalSet{1}, UniversalSet{1}};

    HybridMode target{{"terminal"}, 1, 1, {"x"}, {"u"}};
    target.flow = LinearStage{Matrix{1, 1, {1}}, Matrix{1, 1, {1}}, Matrix{1, 0, {}}, Vector{0}};
    target.control_sets = {UniversalSet{1}};
    target.invariants = {UniversalSet{1}, UniversalSet{1}};

    HybridSystem system{1, {source, target},
        {{{"coast-to-terminal"}, {"coast"}, {"terminal"},
          {interval("ext07-report-guard", 0, 0.5)}, {identity_reset()}}}};
    HybridRequest request{{{"coast"}, {0}}, {{"terminal"}},
        {{{"terminal"}, LinearTerminal{{1}, 0}, "terminal state", "state units"}}};
    return {std::move(system), std::move(request)};
}

registry::PreparedProvider<registry::LPPort> lp_provider() {
    auto registration = take(adapters::lp::make_highs_registration());
    registry::Registry<registry::LPPort> providers;
    const auto id = registration.identity.id;
    if(providers.add(std::move(registration))) throw std::runtime_error("HiGHS LP registration failed");
    registry::Requirements requirements;
    requirements.output.representation = {"csl.program-result.v1"};
    return take(registry::prepare_provider(registry::select_provider(
        providers, registry::Method{id, {}}, requirements)));
}

registry::PreparedProvider<registry::ConvexPort> convex_provider() {
    auto registration = take(adapters::convex::make_highs_registration());
    registry::Registry<registry::ConvexPort> providers;
    const auto id = registration.identity.id;
    if(providers.add(std::move(registration))) throw std::runtime_error("HiGHS convex registration failed");
    registry::Requirements requirements;
    requirements.output.representation = {"csl.program-result.v1"};
    return take(registry::prepare_provider(registry::select_provider(
        providers, registry::Method{id, {}}, requirements)));
}

struct Observation {
    std::uint64_t setup_ns{};
    std::uint64_t assembly_ns{};
    std::uint64_t solve_ns{};
    std::uint64_t verify_ns{};
    std::uint64_t total_ns{};
    std::size_t path_count{};
    std::size_t relation_rows{};
    std::size_t relation_matrix_elements{};
    double objective{};
    double control{};
    std::optional<double> objective_lower;
    std::optional<double> objective_upper;
    std::optional<double> primal_row_violation;
    std::optional<double> primal_variable_violation;
    std::string provider;
    std::string termination;
    std::string outcome;
    std::string verifier;
    std::string verifier_version;
    std::string feasibility;
    std::string optimality;
    std::string coverage;
};

const char* status(synthesis::HybridVerificationStatus value) {
    switch(value) {
    case synthesis::HybridVerificationStatus::established: return "established";
    case synthesis::HybridVerificationStatus::refuted: return "refuted";
    case synthesis::HybridVerificationStatus::unsupported: return "unsupported";
    default: return "not_checked";
    }
}

Observation run_once() {
    const auto total_begin = Clock::now();
    auto [system, request] = fixture();
    auto lp = lp_provider();
    auto convex = convex_provider();
    Observation observation;
    observation.setup_ns = static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(
        Clock::now() - total_begin).count());

    const auto assembly_begin = Clock::now();
    auto built = synthesis::build_hybrid_portfolio_programs(system, request, {"ext07-report"},
        {1, 8}, {16, 128, 2048});
    if(!std::holds_alternative<std::vector<synthesis::HybridPathProgram>>(built))
        throw std::runtime_error("Hybrid branch program construction failed");
    auto programs = std::get<std::vector<synthesis::HybridPathProgram>>(std::move(built));
    observation.assembly_ns = static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(
        Clock::now() - assembly_begin).count());
    observation.path_count = programs.size();
    if(programs.size() != 1 || programs[0].relation_operations.empty())
        throw std::runtime_error("Expected one complete path with operation provenance");
    observation.relation_rows = programs[0].relation_operations.back().cumulative_rows;
    observation.relation_matrix_elements = programs[0].relation_operations.back().cumulative_matrix_elements;

    const auto solve_begin = Clock::now();
    const auto execution = synthesis::execute_hybrid_path_programs(programs, lp, convex, {});
    observation.solve_ns = static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(
        Clock::now() - solve_begin).count());
    if(!execution.all_supplied_branches_completed || execution.branches.size() != 1 ||
       !execution.branches[0].result || !execution.branches[0].result->primal)
        throw std::runtime_error("Hybrid branch optimization did not complete with a primal point");
    const auto& branch = execution.branches[0];
    observation.provider = branch.providers.empty() || !branch.providers[0].actual ? "unavailable" :
        branch.providers[0].actual->id.value + "@" + branch.providers[0].actual->version;
    observation.termination = branch.termination == Termination::completed ? "completed" : "other";
    observation.outcome = branch.outcome == MathematicalOutcome::optimal ? "optimal" : "other";
    const auto& primal = *branch.result->primal;
    if(primal.size() != 4) throw std::runtime_error("Hybrid LP primal has the wrong joint dimension");
    observation.control = primal[1];
    observation.objective = primal[3];
    if(branch.result->objective.lower) observation.objective_lower = branch.result->objective.lower->value;
    if(branch.result->objective.upper) observation.objective_upper = branch.result->objective.upper->value;
    if(branch.result->residuals.primal) {
        observation.primal_row_violation = branch.result->residuals.primal->rows.violation;
        observation.primal_variable_violation = branch.result->residuals.primal->variables.violation;
    }
    if(std::abs(observation.control) > 1e-8 || std::abs(observation.objective) > 1e-8 ||
       observation.provider.find("csl.lp.highs@") != 0) {
        throw std::runtime_error("Hybrid optimizer differs from analytic minimum: control=" +
            std::to_string(observation.control) + ", terminal=" + std::to_string(observation.objective) +
            ", provider=" + observation.provider);
    }

    const auto verify_begin = Clock::now();
    auto candidate_result = synthesis::build_hybrid_path_optimal_face_candidate(
        programs[0], *branch.result, {1e-8, 1e-8});
    if(!std::holds_alternative<synthesis::HybridPathOptimalFaceCandidate>(candidate_result))
        throw std::runtime_error("Hybrid optimal-face candidate construction failed");
    std::vector<synthesis::HybridPathOptimalFaceCandidate> candidates;
    candidates.push_back(std::get<synthesis::HybridPathOptimalFaceCandidate>(std::move(candidate_result)));
    synthesis::OneStepScalarIntervalHybridFamilyVerifier verifier;
    auto verified = synthesis::verify_hybrid_portfolio_family(verifier, system, request, programs,
        candidates, {1, 8}, {1e-8, 1e-8});
    if(!std::holds_alternative<synthesis::HybridFamilyVerificationReport>(verified))
        throw std::runtime_error("Hybrid family verifier did not return a report");
    const auto& report = std::get<synthesis::HybridFamilyVerificationReport>(verified);
    if(report.branches.size() != 1) throw std::runtime_error("Hybrid verification branch count differs");
    observation.verifier = report.verifier_id;
    observation.verifier_version = report.verifier_version;
    observation.feasibility = status(report.branches[0].feasibility);
    observation.optimality = status(report.branches[0].objective_optimality);
    observation.coverage = status(report.branches[0].continuous_coverage);
    if(observation.feasibility != "established" || observation.optimality != "established" ||
       observation.coverage != "established" ||
       report.global_objective_optimality != synthesis::HybridVerificationStatus::established ||
       report.complete_family_coverage != synthesis::HybridVerificationStatus::established) {
        const auto& diagnostics = report.branches[0].diagnostics;
        throw std::runtime_error("Hybrid complete-family verification differs: feasibility=" +
            observation.feasibility + ", optimality=" + observation.optimality + ", coverage=" +
            observation.coverage + ", global=" + status(report.global_objective_optimality) +
            ", complete=" + status(report.complete_family_coverage) +
            (diagnostics.empty() ? std::string{} : ", diagnostic=" + diagnostics.front().explanation));
    }
    observation.verify_ns = static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(
        Clock::now() - verify_begin).count());
    observation.total_ns = static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(
        Clock::now() - total_begin).count());
    return observation;
}

void batch(const char* phase, std::size_t repetition, std::size_t calls) {
    std::uint64_t setup = 0, assembly = 0, solve = 0, verify = 0, total = 0;
    Observation last;
    std::size_t failures = 0;
    std::string error;
    for(std::size_t call = 0; call < calls; ++call) {
        try {
            last = run_once();
            setup += last.setup_ns;
            assembly += last.assembly_ns;
            solve += last.solve_ns;
            verify += last.verify_ns;
            total += last.total_ns;
        } catch(const std::exception& exception) {
            ++failures;
            error = exception.what();
        }
    }
    std::cout << "{\"phase\":\"" << phase << "\",\"repetition\":" << repetition
        << ",\"calls\":" << calls << ",\"failures\":" << failures
        << ",\"status\":\"" << (failures == 0 ? "passed" : "failed")
        << "\",\"path_count\":" << last.path_count << ",\"relation_rows\":" << last.relation_rows
        << ",\"relation_matrix_elements\":" << last.relation_matrix_elements
        << ",\"objective\":" << std::setprecision(17) << last.objective
        << ",\"objective_lower\":";
    if(last.objective_lower) std::cout << *last.objective_lower; else std::cout << "null";
    std::cout << ",\"objective_upper\":";
    if(last.objective_upper) std::cout << *last.objective_upper; else std::cout << "null";
    std::cout << ",\"primal_row_violation\":";
    if(last.primal_row_violation) std::cout << *last.primal_row_violation; else std::cout << "null";
    std::cout << ",\"primal_variable_violation\":";
    if(last.primal_variable_violation) std::cout << *last.primal_variable_violation; else std::cout << "null";
    std::cout
        << ",\"control\":" << last.control << ",\"provider\":\"" << last.provider
        << "\",\"termination\":\"" << last.termination << "\",\"outcome\":\"" << last.outcome
        << "\",\"verifier\":\"" << last.verifier << "\",\"verifier_version\":\""
        << last.verifier_version << "\",\"feasibility\":\"" << last.feasibility
        << "\",\"optimality\":\"" << last.optimality << "\",\"coverage\":\""
        << last.coverage << "\",\"setup_total_ns\":" << setup << ",\"assembly_total_ns\":" << assembly << ",\"solve_total_ns\":"
        << solve << ",\"verify_total_ns\":" << verify << ",\"end_to_end_total_ns\":" << total
        << ",\"error\":\"" << error << "\"}\n";
    if(failures != 0) throw std::runtime_error("One or more EXT-07 report calls failed");
}
}

int main(int argc, char** argv) try {
    if(argc != 2) throw std::runtime_error("Expected smoke or measure mode");
    const std::string mode{argv[1]};
    if(mode == "smoke") batch("smoke", 0, 1);
    else if(mode == "measure") {
        batch("warmup", 0, 10);
        for(std::size_t repetition = 0; repetition < 7; ++repetition) batch("trial", repetition, 20);
    } else throw std::runtime_error("Expected smoke or measure mode");
    return 0;
} catch(const std::exception& exception) {
    std::cerr << exception.what() << '\n';
    return 1;
}
