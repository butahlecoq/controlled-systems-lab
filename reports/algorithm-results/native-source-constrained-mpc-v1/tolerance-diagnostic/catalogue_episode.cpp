#include <csl/adapters/convex/highs.hpp>
#include <csl/controllers/discrete_mpc.hpp>
#include <csl/registry/registry.hpp>

#include <nlohmann/json.hpp>

#include <algorithm>
#include <cmath>
#include <iostream>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string>
#include <variant>

namespace {
using namespace csl;
using namespace csl::controllers;
using namespace csl::optimization;
using Json = nlohmann::json;
constexpr std::size_t horizon = 3;

Json diagnostics(const Diagnostics &values) {
  auto result = Json::array();
  for (const auto &value : values)
    result.push_back(
        {{"field", value.field}, {"explanation", value.explanation}});
  return result;
}

Json optional_scalar(const std::optional<double> &value) {
  return value ? Json(*value) : Json(nullptr);
}

Json matrix(const Matrix &value) {
  return {{"rows", value.rows}, {"cols", value.cols}, {"values", value.values}};
}

Json intervals(const std::vector<Interval> &values) {
  auto result = Json::array();
  for (const auto &value : values)
    result.push_back(Json::array(
        {optional_scalar(value.lower), optional_scalar(value.upper)}));
  return result;
}

Json constraints(const NominalMpcTask &task) {
  auto result = Json{{"state", Json::array()},
                     {"control", Json::array()},
                     {"stage", Json::array()},
                     {"positive_part", Json::array()},
                     {"terminal", Json::array()}};
  for (const auto &bounds : task.state_bounds)
    result["state"].push_back(intervals(bounds));
  for (const auto &bounds : task.control_bounds)
    result["control"].push_back(intervals(bounds));
  for (const auto &rows : task.stage_constraints)
    result["stage"].push_back({{"state", matrix(rows.state_map)},
                               {"control", matrix(rows.control_map)},
                               {"external", matrix(rows.external_map)},
                               {"bounds", intervals(rows.bounds)}});
  for (const auto &budgets : task.control_positive_part_budgets) {
    auto entries = Json::array();
    for (const auto &budget : budgets)
      entries.push_back(
          {{"indices", budget.control_indices}, {"upper", budget.upper_bound}});
    result["positive_part"].push_back(std::move(entries));
  }
  for (const auto &row : task.terminal_state_constraints)
    result["terminal"].push_back(
        {{"state", matrix(row.state_map)}, {"bounds", intervals(row.bounds)}});
  return result;
}

struct Fixture {
  AuthoredTaskChoices choices;
  Vector target, state_weights, control_weights;
};

Fixture make_fixture(const model::catalogue::DiscreteModelData &model, int id) {
  const auto nx = model.coefficients.A.rows;
  const auto nu = model.coefficients.B.cols;
  const auto nw = model.coefficients.E.cols;
  Fixture fixture;
  auto &choices = fixture.choices;
  const std::string prefix =
      "catalogue-model-" + std::to_string(id) + "-matched-three";
  choices.problem_id = {prefix + "/1"};
  choices.program_id = {prefix + "-nominal-qp/1"};
  choices.profile_id = prefix + "/1";
  choices.objective_id = "authored-scale-relative-quadratic/1";
  choices.horizon_id = "authored-fixed-three-transitions/1";
  choices.final_stage = horizon;
  fixture.target = model.initial_state;
  fixture.target[0] += .1 * std::max(1., std::abs(fixture.target[0]));
  fixture.control_weights.assign(nu, .05);
  Matrix q{nx, nx, Vector(nx * nx, 0.)};
  Matrix r{nu, nu, Vector(nu * nu, 0.)};
  Vector linear(nx);
  double offset = 0.;
  for (std::size_t i = 0; i < nx; ++i) {
    const double scale = std::max(1., std::abs(model.initial_state[i]));
    const double weight = 1. / (scale * scale);
    fixture.state_weights.push_back(weight);
    q.values[i * nx + i] = weight;
    linear[i] = -weight * fixture.target[i];
    offset += .5 * weight * fixture.target[i] * fixture.target[i];
  }
  for (std::size_t i = 0; i < nu; ++i)
    r.values[i * nu + i] = fixture.control_weights[i];
  choices.running_costs.assign(horizon, {q, Matrix{nx, nu, Vector(nx * nu, 0.)},
                                         r, linear, Vector(nu, 0.), offset});
  for (std::size_t i = 0; i < nx; ++i) {
    q.values[i * nx + i] *= 2.;
    linear[i] *= 2.;
  }
  choices.terminal_cost = {q, linear, 2. * offset};
  const auto external = model.nominal_external.value_or(Vector(nw, 0.));
  choices.forecast_external.assign(horizon, external);
  choices.replay_external = choices.forecast_external;
  choices.forecast_id = model.nominal_external ? "catalogue-nominal-external/1"
                                               : "authored-zero-external/1";
  choices.replay_id = "forecast-matched-replay/1";
  if (id == 4 || id == 9 || id == 10)
    choices.domain_choice = DomainChoice::explicit_continuous_relaxation;
  if (id == 3 || id == 11 || id == 18 || id == 31)
    choices.arrival_availability = ArrivalAvailability::before_decision;
  if (id == 24 || id == 25 || id == 27) {
    choices.domain_choice = DomainChoice::authored_continuous_domain;
    choices.authored_state_bounds = std::vector<Interval>(nx);
    for (std::size_t i = 0; i < nx; ++i) {
      const double limit = 10. * std::max(1., std::abs(model.initial_state[i]));
      choices.authored_state_bounds->at(i) = {-limit, limit};
    }
    choices.authored_control_bounds =
        std::vector<Interval>(nu, Interval{-1., 1.});
  }
  return fixture;
}

Json episode(const MpcEpisodeEvidence &value) {
  const char *status = "unknown";
  switch (value.stop) {
  case EpisodeStop::completed:
    status = "complete";
    break;
  case EpisodeStop::compilation_rejected:
    status = "compilation-rejected";
    break;
  case EpisodeStop::solver_unsupported:
    status = "solver-unsupported";
    break;
  case EpisodeStop::solver_not_optimal:
    status = "solver-not-optimal";
    break;
  case EpisodeStop::simulation_stopped:
    status = "simulation-stopped";
    break;
  }
  auto decisions = Json::array();
  for (const auto &decision : value.decisions) {
    Json stage{{"attempted", decision.attempt.has_value()},
               {"solver_receipt", decision.solve.has_value()},
               {"observed_state", decision.observed_state},
               {"predicted_states", decision.predicted_states},
               {"predicted_controls", decision.predicted_controls},
               {"replay_diagnostics",
                diagnostics(decision.replay_constraint_diagnostics)}};
    if (decision.solve) {
      if (const auto *result = std::get_if<ProgramResult>(&*decision.solve)) {
        stage["termination"] = static_cast<int>(result->termination);
        stage["raw_diagnostics"] = result->raw_diagnostics;
      } else if (const auto *errors =
                     std::get_if<Diagnostics>(&*decision.solve)) {
        stage["solve_diagnostics"] = diagnostics(*errors);
      } else if (const auto *unsupported =
                     std::get_if<Unsupported>(&*decision.solve)) {
        stage["solve_diagnostics"] = diagnostics(unsupported->diagnostics);
      } else if (const auto *stopped =
                     std::get_if<OperationStopped>(&*decision.solve)) {
        stage["raw_diagnostics"] = stopped->diagnostics;
      }
    }
    decisions.push_back(std::move(stage));
  }
  return {{"status", status},
          {"states", value.realized_states},
          {"controls", value.applied_controls},
          {"realized_cost", optional_scalar(value.realized_objective)},
          {"terminal_diagnostics",
           diagnostics(value.terminal_constraint_diagnostics)},
          {"decisions", std::move(decisions)}};
}

Json run_model(int id, double tolerance) {
  const auto key = "catalogue-2026/model-" + std::to_string(id) + "/1";
  const auto data = model::catalogue::make_discrete_model(key);
  if (const auto *errors = std::get_if<Diagnostics>(&data))
    return {{"model_id", key},
            {"status", "catalogue-rejected"},
            {"diagnostics", diagnostics(*errors)}};
  const auto &model = std::get<model::catalogue::DiscreteModelData>(data);
  const auto fixture = make_fixture(model, id);
  const auto admitted = make_source_task_profile(key, fixture.choices);
  if (const auto *errors = std::get_if<Diagnostics>(&admitted))
    return {{"model_id", key},
            {"status", "task-rejected"},
            {"diagnostics", diagnostics(*errors)}};
  if (const auto *deferred = std::get_if<DeferredTask>(&admitted))
    return {{"model_id", key},
            {"status", "deferred"},
            {"reason", deferred->reason}};
  const auto &task = std::get<NominalMpcTask>(admitted);
  const auto probe =
      compile_mpc_decision(task, StageIndex{0}, task.initial.point);
  if (const auto *errors = std::get_if<Diagnostics>(&probe))
    return {{"model_id", key},
            {"status", "probe-rejected"},
            {"diagnostics", diagnostics(*errors)}};
  const auto &program =
      std::get<CompiledNominalQuadraticHistory>(probe).program;
  const auto provider = adapters::convex::make_highs_registration();
  const auto &registration =
      std::get<registry::Registration<registry::ConvexPort>>(provider);
  const ExecutionContext context{
      std::make_shared<const ResourcePolicy>(ResourcePolicy{1, 1, 1, {}}),
      {},
      {},
      {tolerance, tolerance},
      "catalogue-matched-three"};
  auto open_workspace = registration.factory(program);
  auto feedback_workspace = registration.factory(program);
  if (!open_workspace || !feedback_workspace)
    throw std::runtime_error("HiGHS workspace construction failed");
  return {
      {"model_id", key},
      {"title", model.info.title},
      {"status", "attempted"},
      {"profile", task.provenance.profile_id},
      {"domain", task.provenance.domain_choice},
      {"forecast", task.provenance.forecast_id},
      {"source", task.provenance.source_reference},
      {"backend", registration.identity.id.value},
      {"backend_version", registration.identity.version},
      {"solution_tolerances", Json::array({tolerance, tolerance})},
      {"horizon", horizon},
      {"A", matrix(model.coefficients.A)},
      {"B", matrix(model.coefficients.B)},
      {"G", matrix(model.coefficients.E)},
      {"offset", model.coefficients.offset},
      {"initial", task.initial.point},
      {"target", fixture.target},
      {"state_weights", fixture.state_weights},
      {"control_weights", fixture.control_weights},
      {"external", task.replay_external},
      {"constraints", constraints(task)},
      {"open_loop",
       episode(execute_nominal_episode(task, EpisodePolicy::nominal_open_loop,
                                       *open_workspace, context))},
      {"closed_loop",
       episode(execute_nominal_episode(task, EpisodePolicy::observed_state_mpc,
                                       *feedback_workspace, context))}};
}
} // namespace

int main(int argc, char **argv) try {
  if (argc != 2 && argc != 3)
    throw std::runtime_error(
        "Usage: catalogue_episode MODEL_NUMBER [TOLERANCE]");
  const double tolerance = argc == 2 ? 1e-8 : std::stod(argv[2]);
  if (!std::isfinite(tolerance) || tolerance <= 0.)
    throw std::runtime_error("Tolerance must be positive and finite");
  std::cout << run_model(std::stoi(argv[1]), tolerance).dump() << '\n';
  return 0;
} catch (const std::exception &error) {
  std::cerr << error.what() << '\n';
  return 1;
}
