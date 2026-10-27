#include <csl/adapters/lp/highs.hpp>
#include <csl/adapters/polyhedral/qhull.hpp>
#include <csl/artifacts/stage_projection_batch.hpp>
#include <csl/geometry/affine_sum.hpp>
#include <csl/geometry/polyhedral_projection.hpp>
#include <csl/reachability/nominal_forward.hpp>
#include <nlohmann/json.hpp>

#include <fstream>
#include <iostream>
#include <stdexcept>
#include <type_traits>

namespace {
using namespace csl;
using Json = nlohmann::json;

template<class T, class... E> T take(std::variant<T, E...> value) {
    if (!std::holds_alternative<T>(value)) {
        const auto detail = std::visit([](const auto& error) -> std::string {
            if constexpr (requires { error.explanation; }) return error.explanation;
            else if constexpr (requires { error.diagnostics; }) {
                if constexpr (std::is_same_v<std::decay_t<decltype(error.diagnostics)>, std::string>)
                    return error.diagnostics;
                else {
                    std::string text;
                    for (const auto& diagnostic : error.diagnostics)
                        text += diagnostic.field + ": " + diagnostic.explanation + "; ";
                    return text;
                }
            } else return "provider returned a typed rejection";
        }, value);
        throw std::runtime_error("native route setup or operation failed: " + detail);
    }
    return std::get<T>(std::move(value));
}

template<class Port> registry::PreparedProvider<Port> selected(
        registry::Registration<Port> entry, std::string representation) {
    registry::Registry<Port> registry;
    const registry::Method method{entry.identity.id, entry.identity.version};
    if (registry.add(std::move(entry))) throw std::runtime_error("provider registration failed");
    registry::Requirements requirements;
    requirements.output.representation = {std::move(representation)};
    if constexpr (std::is_same_v<Port, registry::GeometryPort> ||
            std::is_same_v<Port, registry::ConversionPort>)
        requirements.output.relation = SetRelation::equivalent;
    return take(registry::prepare_provider(registry::select_provider(registry, method, requirements)));
}

struct RouteDependencies {
    reachability::ForwardDependencies forward;
    registry::PreparedProvider<registry::GeometryPort> capture_projection;
    registry::PreparedProvider<registry::ConversionPort> to_v;
};

Json evidence_json(const GeometryEvidence& evidence) {
    const auto support = std::visit([](const auto& value) -> Json {
        using T = std::decay_t<decltype(value)>;
        if constexpr (std::is_same_v<T, Unestablished>) return {{"kind", "unestablished"}};
        else if constexpr (std::is_same_v<T, NumericalCheck>)
            return {{"kind", "numerical_check"}, {"absolute_tolerance", value.absolute_tolerance},
                {"relative_tolerance", value.relative_tolerance}, {"max_residual", value.max_residual},
                {"verifier", value.verifier.value}};
        else if constexpr (std::is_same_v<T, SymbolicArgument>)
            return {{"kind", "symbolic_argument"}, {"reference", value.reference}, {"assumptions", value.assumptions}};
        else if constexpr (std::is_same_v<T, CertificateReference>)
            return {{"kind", "certificate_reference"}, {"artifact", value.artifact}, {"verifier", value.verifier}};
        else return {{"kind", "exact_farkas"}, {"subject_problem", value.subject().problem.value},
            {"subject_program", value.subject().program.value}};
    }, evidence.support);
    Json inputs = Json::array();
    for (const auto& input : evidence.reference.inputs) inputs.push_back(input.value);
    Json document{{"reference", {{"problem", evidence.reference.identity.problem.value},
        {"request", evidence.reference.identity.request.value},
        {"ideal_output", evidence.reference.identity.ideal_output.value}, {"inputs", std::move(inputs)}}},
        {"scope", evidence.scope == GeometryClaimScope::set_relation ? "set_relation" :
            evidence.scope == GeometryClaimScope::support_value ? "support_value" : "containment"},
        {"support", support}, {"assumptions", evidence.assumptions}};
    if (evidence.error_bound)
        document["error_bound"] = {{"metric", evidence.error_bound->metric.value},
            {"bound", evidence.error_bound->bound}, {"units", evidence.error_bound->units}};
    else document["error_bound"] = nullptr;
    return document;
}

RouteDependencies dependencies() {
    const adapters::lp::HighsLPOptions lp_options{std::nullopt};
    const adapters::polyhedral::QhullOptions qhull_options{std::nullopt, std::nullopt, {}, {}};
    const geometry::polyhedral::ProjectionOptions projection_options{
        geometry::polyhedral::ProjectionOutput::h, std::nullopt};
    auto lp = take(adapters::lp::make_highs_registration(lp_options));
    auto converter = take(adapters::polyhedral::make_qhull_registration(lp, qhull_options));
    auto hull = geometry::make_lp_hull_reducer_registration();
    auto projection = geometry::polyhedral::make_projection_registration(projection_options);
    auto affine = geometry::make_affine_sum_registration({
        selected(hull, ""), selected(lp, "csl.program-result.v1"),
        selected(converter, "csl.polyhedron.v")}, {std::nullopt, {}});
    auto capture_projection = geometry::polyhedral::make_projection_registration(
        {geometry::polyhedral::ProjectionOutput::v, std::nullopt});
    return {{selected(std::move(projection), "csl.polyhedron.h"),
        selected(std::move(affine), "csl.polyhedron.v"),
        selected(converter, "csl.polyhedron.h")},
        selected(std::move(capture_projection), "csl.polyhedron.v"),
        selected(std::move(converter), "csl.polyhedron.v")};
}

SetHandle interval(const std::string& id, double lower, double upper) {
    auto a = take(numeric::snapshot(Matrix{2, 1, {1.0, -1.0}}));
    auto b = take(numeric::snapshot_vector(Vector{upper, -lower}));
    auto e = take(numeric::snapshot(Matrix{0, 1, {}}));
    auto f = take(numeric::snapshot_vector(Vector{}));
    return take(sets::make_h({{id}, 1, {"u"}}, {std::move(a), std::move(b), std::move(e), std::move(f)})).as_handle();
}

Problem make_problem(const Json& source) {
    const auto& dynamics = source.at("dynamics");
    const std::size_t dimension = source.at("state_names").size();
    const auto& input_a = dynamics.at("A");
    std::vector<double> a_values;
    for (const auto& row : input_a) for (const auto& value : row) a_values.push_back(value.get<double>());
    std::vector<double> b_values;
    for (const auto& value : dynamics.at("B")) b_values.push_back(value.get<double>());
    Matrix a{dimension, dimension, std::move(a_values)};
    Matrix b{dimension, 1, std::move(b_values)};
    Matrix e{dimension, 0, {}};
    Vector offset(dimension, 0.0);
    const std::size_t horizon = dynamics.at("horizon").get<std::size_t>();
    const auto bounds = dynamics.at("control_bounds");
    const auto low = bounds.at(0).get<double>(), high = bounds.at(1).get<double>();
    std::vector<AdmissibleSet> controls;
    std::vector<double> times;
    std::vector<AdmissibleSet> states(horizon + 1, UniversalSet{dimension});
    for (std::size_t stage = 0; stage < horizon; ++stage) {
        controls.emplace_back(interval("fuel-control-" + std::to_string(stage), low, high));
        times.push_back(static_cast<double>(stage));
    }
    times.push_back(static_cast<double>(horizon));
    std::vector<double> initial;
    for (const auto& value : source.at("initial_state")) initial.push_back(value.get<double>());
    auto model = std::make_shared<const SystemModel>(SystemModel{{{dimension, 1, 0},
        TimeDomain::discrete, LinearStage{std::move(a), std::move(b), std::move(e), std::move(offset)}}, {}});
    return {{source.at("problem_id").get<std::string>()}, std::move(model), std::move(times),
        KnownInitial{std::move(initial)}, ContinuousDomain{std::move(controls)}, std::move(states),
        {}, {}, InformationPattern::nominal_open_loop,
        LinearTerminal{Vector(dimension, 0.0), 0.0}};
}

struct CapturedRequest {
    artifacts::StageProjectionCaptureRequest request;
    Json source_evidence;
};

CapturedRequest capture_request(
        const Json& source, const reachability::ForwardTube& tube,
        const reachability::ForwardFailure* failure, const RouteDependencies& dependencies,
        const ExecutionContext& context) {
    namespace ar = artifacts;
    std::vector<ar::CoordinateAnnotation> coordinates;
    const auto& names = source.at("state_names");
    const auto& units = source.at("state_units");
    for (std::size_t i = 0; i < names.size(); ++i)
        coordinates.push_back({names.at(i).get<std::string>(), units.at(i).get<std::string>(), {}, {}});
    std::vector<ar::StageCoordinatePair> pairs;
    std::vector<std::array<std::size_t, 2>> ordinals;
    for (const auto& pair : source.at("coordinate_pairs")) {
        const auto first = pair.at(0).get<std::size_t>(), second = pair.at(1).get<std::size_t>();
        pairs.push_back({ar::CoordinateOrdinal{first}, ar::CoordinateOrdinal{second}});
        ordinals.push_back({first, second});
    }
    std::vector<ar::StageProjectionInput> stages;
    Json stage_sources = Json::array();
    for (const auto& stage : tube.stages) {
        ConversionRequest conversion{{tube.problem,
            {source.at("request_id").get<std::string>() + "/capture/stage/" + std::to_string(stage.stage.value) + "/to-v"},
            {"fuel-stage-v-" + std::to_string(stage.stage.value)}}, stage.marginal.output,
            {"csl.polyhedron.v"}, Assurance::numerical};
        auto prepared = dependencies.to_v.prepare(conversion);
        if (const auto* rejected = std::get_if<registry::Rejection>(&prepared)) {
            const auto detail = rejected->diagnostics.empty()
                ? std::string("no rejection detail") : rejected->diagnostics.front().explanation;
            throw std::runtime_error("route marginal conversion rejected: " + detail);
        }
        auto pipeline = std::get<registry::PreparedPipeline<registry::ConversionPort>>(std::move(prepared)).create();
        auto converted = std::get<0>(pipeline)->run(context);
        const auto* converted_result = std::get_if<OperationResult>(&converted);
        if (!converted_result) throw std::runtime_error("route marginal H-to-V conversion failed");
        auto data = take(sets::from_handle(converted_result->output));
        Json providers = Json::array();
        for (const auto& provider : stage.providers)
            providers.push_back({{"request", provider.request.value}, {"port", provider.port},
                {"requested_module", provider.requested_module.value},
                {"requested_version", provider.requested_version ? Json(*provider.requested_version) : Json(nullptr)},
                {"actual_module", provider.actual_module ? Json(provider.actual_module->value) : Json(nullptr)},
                {"actual_version", provider.actual_version ? Json(*provider.actual_version) : Json(nullptr)}});
        stage_sources.push_back({{"stage", stage.stage.value}, {"marginal_set_id", stage.marginal.output.id.value},
            {"marginal_evidence", evidence_json(stage.marginal.evidence)},
            {"h_to_v_set_id", data.metadata()->id.value},
            {"h_to_v_evidence", evidence_json(converted_result->evidence)},
            {"operation_lineage", [&] { Json values = Json::array(); for (const auto& item : stage.operation_lineage) values.push_back(evidence_json(item)); return values; }()},
            {"providers", std::move(providers)}});
        ar::StageProjectionSet relation;
        relation.relation = converted_result->output;
        relation.owner = ar::PlotSourceOwner{tube.problem,
            std::variant<SetId, FamilyIdentity>{std::in_place_type<SetId>, data.metadata()->id}};
        relation.relation_coordinates.resize(coordinates.size());
        for (std::size_t i = 0; i < coordinates.size(); ++i) relation.relation_coordinates[i] = i;
        auto evidence = converted_result->evidence;
        evidence.reference.identity.ideal_output = {data.metadata()->id.value};
        evidence.assumptions.push_back("source is the nominal_forward marginal " + stage.marginal.output.id.value);
        evidence.assumptions.push_back("capture adapter binds H-to-V conversion evidence to its returned set identifier");
        evidence.assumptions.insert(evidence.assumptions.end(), stage.marginal.evidence.assumptions.begin(),
            stage.marginal.evidence.assumptions.end());
        for (const auto& provider : stage.providers) {
            if (provider.actual_module && provider.actual_version)
                evidence.assumptions.push_back("nominal_forward provider=" + provider.actual_module->value +
                    " version=" + *provider.actual_version);
        }
        relation.evidence.push_back(ar::StageProjectionSourceEvidence{
            stage.stage, data.metadata()->id, std::move(evidence)});
        stages.push_back({stage.stage, static_cast<double>(stage.stage.value), std::move(relation)});
    }
    for (std::size_t stage = tube.stages.size(); stage <= source.at("dynamics").at("horizon").get<std::size_t>(); ++stage) {
        const bool failed_here = failure && failure->stage.value == stage;
        std::string explanation = "nominal_forward did not produce a stage marginal";
        if (failed_here) {
            if (const auto* unsupported = std::get_if<Unsupported>(&failure->cause)) {
                explanation.clear();
                for (const auto& diagnostic : unsupported->diagnostics)
                    explanation += diagnostic.field + ": " + diagnostic.explanation + "; ";
            } else {
                explanation = std::get<OperationStopped>(failure->cause).diagnostics;
            }
        } else if (failure) {
            explanation = "not executed after nominal_forward stopped at R" + std::to_string(failure->stage.value);
        }
        const auto kind = failed_here
            ? (std::holds_alternative<Unsupported>(failure->cause)
                ? ar::StageProjectionGap::Kind::unsupported : ar::StageProjectionGap::Kind::stopped)
            : ar::StageProjectionGap::Kind::missing;
        stages.push_back({{stage}, static_cast<double>(stage), ar::StageProjectionGap{kind, explanation, {}}});
    }
    Json unavailable = Json::array();
    for (const auto& input : stages) {
        if (const auto* gap = std::get_if<ar::StageProjectionGap>(&input.source))
            unavailable.push_back({{"stage", input.stage.value}, {"kind", gap->kind == ar::StageProjectionGap::Kind::missing ? "missing" :
                gap->kind == ar::StageProjectionGap::Kind::unsupported ? "unsupported" : "stopped"},
                {"explanation", gap->explanation}});
    }
    Json source_evidence{{"schema", "csl.nominal-forward-stage-evidence/1"},
        {"run_id", source.at("run_id")}, {"problem_id", tube.problem.value},
        {"request_id", source.at("request_id")}, {"route_id", source.at("route_id")},
        {"source_sha256", ""}, {"stage_sources", std::move(stage_sources)},
        {"unavailable_stages", std::move(unavailable)}};
    return {{csl::ProblemId{tube.problem.value}, {source.at("request_id").get<std::string>()},
        std::move(coordinates), std::move(pairs), std::move(stages),
        SetRelation::equivalent, Assurance::numerical}, std::move(source_evidence)};
}
}

