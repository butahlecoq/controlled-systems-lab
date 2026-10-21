#include <csl/adapters/convex/highs.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <csl/synthesis/hybrid_path_program.hpp>

#include <chrono>
#include <cmath>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <utility>
#include <variant>
#include <vector>

namespace {
using namespace csl;
using namespace csl::model;
using Clock = std::chrono::steady_clock;

template <class T, class... U> T take(std::variant<T, U...> value) {
  if (!std::holds_alternative<T>(value))
    throw std::runtime_error("EXT-07 two-parameter fixture was rejected");
  return std::get<T>(std::move(value));
}

numeric::MatrixView matrix(Matrix value) {
  return take(numeric::snapshot(std::move(value)));
}
numeric::VectorView vector(Vector value) {
  return take(numeric::snapshot_vector(std::move(value)));
}

SetHandle interval(std::string id, double lower, double upper) {
  auto data = take(sets::make_h(
      {{std::move(id)}, 1, {"x"}},
      {matrix({2, 1, {1, -1}}), vector({upper, -lower}), matrix({0, 1, {}}),
       vector({})}));
  return data.as_handle();
}

SetHandle identity_reset(std::string id) {
  auto data = take(sets::make_h(
      {{std::move(id)}, 2, {"pre", "post"}},
      {matrix({0, 2, {}}), vector({}), matrix({1, 2, {1, -1}}), vector({0})}));
  return data.as_handle();
}

SetHandle universal_reset(std::string id) {
  auto data = take(sets::make_h({{std::move(id)}, 2, {"pre", "post"}},
                                {matrix({0, 2, {}}), vector({}),
                                 matrix({0, 2, {}}), vector({})}));
  return data.as_handle();
}

std::pair<HybridSystem, HybridRequest> fixture() {
  const LinearStage first{Matrix{1, 1, {0}}, Matrix{1, 1, {1}},
                                 Matrix{1, 0, {}}, Vector{0}};
  const LinearStage second{Matrix{1, 1, {1}}, Matrix{1, 1, {0}},
                                  Matrix{1, 0, {}}, Vector{0}};
  HybridMode source{{"source"}, 1, 1, {"x"}, {"u"}};
  source.flow = std::vector<LinearStage>{first, second};
  source.control_sets = {interval("control-u0", 0, 1), Singleton{{0}}};
  source.invariants = {UniversalSet{1}, UniversalSet{1}, UniversalSet{1}};

  HybridMode middle{{"middle"}, 1, 1, {"x"}, {"u"}};
  middle.flow = std::vector<LinearStage>{first, second};
  middle.control_sets = {Singleton{{0}}, interval("control-u1", 0, 1)};
  middle.invariants = {UniversalSet{1}, UniversalSet{1}, UniversalSet{1}};

  HybridMode terminal{{"terminal"}, 1, 1, {"x"}, {"u"}};
  terminal.flow = std::vector<LinearStage>{first, second};
  terminal.control_sets = {Singleton{{0}}, Singleton{{0}}};
  terminal.invariants = {UniversalSet{1}, UniversalSet{1}, UniversalSet{1}};

  const auto id0 = identity_reset("reset-0");
  const auto id1 = identity_reset("reset-1");
  HybridSystem system{
      2,
      {source, middle, terminal},
      {{{"enter-half"}, {"source"}, {"middle"},
        {interval("guard-half", 0, 0.5), UniversalSet{1}},
        {id0, universal_reset("unused-half-reset")}},
       {{"enter-full"}, {"source"}, {"middle"},
        {UniversalSet{1}, UniversalSet{1}},
        {id0, universal_reset("unused-full-reset")}},
       {{"finish"}, {"middle"}, {"terminal"},
        {UniversalSet{1}, UniversalSet{1}},
        {universal_reset("unused-terminal-reset"), id1}}}};
  HybridRequest request{
      {{"source"}, {0}}, {{"terminal"}},
      {{{"terminal"}, LinearTerminal{{1}, 0}, "terminal state", "units"}}};
  return {std::move(system), std::move(request)};
}

registry::PreparedProvider<registry::LPPort> lp_provider() {
  auto registration = take(adapters::lp::make_highs_registration());
  registry::Registry<registry::LPPort> providers;
  const auto id = registration.identity.id;
  if (providers.add(std::move(registration)))
    throw std::runtime_error("HiGHS LP registration failed");
  registry::Requirements requirements;
  requirements.output.representation = {"csl.program-result.v1"};
  return take(registry::prepare_provider(registry::select_provider(
      providers, registry::Method{id, {}}, requirements)));
}

registry::PreparedProvider<registry::ConvexPort> convex_provider() {
  auto registration = take(adapters::convex::make_highs_registration());
  registry::Registry<registry::ConvexPort> providers;
  const auto id = registration.identity.id;
  if (providers.add(std::move(registration)))
    throw std::runtime_error("HiGHS convex registration failed");
  registry::Requirements requirements;
  requirements.output.representation = {"csl.program-result.v1"};
  return take(registry::prepare_provider(registry::select_provider(
      providers, registry::Method{id, {}}, requirements)));
}

const char *status(synthesis::HybridVerificationStatus value) {
  switch (value) {
  case synthesis::HybridVerificationStatus::established:
    return "established";
  case synthesis::HybridVerificationStatus::refuted:
    return "refuted";
  case synthesis::HybridVerificationStatus::unsupported:
    return "unsupported";
  default:
    return "not_checked";
  }
}

struct Observation {
  std::uint64_t total_ns{};
  std::size_t paths{};
  std::size_t relation_rows{};
  std::size_t relation_matrix_elements{};
  std::string provider;
  std::string verifier;
  std::string feasibility;
  std::string optimality;
  std::string coverage;
  std::vector<std::string> edge_paths;
};

Observation run_once() {
  const auto begin = Clock::now();
  auto [system, request] = fixture();
  auto lp = lp_provider();
  auto convex = convex_provider();
  auto built = synthesis::build_hybrid_portfolio_programs(
      system, request, {"ext07-two-parameter"}, {2, 8}, {64, 4096, 65536});
  auto programs = take(std::move(built));
  if (programs.size() != 2)
    throw std::runtime_error("Expected both permitted edge paths");

  const auto execution =
      synthesis::execute_hybrid_path_programs(programs, lp, convex, {});
  if (!execution.all_supplied_branches_completed ||
      execution.branches.size() != 2)
    throw std::runtime_error("Both hybrid LP branches must complete");
  for (const auto &branch : execution.branches) {
    if (!branch.result || !branch.result->primal ||
        branch.result->primal->size() != 7 ||
        branch.outcome != MathematicalOutcome::optimal ||
        branch.termination != Termination::completed ||
        std::abs((*branch.result->primal)[1]) > 1e-8 ||
        std::abs((*branch.result->primal)[4]) > 1e-8 ||
        std::abs((*branch.result->primal)[6]) > 1e-8)
      throw std::runtime_error("LP output differs from the analytic minimum");
  }
  std::vector<synthesis::HybridPathOptimalFaceCandidate> candidates;
  for (std::size_t i = 0; i < execution.branches.size(); ++i) {
    const auto &branch = execution.branches[i];
    if (!branch.result)
      throw std::runtime_error("Missing branch optimization result");
    auto candidate = synthesis::build_hybrid_path_optimal_face_candidate(
        programs[i], *branch.result, {1e-8, 1e-8});
    if (!std::holds_alternative<synthesis::HybridPathOptimalFaceCandidate>(
            candidate))
      throw std::runtime_error("A tied branch face could not be constructed");
    candidates.push_back(std::get<synthesis::HybridPathOptimalFaceCandidate>(
        std::move(candidate)));
  }

  synthesis::ExactLinearHHybridFamilyVerifier verifier;
  auto verified = synthesis::verify_hybrid_portfolio_family(
      verifier, system, request, programs, candidates, {2, 8}, {1e-8, 1e-8});
  if (!std::holds_alternative<synthesis::HybridFamilyVerificationReport>(
          verified))
    throw std::runtime_error("Exact linear H verifier rejected the fixture");
  const auto &report =
      std::get<synthesis::HybridFamilyVerificationReport>(verified);
  if (report.branches.size() != 2 ||
      report.global_objective_optimality !=
          synthesis::HybridVerificationStatus::established ||
      report.complete_family_coverage !=
          synthesis::HybridVerificationStatus::established) {
    const auto &branch = report.branches.front();
    throw std::runtime_error(
        std::string("Verifier did not establish the complete family: global=") +
        status(report.global_objective_optimality) + ", complete=" +
        status(report.complete_family_coverage) + ", branch=" +
        status(branch.feasibility) + "/" + status(branch.objective_optimality) +
        "/" + status(branch.continuous_coverage) +
        (branch.diagnostics.empty() ? "" :
         ", diagnostic=" + branch.diagnostics.front().explanation));
  }

  Observation observation;
  observation.total_ns = static_cast<std::uint64_t>(
      std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - begin)
          .count());
  observation.paths = programs.size();
  for (const auto &program : programs) {
    if (program.relation_operations.empty())
      throw std::runtime_error("Missing relation operation evidence");
    const auto &last = program.relation_operations.back();
    observation.relation_rows += last.cumulative_rows;
    observation.relation_matrix_elements += last.cumulative_matrix_elements;
    observation.edge_paths.push_back(program.path.edges.front().value);
  }
  for (const auto &provider : execution.branches.front().providers)
    if (provider.actual)
      observation.provider = provider.actual->id.value + "@" +
                             provider.actual->version;
  observation.verifier = report.verifier_id;
  observation.feasibility = status(report.branches.front().feasibility);
  observation.optimality = status(report.branches.front().objective_optimality);
  observation.coverage = status(report.branches.front().continuous_coverage);
  for (const auto &branch : report.branches)
    if (branch.feasibility != synthesis::HybridVerificationStatus::established ||
        branch.objective_optimality !=
            synthesis::HybridVerificationStatus::established ||
        branch.continuous_coverage !=
            synthesis::HybridVerificationStatus::established)
      throw std::runtime_error("A tied path did not receive full verification");
  return observation;
}

