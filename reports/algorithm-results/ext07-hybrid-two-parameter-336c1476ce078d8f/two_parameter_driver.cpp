#include <csl/adapters/convex/highs.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <csl/synthesis/hybrid_path_program.hpp>
#include "process_cpu_json.hpp"
#include "operation_cpu_json.hpp"

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

std::pair<HybridSystem, HybridRequest> fixture(std::size_t branch_count = 2) {
  if (branch_count == 0 || branch_count > 16)
    throw std::runtime_error("Capacity fixture supports 1 through 16 branches");
  const LinearStage first{Matrix{1, 1, {0}}, Matrix{1, 1, {1}},
                                 Matrix{1, 0, {}}, Vector{0}};
  const LinearStage second{Matrix{1, 1, {1}}, Matrix{1, 1, {0}},
                                  Matrix{1, 0, {}}, Vector{0}};
  HybridMode source{{"source"}, 1, 1, {"x"}, {"u"}, LinearStage{}, {}, {}};
  source.flow = std::vector<LinearStage>{first, second};
  source.control_sets = {interval("control-u0", 0, 1), Singleton{{0}}};
  source.invariants = {UniversalSet{1}, UniversalSet{1}, UniversalSet{1}};

  HybridMode terminal{{"terminal"}, 1, 1, {"x"}, {"u"}, LinearStage{}, {}, {}};
  terminal.flow = std::vector<LinearStage>{first, second};
  terminal.control_sets = {Singleton{{0}}, Singleton{{0}}};
  terminal.invariants = {UniversalSet{1}, UniversalSet{1}, UniversalSet{1}};

  std::vector<HybridMode> modes{source};
  std::vector<HybridTransitionEdge> edges;
  edges.reserve(branch_count * 2);
  const auto id0 = identity_reset("reset-0");
  const auto id1 = identity_reset("reset-1");
  for (std::size_t i = 0; i < branch_count; ++i) {
    const auto suffix = std::to_string(i);
    const auto middle_id = branch_count == 2 ? std::string{"middle"}
                                             : "middle-" + suffix;
    const auto enter_id = branch_count == 2
                              ? (i == 0 ? std::string{"enter-half"}
                                        : std::string{"enter-full"})
                              : "enter-" + suffix;
    const auto finish_id = branch_count == 2 ? std::string{"finish"}
                                             : "finish-" + suffix;
    if (branch_count != 2 || i == 0) {
      HybridMode middle{{middle_id}, 1, 1, {"x"}, {"u"}, LinearStage{}, {}, {}};
      middle.flow = std::vector<LinearStage>{first, second};
      middle.control_sets = {Singleton{{0}}, interval(
          branch_count == 2 ? "control-u1" : "control-u1-" + suffix, 0, 1)};
      middle.invariants = {UniversalSet{1}, UniversalSet{1}, UniversalSet{1}};
      modes.push_back(std::move(middle));
    }
    const double upper = static_cast<double>(i + 1) /
                         static_cast<double>(branch_count);
    const auto guard = i + 1 == branch_count
                           ? AdmissibleSet{UniversalSet{1}}
                           : AdmissibleSet{interval("guard-" + suffix, 0, upper)};
    edges.push_back({{enter_id}, {"source"}, {middle_id},
                     {guard, UniversalSet{1}},
                     {id0, universal_reset("unused-enter-reset-" + suffix)}});
    if (branch_count != 2)
      edges.push_back({{finish_id}, {middle_id}, {"terminal"},
                       {UniversalSet{1}, UniversalSet{1}},
                       {universal_reset("unused-finish-reset-" + suffix), id1}});
  }
  if (branch_count == 2)
    edges.push_back({{"finish"}, {"middle"}, {"terminal"},
                     {UniversalSet{1}, UniversalSet{1}},
                     {universal_reset("unused-terminal-reset"), id1}});
  modes.push_back(terminal);
  HybridSystem system{2, std::move(modes), std::move(edges)};
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
  std::vector<synthesis::ProcessCpuObservation> branch_process_cpu;
  std::vector<std::optional<synthesis::HybridBranchExecution::ProviderInvocationObservation>> provider_invocations;
  std::vector<std::vector<HybridRelationOperationRecord>> operation_records;
  struct BranchOutcome {
    std::string path;
    std::string optimization;
    std::string termination;
    std::string feasibility;
    std::string optimality;
    std::string coverage;
  };
  std::vector<BranchOutcome> branch_outcomes;
};

