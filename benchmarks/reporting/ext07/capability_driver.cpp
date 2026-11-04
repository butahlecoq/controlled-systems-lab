#include <csl/model/hybrid_system.hpp>

#include <chrono>
#include <cstddef>
#include <cstdint>
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
    throw std::runtime_error("EXT-07 capability fixture construction failed");
  return std::get<T>(std::move(value));
}

SetHandle universal_relation(std::string id, std::size_t dimension) {
  auto data = take(sets::make_universal(
      {SetId{std::move(id)}, dimension, {}}));
  return data.as_handle();
}

struct Fixture {
  HybridSystem system;
  HybridRequest request;
  std::string family;
};

Fixture fixture(std::size_t state_dimension, std::size_t horizon,
                std::size_t mode_count, std::size_t parallel_edges) {
  if (state_dimension == 0 || horizon == 0 || mode_count < 2 ||
      parallel_edges == 0)
    throw std::runtime_error("Invalid capability fixture dimensions");

  std::vector<HybridMode> modes;
  modes.reserve(mode_count);
  for (std::size_t i = 0; i < mode_count; ++i) {
    HybridMode mode;
    mode.id = {"mode-" + std::to_string(i)};
    mode.state_dimension = state_dimension;
    mode.control_dimension = state_dimension;
    for (std::size_t j = 0; j < state_dimension; ++j) {
      mode.state_coordinate_labels.push_back("x" + std::to_string(j));
      mode.control_coordinate_labels.push_back("u" + std::to_string(j));
    }
    mode.flow = std::vector<LinearStage>(
        horizon, LinearStage{Matrix{state_dimension, state_dimension,
                                   std::vector<double>(state_dimension * state_dimension, 0)},
                             Matrix{state_dimension, state_dimension,
                                   std::vector<double>(state_dimension * state_dimension, 0)},
                             Matrix{state_dimension, 0, {}},
                             Vector(state_dimension, 0)});
    mode.control_sets.assign(horizon, UniversalSet{state_dimension});
    mode.invariants.assign(horizon + 1, UniversalSet{state_dimension});
    modes.push_back(std::move(mode));
  }

  // The request profile varies dimensions and catalogue size independently.
  // A stage-chain fixture measures horizon without reusing edge identities.
  // Cyclic fixtures hold a smaller mode catalogue fixed while varying horizon,
  // edge count, and the resulting complete branch inventory.
  std::vector<HybridTransitionEdge> edges;
  const bool stage_chain = mode_count == horizon + 1 && parallel_edges == 1;
  const auto source_count = stage_chain ? horizon : mode_count;
  edges.reserve(source_count * parallel_edges);
  for (std::size_t source_index = 0; source_index < source_count; ++source_index) {
    const auto target_index = (source_index + 1) % mode_count;
    for (std::size_t branch = 0; branch < parallel_edges; ++branch) {
      const auto id = "edge-" + std::to_string(source_index) + "-" +
                      std::to_string(branch);
      std::vector<AdmissibleSet> guards(
          horizon, UniversalSet{state_dimension});
      std::vector<SetHandle> resets;
      resets.reserve(horizon);
      for (std::size_t i = 0; i < horizon; ++i)
        resets.push_back(universal_relation(id + "-reset-" + std::to_string(i),
                                            state_dimension * 2));
      edges.push_back({{id}, modes[source_index].id, modes[target_index].id,
                       std::move(guards), std::move(resets)});
    }
  }

  HybridSystem system{horizon, std::move(modes), std::move(edges)};
  std::vector<HybridModeId> terminal_modes{system.modes[horizon % mode_count].id};
  HybridRequest request{
      {system.modes.front().id, Vector(state_dimension, 0)},
      terminal_modes,
      {{terminal_modes.front(),
        LinearTerminal{Vector(state_dimension, 0), 0}, "zero", "units"}}};
  return {std::move(system), std::move(request),
          parallel_edges == 1 ? "single-chain" : "parallel-branching"};
}

struct Result {
  std::size_t state_dimension{};
  std::size_t control_dimension{};
  std::size_t horizon{};
  std::size_t mode_count{};
  std::size_t edge_count{};
  std::size_t path_cap{};
  std::string family;
  std::size_t path_count{};
  std::uint64_t batch_ns{};
  std::size_t calls{};
};

Result measure(const Fixture& f, std::size_t path_cap, std::size_t calls) {
  const auto start = Clock::now();
  Result result;
  for (std::size_t i = 0; i < calls; ++i) {
    const auto report = report_hybrid_capability(
        f.system, f.request, {f.system.horizon, path_cap});
    if (!std::holds_alternative<HybridCapabilityReport>(report))
      throw std::runtime_error("Capability reporting stopped unexpectedly");
    const auto& value = std::get<HybridCapabilityReport>(report);
    if (!value.profile_admitted || !value.path_enumeration_completed ||
        !value.complete_allowed_path_count) {
      const std::string field = value.diagnostics.empty()
                                    ? "unknown"
                                    : value.diagnostics.front().field;
      throw std::runtime_error("Capability profile was rejected or incomplete: " +
                               field);
    }
    if (i == 0) {
      result.state_dimension = value.maximum_state_dimension;
      result.control_dimension = value.maximum_control_dimension;
      result.horizon = value.horizon;
      result.mode_count = value.mode_count;
      result.edge_count = value.edge_count;
      result.path_cap = path_cap;
      result.family = f.family;
      result.path_count = *value.complete_allowed_path_count;
      result.calls = calls;
    }
  }
  const auto end = Clock::now();
  result.batch_ns = static_cast<std::uint64_t>(
      std::chrono::duration_cast<std::chrono::nanoseconds>(end - start).count());
  return result;
}

void print(const Result& r, std::size_t repetition) {
  std::cout << "{\"state_dimension\":" << r.state_dimension
            << ",\"control_dimension\":" << r.control_dimension
            << ",\"horizon\":" << r.horizon
            << ",\"mode_count\":" << r.mode_count
            << ",\"edge_count\":" << r.edge_count
            << ",\"path_cap\":" << r.path_cap
            << ",\"path_count\":" << r.path_count
            << ",\"family\":\"" << r.family
            << "\",\"repetition\":" << repetition
            << ",\"calls\":" << r.calls
            << ",\"batch_ns\":" << r.batch_ns << "}\n";
}
} // namespace

int main(int argc, char** argv) {
  try {
    if (argc != 2 || std::string(argv[1]) != "measure")
      throw std::runtime_error("Usage: csl_ext07_capability_report measure");

    constexpr std::size_t repetitions = 7;
    constexpr std::size_t calls = 1000;
    const std::vector<Fixture> fixtures{
        fixture(1, 1, 2, 1), fixture(2, 1, 2, 1),
        fixture(4, 1, 2, 1), fixture(8, 1, 2, 1),
        fixture(1, 2, 2, 1), fixture(1, 4, 2, 1),
        fixture(1, 8, 2, 1), fixture(1, 4, 4, 1),
        fixture(1, 4, 8, 1), fixture(1, 8, 2, 2)};

    for (const auto& f : fixtures) {
      const std::size_t path_cap = 1U << f.system.horizon;
      (void)measure(f, path_cap, calls); // Excluded warmup batch.
    }
    for (std::size_t repetition = 0; repetition < repetitions; ++repetition)
      for (const auto& f : fixtures)
        print(measure(f, 1U << f.system.horizon, calls), repetition);
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
