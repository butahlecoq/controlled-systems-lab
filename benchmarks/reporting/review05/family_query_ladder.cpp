#include <csl/adapters/convex/highs.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <csl/adapters/polyhedral/qhull.hpp>
#include <csl/geometry/affine_sum.hpp>
#include <csl/execution/observability.hpp>
#include <csl/execution/timing_collector.hpp>
#include <csl/input/scenario_loader.hpp>
#include <csl/synthesis/strategy_a/strategy.hpp>
#include <csl/synthesis/strategy_a/nominal_linear_exact_profile.hpp>
#include <bit>
#include <sstream>
#include <cmath>
#include <fstream>
#include <csl/synthesis/strategy_b/direct_joint.hpp>
#include <csl/synthesis/witness_selector.hpp>
#include <csl/registry/registry.hpp>

#include <algorithm>
#include <chrono>
#include <iomanip>
#include <iostream>
#include <limits>
#include <locale>
#include <memory>
#include <stdexcept>
#include <string>
#include <string_view>
#include <type_traits>
#include <variant>

namespace {
using namespace csl;
using namespace csl::registry;

template<class T, class... Errors>
T take(std::variant<T, Errors...> value, std::string_view stage) {
    if (auto* result = std::get_if<T>(&value)) return std::move(*result);
    std::visit([](const auto& error) {
        if constexpr(requires{error.path;error.message;})std::cerr<<error.path<<": "<<error.message<<'\n';
    },value);
    throw std::runtime_error(std::string(stage) + " was rejected");
}

template<class Port>
PreparedProvider<Port> selected(Registration<Port> registration, std::string representation) {
    Registry<Port> registry;
    const Method method{registration.identity.id, {}};
    if (registry.add(std::move(registration))) throw std::runtime_error("provider registration failed");
    Requirements requirements;
    requirements.output.representation = {std::move(representation)};
    if constexpr (std::is_same_v<Port, GeometryPort> || std::is_same_v<Port, ConversionPort>)
        requirements.output.relation = SetRelation::equivalent;
    return take(prepare_provider(select_provider(registry, method, requirements)), "provider selection");
}

std::string json_quote(std::string_view value) {
    std::string result{"\""};
    for (const char character : value) {
        if (character == '\\' || character == '"') result.push_back('\\');
        if (character == '\n') { result += "\\n"; continue; }
        if (character == '\r') { result += "\\r"; continue; }
        result.push_back(character);
    }
    result.push_back('"');
    return result;
}

const char* termination_name(Termination value) {
    switch (value) {
    case Termination::completed: return "completed";
    case Termination::operation_rejected: return "operation_rejected";
    case Termination::contract_rejected: return "contract_rejected";
    case Termination::cancelled: return "cancelled";
    case Termination::deadline_expired: return "deadline_expired";
    case Termination::resource_limit: return "resource_limit";
    case Termination::numerical_failure: return "numerical_failure";
    }
    return "unknown";
}

const char* outcome_name(MathematicalOutcome value) {
    switch (value) {
    case MathematicalOutcome::optimal: return "optimal";
    case MathematicalOutcome::infeasible: return "infeasible";
    case MathematicalOutcome::unbounded: return "unbounded";
    case MathematicalOutcome::infimum_not_attained: return "infimum_not_attained";
    case MathematicalOutcome::undetermined: return "undetermined";
    }
    return "unknown";
}

void vector_json(std::ostream& out, std::span<const double> values) {
    out << '[';
    for (std::size_t index = 0; index < values.size(); ++index) {
        if (index) out << ',';
        out << values[index];
    }
    out << ']';
}

void matrix_json(std::ostream& out, const numeric::MatrixView& matrix) {
    out << '[';
    for (std::size_t row = 0; row < matrix.rows(); ++row) {
        if (row) out << ',';
        out << '[';
        for (std::size_t column = 0; column < matrix.cols(); ++column) {
            if (column) out << ',';
            out << matrix(row, column);
        }
        out << ']';
    }
    out << ']';
}

void h_relation_json(std::ostream& out, const sets::SetData& relation) {
    const auto metadata = relation.metadata();
    const auto representation = relation.representation();
    const auto* h = std::get_if<sets::HRepresentation>(&representation);
    if (!h) {
        out << "null";
        return;
    }
    out << "{\"id\":" << json_quote(metadata->id.value) << ",\"dimension\":"
        << metadata->set.dimension << ",\"labels\":[";
    for (std::size_t index = 0; index < metadata->coordinate_labels.size(); ++index) {
        if (index) out << ',';
        out << json_quote(metadata->coordinate_labels[index]);
    }
    out << "],\"inequalities\":";
    matrix_json(out, h->inequalities);
    out << ",\"upper_bounds\":";
    vector_json(out, h->upper_bounds.values());
    out << ",\"equalities\":";
    matrix_json(out, h->equalities);
    out << ",\"equality_values\":";
    vector_json(out, h->equality_values.values());
    out << '}';
}

void witness_json(std::ostream& out, const Witness& witness) {
    out << "{\"problem_id\":"<<json_quote(witness.problem.value)<<",\"states\":[";
    for (std::size_t index = 0; index < witness.states.size(); ++index) {
        if (index) out << ',';
        vector_json(out, witness.states[index]);
    }
    out << "],\"controls\":[";
    for (std::size_t index = 0; index < witness.controls.size(); ++index) {
        if (index) out << ',';
        vector_json(out, witness.controls[index]);
    }
    out << "],\"original_objective\":" << witness.original_objective << '}';
}

void bound_json(std::ostream& out, const std::optional<ObjectiveBound>& bound) {
    if (bound) out << bound->value;
    else out << "null";
}
namespace ar=artifacts;
namespace ob=execution::observability;
std::shared_ptr<ob::TimingCollector> collector(const problem::ResolvedProblem& resolved,
    const FamilyRequest& family,const StrategyConfiguration& strategy,
    const WitnessRequest& selection,const OptimalFamily* source,
    const registry::Identity& lp_identity,const registry::Identity& convex_identity) {
    const ar::Unavailable missing{ar::MissingReason::not_instrumented,{}};
    const ar::ModuleIdentity sm{strategy.strategy,"1",missing};
    const ar::ModuleIdentity lm{lp_identity.id,lp_identity.version,missing};
    const ar::ModuleIdentity wm{{synthesis::witness_selector::selector_id},"1",missing};
    ar::ConfigurationInput config;
    config.collection={true,ar::CollectionMode::detail,128,1<<20,128,1<<20};
    config.modules={{"strategy",sm,{}},{"lp",lm,{}},{"convex",{convex_identity.id,convex_identity.version,missing},{}},{"selector",wm,{}}};
    config.numerical=family.numerical;config.resources={1,1,1,{}};
    config.output={ar::OutputKind::synthesis,family.assurance,family.target,family.representation,
        {selection.count,selection.distinctness_tolerance,selection.directions,selection.seed}};
    config.selector={wm.id,wm.version,{}};config.strategy=strategy;config.strategy.selector=wm.id;
    auto configuration=take(ar::resolve_configuration(std::move(config)),"timing configuration");
    auto clock=ob::make_steady_timing_clock();
    ob::PlanInput plan{resolved,std::move(configuration),{source?"selector":"synthesis"},
        {clock->wall_domain()},{},1};
    const auto add=[&](std::uint64_t id,std::string task,std::string operation,
        const ar::ModuleIdentity& module,std::optional<ProgramIdentity> program={},
        std::optional<std::uint64_t> query={},std::optional<std::uint64_t> parent={}) {
        if(std::find(plan.tasks.begin(),plan.tasks.end(),task)==plan.tasks.end())plan.tasks.push_back(task);
        if(std::find(plan.operations.begin(),plan.operations.end(),operation)==plan.operations.end())plan.operations.push_back(operation);
        ar::SpanDescriptor span{};span.id={id};
        if(id)span.parent=ar::SpanParent{{parent.value_or(0)},ar::ParentKind::nested};
        span.task=std::move(task);span.operation=std::move(operation);span.module=module;
        span.clock=clock->wall_domain().id;span.requested_assurance=family.assurance;
        span.applied_assurance=ar::Available<Assurance>{family.assurance};span.query=query;
        span.observation_source="review05-actual-family-query-operation";
        if(program) {span.program=std::make_shared<const ProgramIdentity>(*program);span.backend=std::make_shared<const ar::ModuleIdentity>(lm);}
        plan.spans.push_back(std::move(span));
    };
    if(source) {
        add(0,"selector","selector/run",wm);
        for(std::size_t i=0;i<selection.directions.size();++i) {
            auto id="witness-selector-direction/"+std::to_string(i);
            for(double x:selection.directions[i])id+="/"+std::to_string(std::bit_cast<std::uint64_t>(x));
            add(i+1,"selector","selector.lp.direction-query",wm,
                ProgramIdentity{resolved.identity(),{id}},i);
        }
    } else if(strategy.strategy.value=="csl.synthesis.reach-back") {
        const std::vector<std::string> operations={"strategy-a/run","strategy-a/forward","strategy-a/feasible-preimage",
            "strategy-a/terminal-optimization","strategy-a/terminal-preimage","strategy-a/family-construction"};
        for(std::size_t i=0;i<operations.size();++i)add(i,"strategy-a",operations[i],sm);
    } else {
        add(0,"strategy-b","strategy-b/run",sm);add(1,"strategy-b","strategy-b/family-construction",sm);
        add(2,"strategy-b","strategy-b/program-build",sm);
        auto joint=take(synthesis::strategy_b::build_joint_program(resolved,family),"timed B program");
        const auto identity=std::visit([](const auto& p){return p.identity();},joint.program);
        add(3,"strategy-b","strategy-b/program-solve",sm,identity);
        add(4,"strategy-b","strategy-b/joint-h-assembly",sm,{},{},2);
        add(5,"strategy-b","strategy-b/objective-lift",sm,{},{},2);
        add(6,"strategy-b","strategy-b/program-freeze",sm,{},{},2);
    }
    auto plan_value=take(ob::make_collection_plan(std::move(plan)),"timing plan");
    return take(ob::make_timing_collector(std::move(plan_value),clock,{0},{}),"timing collector");
}
void timing_json(std::ostream& out,const ob::TimingReport& report) {
    const auto& collection=report.observations.description();const auto& clock=collection.clocks.front();
    out<<"{\"period_numerator\":"<<clock.period_numerator<<",\"period_denominator\":"<<clock.period_denominator<<",\"spans\":[";
    for(std::size_t i=0;i<report.spans.size();++i) {
        if(i)out<<',';
        const auto& time=report.spans[i];const auto& row=collection.spans.at(static_cast<std::size_t>(time.id.value));
        out<<"{\"id\":"<<time.id.value<<",\"parent\":";
        if(row.descriptor.parent)out<<row.descriptor.parent->id.value;else out<<"null";
        const auto* interval=std::get_if<ar::TickInterval>(&row.interval);
        out<<",\"start_tick\":";
        if(interval) {if(const auto* value=std::get_if<ar::Available<std::int64_t>>(&interval->start))out<<value->value;else out<<"null";}else out<<"null";
        out<<",\"end_tick\":";
        if(interval) {if(const auto* value=std::get_if<ar::Available<std::int64_t>>(&interval->end))out<<value->value;else out<<"null";}else out<<"null";
        out<<",\"module\":"<<json_quote(row.descriptor.module.id.value)<<",\"module_version\":"<<json_quote(row.descriptor.module.version)<<",\"backend_version\":"<<(row.descriptor.backend?json_quote(row.descriptor.backend->version):"null")<<",\"operation\":"<<json_quote(row.descriptor.operation)<<",\"completed\":"<<(row.completion_observed?"true":"false")<<",\"ticks\":";
        if(const auto* t=std::get_if<ar::Available<std::uint64_t>>(&time.inclusive_wall_ticks))out<<t->value;else out<<"null";
        out<<",\"query\":";if(row.descriptor.query)out<<*row.descriptor.query;else out<<"null";
        out<<",\"program\":";if(row.descriptor.program)out<<json_quote(row.descriptor.program->program.value);else out<<"null";
        out<<",\"input_size\":";if(row.descriptor.input_size)out<<*row.descriptor.input_size;else out<<"null";
        out<<",\"output_size\":";if(row.descriptor.output_size)out<<*row.descriptor.output_size;else out<<"null";
        out<<",\"termination\":";
        if(const auto* status=std::get_if<ar::ReturnedSpan>(&row.status))out<<json_quote(termination_name(status->termination));else out<<"null";
        out<<'}';
    }
    out<<"]}";
}
using Clock=std::chrono::steady_clock;
std::int64_t elapsed(Clock::time_point start) {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-start).count();
}
void diagnostics_json(std::ostream& out,const Diagnostics& diagnostics) {
    out<<'[';for(std::size_t i=0;i<diagnostics.size();++i) {if(i)out<<',';out<<json_quote(diagnostics[i].field+": "+diagnostics[i].explanation);}out<<']';
}
}
int main(int argc,char** argv) try {
    if(argc<4||argc>5)throw std::runtime_error("usage: family_query_ladder scenario strategy {on|off} [materialization-limit]");
    const std::string strategy_id=argv[2];const bool instrumented=std::string_view(argv[3])=="on";
    if((strategy_id!="csl.synthesis.reach-back"&&strategy_id!="csl.synthesis.strategy-b")||
       (std::string_view(argv[3])!="on"&&std::string_view(argv[3])!="off"))throw std::runtime_error("invalid strategy/instrumentation mode");
    const auto loaded=input::load_scenario_file(argv[1]);
    const auto* scenario=std::get_if<input::LoadedScenario>(&loaded);
    if(!scenario)throw std::runtime_error("scenario load rejected");
    const auto& resolved=scenario->problem();const auto horizon=resolved.model().horizon();
    if(resolved.model().dimensions()!=Dimensions{1,1,0}||(horizon!=2&&horizon!=4&&horizon!=8))throw std::runtime_error("unsupported scalar horizon");
    const std::string path=argv[1];const bool flat=path.find("family-query-flat")!=std::string::npos;
    auto lp=take(adapters::lp::make_highs_registration(),"LP registration");
    auto convex=take(adapters::convex::make_highs_registration(),"convex registration");
    auto converter=take(adapters::polyhedral::make_qhull_registration(lp),"conversion registration");
    auto projection=geometry::polyhedral::make_projection_registration();
    auto affine=geometry::make_affine_sum_registration({selected(geometry::make_lp_hull_reducer_registration(),""),selected(lp,"csl.program-result.v1"),selected(converter,"csl.polyhedron.v")});
    Registry<GeometryPort> projections,affines;Registry<ConversionPort> conversions;Registry<LPPort> lps;Registry<ConvexPort> convexes;
    const Method pm{projection.identity.id,{}},am{affine.identity.id,{}},cm{converter.identity.id,{}},lm{lp.identity.id,{}},qm{convex.identity.id,{}};
    if(projections.add(projection)||affines.add(affine)||conversions.add(converter)||lps.add(lp)||convexes.add(convex))throw std::runtime_error("registration failed");
    Requirements h,v,program;h.output.representation={"csl.polyhedron.h"};h.output.relation=SetRelation::equivalent;
    v.output.representation={"csl.polyhedron.v"};v.output.relation=SetRelation::equivalent;program.output.representation={"csl.program-result.v1"};
    auto providers=take(check_providers(select_provider(projections,pm,h),select_provider(affines,am,v),select_provider(conversions,cm,h),select_provider(lps,lm,program),select_provider(convexes,qm,program)),"A providers");
    auto query_provider=take(prepare_provider(select_provider(lps,lm,program)),"query LP");
    StrategyRegistry strategies;
    if(strategies.add(synthesis::strategy_a::make_registration(std::move(providers)))||strategies.add(synthesis::strategy_b::make_registration(lps,convexes)))throw std::runtime_error("strategy registration failed");
    FamilyRequest family;family.profile=strategy_id=="csl.synthesis.reach-back"?synthesis::strategy_a::nominal_linear_exact_profile:synthesis::strategy_b::nominal_linear_exact_profile;
    family.objective=resolved.identity();family.target=FamilyTarget::exact_optimal_relation;family.representation={"csl.polyhedron.h"};family.assurance=Assurance::numerical;
    if(argc==5)family.materialization_limit=std::stoull(argv[4]);
    StrategyConfiguration config;config.strategy={strategy_id};config.lp=lp.identity.id;config.convex=convex.identity.id;config.representation=family.representation;
    WitnessRequest selection{flat?2*horizon:1u,1e-9,{},31};
    for(std::size_t k=0;k<horizon;++k) {Vector direction(horizon,0);direction[k]=1;selection.directions.push_back(direction);direction[k]=-1;selection.directions.push_back(std::move(direction));}
    Requirements output;output.output.representation=family.representation;output.output.family=family.target;output.output.completeness=Completeness::established;
    const StrategyRequest request{resolved,config,family,"1",{}};
    const auto begin=Clock::now();auto prepared_outcome=strategies.prepare(request,output);const auto prepare_ns=elapsed(begin);
    std::cout.imbue(std::locale::classic());std::cout<<std::setprecision(std::numeric_limits<double>::max_digits10);
    std::cout<<"{\"schema\":\"csl.review05.family-query/1\",\"fixture\":"<<json_quote(flat?"FAMILY-QUERY-FLAT":"HORIZON-01")<<",\"horizon\":"<<horizon
        <<",\"problem_id\":"<<json_quote(resolved.identity().value)<<",\"scenario_sha256\":"<<json_quote(problem::hex(scenario->source()->content.digest()))
        <<",\"strategy\":"<<json_quote(strategy_id)<<",\"strategy_version\":\"1\",\"profile\":"<<json_quote(family.profile)
        <<",\"target\":\"exact_optimal_relation\",\"instrumented\":"<<(instrumented?"true":"false")<<",\"prepare_ns\":"<<prepare_ns
        <<",\"verifier_isolated_ns\":null,\"verifier_timing_scope\":\"unavailable; registered synthesis includes verifier and validation\",\"generic_membership_api\":\"unsupported\",\"generic_slice_api\":\"unsupported\"";
    if(const auto* rejected=std::get_if<Rejection>(&prepared_outcome)) {std::cout<<",\"termination\":\"preparation_rejected\",\"diagnostics\":";diagnostics_json(std::cout,rejected->diagnostics);std::cout<<"}\n";return 0;}
    auto prepared=std::get<PreparedStrategy>(std::move(prepared_outcome));
    ExecutionContext context;context.run_id="synthesis";context.numerical=family.numerical;
    context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
    context.backend_thread_observation=std::make_shared<execution::BackendThreadObservation>();
    context.deadline=Clock::now()+std::chrono::seconds(120);
    if(instrumented)context.timing=collector(resolved,family,config,selection,nullptr,lp.identity,convex.identity);
    auto workspace=prepared.create();const auto start=Clock::now();auto outcome=workspace->run(context);const auto synthesis_ns=elapsed(start);
    std::cout<<",\"registered_synthesis_ns\":"<<synthesis_ns<<",\"synthesis_timing\":";
    if(context.timing)timing_json(std::cout,take(context.timing->snapshot(),"synthesis snapshot"));else std::cout<<"null";
    if(const auto* rejected=std::get_if<Unsupported>(&outcome)) {std::cout<<",\"termination\":\"unsupported\",\"diagnostics\":";diagnostics_json(std::cout,rejected->diagnostics);std::cout<<"}\n";return 0;}
    const auto& result=std::get<SynthesisResult>(outcome);
    std::cout<<",\"synthesis_assumptions\":[";
    for(std::size_t i=0;i<result.outcome.assumptions.size();++i) {if(i)std::cout<<',';std::cout<<json_quote(result.outcome.assumptions[i]);}
    std::cout<<"],\"synthesis_stop\":";
    std::visit([&](const auto& stop) {
        if constexpr(requires{stop.diagnostics;})diagnostics_json(std::cout,stop.diagnostics);
        else if constexpr(requires{stop.stop.diagnostics;})std::cout<<json_quote(stop.stop.diagnostics);
        else std::cout<<"null";
    },result.stop);
    std::cout<<",\"termination\":"<<json_quote(termination_name(result.termination))<<",\"outcome\":"<<json_quote(outcome_name(result.outcome.value))<<",\"objective_lower\":";
    bound_json(std::cout,result.objective.lower);std::cout<<",\"objective_upper\":";bound_json(std::cout,result.objective.upper);
    std::cout<<",\"family_registry_verified\":"<<(result.family&&result.family->registry_verified()?"true":"false");
    const auto* complete=result.family?std::get_if<CompleteOptimalFamily>(&result.family->outcome()):nullptr;
    if(result.family) {
        const auto& identity=result.family->identity();
        std::cout<<",\"family_binding\":{\"problem_id\":"<<json_quote(identity.problem.value)<<",\"profile\":"<<json_quote(identity.request.profile)
            <<",\"strategy\":"<<json_quote(identity.strategy.value)<<",\"strategy_version\":"<<json_quote(identity.strategy_version)<<",\"lineage\":[";
        for(std::size_t i=0;i<identity.lineage.size();++i) {
            if(i)std::cout<<',';
            const auto& step=identity.lineage[i];
            std::cout<<"{\"request\":"<<json_quote(step.request.value)<<",\"input\":"<<json_quote(step.input.value)<<",\"output\":"<<json_quote(step.output.value)
                <<",\"module\":"<<json_quote(step.module.value)<<",\"version\":"<<json_quote(step.version)<<'}';
        }
        std::cout<<"]}";
    }
    if(complete)if(const auto* proof=std::get_if<RegisteredCompletenessEvidence>(&complete->completeness.support))
        std::cout<<",\"compiled_verifier\":{\"id\":"<<json_quote(proof->verifier.value)<<",\"version\":"<<json_quote(proof->verifier_version)<<",\"proof\":"<<json_quote(proof->proof)<<'}';
    const auto* relation=complete&&complete->relation.payload?complete->relation.payload->h_relation_for_recording():nullptr;
    std::ostringstream serialized;serialized<<std::setprecision(std::numeric_limits<double>::max_digits10);if(relation)h_relation_json(serialized,*relation);else serialized<<"null";
    std::cout<<",\"relation\":"<<serialized.str()<<",\"relation_json_bytes\":"<<serialized.str().size()<<",\"directions\":[";
    for(std::size_t i=0;i<selection.directions.size();++i) {if(i)std::cout<<',';vector_json(std::cout,selection.directions[i]);}
    std::cout<<"],\"requested_witnesses\":"<<selection.count;
    if(complete&&result.family->registry_verified()) {
        auto registration=synthesis::witness_selector::make_registration(query_provider);
        const SelectorRequest query{*result.family,selection};Requirements witness_output;witness_output.output.representation={"csl.witness-batch.v1"};
        const auto selection_start=Clock::now();auto capability=registration.capabilities(query,witness_output);const auto selector_prepare_ns=elapsed(selection_start);
        std::cout<<",\"selector_prepare_ns\":"<<selector_prepare_ns;
        if(const auto* rejected=std::get_if<Diagnostics>(&capability)) {std::cout<<",\"selector_termination\":\"unsupported\",\"selector_diagnostics\":";diagnostics_json(std::cout,*rejected);}
        else {
            auto selector=registration.factory(query);context.run_id="selector";
            context.timing=instrumented?collector(resolved,family,config,selection,&*result.family,lp.identity,convex.identity):nullptr;
            std::optional<ob::TimingScope> root;if(context.timing)root.emplace(take(context.timing->start({0},context),"selector root"));
            const auto query_start=Clock::now();auto answer=selector->select(*result.family,selection,context);const auto selector_ns=elapsed(query_start);
            if(const auto* selected=std::get_if<WitnessSelection>(&answer)) {
                if(root)root->close(selected->termination);
                std::cout<<",\"selector_ns\":"<<selector_ns<<",\"selector_termination\":"<<json_quote(termination_name(selected->termination))<<",\"selector_diagnostics\":"<<json_quote(selected->diagnostics)
                    <<",\"selector_source_bound\":"<<(selected->batch.source_family&&*selected->batch.source_family==result.family->identity()?"true":"false")
                    <<",\"returned_witnesses\":"<<selected->batch.returned_count()<<",\"distinct_witnesses\":"<<selected->batch.distinct_count()<<",\"witnesses\":[";
                for(std::size_t i=0;i<selected->batch.witnesses.size();++i){if(i)std::cout<<',';witness_json(std::cout,selected->batch.witnesses[i]);}std::cout<<']';
                const auto replay_start=Clock::now();bool replay_ok=true;
                for(const auto& witness:selected->batch.witnesses) {
                    replay_ok=replay_ok&&witness.states.size()==horizon+1&&witness.controls.size()==horizon;
                    if(!replay_ok)break;
                    for(const auto& state:witness.states)replay_ok=replay_ok&&state.size()==1&&std::isfinite(state[0]);
                    for(const auto& control:witness.controls)replay_ok=replay_ok&&control.size()==1&&std::isfinite(control[0]);
                    if(!replay_ok)break;
                    replay_ok=replay_ok&&witness.states[0][0]==0;
                    for(std::size_t k=0;k<horizon;++k)replay_ok=replay_ok&&witness.controls[k][0]>=0&&witness.controls[k][0]<=1&&
                        witness.states[k+1][0]==witness.states[k][0]+witness.controls[k][0];
                    replay_ok=replay_ok&&witness.original_objective==(flat?0:witness.states.back()[0])&&witness.original_objective==0;
                }
                const auto replay_ns=elapsed(replay_start);
                std::cout<<",\"literal_replay_ns\":"<<replay_ns<<",\"literal_replay_ok\":"<<(replay_ok?"true":"false");
            } else {if(root)root->close(Termination::operation_rejected);std::cout<<",\"selector_termination\":\"unsupported\",\"selector_diagnostics\":";diagnostics_json(std::cout,std::get<Unsupported>(answer).diagnostics);}
            std::cout<<",\"selector_timing\":";if(context.timing)timing_json(std::cout,take(context.timing->snapshot(),"selector snapshot"));else std::cout<<"null";
        }
    }
    std::cout<<",\"observed_backend_threads\":";if(auto threads=context.backend_thread_observation->maximum())std::cout<<*threads;else std::cout<<"null";
    std::cout<<",\"resources\":{\"total_threads\":1,\"outer_workers\":1,\"threads_per_worker\":1,\"native_heap_enforcement\":false}}\n";
    return 0;
} catch(const std::exception& error) {std::cerr<<error.what()<<'\n';return 1;}
