#include <csl/adapters/convex/highs.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <csl/adapters/polyhedral/qhull.hpp>
#include <csl/application/comparison.hpp>
#include <csl/execution/observability.hpp>
#include <csl/geometry/affine_sum.hpp>
#include <csl/input/scenario_loader.hpp>
#include <csl/synthesis/strategy_a/strategy.hpp>
#include <csl/synthesis/strategy_b/direct_joint.hpp>
#include <csl/synthesis/witness_selector.hpp>

#include <array>
#include <charconv>
#include <stdexcept>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <optional>
#include <string>
#include <string_view>
#include <type_traits>
#include <variant>

#if defined(_WIN32)
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#else
#include <fcntl.h>
#include <sys/file.h>
#include <unistd.h>
#endif

namespace {
using namespace csl;
using namespace csl::registry;

const char* category_name(input::InputCategory category) {
    using input::InputCategory;
    switch (category) {
    case InputCategory::syntax: return "syntax";
    case InputCategory::encoding: return "encoding";
    case InputCategory::schema: return "schema";
    case InputCategory::field: return "field";
    case InputCategory::io: return "io";
    case InputCategory::limit: return "limit";
    }
    return "unknown";
}

template<class T, class... Others>
T take(std::variant<T, Others...> result, std::string_view stage) {
    if (auto* value = std::get_if<T>(&result)) return std::move(*value);
    std::string message(stage);
    message += " failed";
    std::visit([&](const auto& error) {
        using E = std::decay_t<decltype(error)>;
        if constexpr (std::is_same_v<E, Rejection>) {
            for (const auto& diagnostic : error.diagnostics)
                message += ": " + diagnostic.field + " " + diagnostic.explanation;
        } else if constexpr (std::is_same_v<E, Diagnostics>) {
            for (const auto& diagnostic : error)
                message += ": " + diagnostic.field + " " + diagnostic.explanation;
        } else if constexpr (std::is_same_v<E, Unsupported>) {
            for (const auto& diagnostic : error.diagnostics)
                message += ": " + diagnostic.field + " " + diagnostic.explanation;
        } else if constexpr (requires { error.message; }) {
            message += ": " + error.message;
        }
    }, result);
    throw std::runtime_error(message);
}

template<class Port>
PreparedProvider<Port> selected(Registration<Port> entry, std::string representation) {
    Registry<Port> registry;
    const Method method{entry.identity.id, entry.identity.version};
    if (registry.add(std::move(entry))) throw std::runtime_error("Provider registration failed");
    Requirements requirements;
    requirements.output.representation = {std::move(representation)};
    if constexpr (std::is_same_v<Port, GeometryPort> || std::is_same_v<Port, ConversionPort>)
        requirements.output.relation = SetRelation::equivalent;
    return take(prepare_provider(select_provider(registry, method, requirements)), "Provider selection");
}

struct Modules {
    std::shared_ptr<Registry<GeometryPort>> projections;
    std::shared_ptr<Registry<GeometryPort>> affines;
    std::shared_ptr<Registry<ConversionPort>> conversions;
    std::shared_ptr<Registry<LPPort>> lps;
    std::shared_ptr<Registry<ConvexPort>> convexes;
    StrategyRegistry strategies;
    Registry<SelectorPort> selectors;
    PreparedProvider<LPPort> membership;
    Identity lp_identity;
    Identity convex_identity;
    Identity selector_identity;
};

Modules make_modules() {
    auto lp = take(adapters::lp::make_highs_registration(), "LP registration");
    auto convex = take(adapters::convex::make_highs_registration(), "Convex registration");
    auto converter = take(adapters::polyhedral::make_qhull_registration(lp), "Conversion registration");
    auto projection = geometry::polyhedral::make_projection_registration();
    auto affine = geometry::make_affine_sum_registration({
        selected(geometry::make_lp_hull_reducer_registration(), ""),
        selected(lp, "csl.program-result.v1"),
        selected(converter, "csl.polyhedron.v")});

    auto projections = std::make_shared<Registry<GeometryPort>>();
    auto affines = std::make_shared<Registry<GeometryPort>>();
    auto conversions = std::make_shared<Registry<ConversionPort>>();
    auto lps = std::make_shared<Registry<LPPort>>();
    auto convexes = std::make_shared<Registry<ConvexPort>>();
    const Method pm{projection.identity.id, {}}, am{affine.identity.id, {}},
        cm{converter.identity.id, {}}, lm{lp.identity.id, {}}, qm{convex.identity.id, {}};
    if (projections->add(projection) || affines->add(affine) || conversions->add(converter) ||
        lps->add(lp) || convexes->add(convex))
        throw std::runtime_error("Provider registry registration failed");

    Requirements h, v, program;
    h.output.representation = {"csl.polyhedron.h"};
    h.output.relation = SetRelation::equivalent;
    v.output.representation = {"csl.polyhedron.v"};
    v.output.relation = SetRelation::equivalent;
    program.output.representation = {"csl.program-result.v1"};
    auto providers = take(check_providers(
        select_provider(*projections, pm, h), select_provider(*affines, am, v),
        select_provider(*conversions, cm, h), select_provider(*lps, lm, program),
        select_provider(*convexes, qm, program)), "Strategy provider selection");
    auto membership = take(prepare_provider(select_provider(*lps, lm, program)),
        "Membership provider selection");

    Modules modules{std::move(projections), std::move(affines), std::move(conversions),
        std::move(lps), std::move(convexes), {}, {}, std::move(membership),
        lp.identity, convex.identity, {}};
    if (modules.strategies.add(synthesis::strategy_a::make_registration(std::move(providers))) ||
        modules.strategies.add(synthesis::strategy_b::make_registration(*modules.lps, *modules.convexes)))
        throw std::runtime_error("Strategy registration failed");
    auto selector = synthesis::witness_selector::make_registration(modules.membership);
    modules.selector_identity = selector.identity;
    if (modules.selectors.add(std::move(selector)))
        throw std::runtime_error("Selector registration failed");
    return modules;
}

struct Options {
    enum class Mode { none, validate, run } mode{Mode::none};
    std::filesystem::path scenario;
    std::optional<std::string> profile;
    std::optional<std::string> lp;
    std::optional<std::string> convex;
    std::optional<std::size_t> seed;
    std::optional<std::size_t> threads;
    std::optional<std::filesystem::path> output_directory;
};

std::optional<std::size_t> positive_integer(std::string_view text) {
    std::size_t value{};
    const auto result = std::from_chars(text.data(), text.data() + text.size(), value);
    if (result.ec != std::errc{} || result.ptr != text.data() + text.size() || value == 0)
        return std::nullopt;
    return value;
}

bool parse_options(int argc, char** argv, Options& options) {
    if (argc == 3 && std::string_view(argv[1]) == "--validate-only") {
        options.mode = Options::Mode::validate;
        options.scenario = argv[2];
        return true;
    }
    if (argc < 3 || std::string_view(argv[1]) != "--run") return false;
    options.mode = Options::Mode::run;
    options.scenario = argv[2];
    for (int index = 3; index < argc; ++index) {
        const std::string_view flag(argv[index]);
        if (index + 1 >= argc) return false;
        const std::string_view value(argv[++index]);
        if (value.empty()) return false;
        if (flag == "--profile") options.profile = std::string(value);
        else if (flag == "--lp") options.lp = std::string(value);
        else if (flag == "--convex") options.convex = std::string(value);
        else if (flag == "--seed") {
            options.seed = positive_integer(value);
            if (!options.seed) return false;
        } else if (flag == "--threads") {
            options.threads = positive_integer(value);
            if (!options.threads) return false;
        } else if (flag == "--output-dir") options.output_directory = std::filesystem::path(value);
        else return false;
    }
    return true;
}

void print_input_error(const input::LoadResult& loaded) {
    if (const auto* error = std::get_if<input::InputFailure>(&loaded)) {
        std::cerr << "Input rejected: category=" << category_name(error->category)
                  << " path=" << error->path << " observed=" << error->observed
                  << "; expected " << error->expected << '\n';
    } else if (const auto* unsupported = std::get_if<input::UnsupportedInput>(&loaded)) {
        std::cerr << "Input unsupported: path=" << unsupported->path
                  << " feature=" << unsupported->feature << "; expected "
                  << unsupported->expected << '\n';
    } else if (const auto* stopped = std::get_if<OperationStopped>(&loaded)) {
        std::cerr << "Input stopped: " << stopped->diagnostics << '\n';
    } else if (const auto* historical = std::get_if<input::HistoricalScenario>(&loaded)) {
        const auto record = historical->record();
        std::cerr << "Input unsupported: historical scenario " << record->id
                  << " is non-executable; " << record->execution_gate << '\n';
    }
}

int validate(const input::LoadedScenario& scenario) {
    const auto problem = scenario.problem();
    const auto source = scenario.source();
    const auto requested = scenario.requested_run();
    const auto dimensions = problem.model().dimensions();
    std::cout << "validation=valid schema=" << source->schema
              << " problem=" << problem.identity().value
              << " source_sha256=" << problem::hex(source->content.digest())
              << " horizon=" << problem.model().horizon()
              << " state_dimension=" << dimensions.state
              << " control_dimension=" << dimensions.control
              << " requested=";
    if (std::holds_alternative<input::ComparisonRequest>(requested->selection)) {
        std::cout << "comparison";
    } else {
        std::cout << "explicit_methods count="
                  << std::get<std::vector<input::ModuleRequest>>(requested->selection).size();
    }
    std::cout << " mode=validate_only solvers=not_invoked\n";
    return 0;
}

bool has_unsupported_backend(const input::RequestedRun& requested) {
    for (const auto& [role, value] : requested.backends) {
        if (role != input::BackendRole::lp && role != input::BackendRole::convex) {
            std::cerr << "Input unsupported: path=/run/backends feature=backend_override:"
                      << static_cast<int>(role) << "; this CLI supports only lp and convex overrides\n";
            return true;
        }
        if (value.version) {
            std::cerr << "Input unsupported: path=/run/backends versioned backend selection; "
                         "the current strategy configuration contract accepts backend IDs only\n";
            return true;
        }
    }
    return false;
}

std::string backend_id(const input::RequestedRun& requested, input::BackendRole role,
    const std::optional<std::string>& override, std::string_view fallback) {
    if (override) return *override;
    const auto found = requested.backends.find(role);
    if (found != requested.backends.end()) return found->second.id.value;
    return std::string(fallback);
}

std::string_view termination_name(Termination value) {
    switch (value) {
    case Termination::completed: return "completed";
    case Termination::cancelled: return "cancelled";
    case Termination::resource_limit: return "resource_limit";
    case Termination::numerical_failure: return "numerical_failure";
    case Termination::operation_rejected: return "operation_rejected";
    case Termination::contract_rejected: return "contract_rejected";
    }
    return "unknown";
}

std::string_view outcome_name(MathematicalOutcome value) {
    switch (value) {
    case MathematicalOutcome::optimal: return "optimal";
    case MathematicalOutcome::infeasible: return "infeasible";
    case MathematicalOutcome::unbounded: return "unbounded";
    case MathematicalOutcome::infimum_not_attained: return "infimum_not_attained";
    case MathematicalOutcome::undetermined: return "undetermined";
    }
    return "unknown";
}
template<class T>
bool passed(const T& value) {
    return value == verification::CheckStatus::numerical_pass;
}

int persist(const problem::ResolvedProblem& problem, const application::PreparedComparison& prepared,
    const application::ComparisonExecution& execution, const Modules& modules, const ResourcePolicy& resources, const WitnessRequest& witnesses,
    const std::filesystem::path& directory) {
    namespace ar = artifacts;
    namespace ob = csl::execution::observability;
    std::error_code ec;
    if (!std::filesystem::exists(directory, ec)) {
        std::filesystem::create_directories(directory, ec);
        if (ec) {
            std::cerr << "Output rejected: cannot create directory " << directory.string()
                      << ": " << ec.message() << '\n';
            return 2;
        }
    }
    if (ec || !std::filesystem::is_directory(directory, ec) || ec) {
        std::cerr << "Output rejected: not a writable directory " << directory.string() << '\n';
        return 2;
    }

    struct PublicationLock {
#if defined(_WIN32)
        HANDLE handle{INVALID_HANDLE_VALUE};
        OVERLAPPED overlap{};
#else
        int descriptor{-1};
#endif
        bool acquire(const std::filesystem::path& directory) {
            const auto path = directory / ".scenario-cli-publish.lock";
#if defined(_WIN32)
            handle = CreateFileW(path.c_str(), GENERIC_READ | GENERIC_WRITE,
                FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_ALWAYS,
                FILE_ATTRIBUTE_NORMAL, nullptr);
            if (handle == INVALID_HANDLE_VALUE) return false;
            if (!LockFileEx(handle, LOCKFILE_EXCLUSIVE_LOCK | LOCKFILE_FAIL_IMMEDIATELY,
                    0, MAXDWORD, MAXDWORD, &overlap)) {
                CloseHandle(handle);
                handle = INVALID_HANDLE_VALUE;
                return false;
            }
            return true;
#else
            descriptor = ::open(path.string().c_str(), O_CREAT | O_RDWR, 0666);
            if (descriptor < 0) return false;
            if (::flock(descriptor, LOCK_EX | LOCK_NB) != 0) {
                ::close(descriptor);
                descriptor = -1;
                return false;
            }
            return true;
#endif
        }
        ~PublicationLock() {
#if defined(_WIN32)
            if (handle != INVALID_HANDLE_VALUE) {
                UnlockFileEx(handle, 0, MAXDWORD, MAXDWORD, &overlap);
                CloseHandle(handle);
            }
#else
            if (descriptor >= 0) {
                ::flock(descriptor, LOCK_UN);
                ::close(descriptor);
            }
#endif
        }
    } publication_lock;
    if (!publication_lock.acquire(directory)) {
        std::cerr << "Output rejected: cannot acquire paired publication lock in "
                  << directory.string() << ": another publication may be in progress\n";
        return 2;
    }

    constexpr std::array<std::string_view, 2> names{"reach-back", "strategy-b"};
    std::array<std::filesystem::path, 2> targets{
        directory / "reach-back.run.json", directory / "strategy-b.run.json"};
    for (const auto& target : targets) {
        if (std::filesystem::exists(target, ec) || ec) {
            std::cerr << "Output rejected: refusing to replace existing file "
                      << target.string() << '\n';
            return 2;
        }
    }

    std::array<std::string, 2> encoded;
    for (std::size_t index = 0; index < execution.strategies.size(); ++index) {
        const auto& expected = prepared.expected_synthesis_identity(index);
        const auto unavailable = ar::Unavailable{ar::MissingReason::not_instrumented, {}};
        ar::ConfigurationInput input;
        input.collection = {false, ar::CollectionMode::detail, 0, 0, 0, 0};
        input.modules = {
            {"strategy", {expected.strategy, expected.strategy_version, unavailable}, {}},
            {"lp", {prepared.strategies()[index].lp, modules.lp_identity.version, unavailable}, {}},
            {"convex", {prepared.strategies()[index].convex, modules.convex_identity.version, unavailable}, {}}};
        input.numerical = prepared.family().numerical;
        input.resources = resources;
        input.output = {ar::OutputKind::synthesis, prepared.family().assurance,
            prepared.family().target, prepared.family().representation, witnesses};
        input.selector = {modules.selector_identity.id, modules.selector_identity.version, {}};
        input.strategy = prepared.strategies()[index];
        input.strategy.selector = modules.selector_identity.id;
        const ar::RunId run{"scenario-cli-" + std::string(names[index])};
        const auto configuration = ar::resolve_configuration(std::move(input));
        const auto* configuration_error = std::get_if<ar::ArtifactError>(&configuration);
        if (configuration_error) {
            std::cerr << "Artifact export rejected: code=" << static_cast<int>(configuration_error->code)
                      << " path=" << configuration_error->path << " message="
                      << configuration_error->message << '\n';
            return 3;
        }
        const auto resolved_configuration = std::get<ar::ResolvedConfiguration>(configuration);
        const auto plan = ob::make_collection_plan({problem, resolved_configuration, run, {}, {}, 0});
        const auto* plan_error = std::get_if<ar::ArtifactError>(&plan);
        if (plan_error) {
            std::cerr << "Artifact export rejected: code=" << static_cast<int>(plan_error->code)
                      << " path=" << plan_error->path << " message=" << plan_error->message << '\n';
            return 3;
        }
        const auto statistics = ob::merge_observations(std::get<ob::CollectionPlan>(plan), {});
        const auto* statistics_error = std::get_if<ar::ArtifactError>(&statistics);
        if (statistics_error) {
            std::cerr << "Artifact export rejected: code=" << static_cast<int>(statistics_error->code)
                      << " path=" << statistics_error->path << " message="
                      << statistics_error->message << '\n';
            return 3;
        }
        const auto resource_unavailable = ar::Unavailable{ar::MissingReason::not_instrumented, {}};
        const auto artifact = application::encode_strategy_run(problem, execution.strategies[index],
            resolved_configuration, run, std::get<ar::CollectedStatistics>(statistics),
            {resource_unavailable, resource_unavailable, resource_unavailable, resource_unavailable,
                true, ar::MemoryAccounting::unlimited});
        if (const auto* error = std::get_if<ar::ArtifactError>(&artifact)) {
            std::cerr << "Artifact export rejected: code=" << static_cast<int>(error->code)
                      << " path=" << error->path << " message=" << error->message << '\n';
            return 3;
        }
        encoded[index] = std::get<std::string>(artifact);
    }

    std::array<std::filesystem::path, 2> temporary{targets[0].string() + ".tmp", targets[1].string() + ".tmp"};
    for (const auto& path : temporary) {
        if (std::filesystem::exists(path, ec) || ec) {
            std::cerr << "Output rejected: refusing to replace existing temporary file "
                      << path.string() << '\n';
            return 2;
        }
    }
    for (std::size_t index = 0; index < encoded.size(); ++index) {
        std::ofstream file(temporary[index], std::ios::binary | std::ios::out);
        if (!file || !(file << encoded[index]) || !file.flush()) {
            std::cerr << "Output rejected: cannot write " << temporary[index].string() << '\n';
            for (const auto& path : temporary) std::filesystem::remove(path, ec);
            return 2;
        }
    }
    for (std::size_t index = 0; index < encoded.size(); ++index) {
        std::filesystem::rename(temporary[index], targets[index], ec);
        if (ec) {
            std::cerr << "Output rejected: cannot publish " << targets[index].string()
                      << ": " << ec.message() << '\n';
            for (std::size_t remaining = index; remaining < temporary.size(); ++remaining)
                std::filesystem::remove(temporary[remaining], ec);
            if (index > 0) {
                std::error_code rollback_error;
                std::filesystem::remove(targets[index - 1], rollback_error);
                if (rollback_error)
                    std::cerr << "Output rollback failed: cannot remove "
                              << targets[index - 1].string() << ": "
                              << rollback_error.message() << '\n';
            }
            return 2;
        }
    }
    std::cout << "artifacts_saved=" << targets[0].string() << ',' << targets[1].string() << '\n';
    return 0;
}

int run(const input::LoadedScenario& scenario, const Options& options) {
    const auto requested = scenario.requested_run();
    if (!std::holds_alternative<input::ComparisonRequest>(requested->selection)) {
        std::cerr << "Input unsupported: path=/run/methods; expected the default paired comparison request\n";
        return 2;
    }
    if (has_unsupported_backend(*requested)) return 2;
    const std::string profile = options.profile.value_or("ts01_exact_integrator");
    if (profile != "ts01_exact_integrator" && profile != "ts02_constant_integrator") {
        std::cerr << "Unsupported profile: " << profile << "; expected ts01_exact_integrator or ts02_constant_integrator\n";
        return 2;
    }
    if (requested->representation && requested->representation->value != "csl.polyhedron.h") {
        std::cerr << "Input unsupported: path=/run/backends/representation observed="
                  << requested->representation->value << "; expected csl.polyhedron.h\n";
        return 2;
    }

    const auto problem = scenario.problem();
    FamilyRequest family;
    family.profile = profile;
    family.objective = problem.identity();
    family.target = FamilyTarget::exact_optimal_relation;
    family.assurance = Assurance::numerical;
    family.representation = {"csl.polyhedron.h"};
    if (requested->numerical) family.numerical = *requested->numerical;

    const auto lp_id = backend_id(*requested, input::BackendRole::lp, options.lp, "csl.lp.highs");
    const auto convex_id = backend_id(*requested, input::BackendRole::convex, options.convex, "csl.convex.highs");
    StrategyConfiguration reach_back;
    reach_back.strategy = {"csl.synthesis.reach-back"};
    reach_back.lp = {lp_id};
    reach_back.convex = {convex_id};
    reach_back.representation = family.representation;
    StrategyConfiguration direct = reach_back;
    direct.strategy = {"csl.synthesis.strategy-b"};
    application::ComparisonRequest comparison{problem, family, {reach_back, direct}};

    auto modules = make_modules();
    auto preparation = application::prepare_comparison(comparison, modules.strategies);
    if (const auto* unsupported = std::get_if<application::UnsupportedComparison>(&preparation)) {
        std::cerr << "Comparison unsupported:";
        for (const auto& diagnostic : unsupported->diagnostics)
            std::cerr << " " << diagnostic.field << " " << diagnostic.explanation;
        std::cerr << '\n';
        return 2;
    }
    if (const auto* rejected = std::get_if<application::RejectedComparison>(&preparation)) {
        std::cerr << "Strategy preparation rejected:";
        for (const auto& rejection : rejected->strategies) {
            std::cerr << " " << rejection.provenance.requested.id.value;
            for (const auto& diagnostic : rejection.diagnostics)
                std::cerr << " " << diagnostic.field << " " << diagnostic.explanation;
        }
        std::cerr << '\n';
        return 1;
    }
    const auto& prepared = std::get<application::PreparedComparison>(preparation);

    WitnessRequest witnesses{2, 0, {{1,-1}, {-1,1}}, requested->seed.value_or(31)};
    if (requested->witnesses) {
        if (requested->witnesses->count) witnesses.count = *requested->witnesses->count;
        if (requested->witnesses->distinctness_tolerance)
            witnesses.distinctness_tolerance = *requested->witnesses->distinctness_tolerance;
        if (requested->witnesses->directions) witnesses.directions = *requested->witnesses->directions;
    }
    if (options.seed) witnesses.seed = options.seed;
    ResourcePolicy resources = requested->resources.value_or(ResourcePolicy{1,1,1,{}});
    if (options.threads) {
        resources.total_threads = *options.threads;
        resources.outer_workers = 1;
        resources.threads_per_worker = *options.threads;
    }
    ExecutionContext context;
    context.numerical = family.numerical;
    context.resources = std::make_shared<const ResourcePolicy>(resources);
    Requirements selector_requirements;
    selector_requirements.output.representation = {"csl.witness-batch.v1"};
    const auto execution = application::run_comparison(prepared, modules.selectors,
        {modules.selector_identity.id, modules.selector_identity.version}, witnesses,
        selector_requirements, context, modules.membership);

    std::cout << "mode=run profile=" << profile << " problem=" << problem.identity().value
              << " source_sha256=" << problem::hex(scenario.source()->content.digest())
              << " lp=" << lp_id << " convex=" << convex_id
              << " seed=" << witnesses.seed.value_or(31)
              << " threads=" << resources.total_threads << '\n';
    bool all_passed = true;
    for (std::size_t index = 0; index < execution.strategies.size(); ++index) {
        const auto& strategy = execution.strategies[index];
        const auto* result = std::get_if<SynthesisResult>(&strategy.outcome);
        if (!result) {
            std::cout << "mode=run profile=" << profile << " strategy=" << (index == 0 ? "csl.synthesis.reach-back" : "csl.synthesis.strategy-b")
                      << " outcome=unsupported\n";
            all_passed = false;
            continue;
        }
        const bool complete = result->family &&
            std::holds_alternative<CompleteOptimalFamily>(result->family->outcome());
        const auto* selected_witnesses = std::get_if<WitnessSelection>(&strategy.selection);
        std::cout << "mode=run profile=" << profile << " strategy=" << (index == 0 ? "csl.synthesis.reach-back" : "csl.synthesis.strategy-b");
        if (result->family)
            std::cout << " version=" << result->family->identity().strategy_version;
        std::cout << " seed=" << witnesses.seed.value_or(31) << " threads=" << resources.total_threads
                  << " termination=" << termination_name(result->termination)
                  << " outcome=" << outcome_name(result->outcome.value)
                  << " family=" << (complete ? "complete" : (result->family ? "partial" : "none"))
                  << " selected=" << (selected_witnesses ? selected_witnesses->batch.returned_count() : 0);
        bool verification_passed = selected_witnesses != nullptr &&
            strategy.verification.size() == selected_witnesses->batch.witnesses.size();
        for (const auto& report : strategy.verification) {
            verification_passed = verification_passed &&
                report.termination == Termination::completed && passed(report.bindings) && passed(report.feasibility) && passed(report.objective) && report.recomputed_objective.has_value();
        }
        std::cout << " verification="
                  << (verification_passed ? "numerical_pass" : "not_passed") << '\n';
        if (!verification_passed || result->termination != Termination::completed ||
            result->outcome.value != MathematicalOutcome::optimal || !complete)
            all_passed = false;
    }
    if (!all_passed) return 1;
    if (options.output_directory) return persist(problem, prepared, execution, modules, resources, witnesses, *options.output_directory);
    std::cout << "artifact_export=not_requested\n";
    return 0;
}

} // namespace

int main(int argc, char** argv) try {
    Options options;
    if (!parse_options(argc, argv, options)) {
        std::cerr << "Usage: scenario_cli --validate-only <scenario.json>\n"
                  << "   or: scenario_cli --run <scenario.json> [--profile ts01_exact_integrator|ts02_constant_integrator]"
                     " [--lp id] [--convex id] [--seed n] [--threads n] [--output-dir directory]\n";
        return 2;
    }
    const auto loaded = input::load_scenario_file(options.scenario);
    if (!std::holds_alternative<input::LoadedScenario>(loaded)) {
        print_input_error(loaded);
        return 2;
    }
    const auto& scenario = std::get<input::LoadedScenario>(loaded);
    if (options.mode == Options::Mode::validate) return validate(scenario);
    return run(scenario, options);
} catch (const std::exception& error) {
    std::cerr << "Scenario CLI failed: " << error.what() << '\n';
    return 1;
}