Observation run_once(std::size_t branch_count = 2) {
  const auto begin = Clock::now();
  auto [system, request] = fixture(branch_count);
  auto lp = lp_provider();
  auto convex = convex_provider();
  auto built = synthesis::build_hybrid_portfolio_programs(
      system, request, {"ext07-two-parameter"}, {2, branch_count},
      {64, 4096, 65536});
  auto programs = take(std::move(built));
  Observation observation;
  if (programs.size() != branch_count)
    throw std::runtime_error("Expected every permitted edge path");
  for (const auto &program : programs)
    observation.operation_records.push_back(program.relation_operations);

  const auto execution =
      synthesis::execute_hybrid_path_programs(programs, lp, convex, {});
  if (!execution.all_supplied_branches_completed ||
      execution.branches.size() != branch_count)
    throw std::runtime_error("Every hybrid LP branch must complete");
  for (const auto &branch : execution.branches) {
    observation.branch_process_cpu.push_back(branch.process_cpu);
    observation.provider_invocations.push_back(branch.provider_invocation);
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
  ExecutionContext verifier_context;
  verifier_context.numerical = {1e-8, 1e-8};
  auto verified = synthesis::verify_hybrid_portfolio_family(
      verifier, system, request, programs, candidates, {2, branch_count},
      synthesis::HybridVerifierInvocation{verifier_context});
  if (!std::holds_alternative<synthesis::HybridFamilyVerificationReport>(
          verified))
    throw std::runtime_error("Exact linear H verifier rejected the fixture");
  const auto &report =
      std::get<synthesis::HybridFamilyVerificationReport>(verified);
  if (report.branches.size() != branch_count ||
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
  for (std::size_t i = 0; i < report.branches.size(); ++i) {
    const auto &branch = report.branches[i];
    if (branch.feasibility != synthesis::HybridVerificationStatus::established ||
        branch.objective_optimality !=
            synthesis::HybridVerificationStatus::established ||
        branch.continuous_coverage !=
            synthesis::HybridVerificationStatus::established)
      throw std::runtime_error("A tied path did not receive full verification");
    observation.branch_outcomes.push_back({
        programs[i].path.edges.front().value, "optimal", "completed",
        status(branch.feasibility), status(branch.objective_optimality),
        status(branch.continuous_coverage)});
  }
  return observation;
}

void batch(const char *phase, std::size_t repetition, std::size_t calls,
           std::size_t branch_count = 2) {
  std::uint64_t total = 0;
  std::size_t failures = 0;
  Observation last;
  std::string last_error;
  std::vector<std::uint64_t> durations;
  std::vector<std::vector<synthesis::ProcessCpuObservation>> process_cpu_observations;
  std::vector<std::vector<std::optional<synthesis::HybridBranchExecution::ProviderInvocationObservation>>> provider_invocation_observations;
  std::vector<std::vector<std::vector<HybridRelationOperationRecord>>> operation_observations;
  std::vector<std::vector<Observation::BranchOutcome>> branch_outcome_observations;
  for (std::size_t i = 0; i < calls; ++i) {
    try {
      last = run_once(branch_count);
      total += last.total_ns;
      durations.push_back(last.total_ns);
      process_cpu_observations.push_back(last.branch_process_cpu);
      provider_invocation_observations.push_back(last.provider_invocations);
      operation_observations.push_back(last.operation_records);
      branch_outcome_observations.push_back(last.branch_outcomes);
    } catch (const std::exception &exception) {
      ++failures;
      last_error = exception.what();
      durations.push_back(0);
      process_cpu_observations.emplace_back();
      provider_invocation_observations.emplace_back();
      operation_observations.emplace_back();
      branch_outcome_observations.emplace_back();
    }
  }
  std::cout << "{\"phase\":\"" << phase << "\",\"repetition\":"
            << repetition << ",\"calls\":" << calls << ",\"failures\":"
            << failures << ",\"status\":\""
            << (failures == 0 ? "passed" : "failed")
            << "\",\"paths\":" << last.paths << ",\"edge_paths\":[";
  for (std::size_t i = 0; i < last.edge_paths.size(); ++i) {
    if (i) std::cout << ',';
    std::cout << '"' << last.edge_paths[i] << '"';
  }
  std::cout << "],\"relation_rows\":" << last.relation_rows
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
  std::cout << "],\"process_cpu_observations\":[";
  for(std::size_t call=0;call<process_cpu_observations.size();++call) {
    if(call) std::cout << ',';
    std::cout << '[';
    for(std::size_t branch=0;branch<process_cpu_observations[call].size();++branch) {
      if(branch) std::cout << ',';
      reports::ext07::write_process_cpu_observation(
          std::cout,process_cpu_observations[call][branch]);
    }
    std::cout << ']';
  }
  std::cout << "],\"provider_invocation_observations\":[";
  for(std::size_t call=0;call<provider_invocation_observations.size();++call) {
    if(call) std::cout << ',';
    std::cout << '[';
    for(std::size_t branch=0;branch<provider_invocation_observations[call].size();++branch) {
      if(branch) std::cout << ',';
      reports::ext07::write_provider_invocation_observation(
          std::cout,provider_invocation_observations[call][branch]);
    }
    std::cout << ']';
  }
  std::cout << "],\"operation_observations\":[";
  for(std::size_t call=0;call<operation_observations.size();++call) {
    if(call) std::cout << ',';
    std::cout << '[';
    for(std::size_t path=0;path<operation_observations[call].size();++path) {
      if(path) std::cout << ',';
      reports::ext07::write_operation_records(std::cout,operation_observations[call][path]);
    }
    std::cout << ']';
  }
  std::cout << "],\"branch_outcome_observations\":[";
  for (std::size_t call = 0; call < branch_outcome_observations.size(); ++call) {
    if (call) std::cout << ',';
    std::cout << '[';
    for (std::size_t branch = 0; branch < branch_outcome_observations[call].size(); ++branch) {
      if (branch) std::cout << ',';
      const auto &outcome = branch_outcome_observations[call][branch];
      std::cout << "{\"path\":\"" << outcome.path
                << "\",\"optimization\":\"" << outcome.optimization
                << "\",\"termination\":\"" << outcome.termination
                << "\",\"feasibility\":\"" << outcome.feasibility
                << "\",\"optimality\":\"" << outcome.optimality
                << "\",\"coverage\":\"" << outcome.coverage << "\"}";
    }
    std::cout << ']';
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
  } else if (mode == "capacity") {
    for (const std::size_t branches : {1U, 2U, 4U, 8U, 16U}) {
      batch("warmup", 0, 2, branches);
      for (std::size_t repetition = 0; repetition < 7; ++repetition)
        batch("trial", repetition, 10, branches);
    }
  } else
    throw std::runtime_error("Expected smoke, measure, or capacity mode");
  return 0;
} catch (const std::exception &exception) {
  std::cerr << exception.what() << '\n';
  return 1;
}
