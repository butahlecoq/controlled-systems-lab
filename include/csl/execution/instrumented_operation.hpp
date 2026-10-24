#pragma once

#include <csl/execution/timing_collector.hpp>

#include <functional>
#include <optional>
#include <string_view>
#include <type_traits>
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
        using Result=std::invoke_result_t<Invoke>;
        static_assert(std::is_nothrow_invocable_r_v<Termination,TerminationOf,const Result&>,
            "operation termination classifiers must be noexcept and accept a const result");
        auto result=std::invoke(std::forward<Invoke>(invoke));
        if(scope_){
            auto evidence=geometry_evidence(result);
            scope_->close(std::invoke(std::forward<TerminationOf>(termination_of),std::as_const(result)),
                std::move(evidence),applied_relation(result));
            scope_.reset();
        }
        return result;
    }
private:
    template<class Value> static std::shared_ptr<const GeometryEvidence> copy_evidence(const Value& value) noexcept {
        if constexpr(requires{value.evidence;}) {
            try{return std::make_shared<const GeometryEvidence>(value.evidence);}catch(...){return {};}
        } else if constexpr(requires{value.result.evidence;}) {
            try{return std::make_shared<const GeometryEvidence>(value.result.evidence);}catch(...){return {};}
        } else return {};
    }
    template<class Result> static std::shared_ptr<const GeometryEvidence> geometry_evidence(const Result& result) noexcept {
        if constexpr(requires{result.relation_evidence;}) return result.relation_evidence;
        else if constexpr(requires{result.evidence;}) return copy_evidence(result);
        else if constexpr(requires{std::visit([](const auto& value){return copy_evidence(value);},result);}) {
            try{return std::visit([](const auto& value){return copy_evidence(value);},result);}catch(...){return {};}
        } else return {};
    }
    template<class Result> static std::optional<SetRelation> applied_relation(const Result& result) noexcept {
        if constexpr(requires{result.applied_relation;}) return result.applied_relation;
        else if constexpr(requires{result.relation;}) return result.relation;
        else if constexpr(requires{result.result.relation;}) return result.result.relation;
        else if constexpr(requires{std::visit([](const auto& value){return applied_relation(value);},result);}) {
            try{return std::visit([](const auto& value){return applied_relation(value);},result);}catch(...){return {};}
        }
        else return {};
    }
};

template<class Invoke,class TerminationOf>
auto run_instrumented_operation(const ExecutionContext& context,
    const OperationSpanIdentity& identity,Invoke&& invoke,TerminationOf&& termination_of) {
    return InstrumentedOperation{context,identity}.run(
        std::forward<Invoke>(invoke),std::forward<TerminationOf>(termination_of));
}

}
