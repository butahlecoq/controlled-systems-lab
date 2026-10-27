#include <csl/adapters/lp/highs.hpp>
#include <csl/input/scenario_loader.hpp>
#include <csl/optimization/phase_one.hpp>
#include <csl/sets/data.hpp>
#include <cmath>
#include <fstream>
#include <iostream>
#include <stdexcept>

namespace {
using namespace csl;

template<class T, class... Rest>
T take(std::variant<T, Rest...> result, const char* what) {
    if (auto* value = std::get_if<T>(&result)) return std::move(*value);
    throw std::runtime_error(std::string(what) + " rejected");
}

std::string json_string(std::string_view value) {
    std::string result = "\"";
    for (const char c : value) {
        if (c == '"' || c == '\\') result.push_back('\\');
        if (c == '\n') { result += "\\n"; continue; }
        if (c == '\r') { result += "\\r"; continue; }
        if (c == '\t') { result += "\\t"; continue; }
        result.push_back(c);
    }
    result.push_back('"');
    return result;
}

bool scalar_integrator_fixture(const problem::ResolvedProblem& resolved) {
    const auto source = resolved.description();
    if (source->times != std::vector<double>{0, 1, 2} || source->model->dynamics.time_domain != TimeDomain::discrete ||
        source->model->dynamics.dimensions != Dimensions{1, 1, 0} || source->temporal || source->external ||
        source->information != InformationPattern::nominal_open_loop)
        return false;
    const auto* stage = std::get_if<LinearStage>(&source->model->dynamics.stages);
    if (!stage || stage->A.values != Vector{1} || stage->B.values != Vector{1} ||
        !stage->E.values.empty() || stage->offset != Vector{0})
        return false;
    const auto* initial = std::get_if<KnownInitial>(&source->initial);
    if (!initial || initial->point != Vector{0}) return false;
    if (source->states.size() != 3) return false;
    for (const auto& state : source->states) {
        const auto* universal = std::get_if<UniversalSet>(&state);
        if (!universal || universal->dimension != 1) return false;
    }
    if (source->controls.index() != 0) return false;
    const auto& controls = std::get<ContinuousDomain>(source->controls);
    if (controls.stages.size() != 2) return false;
    for (const auto& control : controls.stages) {
        const auto* handle = std::get_if<SetHandle>(&control);
        if (!handle) return false;
        const auto set = sets::from_handle(*handle);
        const auto* data = std::get_if<sets::SetData>(&set);
        if (!data) return false;
        const auto representation = data->representation();
        const auto* h = std::get_if<sets::HRepresentation>(&representation);
        if (!h || h->inequalities.rows() != 2 || h->inequalities.cols() != 1 ||
            h->inequalities(0, 0) != 1 || h->inequalities(1, 0) != -1 ||
            h->upper_bounds.size() != 2 || h->upper_bounds[0] != 1 || h->upper_bounds[1] != 0 ||
            h->equalities.rows() != 0 || h->equality_values.size() != 0)
            return false;
    }
    const auto* quadratic = std::get_if<QuadraticTerminal>(&source->objective);
    return quadratic && quadratic->Q.rows == 1 && quadratic->Q.cols == 1 &&
        quadratic->Q.values == Vector{2} && quadratic->linear == Vector{-2} && quadratic->offset == 1;
}
}

