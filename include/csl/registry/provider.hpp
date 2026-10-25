#pragma once
#include <csl/registry/registry.hpp>

namespace csl::registry {
// No concrete request or offer exists at this stage. Acceptance is conditional
// on every generated request satisfying the frozen requirements later.
template<class Port> struct ProviderSelection {
    const Registry<Port>& registry;
    Method method;
    Requirements requirements;
};
template<class Port> ProviderSelection<Port> select_provider(const Registry<Port>& registry,
    Method method,Requirements requirements={}) {
    return {registry,std::move(method),std::move(requirements)};
}
namespace detail {
template<class Port> struct CheckedProviderEntry {
    const Registration<Port>* entry;
    Requirements requirements;
    Provenance provenance;
};
}
template<class Port> class PreparedProvider {
    struct Storage {
        Registration<Port> entry;
        Requirements requirements;
        Provenance provenance;
    };
    std::shared_ptr<const Storage> storage_;
    explicit PreparedProvider(std::shared_ptr<const Storage> storage):storage_(std::move(storage)){}
    friend struct detail::ProviderAccess;
public:
    const Provenance& provenance() const noexcept {return storage_->provenance;}
    const Requirements& requirements() const noexcept {return storage_->requirements;}
    // There is deliberately no per-query Requirements parameter.
    std::variant<PreparedPipeline<Port>,Rejection> prepare(const typename Port::Request&) const;
};
// Borrows registrations until synchronous snapshot, like CheckedPipeline.
template<class... Ports> class CheckedProviders {
    std::tuple<detail::CheckedProviderEntry<Ports>...> entries_;
    explicit CheckedProviders(std::tuple<detail::CheckedProviderEntry<Ports>...> entries):entries_(std::move(entries)){}
    friend struct detail::ProviderAccess;
public:
    std::tuple<PreparedProvider<Ports>...> snapshot() const;
    std::vector<Provenance> provenance() const {
        return std::apply([](const auto&... entry){return std::vector<Provenance>{entry.provenance...};},entries_);
    }
};
namespace detail {
struct ProviderAccess {
    template<class Port> static std::variant<CheckedProviderEntry<Port>,Rejection> check(const ProviderSelection<Port>& s) {
        Provenance provenance{Port::name,s.method,{}};
        const auto found=s.registry.entries_.find(s.method.id.value);
        if(found==s.registry.entries_.end())return reject(provenance,"method","unknown method ID");
        const auto& entry=found->second;
        provenance.actual=entry.identity;
        if(s.method.version&&*s.method.version!=entry.identity.version)
            return reject(provenance,"method.version","requested version is unavailable");
        auto diagnostics=check_request_policy(s.requirements,static_cast<bool>(entry.basis_factory));
        if(!diagnostics.empty())return Rejection{provenance,std::move(diagnostics)};
        return CheckedProviderEntry<Port>{&entry,s.requirements,std::move(provenance)};
    }
    template<class... Ports> static std::variant<CheckedProviders<Ports...>,Rejection> check_all(const ProviderSelection<Ports>&... selections) {
        auto entries=std::tuple{check(selections)...};
        std::optional<Rejection> rejected;
        std::apply([&](const auto&... entry){
            ([&]{if(!rejected)if(const auto* r=std::get_if<Rejection>(&entry))rejected=*r;}(),...);
        },entries);
        if(rejected)return *rejected;
        return std::apply([](auto&... entry){
            return CheckedProviders<Ports...>{std::tuple<CheckedProviderEntry<Ports>...>{
                std::get<CheckedProviderEntry<Ports>>(std::move(entry))...}};
        },entries);
    }
    template<class Port> static PreparedProvider<Port> snapshot(const CheckedProviderEntry<Port>& checked) {
        using Storage=typename PreparedProvider<Port>::Storage;
        return PreparedProvider<Port>{std::make_shared<const Storage>(Storage{*checked.entry,checked.requirements,checked.provenance})};
    }
    template<class Port> static std::variant<PreparedPipeline<Port>,Rejection> prepare(
        const PreparedProvider<Port>& provider,const typename Port::Request& request) {
        const auto& storage=*provider.storage_;
        const auto capability=storage.entry.capabilities(request,storage.requirements);
        if(const auto* diagnostics=std::get_if<Diagnostics>(&capability))
            return capability_rejection(storage.provenance,*diagnostics);
        const auto offer=std::get<Offer>(capability);
        auto diagnostics=check_offer(offer,storage.requirements,static_cast<bool>(storage.entry.basis_factory));
        if(!diagnostics.empty())return Rejection{storage.provenance,std::move(diagnostics)};
        // Reuse the same checked-entry snapshot and factory path as fixed queries.
        const CheckedPipeline<Port> checked{std::tuple<CheckedEntry<Port>>{CheckedEntry<Port>{
            &storage.entry,&request,storage.requirements,storage.provenance,offer}}};
        return checked.snapshot();
    }
    template<class... Fixed,class... Generated,class Builder> static StrategyPlan compose(
        CheckedPipeline<Fixed...> fixed,CheckedProviders<Generated...> generated,Builder builder) {
        auto provenance=fixed.provenance();
        auto generated_provenance=generated.provenance();
        provenance.insert(provenance.end(),generated_provenance.begin(),generated_provenance.end());
        return StrategyPlan{[fixed=std::move(fixed),generated=std::move(generated),builder=std::move(builder)]() -> StrategyPlan::Factory {
            auto prepared_fixed=fixed.snapshot();
            auto prepared_generated=generated.snapshot();
            return [prepared_fixed=std::move(prepared_fixed),prepared_generated=std::move(prepared_generated),builder](
                const StrategyRequest& request,const Requirements& requirements) -> std::unique_ptr<SynthesisWorkspace> {
                return builder(prepared_fixed.create(),prepared_generated,request,requirements);
            };
        },std::move(provenance)};
    }
};
}
template<class Port> std::variant<PreparedPipeline<Port>,Rejection> PreparedProvider<Port>::prepare(const typename Port::Request& request) const {
    return detail::ProviderAccess::prepare(*this,request);
}
template<class... Ports> std::tuple<PreparedProvider<Ports>...> CheckedProviders<Ports...>::snapshot() const {
    return std::apply([](const auto&... entry){return std::tuple<PreparedProvider<Ports>...>{detail::ProviderAccess::snapshot(entry)...};},entries_);
}
template<class... Ports> std::variant<CheckedProviders<Ports...>,Rejection> check_providers(const ProviderSelection<Ports>&... selections) {
    return detail::ProviderAccess::check_all(selections...);
}
template<class Port> std::variant<PreparedProvider<Port>,Rejection> prepare_provider(const ProviderSelection<Port>& selection) {
    auto checked=check_providers(selection);
    if(const auto* rejected=std::get_if<Rejection>(&checked))return *rejected;
    return std::get<0>(std::get<CheckedProviders<Port>>(checked).snapshot());
}

enum class LPQueryNotRunReason { cancelled, deadline };
enum class LPQueryStopReason { cancelled, deadline_expired, resource_limit, numerical_failure };
struct LPQueryNotRun {
    ProgramIdentity request;
    Provenance provider;
    LPQueryNotRunReason reason;
};
struct LPQueryRejected {
    ProgramIdentity request;
    Rejection rejection;
};
struct LPQuerySolverUnsupported {
    ProgramIdentity request;
    Provenance provider;
    Diagnostics diagnostics;
};
struct LPQueryCompleted {
    ProgramIdentity request;
    ProgramIdentity returned_subject;
    Provenance provider;
    MathematicalOutcome outcome;
};
struct LPQueryStopped {
    ProgramIdentity request;
    Provenance provider;
    LPQueryStopReason reason;
};
using LPQueryRecord = std::variant<LPQueryNotRun,LPQueryRejected,
    LPQuerySolverUnsupported,LPQueryCompleted,LPQueryStopped>;

// Turns each generated LP into a fresh, admitted provider request. The provider
// is owned by value; its source registry may be destroyed after preparation.
// This exclusive runner intentionally executes one request at a time and keeps
// the request-specific workspace alive only for its synchronous solve.
class RegisteredLPQueryRunner final : public LPWorkspace {
    PreparedProvider<LPPort> provider_;
    std::vector<LPQueryRecord> records_;

