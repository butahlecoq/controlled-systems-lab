#include <csl/registry/strategy_catalogue.hpp>

#include <bit>
#include <cstdint>
#include <sstream>

namespace csl::registry {
namespace {

std::string module_value(const ModuleId& module) {
    return module.value.empty() ? "not_used" : module.value;
}

std::vector<std::pair<std::string, std::string>> slots(const StrategyConfiguration& c) {
    return {{"strategy", module_value(c.strategy)}, {"lp", module_value(c.lp)},
        {"convex", module_value(c.convex)}, {"hull", module_value(c.hull)},
        {"geometry", module_value(c.geometry)}, {"converter", module_value(c.converter)},
        {"approximation", module_value(c.approximation)}, {"selector", module_value(c.selector)},
        {"representation", c.representation.value.empty() ? "not_used" : c.representation.value}};
}

bool active(const std::optional<std::vector<StrategyRegistration::ConfigurationSlot>>& slots,
        StrategyRegistration::ConfigurationSlot slot) {
    return !slots || std::find(slots->begin(),slots->end(),slot) != slots->end();
}

StrategyConfiguration route_configuration(const StrategyConfiguration& requested,
        const Identity& strategy,
        const std::optional<std::vector<StrategyRegistration::ConfigurationSlot>>& active_slots) {
    auto result = requested;
    result.strategy = strategy.id;
    using Slot = StrategyRegistration::ConfigurationSlot;
    if (!active(active_slots,Slot::lp)) result.lp = {};
    if (!active(active_slots,Slot::convex)) result.convex = {};
    if (!active(active_slots,Slot::hull)) result.hull = {};
    if (!active(active_slots,Slot::geometry)) result.geometry = {};
    if (!active(active_slots,Slot::converter)) result.converter = {};
    if (!active(active_slots,Slot::approximation)) result.approximation = {};
    if (!active(active_slots,Slot::selector)) result.selector = {};
    if (!active(active_slots,Slot::representation)) result.representation = {};
    return result;
}

std::string_view slot_name(StrategyRegistration::ConfigurationSlot slot) {
    using Slot = StrategyRegistration::ConfigurationSlot;
    switch (slot) {
    case Slot::lp: return "lp";
    case Slot::convex: return "convex";
    case Slot::hull: return "hull";
    case Slot::geometry: return "geometry";
    case Slot::converter: return "converter";
    case Slot::approximation: return "approximation";
    case Slot::selector: return "selector";
    case Slot::representation: return "representation";
    }
    return "invalid";
}

bool same_configuration(const StrategyConfiguration& a, const StrategyConfiguration& b) {
    return a.strategy == b.strategy && a.lp == b.lp && a.convex == b.convex &&
        a.hull == b.hull && a.geometry == b.geometry && a.converter == b.converter &&
        a.approximation == b.approximation && a.selector == b.selector &&
        a.representation == b.representation;
}

void append(std::ostringstream& output, std::string_view value) {
    output << value.size() << ':' << value;
}

std::string candidate_id(const StrategyCandidateGraph& graph) {
    std::ostringstream key;
    append(key, graph.request_key);
    for (const auto& provider : graph.resolved_providers) {
        append(key, provider.port);
        append(key, provider.requested.id.value);
        append(key, provider.requested.version.value_or("version-unpinned"));
        append(key, provider.actual ? provider.actual->id.value : "unresolved");
        append(key, provider.actual ? provider.actual->version : "unresolved");
    }
    if (graph.expected_lineage) {
        append(key,"expected-lineage");
        for (const auto& step : *graph.expected_lineage) {
            append(key, step.request.value);
            append(key, step.input.value);
            append(key, step.output.value);
            append(key, step.module.value);
            append(key, step.version);
        }
    } else {
        append(key,"no-expected-lineage");
    }
    return "controller-graph-v1/" + key.str();
}

bool same_provider_path(const std::vector<Provenance>& left,
        const std::vector<Provenance>& right) {
    if (left.size() != right.size()) return false;
    for (std::size_t i = 0; i < left.size(); ++i) {
        if (left[i].port != right[i].port || left[i].requested.id != right[i].requested.id ||
            left[i].requested.version != right[i].requested.version ||
            left[i].actual.has_value() != right[i].actual.has_value()) return false;
        if (left[i].actual && (left[i].actual->id != right[i].actual->id ||
            left[i].actual->version != right[i].actual->version)) return false;
    }
    return true;
}

Requirements family_requirements(const StrategyRequest& request) {
    Requirements requirements;
    requirements.output.representation = request.family.representation;
    requirements.output.assurance = request.family.assurance;
    return requirements;
}

StrategyCandidateGraph make_graph(const StrategyRequest& request, const Identity& strategy,
        const std::optional<std::vector<StrategyRegistration::ConfigurationSlot>>& active_slots) {
    StrategyCandidateGraph graph;
    graph.strategy = strategy;
    graph.active_configuration_slots = active_slots;
    graph.problem = request.problem.identity();
    graph.family = request.family;
    graph.configuration = route_configuration(request.configuration, strategy, active_slots);
    graph.module_slots = slots(graph.configuration);
    graph.lineage = request.lineage;

    std::ostringstream key;
    for (const auto& [slot, module] : graph.module_slots) {
        append(key, slot);
        append(key, module);
    }
    append(key, graph.problem.value);
    append(key, graph.family.profile);
    append(key, graph.family.objective.value);
    append(key, std::to_string(static_cast<int>(graph.family.target)));
    append(key, std::to_string(static_cast<int>(graph.family.assurance)));
    append(key, graph.family.representation.value);
    append(key, std::to_string(std::bit_cast<std::uint64_t>(graph.family.numerical.absolute_tolerance)));
    append(key, std::to_string(std::bit_cast<std::uint64_t>(graph.family.numerical.relative_tolerance)));
    append(key, strategy.id.value);
    append(key, strategy.version);
    if (active_slots) {
        append(key, "declared-active-slots");
        for (const auto slot : *active_slots) append(key, slot_name(slot));
    } else {
        append(key, "legacy-unspecified-active-slots");
    }
    if (graph.family.materialization_limit)
        append(key, std::to_string(*graph.family.materialization_limit));
    else
        append(key, "no-materialization-limit");
    for (const auto& step : graph.lineage) {
        append(key, step.request.value);
        append(key, step.input.value);
        append(key, step.output.value);
        append(key, step.module.value);
        append(key, step.version);
    }
    graph.request_key = key.str();
    graph.id = candidate_id(graph);
    return graph;
}

bool matches(const StrategyRegistry& strategies, const StrategyCandidateGraph& graph,
        const StrategyRequest& request) {
    if (!request.configuration.strategy.value.empty() &&
        request.configuration.strategy != graph.strategy.id)
        return false;
    if (!request.strategy_version.empty() && request.strategy_version != graph.strategy.version)
        return false;
    const auto active_slots = strategies.active_configuration_slots(graph.strategy.id);
    const auto expected = make_graph(request, graph.strategy, active_slots);
    return graph.request_key == expected.request_key && graph.strategy.id == expected.strategy.id &&
        graph.strategy.version == expected.strategy.version &&
        graph.problem == expected.problem && graph.family == expected.family &&
        graph.active_configuration_slots == expected.active_configuration_slots &&
        same_configuration(graph.configuration, expected.configuration) &&
        graph.module_slots == expected.module_slots && graph.lineage == expected.lineage;
}

} // namespace

std::vector<StrategyCandidateRow> enumerate_strategy_candidates(
        const StrategyRegistry& strategies, const StrategyRequest& request) {
    return enumerate_strategy_candidates(strategies,request,family_requirements(request));
}

std::vector<StrategyCandidateRow> enumerate_strategy_candidates(
        const StrategyRegistry& strategies, const StrategyRequest& request,
        const Requirements& requirements) {
    std::vector<StrategyCandidateRow> rows;
    const auto identities = strategies.identities();
    rows.reserve(identities.size());
    for (const auto& identity : identities) {
        auto graph = make_graph(request, identity,
            strategies.active_configuration_slots(identity.id));
        auto selected = request;
        selected.configuration = graph.configuration;
        selected.strategy_version = identity.version;
        auto preparation = strategies.prepare(selected, requirements, identity.version);
        if (auto* rejection = std::get_if<Rejection>(&preparation)) {
            rows.push_back({std::move(graph), CandidateStatus::incompatible,
                {rejection->provenance}, std::nullopt, std::move(*rejection)});
            continue;
        }
        auto prepared = std::get<PreparedStrategy>(std::move(preparation));
        auto provenance = prepared.provenance();
        const auto expected = prepared.expected_synthesis_identity();
        const bool exact = expected.problem == graph.problem &&
            expected.request == graph.family && expected.strategy == identity.id &&
            expected.strategy_version == identity.version && !provenance.empty() &&
            provenance.front().actual && provenance.front().actual->id == identity.id &&
            provenance.front().actual->version == identity.version;
        if (!exact) {
            Rejection rejection{provenance.empty() ? Provenance{} : provenance.front(),
                {{DiagnosticCode::evidence_mismatch, "candidate.provider_identity",
                    "Prepared strategy provenance does not match the pinned graph identity"}}};
            rows.push_back({std::move(graph), CandidateStatus::incompatible,
                std::move(provenance), std::nullopt, std::move(rejection)});
            continue;
        }
        graph.resolved_providers = provenance;
        graph.expected_lineage = expected.lineage;
        graph.id = candidate_id(graph);
        rows.push_back({std::move(graph), CandidateStatus::admitted,
            std::move(provenance), std::move(prepared), std::nullopt});
    }
    return rows;
}

std::variant<PreparedStrategyCandidate, Rejection> prepare_strategy_candidate(
        const StrategyRegistry& strategies, const StrategyCandidateGraph& graph,
        const StrategyRequest& request) {
    return prepare_strategy_candidate(strategies,graph,request,family_requirements(request));
}

std::variant<PreparedStrategyCandidate, Rejection> prepare_strategy_candidate(
        const StrategyRegistry& strategies, const StrategyCandidateGraph& graph,
        const StrategyRequest& request, const Requirements& requirements) {
    if (!matches(strategies, graph, request)) {
        return Rejection{{StrategyPort::name,
                {graph.strategy.id, graph.strategy.version}, {}},
            {{DiagnosticCode::unsupported, "candidate.graph",
                "Request problem, family, or selected module slots differ from the canonical candidate"}}};
    }
    auto selected = request;
    selected.configuration = graph.configuration;
    selected.strategy_version = graph.strategy.version;
    auto preparation = strategies.prepare(selected, requirements, graph.strategy.version);
    if (auto* rejection = std::get_if<Rejection>(&preparation)) return *rejection;
    auto prepared = std::get<PreparedStrategy>(std::move(preparation));
    auto provenance = prepared.provenance();
    const auto expected = prepared.expected_synthesis_identity();
    if (expected.problem != graph.problem || expected.request != graph.family ||
        expected.strategy != graph.strategy.id || expected.strategy_version != graph.strategy.version ||
        expected.lineage != graph.expected_lineage ||
        !same_provider_path(graph.resolved_providers, provenance) ||
        graph.id != candidate_id(graph) ||
        provenance.empty() || !provenance.front().actual ||
        provenance.front().actual->id != graph.strategy.id ||
        provenance.front().actual->version != graph.strategy.version) {
        return Rejection{provenance.empty() ? Provenance{} : provenance.front(),
            {{DiagnosticCode::evidence_mismatch, "candidate.provider_identity",
                "Prepared strategy provenance does not match the pinned graph identity"}}};
    }
    return PreparedStrategyCandidate{graph, std::move(prepared), std::move(provenance)};
}

} // namespace csl::registry
