#include <csl/adapters/convex/highs.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <csl/adapters/polyhedral/qhull.hpp>
#include <csl/application/comparison.hpp>
#include <csl/artifacts/comparison_manifest.hpp>
#include <csl/execution/timing_collector.hpp>
#include <csl/geometry/affine_sum.hpp>
#include <csl/geometry/hull_reducer.hpp>
#include <csl/geometry/polyhedral_projection.hpp>
#include <csl/input/scenario_loader.hpp>
#include <csl/problem/validator.hpp>
#include <csl/synthesis/strategy_a/strategy.hpp>
#include <csl/synthesis/strategy_b/direct_joint.hpp>
#include <csl/synthesis/witness_selector.hpp>
#include "Obs04BuildInfo.hpp"
#include <nlohmann/json.hpp>

#include <algorithm>
#include <array>
#include <charconv>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <cstdint>
#include <cerrno>
#include <csignal>
#include <cstring>
#include <iostream>
#include <fstream>
#include <filesystem>
#include <memory>
#include <optional>
#include <span>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <type_traits>
#include <thread>
#include <utility>
#include <vector>
#include <iterator>

#ifndef _WIN32
#include <fcntl.h>
#include <poll.h>
#include <sys/utsname.h>
#include <unistd.h>
#else
#define NOMINMAX
#include <windows.h>
#include <winternl.h>
#endif

#if !defined(NDEBUG) || defined(_DEBUG)
#error "The OBS-04 measurement executable must be compiled as a Release target"
#endif

