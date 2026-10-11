#pragma once
#include <csl/execution/executor.hpp>
#include <condition_variable>
#include <mutex>

namespace csl::execution::detail {
// Per-batch state. All shared mutation is protected by mutex_; individual task
// slots have one worker. Never request_stop while holding this mutex.
class Batch {
    std::span<Job> jobs_;
    const ExecutionContext& caller_;
    AdmissionLimit limit_;
    std::mutex mutex_;
    std::condition_variable changed_;
    std::stop_source stop_;
    ExecutionContext child_;
    std::size_t next_{}, admitted_{}, active_{}, bytes_{};
    bool bytes_known_{true};
    std::optional<SkipReason> invocation_stop_;
    Summary summary_{};
    void close_locked(BatchStopCause);
    void observe_locked();
    std::optional<std::size_t> take();
    std::optional<SkipReason> before_invoke();
    void failure(BatchStopCause);
    void release(Job&);
public:
    Batch(std::span<Job>,const ExecutionContext&,AdmissionLimit);
    void external_cancel() noexcept;
    void worker() noexcept;
    void launch_failure(std::exception_ptr);
    void joined();
    Summary finish(); // only after callback deregistration/quiescence
};
}
