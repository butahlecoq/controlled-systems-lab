#pragma once

#include <csl/core/diagnostics.hpp>
#include <csl/core/outcomes.hpp>
#include <csl/model/contracts.hpp>
#include <csl/optimization/objective_contracts.hpp>
#include <csl/sets/contracts.hpp>
#include <csl/sets/data.hpp>
#include <cstddef>
#include <optional>
#include <span>
#include <string>
#include <stop_token>
#include <variant>
#include <vector>

namespace csl::model {

struct HybridModeId {
    std::string value;
    bool operator==(const HybridModeId&) const = default;
};

struct HybridEdgeId {
    std::string value;
    bool operator==(const HybridEdgeId&) const = default;
};

struct HybridMode {
    HybridModeId id;
    std::size_t state_dimension{};
    std::size_t control_dimension{};
    std::vector<std::string> state_coordinate_labels;
    std::vector<std::string> control_coordinate_labels;
    Coefficients flow{LinearStage{}};
    std::vector<AdmissibleSet> control_sets;
    std::vector<AdmissibleSet> invariants;
};

struct HybridTransitionEdge {
    HybridEdgeId id;
    HybridModeId source;
    HybridModeId target;
    std::vector<AdmissibleSet> guards;
    // Each relation lives in concatenated [source-state, target-state] space.
    std::vector<SetHandle> reset_relations;
};

struct HybridSystem {
    std::size_t horizon;
    std::vector<HybridMode> modes;
    std::vector<HybridTransitionEdge> edges;
};

struct HybridPath {
    std::vector<HybridModeId> modes;
    std::vector<HybridEdgeId> edges;
    bool operator==(const HybridPath&) const = default;
};

struct HybridInitialState {
    HybridModeId mode;
    Vector state;
};

struct HybridModeObjective {
    HybridModeId mode;
    TerminalObjective objective;
    std::string quantity;
    std::string units;
};

struct HybridRequest {
    HybridInitialState initial;
    std::vector<HybridModeId> allowed_terminal_modes;
    std::vector<HybridModeObjective> terminal_objectives;
};

using HybridPathEnumeration = std::variant<std::vector<HybridPath>, Diagnostic, OperationStopped>;

struct HybridEnumerationLimits {
    std::size_t max_horizon;
    std::size_t max_paths;
};

struct HybridRelationLimits {
    std::size_t max_variables;
    std::size_t max_rows;
    std::size_t max_matrix_elements;
};
using HybridRelationResult = std::variant<sets::SetData, Diagnostic, OperationStopped>;

enum class HybridRelationOperationKind {
    initial_state, post_state_invariant, mode_flow, continuous_control,
    pre_reset_invariant, transition_guard, reset_relation
};

struct HybridRelationOperationRecord {
    HybridRelationOperationKind operation;
    std::size_t stage{};
    std::optional<HybridModeId> mode;
    std::optional<HybridEdgeId> edge;
    std::string implementation_id;
    std::string implementation_version;
    std::size_t joint_variables{};
    std::size_t rows_added{};
    std::size_t cumulative_rows{};
    std::size_t cumulative_matrix_elements{};
};

// Framework-owned structural operation identity for trace validation. The
// path index preserves duplicate branches as distinct ordered obligations;
// adapters do not yet receive a shared operation-admission receipt.
struct HybridPlannedOperation {
    std::size_t path_index{};
    HybridRelationOperationKind operation{};
    std::size_t stage{};
    std::optional<HybridModeId> mode;
    std::optional<HybridEdgeId> edge;
    bool operator==(const HybridPlannedOperation&) const = default;
};

// Generates deterministic operation identities without executing a provider
// or constructing a relation. Each path contributes initial state, every
// post-state invariant, and the flow/control/pre-reset/guard/reset operations
// for each edge in path order.
std::vector<HybridPlannedOperation> plan_hybrid_operations(
    std::span<const HybridPath> paths);

struct HybridComposedPathRelation {
    sets::SetData relation;
    HybridRelationLimits limits;
    std::vector<HybridRelationOperationRecord> operations;
};
struct HybridPathCompositionFailureReport {
    HybridPath path;
    HybridRelationLimits limits;
    std::vector<HybridRelationOperationRecord> operations;
    std::variant<Diagnostic, OperationStopped> failure;
};
using HybridComposedPathRelationResult = std::variant<HybridComposedPathRelation,
    HybridPathCompositionFailureReport>;
using HybridRelationPreflightResult = std::variant<std::monostate,
    HybridPathCompositionFailureReport, Diagnostics, OperationStopped>;

struct HybridModeCapabilitySummary {
    HybridModeId mode;
    std::size_t state_dimension{};
    std::size_t control_dimension{};
};

// A request-scoped capacity and admission report. A completed finite path
// count describes only this request and these limits; it is not a scalability
// guarantee for larger horizons or catalogues.
struct HybridCapabilityReport {
    std::size_t horizon{};
    std::size_t mode_count{};
    std::size_t edge_count{};
    std::size_t maximum_state_dimension{};
    std::size_t maximum_control_dimension{};
    std::vector<HybridModeCapabilitySummary> modes;
    HybridEnumerationLimits limits{};
    std::optional<std::size_t> complete_allowed_path_count;
    bool profile_admitted{};
    bool path_enumeration_completed{};
    Diagnostics diagnostics;
};
using HybridCapabilityReportResult = std::variant<HybridCapabilityReport, OperationStopped>;

HybridCapabilityReportResult report_hybrid_capability(
    const HybridSystem&, const HybridRequest&, HybridEnumerationLimits,
    std::stop_token cancellation = {});

// Enumerates each allowed edge path once. The result is complete or the
// request is rejected at the caller's limits; a truncated family is never returned.
HybridPathEnumeration enumerate_hybrid_paths(
    const HybridSystem&, const HybridModeId& initial_mode,
    const std::vector<HybridModeId>& allowed_terminal_modes, HybridEnumerationLimits,
    std::stop_token cancellation = {});

Diagnostics check_hybrid_profile(const HybridSystem&, const HybridRequest&);

// Checks the complete supplied path inventory against direct joint-H operation
// and resource limits without constructing any path relation.
HybridRelationPreflightResult preflight_hybrid_path_relations(
    const HybridSystem&, const HybridRequest&, std::span<const HybridPath>,
    HybridRelationLimits, std::stop_token cancellation = {});

// Builds the exact joint H-relation for one already enumerated branch. The
// relation retains post states, controls, and pre-reset states as coordinates.
HybridRelationResult compose_hybrid_path_relation(const HybridSystem&, const HybridRequest&,
    const HybridPath&, HybridRelationLimits, std::stop_token cancellation = {});
HybridComposedPathRelationResult compose_hybrid_path_relation_with_report(
    const HybridSystem&, const HybridRequest&, const HybridPath&, HybridRelationLimits,
    std::stop_token cancellation = {});

using HybridObjectiveLiftResult = std::variant<TerminalObjective, Diagnostic>;
using HybridObjectiveLiftPreflightResult = std::variant<std::monostate, Diagnostic, OperationStopped>;
// Checks lifted objective dimensions and dense storage without allocating the lift.
HybridObjectiveLiftPreflightResult preflight_hybrid_terminal_objective_lift(
    const HybridSystem&, const HybridRequest&, const HybridPath&, HybridRelationLimits,
    std::stop_token cancellation = {});
HybridObjectiveLiftResult lift_hybrid_terminal_objective(const HybridSystem&, const HybridRequest&,
    const HybridPath&, HybridRelationLimits);

} // namespace csl::model