namespace {
using namespace csl;
namespace ar = artifacts;
namespace ob = execution::observability;
using Json = nlohmann::json;
using Clock = std::chrono::steady_clock;
constexpr double absolute_tolerance = 1e-8;
constexpr double relative_tolerance = 1e-8;

template<class T, class... Rest> T take(std::variant<T, Rest...> value) {
    if (!std::holds_alternative<T>(value)) {
        std::string message = "Unexpected diagnostic or unsupported result";
        std::visit([&](const auto& error) {
            if constexpr (requires { error.path; error.message; })
                message += ": " + error.path + ": " + error.message;
        }, value);
        throw std::runtime_error(message);
    }
    return std::get<T>(std::move(value));
}

Json available_fact(std::string value) {
    if(value.empty())return {{"status","unavailable"},{"reason","platform returned an empty value"}};
    return {{"status","available"},{"value",std::move(value)}};
}

Json unavailable_fact(std::string reason) {
    return {{"status","unavailable"},{"reason",std::move(reason)}};
}

Json available_count(unsigned int value) {
    if(value==0)return unavailable_fact("platform did not report a processor count");
    return {{"status","available"},{"value",value}};
}

std::optional<std::filesystem::path> current_executable_path(std::string_view argv0) {
#ifdef _WIN32
    static_cast<void>(argv0);
    std::vector<wchar_t> buffer(32768);
    const auto length=GetModuleFileNameW(nullptr,buffer.data(),static_cast<DWORD>(buffer.size()));
    if(length==0||length>=buffer.size())return std::nullopt;
    return std::filesystem::path(std::wstring(buffer.data(),length));
#elif defined(__linux__)
    static_cast<void>(argv0);
    std::error_code failure;
    const auto path=std::filesystem::read_symlink("/proc/self/exe",failure);
    if(failure)return std::nullopt;
    return path;
#else
    std::error_code failure;
    const auto path=std::filesystem::absolute(std::filesystem::path(argv0),failure);
    if(failure)return std::nullopt;
    return path;
#endif
}

Json binary_digest(std::string_view argv0) {
    const auto executable=current_executable_path(argv0);
    if(!executable)return unavailable_fact("the running executable path is unavailable on this platform");
    std::ifstream input(*executable,std::ios::binary);
    if(!input)return unavailable_fact("the running executable could not be read");
    const std::vector<char> bytes{std::istreambuf_iterator<char>{input},std::istreambuf_iterator<char>{}};
    if(input.bad())return unavailable_fact("reading the running executable failed");
    std::vector<std::byte> content;
    content.reserve(bytes.size());
    for(const auto value:bytes)content.push_back(static_cast<std::byte>(static_cast<unsigned char>(value)));
    const auto snapshot=problem::snapshot_content(std::span<const std::byte>{content});
    if(const auto* owned=std::get_if<problem::ResolvedContent>(&snapshot))
        return available_fact(problem::hex(owned->digest()));
    return unavailable_fact("the running executable digest could not be computed");
}

struct HostFacts {
    std::string family;
    std::string architecture;
    Json version;
    Json kernel;
    Json cpu_model;
};

HostFacts host_facts() {
    HostFacts host;
#ifdef _WIN32
    host.family="Windows";
    SYSTEM_INFO system_info{};
    GetNativeSystemInfo(&system_info);
    switch(system_info.wProcessorArchitecture) {
    case PROCESSOR_ARCHITECTURE_AMD64: host.architecture="x86_64"; break;
    case PROCESSOR_ARCHITECTURE_ARM64: host.architecture="aarch64"; break;
    case PROCESSOR_ARCHITECTURE_INTEL: host.architecture="x86"; break;
    case PROCESSOR_ARCHITECTURE_ARM: host.architecture="arm"; break;
    case PROCESSOR_ARCHITECTURE_IA64: host.architecture="ia64"; break;
    default: host.architecture="unknown-native-architecture"; break;
    }
    using RtlGetVersion = LONG (WINAPI*)(OSVERSIONINFOW*);
    const auto module=GetModuleHandleW(L"ntdll.dll");
    const auto get_version=module?reinterpret_cast<RtlGetVersion>(GetProcAddress(module,"RtlGetVersion")):nullptr;
    OSVERSIONINFOW info{};
    info.dwOSVersionInfoSize=sizeof(info);
    if(get_version&&get_version(&info)==0) {
        const auto version=std::to_string(info.dwMajorVersion)+"."+
            std::to_string(info.dwMinorVersion)+"."+std::to_string(info.dwBuildNumber);
        host.version=available_fact(version);
        host.kernel=available_fact(version);
    } else {
        host.version=unavailable_fact("RtlGetVersion is unavailable");
        host.kernel=unavailable_fact("RtlGetVersion is unavailable");
    }
    host.cpu_model=unavailable_fact("CPU model capture is not implemented for Windows");
#elif defined(__linux__)
    utsname info{};
    if(uname(&info)==0) {
        host.family=info.sysname;
        host.architecture=info.machine;
        host.version=unavailable_fact("/etc/os-release has no PRETTY_NAME field");
        host.kernel=available_fact(info.release);
    } else {
        host.family="Linux";
        host.architecture="unknown-linux-target-architecture";
        host.version=unavailable_fact("uname failed");
        host.kernel=unavailable_fact("uname failed");
    }
    std::string line;
    std::ifstream os_release("/etc/os-release");
    while(std::getline(os_release,line)) {
        constexpr std::string_view name="PRETTY_NAME=";
        if(!line.starts_with(name))continue;
        auto value=line.substr(name.size());
        if(value.size()>=2&&value.front()=='"'&&value.back()=='"')
            value=value.substr(1,value.size()-2);
        if(value.find('\\')==std::string::npos)host.version=available_fact(std::move(value));
        break;
    }
    std::ifstream cpu_info("/proc/cpuinfo");
    host.cpu_model=unavailable_fact("/proc/cpuinfo has no model name");
    while(std::getline(cpu_info,line)) {
        const auto separator=line.find(':');
        if(separator!=std::string::npos&&line.substr(0,separator).find("model name")!=std::string::npos) {
            auto value=line.substr(separator+1);
            const auto first=value.find_first_not_of(" \t");
            host.cpu_model=first==std::string::npos?unavailable_fact("/proc/cpuinfo had an empty model name"):
                available_fact(value.substr(first));
            break;
        }
    }
    if(host.family.empty())host.family="Linux";
#else
    host.family="unknown";
    host.architecture="unknown";
    host.version=unavailable_fact("platform version capture is not implemented");
    host.kernel=unavailable_fact("kernel capture is not implemented for this platform");
    host.cpu_model=unavailable_fact("CPU model capture is not implemented for this platform");
#endif
    if(host.version.is_null())host.version=unavailable_fact("platform version was not available");
    if(host.kernel.is_null())host.kernel=unavailable_fact("kernel version was not available");
    if(host.cpu_model.is_null())host.cpu_model=unavailable_fact("CPU model was not available");
    return host;
}

struct PreflightTimings {
    std::uint64_t scenario_file_read_ns{};
    std::uint64_t scenario_json_parse_ns{};
    std::uint64_t scenario_load_validation_resolution_ns{};
    std::uint64_t provider_registration_ns{};
    std::uint64_t comparison_admission_ns{};
};

Json environment_manifest(std::string_view argv0) {
    const auto host=host_facts();
    const auto backend_threads=unavailable_fact("native backend thread counts are not observable from the driver");
    return {{"schema","csl.obs04-environment/1"},
        {"build",Json::parse(benchmarks::obs04::build::manifest)},
        {"runtime",{{"schema","csl.obs04-runtime/1"},{"binary_sha256",binary_digest(argv0)},
            {"os_family",host.family},{"os_version",host.version},{"kernel",host.kernel},
            {"architecture",host.architecture},{"cpu_model",host.cpu_model},
            {"logical_cpus",available_count(std::thread::hardware_concurrency())}}},
        {"execution",{{"requested_workers",1},{"observed_driver_workers",1},
            {"requested_backend_threads",1},{"observed_backend_threads",backend_threads},
            {"workspace_policy","fresh-workspace-per-attempt"},
            {"cache_policy","one warm-up repetition per arm; operating-system caches are not flushed"},
            {"warmup_repetitions",1},{"seed_policy",{{"kind","not_applicable"},
                {"reason","fixed analytic fixture uses no random generator"}}},
            {"tolerances",{{"absolute",absolute_tolerance},{"relative",relative_tolerance}}}}}
    };
}

template<class Port> registry::PreparedProvider<Port> selected(
    registry::Registration<Port> entry, std::string representation) {
    registry::Registry<Port> providers;
    const registry::Method method{entry.identity.id, entry.identity.version};
    if (providers.add(std::move(entry))) throw std::runtime_error("Provider registration failed");
    registry::Requirements requirements;
    requirements.output.representation = {std::move(representation)};
    if constexpr (std::is_same_v<Port, registry::GeometryPort> ||
        std::is_same_v<Port, registry::ConversionPort>)
        requirements.output.relation = SetRelation::equivalent;
    return take(registry::prepare_provider(registry::select_provider(providers, method, requirements)));
}

std::string read_scenario_file() {
    std::ifstream input(benchmarks::obs04::build::scenario_file, std::ios::binary);
    if (!input) throw std::runtime_error("Could not open the pinned OBS-04 scenario file");
    std::string bytes{std::istreambuf_iterator<char>{input}, std::istreambuf_iterator<char>{}};
    if (input.bad()) throw std::runtime_error("Could not read the pinned OBS-04 scenario file");
    return bytes;
}

problem::ResolvedProblem load_scenario(std::string_view bytes) {
    const auto input_bytes = std::as_bytes(std::span{bytes.data(), bytes.size()});
    return take(input::load_scenario(input_bytes)).problem();
}

struct Modules {
    std::shared_ptr<registry::Registry<registry::GeometryPort>> projections;
    std::shared_ptr<registry::Registry<registry::GeometryPort>> affines;
    std::shared_ptr<registry::Registry<registry::ConversionPort>> conversions;
    std::shared_ptr<registry::Registry<registry::LPPort>> lps;
    std::shared_ptr<registry::Registry<registry::ConvexPort>> convexes;
    registry::Registry<registry::SelectorPort> selectors;
    std::optional<registry::PreparedProvider<registry::LPPort>> membership;
    registry::StrategyRegistry strategies;
};

Modules make_modules() {
    auto lp = take(adapters::lp::make_highs_registration());
    auto convex = take(adapters::convex::make_highs_registration());
    auto converter = take(adapters::polyhedral::make_qhull_registration(lp));
    auto projection = geometry::polyhedral::make_projection_registration();
    auto affine = geometry::make_affine_sum_registration({
        selected(geometry::make_lp_hull_reducer_registration(), ""),
        selected(lp, "csl.program-result.v1"),
        selected(converter, "csl.polyhedron.v")});

    auto projections = std::make_shared<registry::Registry<registry::GeometryPort>>();
    auto affines = std::make_shared<registry::Registry<registry::GeometryPort>>();
    auto conversions = std::make_shared<registry::Registry<registry::ConversionPort>>();
    auto lps = std::make_shared<registry::Registry<registry::LPPort>>();
    auto convexes = std::make_shared<registry::Registry<registry::ConvexPort>>();
    const registry::Method pm{projection.identity.id, {}}, am{affine.identity.id, {}},
        cm{converter.identity.id, {}}, lm{lp.identity.id, {}}, qm{convex.identity.id, {}};
    if (projections->add(projection) || affines->add(affine) || conversions->add(converter) ||
        lps->add(lp) || convexes->add(convex))
        throw std::runtime_error("Provider registration failed");
    registry::Requirements h, v, program;
    h.output.representation = {"csl.polyhedron.h"}; h.output.relation = SetRelation::equivalent;
    v.output.representation = {"csl.polyhedron.v"}; v.output.relation = SetRelation::equivalent;
    program.output.representation = {"csl.program-result.v1"};
    auto providers = take(registry::check_providers(
        registry::select_provider(*projections, pm, h), registry::select_provider(*affines, am, v),
        registry::select_provider(*conversions, cm, h), registry::select_provider(*lps, lm, program),
        registry::select_provider(*convexes, qm, program)));
    Modules result{std::move(projections), std::move(affines), std::move(conversions),
        std::move(lps), std::move(convexes), {}, {}, {}};
    registry::Requirements membership_requirements;
    membership_requirements.output.representation = {"csl.program-result.v1"};
    auto membership = take(registry::prepare_provider(
        registry::select_provider(*result.lps, lm, membership_requirements)));
    if (result.selectors.add(synthesis::witness_selector::make_registration(membership)))
        throw std::runtime_error("Witness selector registration failed");
    result.membership = std::move(membership);
    if (result.strategies.add(synthesis::strategy_a::make_registration(std::move(providers))) ||
        result.strategies.add(synthesis::strategy_b::make_registration(*result.lps, *result.convexes)))
        throw std::runtime_error("Strategy registration failed");
    return result;
}

application::PreparedComparison prepare(const problem::ResolvedProblem& problem,
    registry::StrategyRegistry& strategies) {
    FamilyRequest family;
    family.profile = "ts01_exact_integrator";
    family.objective = problem.identity();
    family.target = FamilyTarget::exact_optimal_relation;
    family.assurance = Assurance::numerical;
    family.representation = {"csl.polyhedron.h"};
    StrategyConfiguration a;
    a.strategy = {"csl.synthesis.reach-back"}; a.lp = {"csl.lp.highs"};
    a.convex = {"csl.convex.highs"}; a.representation = family.representation;
    StrategyConfiguration b = a; b.strategy = {"csl.synthesis.strategy-b"};
    return take(application::prepare_comparison({problem, family, {a, b}}, strategies));
}

struct CollectionSetup {
    ar::ResolvedConfiguration configuration;
    std::shared_ptr<ob::TimingCollector> collector;
    std::optional<ar::CollectedStatistics> empty_statistics;
};

ar::ResolvedConfiguration configuration_for(const application::PreparedComparison& prepared,
    std::size_t strategy_index, bool enabled) {
    const auto& selected_configuration=prepared.strategies()[strategy_index];
    const auto expected=prepared.expected_synthesis_identity(strategy_index);
    const ar::Unavailable missing{ar::MissingReason::not_instrumented,{}};
    ar::ConfigurationInput config;
    config.collection={enabled,ar::CollectionMode::summary,5,10000,0,0};
    config.modules={{"strategy",{expected.strategy,expected.strategy_version,missing},{}},
        {"lp",{selected_configuration.lp,"1",missing},{}},
        {"convex",{selected_configuration.convex,"1",missing},{}}};
    config.numerical=prepared.family().numerical;
    config.resources={1,1,1,{}};
    config.output={ar::OutputKind::synthesis,prepared.family().assurance,
        prepared.family().target,prepared.family().representation,{2,0,{{1,-1},{-1,1}},31}};
    config.selector={{synthesis::witness_selector::selector_id},"1",{}};
    config.strategy=selected_configuration;
    config.strategy.selector=config.selector.id;
    return take(ar::resolve_configuration(std::move(config)));
}

CollectionSetup collector_for(const application::PreparedComparison& prepared,
    std::size_t strategy_index, bool enabled, std::string run_id,
    const ar::ResolvedConfiguration& resolved_configuration,
    std::optional<ar::ResolvedConfiguration>& fallback_configuration,
    std::optional<ar::CollectedStatistics>& fallback_statistics) {
    const auto clock = ob::make_steady_timing_clock();
    const auto expected = prepared.expected_synthesis_identity(strategy_index);
    const ar::Unavailable missing{ar::MissingReason::not_instrumented,{}};
    auto resolved_config=resolved_configuration;
    fallback_configuration=resolved_configuration;

    ob::PlanInput plan{prepared.problem(), resolved_config, {run_id}, {clock->wall_domain()}, {}, enabled?1u:0u};
    const std::size_t span_count = enabled ? (strategy_index == 0 ? 5 : 1) : 0;
    if(!enabled)plan.clocks.clear();
    if(enabled) {
        plan.tasks = {strategy_index == 0 ? "strategy-a" : "strategy-b"};
        plan.operations = strategy_index == 0
            ? std::vector<std::string>{"strategy-a/run", "strategy-a/forward", "strategy-a/feasible-preimage",
                "strategy-a/terminal-optimization", "strategy-a/terminal-preimage"}
            : std::vector<std::string>{"strategy-b/run"};
    }
    plan.spans.reserve(span_count);
    for (std::size_t index = 0; index < span_count; ++index) {
        ar::SpanDescriptor span{};
        span.id = {index};
        if (index != 0) span.parent = ar::SpanParent{{0}, ar::ParentKind::nested};
        span.task = plan.tasks.front();
        span.operation = plan.operations[index];
        span.module = {expected.strategy, expected.strategy_version, missing};
        span.clock = plan.clocks.front().id;
        span.requested_assurance = prepared.family().assurance;
        span.applied_assurance = ar::Available<Assurance>{prepared.family().assurance};
        plan.spans.push_back(std::move(span));
    }
    auto collection_plan = take(ob::make_collection_plan(std::move(plan)));
    fallback_statistics=take(ob::merge_observations(collection_plan,{}));
    if(enabled) {
        auto collector=take(ob::make_timing_collector(std::move(collection_plan), clock, {0}, {}));
        return {std::move(resolved_config),std::move(collector),*fallback_statistics};
    }
    return {std::move(resolved_config),nullptr,*fallback_statistics};
}

struct Signature {
    Termination termination{};
    MathematicalOutcome outcome{};
    std::optional<double> lower, upper;
    std::string profile;
    bool complete{};
};

Signature signature(const SynthesisOutcome& outcome) {
    const auto* result = std::get_if<SynthesisResult>(&outcome);
    if (!result || !result->family || !result->family->registry_verified())
        throw std::runtime_error("Strategy did not return a registry-verified family");
    const auto* complete = std::get_if<CompleteOptimalFamily>(&result->family->outcome());
    return {result->termination, result->outcome.value,
        result->objective.lower ? std::optional<double>{result->objective.lower->value} : std::nullopt,
        result->objective.upper ? std::optional<double>{result->objective.upper->value} : std::nullopt,
        result->family->identity().request.profile, complete != nullptr};
}

struct TrialRecord {
    std::uint32_t arm_index{};
    std::uint32_t repetition_index{};
    ar::AttemptStatus status{ar::AttemptStatus::completed};
    ar::RunId run_id;
    ar::RecordedRunArtifact run;
    std::string measurement_payload;
    bool quality_passed{true};
};

ar::AttemptStatus attempt_status(const SynthesisOutcome& outcome) {
    if (std::holds_alternative<Unsupported>(outcome)) return ar::AttemptStatus::unsupported;
    switch (std::get<SynthesisResult>(outcome).termination) {
    case Termination::completed: return ar::AttemptStatus::completed;
    case Termination::cancelled: return ar::AttemptStatus::cancelled;
    case Termination::resource_limit: return ar::AttemptStatus::resource_limited;
    case Termination::operation_rejected: return ar::AttemptStatus::unsupported;
    case Termination::numerical_failure:
    case Termination::contract_rejected: return ar::AttemptStatus::failed;
    }
    return ar::AttemptStatus::incomplete;
}

const char* attempt_status_name(ar::AttemptStatus status) {
    switch(status) {
    case ar::AttemptStatus::completed: return "passed";
    case ar::AttemptStatus::failed: return "failed";
    case ar::AttemptStatus::unsupported: return "unsupported";
    case ar::AttemptStatus::cancelled: return "cancelled";
    case ar::AttemptStatus::resource_limited: return "resource_limited";
    case ar::AttemptStatus::incomplete: return "incomplete";
    }
    return "incomplete";
}

const char* terminal_status_name(ar::AttemptStatus status) {
    switch(status) {
    case ar::AttemptStatus::completed: return "completed";
    case ar::AttemptStatus::failed: return "failed";
    case ar::AttemptStatus::unsupported: return "unsupported";
    case ar::AttemptStatus::cancelled: return "cancelled";
    case ar::AttemptStatus::resource_limited: return "resource_limited";
    case ar::AttemptStatus::incomplete: return "incomplete";
    }
    return "incomplete";
}

const char* termination_name(Termination termination) {
    switch(termination) {
    case Termination::completed: return "completed";
    case Termination::cancelled: return "cancelled";
    case Termination::resource_limit: return "resource_limit";
    case Termination::numerical_failure: return "numerical_failure";
    case Termination::operation_rejected: return "operation_rejected";
    case Termination::contract_rejected: return "contract_rejected";
    }
    return "unknown";
}

bool close(const std::optional<double>& left, const std::optional<double>& right) {
    if (!left || !right) return !left && !right;
    if (!std::isfinite(*left) || !std::isfinite(*right)) return false;
    return std::abs(*left - *right) <= absolute_tolerance + relative_tolerance *
        std::max(std::abs(*left), std::abs(*right));
}

bool family_contains_history(const OptimalFamily& family, const Vector& history) {
    const auto* complete = std::get_if<CompleteOptimalFamily>(&family.outcome());
    if (!complete || !complete->relation.payload) return false;
    const auto* relation = complete->relation.payload->h_relation_for_recording();
    if (!relation) return false;
    const auto representation = relation->representation();
    const auto* h = std::get_if<sets::HRepresentation>(&representation);
    if (!h || history.size() != h->inequalities.cols() || history.size() != h->equalities.cols()) return false;
    for (std::size_t row = 0; row < h->inequalities.rows(); ++row) {
        double value = 0.0;
        for (std::size_t col = 0; col < history.size(); ++col) value += h->inequalities(row, col) * history[col];
        if (value > h->upper_bounds[row] + absolute_tolerance) return false;
    }
    for (std::size_t row = 0; row < h->equalities.rows(); ++row) {
        double value = 0.0;
        for (std::size_t col = 0; col < history.size(); ++col) value += h->equalities(row, col) * history[col];
        if (std::abs(value - h->equality_values[row]) > absolute_tolerance) return false;
    }
    return true;
}

void require_ts01_analytic_result(const SynthesisOutcome& outcome, const Signature& observed) {
    if (observed.termination != Termination::completed || observed.outcome != MathematicalOutcome::optimal ||
        !observed.complete || observed.profile != "ts01_exact_integrator" || !observed.lower || !observed.upper ||
        !std::isfinite(*observed.lower) || !std::isfinite(*observed.upper) ||
        std::abs(*observed.lower) > absolute_tolerance || std::abs(*observed.upper) > absolute_tolerance)
        throw std::runtime_error("T-S01 analytic baseline must be completed, optimal, complete, and have objective zero");
    const auto* result = std::get_if<SynthesisResult>(&outcome);
    if (!result || !result->family || !family_contains_history(*result->family, {0, 0, 1, 0, 1}) ||
        !family_contains_history(*result->family, {0, 1, 1, 1, 0}) ||
        family_contains_history(*result->family, {0, 0.75, 1.5, 0.75, 0.75}))
        throw std::runtime_error("T-S01 family failed analytic membership checks");
}

const char* outcome_name(MathematicalOutcome outcome) {
    switch (outcome) {
    case MathematicalOutcome::optimal: return "optimal";
    case MathematicalOutcome::infeasible: return "infeasible";
    case MathematicalOutcome::unbounded: return "unbounded";
    case MathematicalOutcome::infimum_not_attained: return "infimum_not_attained";
    case MathematicalOutcome::undetermined: return "undetermined";
    }
    return "undetermined";
}

std::int64_t ns(Clock::time_point begin, Clock::time_point end) {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(end - begin).count();
}

struct TrialTimings {
    std::optional<Clock::time_point> attempt_begin;
    std::optional<Clock::time_point> setup_begin;
    std::optional<Clock::time_point> strategy_run_begin;
    std::optional<Clock::time_point> selection_setup_begin;
    std::optional<Clock::time_point> selection_run_begin;
    std::optional<Clock::time_point> first_query_begin;
    std::optional<Clock::time_point> additional_query_begin;
    std::optional<Clock::time_point> verification_begin;
    std::optional<std::uint64_t> setup_ns;
    std::optional<std::uint64_t> strategy_run_ns;
    std::optional<std::uint64_t> selection_setup_ns;
    std::optional<std::uint64_t> selection_run_ns;
    std::optional<std::uint64_t> first_query_ns;
    std::optional<std::uint64_t> additional_query_ns;
    std::optional<std::uint64_t> verification_ns;
    std::optional<std::uint64_t> end_to_end_ns;
    std::optional<WitnessSelection> selected_witnesses;
    std::vector<verification::TrajectoryReport> verification_reports;

