#include <csl/optimization/finite_action_zonotope_minimax.hpp>

#include <type_traits>

using namespace csl;
using namespace csl::optimization;

using ZonotopeMinimax = FiniteActionZonotopeMinimaxOutcome (*) (
    const FiniteActionMinimaxRequest&, FiniteActionZonotopeMinimaxLimits,
    const ExecutionContext&);
static_assert(std::is_same_v<decltype(&finite_action_zonotope_minimax), ZonotopeMinimax>);
static_assert(std::variant_size_v<FiniteActionZonotopeSelectionOutcome> == 5);
static_assert(std::variant_size_v<FiniteActionZonotopePlanAttempt> == 3);

int main() {
    auto operation = &finite_action_zonotope_minimax;
    return operation == nullptr;
}
