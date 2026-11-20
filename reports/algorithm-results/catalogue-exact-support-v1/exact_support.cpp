#include <gmpxx.h>
#include <nlohmann/json.hpp>

#include <algorithm>
#include <cmath>
#include <fstream>
#include <iostream>
#include <optional>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {
using Json = nlohmann::json;
using Rational = mpq_class;
using Vector = std::vector<Rational>;
using Matrix = std::vector<Vector>;

void require(bool condition, const char *message) {
  if (!condition)
    throw std::runtime_error(message);
}

Rational exact(const Json &number) {
  const double value = number.get<double>();
  require(std::isfinite(value), "nonfinite binary64 input");
  return Rational(value);
}

Vector vector(const Json &source) {
  Vector result;
  for (const auto &number : source)
    result.push_back(exact(number));
  return result;
}

Matrix matrix(const Json &source) {
  const auto rows = source.at("rows").get<std::size_t>();
  const auto cols = source.at("cols").get<std::size_t>();
  const auto values = vector(source.at("values"));
  require(values.size() == rows * cols, "matrix shape mismatch");
  Matrix result(rows, Vector(cols));
  auto value = values.begin();
  for (auto &row : result)
    for (auto &entry : row)
      entry = *value++;
  return result;
}

Rational dot(const Vector &left, const Vector &right) {
  require(left.size() == right.size(), "dot product dimension mismatch");
  Rational result;
  for (std::size_t i = 0; i < left.size(); ++i)
    result += left[i] * right[i];
  return result;
}

Vector pullback(const Matrix &map, const Vector &direction) {
  require(!map.empty() && map.size() == direction.size(),
          "pullback shape mismatch");
  Vector result(map.front().size());
  for (std::size_t i = 0; i < map.size(); ++i)
    for (std::size_t j = 0; j < result.size(); ++j)
      result[j] += direction[i] * map[i][j];
  return result;
}

bool zero(const Matrix &map) {
  for (const auto &row : map)
    for (const auto &entry : row)
      if (entry != 0)
        return false;
  return true;
}

struct ControlBounds {
  Vector lower;
  Vector upper;
};

ControlBounds control_bounds(const Json &source) {
  ControlBounds result;
  for (const auto &pair : source) {
    result.lower.push_back(exact(pair.at(0)));
    result.upper.push_back(exact(pair.at(1)));
    require(result.lower.back() <= result.upper.back(),
            "reversed control bounds");
  }
  return result;
}

struct Budget {
  Vector weights;
  Rational cap;
};

std::optional<Budget> supported_budget(const Json &constraint) {
  const auto state = matrix(constraint.at("state"));
  const auto control = matrix(constraint.at("control"));
  const auto external = matrix(constraint.at("external"));
  const auto &bounds = constraint.at("bounds");
  require(zero(state) && zero(external) && control.size() == bounds.size() &&
              control.size() <= 1,
          "expected at most one separable control budget per stage");
  if (control.empty())
    return std::nullopt;
  require(bounds.at(0).at(0).is_null() && !bounds.at(0).at(1).is_null(),
          "expected an upper control budget");
  for (const auto &weight : control.front())
    require(weight >= 0, "expected nonnegative budget weights");
  return Budget{control.front(), exact(bounds.at(0).at(1))};
}

struct StageSupport {
  Vector controls;
  Rational multiplier;
};

StageSupport support(const ControlBounds &bounds, const Vector &direction,
                     const std::optional<Budget> &budget) {
  require(bounds.lower.size() == direction.size(),
          "control direction shape mismatch");
  StageSupport result{bounds.lower, 0};
  if (!budget) {
    for (std::size_t i = 0; i < direction.size(); ++i) {
      if (direction[i] > 0)
        result.controls[i] = bounds.upper[i];
      if (direction[i] == 0)
        result.controls[i] = (bounds.lower[i] + bounds.upper[i]) / 2;
    }
    return result;
  }
  Rational slack = budget->cap - dot(budget->weights, result.controls);
  require(slack >= 0, "control budget infeasible at lower endpoints");
  std::vector<std::pair<Rational, std::size_t>> order;
  for (std::size_t i = 0; i < direction.size(); ++i) {
    if (direction[i] <= 0)
      continue;
    if (budget->weights[i] == 0)
      result.controls[i] = bounds.upper[i];
    else if (bounds.lower[i] < bounds.upper[i])
      order.emplace_back(direction[i] / budget->weights[i], i);
  }
  std::stable_sort(order.begin(), order.end(),
                   [](const auto &left, const auto &right) {
                     return left.first > right.first;
                   });
  for (const auto &[ratio, index] : order) {
    const Rational cap =
        budget->weights[index] * (bounds.upper[index] - bounds.lower[index]);
    if (cap <= slack) {
      result.controls[index] = bounds.upper[index];
      slack -= cap;
    } else {
      result.controls[index] += slack / budget->weights[index];
      result.multiplier = ratio;
      break;
    }
  }
  return result;
}

struct Model {
  Matrix A, B, G;
  Vector offset, initial;
  Matrix external;
  std::vector<ControlBounds> controls;
  std::vector<std::optional<Budget>> budgets;
  Json state_limits;
};