    void capture_partial() {
        const auto now = Clock::now();
        const auto elapsed = [now](std::optional<Clock::time_point> begin) -> std::optional<std::uint64_t> {
            if (!begin) return std::nullopt;
            return static_cast<std::uint64_t>(ns(*begin, now));
        };
        if (!setup_ns) setup_ns = elapsed(setup_begin);
        if (!strategy_run_ns) strategy_run_ns = elapsed(strategy_run_begin);
        if (!selection_setup_ns) selection_setup_ns = elapsed(selection_setup_begin);
        if (!selection_run_ns) selection_run_ns = elapsed(selection_run_begin);
        if (!first_query_ns) first_query_ns = elapsed(first_query_begin);
        if (!additional_query_ns) additional_query_ns = elapsed(additional_query_begin);
        if (!verification_ns) verification_ns = elapsed(verification_begin);
        if (!end_to_end_ns) end_to_end_ns = elapsed(attempt_begin);
    }
};

std::string optional_ns_json(const std::optional<std::uint64_t>& value) {
    return value ? std::to_string(*value) : "null";
}

class PerfControl {
public:
    PerfControl() {
#ifdef _WIN32
        if (std::getenv("CSL_PERF_CONTROL_FIFO") || std::getenv("CSL_PERF_ACK_FIFO"))
            throw std::runtime_error("perf FIFO control is supported only on POSIX hosts");
#else
        const char* control_path = std::getenv("CSL_PERF_CONTROL_FIFO");
        const char* ack_path = std::getenv("CSL_PERF_ACK_FIFO");
        if ((control_path == nullptr) != (ack_path == nullptr))
            throw std::runtime_error("perf control and acknowledgement FIFOs must be configured together");
        if (control_path != nullptr) {
            std::signal(SIGPIPE, SIG_IGN);
            const auto open_deadline = Clock::now() + std::chrono::milliseconds(acknowledgement_timeout_ms);
            do {
                control_fd_ = ::open(control_path, O_WRONLY | O_NONBLOCK | O_CLOEXEC);
                if (control_fd_ >= 0) break;
                if (errno == EINTR) continue;
                if (errno != ENXIO)
                    throw std::runtime_error("Could not open perf control FIFO");
                if (Clock::now() >= open_deadline)
                    throw std::runtime_error("Timed out waiting for perf to open the control FIFO");
                std::this_thread::sleep_for(std::chrono::milliseconds(10));
            } while (true);
            ack_fd_ = ::open(ack_path, O_RDONLY | O_NONBLOCK | O_CLOEXEC);
            if (ack_fd_ < 0) {
                ::close(control_fd_);
                control_fd_ = -1;
                throw std::runtime_error("Could not open perf acknowledgement FIFO");
            }
            configured_ = true;
        }
#endif
    }

