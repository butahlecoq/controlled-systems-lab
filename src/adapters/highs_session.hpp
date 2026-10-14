#pragma once
// Private mechanics shared by the independent LP and convex adapters.
#include <csl/contracts.hpp>
#include <Highs.h>
#include <algorithm>
#include <chrono>
#include <optional>
#include <string>

namespace csl::adapters::highs_detail {
struct CallbackState {
    const ExecutionContext& context;
    std::optional<Termination> stop;
    std::string log;
    void poll() {
        if (stop) return;
        if (context.cancellation.stop_requested()) stop=Termination::cancelled;
        else if (context.deadline && std::chrono::steady_clock::now()>=*context.deadline)
            stop=Termination::resource_limit;
    }
};
// Each attempt borrows its execution context synchronously. The owner chooses
// whether a native warning is acceptable; LP and QP deliberately differ here.
// Callback detachment precedes destruction of the borrowed state, including
// partial activation failure. A guard cannot be copied to another session.
template<class Check> class CallbackGuard {
    Highs& native_;
public:
    CallbackGuard(Highs& native,CallbackState& state,Check check):native_(native) {
        try {
            check(native_.setCallback([](int type,const std::string& message,
                const HighsCallbackOutput*,HighsCallbackInput* input,void* user) {
                auto& capture=*static_cast<CallbackState*>(user);
                if (type==kCallbackLogging) capture.log+=message;
                if (type==kCallbackSimplexInterrupt) {
                    capture.poll();
                    if (input && capture.stop) input->user_interrupt=true;
                }
            },&state));
            check(native_.startCallback(kCallbackLogging));
            check(native_.startCallback(kCallbackSimplexInterrupt));
        } catch (...) {
            native_.setCallback(HighsCallbackFunctionType{},nullptr);
            throw;
        }
    }
    CallbackGuard(const CallbackGuard&)=delete;
    CallbackGuard& operator=(const CallbackGuard&)=delete;
    ~CallbackGuard() { native_.setCallback(HighsCallbackFunctionType{},nullptr); }
};
// Keep tolerance, iteration limits, solver selection, model clearing/reuse,
// warm starts and QP readback in each adapter's audited numerical profile.
template<class Check> void configure_common(Highs& h,Check check) {
    // HiGHS 1.11 requires log_to_console for callbacks; the active logging
    // callback captures these messages instead of writing to the console.
    check(h.setOptionValue("log_to_console",true));
    check(h.setOptionValue("output_flag",true));
    check(h.setOptionValue("presolve","off"));
    check(h.setOptionValue("parallel","off"));
    check(h.setOptionValue("threads",HighsInt{1}));
    check(h.setOptionValue("random_seed",HighsInt{0}));
    check(h.setOptionValue("allow_unbounded_or_infeasible",false));
    check(h.setOptionValue("small_matrix_value",1e-12));
    check(h.setOptionValue("large_matrix_value",kHighsInf));
    check(h.setOptionValue("infinite_bound",kHighsInf));
    check(h.setOptionValue("infinite_cost",kHighsInf));
}
template<class Check> double deadline(Highs& h,const ExecutionContext& c,Check check) {
    const double remaining=c.deadline?
        std::max(0.0,std::chrono::duration<double>(*c.deadline-std::chrono::steady_clock::now()).count()):kHighsInf;
    check(h.setOptionValue("time_limit",remaining));
    return remaining;
}
} // namespace csl::adapters::highs_detail