int main(int argc, char** argv) {
    if (argc != 4) {
        std::cerr << "usage: csl_stage_projection_route SOURCE.json SOURCE_SHA256 OUTPUT.json\n";
        return 2;
    }
    try {
        std::ifstream input(argv[1]);
        if (!input) throw std::runtime_error("cannot open demonstration source JSON");
        Json source; input >> source;
        const auto problem = take(csl::problem::resolve(make_problem(source),
            {csl::problem::UncertaintyStructure::stage_product_uncoupled, {}, {}}));
        csl::ExecutionContext context;
        context.numerical = {1e-8, 1e-8};
        auto route_dependencies = dependencies();
        const auto outcome = csl::reachability::nominal_forward(problem,
            {source.at("request_id").get<std::string>()}, route_dependencies.forward, context);
        const auto* tube = std::get_if<csl::reachability::ForwardTube>(&outcome);
        const auto* failure = std::get_if<csl::reachability::ForwardFailure>(&outcome);
        if (failure) tube = &failure->prefix;
        if (!tube) throw std::runtime_error("nominal_forward returned an empty initial or later stage");
        auto captured_request = capture_request(source, *tube, failure, route_dependencies, context);
        auto& request = captured_request.request;
        const auto projection = csl::artifacts::capture_stage_projections(request,
            route_dependencies.capture_projection, context);
        const auto* captured = std::get_if<csl::artifacts::StageProjectionBatchCapture>(&projection);
        if (!captured) {
            if (const auto* error = std::get_if<csl::artifacts::ArtifactError>(&projection))
                throw std::runtime_error("stage projection capture failed at " + error->path + ": " + error->message);
            if (const auto* unsupported = std::get_if<Unsupported>(&projection)) {
                std::string details;
                for (const auto& diagnostic : unsupported->diagnostics)
                    details += diagnostic.field + ": " + diagnostic.explanation + "; ";
                throw std::runtime_error("stage projection capture unsupported: " + details);
            }
            throw std::runtime_error("stage projection capture stopped");
        }
        std::vector<double> stages;
        for (const auto& stage : request.stages) stages.push_back(static_cast<double>(stage.stage.value));
        csl::artifacts::StageProjectionBatchIdentity identity{
            {source.at("run_id").get<std::string>()}, source.at("route_id").get<std::string>(),
            source.at("record_schema").get<std::string>(), argv[2], request.state_coordinates,
            {}, {csl::artifacts::PlotAxis::Kind::stage, std::move(stages), {}, {}}, {}};
        for (const auto& pair : source.at("coordinate_pairs"))
            identity.requested_coordinate_pairs.push_back({pair.at(0).get<std::size_t>(), pair.at(1).get<std::size_t>()});
        std::vector<double> state;
        for (const auto& value : source.at("initial_state")) state.push_back(value.get<double>());
        const auto& dynamics = source.at("dynamics");
        const auto control_value = dynamics.at("control_bounds").at(1).get<double>();
        std::vector<std::vector<double>> history{state};
        for (std::size_t stage = 0; stage < dynamics.at("horizon").get<std::size_t>(); ++stage) {
            std::vector<double> next(state.size(), 0.0);
            for (std::size_t row = 0; row < state.size(); ++row) {
                for (std::size_t column = 0; column < state.size(); ++column)
                    next[row] += dynamics.at("A").at(row).at(column).get<double>() * state[column];
                next[row] += dynamics.at("B").at(row).get<double>() * control_value;
            }
            state = std::move(next);
            history.push_back(state);
        }
        for (const auto& pair : identity.requested_coordinate_pairs) {
            std::vector<std::array<double, 2>> points;
            for (const auto& item : history) points.push_back({item[pair[0]], item[pair[1]]});
            identity.trajectory_series.push_back({identity.run, pair, std::move(points),
                "declared fixed control u=" + std::to_string(control_value) + " at every stage; not optimized"});
        }
        const auto encoded = csl::artifacts::encode_stage_projection_batch_json(identity, *captured);
        const auto* json = std::get_if<std::string>(&encoded);
        if (!json) {
            const auto& error = std::get<csl::artifacts::ArtifactError>(encoded);
            throw std::runtime_error("stage projection batch encoding failed at " + error.path + ": " + error.message);
        }
        std::ofstream output(argv[3]);
        if (!output) throw std::runtime_error("cannot create output batch");
        output << *json << '\n';
        if (!output) throw std::runtime_error("failed writing output batch");
        captured_request.source_evidence["source_sha256"] = argv[2];
        const auto evidence_path = std::string(argv[3]) + ".evidence.json";
        std::ofstream evidence_output(evidence_path);
        if (!evidence_output) throw std::runtime_error("cannot create route evidence sidecar");
        evidence_output << captured_request.source_evidence.dump(2) << '\n';
        if (!evidence_output) throw std::runtime_error("failed writing route evidence sidecar");
        std::cout << "captured " << tube->stages.size() << " available stages from reachability.nominal_forward";
        if (failure) std::cout << "; explicit gaps begin at R" << failure->stage.value;
        std::cout << '\n';
    } catch (const std::exception& error) {
        std::cerr << "stage projection route failed: " << error.what() << '\n';
        return 1;
    }
}
