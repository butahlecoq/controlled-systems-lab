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
    representation_filter_rejected,
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
    std::optional<bool> representation_filter_passed;
    std::string representation_filter_outcome;
    Vector representation_outer_lower;
    Vector representation_outer_upper;
};

struct FiniteActionGraphLayerStatistics {
    std::size_t stage{};
    std::size_t generated{};
    std::size_t retained{};
    std::size_t pruned{};
    std::size_t stage_inadmissible{};
    std::size_t representation_filter_rejected{};
};

struct FiniteGraphCloudActionWitness {
    std::size_t action_index{};
    Vector child_state;
    bool contained_in_outer{};
};

struct FiniteGraphActionCloudEnvelope {
    std::size_t stage{};
    std::size_t parent_node{};
    NominalRepresentation representation{NominalRepresentation::exact_polytope};
    std::string module_id;
    std::string auxiliary_request_id;
    Vector parent_state;
    Matrix auxiliary_A;
    Matrix auxiliary_B;
    Matrix auxiliary_E;
    Vector auxiliary_offset;
    Vector auxiliary_control;
    std::vector<Vector> authored_action_effect_vertices;
    Vector outer_lower;
    Vector outer_upper;
    std::optional<bool> outer_inside_authored_stage_set;
    std::vector<FiniteGraphCloudActionWitness> action_witnesses;
    Assurance assurance{Assurance::numerical};
    // The artificial external channel carries B*conv(authored actions) only;
    // the source task's external disturbance dimension remains unchanged.
    std::string lifting_semantics{"auxiliary-authored-control-image"};
};

struct FiniteActionGraphLimits {
    std::size_t beam_width;
    std::size_t max_nodes;
    // Optional per-authored-edge numerical outer filter. It does not merge or
    // replace discrete action nodes; non-box representations use an explicit
    // coordinate-box outer relaxation for child membership.
    std::optional<NominalRepresentation> edge_representation_filter{};
    // Used only by the zonotope filter.
    std::size_t max_generators_per_stage{1000};
    // Selected approximation of the complete authored-action image from each
    // retained parent. This envelope is recorded and checked for containment;
    // it does not replace or merge discrete edge witnesses.
    std::optional<NominalRepresentation> parent_action_cloud_representation{};
};

struct FiniteActionGraphResult {
    std::vector<FiniteActionGraphNode> nodes;
    std::vector<std::vector<std::size_t>> layers;
    std::vector<FiniteActionGraphLayerStatistics> layer_statistics;
    std::vector<std::size_t> selected_nodes;
    std::size_t predecessor_calls{};
    std::size_t stage_intersection_calls{};
    std::size_t reachable_envelope_calls{};
    std::size_t representation_filter_calls{};
    std::size_t representation_filter_rejections{};
    std::vector<FiniteGraphActionCloudEnvelope> action_cloud_envelopes;
    std::size_t action_cloud_calls{};
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
