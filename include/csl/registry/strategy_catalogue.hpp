#pragma once

#include <csl/registry/registry.hpp>

namespace csl::registry {

enum class CandidateStatus {
    admitted,
    incompatible,
    implementation_missing,
    backend_unavailable,
    excluded
};

struct StrategyCandidateGraph {
    std::string id;
    Identity strategy;
    ProblemId problem;
    FamilyRequest family;
    StrategyConfiguration configuration;
    std::optional<std::vector<StrategyRegistration::ConfigurationSlot>> active_configuration_slots;
    std::vector<std::pair<std::string, std::string>> module_slots;
    std::vector<TransformStepIdentity> lineage;
    std::string request_key;
    std::vector<Provenance> resolved_providers;
    std::optional<std::vector<TransformStepIdentity>> expected_lineage;
};

struct PreparedStrategyCandidate {
    StrategyCandidateGraph graph;
    PreparedStrategy strategy;
    std::vector<Provenance> provenance;
};

struct StrategyCandidateRow {
    StrategyCandidateGraph graph;
    CandidateStatus status{CandidateStatus::incompatible};
    std::vector<Provenance> provenance;
    std::optional<PreparedStrategy> prepared;
    std::optional<Rejection> rejection;
};

// Enumerate the registered strategies for this concrete request profile and
// resolve each candidate through StrategyRegistry::prepare. Source-declared
// inactive slots are represented as not_used; active selections and resolved
// provider provenance remain pinned in the graph. Empty requirement fields
// in the two-argument overload derive representation, assurance, and family
// target from request.family. Explicit requirements are preserved verbatim.
std::vector<StrategyCandidateRow> enumerate_strategy_candidates(const StrategyRegistry &,
                                                                const StrategyRequest &);
std::vector<StrategyCandidateRow> enumerate_strategy_candidates(const StrategyRegistry &,
                                                                const StrategyRequest &,
                                                                const Requirements &);

// Re-prepare one generated request before execution. The candidate must match
// the problem, family and all selected module slots that were enumerated;
// the two-argument overload derives omitted output requirements from the
// request family, while the explicit overload preserves caller requirements.
std::variant<PreparedStrategyCandidate, Rejection>
prepare_strategy_candidate(const StrategyRegistry &, const StrategyCandidateGraph &,
                           const StrategyRequest &);
std::variant<PreparedStrategyCandidate, Rejection>
prepare_strategy_candidate(const StrategyRegistry &, const StrategyCandidateGraph &,
                           const StrategyRequest &, const Requirements &);

} // namespace csl::registry
