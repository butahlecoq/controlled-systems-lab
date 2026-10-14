#include <csl/adapters/convex/highs.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <csl/adapters/polyhedral/qhull.hpp>
#include <csl/geometry/affine_sum.hpp>
#include <csl/input/scenario_loader.hpp>
#include <csl/synthesis/strategy_a/strategy.hpp>
#include <csl/synthesis/strategy_b/direct_joint.hpp>
#include <csl/synthesis/witness_selector.hpp>
#include <csl/verification/trajectory.hpp>
#include <fstream>
#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <locale>
#include <optional>
#include <sstream>
#include <span>
#include <stdexcept>
#include <type_traits>

namespace {
using namespace csl;
using namespace csl::registry;

// This export is a teaching-example summary, never a portable family or proof.
// csl.run-statistics/4 currently cannot encode live T-S01 completeness support.
std::string quoted(std::string_view value) {
    std::ostringstream out;
    out << '"';
    for (const unsigned char c : value) {
        switch (c) {
        case '"': out << "\\\""; break;
        case '\\': out << "\\\\"; break;
        case '\n': out << "\\n"; break;
        case '\r': out << "\\r"; break;
        case '\t': out << "\\t"; break;
        default:
            if (c < 0x20) out << "\\u" << std::hex << std::setw(4) << std::setfill('0') << static_cast<unsigned int>(c) << std::dec;
            else out << static_cast<char>(c);
        }
    }
    out << '"';
    return out.str();
}

template<class T, class... Others> T take(std::variant<T, Others...> result, std::string_view stage) {
    if (auto* value = std::get_if<T>(&result)) return std::move(*value);
    std::ostringstream message;
    message << stage << " rejected";
    std::visit([&](const auto& error) {
        using E = std::decay_t<decltype(error)>;
        if constexpr (std::is_same_v<E, Rejection>) {
            message << " " << error.provenance.requested.id.value;
            for (const auto& diagnostic : error.diagnostics) message << ": " << diagnostic.field << " " << diagnostic.explanation;
        } else if constexpr (std::is_same_v<E, Unsupported>) {
            for (const auto& diagnostic : error.diagnostics) message << ": " << diagnostic.field << " " << diagnostic.explanation;
        }
    }, result);
    throw std::runtime_error(message.str());
}

template<class Port> PreparedProvider<Port> selected(Registration<Port> entry, std::string representation) {
    Registry<Port> registry;
    const Method method{entry.identity.id, entry.identity.version};
    if (registry.add(std::move(entry))) throw std::runtime_error("Provider registration failed");
    Requirements requirements;
    requirements.output.representation = {std::move(representation)};
    if constexpr (std::is_same_v<Port, GeometryPort> || std::is_same_v<Port, ConversionPort>)
        requirements.output.relation = SetRelation::equivalent;
    return take(prepare_provider(select_provider(registry, method, requirements)), "Provider selection");
}

void provenance_json(std::ostream& out, std::span<const Provenance> provenance) {
    out << '[';
    bool comma = false;
    for (const auto& entry : provenance) {
        if (comma) out << ',';
        comma = true;
        if (!entry.actual) throw std::runtime_error("Prepared module has no actual identity");
        out << "{\"port\":" << quoted(entry.port) << ",\"requested\":" << quoted(entry.requested.id.value)
            << ",\"actual\":" << quoted(entry.actual->id.value) << ",\"version\":" << quoted(entry.actual->version) << '}';
    }
    out << ']';
}

void history_json(std::ostream& out, const std::vector<Vector>& history) {
    out << '[';
    for (std::size_t i = 0; i < history.size(); ++i) {
        if (i) out << ',';
        out << '[';
        for (std::size_t j = 0; j < history[i].size(); ++j) { if (j) out << ','; out << history[i][j]; }
        out << ']';
    }
    out << ']';
}

void family_identity_json(std::ostream& out, const FamilyIdentity& identity) {
    out << "{\"problem\":" << quoted(identity.problem.value) << ",\"strategy\":" << quoted(identity.strategy.value)
        << ",\"strategy_version\":" << quoted(identity.strategy_version)
        << ",\"request\":{\"profile\":" << quoted(identity.request.profile)
        << ",\"objective\":" << quoted(identity.request.objective.value)
        << ",\"target\":\"exact_optimal_relation\",\"assurance\":\"numerical\",\"representation\":"
        << quoted(identity.request.representation.value) << ",\"absolute_tolerance\":" << identity.request.numerical.absolute_tolerance
        << ",\"relative_tolerance\":" << identity.request.numerical.relative_tolerance << ",\"materialization_limit\":null}"
        << ",\"coordinates\":{\"state\":" << identity.coordinates.dimensions.state << ",\"control\":" << identity.coordinates.dimensions.control
        << ",\"external\":" << identity.coordinates.dimensions.external << ",\"horizon\":" << identity.coordinates.horizon << "},\"lineage\":[";
    for (std::size_t i = 0; i < identity.lineage.size(); ++i) {
        if (i) out << ',';
        const auto& step = identity.lineage[i];
        out << "{\"request\":" << quoted(step.request.value) << ",\"input\":" << quoted(step.input.value)
            << ",\"output\":" << quoted(step.output.value) << ",\"module\":" << quoted(step.module.value)
            << ",\"version\":" << quoted(step.version) << '}';
    }
    out << "]}";
}

std::string_view check_name(verification::CheckStatus status) {
    using verification::CheckStatus;
    switch (status) {
    case CheckStatus::not_checked: return "not_checked";
    case CheckStatus::numerical_pass: return "numerical_pass";
    case CheckStatus::violation: return "violation";
    case CheckStatus::invalid_input: return "invalid_input";
    case CheckStatus::unsupported: return "unsupported";
    }
    throw std::runtime_error("Unknown verification status");
}

using Clock = std::chrono::steady_clock;
std::uint64_t elapsed_ns(Clock::time_point start, Clock::time_point end) {
    return static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(end - start).count());
}
void timing_json(std::ostream& out, std::optional<std::uint64_t> value, std::string_view unavailable_reason) {
    if (value) out << "{\"available\":true,\"value\":" << *value << ",\"unit\":\"ns\"}";
    else out << "{\"available\":false,\"reason\":" << quoted(unavailable_reason) << '}';
}
void resource_policy_json(std::ostream& out, const ResourcePolicy& policy) {
    out << "{\"total_threads\":" << policy.total_threads << ",\"outer_workers\":" << policy.outer_workers
        << ",\"threads_per_worker\":" << policy.threads_per_worker << ",\"memory_bytes\":";
    if (policy.memory_bytes) out << *policy.memory_bytes;
    else out << "null";
    out << '}';
}
}

