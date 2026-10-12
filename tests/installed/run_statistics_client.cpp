#include <csl/artifacts/run_statistics.hpp>
#include <csl/execution/observability.hpp>
#include <iostream>
#include <stdexcept>

namespace ar=csl::artifacts;
namespace ob=csl::execution::observability;
template<class T>T accepted(ar::ArtifactResult<T> value) {
    if(const auto* error=std::get_if<ar::ArtifactError>(&value))throw std::runtime_error(error->path+": "+error->message);
    return std::get<T>(std::move(value));
}
int main(){
    try {
        using namespace csl;
        Problem input{{"zero"},std::make_shared<const SystemModel>(SystemModel{{{0,0,0},TimeDomain::discrete,
            LinearStage{{0,0,{}},{0,0,{}},{0,0,{}},{}}},{}}),{0},KnownInitial{{}},ContinuousDomain{{}},
            {UniversalSet{0}},{},{},InformationPattern::nominal_open_loop,LinearTerminal{{},0}};
        const auto resolved=problem::resolve(input,{problem::UncertaintyStructure::stage_product_uncoupled});
        if(!std::holds_alternative<problem::ResolvedProblem>(resolved))return 1;
        const auto problem=std::get<problem::ResolvedProblem>(resolved);
        ar::ConfigurationInput config{};config.collection={false,ar::CollectionMode::detail,4,4096,3,4096};
        const ar::Unavailable unknown{ar::MissingReason::not_instrumented,""};
        config.modules={{"lp",{{"lp-a"},"1",unknown},{}},{"strategy",{{"joint"},"1",unknown},{}}};
        config.numerical={0,0};config.resources={2,2,1,{}};
        config.output={ar::OutputKind::synthesis,Assurance::numerical,FamilyTarget::exact_optimal_relation,{"joint"},{1,0,{},{}}};
        config.selector={{"first"},"1",{}};config.strategy={{"joint"},{"lp-a"},{},{},{},{},{},{"first"},{"joint"}};config.workspace=ar::WorkspacePolicy::fresh;
        const auto configuration=accepted(ar::resolve_configuration(config));
        const auto plan=accepted(ob::make_collection_plan({problem,configuration,{"prefix-only"},{},{},0}));
        const auto statistics=accepted(ob::merge_observations(plan,{}));
        ar::RunRecord record{problem.identity(),{0,0,0},0,configuration,{"prefix-only"},ar::SkippedFinal{ar::SkippedReason::cancelled},statistics,
            {unknown,unknown,unknown,unknown,true,ar::MemoryAccounting::unlimited},{},{},ar::ProblemProvenance::problem_revalidated};
        const auto owner=accepted(ar::publish_run({problem,record}));
        const ClaimEvidence feasibility{problem.identity(),SymbolicArgument{"zero-dimensional feasible history","resolved zero problem"}};
        FamilyIdentity family_id{problem.identity(),{"nominal",problem.identity(),FamilyTarget::candidate_relaxation,{0,0},Assurance::numerical,{"joint"},{}},{{0,0,0},0},{"joint"},"1",{}};
        auto published=FamilyPublisher::publish(family_id,CandidateFamily{{family_id.coordinates,{"joint"},{}},HeuristicRelationEvidence{"installed client"},RelationFeasibilityEvidence{feasibility}});
        if(!std::holds_alternative<OptimalFamily>(published))return 4;
        SynthesisResult synthesis{Termination::completed,{problem.identity(),MathematicalOutcome::undetermined,Unestablished{},{}},{},
            std::get<OptimalFamily>(std::move(published)),{},{}};
        const auto projected=ar::project_final(synthesis);
        if(!projected.family||projected.family->family.identity()!=family_id||
           !std::holds_alternative<CandidateFamily>(projected.family->family.outcome()))return 4;
        auto wire=accepted(ar::encode_run(owner));const auto restored=accepted(ar::decode_run(wire));wire.assign(1000,'x');config.modules.clear();
        if(restored.description().problem.value!="csl.problem.v1.sha256:2320a9f596bfa8f5bdd8aa6d272ca96fe5ff229411b65e1ab3e6f469a27f815e" ||
            restored.description().configuration.identity().value!="csl.config.v1.sha256:58af261ea42c3dc78dad8a7d1e037de2df3747a9342b1a4e77d771c6bf598411" ||
            std::get<ar::SkippedFinal>(restored.description().final).reason!=ar::SkippedReason::cancelled ||
            restored.description().provenance!=ar::ProblemProvenance::identity_recorded)return 2;
        std::cout<<"Installed statistics client: immutable identities and portable lifetime round trip passed\n";
        return 0;
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 3;}
}
