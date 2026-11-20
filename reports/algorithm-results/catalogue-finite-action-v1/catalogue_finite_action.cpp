#include <csl/model/discrete_catalogue.hpp>
#include <csl/optimization/finite_action_nominal.hpp>

#include <nlohmann/json.hpp>

#include <algorithm>
#include <array>
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <utility>

namespace {
using namespace csl;
using namespace csl::optimization;
namespace catalogue = csl::model::catalogue;
using Json = nlohmann::json;

constexpr std::size_t horizon = 2;
constexpr FiniteActionNominalLimits limits{9, 64, 16'384, 512, 0};

template <class T, class... Errors>
T require(std::variant<T, Errors...> value, const char *explanation) {
  if (auto *accepted = std::get_if<T>(&value)) {
    return std::move(*accepted);
  }
  throw std::runtime_error(explanation);
}

Json refusal(const Unsupported &error) {
  Json diagnostics = Json::array();
  for (const auto &diagnostic : error.diagnostics) {
    diagnostics.push_back(
        {{"field", diagnostic.field}, {"message", diagnostic.explanation}});
  }
  return {{"status", "unsupported"}, {"diagnostics", std::move(diagnostics)}};
}

Json stop(const OperationStopped &stopped) {
  constexpr std::array reasons{"cancelled", "deadline", "resource-limit",
                               "numerical-failure"};
  return {{"status", "stopped"},
          {"reason", reasons.at(static_cast<std::size_t>(stopped.reason))},
          {"detail", stopped.diagnostics}};
}

const char *score_kind(NominalScoreKind kind) {
  constexpr std::array kinds{"deterministic", "numerical-enclosure",
                             "numerical-enclosure-plus-running"};
  return kinds.at(static_cast<std::size_t>(kind));
}

Json encode_attempt(const NominalPlanAttempt &attempt) {
  return std::visit(
      [](const auto &row) -> Json {
        using T = std::decay_t<decltype(row)>;
        Json result;
        if constexpr (std::is_same_v<T, NominalPlanScored>) {
          result = {{"status", "scored"},
                    {"score", row.candidate_score},
                    {"terminal_score", row.terminal_score},
                    {"running_cost", row.exact_running_cost},
                    {"score_kind", score_kind(row.score_kind)}};
        } else if constexpr (std::is_same_v<T, NominalPlanRejected>) {
          result = {{"status", "rejected"},
                    {"stage", row.stage},
                    {"state", row.violating_state}};
        } else if constexpr (std::is_same_v<T, NominalPlanUnscored>) {
          result = refusal(row.reason);
        } else {
          result = stop(row.reason);
        }
        result["action_indices"] = row.action_indices;
        return result;
      },
      attempt);
}

Json solve(const FiniteActionNominalRequest &request,
           NominalRepresentation representation) {
  auto outcome = finite_action_nominal_profile(request, limits, representation);
  if (const auto *error = std::get_if<Unsupported>(&outcome)) {
    return refusal(*error);
  }
  if (const auto *stopped = std::get_if<OperationStopped>(&outcome)) {
    return stop(*stopped);
  }
  const auto &track = std::get<FiniteActionNominalResult>(outcome).tracks.at(0);
  if (track.representation != representation) {
    throw std::runtime_error("SDK returned a different representation");
  }
  return std::visit(
      [](const auto &row) -> Json {
        using T = std::decay_t<decltype(row)>;
        Json result;
        if constexpr (std::is_same_v<T, NominalTrackSelected>) {
          const auto &replay = row.replay;
          result = {{"status", "selected"},
                    {"selected_attempt", row.selected_attempt},
                    {"score", row.candidate_score},
                    {"score_kind", score_kind(row.score_kind)},
                    {"states", replay.states},
                    {"controls", replay.controls},
                    {"disturbances", replay.disturbances},
                    {"terminal_cost", replay.terminal_objective},
                    {"total_cost", replay.total_objective}};
        } else if constexpr (std::is_same_v<T, NominalTrackUnsupported>) {
          result = refusal(row.reason);
        } else if constexpr (std::is_same_v<T, NominalTrackStopped>) {
          result = stop(row.reason);
        } else {
          result = {{"status", "no-scored-candidate"}};
        }
        constexpr std::array coverages{"complete", "incomplete", "stopped"};
        result["coverage"] =
            coverages.at(static_cast<std::size_t>(row.coverage));
        result["attempts"] = Json::array();
        for (const auto &attempt : row.attempts) {
          result["attempts"].push_back(encode_attempt(attempt));
        }
        return result;
      },
      track.outcome);
}

Json encode_matrix(const Matrix &matrix) {
  return {{"rows", matrix.rows},
          {"columns", matrix.cols},
          {"row_major", matrix.values}};
}

Json run_model(const catalogue::DiscreteModelInfo &info) {
  const auto model = require(catalogue::make_discrete_model(info.id),
                             "missing catalogue model");
  const auto n = model.initial_state.size();
  const auto m = model.coefficients.B.cols;
  const auto q = model.coefficients.E.cols;
  const double dt = model.time_step.value;
  const auto authored = model.system_model();
  const auto system =
      require(model::snapshot(authored, Vector{0, dt, 2 * dt}), "bad dynamics");
  const auto tail = require(model::snapshot(authored, Vector{dt, 2 * dt}),
                            "bad tail dynamics");
  const auto domain = require(
      sets::make_universal({{"finite-action/world"}, n, {}}), "bad domain");

  const auto external = model.nominal_external.value_or(Vector(q, 0.0));
  FiniteDomain actions{m, std::vector<Vector>(3, Vector(m, 0.0))};
  actions.catalogue.at(1).at(0) = -0.1;
  actions.catalogue.at(2).at(0) = 0.1;
  Matrix hessian{n, n, Vector(n * n, 0.0)};
  Vector linear(n, 0.0);
  double constant = 0;
  for (std::size_t i = 0; i < n; ++i) {
    const double x = model.initial_state[i];
    const double s = std::max(1.0, std::abs(x));
    const double weight = 1.0 / (s * s);
    hessian.values[i * n + i] = 2 * weight;
    linear[i] = -2 * weight * x;
    constant += weight * x * x;
  }
  const auto objective = require(
      snapshot(QuadraticTerminal{hessian, linear, constant}), "bad objective");
  const std::string id(info.id);
  const std::array profiles{
      std::pair{"polytope", NominalRepresentation::exact_polytope},
      std::pair{"box", NominalRepresentation::box},
      std::pair{"zonotope", NominalRepresentation::zonotope},
      std::pair{"parallelotope", NominalRepresentation::parallelotope},
      std::pair{"ellipsoid", NominalRepresentation::ellipsoid},
  };
  Json outcomes = Json::object();
  for (const auto &[name, representation] : profiles) {
    const std::string request_id = id + "/finite-action-hold/1/" + name;
    const FiniteActionNominalRequest first{{id},
                                           {request_id + "/0"},
                                           system,
                                           model.initial_state,
                                           actions,
                                           {external, external},
                                           {domain, domain, domain},
                                           objective};
    auto open_loop = solve(first, representation);
    Json feedback = {{"status", "initial-solve-unavailable"},
                     {"applied_controls", Json::array()},
                     {"observed_states", Json::array({model.initial_state})}};
    if (open_loop.at("status") == "selected") {
      const auto first_action = open_loop.at("controls").at(0).get<Vector>();
      const auto observed =
          require(system.step({0}, model.initial_state, first_action, external),
                  "first plant update failed");
      const FiniteActionNominalRequest second{
          {id},       {request_id + "/1"}, tail,     observed, actions,
          {external}, {domain, domain},    objective};
      auto replan = solve(second, representation);
      feedback["status"] = replan.at("status");
      feedback["applied_controls"].push_back(first_action);
      feedback["observed_states"].push_back(observed);
      if (replan.at("status") == "selected") {
        const auto action = replan.at("controls").at(0).get<Vector>();
        const auto endpoint =
            require(system.step({1}, observed, action, external),
                    "second plant update failed");
        feedback["applied_controls"].push_back(action);
        feedback["observed_states"].push_back(endpoint);
        feedback["terminal_cost"] = replan.at("terminal_cost");
      }
      feedback["replan"] = std::move(replan);
    }
    outcomes[name] = {{"open_loop", std::move(open_loop)},
                      {"feedback", std::move(feedback)}};
  }
  const auto &step = model.coefficients;
  return {{"model_id", id},
          {"model_title", info.title},
          {"source_qualification", info.source.qualification},
          {"source_sha256", info.source.sha256},
          {"dt", dt},
          {"dt_unit", model.time_step.unit},
          {"horizon", horizon},
          {"task_profile", "authored-finite-action-hold/1"},
          {"A", encode_matrix(step.A)},
          {"B", encode_matrix(step.B)},
          {"E", encode_matrix(step.E)},
          {"c", step.offset},
          {"x0", model.initial_state},
          {"actions", actions.catalogue},
          {"external", external},
          {"supplied_nominal_external", model.nominal_external.has_value()},
          {"objective",
           {{"Q", encode_matrix(hessian)},
            {"linear", linear},
            {"constant", constant}}},
          {"outcomes", std::move(outcomes)}};
}
} // namespace

int main(int argc, char **argv) {
  try {
    if (argc != 2)
      throw std::invalid_argument("one catalogue model ID is required");
    for (const auto &info : catalogue::discrete_models()) {
      if (info.id == argv[1]) {
        std::cout << run_model(info).dump(2) << '\n';
        return 0;
      }
    }
    throw std::invalid_argument("unknown catalogue model ID");
  } catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
