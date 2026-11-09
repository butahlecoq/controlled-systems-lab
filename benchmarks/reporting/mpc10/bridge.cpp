#include <algorithm>
#include <chrono>
#include <csl/adapters/convex/highs.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <csl/optimization/linear_program.hpp>
#include <csl/synthesis/finite_mixed_branch.hpp>
#include <csl/synthesis/hybrid_path_program.hpp>
#include <csl/synthesis/strategy_b/direct_joint.hpp>
#include <fstream>
#include <iostream>
#include <limits>
#include <nlohmann/json.hpp>
#include <stdexcept>
using namespace csl;
using namespace csl::model;
using namespace csl::synthesis;
using nlohmann::json;
using Clock = std::chrono::steady_clock;
template <class T, class... E> T take(std::variant<T, E...> value) {
  if (!std::holds_alternative<T>(value))
    throw std::runtime_error("public contract rejected construction");
  return std::get<T>(std::move(value));
}
json diagnostics(const Diagnostics &errors) {
  json a = json::array();
  for (const auto &d : errors)
    a.push_back({{"code", static_cast<int>(d.code)},
                 {"field", d.field},
                 {"explanation", d.explanation}});
  return a;
}
template <class V> json refusal(const V &value) {
  json r = {{"status", "public-api-refused"}, {"variant_index", value.index()}};
  if (const auto *d = std::get_if<Diagnostics>(&value))
    r["diagnostics"] = diagnostics(*d);
  if constexpr (requires { std::get_if<OperationStopped>(&value); }) {
    if (const auto *stop = std::get_if<OperationStopped>(&value)) {
      r["stop_reason"] = static_cast<int>(stop->reason);
      r["stop_diagnostics"] = stop->diagnostics;
    }
  }
  return r;
}
std::uint64_t elapsed(Clock::time_point begin) {
  return static_cast<std::uint64_t>(
      std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - begin)
          .count());
}
numeric::MatrixView mat(Matrix m) { return take(numeric::snapshot(m)); }
numeric::VectorView vec(Vector v) { return take(numeric::snapshot_vector(v)); }
SetHandle bounds(const json &b, std::size_t dimension, std::string id) {
  const double lo = b[0], hi = b[1];
  Matrix a{2, dimension, Vector(2 * dimension)};
  a.values[0] = 1;
  a.values[dimension] = -1;
  Matrix e{dimension == 2 ? std::size_t{1} : std::size_t{0}, dimension,
           dimension == 2 ? Vector{0, 1} : Vector{}};
  return take(sets::make_h({{std::move(id)}, dimension, {}},
                           {mat(a), vec({hi, -lo}), mat(e),
                            vec(dimension == 2 ? Vector{0} : Vector{})}))
      .as_handle();
}
SetHandle reset(const json &r, std::string id) {
  double a = r[0], b = r[1];
  return take(sets::make_h({{std::move(id)}, 4, {}},
                           {mat({0, 4, {}}), vec({}),
                            mat({2, 4, {-a, 0, 1, 0, 0, -1, 0, 1}}),
                            vec({b, 0})}))
      .as_handle();
}
json path_json(const HybridPath &p) {
  json modes = json::array(), edges = json::array();
  for (const auto &m : p.modes)
    modes.push_back(m.value);
  for (const auto &e : p.edges)
    edges.push_back(e.value);
  return {{"modes", modes}, {"edges", edges}};
}
json matrix_json(const numeric::MatrixView &m) {
  json a = json::array();
  for (std::size_t i = 0; i < m.rows(); ++i) {
    json row = json::array();
    for (std::size_t j = 0; j < m.cols(); ++j)
      row.push_back(m(i, j));
    a.push_back(row);
  }
  return a;
}
json vector_json(const numeric::VectorView &v) {
  return Vector(v.values().begin(), v.values().end());
}
json interval_json(const Interval &i) {
  return json::array({i.lower ? json(*i.lower) : json(nullptr),
                      i.upper ? json(*i.upper) : json(nullptr)});
}
json program_json(const LinearProgram &p) {
  json variables = json::array(), rows = json::array();
  for (const auto &b : p.variables())
    variables.push_back(interval_json(b));
  for (const auto &b : p.rows())
    rows.push_back(interval_json(b));
  return {{"linear", vector_json(p.objective())},
          {"offset", p.offset()},
          {"matrix", matrix_json(p.constraints())},
          {"variable_bounds", variables},
          {"row_bounds", rows}};
}
json relation_json(const sets::SetData &relation) {
  const auto rep = relation.representation();
  if (const auto *h = std::get_if<sets::HRepresentation>(&rep))
    return {{"inequalities", matrix_json(h->inequalities)},
            {"upper", vector_json(h->upper_bounds)},
            {"equalities", matrix_json(h->equalities)},
            {"values", vector_json(h->equality_values)}};
  return {{"representation_variant", rep.index()}};
}
json result_json(const ProgramResult &r, const LinearProgram &p) {
  json j = {
      {"termination", static_cast<int>(r.termination)},
      {"outcome", static_cast<int>(r.outcome.value)},
      {"raw_diagnostics", r.raw_diagnostics},
      {"assurance",
       "native binary64 observations; complete family not inferred"},
      {"contract_diagnostics", diagnostics(optimization::check_program_result(
                                   r, p, Assurance::numerical))}};
  if (r.primal) {
    j["primal"] = *r.primal;
    auto evaluated = optimization::evaluate_primal(p, *r.primal, {1e-8, 1e-8},
                                                   {{"mpc10.primal"}, "1"});
    if (auto *e = std::get_if<optimization::PrimalEvaluation>(&evaluated))
      j["primal_check"] = {
          {"objective", e->objective},
          {"row_violation", e->residuals.rows.violation},
          {"variable_violation", e->residuals.variables.violation}};
  }
  j["lower_bound"] =
      r.objective.lower ? json(r.objective.lower->value) : json(nullptr);
  j["upper_bound"] =
      r.objective.upper ? json(r.objective.upper->value) : json(nullptr);
  return j;
}
template <class Port>
registry::PreparedProvider<Port>
provider(registry::Registration<Port> registration) {
  registry::Registry<Port> registry;
  auto id = registration.identity.id;
  if (registry.add(std::move(registration)))
    throw std::runtime_error("registration failed");
  registry::Requirements requirements;
  requirements.output.representation = {"csl.program-result.v1"};
  return take(registry::prepare_provider(
      registry::select_provider(registry, {id, {}}, requirements)));
}
std::pair<HybridSystem, HybridRequest> hybrid(const json &s) {
  const auto T = s.at("horizon").get<std::size_t>();
  std::vector<HybridMode> modes;
  std::vector<HybridModeObjective> objectives;
  for (const auto &m : s.at("modes")) {
    std::string id = m.at("id");
    double a = m.at("flow_a"), b = m.at("flow_offset");
    HybridMode mode{{id}, 2, 1, {"x", "y"}, {"u"}, LinearStage{}, {}, {}};
    mode.flow =
        LinearStage{{2, 2, {a, 0, 0, 1}}, {2, 1, {1, 0}}, {2, 0, {}}, {b, 0}};
    for (std::size_t k = 0; k < T; ++k)
      mode.control_sets.push_back(bounds(m.at("control_bounds"), 1, id + ".u"));
    for (const auto &inv : m.at("invariants"))
      mode.invariants.push_back(bounds(inv, 2, id + ".invariant"));
    modes.push_back(std::move(mode));
    const auto allowed =
        s.at("allowed_terminal_modes").get<std::vector<std::string>>();
    if (std::find(allowed.begin(), allowed.end(), id) != allowed.end())
      objectives.push_back(
          {{id},
           LinearTerminal{{m.at("terminal_linear")[0].get<double>(), 0},
                          m.at("terminal_linear")[1]},
           "terminal x",
           "synthetic units"});
  }
  std::vector<HybridTransitionEdge> edges;
  for (const auto &e : s.at("edges")) {
    std::string id = e.at("id");
    HybridTransitionEdge edge{{id}, {e.at("source")}, {e.at("target")}, {}, {}};
    for (const auto &g : e.at("guards")) {
      edge.guards.push_back(bounds(g, 2, id + ".guard"));
      edge.reset_relations.push_back(reset(e.at("reset"), id + ".reset"));
    }
    edges.push_back(std::move(edge));
  }
  std::vector<HybridModeId> terminals;
  for (const auto &t : s.at("allowed_terminal_modes"))
    terminals.push_back({t});
  return {{T, std::move(modes), std::move(edges)},
          {{{s.at("initial_mode")}, {s.at("initial_x"), s.at("initial_y")}},
           std::move(terminals),
           std::move(objectives)}};
}
int main(int argc, char **argv) try {
  if (argc != 2)
    throw std::runtime_error("usage: csl_mpc10 fixture.json");
  std::ifstream stream(argv[1]);
  const auto s = json::parse(stream);
  if (s.at("schema") != "csl.mpc10.fixture/1" || s.at("dimension") != 2 ||
      s.at("initial_y") != 0 || s.at("horizon").get<std::size_t>() > 3)
    throw std::runtime_error("unsupported authored MPC10 profile");
  json out = {{"schema", "csl.mpc10.native/1"},
              {"fixture_id", s.at("id")},
              {"fixture_sha256", s.at("fixture_sha256")}};
  if (s.contains("external_unsupported")) {
    out["status"] = "external-encoding-unsupported";
    out["reason"] = s.at("external_unsupported");
    std::cout << out.dump() << '\n';
    return 0;
  }
  const auto started = Clock::now();
  auto lp = provider(take(adapters::lp::make_highs_registration()));
  auto convex = provider(take(adapters::convex::make_highs_registration()));
  out["provider_setup_ns"] = elapsed(started);
  const auto T = s.at("horizon").get<std::size_t>();
  const auto max = s.at("max_branches").get<std::size_t>();
  ExecutionContext context;
  context.resources =
      std::make_shared<const ResourcePolicy>(ResourcePolicy{1, 1, 1, {}});
  context.numerical = {1e-8, 1e-8};
  context.deadline = Clock::now() + std::chrono::seconds(60);
  std::stop_source cancellation;
  if (s.at("cancel").get<bool>())
    cancellation.request_stop();
  context.cancellation = cancellation.get_token();
  json branches = json::array();
  if (s.at("product") == "hybrid") {
    auto [system, request] = hybrid(s);
    auto begin = Clock::now();
    const auto enumerated = model::enumerate_hybrid_paths(
        system, request.initial.mode, request.allowed_terminal_modes, {8, max},
        context.cancellation);
    out["path_enumeration_probe_ns"] = elapsed(begin);
    out["path_enumeration_probe_variant"] = enumerated.index();
    begin = Clock::now();
    auto built = build_hybrid_portfolio_programs(system, request, {s.at("id")},
                                                 {8, max}, {256, 4096, 1048576},
                                                 {}, context.cancellation);
    out["enumeration_and_formulation_ns"] = elapsed(begin);
    if (!std::holds_alternative<std::vector<HybridPathProgram>>(built)) {
      out["construction"] = refusal(built);
      out["status"] = "construction-refused";
    } else {
      auto programs =
          std::get<std::vector<HybridPathProgram>>(std::move(built));
      begin = Clock::now();
      auto execution =
          execute_hybrid_path_programs(programs, lp, convex, context);
      out["solve_portfolio_ns"] = elapsed(begin);
      out["all_supplied_branches_completed"] =
          execution.all_supplied_branches_completed;
      for (std::size_t i = 0; i < programs.size(); ++i) {
        const auto &p = programs[i];
        const auto &b = execution.branches.at(i);
        const auto &linear = std::get<LinearProgram>(p.program);
        json record = {{"path", path_json(p.path)},
                       {"program", program_json(linear)},
                       {"joint_relation", relation_json(p.joint_relation)},
                       {"diagnostics", diagnostics(b.diagnostics)}};
        if (b.result)
          record["result"] = result_json(*b.result, linear);
        if (b.provider_elapsed_wall_nanoseconds)
          record["provider_elapsed_ns"] = *b.provider_elapsed_wall_nanoseconds;
        if (b.provider_invocation)
          record["provider_invocation_ns"] =
              b.provider_invocation->elapsed_wall_nanoseconds;
        branches.push_back(record);
      }
      begin = Clock::now();
      auto bound_analysis = assemble_hybrid_portfolio_optimal_face_candidates(
          programs, execution, {1e-8, 1e-8});
      out["native_bound_comparison_variant"] = bound_analysis.index();
      // These are candidates selected by numerical primal values. Only the
      // independent public exact verifier may establish global coverage.
      double best = std::numeric_limits<double>::infinity();
      std::vector<std::pair<std::size_t, double>> values;
      for (std::size_t i = 0; i < programs.size(); ++i) {
        const auto &branch = execution.branches.at(i);
        if (!branch.result || branch.outcome != MathematicalOutcome::optimal ||
            !branch.result->primal)
          continue;
        auto evaluated = optimization::evaluate_primal(
            std::get<LinearProgram>(programs[i].program),
            *branch.result->primal, {1e-8, 1e-8},
            {{"mpc10.candidate-ranking"}, "1"});
        if (const auto *v =
                std::get_if<optimization::PrimalEvaluation>(&evaluated)) {
          best = std::min(best, v->objective);
          values.push_back({i, v->objective});
        }
      }
      std::vector<HybridPathOptimalFaceCandidate> candidates;
      for (const auto &[i, value] : values)
        if (value <= best + 1e-8) {
          auto face = build_hybrid_path_optimal_face_candidate(
              programs[i], *execution.branches[i].result, {1e-8, 1e-8});
          if (auto *candidate =
                  std::get_if<HybridPathOptimalFaceCandidate>(&face))
            candidates.push_back(std::move(*candidate));
          else
            out["candidate_construction_refusal"] = refusal(face);
        }
      json face_records = json::array();
      for (const auto &face : candidates)
        face_records.push_back(
            {{"path", path_json(face.path)},
             {"optimal_relation", relation_json(face.relation)},
             {"anchor", face.anchor}});
      out["candidate_optimal_faces"] = face_records;
      ExactLinearHHybridFamilyVerifier verifier;
      auto verified = verify_hybrid_portfolio_family(
          verifier, system, request, programs, candidates, {8, max},
          HybridVerifierInvocation{context});
      if (const auto *r =
              std::get_if<HybridFamilyVerificationReport>(&verified)) {
        json reports = json::array();
        for (const auto &branch : r->branches)
          reports.push_back(
              {{"path", path_json(branch.path)},
               {"feasibility", static_cast<int>(branch.feasibility)},
               {"optimality", static_cast<int>(branch.objective_optimality)},
               {"coverage", static_cast<int>(branch.continuous_coverage)},
               {"diagnostics", diagnostics(branch.diagnostics)}});
        out["family_verification"] = {
            {"verifier", r->verifier_id},
            {"version", r->verifier_version},
            {"global_optimality",
             static_cast<int>(r->global_objective_optimality)},
            {"continuous_coverage",
             static_cast<int>(r->complete_family_coverage)},
            {"branches", reports}};
      } else
        out["family_verification"] = refusal(verified);
      out["family_check_ns"] = elapsed(begin);
      out["status"] = "complete";
    }
  } else {
    const bool finite = s.at("product") == "finite";
    const std::size_t continuous = finite ? 0 : 1;
    FiniteDomain discrete{1, {}};
    for (const auto &a : s.at("catalogue"))
      discrete.catalogue.push_back({a});
    const auto history_begin = Clock::now();
    auto enumeration = take(FiniteActionHistoryCursor::prepare(discrete, T));
    auto histories = enumeration.take_prefix(max);
    out["history_enumeration_ns"] = elapsed(history_begin);
    out["history_enumeration_complete"] = histories.complete;
    out["finite_embedding"] = finite ? "R^0 x finite catalogue; identical "
                                       "histories and physical controls"
                                     : "continuous x finite catalogue";
    Matrix B{2, continuous + 1, Vector(2 * (continuous + 1), 0)};
    for (std::size_t j = 0; j < continuous + 1; ++j)
      B.values[j] = 1;
    std::vector<double> times;
    for (std::size_t k = 0; k <= T; ++k)
      times.push_back(static_cast<double>(k));
    ContinuousDomain continuous_domain;
    for (std::size_t k = 0; k < T; ++k)
      continuous_domain.stages.push_back(
          finite ? AdmissibleSet{UniversalSet{0}}
                 : AdmissibleSet{bounds(s.at("continuous_bounds"), 1, "u")});
    std::vector<AdmissibleSet> states;
    for (const auto &b : s.at("state_bounds"))
      states.push_back(bounds(b, 2, "state"));
    Problem source{
        {s.at("id")},
        std::make_shared<const SystemModel>(SystemModel{
            {{2, continuous + 1, 0},
             TimeDomain::discrete,
             LinearStage{{2, 2, {1, 0, 0, 1}}, B, {2, 0, {}}, {0, 0}}},
            {}}),
        times,
        KnownInitial{{s.at("initial_x"), s.at("initial_y")}},
        MixedDomain{std::move(continuous_domain), discrete},
        std::move(states),
        {},
        {},
        InformationPattern::nominal_open_loop,
        LinearTerminal{{s.at("terminal_linear")[0], 0},
                       s.at("terminal_linear")[1]}};
    auto resolved = take(problem::resolve(
        source,
        {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}}));
    std::uint64_t formulation = 0, solve = 0;
    for (const auto &history : histories.histories) {
      auto begin = Clock::now();
      auto fixed = prepare_finite_mixed_branch(resolved, history);
      json record = {{"path", {{"actions", history.catalogue_indices}}}};
      if (auto *branch = std::get_if<FiniteMixedBranchProblem>(&fixed)) {
        auto r = take(problem::resolve(
            branch->problem,
            {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}}));
        FamilyRequest family{};
        family.profile = "nominal_open_loop";
        family.objective = r.identity();
        family.representation = {"csl.polyhedron.h"};
        auto built = strategy_b::build_joint_program(r, family);
        formulation += elapsed(begin);
        if (auto *program = std::get_if<strategy_b::JointProgram>(&built)) {
          const auto &linear = std::get<LinearProgram>(program->program);
          record["program"] = program_json(linear);
          begin = Clock::now();
          auto prepared = lp.prepare(linear);
          if (auto *pipeline =
                  std::get_if<registry::PreparedPipeline<registry::LPPort>>(
                      &prepared)) {
            auto [workspace] = pipeline->create();
            auto result = workspace->run(context);
            if (auto *actual = std::get_if<ProgramResult>(&result))
              record["result"] = result_json(*actual, linear);
            else
              record["provider_unsupported"] = true;
          } else
            record["provider_rejected"] = true;
          solve += elapsed(begin);
        } else
          record["construction"] = refusal(built);
      } else
        record["branch_specialization_diagnostics"] =
            diagnostics(std::get<Diagnostics>(fixed));
      branches.push_back(record);
    }
    out["enumeration_and_formulation_ns"] = formulation;
    out["solve_portfolio_ns"] = solve;
    out["status"] =
        histories.complete ? "complete" : "incomplete-history-prefix";
  }
  out["branches"] = branches;
  out["total_ns"] = elapsed(started);
  std::cout << out.dump() << '\n';
  return 0;
} catch (const std::exception &error) {
  std::cerr << error.what() << '\n';
  return 1;
}
