#pragma once

#include <csl/core/values.hpp>
#include <csl/core/diagnostics.hpp>
#include <atomic>
#include <chrono>
#include <memory>
#include <stop_token>

namespace csl {
struct ResourcePolicy {
    std::size_t total_threads, outer_workers, threads_per_worker;
    std::optional<std::size_t> memory_bytes; // admission/accounting, not enforced by this revision
};
struct NumericalPolicy { double absolute_tolerance, relative_tolerance; bool operator==(const NumericalPolicy&) const = default; };
namespace execution::observability { class TimingCollector; }
namespace execution {
// Thread-safe maximum scheduler width reported by native adapters during one
// execution scope. The executor creates it when absent and shares it with nested work.
class BackendThreadObservation {
    std::atomic<std::size_t> maximum_{};
public:
    void record(std::size_t threads) noexcept {
        auto current=maximum_.load(std::memory_order_relaxed);
        while(current<threads && !maximum_.compare_exchange_weak(current,threads,
            std::memory_order_relaxed,std::memory_order_relaxed)) {}
    }
    std::optional<std::size_t> maximum() const noexcept {
        const auto observed=maximum_.load(std::memory_order_relaxed);
        return observed ? std::optional<std::size_t>{observed} : std::nullopt;
    }
};
}
struct ExecutionContext {
    std::shared_ptr<const ResourcePolicy> resources; // same policy for all workers
    std::stop_token cancellation;
    std::optional<std::chrono::steady_clock::time_point> deadline;
    NumericalPolicy numerical{1e-8,1e-8};
    std::string run_id;
    std::shared_ptr<execution::observability::TimingCollector> timing{};
    // Shared by an executor and any nested native adapters in this run.
    std::shared_ptr<execution::BackendThreadObservation> backend_thread_observation{};
};
class ExclusiveWorkspace {
public:
    ExclusiveWorkspace() = default;
    ExclusiveWorkspace(const ExclusiveWorkspace&) = delete;
    ExclusiveWorkspace& operator=(const ExclusiveWorkspace&) = delete;
    virtual ~ExclusiveWorkspace() = default;
};
Diagnostics check_resources(const ResourcePolicy&);
} // namespace csl
