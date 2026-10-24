#pragma once

#include <csl/artifacts/run_statistics.hpp>
#include <csl/execution/executor.hpp>

namespace csl::experiments {

// Selection settings are retained with a coarse run so a later query stage can
// replay the exact deterministic witness request against the returned family.
struct SelectionSettings {
    std::size_t count{};
    double distinctness_tolerance{};
    std::vector<Vector> directions;
    std::optional<std::size_t> seed;
};

struct ScenarioConfigurationId {
    std::string scenario;
    artifacts::ConfigId configuration;
    bool operator==(const ScenarioConfigurationId&) const = default;
};

struct ScenarioSweepCase {
    ScenarioConfigurationId identity;
    registry::PreparedStrategy strategy;
    execution::ResourceUse resources;
    SelectionSettings selection;
};

struct SweepCaseRecord {
    ScenarioConfigurationId identity;
    std::shared_ptr<const SelectionSettings> selection;
};

struct SweepResult {
    // Case records and task records use the same stable input order.
    execution::BatchResult<registry::StrategyPort> batch;
    std::vector<SweepCaseRecord> cases;
};

using SweepOutcome = std::variant<SweepResult, Diagnostics>;

// Each case runs one complete prepared strategy on its whole immutable
// scenario/configuration. Horizon stages are not split into executor tasks.
// Returned cases remain in input order in sequential and bounded-parallel mode.
SweepOutcome run_sweep(std::span<const ScenarioSweepCase>, const ResourcePolicy&,
    const ExecutionContext&, execution::Mode, execution::AdmissionLimit = {});

} // namespace csl::experiments