    PerfControl(const PerfControl&) = delete;
    PerfControl& operator=(const PerfControl&) = delete;

    ~PerfControl() {
#ifndef _WIN32
        if (active_) {
            try { command("disable"); } catch (...) {}
        }
        if (ack_fd_ >= 0) ::close(ack_fd_);
        if (control_fd_ >= 0) ::close(control_fd_);
#endif
    }

    bool configured() const noexcept {
#ifndef _WIN32
        return configured_;
#else
        return false;
#endif
    }

    std::size_t acknowledged_commands() const noexcept { return acknowledged_commands_; }

    void enable() {
#ifndef _WIN32
        if (configured_) {
            command("enable");
            active_ = true;
        }
#endif
    }

    void disable() {
#ifndef _WIN32
        if (configured_) {
            command("disable");
            active_ = false;
        }
#endif
    }

private:
#ifndef _WIN32
    static constexpr int acknowledgement_timeout_ms = 5000;

    void command(std::string_view value) {
        const auto deadline = Clock::now() + std::chrono::milliseconds(acknowledgement_timeout_ms);
        std::string message{value};
        message.push_back('\n');
        std::size_t written = 0;
        while (written < message.size()) {
            const auto count = ::write(control_fd_, message.data() + written, message.size() - written);
            if (count < 0 && errno == EINTR) continue;
            if (count < 0 && errno == EAGAIN) {
                if (Clock::now() >= deadline)
                    throw std::runtime_error("Timed out sending perf control command");
                std::this_thread::sleep_for(std::chrono::milliseconds(1));
                continue;
            }
            if (count <= 0) throw std::runtime_error("Could not send perf control command");
            written += static_cast<std::size_t>(count);
        }

        std::array<char, 5> response{};
        std::size_t received = 0;
        while (received < 4) {
            const auto remaining = std::chrono::duration_cast<std::chrono::milliseconds>(deadline - Clock::now()).count();
            if (remaining <= 0) throw std::runtime_error("Timed out waiting for perf control acknowledgement");
            pollfd descriptor{ack_fd_, POLLIN, 0};
            const int ready = ::poll(&descriptor, 1, static_cast<int>(remaining));
            if (ready < 0 && errno == EINTR) continue;
            if (ready == 0) throw std::runtime_error("Timed out waiting for perf control acknowledgement");
            if (ready < 0) throw std::runtime_error("Could not poll perf acknowledgement FIFO");
            if ((descriptor.revents & (POLLERR | POLLNVAL)) != 0)
                throw std::runtime_error("perf acknowledgement FIFO failed");
            if ((descriptor.revents & POLLIN) == 0) {
                if ((descriptor.revents & POLLHUP) != 0)
                    std::this_thread::sleep_for(std::chrono::milliseconds(1));
                continue;
            }
            const auto count = ::read(ack_fd_, response.data() + received, response.size() - received);
            if (count < 0 && (errno == EINTR || errno == EAGAIN)) continue;
            if (count <= 0) throw std::runtime_error("perf closed the acknowledgement FIFO");
            received += static_cast<std::size_t>(count);
        }
        const std::string_view newline_prefix{response.data(), 4};
        constexpr std::string_view newline_ack{"ack\n", 4};
        constexpr std::string_view nul_terminated_ack{"ack\n\0", 5};
        if (newline_prefix != newline_ack)
            throw std::runtime_error("Unexpected perf control acknowledgement frame");
        if (received == 4) {
            // The documented frame ends at newline; Linux perf may append NUL.
            // Give a split optional terminator a bounded chance to arrive.
            pollfd descriptor{ack_fd_, POLLIN, 0};
            int ready;
            do {
                ready = ::poll(&descriptor, 1, 25);
            } while (ready < 0 && errno == EINTR);
            if (ready < 0) throw std::runtime_error("Failed while reading perf control acknowledgement");
            if (ready > 0) {
                const auto count = ::read(ack_fd_, response.data() + received, 1);
                if (count != 1) throw std::runtime_error("perf closed the acknowledgement FIFO");
                ++received;
            }
        }
        const std::string_view acknowledgement{response.data(), received};
        if (acknowledgement != newline_ack && acknowledgement != nul_terminated_ack)
            throw std::runtime_error("Unexpected perf control acknowledgement frame");
        ++acknowledged_commands_;
    }

