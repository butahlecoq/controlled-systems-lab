#include <csl/optimization/finite_action_nominal.hpp>

#include <type_traits>
#include <variant>

using namespace csl::optimization;
using Nominal = FiniteActionNominalOutcome (*)(const FiniteActionNominalRequest &,
    FiniteActionNominalLimits, const csl::ExecutionContext &);
using Profile = FiniteActionNominalOutcome (*)(const FiniteActionNominalRequest &,
    FiniteActionNominalLimits, NominalRepresentation, const csl::ExecutionContext &);
static_assert(std::is_same_v<decltype(&finite_action_nominal), Nominal>);
static_assert(std::is_same_v<decltype(&finite_action_nominal_profile), Profile>);
static_assert(std::is_same_v<decltype(FiniteActionNominalRequest::running_cost), RunningControlCost>);
static_assert(std::is_same_v<decltype(NominalPlanScored::exact_running_cost), double>);
static_assert(std::variant_size_v<ControlPenalty> == 2);

int main() {
  return &finite_action_nominal == nullptr || &finite_action_nominal_profile == nullptr;
}
