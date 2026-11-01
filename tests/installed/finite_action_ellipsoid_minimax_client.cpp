#include <csl/optimization/finite_action_ellipsoid_minimax.hpp>

#include <type_traits>

using namespace csl::optimization;
using EllipsoidMinimax = FiniteActionEllipsoidMinimaxOutcome (*)(
    const FiniteActionMinimaxRequest &, FiniteActionEllipsoidMinimaxLimits,
    const csl::ExecutionContext &);
static_assert(std::is_same_v<decltype(&finite_action_ellipsoid_minimax),
                             EllipsoidMinimax>);

int main() {
  auto operation = &finite_action_ellipsoid_minimax;
  return operation == nullptr;
}
