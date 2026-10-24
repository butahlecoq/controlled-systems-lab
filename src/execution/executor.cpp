#include "detail.hpp"
#include <algorithm>
#include <cmath>
#include <limits>
#include <thread>

namespace csl::execution {
std::optional<Diagnostic> detail::check_task(const TaskId& id,const ResourceUse& use) {
    if (id.value.empty()) return Diagnostic{DiagnosticCode::invalid_input,"execution.task.id","nonempty task ID required"};
    if (!use.peak_compute_threads || use.thread_assumptions.empty())
        return Diagnostic{DiagnosticCode::unsupported,"execution.task."+id.value+".threads","positive aggregate thread count and configuration assumption required"};
    switch (use.call_stop_support) {
    case CallStopSupport::cooperative_boundaries: case CallStopSupport::noninterruptible: case CallStopSupport::unspecified: break;
    default: return Diagnostic{DiagnosticCode::invalid_input,"execution.task."+id.value+".stop_support","unknown declaration"};
    }
    return {};
}
Diagnostics detail::check_context(const ExecutionContext& c,const std::shared_ptr<const ResourcePolicy>& resources,Mode mode) {
    Diagnostics errors;
    if (c.resources!=resources || c.resources.owner_before(resources) || resources.owner_before(c.resources))
        errors.push_back({DiagnosticCode::invalid_input,"execution.resources","context must retain this executor's policy owner"});
    if (c.run_id.empty()) errors.push_back({DiagnosticCode::invalid_input,"execution.run_id","nonempty run ID required"});
    if (!std::isfinite(c.numerical.absolute_tolerance) || !std::isfinite(c.numerical.relative_tolerance) ||
        c.numerical.absolute_tolerance<0 || c.numerical.relative_tolerance<0)
        errors.push_back({DiagnosticCode::invalid_input,"execution.numerical","finite nonnegative tolerances required"});
    if (mode!=Mode::sequential && mode!=Mode::bounded_parallel)
        errors.push_back({DiagnosticCode::invalid_input,"execution.mode","unknown execution mode"});
    return errors;
}
std::variant<std::unique_ptr<Executor>,Diagnostics> make_executor(const ResourcePolicy& p,EnforcementRequest enforcement) {
    auto errors=check_resources(p);
    if (enforcement.require_native_thread_enforcement)
        errors.push_back({DiagnosticCode::unsupported,"execution.native_threads","only declared native thread use is available"});
    if (enforcement.require_hard_memory_limit)
        errors.push_back({DiagnosticCode::unsupported,"execution.memory","workspace credits do not enforce a native heap limit"});
    if (!errors.empty()) return errors;
    return std::unique_ptr<Executor>(new Executor(p));
}
namespace detail {
namespace {
using Clock=std::chrono::steady_clock;
SkipReason skipped(BatchStopCause cause) {
    switch(cause) {
    case BatchStopCause::cancelled: return SkipReason::cancelled;
    case BatchStopCause::deadline: return SkipReason::deadline;
    case BatchStopCause::task_limit: return SkipReason::task_limit;
    default: return SkipReason::batch_failed;
    }
}
}
Batch::Batch(std::span<Job> jobs,const ExecutionContext& caller,AdmissionLimit limit)
    : jobs_(jobs),caller_(caller),limit_(limit),child_(caller) {
    child_.cancellation=stop_.get_token();
    summary_.timing.started_at=Clock::now();
    summary_.timing.configured_deadline=caller.deadline;
    summary_.enforcement.memory=caller.resources->memory_bytes ? MemoryEnforcement::active_reservations_only : MemoryEnforcement::unlimited_accounting;
    for (auto& job:jobs_) {
        job.timing->queued_at=summary_.timing.started_at;
        if (!job.resources->workspace_reservation_bytes) bytes_known_=false;
    }
    if (bytes_known_) summary_.enforcement.peak_workspace_reservation_bytes=0;
}
void Batch::close_locked(BatchStopCause cause) {
    if (!summary_.timing.admission_closed) summary_.timing.admission_closed=AdmissionCloseObservation{cause,Clock::now()};
}
void Batch::observe_locked() {
    if (caller_.cancellation.stop_requested()) {
        close_locked(BatchStopCause::cancelled);
        if (!invocation_stop_) invocation_stop_=SkipReason::cancelled;
    } else if (caller_.deadline && Clock::now()>=*caller_.deadline) {
        close_locked(BatchStopCause::deadline);
        if (!invocation_stop_) invocation_stop_=SkipReason::deadline;
    }
}
void Batch::external_cancel() noexcept {
    const auto observed=Clock::now();
    {
        std::lock_guard lock(mutex_);
        if (!summary_.timing.external_cancellation_observed_at) summary_.timing.external_cancellation_observed_at=observed;
        close_locked(BatchStopCause::cancelled);
        if (!invocation_stop_) invocation_stop_=SkipReason::cancelled;
    }
    // Still record the external observation when this linked token was stopped
    // earlier by an adapter failure. Reentrant request_stop is harmless here.
    stop_.request_stop(); changed_.notify_all();
}
std::optional<std::size_t> Batch::take() {
    std::unique_lock lock(mutex_);
    for (;;) {
        observe_locked();
        if (summary_.timing.admission_closed) {
            const bool stop=invocation_stop_.has_value();
            lock.unlock();
            if (stop) stop_.request_stop();
            changed_.notify_all();
            return {};
        }
        if (next_==jobs_.size()) return {};
        if (limit_.max_admitted_tasks && admitted_>=*limit_.max_admitted_tasks) {
            close_locked(BatchStopCause::task_limit);
            changed_.notify_all();
            return {}; // Admission limit does not cancel already admitted work.
        }
        auto& job=jobs_[next_];
        const auto reservation=job.resources->workspace_reservation_bytes;
        const auto cap=caller_.resources->memory_bytes;
        if (cap && *reservation>*cap) {
            job.skip(job.slot,SkipReason::reservation_exceeds_budget);
            ++next_;
            continue;
        }
        if (cap && *reservation>*cap-bytes_) {
            if (caller_.deadline) changed_.wait_until(lock,*caller_.deadline);
            else changed_.wait(lock);
            continue;
        }
        const auto index=next_++;
        ++admitted_; ++active_;
        if (bytes_known_) {
            if (*reservation>std::numeric_limits<std::size_t>::max()-bytes_) {
                bytes_known_=false;
                summary_.enforcement.peak_workspace_reservation_bytes.reset();
            } else {
                bytes_+=*reservation;
                summary_.enforcement.peak_workspace_reservation_bytes=std::max(*summary_.enforcement.peak_workspace_reservation_bytes,bytes_);
            }
        }
        summary_.enforcement.peak_active_tasks=std::max(summary_.enforcement.peak_active_tasks,active_);
        summary_.enforcement.peak_reserved_threads=std::max(summary_.enforcement.peak_reserved_threads,active_*caller_.resources->threads_per_worker);
        job.timing->admitted_at=Clock::now();
        return index;
    }
}
std::optional<SkipReason> Batch::before_invoke() {
    std::optional<SkipReason> reason;
    {
        std::lock_guard lock(mutex_);
        observe_locked(); reason=invocation_stop_;
    }
    if (reason) { stop_.request_stop(); changed_.notify_all(); }
    return reason;
}
void Batch::failure(BatchStopCause cause) {
    {
        std::lock_guard lock(mutex_);
        close_locked(cause);
        if (!invocation_stop_) invocation_stop_=SkipReason::batch_failed;
    }
    stop_.request_stop(); changed_.notify_all();
}
void Batch::release(Job& job) {
    job.release(job.slot);
    {
        std::lock_guard lock(mutex_);
        --active_;
        if (bytes_known_) bytes_-=*job.resources->workspace_reservation_bytes;
        job.timing->released_at=Clock::now();
    }
    changed_.notify_all();
}
void Batch::worker() noexcept {
    while (const auto index=take()) {
        auto& job=jobs_[*index];
        auto stage=FailureStage::create;
        job.timing->create_started_at=Clock::now();
        try {
            job.create(job.slot);
            job.timing->create_finished_at=Clock::now();
            if (const auto reason=before_invoke()) job.skip(job.slot,*reason);
            else {
                stage=FailureStage::invoke;
                job.timing->call_started_at=Clock::now();
                job.invoke(job.slot,child_);
                job.timing->call_finished_at=Clock::now();
                (void)before_invoke(); // Observe stops without replacing returned evidence.
            }
        } catch (...) {
            const auto finished=Clock::now();
            if (stage==FailureStage::create) job.timing->create_finished_at=finished;
            else job.timing->call_finished_at=finished;
            const auto exception=std::current_exception();
            auto kind=FailureKind::adapter_exception;
            try { std::rethrow_exception(exception); } catch (const std::bad_alloc&) { kind=FailureKind::allocation; } catch (...) {}
            job.fail(job.slot,{stage,kind,exception});
            failure(kind==FailureKind::allocation ? BatchStopCause::allocation : BatchStopCause::adapter_exception);
        }
        release(job);
    }
}
void Batch::launch_failure(std::exception_ptr exception) {
    summary_.launch_failure=exception;
    failure(BatchStopCause::thread_launch);
}
void Batch::joined() { summary_.timing.workers_joined_at=Clock::now(); }
Summary Batch::finish() {
    // No worker or external callback remains; unfinished slots were never claimed.
    for (;next_<jobs_.size();++next_) {
        auto& job=jobs_[next_];
        job.skip(job.slot,summary_.timing.admission_closed ? skipped(summary_.timing.admission_closed->cause) : SkipReason::batch_failed);
    }
    summary_.timing.completed_at=Clock::now();
    return summary_;
}
Summary dispatch(std::span<Job> jobs,const ExecutionContext& context,Mode mode,AdmissionLimit limit) {
    Batch batch(jobs,context,limit);
    std::vector<std::jthread> workers;
    const auto lanes=mode==Mode::sequential ? std::size_t{0} : std::min(jobs.size(),context.resources->outer_workers);
    workers.reserve(lanes); // All collector capacity before factories/launch.
    {
        std::stop_callback callback(context.cancellation,[&batch]() noexcept { batch.external_cancel(); });
        if (mode==Mode::sequential) batch.worker();
        else {
            try { for (std::size_t i=0;i<lanes;++i) workers.emplace_back([&batch] { batch.worker(); }); }
            catch (...) { batch.launch_failure(std::current_exception()); }
            for (auto& worker:workers) worker.join();
        }
        batch.joined();
    } // Callback destruction waits for in-flight notification outside scheduler lock.
    auto summary=batch.finish();
    summary.enforcement.outer_worker_threads_started=workers.size();
    return summary;
}
}
}