    int control_fd_{-1};
    int ack_fd_{-1};
    bool configured_{};
    bool active_{};
#endif
    std::size_t acknowledged_commands_{};
};

TrialRecord trial_impl(const application::PreparedComparison& prepared, std::size_t strategy_index,
    Modules& modules, bool enabled, std::size_t repetition, bool warmup, const Signature& expected,
    const ar::ResolvedConfiguration& resolved_configuration,
    std::optional<ar::ResolvedConfiguration>& fallback_configuration,
    std::optional<ar::CollectedStatistics>& fallback_statistics,
    std::optional<SynthesisOutcome>& returned_outcome, bool& invocation_started,
    TrialTimings& timings) {
    timings.attempt_begin = Clock::now();
    const auto setup_begin = Clock::now();
    timings.setup_begin = setup_begin;
    const ar::RunId run_id{"obs04-" + std::to_string(strategy_index) + "-" +
        (enabled ? "enabled-" : "disabled-") + std::to_string(repetition) + (warmup ? "-warmup" : "")};
    auto setup = collector_for(prepared, strategy_index, enabled, run_id.value,
        resolved_configuration,
        fallback_configuration,fallback_statistics);
    auto collector = setup.collector;
    auto workspaces = prepared.create();
    ExecutionContext context;
    context.resources = std::make_shared<const ResourcePolicy>(ResourcePolicy{1, 1, 1, {}});
    context.numerical = prepared.family().numerical;
    if (collector) context.timing = collector;
    const auto setup_end = Clock::now();
    timings.setup_ns = static_cast<std::uint64_t>(ns(setup_begin, setup_end));
    const auto run_begin = Clock::now();
    timings.strategy_run_begin = run_begin;
    invocation_started=true;
    const auto outcome = workspaces[strategy_index]->run(context);
    returned_outcome=outcome;
    const auto run_end = Clock::now();
    timings.strategy_run_ns = static_cast<std::uint64_t>(ns(run_begin, run_end));
    const auto status=attempt_status(outcome);
    std::optional<Signature> observed;
    bool quality_passed=false;
    if (std::holds_alternative<SynthesisResult>(outcome)) {
        try {
            observed=signature(outcome);
            require_ts01_analytic_result(outcome,*observed);
            quality_passed=observed->termination == expected.termination && observed->outcome == expected.outcome &&
                close(observed->lower, expected.lower) && close(observed->upper, expected.upper) &&
                observed->profile == expected.profile && observed->complete == expected.complete && observed->complete;
        } catch(const std::exception&) { quality_passed=false; }
    }

    std::size_t observed_spans = 0;
    std::size_t completed_spans = 0;
    std::optional<ob::TimingReport> timing_report;
    std::vector<ob::SpanTiming> span_timings;
    std::vector<ar::SpanRecord> span_records;
    if (collector) {
        timing_report = take(collector->snapshot());
        fallback_statistics=timing_report->observations;
        observed_spans = timing_report->observations.description().spans.size();
        for (const auto& span : timing_report->observations.description().spans)
            if (span.completion_observed) ++completed_spans;
        span_timings = timing_report->spans;
        span_records = timing_report->observations.description().spans;
        if (status==ar::AttemptStatus::completed && (!timing_report->diagnostics.empty() ||
            observed_spans != (strategy_index == 0 ? 5u : 1u) || completed_spans != observed_spans ||
            span_timings.size() != observed_spans)) quality_passed=false;
    }
    struct SpanEvent { std::string operation; std::uint64_t inclusive, exclusive; };
    std::vector<SpanEvent> span_events;
    span_events.reserve(span_timings.size());
    for (std::size_t index = 0; index < span_timings.size(); ++index) {
        const auto inclusive = std::get_if<ar::Available<std::uint64_t>>(&span_timings[index].inclusive_wall_ticks);
        const auto exclusive = std::get_if<ar::Available<std::uint64_t>>(&span_timings[index].exclusive_wall_ticks);
        if (!inclusive || !exclusive || span_timings[index].id != span_records[index].descriptor.id) {
            quality_passed=false;
            continue;
        }
        span_events.push_back({span_records[index].descriptor.operation, inclusive->value, exclusive->value});
    }
    const auto selection_setup_begin = Clock::now();
    auto& selected_witnesses = timings.selected_witnesses;
    auto& verification_reports = timings.verification_reports;
    std::uint64_t selection_setup_ns = 0;
    std::uint64_t selection_run_ns = 0;
    std::optional<std::uint64_t> first_witness_query_ns;
    std::optional<std::uint64_t> additional_witness_query_ns;
    std::uint64_t verification_ns = 0;
    const auto* synthesis_result = std::get_if<SynthesisResult>(&outcome);
    if (synthesis_result && synthesis_result->family &&
        std::holds_alternative<CompleteOptimalFamily>(synthesis_result->family->outcome())) {
        timings.selection_setup_begin = selection_setup_begin;
        if (!modules.membership) throw std::runtime_error("Witness verification LP provider is unavailable");
        const WitnessRequest request{2, 0, {{1, -1}, {-1, 1}}, 31};
        const WitnessRequest first_request{1, request.distinctness_tolerance,
            {request.directions[0]}, request.seed};
        const WitnessRequest additional_request{1, request.distinctness_tolerance,
            {request.directions[1]}, request.seed};
        registry::Requirements selector_requirements;
        selector_requirements.output.representation = {"csl.witness-batch.v1"};
        const auto prepare_selector = [&](const WitnessRequest& selection_request) {
            const registry::SelectorRequest selector_request{*synthesis_result->family, selection_request};
            return take(registry::prepare_pipeline(registry::select(modules.selectors,
                {synthesis::witness_selector::selector_id, "1"}, selector_request, selector_requirements)));
        };
        auto first_selector = prepare_selector(first_request);
        auto first_workspaces = first_selector.create();
        auto additional_selector = prepare_selector(additional_request);
        auto additional_workspaces = additional_selector.create();
        const auto selection_setup_end = Clock::now();
        selection_setup_ns = ns(selection_setup_begin, selection_setup_end);
        timings.selection_setup_ns = static_cast<std::uint64_t>(selection_setup_ns);
        const auto selection_run_begin = Clock::now();
        timings.selection_run_begin = selection_run_begin;
        const auto first_query_begin = Clock::now();
        timings.first_query_begin = first_query_begin;
        const auto first_outcome = std::get<0>(first_workspaces)->run(context);
        const auto first_query_end = Clock::now();
        first_witness_query_ns = ns(first_query_begin, first_query_end);
        timings.first_query_ns = static_cast<std::uint64_t>(*first_witness_query_ns);
        if (!std::holds_alternative<WitnessSelection>(first_outcome))
            throw std::runtime_error("Witness selector rejected the first analytic direction query");
        const auto& first_selection = std::get<WitnessSelection>(first_outcome);
        if (first_selection.termination != Termination::completed ||
            first_selection.batch.returned_count() != 1)
            throw std::runtime_error("First witness query did not return one history");
        WitnessBatch partial{{first_selection.batch.witnesses.front()}, request.count,
            {synthesis::witness_selector::selector_id}, request.seed,
            synthesis_result->family->identity(), request.directions, request.distinctness_tolerance};
        selected_witnesses = WitnessSelection{std::move(partial), Termination::operation_rejected,
            "The additional direction query did not complete; the first witness is retained as partial evidence."};
        const auto additional_query_begin = Clock::now();
        timings.additional_query_begin = additional_query_begin;
        const auto additional_outcome = std::get<0>(additional_workspaces)->run(context);
        const auto additional_query_end = Clock::now();
        additional_witness_query_ns = ns(additional_query_begin, additional_query_end);
        timings.additional_query_ns = static_cast<std::uint64_t>(*additional_witness_query_ns);
        const auto selection_run_end = Clock::now();
        selection_run_ns = ns(selection_run_begin, selection_run_end);
        timings.selection_run_ns = static_cast<std::uint64_t>(selection_run_ns);
        if (!std::holds_alternative<WitnessSelection>(additional_outcome))
            throw std::runtime_error("Witness selector rejected the additional analytic direction query");
        const auto& additional_selection = std::get<WitnessSelection>(additional_outcome);
        if (additional_selection.termination != Termination::completed ||
            additional_selection.batch.returned_count() != 1)
            throw std::runtime_error("Witness selector did not return one history for each timed query");
        WitnessBatch combined{{}, request.count, {synthesis::witness_selector::selector_id},
            request.seed, synthesis_result->family->identity(), request.directions,
            request.distinctness_tolerance};
        combined.witnesses.reserve(request.count);
        combined.witnesses.push_back(first_selection.batch.witnesses.front());
        combined.witnesses.push_back(additional_selection.batch.witnesses.front());
        selected_witnesses = WitnessSelection{std::move(combined), Termination::completed,
            "Composed from ordered first and additional direction queries; no uniform sampling or uniqueness guarantee."};
        if (selected_witnesses->termination != Termination::completed ||
            selected_witnesses->batch.requested != request.count ||
            selected_witnesses->batch.returned_count() != request.count ||
            selected_witnesses->batch.distinct_count() != request.count)
            throw std::runtime_error("Witness selector returned an incomplete analytic request");
        const auto expected_synthesis = prepared.expected_synthesis_identity(strategy_index);
        if (!expected_synthesis.lineage)
            throw std::runtime_error("Prepared strategy has no lineage for independent witness verification");
        const auto verification_begin = Clock::now();
        timings.verification_begin = verification_begin;
        for (const auto& witness : selected_witnesses->batch.witnesses) {
            verification::TrajectoryRequest verification_request;
            verification_request.witness = witness;
            verification_request.assurance = expected_synthesis.request.assurance;
            verification_request.outcome = synthesis_result->outcome;
            verification_request.family = synthesis_result->family;
            verification_request.bounds = synthesis_result->objective;
            verification_request.expected_synthesis = verification::ExpectedSynthesisBinding{
                expected_synthesis.request, expected_synthesis.strategy,
                expected_synthesis.strategy_version, *expected_synthesis.lineage};
            verification_reports.push_back(verification::verify_trajectory(prepared.problem(),
                verification_request, context, modules.membership));
        }
        const auto verification_end = Clock::now();
        verification_ns = ns(verification_begin, verification_end);
        timings.verification_ns = static_cast<std::uint64_t>(verification_ns);
        for (const auto& report : verification_reports) {
            if (report.bindings != verification::CheckStatus::numerical_pass ||
                report.feasibility != verification::CheckStatus::numerical_pass ||
                report.objective != verification::CheckStatus::numerical_pass)
                quality_passed = false;
        }
    }
    const auto attempt_end = Clock::now();
    timings.end_to_end_ns = static_cast<std::uint64_t>(ns(*timings.attempt_begin, attempt_end));

    std::ostringstream event;
    event << "{\"schema\":\"csl.obs04-instrumentation-comparison-event/6\",\"repetition\":" << repetition
        << ",\"warmup\":" << (warmup ? "true" : "false") << ",\"strategy\":\""
        << (strategy_index == 0 ? "csl.synthesis.reach-back" : "csl.synthesis.strategy-b")
        << "\",\"instrumentation\":\"" << (enabled ? "enabled" : "disabled")
        << "\",\"setup_ns\":" << *timings.setup_ns << ",\"strategy_run_ns\":" << *timings.strategy_run_ns
        << ",\"family_construction_ns\":null"
        << ",\"end_to_end_ns\":" << *timings.end_to_end_ns
        << ",\"selection_setup_ns\":" << selection_setup_ns
        << ",\"selection_run_ns\":" << selection_run_ns
        << ",\"first_witness_query_ns\":"
        << (first_witness_query_ns ? std::to_string(*first_witness_query_ns) : "null")
        << ",\"additional_witness_query_ns\":"
        << (additional_witness_query_ns ? std::to_string(*additional_witness_query_ns) : "null")
        << ",\"verification_ns\":" << verification_ns
        << ",\"requested_witness_count\":" << (selected_witnesses ? selected_witnesses->batch.requested : 2)
        << ",\"returned_witness_count\":"
        << (selected_witnesses ? std::to_string(selected_witnesses->batch.returned_count()) : "null")
        << ",\"distinct_witness_count\":"
        << (selected_witnesses ? std::to_string(selected_witnesses->batch.distinct_count()) : "null")
        << ",\"spans_planned\":" << (enabled ? (strategy_index == 0 ? 5 : 1) : 0)
        << ",\"spans_completed\":" << completed_spans << ",\"span_clock_period_num\":"
        << (enabled ? Clock::period::num : 0) << ",\"span_clock_period_den\":" << (enabled ? Clock::period::den : 0)
        << ",\"span_timings\":[";
    for (std::size_t index = 0; index < span_events.size(); ++index) {
        if (index) event << ',';
        event << "{\"operation\":\"" << span_events[index].operation
            << "\",\"inclusive_wall_ticks\":" << span_events[index].inclusive
            << ",\"exclusive_wall_ticks\":" << span_events[index].exclusive << '}';
    }
    event << "],\"status\":\"" << attempt_status_name(status)
        << "\",\"phase_status\":\"" << (quality_passed?"passed":"failed")
        << "\",\"outcome\":\""
        << (observed?outcome_name(observed->outcome):"undetermined")
        << "\",\"analytic_family_checked\":" << (quality_passed?"true":"false")
        << ",\"complete_family_verified\":" << (observed&&observed->complete ? "true" : "false")
        << ",\"absolute_tolerance\":" << absolute_tolerance
        << ",\"relative_tolerance\":" << relative_tolerance << '}';

    auto statistics=timing_report?timing_report->observations:std::move(*setup.empty_statistics);
    const auto* synthesis=std::get_if<SynthesisResult>(&outcome);
    application::StrategyExecution recorded_execution{outcome,
        synthesis?ar::project_final(*synthesis):ar::FinalOutcome{ar::UnsupportedFinal{std::get<Unsupported>(outcome).diagnostics}},
        selected_witnesses ? application::SelectionOutcome{*selected_witnesses} : application::SelectionOutcome{std::monostate{}},
        std::move(verification_reports)};
    const ar::Unavailable unavailable{ar::MissingReason::not_requested,{}};
    const auto run_wire=take(application::encode_strategy_run(prepared.problem(),recorded_execution,
        std::move(setup.configuration),run_id,std::move(statistics),
        {unavailable,unavailable,unavailable,unavailable,false,ar::MemoryAccounting::unlimited}));
    auto run=take(ar::decode_recorded_run(run_wire,prepared.problem()));
    const auto measurement=event.str();
    std::cout << measurement << '\n';
    const auto arm=static_cast<std::uint32_t>(strategy_index*2+(enabled?1:0));
    return {arm,static_cast<std::uint32_t>(repetition),status,
        run_id,std::move(run),measurement,quality_passed};
}

std::string escaped(std::string_view value) {
    std::string result;
    for (const char ch : value) {
        if (ch == '"' || ch == '\\') { result.push_back('\\'); result.push_back(ch); }
        else if (ch == '\n') result += "\\n";
        else if (ch == '\r') result += "\\r";
        else if (static_cast<unsigned char>(ch) >= 0x20) result.push_back(ch);
    }
    return result;
}

TrialRecord failed_trial(const application::PreparedComparison& prepared, std::size_t strategy_index,
    bool enabled, std::size_t repetition, bool warmup, std::string_view message,
    ar::ResolvedConfiguration configuration, ar::CollectedStatistics statistics,
    bool invocation_started, const TrialTimings& timings) {
    const ar::RunId run_id{"obs04-" + std::to_string(strategy_index) + "-"+
        (enabled ? "enabled-" : "disabled-") + std::to_string(repetition) + (warmup ? "-warmup" : "")};
    const auto description=prepared.problem().description();
    const ar::Unavailable unavailable{ar::MissingReason::not_requested,{}};
    ar::RunRecord record{prepared.problem().identity(),description->model->dynamics.dimensions,
        static_cast<std::uint64_t>(description->times.size()-1),std::move(configuration),run_id,
        ar::FailedFinal{invocation_started?ar::FailurePhase::invoke:ar::FailurePhase::create,
            ar::FailureReason::adapter_exception,std::string(message),{}},
        std::move(statistics),{unavailable,unavailable,unavailable,unavailable,false,ar::MemoryAccounting::unlimited},
        {},{},ar::ProblemProvenance::problem_revalidated,{}};
    auto published=take(ar::publish_run({prepared.problem(),std::move(record)}));
    auto encoded=take(ar::encode_recorded_run(published));
    const auto bytes=encoded.content().bytes();
    std::string wire; wire.reserve(bytes.size());
    for(const auto byte:bytes)wire.push_back(static_cast<char>(std::to_integer<unsigned char>(byte)));
    auto run=take(ar::decode_recorded_run(wire,prepared.problem()));
    std::ostringstream event;
    event << "{\"schema\":\"csl.obs04-instrumentation-comparison-event/6\",\"repetition\":" << repetition
        << ",\"warmup\":" << (warmup?"true":"false") << ",\"strategy\":\""
        << (strategy_index==0?"csl.synthesis.reach-back":"csl.synthesis.strategy-b")
        << "\",\"instrumentation\":\"" << (enabled?"enabled":"disabled")
        << "\",\"setup_ns\":" << optional_ns_json(timings.setup_ns)
        << ",\"strategy_run_ns\":" << optional_ns_json(timings.strategy_run_ns)
        << ",\"family_construction_ns\":null,\"end_to_end_ns\":" << optional_ns_json(timings.end_to_end_ns)
        << ",\"selection_setup_ns\":" << optional_ns_json(timings.selection_setup_ns)
        << ",\"selection_run_ns\":" << optional_ns_json(timings.selection_run_ns)
        << ",\"first_witness_query_ns\":" << optional_ns_json(timings.first_query_ns)
        << ",\"additional_witness_query_ns\":" << optional_ns_json(timings.additional_query_ns)
        << ",\"verification_ns\":" << optional_ns_json(timings.verification_ns)
        << ",\"requested_witness_count\":2,\"returned_witness_count\":"
        << (timings.selected_witnesses?std::to_string(timings.selected_witnesses->batch.returned_count()):"null")
        << ",\"distinct_witness_count\":"
        << (timings.selected_witnesses?std::to_string(timings.selected_witnesses->batch.distinct_count()):"null")
        << ",\"status\":\"failed\",\"phase_status\":\"failed\",\"analytic_family_checked\":false,\"complete_family_verified\":false,\"error\":\""
        << escaped(message) << "\"}";
    const auto measurement=event.str();
    std::cout << measurement << '\n';
    return {static_cast<std::uint32_t>(strategy_index*2+(enabled?1:0)),
        static_cast<std::uint32_t>(repetition),ar::AttemptStatus::failed,
        run_id,std::move(run),measurement};
}

TrialRecord unserializable_outcome_trial(const application::PreparedComparison& prepared,
    std::size_t strategy_index, bool enabled, std::size_t repetition, bool warmup,
    const SynthesisOutcome& outcome, ar::ResolvedConfiguration configuration,
    ar::CollectedStatistics statistics, std::string_view message, const TrialTimings& timings) {
    const ar::RunId run_id{"obs04-"+std::to_string(strategy_index)+"-"+
        (enabled?"enabled-":"disabled-")+std::to_string(repetition)+(warmup?"-warmup":"")};
    const auto* synthesis=std::get_if<SynthesisResult>(&outcome);
    const ar::Unavailable unavailable{ar::MissingReason::not_requested,{}};
    const auto description=prepared.problem().description();
    std::ostringstream detail;
    detail << "Strategy returned a terminal outcome, but its run record could not be serialized. "
        << "Returned status=" << terminal_status_name(attempt_status(outcome));
    if(synthesis) {
        detail << ", termination=" << termination_name(synthesis->termination)
            << ", mathematical_outcome=" << outcome_name(synthesis->outcome.value);
        if(synthesis->family)
            detail << ", profile=" << synthesis->family->identity().request.profile
                << ", complete_family="
                << (std::holds_alternative<CompleteOptimalFamily>(synthesis->family->outcome())?"true":"false");
    } else {
        detail << ", mathematical_outcome=unsupported";
    }
    detail << ". Recording error: " << message;
    ar::RunRecord record{prepared.problem().identity(),description->model->dynamics.dimensions,
        static_cast<std::uint64_t>(description->times.size()-1),std::move(configuration),run_id,
        ar::FailedFinal{ar::FailurePhase::publication,ar::FailureReason::adapter_exception,detail.str(),{}},
        std::move(statistics),{unavailable,unavailable,unavailable,unavailable,false,ar::MemoryAccounting::unlimited},
        {},{},ar::ProblemProvenance::problem_revalidated,{}};
    auto published=take(ar::publish_run({prepared.problem(),std::move(record)}));
    auto encoded=take(ar::encode_recorded_run(published));
    const auto bytes=encoded.content().bytes();
    std::string wire;wire.reserve(bytes.size());
    for(const auto byte:bytes)wire.push_back(static_cast<char>(std::to_integer<unsigned char>(byte)));
    auto run=take(ar::decode_recorded_run(wire,prepared.problem()));
    std::ostringstream event;
    event << "{\"schema\":\"csl.obs04-instrumentation-comparison-event/6\",\"repetition\":"
        << repetition << ",\"warmup\":" << (warmup?"true":"false") << ",\"strategy\":\""
        << (strategy_index==0?"csl.synthesis.reach-back":"csl.synthesis.strategy-b")
        << "\",\"instrumentation\":\"" << (enabled?"enabled":"disabled")
        << "\",\"setup_ns\":" << optional_ns_json(timings.setup_ns)
        << ",\"strategy_run_ns\":" << optional_ns_json(timings.strategy_run_ns)
        << ",\"family_construction_ns\":null,\"end_to_end_ns\":" << optional_ns_json(timings.end_to_end_ns)
        << ",\"selection_setup_ns\":" << optional_ns_json(timings.selection_setup_ns)
        << ",\"selection_run_ns\":" << optional_ns_json(timings.selection_run_ns)
        << ",\"first_witness_query_ns\":" << optional_ns_json(timings.first_query_ns)
        << ",\"additional_witness_query_ns\":" << optional_ns_json(timings.additional_query_ns)
        << ",\"verification_ns\":" << optional_ns_json(timings.verification_ns)
        << ",\"requested_witness_count\":2,\"returned_witness_count\":"
        << "null"
        << ",\"distinct_witness_count\":"
        << "null"
        << ",\"status\":\"failed\",\"phase_status\":\"failed\",\"solver_returned\":true,"
        << "\"solver_outcome_in_run_artifact\":false,\"solver_status\":\""
        << terminal_status_name(attempt_status(outcome)) << "\",\"solver_termination\":\""
        << (synthesis?termination_name(synthesis->termination):"unsupported")
        << "\",\"solver_outcome\":\""
        << (synthesis?outcome_name(synthesis->outcome.value):"unsupported")
        << "\",\"complete_family_verified\":"
        << (synthesis&&synthesis->family&&
            std::holds_alternative<CompleteOptimalFamily>(synthesis->family->outcome())?"true":"false")
        << ",\"recording_error\":\"" << escaped(message) << "\"}";
    const auto measurement=event.str();
    std::cout << measurement << '\n';
    return {static_cast<std::uint32_t>(strategy_index*2+(enabled?1:0)),
        static_cast<std::uint32_t>(repetition),ar::AttemptStatus::failed,
        run_id,std::move(run),measurement,false};
}

TrialRecord recording_failure_trial(const application::PreparedComparison& prepared,
    std::size_t strategy_index, bool enabled, std::size_t repetition, bool warmup,
    const SynthesisOutcome& outcome, ar::ResolvedConfiguration configuration,
    ar::CollectedStatistics statistics, std::string_view message, const TrialTimings& timings) {
    const ar::RunId run_id{"obs04-"+std::to_string(strategy_index)+"-"+
        (enabled?"enabled-":"disabled-")+std::to_string(repetition)+(warmup?"-warmup":"")};
    const auto status=attempt_status(outcome);
    const auto* synthesis=std::get_if<SynthesisResult>(&outcome);
    application::StrategyExecution execution{outcome,
        synthesis?ar::project_final(*synthesis):ar::FinalOutcome{
            ar::UnsupportedFinal{std::get<Unsupported>(outcome).diagnostics}},
        timings.selected_witnesses?application::SelectionOutcome{*timings.selected_witnesses}:
            application::SelectionOutcome{std::monostate{}},timings.verification_reports};
    const ar::Unavailable unavailable{ar::MissingReason::not_requested,{}};
    std::string wire;
    try {
        wire=take(application::encode_strategy_run(prepared.problem(),execution,
            configuration,run_id,statistics,
            {unavailable,unavailable,unavailable,unavailable,false,ar::MemoryAccounting::unlimited}));
        auto run=take(ar::decode_recorded_run(wire,prepared.problem()));
        std::ostringstream event;
        event << "{\"schema\":\"csl.obs04-instrumentation-comparison-event/6\",\"repetition\":"
            << repetition << ",\"warmup\":" << (warmup?"true":"false") << ",\"strategy\":\""
            << (strategy_index==0?"csl.synthesis.reach-back":"csl.synthesis.strategy-b")
            << "\",\"instrumentation\":\"" << (enabled?"enabled":"disabled")
            << "\",\"setup_ns\":" << optional_ns_json(timings.setup_ns)
            << ",\"strategy_run_ns\":" << optional_ns_json(timings.strategy_run_ns)
            << ",\"family_construction_ns\":null,\"end_to_end_ns\":" << optional_ns_json(timings.end_to_end_ns)
            << ",\"selection_setup_ns\":" << optional_ns_json(timings.selection_setup_ns)
            << ",\"selection_run_ns\":" << optional_ns_json(timings.selection_run_ns)
            << ",\"first_witness_query_ns\":" << optional_ns_json(timings.first_query_ns)
            << ",\"additional_witness_query_ns\":" << optional_ns_json(timings.additional_query_ns)
            << ",\"verification_ns\":" << optional_ns_json(timings.verification_ns)
            << ",\"requested_witness_count\":2,\"returned_witness_count\":"
            << (timings.selected_witnesses?std::to_string(timings.selected_witnesses->batch.returned_count()):"null")
            << ",\"distinct_witness_count\":"
            << (timings.selected_witnesses?std::to_string(timings.selected_witnesses->batch.distinct_count()):"null")
            << ",\"status\":\"" << attempt_status_name(status)
            << "\",\"phase_status\":\"failed\",\"phase_error\":\"" << escaped(message)
            << "\",\"analytic_family_checked\":false,\"complete_family_verified\":false,\"recording_error\":\""
            << escaped(message) << "\"}";
        const auto measurement=event.str();
        std::cout << measurement << '\n';
        return {static_cast<std::uint32_t>(strategy_index*2+(enabled?1:0)),
            static_cast<std::uint32_t>(repetition),status,run_id,std::move(run),measurement,false};
    } catch(const std::exception& serialization_error) {
        return unserializable_outcome_trial(prepared,strategy_index,enabled,repetition,warmup,outcome,
            std::move(configuration),std::move(statistics),serialization_error.what(),timings);
    }
}

ar::CollectedStatistics empty_fallback_statistics(const problem::ResolvedProblem& problem,
    const ar::ResolvedConfiguration& configuration, const ar::RunId& run_id) {
    const bool enabled=configuration.description().collection.enabled;
    const ar::Unavailable completeness{enabled?ar::MissingReason::incomplete_span:
        ar::MissingReason::collection_disabled,{}};
    ar::CollectionRecord record{problem.identity(),configuration.identity(),run_id,
        configuration.description().collection,{}, {},{},completeness,{}, {}};
    return take(ar::publish_collection(std::move(record)));
}

std::optional<TrialRecord> trial(const application::PreparedComparison& prepared, std::size_t strategy_index,
    Modules& modules, bool enabled, std::size_t repetition, bool warmup, const Signature& expected,
    const ar::ResolvedConfiguration& resolved_configuration) {
    std::optional<ar::ResolvedConfiguration> fallback_configuration{resolved_configuration};
    std::optional<ar::CollectedStatistics> fallback_statistics;
    const ar::RunId run_id{"obs04-"+std::to_string(strategy_index)+"-"+
        (enabled?"enabled-":"disabled-")+std::to_string(repetition)+(warmup?"-warmup":"")};
    fallback_statistics=empty_fallback_statistics(prepared.problem(),resolved_configuration,run_id);
    std::optional<SynthesisOutcome> returned_outcome;
    bool invocation_started=false;
    TrialTimings timings;
    try {
        return trial_impl(prepared, strategy_index, modules, enabled, repetition, warmup, expected,
            resolved_configuration,
            fallback_configuration,fallback_statistics,returned_outcome,invocation_started,timings);
    } catch (const std::exception& error) {
        if(!fallback_configuration||!fallback_statistics)throw;
        timings.capture_partial();
        if(returned_outcome)
            return recording_failure_trial(prepared,strategy_index,enabled,repetition,warmup,
                *returned_outcome,std::move(*fallback_configuration),std::move(*fallback_statistics),error.what(),timings);
        return failed_trial(prepared,strategy_index,enabled,repetition,warmup,error.what(),
            std::move(*fallback_configuration),std::move(*fallback_statistics),invocation_started,timings);
    }
}

void profile_calls(const application::PreparedComparison& prepared, std::size_t strategy_index,
    std::size_t calls, const Signature& expected, PerfControl& perf_control) {
    if (!perf_control.configured())
        throw std::runtime_error("Profile mode requires acknowledged perf control and acknowledgement FIFOs");
    std::size_t passed = 0;
    for (std::size_t repetition = 0; repetition < calls; ++repetition) {
        auto workspaces = prepared.create();
        if (strategy_index >= workspaces.size())
            throw std::runtime_error("Profile strategy index is unavailable");
        ExecutionContext context;
        context.resources = std::make_shared<const ResourcePolicy>(ResourcePolicy{1, 1, 1, {}});
        context.numerical = prepared.family().numerical;
        perf_control.enable();
        const auto outcome = workspaces[strategy_index]->run(context);
        perf_control.disable();
        const auto observed = signature(outcome);
        require_ts01_analytic_result(outcome, observed);
        const bool equivalent = observed.termination == expected.termination &&
            observed.outcome == expected.outcome && close(observed.lower, expected.lower) &&
            close(observed.upper, expected.upper) && observed.profile == expected.profile &&
            observed.complete == expected.complete && observed.complete;
        if (!equivalent) throw std::runtime_error("Profile call changed the analytic comparison outcome");
        ++passed;
    }
    std::cout << "{\"schema\":\"csl.obs04-call-profile/1\",\"strategy\":\""
        << (strategy_index == 0 ? "csl.synthesis.reach-back" : "csl.synthesis.strategy-b")
        << "\",\"calls\":" << calls << ",\"passed\":" << passed
        << ",\"analytic_family_checked\":true,\"complete_family_verified\":true"
        << ",\"sample_scope\":\"acknowledged_perf_control_window\",\"perf_controlled\":true,\"acknowledged_commands\":"
        << perf_control.acknowledged_commands() << "}\n";
}
}

