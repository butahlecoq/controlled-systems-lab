#pragma once

#include <csl/core/diagnostics.hpp>
#include <csl/model/contracts.hpp>
#include <csl/optimization/objective_contracts.hpp>
#include <csl/sets/contracts.hpp>
#include <cstddef>
#include <string>
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

using HybridPathEnumeration = std::variant<std::vector<HybridPath>, Diagnostic>;

struct HybridEnumerationLimits {
    std::size_t max_horizon;
    std::size_t max_paths;
};

// Enumerates each allowed edge path once. The result is complete or the
// request is rejected at the caller's limits; a truncated family is never returned.
HybridPathEnumeration enumerate_hybrid_paths(
    const HybridSystem&, const HybridModeId& initial_mode,
    const std::vector<HybridModeId>& allowed_terminal_modes, HybridEnumerationLimits);

Diagnostics check_hybrid_profile(const HybridSystem&, const HybridRequest&);

} // namespace csl::model
