#pragma once

#include <csl/artifacts/scenario_sweep.hpp>
#include <csl/execution/executor.hpp>
#include <csl/registry/provider.hpp>

namespace csl::experiments {

// Selection settings are retained with a coarse run so a later query stage can
// replay the exact deterministic witness request against the returned family.
struct SelectionSettings {
    std::size_t count{};
    double distinctness_tolerance{};
    std::vector<Vector> directions;
    std::optional<std::size_t> seed;
};

struct ScenarioId {
    std::string value;
    bool operator==(const ScenarioId&) const = default;
};

struct ScenarioConfigurationId {
    ScenarioId scenario;
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
    // Original request and caller-declared output reservations retained for this sweep.
    ResourcePolicy requested_resources{};
    std::optional<std::size_t> retained_result_reservation_bytes;
};

enum class QueryNotRunReason {
    strategy_skipped,
    strategy_failed,
    strategy_unsupported,
    family_unavailable,
};

struct FamilyQueryNotRun { QueryNotRunReason reason; };
struct FamilyQueryRejected { Diagnostics diagnostics; };
struct FamilyQueryScheduled { std::size_t task_index; };
using FamilyQueryStatus = std::variant<FamilyQueryNotRun, FamilyQueryRejected, FamilyQueryScheduled>;

struct FamilyQueryRecord {
    ScenarioConfigurationId identity;
    FamilyQueryStatus status;
};

struct FamilyQueryResult {
    // The original coarse results remain unchanged and available beside the
    // selector batch. Each query record is aligned with sweep.cases.
    SweepResult sweep;
    std::vector<FamilyQueryRecord> queries;
    // Only eligible, selector-accepted requests appear in this compact batch.
    // FamilyQueryScheduled::task_index points into query_batch.tasks.
    execution::BatchResult<registry::SelectorPort> query_batch;
    // Caller-declared reservation for selector outputs retained by this phase.
    std::optional<std::size_t> query_result_reservation_bytes;
};

using SweepOutcome = std::variant<SweepResult, Diagnostics>;
using FamilyQueryOutcome = std::variant<FamilyQueryResult, Diagnostics>;

// Each case runs one complete prepared strategy on its whole immutable
// scenario/configuration. Horizon stages are not split into executor tasks.
// Returned cases remain in input order in sequential and bounded-parallel mode.
SweepOutcome run_sweep(std::span<const ScenarioSweepCase>, const ResourcePolicy&,
    const ExecutionContext&, execution::Mode, execution::AdmissionLimit = {});

// Runs compatible selector requests only after the complete coarse batch has
// joined. Ownership of `coarse` transfers on success; on diagnostics it remains
// unchanged so callers can retain or inspect the already completed sweep.
FamilyQueryOutcome run_family_queries(SweepResult&& coarse,
    const registry::PreparedProvider<registry::SelectorPort>& selector,
    const ResourcePolicy&, const ExecutionContext&, execution::Mode,
    const execution::ResourceUse& query_resources, execution::AdmissionLimit = {});

// Combines live phase dispositions and measured executor facts with caller-owned
// inert per-case run records. Coarse records must match each live task's terminal
// status, mathematical outcome, objective bounds, and configuration identity;
// query records are aligned with cases, with values only for cases whose selector
// task was scheduled.
artifacts::ArtifactResult<artifacts::RecordedSweepArtifact> record_family_query_sweep(
    const problem::ResolvedContent& canonical_spec, const FamilyQueryResult&,
    std::span<const artifacts::RecordedRunArtifact> coarse_runs,
    std::span<const std::optional<artifacts::RecordedRunArtifact>> query_runs,
    artifacts::EncodeLimits limits = {});

} // namespace csl::experiments
