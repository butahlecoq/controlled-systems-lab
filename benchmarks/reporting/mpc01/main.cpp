#include "fixtures.hpp"
#include "hpipm_adapter.hpp"
#include "environment.hpp"
#include "osqp_adapter.hpp"
#include "timing.hpp"
#include "trajectory_evidence.hpp"

#include <csl/artifacts/comparison_manifest.hpp>
#include <csl/problem/resolved_problem.hpp>
#include <nlohmann/json.hpp>

#include <algorithm>
#include <charconv>
#include <cmath>
#include <iostream>
#include <fstream>
#include <filesystem>
#include <map>
#include <span>
#include <stdexcept>
#include <string>
#include <variant>

namespace {

using namespace csl::mpc01;
using json = nlohmann::json;
namespace ar = csl::artifacts;
using timing::Clock;
using timing::elapsed_ns;

template<class T> T take_artifact(ar::ArtifactResult<T> result) {
    if (const auto* error = std::get_if<ar::ArtifactError>(&result)) {
        throw std::runtime_error(error->path + ": " + error->message);
    }
    return std::get<T>(std::move(result));
}

template<class T> T take_csl(std::variant<T, csl::Diagnostic> result) {
    if (const auto* diagnostic = std::get_if<csl::Diagnostic>(&result)) {
        throw std::runtime_error(diagnostic->explanation);
    }
    return std::get<T>(std::move(result));
}

struct CapturedAttempt {
    NativeAttempt attempt;
    std::string start_mode;
    std::uint32_t repetition{};
    json event;
};

std::string termination_name(Termination value) {
    switch (value) {
        case Termination::completed: return "completed";
        case Termination::refused: return "refused";
        case Termination::unsupported: return "unsupported";
        case Termination::failed: return "failed";
        case Termination::timed_out: return "timed_out";
        case Termination::resource_limited: return "resource_limited";
        case Termination::cancelled: return "cancelled";
        case Termination::incomplete: return "incomplete";
    }
    return "incomplete";
}

std::string outcome_name(MathematicalOutcome value) {
    switch (value) {
        case MathematicalOutcome::optimal: return "optimal";
        case MathematicalOutcome::feasible: return "feasible";
        case MathematicalOutcome::infeasible: return "infeasible";
        case MathematicalOutcome::unbounded: return "unbounded";
        case MathematicalOutcome::undetermined: return "undetermined";
    }
    return "undetermined";
}

json optional_finite(double value) {
    return std::isfinite(value) ? json(value) : json(nullptr);
}

json serialize_attempt(const MpcCase& problem, const NativeAttempt& attempt,
                       const std::string& start_mode) {
    json row = {{"schema", "csl.mpc01-native-attempt/1"},
                {"case_id", problem.id},
                {"case_version", problem.version},
                {"input_sha256", problem.canonical_input_sha256},
                {"method", attempt.method},
                {"start_mode", start_mode},
                {"termination", termination_name(attempt.termination)},
                {"mathematical_outcome", outcome_name(attempt.outcome)},
                {"native_status", attempt.native_status},
                {"timings_ns", {{"formulation", attempt.formulation_ns},
                                {"setup", attempt.setup_ns},
                                {"warm_start", attempt.warm_start_ns},
                                {"solve", attempt.solve_ns},
                                {"extraction", attempt.extraction_ns}}},
                {"solver_iterations", attempt.solver_iterations
                    ? json(*attempt.solver_iterations) : json(nullptr)},
                {"warm_start_requested", attempt.warm_start_requested},
                {"warm_start_seed_applied", attempt.warm_start_seed_applied},
                {"factorization_in_setup", attempt.factorization_in_setup},
                {"factorization_in_solve", attempt.factorization_in_solve},
                {"solver_settings", attempt.method == "osqp-sparse-qp"
                    ? json{{"max_iter", 200000}, {"eps_abs", 1e-7}, {"eps_rel", 1e-7}, {"warm_starting", true}}
                    : json{{"mode", "BALANCE"}, {"max_iter", 1000}, {"tol_stat", 1e-8},
                           {"tol_eq", 1e-8}, {"tol_ineq", 1e-8}, {"tol_comp", 1e-8},
                           {"warm_start", attempt.warm_start_requested}}},
                {"diagnostics", attempt.diagnostics}};
    row["solver_objective"] = attempt.solver_objective
        && (attempt.outcome == MathematicalOutcome::optimal ||
            attempt.outcome == MathematicalOutcome::feasible)
        ? optional_finite(*attempt.solver_objective) : json(nullptr);
    row["original_objective"] = attempt.original_objective
        && (attempt.outcome == MathematicalOutcome::optimal ||
            attempt.outcome == MathematicalOutcome::feasible)
        ? optional_finite(*attempt.original_objective) : json(nullptr);
    if (attempt.witness) {
        const auto check = evidence::check_trajectory(problem, *attempt.witness);
        const bool has_usable_witness = attempt.outcome == MathematicalOutcome::optimal ||
                                        attempt.outcome == MathematicalOutcome::feasible;
        row[has_usable_witness ? "trajectory" : "candidate_iterate"] = {
            {"states", attempt.witness->states}, {"controls", attempt.witness->controls}};
        row[has_usable_witness ? "original_data_diagnostics" : "candidate_iterate_diagnostics"] = {
            {"checker", "binary64-residual-diagnostic/1"},
            {"evidence_status", "inconclusive"},
            {"max_dynamics_residual", check.dynamics_residual},
            {"max_state_bound_violation", check.state_bound_violation},
            {"max_control_bound_violation", check.control_bound_violation}};
    }
    return row;
}

ar::ResolvedConfiguration configuration(const std::string& backend_id,
                                         const std::string& version,
                                         const std::string& archive_sha256,
                                         const std::string& start_mode) {
    ar::ConfigurationInput input;
    input.collection = {false, ar::CollectionMode::summary, 0, 0, 0, 0};
    input.modules = {{"strategy", {{backend_id}, version,
        ar::PinAvailability{ar::Available<ar::ModulePin>{{ar::PinScope::source_archive, archive_sha256}}}}, {}}};
    const bool osqp = backend_id == "csl.external.osqp.sparse-qp";
    input.modules.front().options = {
        {"start_mode", ar::OptionScalar{start_mode}},
        {"native_defaults", ar::OptionScalar{osqp ? std::string{"osqp_set_default_settings"} : std::string{"d_ocp_qp_ipm_arg_set_default_BALANCE"}}},
        {"iteration_limit", ar::OptionScalar{std::int64_t{osqp ? 200000 : 1000}}},
        {"warm_start_enabled", ar::OptionScalar{osqp || start_mode == "warm_if_available"}}};
    if (osqp) {
        input.modules.front().options.push_back({"eps_abs", ar::OptionScalar{1e-7}});
        input.modules.front().options.push_back({"eps_rel", ar::OptionScalar{1e-7}});
    } else {
        input.modules.front().options.push_back({"tol_stat", ar::OptionScalar{1e-8}});
        input.modules.front().options.push_back({"tol_eq", ar::OptionScalar{1e-8}});
        input.modules.front().options.push_back({"tol_ineq", ar::OptionScalar{1e-8}});
        input.modules.front().options.push_back({"tol_comp", ar::OptionScalar{1e-8}});
        input.modules.front().options.push_back({"mode", ar::OptionScalar{std::string{"BALANCE"}}});
    }
    if (!osqp) {
        input.modules.push_back({"linear-algebra", {{"csl.external.blasfeo"},
            "d6251233923c9b475fe894fb729fb63ab693e301",
            ar::Available<ar::ModulePin>{{ar::PinScope::source_archive,
                "d2454027985a907f6fedb0c6a14e0e7825e586968309b38f7f02146db70770da"}}}, {}});
    }
    // Shared diagnostic request; native stopping settings are module options above.
    input.numerical = {1e-8, 1e-8};
    input.resources = {1, 1, 1, {}};
    input.output = {ar::OutputKind::program, csl::Assurance::numerical,
        csl::FamilyTarget::candidate_relaxation, {"csl.program.terminal-quadratic"}, {0, 0, {}, {}}};
    input.selector = {{"csl.selector.none"}, "1", {}};
    input.strategy = {{backend_id}, {}, {}, {}, {}, {}, {},
        input.selector.id, input.output.representation};
    input.workspace = ar::WorkspacePolicy::fresh;
    return take_artifact(ar::resolve_configuration(std::move(input)));
}

ar::AttemptStatus attempt_status(Termination termination) {
    switch (termination) {
        case Termination::completed: return ar::AttemptStatus::completed;
        case Termination::refused: return ar::AttemptStatus::refused;
        case Termination::unsupported: return ar::AttemptStatus::unsupported;
        case Termination::timed_out: return ar::AttemptStatus::timed_out;
        case Termination::resource_limited: return ar::AttemptStatus::resource_limited;
        case Termination::cancelled: return ar::AttemptStatus::cancelled;
        case Termination::failed: return ar::AttemptStatus::failed;
        case Termination::incomplete: return ar::AttemptStatus::incomplete;
    }
    return ar::AttemptStatus::incomplete;
}

ar::RecordedRunArtifact recorded_attempt(const MpcCase& problem, const CapturedAttempt& captured,
                                         std::string run_id, const std::string& backend_id,
                                         const std::string& version, const std::string& archive_sha256,
                                         const csl::ProblemId& problem_id,
                                         const csl::problem::ResolvedContent& input_content) {
    auto config = configuration(backend_id, version, archive_sha256, captured.start_mode);
    const ar::RunId run{std::move(run_id)};
    const ar::CollectionSettings settings{false, ar::CollectionMode::summary, 0, 0, 0, 0};
    auto statistics = take_artifact(ar::publish_collection({problem_id, config.identity(), run, settings,
        {}, {}, {}, ar::Unavailable{ar::MissingReason::collection_disabled, {}}, {}, {}}));
    const csl::ProgramIdentity subject{problem_id, {"csl.mpc01.nominal-open-loop"}};
    const csl::ProgramOutcomeClaim claim{subject, csl::MathematicalOutcome::undetermined,
        csl::Unestablished{}, {"Native solver status and binary64 residual diagnostics do not establish independent optimality or feasibility."}};
    const csl::Termination termination = captured.attempt.termination == Termination::completed
        ? csl::Termination::completed
        : captured.attempt.termination == Termination::timed_out ? csl::Termination::deadline_expired
        : captured.attempt.termination == Termination::resource_limited ? csl::Termination::resource_limit
        : captured.attempt.termination == Termination::cancelled ? csl::Termination::cancelled
        : captured.attempt.termination == Termination::refused || captured.attempt.termination == Termination::unsupported
            ? csl::Termination::operation_rejected
        : captured.attempt.termination == Termination::failed ? csl::Termination::numerical_failure
        : csl::Termination::contract_rejected;
    const auto event_bytes = captured.event.dump();
    auto event_content = take_csl(csl::problem::snapshot_content(std::as_bytes(
        std::span<const char>{event_bytes.data(), event_bytes.size()})));
    std::vector<ar::Attachment> attachments{
        {{"mpc01-input"}, ar::AttachmentRole::diagnostics, input_content.digest(),
            input_content.bytes().size(), "application/json", "csl.mpc01-canonical-input/1", {}, input_content},
        {{"native-attempt"}, ar::AttachmentRole::diagnostics, event_content.digest(),
            event_content.bytes().size(), "application/json", "csl.mpc01-native-attempt/1", {}, event_content}};
    csl::ProgramResult result{termination, claim, {}, {}, event_bytes, {}};
    ar::FinalOutcome final = ar::ProgramFinal{std::move(result), ar::AttachmentId{"native-attempt"}};
    if (captured.attempt.termination == Termination::unsupported)
        final = ar::UnsupportedFinal{{{csl::DiagnosticCode::unsupported, "native-solver", captured.attempt.diagnostics}}};
    else if (captured.attempt.termination == Termination::incomplete)
        final = ar::SkippedFinal{ar::SkippedReason::batch_failed};
    ar::RunRecord record{problem_id, {problem.state_dimension(), problem.control_dimension(), 0},
        problem.horizon(), std::move(config), run,
        std::move(final), statistics,
        {ar::Unavailable{ar::MissingReason::not_instrumented, {}},
         ar::Unavailable{ar::MissingReason::not_instrumented, {}},
         ar::Unavailable{ar::MissingReason::not_instrumented, {}},
         ar::Unavailable{ar::MissingReason::not_instrumented, {}}, false, ar::MemoryAccounting::unlimited},
        {}, std::move(attachments), ar::ProblemProvenance::identity_recorded, {}};
    return take_artifact(ar::encode_recorded_run(take_artifact(ar::publish_identity_recorded_run(std::move(record)))));
}

std::string comparison_record(const MpcCase& problem, std::vector<CapturedAttempt> attempts,
                              std::string_view executable, bool hpipm_first,
                              std::uint32_t repetitions) {
    if (attempts.size() != static_cast<std::size_t>(4) * repetitions)
        throw std::runtime_error("MPC comparison record does not contain every solver/start-mode repetition");
    std::stable_sort(attempts.begin(), attempts.end(), [](const auto& left, const auto& right) {
        const auto rank=[](const CapturedAttempt& attempt) {
            const auto method=attempt.attempt.method=="osqp-sparse-qp"?0:2;
            return method+(attempt.start_mode=="cold"?0:1);
        };
        const auto left_rank = rank(left);
        const auto right_rank = rank(right);
        if (left_rank != right_rank) return left_rank < right_rank;
        return left.repetition < right.repetition;
    });
    const auto input_content = take_csl(csl::problem::snapshot_content(std::as_bytes(
        std::span<const char>{problem.canonical_input_bytes.data(), problem.canonical_input_bytes.size()})));
    const csl::ProblemId problem_id{"csl.problem.v1.sha256:" + csl::problem::hex(input_content.digest())};
    std::vector<ar::ComparisonAttempt> ordered;
    json arms = json::array();
    std::optional<csl::problem::ContentDigest> request;
    for (std::size_t index = 0; index < attempts.size(); ++index) {
        const auto& captured = attempts[index];
        const auto arm = static_cast<std::uint32_t>(index / repetitions);
        const auto repetition = static_cast<std::uint32_t>(index % repetitions);
        const bool osqp = captured.attempt.method == "osqp-sparse-qp";
        if (!osqp && captured.attempt.method != "hpipm-structured-ocp-qp")
            throw std::runtime_error("Unknown MPC solver method");
        const std::string backend_id = osqp ? "csl.external.osqp.sparse-qp" : "csl.external.hpipm.structured-ocp-qp";
        const std::string strategy = backend_id;
        const std::string version = osqp ? "1.0.0" : "e3a56c1caddd7f12d125d84f337b9a9e5c186271";
        const std::string archive_sha256 = osqp
            ? "dd6a1c2e7e921485697d5e7cdeeb043c712526c395b3700601f51d472a7d8e48"
            : "97278f7c10a72387c574488701a1e85626df7f3fa3aea190ba41d1368a83aa4b";
        if (captured.repetition != repetition)
            throw std::runtime_error("MPC attempts are not ordered by arm and repetition");
        const auto run_id = problem.id + "-arm-" + std::to_string(arm) + "-r-" + std::to_string(repetition);
        auto run = recorded_attempt(problem, captured, run_id, backend_id, version, archive_sha256,
            problem_id, input_content);
        const auto current_request = take_artifact(ar::comparison_request_digest(run));
        if (request && *request != current_request)
            throw std::runtime_error("MPC solver attempts do not share the same normalized request");
        request = current_request;
        const auto config = take_artifact(ar::comparison_configuration_id(run));
        if (repetition == 0)
            arms.push_back({{"configuration_id", config.value}, {"strategy", strategy}, {"instrumentation", "disabled"}});
        const auto status = attempt_status(captured.attempt.termination);
        const json event = {{"schema", "csl.mpc01-comparison-event/1"},
            {"strategy", strategy}, {"instrumentation", "disabled"}, {"repetition", repetition},
            {"status", captured.attempt.termination == Termination::completed ? "passed" : termination_name(captured.attempt.termination)},
            {"attempt", captured.event}};
        ordered.push_back({arm, repetition, status,
            {ar::RunId{run_id}, run.content().digest()}, std::move(run), event.dump()});
    }
    const json spec_json = {{"arms", arms},
        {"input_manifest_hash", csl::problem::hex(input_content.digest())},
        {"input_manifest_source", "csl.mpc01-canonical-input/1"},
        {"problem_id", problem_id.value}, {"repetitions", repetitions},
        {"request_digest", csl::problem::hex(*request)},
        {"environment", csl::mpc01::environment_manifest(executable, hpipm_first)},
        {"schema", "csl.comparison-spec/3"}};
    const auto spec_bytes = spec_json.dump();
    const auto spec = take_csl(csl::problem::snapshot_content(std::as_bytes(
        std::span<const char>{spec_bytes.data(), spec_bytes.size()})));
    const auto comparison = take_artifact(ar::encode_recorded_comparison(spec, ordered));
    const auto bytes = comparison.content().bytes();
    const std::string wire(reinterpret_cast<const char*>(bytes.data()), bytes.size());
    (void)take_artifact(ar::decode_recorded_comparison(wire));
    return wire;
}

MpcCase take_fixture(FixtureLoad result) {
    if (const auto* error = std::get_if<std::string>(&result)) throw std::runtime_error(*error);
    return std::get<MpcCase>(std::move(result));
}

void run_single_attempt(const MpcCase& problem, std::string_view method,
                        std::string_view start_mode, std::uint32_t repetition) {
    NativeAttempt attempt;
    std::optional<NativeAttempt> warm_seed;
    if (method == "osqp-sparse-qp") {
        const auto map_start = Clock::now();
        const auto mapped = make_osqp_problem(problem);
        const auto map_end = Clock::now();
        if (const auto* error = std::get_if<ValidationError>(&mapped))
            throw std::runtime_error("OSQP map " + error->path + ": " + error->message);
        const auto& qp = std::get<SparseQp>(mapped);
        if (start_mode == "cold") {
            attempt = solve_osqp(problem, qp);
        } else {
            warm_seed = solve_osqp(problem, qp);
            warm_seed->formulation_ns = elapsed_ns(map_start, map_end);
            const auto warm_map_start = Clock::now();
            const auto warm_mapped = make_osqp_problem(problem);
            const auto warm_map_end = Clock::now();
            if (const auto* error = std::get_if<ValidationError>(&warm_mapped))
                throw std::runtime_error("OSQP warm map " + error->path + ": " + error->message);
            attempt = solve_osqp(problem, std::get<SparseQp>(warm_mapped), &*warm_seed);
            attempt.formulation_ns = elapsed_ns(warm_map_start, warm_map_end);
        }
        if (start_mode == "cold") attempt.formulation_ns = elapsed_ns(map_start, map_end);
    } else if (method == "hpipm-structured-ocp-qp") {
        const auto map_start = Clock::now();
        const auto mapped = make_hpipm_problem(problem);
        const auto map_end = Clock::now();
        if (const auto* error = std::get_if<ValidationError>(&mapped))
            throw std::runtime_error("HPIPM map " + error->path + ": " + error->message);
        const auto& qp = std::get<OcpQp>(mapped);
        if (start_mode == "cold") {
            attempt = solve_hpipm(problem, qp);
        } else {
            warm_seed = solve_hpipm(problem, qp);
            warm_seed->formulation_ns = elapsed_ns(map_start, map_end);
            const auto warm_map_start = Clock::now();
            const auto warm_mapped = make_hpipm_problem(problem);
            const auto warm_map_end = Clock::now();
            if (const auto* error = std::get_if<ValidationError>(&warm_mapped))
                throw std::runtime_error("HPIPM warm map " + error->path + ": " + error->message);
            attempt = solve_hpipm(problem, std::get<OcpQp>(warm_mapped), &*warm_seed);
            attempt.formulation_ns = elapsed_ns(warm_map_start, warm_map_end);
        }
        if (start_mode == "cold") attempt.formulation_ns = elapsed_ns(map_start, map_end);
    } else {
        throw std::runtime_error("Unsupported single-attempt solver method");
    }
    auto event = serialize_attempt(problem, attempt, std::string{start_mode});
    event["start_mode"] = start_mode;
    event["repetition"] = repetition;
    event["resource_scope"] = "one-native-attempt-process-tree";
    if (warm_seed) {
        event["warm_seed_native_status"] = warm_seed->native_status;
        event["warm_seed_timings_ns"] = {
            {"formulation", warm_seed->formulation_ns}, {"setup", warm_seed->setup_ns},
            {"solve", warm_seed->solve_ns}, {"extraction", warm_seed->extraction_ns}};
    }
    std::cout << event.dump() << '\n';
}

MpcCase single_fixture(std::string_view id) {
    if (id == "ts01") return make_ts01();
    if (id == "ts02") return make_ts02();
    if (id == "ts03-singular") return make_ts03_singular();
    if (id == "infeasible") return make_infeasible();
    if (id == "unbounded") return make_unbounded();
    if (id == "double-integrator-421")
        return take_fixture(load_double_integrator_421("examples/scenarios/double-integrator-generality.json"));
    if (id == "b04-reference-v1")
        return take_fixture(load_b04_reference_v1("docs/research/evidence/b04-reference-v1/canonical-case.json"));
    throw std::runtime_error("Unknown MPC fixture ID");
}

Termination parse_termination(std::string_view value) {
    if (value == "completed") return Termination::completed;
    if (value == "refused") return Termination::refused;
    if (value == "unsupported") return Termination::unsupported;
    if (value == "failed") return Termination::failed;
    if (value == "timed_out") return Termination::timed_out;
    if (value == "resource_limited") return Termination::resource_limited;
    if (value == "cancelled") return Termination::cancelled;
    if (value == "incomplete") return Termination::incomplete;
    throw std::runtime_error("Unknown saved attempt termination");
}

MathematicalOutcome parse_outcome(std::string_view value) {
    if (value == "optimal") return MathematicalOutcome::optimal;
    if (value == "feasible") return MathematicalOutcome::feasible;
    if (value == "infeasible") return MathematicalOutcome::infeasible;
    if (value == "unbounded") return MathematicalOutcome::unbounded;
    if (value == "undetermined") return MathematicalOutcome::undetermined;
    throw std::runtime_error("Unknown saved mathematical outcome");
}

NativeAttempt parse_native_attempt(const json& event) {
    NativeAttempt attempt;
    attempt.method = event.at("method").get<std::string>();
    attempt.termination = parse_termination(event.at("termination").get<std::string>());
    attempt.outcome = parse_outcome(event.at("mathematical_outcome").get<std::string>());
    attempt.native_status = event.at("native_status").get<std::string>();
    const auto& timings = event.at("timings_ns");
    attempt.formulation_ns = timings.at("formulation").get<std::uint64_t>();
    attempt.setup_ns = timings.at("setup").get<std::uint64_t>();
    attempt.warm_start_ns = timings.at("warm_start").get<std::uint64_t>();
    attempt.solve_ns = timings.at("solve").get<std::uint64_t>();
    attempt.extraction_ns = timings.at("extraction").get<std::uint64_t>();
    if (!event.at("solver_iterations").is_null())
        attempt.solver_iterations = event.at("solver_iterations").get<std::uint64_t>();
    attempt.factorization_in_setup = event.at("factorization_in_setup").get<bool>();
    attempt.factorization_in_solve = event.at("factorization_in_solve").get<bool>();
    attempt.warm_start_requested = event.at("warm_start_requested").get<bool>();
    attempt.warm_start_seed_applied = event.at("warm_start_seed_applied").get<bool>();
    attempt.diagnostics = event.at("diagnostics").get<std::string>();
    if (!event.at("solver_objective").is_null())
        attempt.solver_objective = event.at("solver_objective").get<double>();
    if (!event.at("original_objective").is_null())
        attempt.original_objective = event.at("original_objective").get<double>();
    const char* trajectory_key = event.contains("trajectory") ? "trajectory"
        : event.contains("candidate_iterate") ? "candidate_iterate" : nullptr;
    if (trajectory_key != nullptr) {
        const auto& trajectory = event.at(trajectory_key);
        attempt.witness = Trajectory{trajectory.at("states").get<std::vector<Vector>>(),
                                     trajectory.at("controls").get<std::vector<Vector>>()};
    }
    return attempt;
}

void build_records_from_attempts(const std::filesystem::path& input_path,
                                 const std::filesystem::path& output_path,
                                 std::string_view executable) {
    if (std::filesystem::exists(output_path))
        throw std::runtime_error("Comparison-record output already exists");
    std::map<std::string, MpcCase> cases;
    for (const auto id : {"ts01", "ts02", "ts03-singular", "infeasible", "unbounded",
                          "double-integrator-421", "b04-reference-v1"}) {
        auto problem = single_fixture(id);
        cases.emplace(problem.id, std::move(problem));
    }
    std::map<std::string, std::vector<CapturedAttempt>> grouped;
    std::ifstream input(input_path);
    if (!input) throw std::runtime_error("Cannot open saved per-attempt events");
    std::string line;
    std::uint32_t repetitions = 0;
    while (std::getline(input, line)) {
        if (line.empty()) continue;
        const auto event = json::parse(line);
        if (event.at("schema") != "csl.mpc01-native-attempt/1")
            throw std::runtime_error("Unsupported saved native-attempt schema");
        const auto case_id = event.at("case_id").get<std::string>();
        const auto found = cases.find(case_id);
        if (found == cases.end()) throw std::runtime_error("Attempt references an unknown MPC fixture");
        const auto repetition = event.at("repetition").get<std::uint32_t>();
        repetitions = std::max(repetitions, repetition + 1);
        const auto start_mode = event.at("start_mode").get<std::string>();
        grouped[case_id].push_back({parse_native_attempt(event), start_mode, repetition, event});
    }
    if (input.bad() || grouped.size() != cases.size() || repetitions == 0)
        throw std::runtime_error("Saved per-attempt events are incomplete");
    std::ofstream output(output_path, std::ios::binary);
    if (!output) throw std::runtime_error("Cannot create comparison-record output");
    for (const auto& [case_id, problem] : cases) {
        const auto& attempts = grouped.at(case_id);
        if (attempts.size() != static_cast<std::size_t>(4) * repetitions)
            throw std::runtime_error("Saved fixture lacks a complete solver/start-mode repetition matrix");
        output << comparison_record(problem, attempts, executable, false, repetitions) << '\n';
        output.flush();
        if (!output) throw std::runtime_error("Cannot write canonical comparison record");
    }
}

void run_case(const MpcCase& problem, bool hpipm_first, std::uint32_t repetitions,
              std::ostream* records, std::string_view executable) {
    std::vector<CapturedAttempt> attempts;
    attempts.reserve(static_cast<std::size_t>(4) * repetitions);
    const auto capture = [&](const NativeAttempt& attempt, const std::string& start_mode,
                             std::uint32_t repetition) {
        auto event = serialize_attempt(problem, attempt, start_mode);
        std::cout << event.dump() << '\n';
        attempts.push_back({attempt, start_mode, repetition, std::move(event)});
    };
    const auto run_osqp = [&](std::uint32_t repetition) {
        const auto map_start = Clock::now();
        const auto mapped = make_osqp_problem(problem);
        const auto map_end = Clock::now();
        if (const auto* error = std::get_if<ValidationError>(&mapped)) {
            throw std::runtime_error("OSQP map " + error->path + ": " + error->message);
        }
        auto cold = solve_osqp(problem, std::get<SparseQp>(mapped));
        cold.formulation_ns = elapsed_ns(map_start, map_end);
        capture(cold, "cold", repetition);
        const auto warm_map_start = Clock::now();
        const auto warm_mapped = make_osqp_problem(problem);
        const auto warm_map_end = Clock::now();
        if (const auto* error = std::get_if<ValidationError>(&warm_mapped)) {
            throw std::runtime_error("OSQP warm map " + error->path + ": " + error->message);
        }
        auto warm = solve_osqp(problem, std::get<SparseQp>(warm_mapped),
                               &cold);
        warm.formulation_ns = elapsed_ns(warm_map_start, warm_map_end);
        capture(warm, "warm_if_available", repetition);
    };
    const auto run_hpipm = [&](std::uint32_t repetition) {
        const auto map_start = Clock::now();
        const auto mapped = make_hpipm_problem(problem);
        const auto map_end = Clock::now();
        if (const auto* error = std::get_if<ValidationError>(&mapped)) {
            throw std::runtime_error("HPIPM map " + error->path + ": " + error->message);
        }
        auto cold = solve_hpipm(problem, std::get<OcpQp>(mapped));
        cold.formulation_ns = elapsed_ns(map_start, map_end);
        capture(cold, "cold", repetition);
        const auto warm_map_start = Clock::now();
        const auto warm_mapped = make_hpipm_problem(problem);
        const auto warm_map_end = Clock::now();
        if (const auto* error = std::get_if<ValidationError>(&warm_mapped)) {
            throw std::runtime_error("HPIPM warm map " + error->path + ": " + error->message);
        }
        auto warm = solve_hpipm(problem, std::get<OcpQp>(warm_mapped),
                                &cold);
        warm.formulation_ns = elapsed_ns(warm_map_start, warm_map_end);
        capture(warm, "warm_if_available", repetition);
    };
    for (std::uint32_t repetition = 0; repetition < repetitions; ++repetition) {
        const bool hpipm_this_repetition = hpipm_first ? repetition % 2 == 0 : repetition % 2 != 0;
        if (hpipm_this_repetition) {
            run_hpipm(repetition);
            run_osqp(repetition);
        } else {
            run_osqp(repetition);
            run_hpipm(repetition);
        }
    }
    if (records) {
        *records << comparison_record(problem, std::move(attempts),
            executable, hpipm_first, repetitions) << '\n';
        records->flush();
        if (!*records) throw std::runtime_error("Cannot write MPC comparison record");
    }
}

} // namespace

