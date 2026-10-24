#pragma once

#include <csl/artifacts/run_statistics.hpp>

namespace csl::artifacts {

enum class SweepNotRunReason {
    strategy_skipped,
    strategy_failed,
    strategy_unsupported,
    family_unavailable
};

struct SweepQueryNotRun { SweepNotRunReason reason; };
struct SweepQueryRejected { Diagnostics diagnostics; };
using SweepQueryDisposition = std::variant<SweepQueryNotRun, SweepQueryRejected, RecordedRunArtifact>;

struct SweepSelectionInput {
    std::uint64_t requested_count{};
    double distinctness_tolerance{};
    std::vector<Vector> directions;
    std::optional<std::uint64_t> seed;
};

struct SweepCaseInput {
    std::string scenario_id;
    ConfigId configuration;
    RecordedRunArtifact coarse_run;
    SweepSelectionInput selection;
    SweepQueryDisposition query;
};

enum class SweepMemorySupport {
    unlimited_accounting,
    active_workspace_reservations,
    active_and_retained_reservations,
    process_observation,
    operating_system_limit
};

struct SweepPhaseResources {
    ResourcePolicy requested;
    std::optional<std::uint64_t> executor_worker_threads_started;
    std::optional<std::uint64_t> peak_active_tasks;
    std::optional<std::uint64_t> backend_threads;
    std::optional<std::uint64_t> peak_workspace_reservation_bytes;
    std::optional<std::uint64_t> retained_result_reservation_bytes;
    std::optional<std::uint64_t> observed_process_memory_bytes;
    SweepMemorySupport memory_support{SweepMemorySupport::unlimited_accounting};
    std::string memory_observation_scope;
};

// A self-contained, inert two-phase sweep archive. Run artifacts remain the
// source of truth for mathematical outcomes; this manifest binds them to
// scenario identity, deterministic selection input, and phase resource facts.
class RecordedSweepArtifact {
public:
    RecordedSweepArtifact(const RecordedSweepArtifact&) = default;
    RecordedSweepArtifact& operator=(const RecordedSweepArtifact&) = default;
    const problem::ResolvedContent& content() const noexcept { return content_; }
    problem::ContentDigest identity() const noexcept { return content_.digest(); }
private:
    explicit RecordedSweepArtifact(problem::ResolvedContent content) : content_(std::move(content)) {}
    problem::ResolvedContent content_;
    friend ArtifactResult<RecordedSweepArtifact> encode_recorded_sweep(
        const problem::ResolvedContent&, std::string, const std::vector<SweepCaseInput>&,
        const SweepPhaseResources&, const SweepPhaseResources&, EncodeLimits);
    friend ArtifactResult<RecordedSweepArtifact> decode_recorded_sweep(std::string_view, DecodeLimits);
};

ArtifactResult<RecordedSweepArtifact> encode_recorded_sweep(
    const problem::ResolvedContent& canonical_spec, std::string run_id,
    const std::vector<SweepCaseInput>& cases,
    const SweepPhaseResources& coarse_resources,
    const SweepPhaseResources& query_resources,
    EncodeLimits limits = {});
ArtifactResult<RecordedSweepArtifact> decode_recorded_sweep(std::string_view, DecodeLimits = {});

} // namespace csl::artifacts
