#include <csl/execution/timing_collector.hpp>
#include <atomic>
#include <charconv>
#include <iostream>
#include <stdexcept>
#include <string_view>

namespace ar=csl::artifacts;
namespace ob=csl::execution::observability;
using namespace csl;
namespace {
template<class T> T accepted(ar::ArtifactResult<T> result){
    if(auto* error=std::get_if<ar::ArtifactError>(&result))throw std::runtime_error(error->path+": "+error->message);
    return std::get<T>(std::move(result));
}
std::uint64_t parse(std::string_view value){
    std::uint64_t number{};auto [last,error]=std::from_chars(value.data(),value.data()+value.size(),number);
    if(error!=std::errc{}||last!=value.data()+value.size())throw std::runtime_error("Arguments must be positive integers");
    return number;
}
std::shared_ptr<ob::TimingCollector> prepare(bool enabled,std::uint64_t count){
    Problem zero{{"zero"},std::make_shared<const SystemModel>(SystemModel{{{0,0,0},TimeDomain::discrete,
        LinearStage{{0,0,{}},{0,0,{}},{0,0,{}},{}}},{}}),{0},KnownInitial{{}},ContinuousDomain{{}},
        {UniversalSet{0}},{},{},InformationPattern::nominal_open_loop,LinearTerminal{{},0}};
    auto resolved=problem::resolve(zero,{problem::UncertaintyStructure::stage_product_uncoupled});
    if(!std::holds_alternative<problem::ResolvedProblem>(resolved))throw std::runtime_error("Fixture failed resolution");
    ar::ConfigurationInput config;
    config.collection={enabled,ar::CollectionMode::summary,count+1,(count+1)*2048,0,0};
    const ar::Unavailable missing{ar::MissingReason::not_instrumented,{}};
    config.modules={{"lp",{{"fixture-lp"},"1",missing},{}},{"strategy",{{"fixture-strategy"},"1",missing},{}}};
    config.resources={1,1,1,{}};config.numerical={0,0};
    config.output={ar::OutputKind::synthesis,Assurance::numerical,FamilyTarget::exact_optimal_relation,{"joint"},{1,0,{},{}}};
    config.selector={{"fixture-selector"},"1",{}};
    config.strategy={{"fixture-strategy"},{"fixture-lp"},{},{},{},{},{},{"fixture-selector"},{"joint"}};
    auto clock=ob::make_steady_timing_clock();
    ob::PlanInput plan{std::get<problem::ResolvedProblem>(resolved),accepted(ar::resolve_configuration(config)),{"overhead"},{},{},enabled?1u:0u};
    if(enabled){
        plan.clocks={clock->wall_domain()};plan.tasks={"worker"};plan.operations={"checksum"};
        plan.spans.reserve(static_cast<std::size_t>(count+1));
        for(std::uint64_t id=0;id<=count;++id){
            ar::SpanDescriptor span{};span.id={id};if(id)span.parent=ar::SpanParent{{0},ar::ParentKind::nested};
            span.bucket=0;span.task="worker";span.operation="checksum";span.module=config.modules[0].implementation;
            span.clock=plan.clocks[0].id;span.requested_assurance=Assurance::numerical;span.applied_assurance=ar::Available<Assurance>{Assurance::numerical};
            plan.spans.push_back(std::move(span));
        }
    }
    return accepted(ob::make_timing_collector(accepted(ob::make_collection_plan(std::move(plan))),clock,{0},{}));
}
using Time=std::chrono::steady_clock;
std::int64_t nanoseconds(Time::time_point first,Time::time_point last){return std::chrono::duration_cast<std::chrono::nanoseconds>(last-first).count();}
void run(bool enabled,std::uint64_t count,std::uint64_t repetition){
    const auto setup_begin=Time::now();auto collector=prepare(enabled,count);ExecutionContext context{};context.timing=collector;context.run_id="overhead";
    const auto setup_end=Time::now();
    std::uint64_t checksum=0,failures=0;
    const auto loop_begin=Time::now();auto root_result=ob::start_timing(context,{0});
    if(std::holds_alternative<ar::ArtifactError>(root_result))++failures;
    for(std::uint64_t id=1;id<=count;++id){
        auto scope=ob::start_timing(context,{id});
        if(std::holds_alternative<ar::ArtifactError>(scope))++failures;
        checksum+=id;
        // Keep the checksum work and scope lifetime inside the measured loop.
        std::atomic_signal_fence(std::memory_order_seq_cst);
    }
    if(auto* root=std::get_if<ob::TimingScope>(&root_result))root->close();
    const auto loop_end=Time::now();auto report=accepted(collector->snapshot());const auto publication_end=Time::now();
    if(checksum!=count*(count+1)/2)++failures;
    std::uint64_t observed=0;for(const auto& bucket:report.observations.description().buckets)observed+=bucket.observed.value;
    if(observed!=(enabled?count+1:0))++failures;
    if(!report.diagnostics.empty())++failures;
    if(enabled&&!std::holds_alternative<ar::Available<std::uint64_t>>(report.run_wall_ticks))++failures;
    if(!enabled&&(!report.spans.empty()||std::get<ar::Unavailable>(report.run_wall_ticks).reason!=ar::MissingReason::collection_disabled))++failures;
    std::cout<<repetition<<','<<(enabled?"enabled":"disabled")<<','<<count<<','<<nanoseconds(setup_begin,setup_end)<<','
        <<nanoseconds(loop_begin,loop_end)<<','<<nanoseconds(loop_end,publication_end)<<','<<nanoseconds(setup_begin,publication_end)<<','
        <<checksum<<','<<observed<<','<<failures<<'\n';
    if(failures)throw std::runtime_error("Benchmark work or observations failed validation");
}
}
int main(int argc,char** argv){
    try {
        const auto count=argc>1?parse(argv[1]):10000;
        const auto repetitions=argc>2?parse(argv[2]):5;
        if(argc>4||!count||count>1000000||repetitions<5||repetitions>100)throw std::runtime_error("Usage: observability_overhead [spans 1..1000000] [repetitions 5..100] [source-commit]");
        std::cout<<"# source_commit="<<(argc>3?argv[3]:"unrecorded")<<'\n';
#ifdef NDEBUG
        std::cout<<"# build=Release NDEBUG\n";
#else
        std::cout<<"# build=Debug; measurements are functional only\n";
#endif
#ifdef _MSC_VER
        std::cout<<"# compiler=MSVC "<<_MSC_VER<<'\n';
#else
        std::cout<<"# compiler="<<__VERSION__<<'\n';
#endif
        std::cout<<"# wall_clock=steady_clock; CPU=unavailable; serial checksum workload; setup and publication measured separately\n"
            <<"repetition,mode,spans,setup_ns,loop_ns,publication_ns,end_to_end_ns,checksum,observed,failures\n";
        for(std::uint64_t repetition=1;repetition<=repetitions;++repetition){
            // Alternate first side to balance warmup/drift. Both sides run each repetition.
            run(repetition%2==0,count,repetition);run(repetition%2!=0,count,repetition);
        }
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