void batch(const char *phase, std::size_t repetition, std::size_t calls) {
  std::uint64_t total = 0;
  std::size_t failures = 0;
  Observation last;
  std::string last_error;
  std::vector<std::uint64_t> durations;
  for (std::size_t i = 0; i < calls; ++i) {
    try {
      last = run_once();
      total += last.total_ns;
      durations.push_back(last.total_ns);
    } catch (const std::exception &exception) {
      ++failures;
      last_error = exception.what();
      durations.push_back(0);
    }
  }
  std::cout << "{\"phase\":\"" << phase << "\",\"repetition\":"
            << repetition << ",\"calls\":" << calls << ",\"failures\":"
            << failures << ",\"status\":\""
            << (failures == 0 ? "passed" : "failed")
            << "\",\"paths\":" << last.paths << ",\"edge_paths\":[\""
            << (last.edge_paths.empty() ? "" : last.edge_paths[0]) << "\",\""
            << (last.edge_paths.size() < 2 ? "" : last.edge_paths[1])
            << "\"],\"relation_rows\":" << last.relation_rows
            << ",\"relation_matrix_elements\":"
            << last.relation_matrix_elements << ",\"provider\":\""
            << last.provider << "\",\"verifier\":\"" << last.verifier
            << "\",\"feasibility\":\"" << last.feasibility
            << "\",\"optimality\":\"" << last.optimality
            << "\",\"coverage\":\"" << last.coverage
            << "\",\"end_to_end_total_ns\":" << total
            << ",\"call_durations_ns\":[";
  for (std::size_t i = 0; i < durations.size(); ++i) {
    if (i)
      std::cout << ',';
    std::cout << durations[i];
  }
  std::cout << "],\"error\":\"" << last_error << "\"}\n";
  if (failures)
    throw std::runtime_error("One or more measured verifier calls failed");
}
} // namespace

int main(int argc, char **argv) try {
  if (argc != 2)
    throw std::runtime_error("Expected smoke or measure mode");
  const std::string mode{argv[1]};
  if (mode == "smoke")
    batch("smoke", 0, 1);
  else if (mode == "measure") {
    batch("warmup", 0, 10);
    for (std::size_t repetition = 0; repetition < 7; ++repetition)
      batch("trial", repetition, 20);
  } else
    throw std::runtime_error("Expected smoke or measure mode");
  return 0;
} catch (const std::exception &exception) {
  std::cerr << exception.what() << '\n';
  return 1;
}