int main(int argc, char** argv) {
    try {
        if (argc == 4 && std::string(argv[1]) == "--records-from-attempts") {
            build_records_from_attempts(argv[2], argv[3], argv[0]);
            return 0;
        }
        if (argc == 6 && std::string(argv[1]) == "--single-attempt") {
            std::uint32_t repetition = 0;
            const std::string value = argv[5];
            const auto [end, error] = std::from_chars(value.data(), value.data() + value.size(), repetition);
            if (error != std::errc{} || end != value.data() + value.size())
                throw std::runtime_error("repetition must be an unsigned integer");
            if (std::string_view(argv[4]) != "cold" && std::string_view(argv[4]) != "warm_if_available")
                throw std::runtime_error("start mode must be cold or warm_if_available");
            run_single_attempt(single_fixture(argv[2]), argv[3], argv[4], repetition);
            return 0;
        }
        if (argc == 3 && std::string(argv[1]) == "--verify-records") {
            std::ifstream input(argv[2], std::ios::binary);
            if (!input) throw std::runtime_error("Cannot open comparison records");
            std::string line;
            std::size_t count = 0;
            while (std::getline(input, line)) {
                (void)take_artifact(ar::decode_recorded_comparison(line));
                ++count;
            }
            if (input.bad() || count == 0) throw std::runtime_error("Empty or unreadable comparison records");
            std::cout << "verified " << count << " comparison records\n";
            return 0;
        }
        if (argc < 3) {
            std::cerr << "usage: csl_mpc01_report --single-attempt <fixture-id> <solver-method> <cold|warm_if_available> <repetition>\n       csl_mpc01_report --records-from-attempts <native-attempts.jsonl> <new-records.jsonl>\n       csl_mpc01_report <double-integrator-generality.json> <b04-reference-v1/canonical-case.json> [--reverse] [--repetitions <positive-count>] [--records <new-file.jsonl>]\n";
            return 2;
        }
        bool hpipm_first = false;
        std::uint32_t repetitions = 1;
        std::optional<std::filesystem::path> record_path;
        for (int i = 3; i < argc; ++i) {
            const std::string option = argv[i];
            if (option == "--reverse") hpipm_first = true;
            else if (option == "--repetitions" && i + 1 < argc) {
                const std::string value = argv[++i];
                const auto [end, error] = std::from_chars(value.data(), value.data() + value.size(), repetitions);
                if (error != std::errc{} || end != value.data() + value.size() || repetitions == 0 || repetitions > 1000)
                    throw std::runtime_error("--repetitions must be an integer from 1 to 1000");
            }
            else if (option == "--records" && i + 1 < argc && !record_path) record_path = argv[++i];
            else throw std::runtime_error("Unknown or incomplete MPC runner option: " + option);
        }
        std::ofstream record_file;
        if (record_path) {
            if (std::filesystem::exists(*record_path)) throw std::runtime_error("Record output already exists");
            record_file.open(*record_path, std::ios::binary);
            if (!record_file) throw std::runtime_error("Cannot create record output");
        }
        auto* records = record_path ? &record_file : nullptr;
        run_case(make_ts01(), hpipm_first, repetitions, records, argv[0]);
        run_case(make_ts02(), hpipm_first, repetitions, records, argv[0]);
        run_case(make_ts03_singular(), hpipm_first, repetitions, records, argv[0]);
        run_case(make_infeasible(), hpipm_first, repetitions, records, argv[0]);
        run_case(make_unbounded(), hpipm_first, repetitions, records, argv[0]);
        run_case(take_fixture(load_double_integrator_421(argv[1])), hpipm_first, repetitions, records, argv[0]);
        run_case(take_fixture(load_b04_reference_v1(argv[2])), hpipm_first, repetitions, records, argv[0]);
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "MPC-01 run failed: " << error.what() << '\n';
        return 1;
    }
}
