#pragma once

#include <csl/optimization/objectives.hpp>
#include <csl/reachability/finite_plan_zonotope.hpp>

namespace csl::optimization::detail {

using ZonotopeCornerCertificate = std::variant<std::monostate, std::vector<int>, OperationStopped>;

ZonotopeCornerCertificate
certify_zonotope_corner(const reachability::FinitePlanZonotopeTrace::Stage &, const Objective &,
                        const ExecutionContext &);

} // namespace csl::optimization::detail
