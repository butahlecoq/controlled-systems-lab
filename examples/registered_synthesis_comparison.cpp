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
#include <array>
#include <iomanip>
#include <iostream>
#include <locale>
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
}

int main(int argc, char** argv) try {
    using namespace csl;
    using namespace csl::registry;
    if (argc < 2 || argc > 3) {
        std::cerr << "Usage: registered_synthesis_comparison <two-stage-integrator.json> [results.json]\n";
        return 2;
    }
    const auto loaded = input::load_scenario_file(argv[1]);
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
    FamilyRequest family;
    family.profile = "ts01_exact_integrator";
    family.objective = resolved.identity();
    family.target = FamilyTarget::exact_optimal_relation;
    family.assurance = Assurance::numerical;
    family.representation = {"csl.polyhedron.h"};
    ExecutionContext context;
    context.numerical = family.numerical;
    context.resources = std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});

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

    std::ostringstream json;
    json.imbue(std::locale::classic()); json << std::setprecision(17);
    json << "{\"schema\":\"csl.example.synthesis-comparison/1\",\"scope\":\"exact T-S01 teaching profile; functional comparison, no performance claim\","
        << "\"problem\":" << quoted(resolved.identity().value) << ",\"source_sha256\":" << quoted(problem::hex(scenario.source()->content.digest()))
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
