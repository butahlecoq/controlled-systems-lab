#include <csl/adapters/convex/highs.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <csl/adapters/polyhedral/qhull.hpp>
#include <csl/application/comparison.hpp>
#include <csl/execution/timing_collector.hpp>
#include <csl/geometry/affine_sum.hpp>
#include <csl/geometry/hull_reducer.hpp>
#include <csl/geometry/polyhedral_projection.hpp>
#include <csl/problem/validator.hpp>
#include <csl/synthesis/strategy_a/strategy.hpp>
#include <csl/synthesis/strategy_b/direct_joint.hpp>
#include <csl/synthesis/witness_selector.hpp>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <string_view>
#include <type_traits>
#include <utility>

#if !defined(NDEBUG) || defined(_DEBUG)
#error "The OBS-04 measurement executable must be compiled as a Release target"
#endif

namespace {
using namespace csl;
namespace ar = artifacts;
namespace ob = execution::observability;
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

SetHandle interval(std::string id) {
    return take(sets::make_h({{std::move(id)}, 1, {"u"}},
        {take(numeric::snapshot(Matrix{2, 1, {1, -1}})),
         take(numeric::snapshot_vector(Vector{1, 0})),
         take(numeric::snapshot(Matrix{0, 1, {}})),
         take(numeric::snapshot_vector(Vector{}))})).as_handle();
}

problem::ResolvedProblem source() {
    return take(problem::resolve({{"obs04-ts01-instrumentation"},
        std::make_shared<const SystemModel>(SystemModel{{
            {1, 1, 0}, TimeDomain::discrete,
            LinearStage{{1, 1, {1}}, {1, 1, {1}}, {1, 0, {}}, {0}}}, {}}),
        {0, 1, 2}, KnownInitial{{0}}, ContinuousDomain{{interval("u0"), interval("u1")}},
        {UniversalSet{1}, UniversalSet{1}, UniversalSet{1}}, {}, {},
        InformationPattern::nominal_open_loop, QuadraticTerminal{{1, 1, {2}}, {-2}, 1}},
        {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}}));
}

struct Modules {
    std::shared_ptr<registry::Registry<registry::GeometryPort>> projections;
    std::shared_ptr<registry::Registry<registry::GeometryPort>> affines;
    std::shared_ptr<registry::Registry<registry::ConversionPort>> conversions;
    std::shared_ptr<registry::Registry<registry::LPPort>> lps;
    std::shared_ptr<registry::Registry<registry::ConvexPort>> convexes;
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
        std::move(lps), std::move(convexes), {}};
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

