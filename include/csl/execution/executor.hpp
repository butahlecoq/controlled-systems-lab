#pragma once
#include <csl/registry/registry.hpp>
#include <atomic>
#include <exception>
#include <span>

namespace csl::execution {
struct TaskId { std::string value; };
enum class Mode { sequential, bounded_parallel };
enum class CallStopSupport { cooperative_boundaries, noninterruptible, unspecified };
struct ResourceUse {
    std::size_t peak_compute_threads;
    std::string thread_assumptions;
    std::optional<std::size_t> workspace_reservation_bytes;
    CallStopSupport call_stop_support;
};
struct EnforcementRequest { bool require_native_thread_enforcement{false}, require_hard_memory_limit{false}; };
struct AdmissionLimit { std::optional<std::size_t> max_admitted_tasks; };
template<class Port> using Outcome = decltype(std::declval<registry::BoundWorkspace<Port>&>().run(std::declval<const ExecutionContext&>()));
enum class SkipReason { cancelled, deadline, task_limit, reservation_exceeds_budget, batch_failed };
enum class FailureStage { create, invoke };
enum class FailureKind { allocation, adapter_exception };
struct Skipped { SkipReason reason; };
struct TaskFailure { FailureStage stage; FailureKind kind; std::exception_ptr exception; };
template<class Port> struct Returned { Outcome<Port> value; };
template<class Port> using TaskOutcome = std::variant<Skipped,Returned<Port>,TaskFailure>;
using TimePoint = std::chrono::steady_clock::time_point;
struct TaskTiming {
    TimePoint queued_at;
    std::optional<TimePoint> admitted_at, create_started_at, create_finished_at;
    std::optional<TimePoint> call_started_at, call_finished_at, released_at;
};
template<class Port> struct TaskRecord {
    TaskId id;
    std::vector<registry::Provenance> provenance;
    ResourceUse declared_resources;
    TaskTiming timing;
    TaskOutcome<Port> outcome;
};
enum class BatchStopCause { cancelled, deadline, task_limit, allocation, adapter_exception, thread_launch };
struct AdmissionCloseObservation { BatchStopCause cause; TimePoint observed_at; };
struct BatchTiming {
    TimePoint started_at;
    std::optional<TimePoint> configured_deadline;
    std::optional<AdmissionCloseObservation> admission_closed;
    std::optional<TimePoint> external_cancellation_observed_at;
    TimePoint workers_joined_at, completed_at;
};
enum class OuterAdmissionEnforcement { enforced };
enum class NativeThreadEnforcement { declared_only };
enum class MemoryEnforcement { unlimited_accounting, active_reservations_only };
struct EnforcementReport {
    OuterAdmissionEnforcement outer_admission{OuterAdmissionEnforcement::enforced};
    NativeThreadEnforcement native_threads{NativeThreadEnforcement::declared_only};
    MemoryEnforcement memory{MemoryEnforcement::unlimited_accounting};
    std::size_t peak_active_tasks{}, peak_reserved_threads{};
    std::optional<std::size_t> peak_workspace_reservation_bytes;
};
template<class Port> struct BatchResult {
    std::string run_id;
    std::shared_ptr<const ResourcePolicy> resources;
    NumericalPolicy numerical;
    Mode mode;
    std::vector<TaskRecord<Port>> tasks;
    BatchTiming timing;
    EnforcementReport enforcement;
    std::exception_ptr launch_failure;
};
class Executor;
template<class Port> class Task;
template<class Port> std::variant<Task<Port>,Diagnostic> make_task(TaskId,const registry::PreparedPipeline<Port>&,const ResourceUse&);
std::variant<Task<registry::StrategyPort>,Diagnostic> make_task(TaskId,const registry::PreparedStrategy&,const ResourceUse&);
namespace detail {
std::optional<Diagnostic> check_task(const TaskId&,const ResourceUse&);
Diagnostics check_context(const ExecutionContext&,const std::shared_ptr<const ResourcePolicy>&,Mode);
// Internal synchronous binding: no public task accepts user callbacks or raw workspaces.
struct Job {
    const ResourceUse* resources;
    TaskTiming* timing;
    void* slot;
    void (*create)(void*);
    void (*invoke)(void*,const ExecutionContext&);
    void (*release)(void*) noexcept;
    void (*skip)(void*,SkipReason) noexcept;
    void (*fail)(void*,TaskFailure) noexcept;
};
struct Summary { BatchTiming timing; EnforcementReport enforcement; std::exception_ptr launch_failure; };
Summary dispatch(std::span<Job>,const ExecutionContext&,Mode,AdmissionLimit);
}
template<class Port> class Task {
    using Factory = std::function<std::unique_ptr<registry::BoundWorkspace<Port>>() >;
    struct Storage {
        TaskId id;
        ResourceUse resources;
        std::vector<registry::Provenance> provenance;
        Factory create;
    };
    std::shared_ptr<const Storage> storage_;
    Task(TaskId id,ResourceUse resources,std::vector<registry::Provenance> provenance,Factory create)
        : storage_(std::make_shared<const Storage>(Storage{std::move(id),std::move(resources),std::move(provenance),std::move(create)})) {}
    friend class Executor;
    template<class P> friend std::variant<Task<P>,Diagnostic> make_task(TaskId,const registry::PreparedPipeline<P>&,const ResourceUse&);
    friend std::variant<Task<registry::StrategyPort>,Diagnostic> make_task(TaskId,const registry::PreparedStrategy&,const ResourceUse&);
public:
    Task(const Task&) noexcept = default;
    Task& operator=(const Task&) noexcept = default;
    const TaskId& id() const noexcept { return storage_->id; }
    const ResourceUse& resources() const noexcept { return storage_->resources; }
    const std::vector<registry::Provenance>& provenance() const noexcept { return storage_->provenance; }
};
template<class Port> std::variant<Task<Port>,Diagnostic> make_task(TaskId id,const registry::PreparedPipeline<Port>& prepared,const ResourceUse& resources) {
    if (auto diagnostic=detail::check_task(id,resources)) return *diagnostic;
    auto provenance=prepared.provenance();
    return Task<Port>{std::move(id),resources,{provenance.begin(),provenance.end()},
        [prepared] { auto tuple=prepared.create(); return std::move(std::get<0>(tuple)); }};
}
inline std::variant<Task<registry::StrategyPort>,Diagnostic> make_task(TaskId id,const registry::PreparedStrategy& prepared,const ResourceUse& resources) {
    if (auto diagnostic=detail::check_task(id,resources)) return *diagnostic;
    return Task<registry::StrategyPort>{std::move(id),resources,prepared.provenance(),[prepared] { return prepared.create(); }};
}
class Executor {
    std::shared_ptr<const ResourcePolicy> resources_;
    std::atomic<bool> busy_{false};
    explicit Executor(const ResourcePolicy& resources) : resources_(std::make_shared<const ResourcePolicy>(resources)) {}
    friend std::variant<std::unique_ptr<Executor>,Diagnostics> make_executor(const ResourcePolicy&,EnforcementRequest);
public:
    Executor(const Executor&) = delete;
    Executor& operator=(const Executor&) = delete;
    std::shared_ptr<const ResourcePolicy> resources() const noexcept { return resources_; }
    template<class Port> std::variant<BatchResult<Port>,Diagnostics> run(std::span<const Task<Port>> tasks,const ExecutionContext& context,Mode mode,AdmissionLimit limit = {}) {
        static_assert(std::is_nothrow_move_constructible_v<Outcome<Port>>, "execution requires an owning, nothrow movable port outcome");
        if (busy_.exchange(true)) return Diagnostics{{DiagnosticCode::unsupported,"execution.busy","executor already has an active batch"}};
        struct Guard { std::atomic<bool>& busy; ~Guard() { busy.store(false); } } guard{busy_};
        auto diagnostics=detail::check_context(context,resources_,mode);
        for (std::size_t i=0;i<tasks.size();++i) {
            const auto& task=tasks[i];
            const auto field="execution.task."+task.id().value;
            if (task.resources().peak_compute_threads > resources_->threads_per_worker)
                diagnostics.push_back({DiagnosticCode::unsupported,field+".threads","declared aggregate exceeds lane capacity"});
            if (resources_->memory_bytes && !task.resources().workspace_reservation_bytes)
                diagnostics.push_back({DiagnosticCode::unsupported,field+".memory","finite credit cap requires a workspace reservation"});
            for (std::size_t j=0;j<i;++j) if (tasks[j].id().value==task.id().value)
                diagnostics.push_back({DiagnosticCode::invalid_input,field+".id","task IDs must be unique within a batch"});
        }
        if (!diagnostics.empty()) return diagnostics;
        const ExecutionContext frozen=context;
        BatchResult<Port> result{frozen.run_id,resources_,frozen.numerical,mode,{},{},{},{}};
        result.tasks.reserve(tasks.size());
        for (const auto& task:tasks)
            result.tasks.push_back({task.id(),task.provenance(),task.resources(),{},Skipped{SkipReason::batch_failed}});
        struct Slot {
            const Task<Port>* task;
            TaskRecord<Port>* record;
            std::unique_ptr<registry::BoundWorkspace<Port>> workspace;
        };
        std::vector<Slot> slots;
        std::vector<detail::Job> jobs;
        slots.reserve(tasks.size()); jobs.reserve(tasks.size());
        for (std::size_t i=0;i<tasks.size();++i) slots.push_back({&tasks[i],&result.tasks[i],{}});
        for (auto& slot:slots) jobs.push_back({&slot.record->declared_resources,&slot.record->timing,&slot,
            [](void* raw) { auto& s=*static_cast<Slot*>(raw); s.workspace=s.task->storage_->create(); },
            [](void* raw,const ExecutionContext& c) {
                auto& s=*static_cast<Slot*>(raw);
                s.record->outcome.template emplace<Returned<Port>>(s.workspace->run(c));
            },
            [](void* raw) noexcept { static_cast<Slot*>(raw)->workspace.reset(); },
            [](void* raw,SkipReason reason) noexcept { static_cast<Slot*>(raw)->record->outcome.template emplace<Skipped>(reason); },
            [](void* raw,TaskFailure failure) noexcept { static_cast<Slot*>(raw)->record->outcome.template emplace<TaskFailure>(std::move(failure)); }});
        auto summary=detail::dispatch(jobs,frozen,mode,limit);
        result.timing=summary.timing;
        result.enforcement=summary.enforcement;
        result.launch_failure=summary.launch_failure;
        return result;
    }
};
std::variant<std::unique_ptr<Executor>,Diagnostics> make_executor(const ResourcePolicy&,EnforcementRequest = {});
}
