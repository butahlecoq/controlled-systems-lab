#include <csl/geometry/generators.hpp>
#include <csl/model/discrete_catalogue.hpp>
#include <csl/model/linear_system.hpp>

#include <algorithm>
#include <array>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <numbers>
#include <stdexcept>
#include <variant>

namespace {
using namespace csl;
constexpr std::size_t horizon = 3;
constexpr std::size_t directions = 32;

template <class T, class... Errors> T take(std::variant<T, Errors...> result) {
  if (auto *value = std::get_if<T>(&result))
    return std::move(*value);
  throw std::runtime_error(
      "Native catalogue, dynamics, or generator operation refused");
}

void sample(std::string_view model, std::size_t stage,
            const sets::GeneratorSet &set, std::size_t i, std::size_t j,
            double dx, double dy) {
  const auto &G = set.generators();
  double x = set.center()[i];
  double y = set.center()[j];
  for (std::size_t col = 0; col < G.cols; ++col) {
    const double a = G.values[i * G.cols + col];
    const double b = G.values[j * G.cols + col];
    const double value = dx * a + dy * b;
    const double sign = (value > 0) - (value < 0);
    x += sign * a;
    y += sign * b;
  }
  const double support = dx * x + dy * y;
  if (!std::isfinite(x) || !std::isfinite(y) || !std::isfinite(support))
    throw std::runtime_error("Nonfinite support witness");
  std::cout << model << ',' << stage << ',' << i << ',' << j << ',' << dx << ','
            << dy << ',' << support << ',' << x << ',' << y << '\n';
}

void run(const model::catalogue::DiscreteModelInfo &info) {
  const auto data = take(model::catalogue::make_discrete_model(info.id));
  const auto &coefficients = data.coefficients;
  const auto n = coefficients.A.rows;
  const auto m = coefficients.B.cols;
  if (n < 2 || std::ranges::any_of(
                   coefficients.offset, [](double x) { return x != 0.0; }))
    throw std::runtime_error(
        "Fixture requires two state coordinates and zero affine offset");
  std::array<double, horizon + 1> time{};
  for (std::size_t k = 0; k <= horizon; ++k)
    time[k] = k * data.time_step.value;
  const auto system = take(model::snapshot(data.system_model(), time));
  const auto external =
      data.nominal_external.value_or(Vector(coefficients.E.cols, 0.0));
  auto reachable = take(sets::make_generator_set(
      {{"initial"}, data.initial_state, {n, 0, {}}, {}, {0, 0, {}}, {}, {}}));
  for (std::size_t stage = 0;; ++stage) {
    for (std::size_t i = 0; i < n; ++i) {
      const auto j = (i + 1) % n;
      sample(info.id, stage, reachable, i, j, 1.0, 0.0);
      sample(info.id, stage, reachable, i, j, -1.0, 0.0);
    }
    const auto i = info.id == "catalogue-2026/model-26/1" ? std::size_t{27} : 0;
    const auto j = i + 1;
    for (std::size_t direction = 0; direction < directions; ++direction) {
      const double angle = 2 * std::numbers::pi * direction / directions;
      sample(info.id, stage, reachable, i, j, std::cos(angle), std::sin(angle));
    }
    if (stage == horizon)
      return;
    const auto drift =
        take(system.step({stage}, Vector(n, 0.0), Vector(m, 0.0), external));
    const auto propagated = take(geometry::generators::affine_image(
        reachable, coefficients.A, drift, {"propagated"}));
    std::vector<sets::FactorId> factors;
    for (std::size_t control = 0; control < m; ++control)
      factors.push_back(
          {std::to_string(stage) + "/" + std::to_string(control)});
    const auto control_image =
        take(sets::make_generator_set({{"control-image"},
                                       Vector(n, 0.0),
                                       coefficients.B,
                                       std::move(factors),
                                       {0, m, {}},
                                       {},
                                       {}}));
    reachable = take(geometry::generators::minkowski_sum(
        propagated, control_image, {"reachable"}));
  }
}
} // namespace

int main() {
  try {
    std::cout << std::setprecision(17)
              << "model,stage,i,j,dx,dy,support,witness_x,witness_y\n";
    for (const auto &info : csl::model::catalogue::discrete_models())
      run(info);
  } catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