    static std::optional<LPQueryNotRunReason> stopped(const ExecutionContext& context) {
        if(context.cancellation.stop_requested())return LPQueryNotRunReason::cancelled;
        if(context.deadline&&std::chrono::steady_clock::now()>=*context.deadline)
            return LPQueryNotRunReason::deadline;
        return std::nullopt;
    }
    static ProgramResult stopped_result(const LinearProgram& request,LPQueryNotRunReason reason) {
        const auto termination=reason==LPQueryNotRunReason::cancelled?
            Termination::cancelled:Termination::resource_limit;
        const auto diagnostic=reason==LPQueryNotRunReason::cancelled?
            "cancelled before generated LP execution":"deadline before generated LP execution";
        return {termination,{request.identity(),MathematicalOutcome::undetermined,Unestablished{},{}},
            {},{},diagnostic,{}};
    }
protected:
    ProgramOutcome do_solve(const LinearProgram& request,const ExecutionContext& context) override {
        if(const auto reason=stopped(context)) {
            const auto result=stopped_result(request,*reason);
            records_.emplace_back(LPQueryNotRun{request.identity(),provider_.provenance(),*reason});
            return result;
        }

        auto prepared_result=provider_.prepare(request);
        if(const auto* rejection=std::get_if<Rejection>(&prepared_result)) {
            records_.emplace_back(LPQueryRejected{request.identity(),*rejection});
            return Unsupported{rejection->diagnostics};
        }
        auto prepared=std::get<PreparedPipeline<LPPort>>(std::move(prepared_result));
        const auto provider=prepared.provenance()[0];
        if(const auto reason=stopped(context)) {
            const auto result=stopped_result(request,*reason);
            records_.emplace_back(LPQueryNotRun{request.identity(),provider,*reason});
            return result;
        }

        auto workspaces=prepared.create();
        auto outcome=std::get<0>(workspaces)->run(context);
        if(const auto* unsupported=std::get_if<Unsupported>(&outcome))
            records_.emplace_back(LPQuerySolverUnsupported{request.identity(),provider,unsupported->diagnostics});
        else {
            const auto& result=std::get<ProgramResult>(outcome);
            if(result.termination==Termination::operation_rejected || result.termination==Termination::contract_rejected)
                records_.emplace_back(LPQuerySolverUnsupported{request.identity(),provider,
                    {{DiagnosticCode::invalid_claim,"lp.termination","Synthesis-only termination is invalid for an LP result"}}});
            else if(result.termination==Termination::completed)
                records_.emplace_back(LPQueryCompleted{request.identity(),result.outcome.subject,provider,result.outcome.value});
            else {
                LPQueryStopReason reason=LPQueryStopReason::numerical_failure;
                switch(result.termination) {
                case Termination::cancelled: reason=LPQueryStopReason::cancelled; break;
                case Termination::deadline_expired: reason=LPQueryStopReason::deadline_expired; break;
                case Termination::resource_limit: reason=LPQueryStopReason::resource_limit; break;
                case Termination::numerical_failure: reason=LPQueryStopReason::numerical_failure; break;
                case Termination::operation_rejected: break; // handled before this branch
                case Termination::contract_rejected: break; // handled before this branch
                case Termination::completed: break;
                }
                records_.emplace_back(LPQueryStopped{request.identity(),provider,reason});
            }
        }
        return outcome;
    }
public:
    explicit RegisteredLPQueryRunner(PreparedProvider<LPPort> provider):provider_(std::move(provider)){}
    const std::vector<LPQueryRecord>& records() const noexcept {return records_;}
};

// Builder(fixed workspace tuple, prepared provider tuple, frozen strategy request,
// requirements). All borrows stay live through StrategyRegistry::prepare.
template<class... Fixed,class... Generated,class Builder> StrategyPlan compose_strategy(
    CheckedPipeline<Fixed...> fixed,CheckedProviders<Generated...> generated,Builder builder) {
    return detail::ProviderAccess::compose(std::move(fixed),std::move(generated),std::move(builder));
}
} // namespace csl::registry