int main(int argc, char** argv) {
    try {
        if (std::string_view{OBS04_BUILD_CONFIGURATION} != "Release")
            throw std::runtime_error("OBS-04 comparison driver must be built with the Release configuration");
        std::optional<std::size_t> profile_strategy;
        std::size_t profile_calls_count = 0;
        std::optional<std::filesystem::path> requested_record_path;
        bool profile_strategy_seen = false;
        bool profile_calls_seen = false;
        for (int argument = 1; argument < argc; ++argument) {
            const std::string_view option{argv[argument]};
            if (option == "--profile-strategy" && argument + 1 < argc) {
                if (profile_strategy_seen)
                    throw std::invalid_argument("--profile-strategy may be provided only once");
                profile_strategy_seen = true;
                const std::string_view strategy{argv[++argument]};
                if (strategy == "reach-back") profile_strategy = 0;
                else if (strategy == "direct-joint") profile_strategy = 1;
                else throw std::invalid_argument("Profile strategy must be reach-back or direct-joint");
            } else if (option == "--profile-calls" && argument + 1 < argc) {
                if (profile_calls_seen)
                    throw std::invalid_argument("--profile-calls may be provided only once");
                profile_calls_seen = true;
                const std::string_view value{argv[++argument]};
                const auto [end, error] = std::from_chars(
                    value.data(), value.data() + value.size(), profile_calls_count);
                if (error != std::errc{} || end != value.data() + value.size())
                    throw std::invalid_argument("Profile call count must be a complete unsigned integer");
            } else if (option == "--record" && argument + 1 < argc) {
                if (requested_record_path)
                    throw std::invalid_argument("--record may be provided only once");
                requested_record_path=argv[++argument];
            } else {
                throw std::invalid_argument("usage: csl_obs04_instrumentation_comparison [--record path] | [--profile-strategy reach-back|direct-joint --profile-calls N]");
            }
        }
        if (profile_calls_count > 10000)
            throw std::invalid_argument("Profile call count must not exceed 10000");
        if (profile_strategy_seen != profile_calls_seen)
            throw std::invalid_argument("Profile strategy and positive call count must be provided together");
        if (profile_calls_seen && profile_calls_count == 0)
            throw std::invalid_argument("Profile call count must be positive");
        if(profile_strategy&&requested_record_path)
            throw std::invalid_argument("Profile mode and comparison-record capture are separate modes");
        PreflightTimings preflight;
        auto phase_begin=Clock::now();
        const auto scenario_bytes = read_scenario_file();
        preflight.scenario_file_read_ns=static_cast<std::uint64_t>(ns(phase_begin,Clock::now()));
        phase_begin=Clock::now();
        const auto parsed_scenario = Json::parse(scenario_bytes);
        if (!parsed_scenario.is_object()) throw std::runtime_error("OBS-04 scenario JSON root is not an object");
        preflight.scenario_json_parse_ns=static_cast<std::uint64_t>(ns(phase_begin,Clock::now()));
        phase_begin=Clock::now();
        const auto problem = load_scenario(scenario_bytes);
        preflight.scenario_load_validation_resolution_ns=static_cast<std::uint64_t>(ns(phase_begin,Clock::now()));
        phase_begin=Clock::now();
        auto modules = make_modules();
        preflight.provider_registration_ns=static_cast<std::uint64_t>(ns(phase_begin,Clock::now()));
        phase_begin=Clock::now();
        const auto prepared = prepare(problem, modules.strategies);
        preflight.comparison_admission_ns=static_cast<std::uint64_t>(ns(phase_begin,Clock::now()));
        std::array<ar::ResolvedConfiguration,4> configuration_templates{
            configuration_for(prepared,0,false),configuration_for(prepared,0,true),
            configuration_for(prepared,1,false),configuration_for(prepared,1,true)};
        const auto workspaces = prepared.create();
        std::array<Signature, 2> expected;
        for (std::size_t i = 0; i < workspaces.size(); ++i) {
            const auto baseline = workspaces[i]->run(ExecutionContext{
                std::make_shared<const ResourcePolicy>(ResourcePolicy{1, 1, 1, {}}), {}, {},
                prepared.family().numerical, "obs04-analytic-baseline", {}});
            expected[i] = signature(baseline);
            require_ts01_analytic_result(baseline, expected[i]);
        }
        if (profile_strategy) {
            auto warmup = prepared.create();
            ExecutionContext context;
            context.resources = std::make_shared<const ResourcePolicy>(ResourcePolicy{1, 1, 1, {}});
            context.numerical = prepared.family().numerical;
            const auto warmup_result = warmup[*profile_strategy]->run(context);
            const auto warmup_signature = signature(warmup_result);
            require_ts01_analytic_result(warmup_result, warmup_signature);
            if (warmup_signature.termination != expected[*profile_strategy].termination ||
                warmup_signature.outcome != expected[*profile_strategy].outcome ||
                !close(warmup_signature.lower, expected[*profile_strategy].lower) ||
                !close(warmup_signature.upper, expected[*profile_strategy].upper) ||
                warmup_signature.profile != expected[*profile_strategy].profile ||
                !warmup_signature.complete)
                throw std::runtime_error("Profile warmup changed the analytic comparison outcome");
            PerfControl perf_control;
            profile_calls(prepared, *profile_strategy, profile_calls_count,
                expected[*profile_strategy], perf_control);
            return 0;
        }
        std::cout << "# fixture=T-S01; strategies=reach-back,direct-joint; profile=ts01_exact_integrator\n"
            << "# timed_region=exclusive workspace StrategyPort::run; setup and collection snapshot are reported separately\n"
            << "# alternation=strategy execution order and instrumentation mode both alternate by repetition\n"
            << "# instrumentation=Strategy A phase spans; Strategy B run span; CPU and native backend threads unavailable\n";
        std::size_t failures = 0;
        std::vector<TrialRecord> captured;
        for (std::size_t repetition = 0; repetition <= 7; ++repetition) {
            const bool warmup = repetition == 0;
            for (std::size_t slot = 0; slot < 2; ++slot) {
                const std::size_t strategy = (repetition + slot) % 2;
                const bool enabled_first = ((repetition + strategy) % 2) != 0;
                for(const bool enabled : {enabled_first,!enabled_first}) {
                    auto result=trial(prepared,strategy,modules,enabled,repetition,warmup,expected[strategy],
                        configuration_templates[strategy*2+(enabled?1u:0u)]);
                    if(!result) { ++failures; continue; }
                    if(result->status!=ar::AttemptStatus::completed||!result->quality_passed)++failures;
                    captured.push_back(std::move(*result));
                }
            }
        }
        std::sort(captured.begin(),captured.end(),[](const auto& left,const auto& right) {
            return std::pair{left.arm_index,left.repetition_index}<std::pair{right.arm_index,right.repetition_index};
        });
        if(captured.size()!=32)throw std::runtime_error("The comparison record does not contain all 32 warmup and measured attempts");
        std::array<std::string,4> config_ids{};
        for(const auto& attempt:captured) {
            if(attempt.repetition_index!=0)continue;
            config_ids.at(attempt.arm_index)=take(ar::comparison_configuration_id(attempt.run)).value;
        }
        for(const auto& id:config_ids)if(id.empty())throw std::runtime_error("Comparison record is missing a configuration arm");
        const auto request_digest=take(ar::comparison_request_digest(captured.front().run));
        for(const auto& attempt:captured)
            if(take(ar::comparison_request_digest(attempt.run))!=request_digest)
                throw std::runtime_error("Comparison arms do not share the same mathematical request");
        const auto canonical_problem=problem.canonical_bytes();
        const auto manifest_bytes=std::span<const std::byte>{canonical_problem};
        const auto input_manifest_hash=take(problem::snapshot_content(manifest_bytes)).digest();
        Json arms=Json::array();
        for(std::size_t index=0;index<config_ids.size();++index) {
            arms.push_back({{"configuration_id",config_ids[index]},
                {"instrumentation",index%2==0?"disabled":"enabled"},
                {"strategy",index/2==0?"csl.synthesis.reach-back":"csl.synthesis.strategy-b"}});
        }
        const Json spec{{"arms",std::move(arms)},
            {"environment",environment_manifest(argc>0?argv[0]:std::string_view{})},
            {"input_manifest_hash",problem::hex(input_manifest_hash)},
            {"input_manifest_source","resolved-problem-canonical-bytes"},
            {"problem_id",problem.identity().value},{"repetitions",8},
            {"request_digest",problem::hex(request_digest)},{"schema","csl.comparison-spec/3"}};
        const auto spec_text=spec.dump();
        const auto spec_content_result=problem::snapshot_content(std::span<const std::byte>{
            reinterpret_cast<const std::byte*>(spec_text.data()),spec_text.size()});
        auto spec_content=take(std::move(spec_content_result));
        std::vector<ar::ComparisonAttempt> attempts;
        attempts.reserve(captured.size());
        for(auto& attempt:captured)
            attempts.push_back({attempt.arm_index,attempt.repetition_index,attempt.status,
                {attempt.run_id,attempt.run.content().digest()},std::move(attempt.run),
                std::move(attempt.measurement_payload)});
        auto comparison=take(ar::encode_recorded_comparison(spec_content,attempts));
        std::string comparison_wire;
        for(const auto byte:comparison.content().bytes())
            comparison_wire.push_back(static_cast<char>(std::to_integer<unsigned char>(byte)));
        const auto replay=take(ar::decode_recorded_comparison(comparison_wire));
        if(replay.content().digest()!=comparison.content().digest())
            throw std::runtime_error("Saved comparison record failed exact round-trip identity");
        const std::filesystem::path record_path=requested_record_path?*requested_record_path:
            std::filesystem::path{"obs04-comparison-record-"+problem::hex(comparison.content().digest())+".json"};
        if(std::filesystem::exists(record_path))
            throw std::runtime_error("Refusing to overwrite existing comparison record: "+record_path.string());
        std::ofstream output(record_path,std::ios::binary|std::ios::out);
        if(!output||!(output<<comparison_wire)||!output.flush())
            throw std::runtime_error("Could not write comparison record: "+record_path.string());
        const auto comparison_json=Json::parse(comparison_wire);
        std::cout << "# shared_preflight=" << Json{{"schema","csl.obs04-shared-preflight/2"},
            {"comparison_spec_id",comparison_json.at("comparison_spec_id")},
            {"comparison_run_id",comparison_json.at("comparison_run_id")},
            {"scope","selected_shared_preflight_blocks_before_configuration_workspaces_and_baselines"},
            {"scenario_file_read_ns",preflight.scenario_file_read_ns},
            {"scenario_json_parse_ns",preflight.scenario_json_parse_ns},
            {"scenario_load_validation_resolution_ns",preflight.scenario_load_validation_resolution_ns},
            {"provider_registration_ns",preflight.provider_registration_ns},
            {"comparison_admission_ns",preflight.comparison_admission_ns}}.dump() << '\n';
        std::cout << "# comparison_record_digest=" << problem::hex(comparison.content().digest())
            << "; attempts=" << attempts.size() << "; failures=" << failures << '\n';
        if (failures != 0) return 1;
    } catch (const std::exception& error) {
        std::cerr << "OBS-04 measurement failed: " << error.what() << '\n';
        return 1;
    }
    return 0;
}