std::shared_ptr<ob::TimingCollector> collector_for(const application::PreparedComparison& prepared,
    std::size_t strategy_index, std::string run_id) {
    const auto clock = ob::make_steady_timing_clock();
    const auto& configuration = prepared.strategies()[strategy_index];
    const auto expected = prepared.expected_synthesis_identity(strategy_index);
    const ar::Unavailable missing{ar::MissingReason::not_instrumented, {}};
    ar::ConfigurationInput config;
    config.collection = {true, ar::CollectionMode::summary, 5, 10000, 0, 0};
    config.modules = {{"strategy", {expected.strategy, expected.strategy_version, missing}, {}},
        {"lp", {configuration.lp, "1", missing}, {}},
        {"convex", {configuration.convex, "1", missing}, {}}};
    config.numerical = prepared.family().numerical;
    config.resources = {1, 1, 1, {}};
    config.output = {ar::OutputKind::synthesis, prepared.family().assurance,
        prepared.family().target, prepared.family().representation, {2, 0, {{1, -1}, {-1, 1}}, 31}};
    config.selector = {{synthesis::witness_selector::selector_id}, "1", {}};
    config.strategy = configuration;
    config.strategy.selector = config.selector.id;
    const auto resolved_config = take(ar::resolve_configuration(std::move(config)));

    ob::PlanInput plan{prepared.problem(), resolved_config, {run_id}, {clock->wall_domain()}, {}, 1};
    const std::size_t span_count = strategy_index == 0 ? 5 : 1;
    plan.tasks = {strategy_index == 0 ? "strategy-a" : "strategy-b"};
    plan.operations = strategy_index == 0
        ? std::vector<std::string>{"strategy-a/run", "strategy-a/forward", "strategy-a/feasible-preimage",
            "strategy-a/terminal-optimization", "strategy-a/terminal-preimage"}
        : std::vector<std::string>{"strategy-b/run"};
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
    return take(ob::make_timing_collector(std::move(collection_plan), clock, {0}, {}));
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

void trial_impl(const application::PreparedComparison& prepared, std::size_t strategy_index,
    bool enabled, std::size_t repetition, bool warmup, const Signature& expected) {
    const auto setup_begin = Clock::now();
    auto collector = enabled ? collector_for(prepared, strategy_index,
        "obs04-" + std::to_string(strategy_index) + "-" + std::to_string(repetition) + (warmup ? "-warmup" : "")) : nullptr;
    auto workspaces = prepared.create();
    ExecutionContext context;
    context.resources = std::make_shared<const ResourcePolicy>(ResourcePolicy{1, 1, 1, {}});
    context.numerical = prepared.family().numerical;
    if (collector) context.timing = collector;
    const auto setup_end = Clock::now();
    const auto run_begin = Clock::now();
    const auto outcome = workspaces[strategy_index]->run(context);
    const auto run_end = Clock::now();
    const auto observed = signature(outcome);
    require_ts01_analytic_result(outcome, observed);
    const bool equivalent = observed.termination == expected.termination && observed.outcome == expected.outcome &&
        close(observed.lower, expected.lower) && close(observed.upper, expected.upper) &&
        observed.profile == expected.profile && observed.complete == expected.complete && observed.complete;
    if (!equivalent) throw std::runtime_error("Instrumentation changed the analytic comparison outcome");

    std::size_t observed_spans = 0;
    std::size_t completed_spans = 0;
    std::vector<ob::SpanTiming> span_timings;
    std::vector<ar::SpanRecord> span_records;
    if (collector) {
        const auto report = take(collector->snapshot());
        observed_spans = report.observations.description().spans.size();
        for (const auto& span : report.observations.description().spans)
            if (span.completion_observed) ++completed_spans;
        span_timings = report.spans;
        span_records = report.observations.description().spans;
        if (!report.diagnostics.empty() || observed_spans != (strategy_index == 0 ? 5u : 1u) ||
            completed_spans != observed_spans || span_timings.size() != observed_spans)
            throw std::runtime_error("Timing collector did not retain every expected completed span");
    }
    struct SpanEvent { std::string operation; std::uint64_t inclusive, exclusive; };
    std::vector<SpanEvent> span_events;
    span_events.reserve(span_timings.size());
    for (std::size_t index = 0; index < span_timings.size(); ++index) {
        const auto inclusive = std::get_if<ar::Available<std::uint64_t>>(&span_timings[index].inclusive_wall_ticks);
        const auto exclusive = std::get_if<ar::Available<std::uint64_t>>(&span_timings[index].exclusive_wall_ticks);
        if (!inclusive || !exclusive || span_timings[index].id != span_records[index].descriptor.id)
            throw std::runtime_error("Timing collector returned unavailable or misaligned span durations");
        span_events.push_back({span_records[index].descriptor.operation, inclusive->value, exclusive->value});
    }
    std::cout << "{\"schema\":\"csl.obs04-instrumentation-comparison-event/2\",\"repetition\":" << repetition
        << ",\"warmup\":" << (warmup ? "true" : "false") << ",\"strategy\":\""
        << (strategy_index == 0 ? "csl.synthesis.reach-back" : "csl.synthesis.strategy-b")
        << "\",\"instrumentation\":\"" << (enabled ? "enabled" : "disabled")
        << "\",\"setup_ns\":" << ns(setup_begin, setup_end) << ",\"strategy_run_ns\":" << ns(run_begin, run_end)
        << ",\"spans_planned\":" << (enabled ? (strategy_index == 0 ? 5 : 1) : 0)
        << ",\"spans_completed\":" << completed_spans << ",\"span_clock_period_num\":"
        << (enabled ? Clock::period::num : 0) << ",\"span_clock_period_den\":" << (enabled ? Clock::period::den : 0)
        << ",\"span_timings\":[";
    for (std::size_t index = 0; index < span_events.size(); ++index) {
        if (index) std::cout << ',';
        std::cout << "{\"operation\":\"" << span_events[index].operation
            << "\",\"inclusive_wall_ticks\":" << span_events[index].inclusive
            << ",\"exclusive_wall_ticks\":" << span_events[index].exclusive << '}';
    }
    std::cout << "],\"status\":\"passed\",\"outcome\":\"" << outcome_name(observed.outcome)
        << "\",\"analytic_family_checked\":true,\"complete_family_verified\":"
        << (observed.complete ? "true" : "false") << ",\"absolute_tolerance\":" << absolute_tolerance
        << ",\"relative_tolerance\":" << relative_tolerance << "}\n";
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

bool trial(const application::PreparedComparison& prepared, std::size_t strategy_index,
    bool enabled, std::size_t repetition, bool warmup, const Signature& expected) {
    try {
        trial_impl(prepared, strategy_index, enabled, repetition, warmup, expected);
        return true;
    } catch (const std::exception& error) {
        std::cout << "{\"schema\":\"csl.obs04-instrumentation-comparison-event/2\",\"repetition\":" << repetition
            << ",\"warmup\":" << (warmup ? "true" : "false") << ",\"strategy\":\""
            << (strategy_index == 0 ? "csl.synthesis.reach-back" : "csl.synthesis.strategy-b")
            << "\",\"instrumentation\":\"" << (enabled ? "enabled" : "disabled")
        << "\",\"status\":\"failed\",\"analytic_family_checked\":false,\"complete_family_verified\":false,\"error\":\""
            << escaped(error.what()) << "\"}\n";
        return false;
    }
}
}

int main() {
    try {
        const auto problem = source();
        auto modules = make_modules();
        const auto prepared = prepare(problem, modules.strategies);
        const auto workspaces = prepared.create();
        std::array<Signature, 2> expected;
        for (std::size_t i = 0; i < workspaces.size(); ++i) {
            const auto baseline = workspaces[i]->run(ExecutionContext{
                std::make_shared<const ResourcePolicy>(ResourcePolicy{1, 1, 1, {}}), {}, {},
                prepared.family().numerical, "obs04-analytic-baseline", {}});
            expected[i] = signature(baseline);
            require_ts01_analytic_result(baseline, expected[i]);
        }
        std::cout << "# fixture=T-S01; strategies=reach-back,direct-joint; profile=ts01_exact_integrator\n"
            << "# timed_region=exclusive workspace StrategyPort::run; setup and collection snapshot are reported separately\n"
            << "# alternation=strategy execution order and instrumentation mode both alternate by repetition\n"
            << "# instrumentation=Strategy A phase spans; Strategy B run span; CPU and native backend threads unavailable\n";
        std::size_t failures = 0;
        for (std::size_t repetition = 0; repetition <= 7; ++repetition) {
            const bool warmup = repetition == 0;
            for (std::size_t slot = 0; slot < 2; ++slot) {
                const std::size_t strategy = (repetition + slot) % 2;
                const bool enabled_first = ((repetition + strategy) % 2) != 0;
                if (!trial(prepared, strategy, enabled_first, repetition, warmup, expected[strategy])) ++failures;
                if (!trial(prepared, strategy, !enabled_first, repetition, warmup, expected[strategy])) ++failures;
            }
        }
        if (failures != 0) return 1;
    } catch (const std::exception& error) {
        std::cerr << "OBS-04 measurement failed: " << error.what() << '\n';
        return 1;
    }
    return 0;
}
