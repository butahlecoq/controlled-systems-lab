#pragma once

#include <csl/execution/timing_collector.hpp>

#include <functional>
#include <optional>
#include <string_view>
#include <utility>

namespace csl::execution::observability {

struct OperationSpanIdentity {
    std::string_view task;
    std::string_view operation;
    artifacts::ModuleIdentity module;
    std::optional<artifacts::ModuleIdentity> backend;
    std::optional<ProgramIdentity> program;
    std::optional<std::uint64_t> stage;
    std::optional<std::uint64_t> query;
};

std::optional<TimingScope> start_operation_timing(
    const ExecutionContext&, const OperationSpanIdentity&) noexcept;

class InstrumentedOperation {
    std::optional<TimingScope> scope_;
public:
    InstrumentedOperation(const ExecutionContext& context,const OperationSpanIdentity& identity)
        :scope_(start_operation_timing(context,identity)){}
    void not_called(artifacts::NotCalledReason reason) noexcept {
        if(scope_){scope_->close_not_called(reason);scope_.reset();}
    }
    template<class Invoke,class TerminationOf>
    auto run(Invoke&& invoke,TerminationOf&& termination_of) {
        auto result=std::invoke(std::forward<Invoke>(invoke));
        if(scope_){scope_->close(std::invoke(std::forward<TerminationOf>(termination_of),result));scope_.reset();}
        return result;
    }
};

template<class Invoke,class TerminationOf>
auto run_instrumented_operation(const ExecutionContext& context,
    const OperationSpanIdentity& identity,Invoke&& invoke,TerminationOf&& termination_of) {
    return InstrumentedOperation{context,identity}.run(
        std::forward<Invoke>(invoke),std::forward<TerminationOf>(termination_of));
}

}
