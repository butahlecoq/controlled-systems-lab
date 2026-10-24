#include <csl/execution/instrumented_operation.hpp>

#include <variant>

namespace csl::execution::observability {
namespace {
bool same_module(const artifacts::ModuleIdentity& planned,
    const artifacts::ModuleIdentity& actual) noexcept {
    return planned.id==actual.id&&planned.version==actual.version;
}
bool same_optional_module(const std::shared_ptr<const artifacts::ModuleIdentity>& planned,
    const std::optional<artifacts::ModuleIdentity>& actual) noexcept {
    if(static_cast<bool>(planned)!=actual.has_value())return false;
    return !planned||same_module(*planned,*actual);
}
bool same_program(const std::shared_ptr<const ProgramIdentity>& planned,
    const std::optional<ProgramIdentity>& actual) noexcept {
    if(static_cast<bool>(planned)!=actual.has_value())return false;
    return !planned||*planned==*actual;
}
}

std::optional<TimingScope> start_operation_timing(const ExecutionContext& context,
    const OperationSpanIdentity& identity) noexcept {
    if(!context.timing||!context.timing->enabled())return {};
    try {
        const auto snapshot=context.timing->snapshot();
        const auto* report=std::get_if<TimingReport>(&snapshot);
        if(!report)return {};
        const artifacts::SpanDescriptor* match=nullptr;
        for(const auto& span:report->observations.description().spans) {
            const auto& descriptor=span.descriptor;
            if(descriptor.task!=identity.task||descriptor.operation!=identity.operation||
                !same_module(descriptor.module,identity.module)||!same_optional_module(descriptor.backend,identity.backend)||
                !same_program(descriptor.program,identity.program)||descriptor.stage!=identity.stage||
                descriptor.query!=identity.query)continue;
            if(match)return {};
            match=&descriptor;
        }
        if(!match)return {};
        auto started=start_timing(context,match->id);
        if(auto* scope=std::get_if<TimingScope>(&started))return std::move(*scope);
    } catch(...) {
        return {};
    }
    return {};
}

}
