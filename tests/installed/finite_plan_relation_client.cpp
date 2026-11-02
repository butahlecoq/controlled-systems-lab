#include <csl/reachability/finite_plan_box.hpp>
#include <csl/reachability/finite_plan_ellipsoid.hpp>
#include <csl/reachability/finite_plan_parallelotope.hpp>
#include <csl/reachability/finite_plan_zonotope.hpp>

static_assert(csl::reachability::FinitePlanBoxTrace::relation ==
              csl::SetRelation::outer);
static_assert(csl::reachability::FinitePlanEllipsoidTrace::relation ==
              csl::SetRelation::outer);
static_assert(csl::reachability::FinitePlanParallelotopeTrace::relation ==
              csl::SetRelation::outer);
static_assert(csl::reachability::FinitePlanZonotopeTrace::relation ==
              csl::SetRelation::outer);

int main() { return 0; }
