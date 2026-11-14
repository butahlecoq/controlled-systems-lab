#pragma once

#include <csl/geometry/hull_reducer.hpp>
#include <csl/registry/registry.hpp>

#include <algorithm>
#include <mutex>

namespace csl::geometry::detail {

class ChildLPTraceBuffer {
  public:
    static constexpr std::size_t record_limit = 4096;
    static constexpr std::size_t diagnostic_limit = 1024;

    void record(const LinearProgram &program, const ProgramOutcome &outcome,
                const registry::Provenance &provider) noexcept {
        try {
            std::lock_guard lock(mutex_);
            ++total_;
            if (records_.size() >= record_limit) {
                ++omitted_;
                return;
            }
            try {
                HullChildLPInvocation record;
                const auto &identity = program.identity();
                record.request = identity;
                record.requested_provider =
                    provider.requested.id.value +
                    (provider.requested.version ? "@" + *provider.requested.version : "");
                if (provider.actual) {
                    record.actual_provider = provider.actual->id.value;
                    record.actual_version = provider.actual->version;
                } else
                    record.actual_provider = "unresolved";
                if (const auto *unsupported = std::get_if<Unsupported>(&outcome)) {
                    record.status = "port_unsupported";
                    for (const auto &diagnostic : unsupported->diagnostics) {
                        append_diagnostic(record, diagnostic.field);
                        append_diagnostic(record, ": ");
                        append_diagnostic(record, diagnostic.explanation);
                    }
                } else {
                    const auto &result = std::get<ProgramResult>(outcome);
                    record.status = termination_name(result.termination);
                    record.outcome = mathematical_outcome_name(result.outcome.value);
                    append_diagnostic(record, result.raw_diagnostics);
                }
                records_.push_back(std::move(record));
            } catch (...) {
                ++omitted_;
                capture_failed_ = true;
            }
        } catch (...) {
            // The observer must never alter the reducer's LP execution.
        }
    }

    std::vector<HullChildLPInvocation> records() const {
        std::lock_guard lock(mutex_);
        return records_;
    }
    std::size_t total() const {
        std::lock_guard lock(mutex_);
        return total_;
    }
    std::size_t omitted() const {
        std::lock_guard lock(mutex_);
        return omitted_;
    }
    bool capture_failed() const {
        std::lock_guard lock(mutex_);
        return capture_failed_;
    }

  private:
    static void append_diagnostic(HullChildLPInvocation &record, std::string_view text) {
        if (text.empty())
            return;
        const auto remaining = diagnostic_limit - record.raw_diagnostics.size();
        const auto count = std::min(remaining, text.size());
        record.raw_diagnostics.append(text.substr(0, count));
        record.raw_diagnostics_truncated = record.raw_diagnostics_truncated || count < text.size();
    }
    static std::string_view termination_name(Termination termination) noexcept {
        switch (termination) {
        case Termination::completed:
            return "completed";
        case Termination::cancelled:
            return "cancelled";
        case Termination::deadline_expired:
            return "deadline_expired";
        case Termination::resource_limit:
            return "resource_limit";
        case Termination::numerical_failure:
            return "numerical_failure";
        case Termination::operation_rejected:
            return "operation_rejected";
        case Termination::contract_rejected:
            return "contract_rejected";
        }
        return "unknown";
    }
    static std::string_view mathematical_outcome_name(MathematicalOutcome outcome) noexcept {
        switch (outcome) {
        case MathematicalOutcome::optimal:
            return "optimal";
        case MathematicalOutcome::infeasible:
            return "infeasible";
        case MathematicalOutcome::unbounded:
            return "unbounded";
        case MathematicalOutcome::infimum_not_attained:
            return "infimum_not_attained";
        case MathematicalOutcome::undetermined:
            return "undetermined";
        }
        return "unknown";
    }

    mutable std::mutex mutex_;
    std::vector<HullChildLPInvocation> records_;
    std::size_t total_{};
    std::size_t omitted_{};
    bool capture_failed_{};
};

inline void trace_child_lp(registry::BoundWorkspace<registry::LPPort> &workspace,
                           const std::shared_ptr<ChildLPTraceBuffer> &trace,
                           registry::Provenance provider) {
    workspace.set_lp_query_observer(
        [trace, provider = std::move(provider)](const LinearProgram &program,
                                                const ProgramOutcome &outcome) noexcept {
            trace->record(program, outcome, provider);
        });
}

inline void append_child_lp_trace(HullReduction &reduction, const ChildLPTraceBuffer &trace) {
    auto records = trace.records();
    reduction.child_lp_invocations.insert(reduction.child_lp_invocations.end(),
                                          std::make_move_iterator(records.begin()),
                                          std::make_move_iterator(records.end()));
    reduction.child_lp_invocations_total += trace.total();
    reduction.child_lp_invocations_omitted += trace.omitted();
    reduction.child_lp_trace_capture_failed =
        reduction.child_lp_trace_capture_failed || trace.capture_failed();
}

} // namespace csl::geometry::detail
