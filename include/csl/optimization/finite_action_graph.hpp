#pragma once

#include <csl/geometry/contracts.hpp>
#include <csl/optimization/finite_action_nominal.hpp>
#include <csl/registry/provider.hpp>

#include <optional>

namespace csl::optimization {

enum class FiniteGraphBackwardStatus {
    root_node,
    pending,
    terminal_admissible,
    terminal_outside_stage_set,
    skipped_suffix_nonviable,
    predecessor_membership_false,
    discrete_transition_witness_failed,
    parent_stage_intersection_empty,
    eligible_numerical_predecessor_and_discrete_edge
};

struct FiniteActionGraphNode {
    std::size_t stage{};
    Vector state;
    std::optional<std::size_t> parent_node;
    std::optional<std::size_t> action_index;
    double edge_running_cost{};
    double heuristic_score{};
    bool state_admissible{};
    bool stage_intersection_nonempty{};
    bool backward_viable{};
    std::optional<bool> predecessor_contains_parent;
    std::optional<bool> discrete_transition_witness;
    std::optional<double> backward_value;
    std::vector<std::size_t> action_lineage;
    FiniteGraphBackwardStatus backward_status{FiniteGraphBackwardStatus::pending};
    std::optional<bool> reachable_envelope_contains;
};

struct FiniteActionGraphLayerStatistics {
    std::size_t stage{};
    std::size_t generated{};
    std::size_t retained{};
    std::size_t pruned{};
    std::size_t stage_inadmissible{};
};

struct FiniteActionGraphLimits {
    std::size_t beam_width;
    std::size_t max_nodes;
};

struct FiniteActionGraphResult {
    std::vector<FiniteActionGraphNode> nodes;
    std::vector<std::vector<std::size_t>> layers;
    std::vector<FiniteActionGraphLayerStatistics> layer_statistics;
    std::vector<std::size_t> selected_nodes;
    std::size_t predecessor_calls{};
    std::size_t stage_intersection_calls{};
    std::size_t reachable_envelope_calls{};
    bool search_complete{};
    bool node_budget_exhausted{};
    bool has_viable_path{};
    double total_objective{};
};

using FiniteActionGraphOutcome = std::variant<FiniteActionGraphResult, Unsupported, OperationStopped>;

// Builds a deterministic, beam-bounded tree over every remaining authored
// stage. Stage H intersections and numerical predecessor membership filter
// candidates before Bellman selection. Every selected edge retains its
// authored action index and recomputed parent-to-child transition witness.
// This reports optimality only over the retained tree and the supplied model.
FiniteActionGraphOutcome finite_action_stage_layered_graph(
    const FiniteActionNominalRequest&, FiniteActionGraphLimits,
    const registry::PreparedProvider<registry::GeometryPort>& projection_provider,
    const ExecutionContext& = {});

// Optional registered forward-set operation. It is applied to each retained
// parent before any of that parent's discrete action edges are admitted.
FiniteActionGraphOutcome finite_action_stage_layered_graph(
    const FiniteActionNominalRequest&, FiniteActionGraphLimits,
    const registry::PreparedProvider<registry::GeometryPort>& projection_provider,
    const registry::PreparedProvider<registry::GeometryPort>& reachable_set_provider,
    const ExecutionContext& = {});

} // namespace csl::optimization
