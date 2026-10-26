#pragma once
#include <csl/execution/observability.hpp>
#include <cstdint>
#include <span>
#include <thread>

namespace csl::execution::observability {
// Read methods must not throw. The collector serializes reads, including injected clocks.
class TimingClock {
public:
    virtual ~TimingClock()=default;
    virtual artifacts::ClockDomain wall_domain() const=0;
    virtual std::optional<artifacts::ClockDomain> cpu_domain() const=0;
    virtual artifacts::Metric<std::int64_t> wall_now() noexcept=0;
    virtual artifacts::Metric<std::int64_t> cpu_now() noexcept=0;
};
std::shared_ptr<TimingClock> make_steady_timing_clock();
enum class TimingDiagnosticCode { incomplete_span, wall_clock_regressed, clock_unavailable,
    cpu_clock_regressed, cpu_thread_changed, child_outside_parent };
struct TimingDiagnostic { artifacts::SpanId span; TimingDiagnosticCode code; };
struct SpanTiming {
    artifacts::SpanId id;
    artifacts::Metric<std::uint64_t> inclusive_wall_ticks,exclusive_wall_ticks,cpu_ticks;
    // For thread CPU, this identifies the sampling thread; process CPU has no thread owner.
    std::optional<std::thread::id> cpu_thread;
};
struct TimingReport {
    artifacts::CollectedStatistics observations;
    artifacts::Metric<std::uint64_t> run_wall_ticks,worker_work_ticks;
    std::vector<SpanTiming> spans;
    std::optional<artifacts::ClockDomain> cpu_clock;
    std::vector<TimingDiagnostic> diagnostics;
};
class TimingCollector;
class TimingScope {
public:
    TimingScope() noexcept=default;
    TimingScope(TimingScope&&) noexcept;
    TimingScope& operator=(TimingScope&&) noexcept;
    ~TimingScope();
    TimingScope(const TimingScope&)=delete;
    TimingScope& operator=(const TimingScope&)=delete;
    // Explicit termination wins over automatic stop classification. Repeated close is inert.
    void close(Termination) noexcept;
    void close(Termination,std::shared_ptr<const GeometryEvidence>) noexcept;
    void close(Termination,std::shared_ptr<const GeometryEvidence>,std::optional<SetRelation>) noexcept;
    void observe_input_size(std::uint64_t) noexcept;
    void observe_output_size(std::uint64_t) noexcept;
    void mark_input_size_unavailable() noexcept;
    void mark_output_size_unavailable() noexcept;
    void close_not_called(artifacts::NotCalledReason,
        Termination=Termination::operation_rejected) noexcept;
    void close_not_called_with_detail(artifacts::NotCalledReason,std::string_view,
        Termination=Termination::operation_rejected) noexcept;
    void close() noexcept;
private:
    struct Owner;
    std::shared_ptr<Owner> owner_;
    std::size_t slot_{};
    std::stop_token cancellation_;
    std::optional<std::chrono::steady_clock::time_point> deadline_;
    int exceptions_{};
    TimingScope(std::shared_ptr<Owner>,std::size_t,const ExecutionContext&);
    friend class TimingCollector;
    friend CollectionResult<std::shared_ptr<TimingCollector>> make_timing_collector(
        CollectionPlan,std::shared_ptr<TimingClock>,artifacts::SpanId,std::vector<artifacts::SpanId>);
};
class TimingCollector {
public:
    CollectionResult<TimingScope> start(artifacts::SpanId,const ExecutionContext& = {});
    // Check a caller-owned layout before execution without sampling clocks or claiming spans.
    CollectionResult<bool> validate_unstarted(std::span<const artifacts::SpanId>) const;
    // Consistent snapshot; open/unstarted spans remain incomplete. Snapshots do not consume scopes.
    CollectionResult<TimingReport> snapshot() const;
    bool enabled() const noexcept;
private:
    std::shared_ptr<TimingScope::Owner> owner_;
    explicit TimingCollector(std::shared_ptr<TimingScope::Owner>);
    friend CollectionResult<std::shared_ptr<TimingCollector>> make_timing_collector(
        CollectionPlan,std::shared_ptr<TimingClock>,artifacts::SpanId,std::vector<artifacts::SpanId>);
};
// worker_spans must be unique descendants of run_span with no ancestor/descendant pair.
// All planned spans use the clock's wall domain; CPU is an optional separate report metric.
CollectionResult<std::shared_ptr<TimingCollector>> make_timing_collector(
    CollectionPlan,std::shared_ptr<TimingClock>,artifacts::SpanId run_span,
    std::vector<artifacts::SpanId> worker_spans);
CollectionResult<TimingScope> start_timing(const ExecutionContext&,artifacts::SpanId);
}
