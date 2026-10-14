#pragma once

#include <csl/core/values.hpp>
#include <csl/core/diagnostics.hpp>
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
struct ExecutionContext {
    std::shared_ptr<const ResourcePolicy> resources; // same policy for all workers
    std::stop_token cancellation;
    std::optional<std::chrono::steady_clock::time_point> deadline;
    NumericalPolicy numerical{1e-8,1e-8};
    std::string run_id;
    std::shared_ptr<execution::observability::TimingCollector> timing{};
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