int main(int argc, char** argv) try {
    using namespace csl;
    using namespace csl::optimization;
    using namespace csl::registry;
    if (argc != 3) {
        std::cerr << "Usage: scenario_backend_substitution <scenario.json> <output.json>\n";
        return 2;
    }
    const auto loaded = input::load_scenario_file(argv[1]);
    if (!std::holds_alternative<input::LoadedScenario>(loaded)) {
        std::cerr << "Scenario rejected: provider fixture requires an executable csl.scenario/1 input\n";
        return 2;
    }
    const auto& scenario = std::get<input::LoadedScenario>(loaded);
    const auto requested = scenario.requested_run();
    const auto request = requested->backends.find(input::BackendRole::lp);
    if (request == requested->backends.end()) {
        std::cerr << "Input unsupported: path=/run/backends/lp observed=missing-backend\n";
        return 2;
    }
    if (request->second.version) {
        std::cerr << "Input unsupported: path=/run/backends/lp/version observed="
                  << *request->second.version << " expected=backend ID selection only\n";
        return 2;
    }

    // Provider-specific fixture: the scalar two-stage integrator can reach x2=1
    // exactly when u0+u1=1. With u in [0,1], this is a zero-objective equality
    // feasibility LP; no optimality or general synthesis claim is made here.
    if (scenario.metadata()->id != "two-stage-integrator" ||
        !scalar_integrator_fixture(scenario.problem())) {
        std::cerr << "Input unsupported: path=/scenario/model observed=" << scenario.metadata()->id
                  << " observed_problem=" << scenario.problem().identity().value
                  << " expected=the two-stage scalar integrator fixture with its declared objective and domains\n";
        return 2;
    }
    const auto program = std::get<LinearProgram>(phase_one::make_program(
        {{"scenario.two-stage-integrator.reachable-controls"}, {"lp"}},
        {1, 2, {0, 2}, {0, 1}, {1, 1}}, Vector{1}));
    Registry<LPPort> registry;
    auto highs = take(adapters::lp::make_highs_registration(), "HiGHS registration");
    auto bland = take(phase_one::make_registration(), "Phase I registration");
    const auto highs_identity = highs.identity;
    const auto bland_identity = bland.identity;
    if (registry.add(std::move(highs)) || registry.add(std::move(bland)))
        throw std::runtime_error("Backend registration failed");
    Requirements requirements;
    requirements.output.representation = {"csl.program-result.v1"};
    auto preparation = prepare_pipeline(select(registry, {{request->second.id.value}, {}}, program, requirements));
    if (const auto* rejected = std::get_if<Rejection>(&preparation)) {
        std::cerr << "Input unsupported: path=/run/backends/lp observed="
                  << rejected->provenance.requested.id.value;
        for (const auto& diagnostic : rejected->diagnostics)
            std::cerr << " reason=" << diagnostic.field << ':' << diagnostic.explanation;
        std::cerr << '\n';
        return 2;
    }
    const auto& prepared = std::get<PreparedPipeline<LPPort>>(preparation);
    auto [workspace] = prepared.create();
    const auto outcome = workspace->run({{}, {}, {}, {1e-8, 1e-8}, "scenario-backend-fixture"});
    const auto* result = std::get_if<ProgramResult>(&outcome);
    if (!result || result->termination != Termination::completed ||
        result->outcome.value != MathematicalOutcome::optimal || !result->primal ||
        !check_program_result(*result, program, Assurance::numerical).empty())
        throw std::runtime_error("Provider did not return a checked feasibility witness");
    const auto& u = *result->primal;
    if (u.size() != 2 || u[0] < -1e-8 || u[1] < -1e-8 ||
        u[0] > 1 + 1e-8 || u[1] > 1 + 1e-8 ||
        std::abs(u[0] + u[1] - 1) > 1e-8)
        throw std::runtime_error("Independent scenario equation check failed");

    const auto actual = prepared.provenance()[0].actual.value();
    const auto& expected = actual.id == highs_identity.id ? highs_identity : bland_identity;
    if (actual.id != expected.id || actual.version != expected.version)
        throw std::runtime_error("Effective provider identity was not retained");
    const auto source = scenario.source();
    std::ofstream output(argv[2], std::ios::binary | std::ios::trunc);
    if (!output) throw std::runtime_error("Cannot create output artifact");
    output << "{\n  \"schema\": \"csl.scenario-backend-feasibility/1\",\n"
           << "  \"problem\": " << json_string(scenario.problem().identity().value) << ",\n"
           << "  \"scenario_source_sha256\": " << json_string(problem::hex(source->content.digest())) << ",\n"
           << "  \"scenario_id\": " << json_string(scenario.metadata()->id) << ",\n"
           << "  \"requested_backend\": " << json_string(request->second.id.value) << ",\n"
           << "  \"effective_backend\": {\"id\": " << json_string(actual.id.value)
           << ", \"version\": " << json_string(actual.version) << "},\n"
           << "  \"effective_configuration\": {\"profile\": \"zero-objective-equality-feasibility\", "
              "\"absolute_tolerance\": 1e-8, \"relative_tolerance\": 1e-8, \"threads\": 1},\n"
           << "  \"fixture\": \"two-stage-integrator terminal reachability: u0+u1=1, 0<=u<=1\",\n"
           << "  \"termination\": \"completed\",\n  \"outcome\": \"feasible\",\n"
           << "  \"evidence_scope\": \"numerical feasibility witness; no optimality or complete-family claim\",\n"
           << "  \"controls\": [" << u[0] << ", " << u[1] << "],\n"
           << "  \"terminal_sum\": " << (u[0] + u[1]) << "\n}\n";
    if (!output) throw std::runtime_error("Failed while writing output artifact");
    std::cout << "problem=" << scenario.problem().identity().value
              << " backend=" << actual.id.value << " version=" << actual.version
              << " outcome=feasible controls=" << u[0] << ',' << u[1]
              << " evidence=numerical_feasibility_only artifact=" << argv[2] << '\n';
} catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
}
