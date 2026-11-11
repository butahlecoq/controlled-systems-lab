#include <csl/problem/resolved_problem.hpp>
#include <csl/numeric/data.hpp>
#include <csl/registry/strategy_catalogue.hpp>
#include <csl/sets/data.hpp>
#include <csl/synthesis/strategy_ts01/analytic_profile.hpp>

#include <iostream>
#include <stdexcept>

namespace {
void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}

template<class T> T take(csl::numeric::Result<T> result) {
    if (!std::holds_alternative<T>(result)) throw std::runtime_error("numeric snapshot failed");
    return std::get<T>(std::move(result));
}

csl::SetHandle interval(std::string id) {
    using namespace csl;
    const sets::Description description{SetId{std::move(id)}, 1, {"u"}};
    const Vector bounds{1,0};
    const Vector no_values{};
    const sets::HRepresentation representation{
        take(numeric::snapshot(Matrix{2,1,{1,-1}})), take(numeric::snapshot_vector(bounds)),
        take(numeric::snapshot(Matrix{0,1,{}})), take(numeric::snapshot_vector(no_values))};
    auto result = sets::make_h(description, representation);
    require(std::holds_alternative<sets::SetData>(result), "interval construction failed");
    return std::get<sets::SetData>(std::move(result)).as_handle();
}

csl::problem::ResolvedProblem make_problem() {
    using namespace csl;
    const LinearStage stage{{1,1,{1}}, {1,1,{1}}, {1,0,{}}, {0}};
    auto model = std::make_shared<const SystemModel>(SystemModel{
        Dynamics{{1,1,0}, TimeDomain::discrete, stage}, {}});
    Problem source;
    source.id = {"installed-strategy-catalogue"};
    source.model = std::move(model);
    source.times = {0,1,2};
    source.initial = KnownInitial{{0}};
    source.controls = ContinuousDomain{{interval("u0"), interval("u1")}};
    source.states = {UniversalSet{1}, UniversalSet{1}, UniversalSet{1}};
    source.information = InformationPattern::nominal_open_loop;
    QuadraticTerminal objective;
    objective.Q = Matrix{1,1,{2}};
    objective.linear = {-2};
    objective.offset = 1;
    source.objective = std::move(objective);
    auto resolved = problem::resolve(source,
        {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}});
    require(std::holds_alternative<problem::ResolvedProblem>(resolved), "problem resolution failed");
    return std::get<problem::ResolvedProblem>(std::move(resolved));
}
}

int main() try {
    using namespace csl;
    registry::StrategyRegistry strategies;
    require(!strategies.add(synthesis::strategy_ts01::make_registration()),
        "analytic strategy registration failed");
    const auto problem = make_problem();
    FamilyRequest family;
    family.profile = "ts01_exact_integrator";
    family.objective = problem.identity();
    family.target = FamilyTarget::exact_optimal_relation;
    family.assurance = Assurance::numerical;
    family.representation = {"csl.polyhedron.h"};
    StrategyConfiguration configuration;
    configuration.strategy = {"csl.synthesis.ts01-analytic"};
    configuration.representation = family.representation;
    registry::StrategyRequest request{problem, configuration, family, {}, {}};
    registry::Requirements requirements;
    requirements.output.representation = {"csl.polyhedron.h"};
    requirements.output.family = FamilyTarget::exact_optimal_relation;
    requirements.output.completeness = registry::Completeness::established;
    const auto rows = registry::enumerate_strategy_candidates(strategies, request, requirements);
    require(rows.size() == 1 && rows.front().status == registry::CandidateStatus::admitted,
        "analytic strategy candidate was not admitted");
    require(rows.front().prepared.has_value() && !rows.front().provenance.empty(),
        "prepared strategy receipt is missing");
    auto receipt = registry::prepare_strategy_candidate(strategies, rows.front().graph,
        request, requirements);
    require(std::holds_alternative<registry::PreparedStrategyCandidate>(receipt),
        "pinned analytic strategy candidate did not re-prepare");
    std::cout << "Installed strategy catalogue client: concrete TS01 admission and re-prepare passed\n";
    return 0;
} catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
}
