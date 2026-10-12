#include <csl/registry/registry.hpp>

namespace csl::registry {
StrategyRequest StrategyPort::snapshot(const Request& request) {
    auto result = request;
    if (request.problem.model)
        result.problem.model = std::make_shared<const SystemModel>(*request.problem.model);
    return result;
}
std::optional<Rejection> StrategyRegistry::add(StrategyRegistration entry) {
    Provenance provenance{StrategyPort::name,{entry.identity.id,entry.identity.version},entry.identity};
    if (entry.identity.id.value.empty() || entry.identity.version.empty() || !entry.capabilities || !entry.planner)
        return detail::reject(provenance,"registration","identity, version, capabilities and planner are required");
    const auto found = entries_.find(entry.identity.id.value);
    if (found != entries_.end()) {
        provenance.actual = found->second.identity;
        return detail::reject(provenance,"registration","method ID already registered");
    }
    entries_.emplace(entry.identity.id.value,std::move(entry));
    return {};
}
std::variant<PreparedStrategy,Rejection> StrategyRegistry::prepare(const StrategyRequest& request,
    const Requirements& requirements, std::optional<std::string> version) const {
    Provenance provenance{StrategyPort::name,{request.configuration.strategy,std::move(version)},{}};
    const auto found = entries_.find(request.configuration.strategy.value);
    if (found == entries_.end()) return detail::reject(provenance,"method","unknown strategy ID");
    const auto& entry = found->second;
    provenance.actual = entry.identity;
    if (provenance.requested.version && *provenance.requested.version != entry.identity.version)
        return detail::reject(provenance,"method.version","requested strategy version is unavailable");
    const auto capability = entry.capabilities(request,requirements);
    if (const auto* diagnostics = std::get_if<Diagnostics>(&capability)) return detail::capability_rejection(provenance,*diagnostics);
    auto diagnostics = detail::check_offer(std::get<Offer>(capability),requirements,false);
    if (!diagnostics.empty()) return Rejection{provenance,std::move(diagnostics)};
    auto planned = entry.planner(request,requirements);
    if (const auto* rejection = std::get_if<Rejection>(&planned)) return *rejection;
    auto& plan = std::get<StrategyPlan>(planned);
    auto records = plan.provenance_;
    records.insert(records.begin(),provenance);
    // Every pure dependency/transition check has succeeded. Only now copy numerical requests.
    auto snapshot = std::make_shared<const StrategyRequest>(StrategyPort::snapshot(request));
    auto factory = plan.snapshot_();
    return PreparedStrategy{std::move(snapshot),requirements,std::move(factory),std::move(records)};
}
namespace detail {
namespace {
Diagnostics compare_output(const Output& actual, const Output& required, const std::string& prefix) {
    auto failure = [&](const char* field, const char* reason) -> Diagnostics {
        return {{DiagnosticCode::unsupported,prefix+field,reason}};
    };
    if (actual.representation.value != required.representation.value)
        return failure("representation","selected output representation is incompatible");
    if (actual.assurance != required.assurance)
        return failure("assurance","selected output assurance is incompatible");
    if (required.relation && actual.relation != required.relation)
        return failure("relation","selected output relation is incompatible");
    if (required.family && actual.family != required.family)
        return failure("family","selected output family scope is incompatible");
    if (required.completeness && actual.completeness != required.completeness)
        return failure("completeness","selected output completeness is not established at the requested level");
    return {};
}
}
Diagnostics check_request_policy(const Requirements& required, bool has_basis) {
    if (required.scalar != Scalar::binary64)
        return {{DiagnosticCode::unsupported,"scalar","only binary64 buffers are supported"}};
    if (required.output.assurance == Assurance::validated)
        return {{DiagnosticCode::unsupported,"output.assurance","revision 1.1 has no validated evidence interface"}};
    if (required.basis_diagnostics && !has_basis)
        return {{DiagnosticCode::unsupported,"basis","selected method has no basis diagnostics factory"}};
    return {};
}
Diagnostics check_offer(const Offer& offer, const Requirements& required, bool has_basis) {
    auto diagnostics=check_request_policy(required,has_basis);
    if (!diagnostics.empty()) return diagnostics;
    return compare_output(offer.output,required.output,"output.");
}
Diagnostics check_transition(const Output& actual, const Output& required) {
    return compare_output(actual,required,"transition.");
}
Rejection reject(Provenance provenance, std::string field, std::string reason) {
    return {std::move(provenance),{{DiagnosticCode::unsupported,std::move(field),std::move(reason)}}};
}
Rejection capability_rejection(Provenance provenance, Diagnostics diagnostics) {
    if (diagnostics.empty()) return reject(std::move(provenance),"capability","capability callback rejected without diagnostics");
    return {std::move(provenance),std::move(diagnostics)};
}
}
} // namespace csl::registry
