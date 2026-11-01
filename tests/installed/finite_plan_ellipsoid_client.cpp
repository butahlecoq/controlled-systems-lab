#include <csl/reachability/finite_plan_ellipsoid.hpp>

#include <cmath>
#include <iostream>
#include <variant>

using namespace csl;

int main() {
  const SystemModel authored{{{1, 0, 0}, TimeDomain::discrete,
      LinearStage{{1, 1, {1.0}}, {1, 0, {}}, {1, 0, {}}, {0.0}}}, {}};
  const auto system_result = model::snapshot(authored, Vector{0.0, 1.0});
  if (!std::holds_alternative<model::LinearSystem>(system_result)) return 1;
  const auto system = std::get<model::LinearSystem>(system_result);
  const auto initial_point = numeric::snapshot_vector(Vector{0.0});
  if (!std::holds_alternative<numeric::VectorView>(initial_point)) return 2;
  const auto initial_result = sets::make_singleton(
      {{"installed-ellipse-initial"}, 1, {"x"}},
      std::get<numeric::VectorView>(initial_point));
  if (!std::holds_alternative<sets::SetData>(initial_result)) return 3;
  const auto disturbance_point = numeric::snapshot_vector(Vector{});
  if (!std::holds_alternative<numeric::VectorView>(disturbance_point)) return 4;
  const auto disturbance_result = sets::make_singleton(
      {{"installed-ellipse-disturbance"}, 0, {}},
      std::get<numeric::VectorView>(disturbance_point));
  if (!std::holds_alternative<sets::SetData>(disturbance_result)) return 5;
  const auto safe0 = sets::make_universal({{"installed-safe-0"}, 1, {"x"}});
  const auto safe1 = sets::make_universal({{"installed-safe-1"}, 1, {"x"}});
  if (!std::holds_alternative<sets::SetData>(safe0) ||
      !std::holds_alternative<sets::SetData>(safe1)) return 6;
  const reachability::FixedPlanRequest request{
      system, std::get<sets::SetData>(initial_result), {Vector{}},
      {std::get<sets::SetData>(disturbance_result)},
      {std::get<sets::SetData>(safe0), std::get<sets::SetData>(safe1)},
      {"installed-ellipsoid-request"}};
  const auto outcome = reachability::finite_plan_ellipsoid(request);
  const auto* trace = std::get_if<reachability::FinitePlanEllipsoidTrace>(&outcome);
  if (!trace || trace->stages.size() != 2 || trace->stages[1].center.size() != 1 ||
      !std::isfinite(trace->stages[1].radii[0])) return 7;
  std::cout << "Installed ellipsoid propagation client: public stage trace passed\n";
  return 0;
}
