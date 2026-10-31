#include <csl/adapters/convex/highs.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <csl/adapters/polyhedral/qhull.hpp>
#include <csl/geometry/affine_sum.hpp>
#include <csl/input/scenario_loader.hpp>
#include <csl/synthesis/strategy_a/strategy.hpp>
#include <csl/synthesis/strategy_b/direct_joint.hpp>
#include <csl/registry/registry.hpp>

#include <chrono>
#include <iomanip>
#include <iostream>
#include <limits>
#include <locale>
#include <memory>
#include <stdexcept>
#include <string>
#include <string_view>
#include <type_traits>
#include <variant>

namespace {
using namespace csl;
using namespace csl::registry;

template<class T, class... Errors>
T take(std::variant<T, Errors...> value, std::string_view stage) {
    if (auto* result = std::get_if<T>(&value)) return std::move(*result);
    throw std::runtime_error(std::string(stage) + " was rejected");
}

template<class Port>
PreparedProvider<Port> selected(Registration<Port> registration, std::string representation) {
    Registry<Port> registry;
    const Method method{registration.identity.id, {}};
    if (registry.add(std::move(registration))) throw std::runtime_error("provider registration failed");
    Requirements requirements;
    requirements.output.representation = {std::move(representation)};
    if constexpr (std::is_same_v<Port, GeometryPort> || std::is_same_v<Port, ConversionPort>)
        requirements.output.relation = SetRelation::equivalent;
    return take(prepare_provider(select_provider(registry, method, requirements)), "provider selection");
}

std::string quoted(std::string_view value) {
    std::string result{"\""};
    for (const char character : value) {
        if (character == '\\' || character == '"') result.push_back('\\');
        if (character == '\n') { result += "\\n"; continue; }
        if (character == '\r') { result += "\\r"; continue; }
        result.push_back(character);
    }
    result.push_back('"');
    return result;
}

const char* termination_name(Termination value) {
    switch (value) {
    case Termination::completed: return "completed";
    case Termination::operation_rejected: return "operation_rejected";
    case Termination::contract_rejected: return "contract_rejected";
    case Termination::cancelled: return "cancelled";
    case Termination::deadline_expired: return "deadline_expired";
    case Termination::resource_limit: return "resource_limit";
    case Termination::numerical_failure: return "numerical_failure";
    }
    return "unknown";
}

const char* outcome_name(MathematicalOutcome value) {
    switch (value) {
    case MathematicalOutcome::optimal: return "optimal";
    case MathematicalOutcome::infeasible: return "infeasible";
    case MathematicalOutcome::unbounded: return "unbounded";
    case MathematicalOutcome::infimum_not_attained: return "infimum_not_attained";
    case MathematicalOutcome::undetermined: return "undetermined";
    }
    return "unknown";
}

void vector_json(std::ostream& out, std::span<const double> values) {
    out << '[';
    for (std::size_t index = 0; index < values.size(); ++index) {
        if (index) out << ',';
        out << values[index];
    }
    out << ']';
}

void matrix_json(std::ostream& out, const numeric::MatrixView& matrix) {
    out << '[';
    for (std::size_t row = 0; row < matrix.rows(); ++row) {
        if (row) out << ',';
        out << '[';
        for (std::size_t column = 0; column < matrix.cols(); ++column) {
            if (column) out << ',';
            out << matrix(row, column);
        }
        out << ']';
    }
    out << ']';
}

void h_relation_json(std::ostream& out, const sets::SetData& relation) {
    const auto metadata = relation.metadata();
    const auto representation = relation.representation();
    const auto* h = std::get_if<sets::HRepresentation>(&representation);
    if (!h) {
        out << "null";
        return;
    }
    out << "{\"id\":" << quoted(metadata->id.value) << ",\"dimension\":"
        << metadata->set.dimension << ",\"labels\":[";
    for (std::size_t index = 0; index < metadata->coordinate_labels.size(); ++index) {
        if (index) out << ',';
        out << quoted(metadata->coordinate_labels[index]);
    }
    out << "],\"inequalities\":";
    matrix_json(out, h->inequalities);
    out << ",\"upper_bounds\":";
    vector_json(out, h->upper_bounds.values());
    out << ",\"equalities\":";
    matrix_json(out, h->equalities);
    out << ",\"equality_values\":";
    vector_json(out, h->equality_values.values());
    out << '}';
}

void witness_json(std::ostream& out, const Witness& witness) {
    out << "{\"states\":[";
    for (std::size_t index = 0; index < witness.states.size(); ++index) {
        if (index) out << ',';
        vector_json(out, witness.states[index]);
    }
    out << "],\"controls\":[";
    for (std::size_t index = 0; index < witness.controls.size(); ++index) {
        if (index) out << ',';
        vector_json(out, witness.controls[index]);
    }
    out << "],\"original_objective\":" << witness.original_objective << '}';
}

void bound_json(std::ostream& out, const std::optional<ObjectiveBound>& bound) {
    if (bound) out << bound->value;
    else out << "null";
}
}

