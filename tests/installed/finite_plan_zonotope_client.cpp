#include <csl/reachability/finite_plan_zonotope.hpp>

#include <type_traits>

using namespace csl;

using ZonotopePropagation = reachability::FinitePlanZonotopeOutcome (*) (
    const reachability::FixedPlanRequest&, reachability::FinitePlanZonotopeLimits,
    const ExecutionContext&);
static_assert(std::is_same_v<decltype(&reachability::finite_plan_zonotope),
    ZonotopePropagation>);

int main() {
    auto operation = &reachability::finite_plan_zonotope;
    return operation == nullptr;
}
