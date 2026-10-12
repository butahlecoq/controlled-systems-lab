#include "resolved_storage.hpp"
#include <algorithm>

namespace csl::problem {
ResolvedProblem::ResolvedProblem(std::shared_ptr<const detail::ResolvedStorage> storage):storage_(std::move(storage)) {}
ProblemId ResolvedProblem::identity() const {return storage_->description.id;}
std::string ResolvedProblem::authored_label() const {return storage_->label;}
std::shared_ptr<const Problem> ResolvedProblem::description() const noexcept {return {storage_,&storage_->description};}
model::LinearSystem ResolvedProblem::model() const {return storage_->model;}
ControlDomains ResolvedProblem::controls() const {return storage_->controls;}
InitialData ResolvedProblem::initial() const {return storage_->initial;}
ExternalData ResolvedProblem::external() const {return storage_->external;}
Constraints ResolvedProblem::constraints() const {return storage_->constraints;}
optimization::Objective ResolvedProblem::objective() const {return storage_->objective;}
std::shared_ptr<const std::vector<ContentBinding>> ResolvedProblem::content() const noexcept {return {storage_,&storage_->content};}
std::vector<std::byte> ResolvedProblem::canonical_bytes() const {return detail::encode_problem(storage_->description,storage_->content);}
PreparedResolvedStrategy::PreparedResolvedStrategy(ResolvedProblem p,registry::PreparedStrategy prepared):problem_(p),preparation_(std::move(prepared)) {}
ResolvedProblem PreparedResolvedStrategy::problem() const {return problem_;}
registry::PreparedStrategy PreparedResolvedStrategy::preparation() const {return preparation_;}
Resolution resolve(const Problem& authored,const ResolutionContext& context) {
    switch(context.uncertainty) {
    case UncertaintyStructure::stage_product_uncoupled: break;
    case UncertaintyStructure::correlated_history:
    case UncertaintyStructure::fixed_parameter:
    case UncertaintyStructure::initial_external_coupling:
    case UncertaintyStructure::state_or_parameter_dependent_dynamics:
        return Diagnostic{DiagnosticCode::unsupported,"problem.uncertainty.structure","this declaration cannot be represented by independent stage factors"};
    case UncertaintyStructure::unspecified:
    default:
        return Diagnostic{DiagnosticCode::invalid_input,"problem.uncertainty.structure","explicit stage-product and uncoupled initial/external intake is required"};
    }
    if(!authored.model) return Diagnostic{DiagnosticCode::invalid_input,"problem.model","model is required"};
    switch(authored.information) {
    case InformationPattern::nominal_open_loop: case InformationPattern::feedback: break;
    default: return Diagnostic{DiagnosticCode::invalid_input,"problem.information","unknown information pattern"};
    }
    switch(authored.model->dynamics.time_domain) {
    case TimeDomain::discrete: break;
    case TimeDomain::continuous: return Diagnostic{DiagnosticCode::unsupported,"model.time_domain","continuous-time publication is not implemented"};
    default: return Diagnostic{DiagnosticCode::invalid_input,"model.time_domain","unknown time domain"};
    }
    std::vector<ContentBinding> content(context.external_content.begin(),context.external_content.end());
    for(const auto& binding:content) {
        const auto key_character=[](unsigned char c) {
            return (c>='a' && c<='z') || (c>='A' && c<='Z') || (c>='0' && c<='9') ||
                c=='.' || c=='_' || c=='/' || c==':' || c=='-';
        };
        if(binding.key.empty() || !std::all_of(binding.key.begin(),binding.key.end(),key_character))
            return Diagnostic{DiagnosticCode::invalid_input,"problem.content.key","binding keys must use nonempty ASCII letters, digits, dot, underscore, slash, colon or hyphen"};
    }
    std::sort(content.begin(),content.end(),[](const auto& a,const auto& b){return a.key<b.key;});
    if(std::adjacent_find(content.begin(),content.end(),[](const auto& a,const auto& b){return a.key==b.key;})!=content.end())
        return Diagnostic{DiagnosticCode::invalid_input,"problem.content.key","duplicate binding keys are ambiguous"};
    Problem frozen=authored;
    frozen.model=std::make_shared<const SystemModel>(*authored.model);
    auto model_result=model::snapshot(*frozen.model,frozen.times);
    if(auto* failure=std::get_if<Diagnostic>(&model_result)) return *failure;
    const auto model=std::get<model::LinearSystem>(std::move(model_result));
    auto controls=snapshot_controls(frozen.controls,model);
    if(auto* failure=std::get_if<Diagnostic>(&controls)) return *failure;
    auto initial=snapshot_initial(frozen.initial,model);
    if(auto* failure=std::get_if<Diagnostic>(&initial)) return *failure;
    auto external=snapshot_external(frozen.external,model);
    if(auto* failure=std::get_if<Diagnostic>(&external)) return *failure;
    auto constraints=snapshot_constraints(frozen.states,frozen.temporal,model);
    if(auto* failure=std::get_if<Diagnostic>(&constraints)) return *failure;
    auto objective=optimization::snapshot(frozen.objective,context.objective_policy);
    if(auto* failure=std::get_if<Diagnostic>(&objective)) return *failure;
    if(auto* stopped=std::get_if<OperationStopped>(&objective)) return *stopped;
    if(std::get<optimization::Objective>(objective).dimension()!=model.dimensions().state)
        return Diagnostic{DiagnosticCode::invalid_input,"problem.objective.dimension","terminal objective dimension must match state dimension"};
    if(frozen.external) {
        if(const auto* adversarial=std::get_if<AdversarialExternalInput>(&*frozen.external)) {
            if(std::none_of(content.begin(),content.end(),[&](const auto& b){return b.key==adversarial->semantics_reference;}))
                return Diagnostic{DiagnosticCode::unsupported,"problem.external.semantics_reference","adversarial semantics require a binding to resolved content bytes"};
        }
    }
    const auto digest=detail::identity_digest(frozen,content);
    if(auto* failure=std::get_if<Diagnostic>(&digest)) return *failure;
    const auto label=frozen.id.value;
    frozen.id={"csl.problem.v1.sha256:"+hex(std::get<ContentDigest>(digest))};
    return detail::ResolvedAccess::problem(std::make_shared<const detail::ResolvedStorage>(
        std::move(frozen),label,model,std::get<ControlDomains>(controls),std::get<InitialData>(initial),
        std::get<ExternalData>(external),std::get<Constraints>(constraints),std::get<optimization::Objective>(objective),std::move(content)));
}
StrategyAdmission prepare_strategy(const ResolvedProblem& problem,const registry::StrategyRegistry& registry,
    const StrategyConfiguration& configuration,const FamilyRequest& family,
    const registry::Requirements& requirements,std::optional<std::string> version) {
    auto prepared=registry.prepare({problem,configuration,family,{}},requirements,std::move(version));
    if(auto* rejection=std::get_if<registry::Rejection>(&prepared)) return *rejection;
    return detail::ResolvedAccess::prepared(problem,std::get<registry::PreparedStrategy>(std::move(prepared)));
}
} // namespace csl::problem
