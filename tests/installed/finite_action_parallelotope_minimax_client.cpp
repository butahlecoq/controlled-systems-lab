#include <csl/optimization/finite_action_parallelotope_minimax.hpp>

#include <type_traits>

using namespace csl::optimization;
using ParallelotopeMinimax = FiniteActionParallelotopeMinimaxOutcome (*)(
    const FiniteActionMinimaxRequest &, FiniteActionParallelotopeMinimaxLimits,
    const ExecutionContext &);
static_assert(std::is_same_v<decltype(&finite_action_parallelotope_minimax),
                             ParallelotopeMinimax>);

int main() {
  auto operation = &finite_action_parallelotope_minimax;
  return operation == nullptr;
}
