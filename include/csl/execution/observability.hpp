#pragma once
#include <csl/artifacts/run_statistics.hpp>
#include <csl/execution/executor.hpp>

namespace csl::execution::observability {
template<class T> using CollectionResult=artifacts::ArtifactResult<T>;
struct ShardId { std::uint64_t value; bool operator==(const ShardId&) const=default; };
struct PlanInput {
    problem::ResolvedProblem problem; artifacts::ResolvedConfiguration configuration;
    artifacts::RunId run; std::vector<artifacts::ClockDomain> clocks;
    std::vector<artifacts::SpanDescriptor> spans; std::uint64_t shard_count;
    std::vector<std::string> tasks{},operations{};
};
struct CollectionAccess;
class CollectionPlan {
public:
    CollectionPlan(const CollectionPlan&)=default;
    CollectionPlan& operator=(const CollectionPlan&)=default;
    const PlanInput& description() const noexcept;
private:
    struct Storage; std::shared_ptr<const Storage> storage_;
    explicit CollectionPlan(std::shared_ptr<const Storage>);
    friend struct CollectionAccess;
    friend class ObservationShard;
};
enum class ObservationState { returned, not_called, unknown };
enum class CompletionStatus { returned, rejected, skipped, failed, incomplete };
struct TickValue { bool available; std::int64_t value; artifacts::MissingReason missing; };
struct CountValue { bool available; std::uint64_t value; artifacts::MissingReason missing; };
struct SpanCompletionView {
    artifacts::SpanId id; TickValue start,end;
    ObservationState execution; artifacts::NotCalledReason not_called_reason;
    bool has_termination; Termination termination;
    CountValue iterations; std::string_view detail;
    CompletionStatus status{CompletionStatus::returned};
    bool has_outcome{false};MathematicalOutcome outcome{MathematicalOutcome::undetermined};
};
enum class RecordDisposition { retained, detail_dropped, detail_rejected, duplicate, wrong_shard, unknown_span };
class ObservationShard {
public:
    ObservationShard(ObservationShard&&) noexcept;
    ObservationShard& operator=(ObservationShard&&) noexcept;
    ~ObservationShard();
    ObservationShard(const ObservationShard&)=delete;
    ObservationShard& operator=(const ObservationShard&)=delete;
    RecordDisposition record(SpanCompletionView) noexcept;
    void record_overflow(std::uint64_t bucket,std::uint64_t count) noexcept;
private:
    struct Storage;std::unique_ptr<Storage> storage_;
    explicit ObservationShard(std::unique_ptr<Storage>);
    friend struct CollectionAccess;
};
CollectionResult<CollectionPlan> make_collection_plan(PlanInput);
CollectionResult<ObservationShard> make_observation_shard(const CollectionPlan&,ShardId);
CollectionResult<artifacts::CollectedStatistics> merge_observations(const CollectionPlan&,std::vector<ObservationShard>);
artifacts::ExecutionSummary project_execution(const BatchTiming&);
artifacts::ExecutionSummary::Task project_task(const TaskId&,const TaskTiming&,TimePoint origin,artifacts::SpanStatus);
artifacts::ResourceObservation project_resources(const EnforcementReport&);
}
