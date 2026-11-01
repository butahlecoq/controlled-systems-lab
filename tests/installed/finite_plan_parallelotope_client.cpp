#include <csl/reachability/finite_plan_parallelotope.hpp>

#include <type_traits>

using namespace csl;

using ParallelotopePropagation = reachability::FinitePlanParallelotopeOutcome (
        *)(const reachability::FixedPlanRequest &, const ExecutionContext &);
static_assert(std::is_same_v<decltype(&reachability::finite_plan_parallelotope),
                             ParallelotopePropagation>);

int main() {
  auto operation = &reachability::finite_plan_parallelotope;
  return operation == nullptr;
}