int main(int argc, char** argv) try {
    using namespace csl;
    using namespace csl::registry;
    const bool measure = argc >= 2 && std::string_view(argv[1]) == "--measure";
    const int scenario_index = measure ? 2 : 1;
    if ((measure && (argc < 3 || argc > 4)) || (!measure && (argc < 2 || argc > 3))) {
        std::cerr << "Usage: registered_synthesis_comparison <two-stage-integrator.json> [results.json]\n"
                  << "   or: registered_synthesis_comparison --measure <two-stage-integrator.json> [events.jsonl]\n";
        return 2;
    }
    const auto scenario_load_started = Clock::now();
    const auto loaded = input::load_scenario_file(argv[scenario_index]);
    if (const auto* error = std::get_if<input::InputFailure>(&loaded)) {
        std::cerr << "Input rejected: " << error->path << "; expected " << error->expected << '\n'; return 2;
    }
    if (const auto* error = std::get_if<input::UnsupportedInput>(&loaded)) {
        std::cerr << "Input unsupported: " << error->path << "; expected " << error->expected << '\n'; return 2;
    }
    if (!std::holds_alternative<input::LoadedScenario>(loaded)) {
        std::cerr << "Input rejected: historical or stopped input is not executable\n"; return 2;
    }
    const auto& scenario = std::get<input::LoadedScenario>(loaded);
    const auto& intent = *scenario.requested_run();
    if (!std::holds_alternative<input::ComparisonRequest>(intent.selection) || !intent.backends.empty() || intent.representation ||
        intent.witnesses || intent.numerical || intent.resources || intent.seed) {
        std::cerr << "Input rejected: this fixed T-S01 comparison does not accept run overrides\n"; return 2;
    }
    // Loading resolves once; every StrategyRequest copies the same immutable storage.
    const auto resolved = scenario.problem();
    const auto scenario_load_ns = elapsed_ns(scenario_load_started, Clock::now());
    FamilyRequest family;
    family.profile = "ts01_exact_integrator";
    family.objective = resolved.identity();
    family.target = FamilyTarget::exact_optimal_relation;
    family.assurance = Assurance::numerical;
    family.representation = {"csl.polyhedron.h"};
    ExecutionContext context;
    context.numerical = family.numerical;
    const ResourcePolicy resource_policy{1,1,1,{}};
    context.resources = std::make_shared<const ResourcePolicy>(resource_policy);

    const auto provider_setup_started = Clock::now();
    auto lp = take(adapters::lp::make_highs_registration(), "LP registration");
    auto convex = take(adapters::convex::make_highs_registration(), "Convex registration");
    auto converter = take(adapters::polyhedral::make_qhull_registration(lp), "Conversion registration");
    auto projection = geometry::polyhedral::make_projection_registration();
    auto affine = geometry::make_affine_sum_registration({selected(geometry::make_lp_hull_reducer_registration(), ""),
        selected(lp, "csl.program-result.v1"), selected(converter, "csl.polyhedron.v")});
    Registry<GeometryPort> projections, affines;
    Registry<ConversionPort> conversions;
    Registry<LPPort> lps;
    Registry<ConvexPort> convexes;
    const Method pm{projection.identity.id, {}}, am{affine.identity.id, {}}, cm{converter.identity.id, {}},
        lm{lp.identity.id, {}}, qm{convex.identity.id, {}};
    if (projections.add(projection) || affines.add(affine) || conversions.add(converter) || lps.add(lp) || convexes.add(convex))
        throw std::runtime_error("Module registration failed");
    Requirements h, v, program;
    h.output.representation = {"csl.polyhedron.h"}; h.output.relation = SetRelation::equivalent;
    v.output.representation = {"csl.polyhedron.v"}; v.output.relation = SetRelation::equivalent;
    program.output.representation = {"csl.program-result.v1"};
    auto providers = take(check_providers(select_provider(projections, pm, h), select_provider(affines, am, v),
        select_provider(conversions, cm, h), select_provider(lps, lm, program), select_provider(convexes, qm, program)), "Strategy A providers");
    StrategyRegistry strategies;
    if (strategies.add(synthesis::strategy_a::make_registration(std::move(providers))) ||
        strategies.add(synthesis::strategy_b::make_registration(lps, convexes))) throw std::runtime_error("Strategy registration failed");
    const auto membership = take(prepare_provider(select_provider(lps, lm, program)), "Membership LP");
    Registry<SelectorPort> selectors;
    if (selectors.add(synthesis::witness_selector::make_registration(membership))) throw std::runtime_error("Selector registration failed");
    Requirements output;
    output.output.representation = family.representation; output.output.family = family.target;
    output.output.completeness = Completeness::established;
    Requirements witness_output; witness_output.output.representation = {"csl.witness-batch.v1"};
    const auto shared_provider_setup_ns = elapsed_ns(provider_setup_started, Clock::now());

    if (measure) {
        std::ofstream event_file;
        if (argc == 4) {
            std::ifstream existing(argv[3], std::ios::binary);
            if (existing.good()) { std::cerr << "Output rejected: events file already exists\n"; return 2; }
            event_file.open(argv[3], std::ios::binary | std::ios::out);
            if (!event_file) { std::cerr << "Output rejected: cannot create events file\n"; return 2; }
        }
        const auto emit = [&](const std::string& line) {
            std::cout << line;
            if (event_file) event_file << line;
            if (!std::cout || (event_file && !event_file)) throw std::runtime_error("Measurement event output failed");
        };
        std::ostringstream header;
        header.imbue(std::locale::classic());
        header << std::setprecision(17)
            << "{\"schema\":\"csl.synthesis.paired-ts01-event/1\",\"event\":\"header\",\"problem\":"
            << quoted(resolved.identity().value) << ",\"scenario_sha256\":" << quoted(problem::hex(scenario.source()->content.digest()))
            << ",\"profile\":\"ts01_exact_integrator\",\"target\":\"exact_optimal_relation\",\"representation\":\"csl.polyhedron.h\",\"assurance\":\"numerical\","
            << "\"resource_policy\":";
        resource_policy_json(header, *context.resources);
        header
            << ",\"absolute_tolerance\":" << family.numerical.absolute_tolerance << ",\"relative_tolerance\":" << family.numerical.relative_tolerance
            << ",\"shared_setup_ns\":{\"scenario_load_and_resolution\":" << scenario_load_ns
            << ",\"provider_and_registry_setup\":" << shared_provider_setup_ns << "},"
            << "\"shared_setup_scope\":\"Scenario JSON parse and immutable resolution are timed once; provider registration/selection, strategy and selector registries, and prepared membership provider are timed once. These shared setup values are excluded from per-strategy totals.\","
            << "\"order_policy\":\"One excluded A-then-B warmup pair; seven measured pairs alternate A/B then B/A. Both members of every pair share this immutable resolved problem and provider registries.\","
            << "\"per_strategy_scope\":\"Fresh StrategyRegistry::prepare through exclusive workspace creation, public StrategyPort run and complete-family acceptance, selector preparation/query returning two distinct histories, and witness-only verification of both histories against the original resolved problem. Excludes process startup, shared scenario/provider setup, JSON serialization/file I/O, build, plots and report rendering.\","
            << "\"phase_scope\":{\"preparation_ns\":\"StrategyRegistry::prepare including capability admission and immutable plan creation\",\"workspace_creation_ns\":\"Prepared strategy create through exclusive workspace return\",\"family_construction_ns\":\"Public workspace run through result return, including the registered exact-profile verifier\",\"selector_preparation_ns\":\"Selector selection/preparation for this strategy result\",\"selector_workspace_creation_ns\":\"Prepared selector create through exclusive query workspace return\",\"witness_query_ns\":\"Selector workspace run and checked batch binding/count\",\"original_verification_ns\":\"verification::verify_trajectory for both selected witnesses\",\"end_to_end_strategy_ns\":\"Preparation start through completion of both original-data witness checks; inclusive total, not a sum of other measured phases\"},"
            << "\"phase_counters_unavailable\":[\"Internal LP/convex, projection, affine-sum, conversion, hull-membership and verifier subphase durations/call counts are not exposed by these public APIs.\",\"CPU time and per-call peak memory are not measured by this timing driver.\"]}\n";
        emit(header.str());

        const auto run_measured = [&](const char* id, std::size_t repetition, bool warmup, std::size_t order_position) {
            Clock::time_point total_started{};
            std::optional<std::uint64_t> end_to_end_ns;
            std::optional<std::uint64_t> preparation_ns, workspace_creation_ns, family_construction_ns;
            std::optional<std::uint64_t> selector_preparation_ns, selector_workspace_creation_ns, witness_query_ns, original_verification_ns;
            std::string status = "failed", error, outcome = "unknown", termination = "unknown";
            bool complete_family = false;
            std::string strategy_version, family_identity;
            std::string strategy_provenance = "[]", selector_provenance = "[]", membership_provenance = "[]";
            std::array<std::optional<verification::TrajectoryReport>, 2> verified_reports;
            std::size_t distinct_witnesses = 0;
            double maximum_residual = 0.0;
            std::size_t residual_count = 0;
            const auto measure_phase = [](auto& destination, auto&& operation) {
                const auto started = Clock::now();
                try {
                    auto value = operation();
                    destination = elapsed_ns(started, Clock::now());
                    return value;
                } catch (...) {
                    destination = elapsed_ns(started, Clock::now());
                    throw;
                }
            };
            const auto measure_phase_void = [](auto& destination, auto&& operation) {
                const auto started = Clock::now();
                try {
                    operation();
                    destination = elapsed_ns(started, Clock::now());
                } catch (...) {
                    destination = elapsed_ns(started, Clock::now());
                    throw;
                }
            };
            try {
                StrategyConfiguration configuration;
                configuration.strategy = {id}; configuration.lp = lp.identity.id; configuration.convex = convex.identity.id;
                configuration.representation = family.representation;
                const StrategyRequest request{resolved, configuration, family, {}, {}};
                total_started = Clock::now();
                const auto prepared = measure_phase(preparation_ns, [&] { return take(strategies.prepare(request, output), "Strategy preparation"); });
                if (prepared.provenance().empty()) throw std::runtime_error("Prepared strategy provenance is empty");
                if (!prepared.provenance().front().actual) throw std::runtime_error("Prepared strategy identity is unavailable");

                auto workspace = measure_phase(workspace_creation_ns, [&] { return prepared.create(); });
                if (!workspace) throw std::runtime_error("Prepared strategy returned no exclusive workspace");

                const auto result = measure_phase(family_construction_ns, [&] { return take(workspace->run(context), "Strategy execution"); });
                termination = result.termination == Termination::completed ? "completed" : "stopped";
                outcome = result.outcome.value == MathematicalOutcome::optimal ? "optimal" : "nonoptimal";
                if (result.termination != Termination::completed || result.outcome.value != MathematicalOutcome::optimal ||
                    !result.family || !std::holds_alternative<CompleteOptimalFamily>(result.family->outcome()) ||
                    result.family->identity().problem != resolved.identity() || result.family->identity().request != family ||
                    result.family->identity().strategy != configuration.strategy)
                    throw std::runtime_error("Strategy did not return the requested registered complete family");
                complete_family = true;
                const SelectorRequest query{*result.family, {2,0,{{1,-1},{-1,1}},31}};
                const auto selector = measure_phase(selector_preparation_ns, [&] { return take(prepare_pipeline(select(selectors, {{synthesis::witness_selector::selector_id}, {}}, query, witness_output)), "Selector preparation"); });
                if (selector.provenance().empty()) throw std::runtime_error("Selector provenance is empty");
                auto selected_workspace = measure_phase(selector_workspace_creation_ns, [&] { return selector.create(); });
                if (!std::get<0>(selected_workspace)) throw std::runtime_error("Selector returned no exclusive workspace");
                const auto selected_result = measure_phase(witness_query_ns, [&] { return take(std::get<0>(selected_workspace)->run(context), "Selector execution"); });
                if (selected_result.termination != Termination::completed || selected_result.batch.returned_count() != 2 ||
                    selected_result.batch.distinct_count() != 2 || selected_result.batch.witnesses.size() != 2 ||
                    selected_result.batch.source_family != result.family->identity())
                    throw std::runtime_error("Selector did not return two distinct histories bound to the source family");
                distinct_witnesses = selected_result.batch.distinct_count();

                measure_phase_void(original_verification_ns, [&] {
                    for (std::size_t index = 0; index < selected_result.batch.witnesses.size(); ++index) {
                        verification::TrajectoryRequest verify;
                        verify.witness = selected_result.batch.witnesses[index];
                        const auto report = verification::verify_trajectory(resolved, verify, context, membership);
                        using verification::CheckStatus;
                        if (report.termination != Termination::completed || report.bindings != CheckStatus::numerical_pass ||
                            report.feasibility != CheckStatus::numerical_pass || report.objective != CheckStatus::numerical_pass ||
                            !report.recomputed_objective)
                            throw std::runtime_error("Original-problem trajectory verification failed");
                        verified_reports[index] = std::move(report);
                    }
                });
                end_to_end_ns = elapsed_ns(total_started, Clock::now());
                status = "passed";
                strategy_version = prepared.provenance().front().actual->version;
                std::ostringstream identity;
                family_identity_json(identity, result.family->identity());
                family_identity = identity.str();
                std::ostringstream strategy_modules, selector_modules, membership_modules;
                provenance_json(strategy_modules, prepared.provenance());
                provenance_json(selector_modules, selector.provenance());
                provenance_json(membership_modules, std::array{membership.provenance()});
                strategy_provenance = strategy_modules.str();
                selector_provenance = selector_modules.str();
                membership_provenance = membership_modules.str();
            } catch (const std::exception& exception) {
                if (total_started != Clock::time_point{} && !end_to_end_ns)
                    end_to_end_ns = elapsed_ns(total_started, Clock::now());
                status = "failed";
                error = exception.what();
            }
            std::vector<std::string> witness_json;
            for (const auto& saved_report : verified_reports) {
                if (!saved_report) continue;
                const auto& report = *saved_report;
                const auto& witness = report.input.witness;
                std::ostringstream item;
                item.imbue(std::locale::classic()); item << std::setprecision(17);
                item << "{\"states\":"; history_json(item, witness.states);
                item << ",\"controls\":"; history_json(item, witness.controls);
                item << ",\"original_objective\":" << witness.original_objective << ",\"recomputed_objective\":" << *report.recomputed_objective
                    << ",\"residual_count\":" << report.residuals.size() << ",\"maximum_absolute_residual\":";
                double local_max = 0.0;
                for (const auto& residual : report.residuals) local_max = std::max(local_max, residual.measure.violation);
                item << local_max << ",\"verification\":{\"verifier\":" << quoted(report.verifier.id.value)
                    << ",\"version\":" << quoted(report.verifier.version) << ",\"bindings\":" << quoted(check_name(report.bindings))
                    << ",\"feasibility\":" << quoted(check_name(report.feasibility)) << ",\"objective\":" << quoted(check_name(report.objective))
                    << ",\"optimality\":\"unsupported\",\"completeness\":\"unsupported\"}}";
                witness_json.push_back(item.str());
                maximum_residual = std::max(maximum_residual, local_max);
                residual_count += report.residuals.size();
            }
            std::ostringstream event;
            event.imbue(std::locale::classic()); event << std::setprecision(17);
            event << "{\"schema\":\"csl.synthesis.paired-ts01-event/1\",\"event\":\"trial\",\"repetition\":" << repetition
                << ",\"warmup\":" << (warmup ? "true" : "false") << ",\"order_position\":" << order_position
                << ",\"strategy\":" << quoted(id) << ",\"strategy_version\":" << quoted(strategy_version)
                << ",\"strategy_provenance\":" << strategy_provenance << ",\"selector_provenance\":" << selector_provenance
                << ",\"membership_provenance\":" << membership_provenance
                << ",\"status\":" << quoted(status) << ",\"termination\":" << quoted(termination)
                << ",\"outcome\":" << quoted(outcome) << ",\"complete_family_verified\":" << (complete_family ? "true" : "false")
                << ",\"assurance\":\"numerical\",\"family_identity\":" << (family_identity.empty() ? "null" : family_identity)
                << ",\"distinct_witnesses\":" << distinct_witnesses << ",\"witnesses\":[";
            for (std::size_t i = 0; i < witness_json.size(); ++i) { if (i) event << ','; event << witness_json[i]; }
            event << "],\"verification_summary\":{\"residual_count\":" << residual_count << ",\"maximum_absolute_residual\":" << maximum_residual
                << ",\"optimality\":\"unsupported\",\"completeness\":\"unsupported\"},\"timings_ns\":{\"preparation\":";
            timing_json(event, preparation_ns, "Strategy preparation did not return"); event << ",\"workspace_creation\":";
            timing_json(event, workspace_creation_ns, "Strategy workspace creation was not reached"); event << ",\"family_construction\":";
            timing_json(event, family_construction_ns, "Strategy run did not return"); event << ",\"selector_preparation\":";
            timing_json(event, selector_preparation_ns, "Selector preparation was not reached"); event << ",\"selector_workspace_creation\":";
            timing_json(event, selector_workspace_creation_ns, "Selector workspace creation was not reached"); event << ",\"witness_query\":";
            timing_json(event, witness_query_ns, "Selector query was not reached"); event << ",\"original_verification\":";
            timing_json(event, original_verification_ns, "Original-data verification was not reached");
            event << ",\"end_to_end_strategy\":";
            timing_json(event, end_to_end_ns, "Strategy preparation was not reached"); event << '}';
            if (!error.empty()) event << ",\"error\":" << quoted(error);
            event << "}\n";
            emit(event.str());
            return status == "passed";
        };

        bool all_passed = true;
        for (std::size_t repetition = 0; repetition <= 7; ++repetition) {
            const bool warmup = repetition == 0;
            const std::size_t order_position = repetition == 0 ? 0 : (repetition - 1) % 2;
            const char* first = order_position == 0 ? "csl.synthesis.reach-back" : "csl.synthesis.strategy-b";
            const char* second = order_position == 0 ? "csl.synthesis.strategy-b" : "csl.synthesis.reach-back";
            all_passed = run_measured(first, repetition, warmup, 0) && all_passed;
            all_passed = run_measured(second, repetition, warmup, 1) && all_passed;
        }
        if (event_file && !event_file.flush()) { std::cerr << "Output rejected: cannot flush events file\n"; return 2; }
        if (!all_passed) return 1;
        return 0;
    }

    std::ostringstream json;
    json.imbue(std::locale::classic()); json << std::setprecision(17);
    json << "{\"schema\":\"csl.example.synthesis-comparison/1\",\"scope\":\"exact T-S01 teaching profile; functional comparison, no performance claim\","
        << "\"problem\":" << quoted(resolved.identity().value) << ",\"source_sha256\":" << quoted(problem::hex(scenario.source()->content.digest()))
        << ",\"resource_policy\":";
    resource_policy_json(json, *context.resources);
    json
        << ",\"family_payload_export\":\"unavailable: live T-S01 completeness support is not portable in csl.run-statistics/4; this summary cannot reconstruct a family\",\"results\":[";
    bool comma = false;
    for (const auto* id : {"csl.synthesis.reach-back", "csl.synthesis.strategy-b"}) {
        StrategyConfiguration configuration;
        configuration.strategy = {id}; configuration.lp = lp.identity.id; configuration.convex = convex.identity.id;
        configuration.representation = family.representation;
        const StrategyRequest request{resolved, configuration, family, {}, {}};
        const auto prepared = take(strategies.prepare(request, output), "Strategy preparation");
        auto workspace = prepared.create();
        const auto result = take(workspace->run(context), "Strategy execution");
        if (result.termination != Termination::completed || result.outcome.value != MathematicalOutcome::optimal ||
            !result.family || !std::holds_alternative<CompleteOptimalFamily>(result.family->outcome()) ||
            result.family->identity().problem != resolved.identity() || result.family->identity().request != family ||
            result.family->identity().strategy != configuration.strategy)
            throw std::runtime_error("Strategy did not return the requested complete registered family");
        const SelectorRequest query{*result.family, {2,0,{{1,-1},{-1,1}},31}};
        const auto selector = take(prepare_pipeline(select(selectors, {{synthesis::witness_selector::selector_id}, {}}, query, witness_output)), "Selector preparation");
        auto selected_workspace = selector.create();
        const auto selected_result = take(std::get<0>(selected_workspace)->run(context), "Selector execution");
        if (selected_result.termination != Termination::completed || selected_result.batch.returned_count() != 2 ||
            selected_result.batch.distinct_count() != 2 || selected_result.batch.source_family != result.family->identity())
            throw std::runtime_error("Selector did not return two distinct histories bound to the source family");
        if (comma) json << ',';
        comma = true;
        json << "{\"strategy\":" << quoted(id) << ",\"problem\":" << quoted(resolved.identity().value)
            << ",\"termination\":\"completed\",\"outcome\":\"optimal\",\"family_source\":";
        family_identity_json(json, *selected_result.batch.source_family);
        json << ",\"strategy_provenance\":"; provenance_json(json, prepared.provenance());
        json << ",\"selector_provenance\":"; provenance_json(json, selector.provenance());
        json << ",\"membership_provenance\":"; provenance_json(json, std::array{membership.provenance()});
        json << ",\"selection\":{\"count\":" << query.selection.count << ",\"distinctness_tolerance\":" << query.selection.distinctness_tolerance
            << ",\"seed\":" << *query.selection.seed << ",\"directions\":";
        history_json(json, query.selection.directions);
        json << "},\"distinct_witnesses\":" << selected_result.batch.distinct_count() << ",\"witnesses\":[";
        for (std::size_t i = 0; i < selected_result.batch.witnesses.size(); ++i) {
            const auto& witness = selected_result.batch.witnesses[i];
            verification::TrajectoryRequest verify;
            verify.witness = witness;
            // Verify original-model feasibility/objective independently of family claims.
            const auto report = verification::verify_trajectory(resolved, verify, context, membership);
            using verification::CheckStatus;
            if (report.termination != Termination::completed || report.bindings != CheckStatus::numerical_pass ||
                report.feasibility != CheckStatus::numerical_pass || report.objective != CheckStatus::numerical_pass || !report.recomputed_objective)
                throw std::runtime_error("Original-problem trajectory verification failed");
            if (i) json << ',';
            json << "{\"states\":"; history_json(json, witness.states);
            json << ",\"controls\":"; history_json(json, witness.controls);
            json << ",\"original_objective\":" << witness.original_objective << ",\"recomputed_objective\":" << *report.recomputed_objective
                << ",\"verification\":{\"scope\":\"witness-only original-problem numerical checks\",\"verifier\":" << quoted(report.verifier.id.value)
                << ",\"version\":" << quoted(report.verifier.version) << ",\"bindings\":" << quoted(check_name(report.bindings))
                << ",\"feasibility\":" << quoted(check_name(report.feasibility)) << ",\"objective\":" << quoted(check_name(report.objective))
                << ",\"optimality\":" << quoted(check_name(report.optimality)) << ",\"completeness\":" << quoted(check_name(report.completeness)) << "}}";
        }
        json << "]}";
    }
    json << "]}\n";
    if (argc == 3) {
        std::ofstream file(argv[2], std::ios::binary | std::ios::trunc);
        if (!file || !(file << json.str()) || !(file.flush())) { std::cerr << "Output rejected: cannot write results file\n"; return 2; }
    }
    std::cout << json.str();
} catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
