#include <csl/optimization/finite_action_nominal.hpp>

#include <cmath>
#include <iostream>
#include <type_traits>
#include <variant>

using namespace csl;
using namespace csl::optimization;

using Nominal = FiniteActionNominalOutcome (*)(const FiniteActionNominalRequest &,
    FiniteActionNominalLimits, const ExecutionContext &);
using Profile = FiniteActionNominalOutcome (*)(const FiniteActionNominalRequest &,
    FiniteActionNominalLimits, NominalRepresentation, const ExecutionContext &);
static_assert(std::is_same_v<decltype(&finite_action_nominal), Nominal>);
static_assert(std::is_same_v<decltype(&finite_action_nominal_profile), Profile>);
static_assert(std::is_same_v<decltype(FiniteActionNominalRequest::running_cost), RunningControlCost>);
static_assert(std::is_same_v<decltype(FiniteActionNominalRequest::candidate_action_indices),
    std::optional<std::vector<std::vector<std::size_t>>>>);
static_assert(std::is_same_v<decltype(NominalPlanScored::exact_running_cost), double>);
static_assert(std::variant_size_v<ControlPenalty> == 2);

int main() {
    const SystemModel authored{{{2,1,0}, TimeDomain::discrete,
        LinearStage{{2,2,{1,0,0,1}}, {2,1,{1,0}}, {2,0,{}}, {0,0}}}, {}};
    const auto system_result = model::snapshot(authored, Vector{0,1,2});
    const auto* system = std::get_if<model::LinearSystem>(&system_result);
    if(!system) return 1;
    const auto safe_result = sets::make_universal({{"installed-candidate-safe"},2,{"x","y"}});
    const auto* safe = std::get_if<sets::SetData>(&safe_result);
    if(!safe) return 2;
    const auto objective_result = snapshot(LinearTerminal{{-1,0}, 0.0});
    const auto* objective = std::get_if<Objective>(&objective_result);
    if(!objective) return 3;

    FiniteActionNominalRequest request{
        {"installed-candidate-source"}, {"installed-candidate-default"}, *system, {0,0},
        {1, {{0},{1}}}, {{},{}}, {*safe,*safe,*safe}, *objective};
    const FiniteActionNominalLimits limits{4,64,64,64,0.0};
    const auto default_result = finite_action_nominal_profile(request, limits,
        NominalRepresentation::exact_polytope);
    const auto* default_tracks = std::get_if<FiniteActionNominalResult>(&default_result);
    if(!default_tracks || default_tracks->tracks.size()!=1) return 4;
    const auto* default_selected = std::get_if<NominalTrackSelected>(&default_tracks->tracks.front().outcome);
    if(!default_selected || default_selected->coverage!=NominalSearchCoverage::complete ||
       default_selected->attempts.size()!=4) return 5;

    auto restricted = request;
    restricted.request = {"installed-candidate-restricted"};
    restricted.running_cost = {"installed-euclidean-control-cost/1", 2, {
        {0, {EuclideanControlPenalty{Matrix{1,1,{1}}, {0}, 0.25}}}}};
    restricted.candidate_action_indices = std::vector<std::vector<std::size_t>>{{1,0},{0,0}};
    const auto restricted_result = finite_action_nominal_profile(restricted, limits,
        NominalRepresentation::exact_polytope);
    const auto* restricted_tracks = std::get_if<FiniteActionNominalResult>(&restricted_result);
    if(!restricted_tracks || restricted_tracks->tracks.size()!=1) return 6;
    const auto* selected = std::get_if<NominalTrackSelected>(&restricted_tracks->tracks.front().outcome);
    if(!selected || selected->coverage!=NominalSearchCoverage::incomplete ||
       selected->replay.controls!=std::vector<Vector>{{1},{0}} ||
       selected->replay.states!=std::vector<Vector>{{0,0},{1,0},{1,0}} ||
       std::abs(selected->replay.terminal_objective + 1.0)>1e-12 ||
       std::abs(selected->replay.running_objective - 0.25)>1e-12 ||
       std::abs(selected->replay.total_objective + 0.75)>1e-12 ||
       selected->selected_attempt>=selected->attempts.size()) return 7;
    const auto* scored = std::get_if<NominalPlanScored>(&selected->attempts[selected->selected_attempt]);
    if(!scored || scored->action_indices!=std::vector<std::size_t>{1,0} ||
       std::abs(scored->exact_running_cost - 0.25)>1e-12) return 8;

    auto empty = restricted;
    empty.request = {"installed-candidate-empty"};
    empty.candidate_action_indices = std::vector<std::vector<std::size_t>>{};
    const auto empty_result = finite_action_nominal_profile(empty, limits,
        NominalRepresentation::exact_polytope);
    const auto* refusal = std::get_if<Unsupported>(&empty_result);
    if(!refusal || refusal->diagnostics.empty() ||
       refusal->diagnostics.front().field!="finite_nominal.candidate_plans") return 9;

    std::cout << "Installed nominal client: default exhaustive, source-cost restricted candidate, and empty rejection passed\n";
    return 0;
}
