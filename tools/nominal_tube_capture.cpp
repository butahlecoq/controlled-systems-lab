#include <csl/adapters/lp/highs.hpp>
#include <csl/adapters/polyhedral/qhull.hpp>
#include <csl/geometry/affine_sum.hpp>
#include <csl/geometry/polyhedral_intersection.hpp>
#include <csl/reachability/nominal_tube.hpp>

#include <nlohmann/json.hpp>

#include <chrono>
#include <cmath>
#include <fstream>
#include <iostream>
#include <limits>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <utility>
#include <vector>

namespace {
using Json = nlohmann::json;
using namespace csl;
using namespace csl::reachability;

template<class T, class... E> T take(std::variant<T, E...> value, const char* context) {
    if (!std::holds_alternative<T>(value)) throw std::runtime_error(context);
    return std::get<T>(std::move(value));
}

template<class Port> registry::PreparedProvider<Port> selected(
        registry::Registration<Port> registration, std::string representation) {
    registry::Registry<Port> candidates;
    const registry::Method method{registration.identity.id, registration.identity.version};
    if (candidates.add(std::move(registration))) throw std::runtime_error("provider registration failed");
    registry::Requirements requirements;
    requirements.output.representation = {std::move(representation)};
    if constexpr (std::is_same_v<Port, registry::GeometryPort> ||
                  std::is_same_v<Port, registry::ConversionPort>)
        requirements.output.relation = SetRelation::equivalent;
    return take(registry::prepare_provider(
        registry::select_provider(candidates, method, requirements)), "provider selection failed");
}

Matrix matrix(const Json& rows) {
    if (!rows.is_array()) throw std::runtime_error("matrix must be a nested numeric array");
    const auto height = rows.size();
    const auto width = height == 0 ? std::size_t{0} : rows.at(0).size();
    Matrix result{height, width, {}};
    result.values.reserve(height * width);
    for (const auto& row : rows) {
        if (!row.is_array() || row.size() != width) throw std::runtime_error("matrix rows have inconsistent widths");
        for (const auto& value : row) {
            const auto number = value.get<double>();
            if (!std::isfinite(number)) throw std::runtime_error("matrix contains a nonfinite coefficient");
            result.values.push_back(number);
        }
    }
    return result;
}

SetHandle box(const std::string& id, const std::vector<std::string>& labels,
        const Json& bounds) {
    const auto dimension = labels.size();
    if (!bounds.is_array() || bounds.size() != dimension)
        throw std::runtime_error("box bounds do not match coordinate labels");
    Matrix rows{2 * dimension, dimension, Vector(2 * dimension * dimension, 0.0)};
    Vector rhs(2 * dimension, 0.0);
    for (std::size_t coordinate = 0; coordinate < dimension; ++coordinate) {
        const auto lower = bounds[coordinate][0].get<double>();
        const auto upper = bounds[coordinate][1].get<double>();
        if (!std::isfinite(lower) || !std::isfinite(upper) || lower > upper)
            throw std::runtime_error("box bounds must be finite ordered physical coordinates");
        rows.values[(2 * coordinate) * dimension + coordinate] = 1.0;
        rhs[2 * coordinate] = upper;
        rows.values[(2 * coordinate + 1) * dimension + coordinate] = -1.0;
        rhs[2 * coordinate + 1] = -lower;
    }
    const auto h = take(sets::make_h({{id}, dimension, labels},
        {take(numeric::snapshot(rows), "could not snapshot box rows"),
         take(numeric::snapshot_vector(rhs), "could not snapshot box bounds"),
         take(numeric::snapshot(Matrix{0, dimension, {}}), "could not snapshot empty equality rows"),
         take(numeric::snapshot_vector(Vector{}), "could not snapshot empty equality bounds")}),
        "could not construct H box");
    return h.as_handle();
}

std::vector<double> vector(const Json& values) {
    if (!values.is_array()) throw std::runtime_error("vector must be a numeric array");
    std::vector<double> result;
    result.reserve(values.size());
    for (const auto& value : values) {
        const auto number = value.get<double>();
        if (!std::isfinite(number)) throw std::runtime_error("vector contains a nonfinite value");
        result.push_back(number);
    }
    return result;
}

std::vector<double> vector_values(std::span<const double> values) {
    return {values.begin(), values.end()};
}

std::string relation(SetRelation relation) {
    switch (relation) {
    case SetRelation::equivalent: return "equivalent";
    case SetRelation::inner: return "inner";
    case SetRelation::outer: return "outer";
    case SetRelation::heuristic: return "heuristic";
    }
    return "unknown";
}

Json set_json(const SetHandle& handle) {
    const auto imported = take(sets::from_handle(handle), "set handle could not be opened");
    const auto metadata = imported.metadata();
    const auto representation = imported.representation();
    const auto* h = std::get_if<sets::HRepresentation>(&representation);
    if (!h) throw std::runtime_error("tube capture requires an H representation at every stored stage");
    Json inequalities = Json::array();
    for (std::size_t row = 0; row < h->inequalities.rows(); ++row) {
        Json values = Json::array();
        for (std::size_t column = 0; column < h->inequalities.cols(); ++column)
            values.push_back(h->inequalities(row, column));
        inequalities.push_back(std::move(values));
    }
    Json equalities = Json::array();
    for (std::size_t row = 0; row < h->equalities.rows(); ++row) {
        Json values = Json::array();
        for (std::size_t column = 0; column < h->equalities.cols(); ++column)
            values.push_back(h->equalities(row, column));
        equalities.push_back(std::move(values));
    }
    return {
        {"set_id", metadata->id.value},
        {"dimension", metadata->set.dimension},
        {"coordinate_labels", metadata->coordinate_labels},
        {"representation", "csl.polyhedron.h"},
        {"inequalities", {{"A", std::move(inequalities)}, {"b", vector_values(h->upper_bounds.values())}}},
        {"equalities", {{"E", std::move(equalities)}, {"f", vector_values(h->equality_values.values())}}},
    };
}

Json identity_json(const GeometryRequestIdentity& identity) {
    return {{"problem_id", identity.problem.value}, {"request_id", identity.request.value},
        {"ideal_output_id", identity.ideal_output.value}};
}

Json reference_json(const GeometryReference& reference) {
    Json inputs = Json::array();
    for (const auto& input : reference.inputs) inputs.push_back(input.value);
    return {{"identity", identity_json(reference.identity)}, {"inputs", std::move(inputs)}};
}

Json evidence_json(const GeometryEvidence& evidence) {
    return {{"reference", reference_json(evidence.reference)},
        {"scope", evidence.scope == GeometryClaimScope::set_relation ? "set_relation" :
            evidence.scope == GeometryClaimScope::support_value ? "support_value" : "containment"},
        {"support", std::holds_alternative<Unestablished>(evidence.support) ? "unestablished" : "supported"},
        {"assumptions", evidence.assumptions},
        {"error_bound", evidence.error_bound ? Json{{"metric", evidence.error_bound->metric.value},
            {"bound", evidence.error_bound->bound}, {"units", evidence.error_bound->units}} : Json(nullptr)}};
}

Json operation_json(const OperationResult& operation) {
    return {{"output", set_json(operation.output)}, {"relation", relation(operation.relation)},
        {"evidence", evidence_json(operation.evidence)}};
}

Json provider_json(const RequestProvenance& provider) {
    return {{"request_id", provider.request.value}, {"port", provider.port},
        {"requested_provider", {{"id", provider.requested_module.value}, {"version", provider.requested_version.value_or("")}}},
        {"actual_provider", provider.actual_module ? Json{{"id", provider.actual_module->value},
            {"version", provider.actual_version.value_or("")}} : Json(nullptr)}};
}

Json stage_json(const NominalTubeStage& stage) {
    Json requests = Json::array(), providers = Json::array(), lineage = Json::array(), source_sets = Json::array();
    for (const auto& request : stage.requests) requests.push_back(reference_json(request));
    for (const auto& provider : stage.providers) providers.push_back(provider_json(provider));
    for (const auto& evidence : stage.lineage) lineage.push_back(evidence_json(evidence));
    for (const auto& source : stage.source_sets) source_sets.push_back(source.value);
    return {{"stage", stage.stage.value}, {"state_coordinates", stage.coordinates},
        {"state_coordinate_labels", stage.coordinate_labels},
        {"forward", stage.forward ? operation_json(*stage.forward) : Json(nullptr)},
        {"backward", stage.backward ? operation_json(*stage.backward) : Json(nullptr)},
        {"intersection", stage.intersection ? operation_json(*stage.intersection) : Json(nullptr)},
        {"source_set_ids", std::move(source_sets)}, {"requests", std::move(requests)},
        {"providers", std::move(providers)}, {"lineage", std::move(lineage)}};
}

Json stages_json(const NominalTube& tube) {
    Json result = Json::array();
    for (const auto& stage : tube.stages) result.push_back(stage_json(stage));
    return result;
}

Json provider_list_json(const std::vector<RequestProvenance>& providers) {
    Json result = Json::array();
    for (const auto& provider : providers) result.push_back(provider_json(provider));
    return result;
}

Json diagnostic_json(const Diagnostics& diagnostics) {
    Json result = Json::array();
    for (const auto& diagnostic : diagnostics)
        result.push_back({{"code", static_cast<int>(diagnostic.code)}, {"field", diagnostic.field},
            {"explanation", diagnostic.explanation}});
    return result;
}

Json failure_json(const NominalTubeFailure& failure) {
    Json cause;
    if (const auto* rejected = std::get_if<Unsupported>(&failure.cause))
        cause = {{"kind", "unsupported"}, {"diagnostics", diagnostic_json(rejected->diagnostics)}};
    else {
        const auto& stopped = std::get<OperationStopped>(failure.cause);
        cause = {{"kind", "stopped"}, {"reason", static_cast<int>(stopped.reason)},
            {"diagnostics", stopped.diagnostics}};
    }
    Json active = failure.active_request ? identity_json(*failure.active_request) : Json(nullptr);
    Json partial = nullptr;
    if (failure.forward_partial) {
        partial = {{"stage", failure.forward_partial->stage.value},
            {"marginal", operation_json(failure.forward_partial->marginal)},
            {"source_coordinates", failure.forward_partial->source_coordinates},
            {"projection_source", set_json(failure.forward_partial->projection_source)}};
    }
    Json forward_lineage = Json::array();
    for (const auto& item : failure.forward_lineage) forward_lineage.push_back(evidence_json(item));
    Json coordinates = Json::array();
    for (const auto& item : failure.coordinate_lineage)
        coordinates.push_back({{"coordinates", item.coordinates},
            {"source", item.source.id.value}, {"target", item.target.id.value}});
    return {{"stage", failure.stage.value}, {"phase", static_cast<int>(failure.phase)},
        {"active_request", std::move(active)}, {"cause", std::move(cause)},
        {"forward_partial", std::move(partial)}, {"forward_providers", provider_list_json(failure.forward_providers)},
        {"forward_lineage", std::move(forward_lineage)}, {"coordinate_lineage", std::move(coordinates)}};
}

Problem build_problem(const Json& request) {
    const auto& state_coordinates = request.at("state_coordinates");
    const auto& control_coordinates = request.at("control_coordinates");
    const auto& physical = request.at("physical_coefficients");
    const auto n = state_coordinates.size(), m = control_coordinates.size();
    const auto horizon = request.at("time").at("intervals").get<std::size_t>();
    if (n == 0 || m == 0 || physical.size() != horizon ||
        request.at("time").at("grid").size() != horizon + 1)
        throw std::runtime_error("source request dimensions or original time grid are incomplete");

    std::vector<std::string> state_labels, control_labels;
    Vector initial = vector(request.at("initial_state"));
    if (initial.size() != n) throw std::runtime_error("initial state width differs from source state coordinates");
    for (const auto& coordinate : state_coordinates) state_labels.push_back(coordinate.at("name").get<std::string>());
    for (const auto& coordinate : control_coordinates) control_labels.push_back(coordinate.at("name").get<std::string>());

    std::vector<LinearStage> dynamics;
    dynamics.reserve(horizon);
    for (const auto& stage : physical) {
        auto a = matrix(stage.at("A"));
        auto b = matrix(stage.at("B"));
        auto c = vector(stage.at("c"));
        if (a.rows != n || a.cols != n || b.rows != n || b.cols != m || c.size() != n)
            throw std::runtime_error("physical affine stage has a shape different from the source model");
        dynamics.push_back({std::move(a), std::move(b), Matrix{n, 0, {}}, std::move(c)});
    }
    auto model = std::make_shared<const SystemModel>(SystemModel{{{n, m, 0}, TimeDomain::discrete,
        std::move(dynamics)}, {}});

    std::vector<AdmissibleSet> controls, states;
    controls.reserve(horizon);
    states.reserve(horizon + 1);
    for (std::size_t stage = 0; stage < horizon; ++stage)
        controls.emplace_back(box("continuous-control-" + std::to_string(stage), control_labels,
            request.at("control_constraints")));
    for (std::size_t stage = 0; stage <= horizon; ++stage)
        states.emplace_back(box("physical-state-" + std::to_string(stage), state_labels,
            request.at("state_constraints")));
    const auto& source_cost = request.at("objective_metadata").at("source_objective").at("source_definition");
    const auto target = vector(source_cost.at("terminal_target"));
    const auto scales = vector(source_cost.at("terminal_scale"));
    const auto weights = vector(source_cost.at("terminal_weights"));
    if (target.size() != n || scales.size() != n || weights.size() != n)
        throw std::runtime_error("source terminal cost metadata differs from model state dimensions");
    Matrix q{n, n, Vector(n * n, 0.0)};
    Vector linear(n, 0.0);
    double offset = 0.0;
    for (std::size_t i = 0; i < n; ++i) {
        const auto coefficient = weights[i] / (scales[i] * scales[i]);
        q.values[i * n + i] = 2.0 * coefficient;
        linear[i] = -2.0 * coefficient * target[i];
        offset += coefficient * target[i] * target[i];
    }
    const auto grid = vector(request.at("time").at("grid"));
    if (grid.size() != horizon + 1) throw std::runtime_error("time grid width changed while parsing");
    Problem source{{request.at("source").at("task_id").get<std::string>() + "/full-state-H-tube"},
        std::move(model), grid, KnownInitial{std::move(initial)}, ContinuousDomain{std::move(controls)},
        std::move(states), {}, {}, InformationPattern::nominal_open_loop,
        QuadraticTerminal{std::move(q), std::move(linear), offset}};
    return source;
}

struct Arguments {
    std::string input;
    std::string output;
    std::size_t max_projection_rows{};
    double deadline_seconds{};
};

Arguments arguments(int argc, char** argv) {
    Arguments result;
    for (int i = 1; i < argc; ++i) {
        const std::string name = argv[i];
        if (i + 1 >= argc) throw std::runtime_error("every command-line option requires a value");
        const std::string value = argv[++i];
        if (name == "--input") result.input = value;
        else if (name == "--output") result.output = value;
        else if (name == "--max-projection-rows") result.max_projection_rows = std::stoull(value);
        else if (name == "--deadline-seconds") result.deadline_seconds = std::stod(value);
        else throw std::runtime_error("unknown command-line option: " + name);
    }
    if (result.input.empty() || result.output.empty() || result.max_projection_rows == 0 ||
        !std::isfinite(result.deadline_seconds) || result.deadline_seconds <= 0)
        throw std::runtime_error("require --input, --output, positive --max-projection-rows and --deadline-seconds");
    return result;
}

} // namespace