Model load(const Json &record) {
  const auto &constraints = record.at("constraints");
  require(constraints.at("terminal").empty(),
          "terminal coupling is outside this diagnostic");
  for (const auto &budgets : constraints.at("positive_part"))
    require(budgets.empty(),
            "positive-part budgets are outside this diagnostic");
  Model model{matrix(record.at("A")),
              matrix(record.at("B")),
              matrix(record.at("G")),
              vector(record.at("offset")),
              vector(record.at("initial")),
              {},
              {},
              {},
              constraints.at("state")};
  const auto &source_stage = constraints.at("stage");
  for (const auto &entry : record.at("external"))
    model.external.push_back(vector(entry));
  for (const auto &entry : constraints.at("control"))
    model.controls.push_back(control_bounds(entry));
  require(model.controls.size() == 3 &&
              model.external.size() == model.controls.size() &&
              (source_stage.empty() ||
               source_stage.size() == model.controls.size()),
          "expected three matched stages");
  for (std::size_t k = 0; k < model.controls.size(); ++k)
    model.budgets.push_back(source_stage.empty()
                                ? std::nullopt
                                : supported_budget(source_stage.at(k)));
  require(model.state_limits.size() == model.controls.size() + 1,
          "state-bound grid mismatch");
  return model;
}

Vector next(const Model &model, const Vector &state, const Vector &action,
            std::size_t k) {
  Vector output;
  for (std::size_t i = 0; i < model.offset.size(); ++i)
    output.push_back(model.offset[i] + dot(model.A.at(i), state) +
                     dot(model.B.at(i), action) +
                     dot(model.G.at(i), model.external.at(k)));
  return output;
}

void check_state(const Json &bounds, const Vector &state, std::size_t stage,
                 Json &failures) {
  require(bounds.size() == state.size(), "state-bound dimension mismatch");
  for (std::size_t j = 0; j < state.size(); ++j) {
    const auto &pair = bounds.at(j);
    if (!pair.at(0).is_null() && state[j] < exact(pair.at(0)))
      failures.push_back(
          {{"stage", stage}, {"coordinate", j}, {"side", "lower"}});
    if (!pair.at(1).is_null() && state[j] > exact(pair.at(1)))
      failures.push_back(
          {{"stage", stage}, {"coordinate", j}, {"side", "upper"}});
  }
}

Json encode(const Vector &values) {
  Json output = Json::array();
  for (const auto &value : values)
    output.push_back(value.get_str());
  return output;
}

Json sample_certificate(const Model &model, const Json &sample,
                        const Json &plane, bool full) {
  require(sample.at("status") == "unsupported", "original status changed");
  const auto k = sample.at("stage").get<std::size_t>();
  Vector direction(model.initial.size());
  direction.at(plane.at(0).get<std::size_t>()) =
      exact(sample.at("direction").at(0));
  direction.at(plane.at(1).get<std::size_t>()) =
      exact(sample.at("direction").at(1));
  std::vector<Vector> costs(model.controls.size(),
                            Vector(model.controls.front().lower.size()));
  Vector adjoint = direction;
  for (std::size_t j = k; j != 0; --j) {
    costs.at(j - 1) = pullback(model.B, adjoint);
    adjoint = pullback(model.A, adjoint);
  }

  Vector state = model.initial;
  Rational objective = k == 0 ? dot(direction, state) : Rational{};
  Json actions = Json::array(), duals = Json::array(),
       violations = Json::array();
  if (full)
    check_state(model.state_limits.at(0), state, 0, violations);
  for (std::size_t j = 0; j < model.controls.size(); ++j) {
    const auto witness = support(model.controls[j], costs[j],
                                 full ? model.budgets[j] : std::nullopt);
    actions.push_back(encode(witness.controls));
    duals.push_back(witness.multiplier.get_str());
    state = next(model, state, witness.controls, j);
    if (j + 1 == k)
      objective = dot(direction, state);
    if (full)
      check_state(model.state_limits.at(j + 1), state, j + 1, violations);
  }
  return {{"stage", k},
          {"direction", sample.at("direction")},
          {"prior_native_status", sample.at("status")},
          {"status", violations.empty() ? "exact-optimal" : "inconclusive"},
          {"relaxed_support", objective.get_str()},
          {"controls", std::move(actions)},
          {"budget_multipliers", std::move(duals)},
          {"state_violations", std::move(violations)}};
}
} // namespace

int main(int argc, char **argv) try {
  require(argc == 2, "Usage: exact_support archived-model.json");
  std::ifstream stream(argv[1]);
  require(static_cast<bool>(stream), "cannot read source JSON");
  const auto record = Json::parse(stream);
  const auto model = load(record);
  Json output{{"model_id", record.at("model_id")},
              {"schema", "csl.exact-supported-projection/1"}};
  for (const auto *profile : {"intervals_only", "full_history"}) {
    auto items = Json::array();
    for (const auto &sample : record.at(profile).at("samples"))
      items.push_back(
          sample_certificate(model, sample, record.at("plane"),
                             std::string(profile) == "full_history"));
    output[profile] = std::move(items);
  }
  std::cout << output.dump(2) << '\n';
} catch (const std::exception &error) {
  std::cerr << error.what() << '\n';
  return 1;
}
