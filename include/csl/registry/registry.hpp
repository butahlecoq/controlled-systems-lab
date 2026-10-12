#pragma once

#include <csl/contracts.hpp>
#include <array>
#include <functional>
#include <map>
#include <stdexcept>
#include <tuple>
#include <type_traits>
#include <utility>

namespace csl::registry {
// Compatible-toolchain source interface; see docs/contracts/registry.md for the
// callback purity, borrowed preparation lifetime and immutable payload contracts.
struct Identity { ModuleId id; std::string version; };
struct Method { ModuleId id; std::optional<std::string> version; };
struct Provenance { std::string port; Method requested; std::optional<Identity> actual; };
struct Rejection { Provenance provenance; Diagnostics diagnostics; };
enum class Scalar { binary64, binary32, exact, interval };
enum class Completeness { unestablished, established };
struct Output {
    RepresentationId representation;
    Assurance assurance{Assurance::numerical};
    std::optional<SetRelation> relation;
    std::optional<FamilyTarget> family;
    std::optional<Completeness> completeness;
};
struct Requirements {
    Scalar scalar{Scalar::binary64};
    Output output;
    bool basis_diagnostics{false};
};
struct Offer { Output output; };
using Capability = std::variant<Offer, Diagnostics>;
struct Transition { std::size_t producer; Output required; };
struct SelectorRequest { OptimalFamily family; WitnessRequest selection; };
struct StrategyRequest { Problem problem; StrategyConfiguration configuration; };

struct LPPort {
    using Request = LinearProgram; using Workspace = LPWorkspace;
    static constexpr const char* name = "lp";
    static Request snapshot(const Request& r) { return r; }
    static ProgramOutcome run(Workspace& w, const Request& r, const ExecutionContext& c) { return w.solve(r,c); }
};
struct ConvexPort {
    using Request = ConvexProgram; using Workspace = ConvexWorkspace;
    static constexpr const char* name = "convex";
    static Request snapshot(const Request& r) { return r; }
    static ProgramOutcome run(Workspace& w, const Request& r, const ExecutionContext& c) { return w.solve(r,c); }
};
struct GeometryPort {
    using Request = OperationRequest; using Workspace = SetOperatorWorkspace;
    static constexpr const char* name = "geometry";
    static Request snapshot(const Request& r) { return r; }
    static OperationOutcome run(Workspace& w, const Request& r, const ExecutionContext& c) { return w.apply(r,c); }
};
struct ConversionPort {
    using Request = ConversionRequest; using Workspace = RepresentationConverterWorkspace;
    static constexpr const char* name = "conversion";
    static Request snapshot(const Request& r) { return r; }
    static SetTransformOutcome run(Workspace& w, const Request& r, const ExecutionContext& c) { return w.convert(r,c); }
};
struct ApproximationPort {
    using Request = ApproximationRequest; using Workspace = SetApproximatorWorkspace;
    static constexpr const char* name = "approximation";
    static Request snapshot(const Request& r) { return r; }
    static SetTransformOutcome run(Workspace& w, const Request& r, const ExecutionContext& c) { return w.approximate(r,c); }
};
struct SelectorPort {
    using Request = SelectorRequest; using Workspace = WitnessSelectorWorkspace;
    static constexpr const char* name = "selector";
    static Request snapshot(const Request& r) { return r; }
    static std::variant<WitnessSelection, Unsupported> run(Workspace& w, const Request& r, const ExecutionContext& c) {
        return w.select(r.family,r.selection,c);
    }
};
struct StrategyPort {
    using Request = StrategyRequest; using Workspace = SynthesisWorkspace;
    static constexpr const char* name = "strategy";
    static Request snapshot(const Request&);
    static SynthesisOutcome run(Workspace& w, const Request& r, const ExecutionContext& c) { return w.solve(r.problem,c); }
};

template<class Port> struct Registration {
    Identity identity;
    std::function<Capability(const typename Port::Request&, const Requirements&)> capabilities;
    std::function<std::unique_ptr<typename Port::Workspace>(const typename Port::Request&)> factory;
    // The diagnostic may borrow this particular workspace; BoundWorkspace destroys
    // diagnostics before the mathematical workspace. No cross-creation state is shared.
    std::function<std::unique_ptr<BasisDiagnostics>(const typename Port::Request&, typename Port::Workspace&)> basis_factory{};
};
namespace detail {
struct PipelineAccess;
Diagnostics check_offer(const Offer&, const Requirements&, bool has_basis);
Diagnostics check_transition(const Output&, const Output&);
Rejection reject(Provenance, std::string field, std::string reason);
Rejection capability_rejection(Provenance, Diagnostics);
}
template<class Port> class Registry {
    std::map<std::string, Registration<Port>> entries_;
    friend struct detail::PipelineAccess;
public:
    std::optional<Rejection> add(Registration<Port> entry) {
        const Method requested{entry.identity.id,entry.identity.version};
        Provenance provenance{Port::name,requested,entry.identity};
        if (entry.identity.id.value.empty() || entry.identity.version.empty() || !entry.capabilities || !entry.factory)
            return detail::reject(provenance,"registration","identity, version, capability and factory are required");
        const auto found = entries_.find(entry.identity.id.value);
        if (found != entries_.end()) {
            provenance.actual = found->second.identity;
            return detail::reject(provenance,"registration","method ID already registered");
        }
        entries_.emplace(entry.identity.id.value,std::move(entry));
        return {};
    }
};
// Borrows request and registry until synchronous preparation (including snapshot)
// finishes. The producer must keep both stable throughout that interval.
template<class Port> struct Selection {
    const Registry<Port>& registry;
    Method method;
    const typename Port::Request& request;
    Requirements requirements;
    std::vector<Transition> inputs;
};
template<class Port> Selection<Port> select(const Registry<Port>& registry, Method method,
    const typename Port::Request& request, Requirements requirements = {}, std::vector<Transition> inputs = {}) {
    return {registry,std::move(method),request,std::move(requirements),std::move(inputs)};
}

template<class Port> class BoundWorkspace final : public ExclusiveWorkspace {
    std::shared_ptr<const typename Port::Request> request_;
    std::unique_ptr<typename Port::Workspace> workspace_;
    std::unique_ptr<BasisDiagnostics> basis_;
    friend struct detail::PipelineAccess;
    BoundWorkspace(std::shared_ptr<const typename Port::Request> request,
        std::unique_ptr<typename Port::Workspace> workspace, std::unique_ptr<BasisDiagnostics> basis)
        : request_(std::move(request)), workspace_(std::move(workspace)), basis_(std::move(basis)) {
        if (!workspace_) throw std::logic_error("registered factory returned a null workspace");
    }
public:
    auto run(const ExecutionContext& context) { return Port::run(*workspace_,*request_,context); }
    const BasisDiagnostics* basis() const { return basis_.get(); }
    const WorkspaceIdentity& workspace_identity() const noexcept requires std::is_same_v<Port,LPPort> {
        return workspace_->workspace_identity();
    }
    const std::optional<SolveAttempt>& last_attempt() const noexcept requires std::is_same_v<Port,LPPort> {
        return workspace_->last_attempt();
    }
    const WorkspaceIdentity& workspace_identity() const noexcept requires std::is_same_v<Port,ConvexPort> {
        return workspace_->workspace_identity();
    }
    const std::optional<ConvexSolveAttempt>& last_attempt() const noexcept requires std::is_same_v<Port,ConvexPort> {
        return workspace_->last_attempt();
    }
};
namespace detail {
template<class Port> struct CheckedEntry {
    const Registration<Port>* entry;
    const typename Port::Request* request;
    Requirements requirements;
    Provenance provenance;
    Offer offer;
};
template<class Port> struct PreparedEntry {
    Registration<Port> entry;
    std::shared_ptr<const typename Port::Request> request;
    Requirements requirements;
    Provenance provenance;
};
}
template<class... Ports> class PreparedPipeline {
    std::tuple<detail::PreparedEntry<Ports>...> entries_;
    friend struct detail::PipelineAccess;
    explicit PreparedPipeline(std::tuple<detail::PreparedEntry<Ports>...> entries) : entries_(std::move(entries)) {}
public:
    std::array<Provenance,sizeof...(Ports)> provenance() const {
        return std::apply([](const auto&... entries) { return std::array<Provenance,sizeof...(Ports)>{entries.provenance...}; },entries_);
    }
    std::tuple<std::unique_ptr<BoundWorkspace<Ports>>...> create() const;
};
template<class... Ports> class CheckedPipeline {
    std::tuple<detail::CheckedEntry<Ports>...> entries_;
    friend struct detail::PipelineAccess;
    explicit CheckedPipeline(std::tuple<detail::CheckedEntry<Ports>...> entries) : entries_(std::move(entries)) {}
public:
    // For registered planner composition. Input borrows remain live and unchanged
    // until snapshot returns; CheckedPipeline is not a retained prepared result.
    PreparedPipeline<Ports...> snapshot() const;
    std::vector<Provenance> provenance() const {
        return std::apply([](const auto&... e) { return std::vector<Provenance>{e.provenance...}; },entries_);
    }
};
namespace detail {
struct PipelineAccess {
    template<class Port> static std::unique_ptr<BoundWorkspace<Port>> create(const PreparedEntry<Port>& e) {
        auto workspace = e.entry.factory(*e.request);
        if (!workspace) throw std::logic_error("registered factory returned a null workspace");
        auto basis = e.requirements.basis_diagnostics ? e.entry.basis_factory(*e.request,*workspace) : nullptr;
        if (e.requirements.basis_diagnostics && !basis) throw std::logic_error("basis factory returned null");
        return std::unique_ptr<BoundWorkspace<Port>>(new BoundWorkspace<Port>(e.request,std::move(workspace),std::move(basis)));
    }
    template<class Port> static std::unique_ptr<BoundWorkspace<Port>> bind(
        std::shared_ptr<const typename Port::Request> request, std::unique_ptr<typename Port::Workspace> workspace) {
        return std::unique_ptr<BoundWorkspace<Port>>(new BoundWorkspace<Port>(std::move(request),std::move(workspace),nullptr));
    }
    template<class Port> static PreparedEntry<Port> snapshot_entry(const CheckedEntry<Port>& e) {
        return {*e.entry,std::make_shared<const typename Port::Request>(Port::snapshot(*e.request)),e.requirements,e.provenance};
    }
    template<class... Ports> static PreparedPipeline<Ports...> snapshot(const CheckedPipeline<Ports...>& checked) {
        return std::apply([](const auto&... e) {
            return PreparedPipeline<Ports...>{std::tuple<PreparedEntry<Ports>...>{
                snapshot_entry(e)...}};
        },checked.entries_);
    }
    template<class Port> static std::variant<CheckedEntry<Port>,Rejection> check_entry(const Selection<Port>& s) {
        Provenance provenance{Port::name,s.method,{}};
        const auto found = s.registry.entries_.find(s.method.id.value);
        if (found == s.registry.entries_.end()) return reject(provenance,"method","unknown method ID");
        const auto& entry = found->second;
        provenance.actual = entry.identity;
        if (s.method.version && *s.method.version != entry.identity.version)
            return reject(provenance,"method.version","requested version is unavailable");
        const auto capability = entry.capabilities(s.request,s.requirements);
        if (const auto* diagnostics = std::get_if<Diagnostics>(&capability)) return capability_rejection(provenance,*diagnostics);
        const auto offer = std::get<Offer>(capability);
        auto diagnostics = check_offer(offer,s.requirements,static_cast<bool>(entry.basis_factory));
        if (!diagnostics.empty()) return Rejection{provenance,std::move(diagnostics)};
        return CheckedEntry<Port>{&entry,&s.request,s.requirements,provenance,offer};
    }
    template<class... Ports> static std::variant<CheckedPipeline<Ports...>,Rejection> check(const Selection<Ports>&... s) {
        auto entries = std::tuple{check_entry(s)...};
        std::optional<Rejection> rejection;
        std::apply([&](const auto&... e) {
            ([&] { if (!rejection) if (const auto* r = std::get_if<Rejection>(&e)) rejection = *r; }(),...);
        },entries);
        if (rejection) return *rejection;
        const auto offers = std::apply([](const auto&... e) {
            return std::array<Offer,sizeof...(Ports)>{std::get<CheckedEntry<Ports>>(e).offer...};
        },entries);
        const auto provenances = std::apply([](const auto&... e) {
            return std::array<Provenance,sizeof...(Ports)>{std::get<CheckedEntry<Ports>>(e).provenance...};
        },entries);
        std::size_t index = 0;
        ([&] {
            for (const auto& transition : s.inputs) {
                if (rejection) break;
                if (transition.producer >= index) {
                    rejection = reject(provenances[index],"transition.producer","producer must precede its consumer");
                    break;
                }
                auto diagnostics = check_transition(offers[transition.producer].output,transition.required);
                if (!diagnostics.empty()) rejection = Rejection{provenances[index],std::move(diagnostics)};
            }
            ++index;
        }(),...);
        if (rejection) return *rejection;
        return std::apply([](auto&... e) {
            return CheckedPipeline<Ports...>{std::tuple<CheckedEntry<Ports>...>{std::get<CheckedEntry<Ports>>(std::move(e))...}};
        },entries);
    }
};
}
template<class... Ports> auto check_pipeline(const Selection<Ports>&... selections) {
    return detail::PipelineAccess::check(selections...);
}
template<class... Ports> auto prepare_pipeline(const Selection<Ports>&... selections)
    -> std::variant<PreparedPipeline<Ports...>,Rejection> {
    auto checked = check_pipeline(selections...);
    if (auto* rejection = std::get_if<Rejection>(&checked)) return *rejection;
    return std::get<CheckedPipeline<Ports...>>(checked).snapshot();
}
template<class... Ports> PreparedPipeline<Ports...> CheckedPipeline<Ports...>::snapshot() const {
    return detail::PipelineAccess::snapshot(*this);
}
template<class... Ports> std::tuple<std::unique_ptr<BoundWorkspace<Ports>>...> PreparedPipeline<Ports...>::create() const {
    return std::apply([](const auto&... e) { return std::tuple<std::unique_ptr<BoundWorkspace<Ports>>...>{detail::PipelineAccess::create(e)...}; },entries_);
}

class StrategyPlan {
    using Factory = std::function<std::unique_ptr<SynthesisWorkspace>(const StrategyRequest&,const Requirements&)>;
    std::function<Factory()> snapshot_;
    std::vector<Provenance> provenance_;
    StrategyPlan(std::function<Factory()> snapshot, std::vector<Provenance> provenance)
        : snapshot_(std::move(snapshot)), provenance_(std::move(provenance)) {}
    template<class... Ports,class Builder> friend StrategyPlan compose_strategy(CheckedPipeline<Ports...>,Builder);
    friend class StrategyRegistry;
};
template<class... Ports,class Builder> StrategyPlan compose_strategy(CheckedPipeline<Ports...> checked, Builder builder) {
    auto provenance = checked.provenance();
    return StrategyPlan{[checked=std::move(checked),builder=std::move(builder)]() -> StrategyPlan::Factory {
        auto prepared = checked.snapshot();
        return [prepared=std::move(prepared),builder](const StrategyRequest& request,const Requirements& requirements) -> std::unique_ptr<SynthesisWorkspace> {
            return builder(prepared.create(),request,requirements);
        };
    },std::move(provenance)};
}
struct StrategyRegistration {
    Identity identity;
    std::function<Capability(const StrategyRequest&,const Requirements&)> capabilities;
    // Pure planning only: declare every required typed dependency with
    // check_pipeline, then compose_strategy. No prepare/create/native work here.
    std::function<std::variant<StrategyPlan,Rejection>(const StrategyRequest&,const Requirements&)> planner;
};
class PreparedStrategy {
    std::shared_ptr<const StrategyRequest> request_;
    Requirements requirements_;
    std::function<std::unique_ptr<SynthesisWorkspace>(const StrategyRequest&,const Requirements&)> factory_;
    std::vector<Provenance> provenance_;
    friend class StrategyRegistry;
    PreparedStrategy(std::shared_ptr<const StrategyRequest> request, Requirements requirements,
        std::function<std::unique_ptr<SynthesisWorkspace>(const StrategyRequest&,const Requirements&)> factory, std::vector<Provenance> provenance)
        : request_(std::move(request)),requirements_(std::move(requirements)),factory_(std::move(factory)),provenance_(std::move(provenance)) {}
public:
    const std::vector<Provenance>& provenance() const { return provenance_; }
    const Requirements& requirements() const { return requirements_; }
    std::unique_ptr<BoundWorkspace<StrategyPort>> create() const {
        return detail::PipelineAccess::bind<StrategyPort>(request_,factory_(*request_,requirements_));
    }
};
class StrategyRegistry {
    std::map<std::string,StrategyRegistration> entries_;
public:
    std::optional<Rejection> add(StrategyRegistration);
    std::variant<PreparedStrategy,Rejection> prepare(const StrategyRequest&, const Requirements& = {},
        std::optional<std::string> version = {}) const;
};
} // namespace csl::registry