int main(int argc, char** argv) {
    const auto started = std::chrono::steady_clock::now();
    std::string output_path;
    try {
        const auto options = arguments(argc, argv);
        output_path = options.output;
        std::ifstream input_stream(options.input);
        if (!input_stream) throw std::runtime_error("could not open request JSON");
        const auto input = Json::parse(input_stream);
        if (input.at("schema") != "csl.nominal-h-tube-input/1")
            throw std::runtime_error("unsupported nominal H tube input schema");
        const auto source = build_problem(input);
        const auto resolved = take(problem::resolve(source,
            {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}}),
            "source problem profile could not be resolved");

        auto lp = take(adapters::lp::make_highs_registration(), "HiGHS registration failed");
        auto converter = take(adapters::polyhedral::make_qhull_registration(lp), "Qhull registration failed");
        auto affine = geometry::make_affine_sum_registration({
            selected(geometry::make_lp_hull_reducer_registration(), ""),
            selected(lp, "csl.program-result.v1"),
            selected(converter, "csl.polyhedron.v")}, {{}, {}});
        reachability::ForwardDependencies forward{
            selected(geometry::polyhedral::make_projection_registration(
                {geometry::polyhedral::ProjectionOutput::h, options.max_projection_rows}), "csl.polyhedron.h"),
            selected(std::move(affine), "csl.polyhedron.v"),
            selected(converter, "csl.polyhedron.h")};
        auto intersection = selected(geometry::polyhedral::make_intersection_registration(), "csl.polyhedron.h");

        const auto labels = input.at("state_coordinates").get<std::vector<Json>>();
        std::vector<std::string> state_labels;
        for (const auto& coordinate : labels) state_labels.push_back(coordinate.at("name").get<std::string>());
        const auto terminal = box("physical-terminal-feasibility", state_labels,
            input.at("terminal_feasibility").at("bounds"));
        ExecutionContext context;
        context.deadline = std::chrono::steady_clock::now() +
            std::chrono::duration_cast<std::chrono::steady_clock::duration>(
                std::chrono::duration<double>(options.deadline_seconds));
        const auto outcome = reachability::nominal_tube(resolved, {"source-bound-nominal-tube"}, terminal,
            {std::move(forward), std::move(intersection)}, context);

        Json record{{"schema", "csl.nominal-h-tube-record/1"}, {"input", input},
            {"resource_profile", {{"max_projection_rows", options.max_projection_rows},
                {"deadline_seconds", options.deadline_seconds}}}};
        if (const auto* tube = std::get_if<reachability::NominalTube>(&outcome)) {
            record["completion"] = "complete";
            record["problem_id"] = tube->problem.value;
            record["request_id"] = tube->request.value;
            record["stages"] = stages_json(*tube);
        } else if (const auto* empty = std::get_if<reachability::NominalTubeEmptyForward>(&outcome)) {
            record["completion"] = "forward_empty";
            record["first_empty_stage"] = empty->first_empty_stage.value;
            record["empty_evidence"] = evidence_json(empty->evidence);
            record["problem_id"] = empty->prefix.problem.value;
            record["request_id"] = empty->prefix.request.value;
            record["stages"] = stages_json(empty->prefix);
        } else {
            const auto& failure = std::get<reachability::NominalTubeFailure>(outcome);
            record["completion"] = "stopped_or_rejected";
            record["problem_id"] = failure.prefix.problem.value;
            record["request_id"] = failure.prefix.request.value;
            record["stages"] = stages_json(failure.prefix);
            record["failure"] = failure_json(failure);
        }
        record["elapsed_seconds"] = std::chrono::duration<double>(
            std::chrono::steady_clock::now() - started).count();
        std::ofstream output_stream(options.output);
        if (!output_stream) throw std::runtime_error("could not create output record");
        output_stream << record.dump(2) << '\n';
        return 0;
    } catch (const std::exception& failure) {
        std::cerr << failure.what() << '\n';
        if (!output_path.empty()) {
            std::ofstream output_stream(output_path);
            if (output_stream) output_stream << Json{{"schema", "csl.nominal-h-tube-record/1"},
                {"completion", "request_rejected"}, {"diagnostic", failure.what()}}.dump(2) << '\n';
        }
        return 2;
    }
}