int main(int argc, char** argv) try {
    using namespace csl;
    if (argc != 3) {
        std::cerr << "usage: csl_review05_dimension_ladder <scenario.json> <csl.synthesis.reach-back|csl.synthesis.strategy-b>\n";
        return 2;
    }
    const std::string_view strategy_id = argv[2];
    if (strategy_id != "csl.synthesis.reach-back" && strategy_id != "csl.synthesis.strategy-b")
        throw std::invalid_argument("unrecognized strategy ID");

    const auto loaded = input::load_scenario_file(argv[1]);
    if (const auto* error = std::get_if<input::InputFailure>(&loaded))
        throw std::runtime_error("scenario rejected at " + error->path + "; expected " + error->expected);
    if (const auto* error = std::get_if<input::UnsupportedInput>(&loaded))
        throw std::runtime_error("scenario unsupported at " + error->path + "; expected " + error->expected);
    if (!std::holds_alternative<input::LoadedScenario>(loaded))
        throw std::runtime_error("scenario is not executable");
    const auto& scenario = std::get<input::LoadedScenario>(loaded);
    const auto& resolved = scenario.problem();
    const auto horizon = resolved.model().horizon();
    const auto dimensions = resolved.model().dimensions();
    if (dimensions.state != dimensions.control || dimensions.state < 1 || dimensions.state > 2 ||
        dimensions.external != 0 || (horizon != 2 && horizon != 4))
        throw std::runtime_error("only the pinned 1D/2D, T=2/4 vector fixtures are admitted");

    auto lp = take(adapters::lp::make_highs_registration(), "LP registration");
    auto convex = take(adapters::convex::make_highs_registration(), "convex registration");
    auto converter = take(adapters::polyhedral::make_qhull_registration(lp), "conversion registration");
    auto projection = geometry::polyhedral::make_projection_registration();
    auto affine = geometry::make_affine_sum_registration({
        selected(geometry::make_lp_hull_reducer_registration(), ""),
        selected(lp, "csl.program-result.v1"), selected(converter, "csl.polyhedron.v")});
    Registry<GeometryPort> projections, affines;
    Registry<ConversionPort> conversions;
    Registry<LPPort> lps;
    Registry<ConvexPort> convexes;
    const Method pm{projection.identity.id, {}}, am{affine.identity.id, {}}, cm{converter.identity.id, {}},
        lm{lp.identity.id, {}}, qm{convex.identity.id, {}};
    if (projections.add(projection) || affines.add(affine) || conversions.add(converter) ||
        lps.add(lp) || convexes.add(convex)) throw std::runtime_error("provider registration failed");

    Requirements h, v, program;
    h.output.representation = {"csl.polyhedron.h"}; h.output.relation = SetRelation::equivalent;
    v.output.representation = {"csl.polyhedron.v"}; v.output.relation = SetRelation::equivalent;
    program.output.representation = {"csl.program-result.v1"};
    auto providers = take(check_providers(select_provider(projections, pm, h), select_provider(affines, am, v),
        select_provider(conversions, cm, h), select_provider(lps, lm, program), select_provider(convexes, qm, program)),
        "Strategy A providers");

    StrategyRegistry strategies;
    if (strategies.add(synthesis::strategy_a::make_registration(std::move(providers))) ||
        strategies.add(synthesis::strategy_b::make_registration(lps, convexes)))
        throw std::runtime_error("strategy registration failed");

    FamilyRequest family;
    family.profile = "nominal_open_loop";
    family.objective = resolved.identity();
    family.target = FamilyTarget::candidate_relaxation;
    family.assurance = Assurance::numerical;
    family.representation = {"csl.polyhedron.h"};
    StrategyConfiguration configuration;
    configuration.strategy = {std::string(strategy_id)};
    configuration.lp = lp.identity.id;
    configuration.convex = convex.identity.id;
    configuration.representation = family.representation;
    const StrategyRequest request{resolved, configuration, family, "1", {}};
    Requirements requested_output;
    requested_output.output.representation = family.representation;
    requested_output.output.family = family.target;
    requested_output.output.completeness = Completeness::unestablished;
    auto prepared = take(strategies.prepare(request, requested_output), "Strategy preparation");
    auto workspace = prepared.create();
    if (!workspace) throw std::runtime_error("Strategy returned no workspace");
    ExecutionContext context;
    context.numerical = family.numerical;
    context.resources = std::make_shared<const ResourcePolicy>(ResourcePolicy{1, 1, 1, {}});
    context.backend_thread_observation = std::make_shared<execution::BackendThreadObservation>();

    const auto started = std::chrono::steady_clock::now();
    const auto outcome = workspace->run(context);
    const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now() - started).count();

    std::cout.imbue(std::locale::classic());
    std::cout << std::setprecision(std::numeric_limits<double>::max_digits10);
    std::cout << "{\"schema\":\"csl.review05.dimension-attempt/1\",\"fixture\":\"DIMENSION-01-vector-integrator\",\"horizon\":" << horizon
        << ",\"problem_id\":" << quoted(resolved.identity().value)
        << ",\"scenario_sha256\":" << quoted(problem::hex(scenario.source()->content.digest()))
        << ",\"strategy\":" << quoted(strategy_id)
        << ",\"strategy_version\":" << quoted(prepared.provenance().front().actual->version)
        << ",\"target\":\"candidate_relaxation\",\"assurance\":\"numerical\",\"representation\":\"csl.polyhedron.h\""
        << ",\"solver_threads_requested\":1,\"observed_backend_threads\":";
    if (const auto observed = context.backend_thread_observation->maximum()) std::cout << *observed;
    else std::cout << "null";
    std::cout << ",\"strategy_run_ns\":" << elapsed;

    if (const auto* unsupported = std::get_if<Unsupported>(&outcome)) {
        std::cout << ",\"termination\":\"unsupported\",\"diagnostics\":[";
        for (std::size_t index = 0; index < unsupported->diagnostics.size(); ++index) {
            if (index) std::cout << ',';
            std::cout << quoted(unsupported->diagnostics[index].explanation);
        }
        std::cout << "],\"candidate_relation\":null,\"incumbents\":[]}\n";
        return 0;
    }
    const auto& result = std::get<SynthesisResult>(outcome);
    std::cout << ",\"termination\":" << quoted(termination_name(result.termination))
        << ",\"outcome\":" << quoted(outcome_name(result.outcome.value)) << ",\"objective_lower\":";
    bound_json(std::cout, result.objective.lower);
    std::cout << ",\"objective_upper\":";
    bound_json(std::cout, result.objective.upper);
    std::cout << ",\"family_variant\":";
    const CandidateFamily* candidate = nullptr;
    if (result.family) {
        candidate = std::get_if<CandidateFamily>(&result.family->outcome());
        std::cout << (candidate ? "\"candidate\"" : "\"non_candidate\"");
    } else std::cout << "null";
    std::cout << ",\"family_registry_verified\":" << (result.family && result.family->registry_verified() ? "true" : "false")
        << ",\"candidate_coordinates\":";
    if (candidate) {
        const auto& coordinates = candidate->relation.coordinates;
        std::cout << "{\"state_dimension\":" << coordinates.dimensions.state
            << ",\"control_dimension\":" << coordinates.dimensions.control
            << ",\"external_dimension\":" << coordinates.dimensions.external
            << ",\"horizon\":" << coordinates.horizon << '}';
    } else std::cout << "null";
    std::cout << ",\"candidate_relation\":";
    const sets::SetData* relation = nullptr;
    if (candidate && candidate->relation.payload) {
        relation = candidate->relation.payload->h_relation_for_recording();
        if (!relation) {
            const auto* reach_back = dynamic_cast<const synthesis::strategy_a::CandidateHistory*>(
                candidate->relation.payload.get());
            if (reach_back) relation = &reach_back->history.relation;
        }
    }
    if (relation) h_relation_json(std::cout, *relation);
    else std::cout << "null";
    std::cout << ",\"incumbents\":[";
    for (std::size_t index = 0; index < result.incumbents.size(); ++index) {
        if (index) std::cout << ',';
        witness_json(std::cout, result.incumbents[index].witness);
    }
    std::cout << "]}\n";
    return 0;
} catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
}
