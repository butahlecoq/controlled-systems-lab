#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/execution/timing_collector.hpp>
#include <atomic>
#include <latch>
#include <limits>
#include <thread>
using namespace csl;
namespace ar=csl::artifacts;
namespace ob=csl::execution::observability;
namespace {
template<class T> T accepted(ar::ArtifactResult<T> value) {
    if(const auto* e=std::get_if<ar::ArtifactError>(&value)) INFO((e->path+": "+e->message));
    REQUIRE(std::holds_alternative<T>(value));return std::get<T>(std::move(value));
}
template<class T> T measured(const ar::Metric<T>& value) {
    REQUIRE(std::holds_alternative<ar::Available<T>>(value));return std::get<ar::Available<T>>(value).value;
}
ar::MissingReason absent(const ar::Metric<std::uint64_t>& value) {
    REQUIRE(std::holds_alternative<ar::Unavailable>(value));return std::get<ar::Unavailable>(value).reason;
}
ar::ClockDomain domain(ar::ClockMetric metric=ar::ClockMetric::steady_wall) {
    return {{metric==ar::ClockMetric::steady_wall?"wall":"cpu"},metric,
        metric==ar::ClockMetric::thread_cpu?"calling-thread":metric==ar::ClockMetric::process_cpu?"process":"run",
        1,1000,ar::Available<std::uint64_t>{1},"test-origin"};
}
class FakeClock final:public ob::TimingClock {
public:
    std::atomic<std::int64_t> wall{0},cpu{0};
    bool available=true;
    std::atomic<unsigned> wall_reads{0},cpu_reads{0};
    ar::ClockDomain wall_metadata=domain();
    std::optional<ar::ClockDomain> cpu_metadata;
    ar::ClockDomain wall_domain() const override{return wall_metadata;}
    std::optional<ar::ClockDomain> cpu_domain() const override{return cpu_metadata;}
    ar::Metric<std::int64_t> wall_now() noexcept override {
        ++wall_reads;return available?ar::Metric<std::int64_t>{ar::Available<std::int64_t>{wall.load()}}:
            ar::Metric<std::int64_t>{ar::Unavailable{ar::MissingReason::clock_unavailable,{}}};
    }
    ar::Metric<std::int64_t> cpu_now() noexcept override{++cpu_reads;return ar::Available<std::int64_t>{cpu.load()};}
};
ob::CollectionPlan plan(bool enabled=true,std::size_t count=4,bool escaped_child=false,ar::ClockDomain wall_metadata=domain()) {
    Problem z{{"zero"},std::make_shared<const SystemModel>(SystemModel{{{0,0,0},TimeDomain::discrete,
        LinearStage{{0,0,{}},{0,0,{}},{0,0,{}},{}}},{}}),{0},KnownInitial{{}},ContinuousDomain{{}},
        {UniversalSet{0}},{},{},InformationPattern::nominal_open_loop,LinearTerminal{{},0}};
    auto resolved=problem::resolve(z,{problem::UncertaintyStructure::stage_product_uncoupled});
    REQUIRE(std::holds_alternative<problem::ResolvedProblem>(resolved));
    ar::ConfigurationInput c;
    c.collection={enabled,ar::CollectionMode::detail,100,100000,100,10000};
    const ar::Unavailable missing{ar::MissingReason::not_instrumented,{}};
    c.modules={{"lp",{{"lp"},"1",missing},{}},{"strategy",{{"joint"},"1",missing},{}}};
    c.resources={2,2,1,{}};c.numerical={0,0};
    c.output={ar::OutputKind::synthesis,Assurance::numerical,FamilyTarget::exact_optimal_relation,{"joint"},{1,0,{},{}}};
    c.selector={{"first"},"1",{}};c.strategy={{"joint"},{"lp"},{},{},{},{},{},{"first"},{"joint"}};
    ob::PlanInput p{std::get<problem::ResolvedProblem>(resolved),accepted(ar::resolve_configuration(c)),{"run"},{},{},enabled?2u:0u};
    if(enabled){
        p.clocks={wall_metadata};p.tasks={"task"};p.operations={"solve"};
        for(std::size_t i=0;i<count;++i){
            ar::SpanDescriptor d{};d.id={i};if(i)d.parent=ar::SpanParent{{i==3&&count==4?1u:0u},i==3&&count==4&&!escaped_child?ar::ParentKind::nested:ar::ParentKind::spawned};
            d.shard=i%2;d.bucket=0;d.task="task";d.operation="solve";d.module=c.modules[0].implementation;
            d.clock={"wall"};d.requested_assurance=Assurance::numerical;d.applied_assurance=ar::Available<Assurance>{Assurance::numerical};
            p.spans.push_back(std::move(d));
        }
    }
    return accepted(ob::make_collection_plan(std::move(p)));
}
std::shared_ptr<ob::TimingCollector> collector(std::shared_ptr<FakeClock> clock,bool enabled=true) {
    return accepted(ob::make_timing_collector(plan(enabled),clock,{0},enabled?std::vector<ar::SpanId>{{1},{2}}:std::vector<ar::SpanId>{}));
}
}
TEST_CASE("T-OBS02 overlapping children use union while run and worker work remain separate") {
    auto clock=std::make_shared<FakeClock>();auto timer=collector(clock);
    auto root=accepted(timer->start({0}));clock->wall=2;auto a=accepted(timer->start({1}));
    clock->wall=4;auto nested=accepted(timer->start({3}));clock->wall=5;auto b=accepted(timer->start({2}));
    clock->wall=9;nested.close();clock->wall=12;a.close();clock->wall=17;b.close();clock->wall=20;root.close();
    const auto report=accepted(timer->snapshot());
    CHECK(measured(report.run_wall_ticks)==20);CHECK(measured(report.worker_work_ticks)==22);
    REQUIRE(report.spans.size()==4);
    CHECK(measured(report.spans[0].inclusive_wall_ticks)==20);CHECK(measured(report.spans[0].exclusive_wall_ticks)==5);
    CHECK(measured(report.spans[1].inclusive_wall_ticks)==10);CHECK(measured(report.spans[1].exclusive_wall_ticks)==5);
    CHECK(measured(report.spans[2].exclusive_wall_ticks)==12);CHECK(measured(report.spans[3].inclusive_wall_ticks)==5);
    CHECK(absent(report.spans[0].cpu_ticks)==ar::MissingReason::not_supported);
    CHECK(measured(report.observations.description().buckets[0].inclusive_ticks)==47);
}
TEST_CASE("concurrent spawned tasks retain predeclared IDs and count each worker once") {
    auto clock=std::make_shared<FakeClock>();
    auto timer=accepted(ob::make_timing_collector(plan(true,17),clock,{0},
        {{1},{2},{3},{4},{5},{6},{7},{8},{9},{10},{11},{12},{13},{14},{15},{16}}));
    auto root=accepted(timer->start({0}));clock->wall=1;
    std::latch started{16},release{1};std::vector<std::thread> workers;
    std::atomic<unsigned> errors{0};
    for(std::uint64_t id=1;id<=16;++id)workers.emplace_back([&,id]{
        auto started_span=timer->start({id});
        if(auto* scope=std::get_if<ob::TimingScope>(&started_span)){
            started.count_down();release.wait();scope->close();
        }else{++errors;started.count_down();release.wait();}
    });
    started.wait();clock->wall=2;release.count_down();for(auto& worker:workers)worker.join();
    clock->wall=3;root.close();const auto report=accepted(timer->snapshot());
    CHECK(errors==0);CHECK(measured(report.run_wall_ticks)==3);CHECK(measured(report.worker_work_ticks)==16);
    CHECK(measured(report.spans[0].exclusive_wall_ticks)==2);
    CHECK(report.observations.description().buckets[0].observed.value==17);
    CHECK(report.observations.description().spans[16].descriptor.parent->id.value==0);
    CHECK(std::holds_alternative<ar::ArtifactError>(ob::make_timing_collector(plan(),clock,{0},{{1},{3}})));
}
TEST_CASE("RAII close preserves cancellation resource limits and exception failure") {
    auto clock=std::make_shared<FakeClock>();auto timer=collector(clock);
    {auto root=accepted(timer->start({0}));
     std::stop_source stop;ExecutionContext context{};context.cancellation=stop.get_token();
     {auto cancelled=accepted(timer->start({1},context));stop.request_stop();}
     {auto limited=accepted(timer->start({2}));limited.close(Termination::resource_limit);limited.close();}
     try {auto failed=accepted(timer->start({3}));throw 7;}catch(int){}
    }
    const auto report=accepted(timer->snapshot());const auto& spans=report.observations.description().spans;
    CHECK(std::get<ar::ReturnedSpan>(spans[1].status).termination==Termination::cancelled);
    CHECK(std::get<ar::ReturnedSpan>(spans[2].status).termination==Termination::resource_limit);
    CHECK(std::holds_alternative<ar::FailedSpan>(spans[3].status));
    CHECK(measured(report.run_wall_ticks)==0);
}
TEST_CASE("incomplete clock unavailable and backwards samples cannot manufacture totals") {
    auto clock=std::make_shared<FakeClock>();auto timer=collector(clock);
    auto root=accepted(timer->start({0}));clock->wall=5;auto child=accepted(timer->start({1}));
    auto report=accepted(timer->snapshot());
    CHECK(absent(report.run_wall_ticks)==ar::MissingReason::incomplete_span);
    CHECK(absent(report.spans[0].exclusive_wall_ticks)==ar::MissingReason::incomplete_span);
    clock->wall=4;child.close();root.close();report=accepted(timer->snapshot());
    CHECK(absent(report.run_wall_ticks)==ar::MissingReason::clock_mismatch);
    CHECK(absent(report.worker_work_ticks)==ar::MissingReason::clock_mismatch);
    CHECK(std::any_of(report.diagnostics.begin(),report.diagnostics.end(),[](const auto& d){return d.code==ob::TimingDiagnosticCode::wall_clock_regressed;}));
    auto unavailable=std::make_shared<FakeClock>();unavailable->available=false;
    auto absent_timer=collector(unavailable);
    for(std::uint64_t id:{0,1,2,3}){auto span=accepted(absent_timer->start({id}));}
    const auto absent_report=accepted(absent_timer->snapshot());
    CHECK(absent(absent_report.run_wall_ticks)==ar::MissingReason::clock_unavailable);
}
TEST_CASE("process CPU belongs only to the run and thread CPU requires the same thread") {
    auto clock=std::make_shared<FakeClock>();clock->cpu_metadata=domain(ar::ClockMetric::process_cpu);
    auto timer=collector(clock);auto root=accepted(timer->start({0}));clock->cpu=2;
    auto a=accepted(timer->start({1}));auto b=accepted(timer->start({2}));auto nested=accepted(timer->start({3}));
    clock->cpu=11;nested.close();a.close();b.close();clock->cpu=15;root.close();
    auto report=accepted(timer->snapshot());CHECK(measured(report.spans[0].cpu_ticks)==15);
    CHECK(report.cpu_clock->metric==ar::ClockMetric::process_cpu);
    CHECK(absent(report.spans[1].cpu_ticks)==ar::MissingReason::not_applicable);
    CHECK(absent(report.spans[2].cpu_ticks)==ar::MissingReason::not_applicable);
    clock=std::make_shared<FakeClock>();clock->cpu_metadata=domain(ar::ClockMetric::thread_cpu);
    timer=collector(clock);root=accepted(timer->start({0}));clock->cpu=3;a=accepted(timer->start({1}));
    clock->cpu=7;a.close();b=accepted(timer->start({2}));
    std::thread other([scope=std::move(b)]() mutable{scope.close();});other.join();
    {auto n=accepted(timer->start({3}));}clock->cpu=10;root.close();
    report=accepted(timer->snapshot());CHECK(measured(report.spans[1].cpu_ticks)==4);
    CHECK(absent(report.spans[2].cpu_ticks)==ar::MissingReason::clock_mismatch);
    CHECK(measured(report.spans[0].cpu_ticks)==10);
}
TEST_CASE("duplicate starts moves and repeated snapshots cannot double count a span") {
    auto clock=std::make_shared<FakeClock>();auto timer=collector(clock);auto root=accepted(timer->start({0}));
    CHECK(std::holds_alternative<ar::ArtifactError>(timer->start({0})));
    CHECK(std::holds_alternative<ar::ArtifactError>(timer->start({999})));
    auto moved=std::move(root);clock->wall=1;moved.close();
    CHECK(std::holds_alternative<ar::ArtifactError>(timer->start({0})));
    for(std::uint64_t id:{1,2,3}){auto scope=accepted(timer->start({id}));}
    const auto a=accepted(timer->snapshot()),b=accepted(timer->snapshot());
    CHECK(a.observations.description().buckets[0].observed.value==4);
    CHECK(b.observations.description().buckets[0].observed.value==4);
    CHECK(measured(a.worker_work_ticks)==0);
}
TEST_CASE("disabled context keeps result evidence and explicitly omits detailed measurements") {
    auto clock=std::make_shared<FakeClock>();clock->available=false;auto timer=collector(clock,false);
    ExecutionContext context{};context.timing=timer;
    const ProgramResult result{Termination::cancelled,{ProgramIdentity{{"problem"},{"program"}},MathematicalOutcome::undetermined,Unestablished{},{"partial"}},
        Vector{2}, {},"retained evidence"};
    {auto scope=accepted(ob::start_timing(context,{999}));}
    const auto final=ar::project_final(result);const auto report=accepted(timer->snapshot());
    CHECK(final.result.termination==Termination::cancelled);CHECK(final.result.primal==std::optional<Vector>{{2}});
    CHECK(final.result.raw_diagnostics=="retained evidence");
    CHECK(absent(report.run_wall_ticks)==ar::MissingReason::collection_disabled);
    CHECK(absent(report.worker_work_ticks)==ar::MissingReason::collection_disabled);
    CHECK(report.observations.description().spans.empty());CHECK(report.spans.empty());
    CHECK(clock->wall_reads==0);CHECK(clock->cpu_reads==0);
}



TEST_CASE("spawned descendants may outlive a local parent but their work still occupies the run") {
    auto clock=std::make_shared<FakeClock>();
    auto timer=accepted(ob::make_timing_collector(plan(true,4,true),clock,{0},{{1},{2}}));
    auto root=accepted(timer->start({0}));clock->wall=2;auto a=accepted(timer->start({1}));
    clock->wall=4;auto child=accepted(timer->start({3}));clock->wall=6;a.close();
    clock->wall=7;auto b=accepted(timer->start({2}));clock->wall=9;child.close();
    clock->wall=11;b.close();clock->wall=12;root.close();const auto report=accepted(timer->snapshot());
    CHECK(measured(report.run_wall_ticks)==12);CHECK(measured(report.worker_work_ticks)==8);
    CHECK(measured(report.spans[0].exclusive_wall_ticks)==3);CHECK(measured(report.spans[1].exclusive_wall_ticks)==2);
    CHECK(report.diagnostics.empty());
}
TEST_CASE("a task outside the measured run diagnoses an invalid latency envelope") {
    auto clock=std::make_shared<FakeClock>();auto timer=collector(clock);
    auto root=accepted(timer->start({0}));clock->wall=2;auto child=accepted(timer->start({1}));
    {auto nested=accepted(timer->start({3}));}{auto sibling=accepted(timer->start({2}));}
    clock->wall=4;root.close();clock->wall=5;child.close();const auto report=accepted(timer->snapshot());
    CHECK(absent(report.run_wall_ticks)==ar::MissingReason::clock_mismatch);
    CHECK(std::any_of(report.diagnostics.begin(),report.diagnostics.end(),[](const auto& d){return d.code==ob::TimingDiagnosticCode::child_outside_parent;}));
}
TEST_CASE("clock domains worker ancestry and run context are checked at admission") {
    auto clock=std::make_shared<FakeClock>();auto timer=collector(clock);ExecutionContext context{};context.run_id="other-run";
    CHECK(std::holds_alternative<ar::ArtifactError>(timer->start({0},context)));
    CHECK(std::holds_alternative<ar::ArtifactError>(ob::make_timing_collector(plan(),clock,{1},{{2}})));
    CHECK(std::holds_alternative<ar::ArtifactError>(ob::make_timing_collector(plan(),clock,{0},{{1},{1}})));
    CHECK(std::holds_alternative<ar::ArtifactError>(ob::make_timing_collector(plan(),clock,{0},{{1},{3}})));
    CHECK(std::holds_alternative<ar::ArtifactError>(ob::make_timing_collector(plan(),nullptr,{0},{})));
    clock->cpu_metadata=domain();
    CHECK(std::holds_alternative<ar::ArtifactError>(ob::make_timing_collector(plan(),clock,{0},{})));
}
TEST_CASE("deadline closure is cancelled and explicit termination survives a pending stop") {
    auto clock=std::make_shared<FakeClock>();auto timer=collector(clock);ExecutionContext context{};
    context.timing=timer;context.run_id="run";context.deadline=std::chrono::steady_clock::time_point::min();
    {auto root=accepted(ob::start_timing(context,{0}));
     {auto a=accepted(ob::start_timing(context,{1}));}
     {auto b=accepted(ob::start_timing(context,{2}));b.close(Termination::resource_limit);}
     {auto c=accepted(ob::start_timing(context,{3}));c.close(Termination::operation_rejected);}
    }
    const auto report=accepted(timer->snapshot());const auto& spans=report.observations.description().spans;
    CHECK(std::get<ar::ReturnedSpan>(spans[0].status).termination==Termination::cancelled);
    CHECK(std::get<ar::ReturnedSpan>(spans[1].status).termination==Termination::cancelled);
    CHECK(std::get<ar::ReturnedSpan>(spans[2].status).termination==Termination::resource_limit);
    REQUIRE(std::holds_alternative<ar::ReturnedSpan>(spans[3].status));
    CHECK(std::get<ar::ReturnedSpan>(spans[3].status).termination==Termination::operation_rejected);
}
TEST_CASE("CPU backwards readings are unavailable without discarding sound wall timing") {
    auto clock=std::make_shared<FakeClock>();clock->cpu_metadata=domain(ar::ClockMetric::process_cpu);clock->cpu=10;
    auto timer=collector(clock);auto root=accepted(timer->start({0}));
    for(std::uint64_t id:{1,2,3}){auto child=accepted(timer->start({id}));}
    clock->wall=5;clock->cpu=9;root.close();const auto report=accepted(timer->snapshot());
    CHECK(measured(report.run_wall_ticks)==5);CHECK(absent(report.spans[0].cpu_ticks)==ar::MissingReason::clock_mismatch);
    CHECK(std::any_of(report.diagnostics.begin(),report.diagnostics.end(),[](const auto& d){return d.code==ob::TimingDiagnosticCode::cpu_clock_regressed;}));
}

TEST_CASE("all termination variants survive OBS-01 completion publication") {
    for(auto termination:{Termination::completed,Termination::cancelled,Termination::resource_limit,
        Termination::numerical_failure,Termination::operation_rejected,Termination::contract_rejected}){
        auto clock=std::make_shared<FakeClock>();auto timer=collector(clock);
        for(std::uint64_t id:{0,1,2,3}){auto scope=accepted(timer->start({id}));scope.close(termination);}
        const auto report=accepted(timer->snapshot());
        for(const auto& span:report.observations.description().spans){
            REQUIRE(std::holds_alternative<ar::ReturnedSpan>(span.status));
            CHECK(std::get<ar::ReturnedSpan>(span.status).termination==termination);
        }
        CHECK(report.observations.description().buckets[0].observed.value==4);
    }
}
TEST_CASE("worker sum overflow and negative clocks are diagnosed with no wrapped totals") {
    auto clock=std::make_shared<FakeClock>();
    auto timer=accepted(ob::make_timing_collector(plan(true,5),clock,{0},{{1},{2},{3}}));
    std::vector<ob::TimingScope> scopes;
    for(std::uint64_t id:{0,1,2,3,4})scopes.push_back(accepted(timer->start({id})));
    clock->wall=std::numeric_limits<std::int64_t>::max();for(auto& scope:scopes)scope.close();
    auto report=accepted(timer->snapshot());
    CHECK(measured(report.run_wall_ticks)==9223372036854775807ULL);
    CHECK(measured(report.spans[0].exclusive_wall_ticks)==0);
    CHECK(absent(report.worker_work_ticks)==ar::MissingReason::overflow);
    clock=std::make_shared<FakeClock>();clock->wall=-1;timer=collector(clock);
    for(std::uint64_t id:{0,1,2,3}){auto scope=accepted(timer->start({id}));}
    report=accepted(timer->snapshot());CHECK(absent(report.run_wall_ticks)==ar::MissingReason::clock_mismatch);
}
TEST_CASE("concurrent duplicate claims yield one completion and never duplicate work") {
    auto clock=std::make_shared<FakeClock>();auto timer=collector(clock);auto root=accepted(timer->start({0}));
    std::latch launch{1};std::atomic<unsigned> accepted_count{0},rejected_count{0};std::vector<std::thread> threads;
    for(unsigned i=0;i<16;++i)threads.emplace_back([&]{launch.wait();auto result=timer->start({1});
        if(std::holds_alternative<ob::TimingScope>(result))++accepted_count;else ++rejected_count;});
    launch.count_down();for(auto& thread:threads)thread.join();
    for(std::uint64_t id:{2,3}){auto scope=accepted(timer->start({id}));}root.close();
    const auto report=accepted(timer->snapshot());CHECK(accepted_count==1);CHECK(rejected_count==15);
    CHECK(report.observations.description().buckets[0].observed.value==4);CHECK(measured(report.worker_work_ticks)==0);
}
TEST_CASE("an open CPU scope is incomplete rather than an unsupported measurement") {
    auto clock=std::make_shared<FakeClock>();clock->cpu_metadata=domain(ar::ClockMetric::process_cpu);
    auto timer=collector(clock);auto root=accepted(timer->start({0}));const auto report=accepted(timer->snapshot());
    CHECK(absent(report.spans[0].cpu_ticks)==ar::MissingReason::incomplete_span);
}
TEST_CASE("move assignment closes its old span before taking the new owner") {
    auto clock=std::make_shared<FakeClock>();auto timer=collector(clock);auto root=accepted(timer->start({0}));
    clock->wall=1;auto a=accepted(timer->start({1}));clock->wall=2;auto b=accepted(timer->start({2}));
    clock->wall=3;auto n=accepted(timer->start({3}));clock->wall=4;n.close();
    clock->wall=5;a=std::move(b);clock->wall=10;a.close();clock->wall=20;root.close();
    const auto report=accepted(timer->snapshot());CHECK(measured(report.spans[1].inclusive_wall_ticks)==4);
    CHECK(measured(report.spans[2].inclusive_wall_ticks)==8);CHECK(measured(report.worker_work_ticks)==12);
    CHECK(report.observations.description().buckets[0].observed.value==4);
}
TEST_CASE("clock resolution and calibration mismatches reject before sampling") {
    struct Fixture {ar::ClockDomain planned,actual;};
    std::vector<Fixture> fixtures;
    auto planned=domain(),actual=planned;
    actual.resolution_ticks=ar::Available<std::uint64_t>{2};fixtures.push_back({planned,actual});
    actual=planned;actual.resolution_ticks=ar::Unavailable{ar::MissingReason::not_supported,"not measured"};fixtures.push_back({planned,actual});
    planned.resolution_ticks=ar::Unavailable{ar::MissingReason::not_supported,"not measured"};
    actual=planned;actual.resolution_ticks=ar::Available<std::uint64_t>{1};fixtures.push_back({planned,actual});
    actual=planned;actual.resolution_ticks=ar::Unavailable{ar::MissingReason::clock_unavailable,"not measured"};fixtures.push_back({planned,actual});
    actual=planned;actual.resolution_ticks=ar::Unavailable{ar::MissingReason::not_supported,"different limitation"};fixtures.push_back({planned,actual});
    planned=domain();planned.calibration=ar::Available<std::string>{"reviewed calibration"};
    actual=planned;actual.calibration=ar::Available<std::string>{"different calibration"};fixtures.push_back({planned,actual});
    actual=planned;actual.calibration=ar::Unavailable{ar::MissingReason::not_instrumented,"not calibrated"};fixtures.push_back({planned,actual});
    planned.calibration=ar::Unavailable{ar::MissingReason::not_instrumented,"not calibrated"};
    actual=planned;actual.calibration=ar::Available<std::string>{"reviewed calibration"};fixtures.push_back({planned,actual});
    actual=planned;actual.calibration=ar::Unavailable{ar::MissingReason::not_supported,"not calibrated"};fixtures.push_back({planned,actual});
    actual=planned;actual.calibration=ar::Unavailable{ar::MissingReason::not_instrumented,"different limitation"};fixtures.push_back({planned,actual});
    for(const auto& fixture:fixtures){
        auto clock=std::make_shared<FakeClock>();clock->wall_metadata=fixture.actual;
        auto result=ob::make_timing_collector(plan(true,4,false,fixture.planned),clock,{0},{{1},{2}});
        REQUIRE(std::holds_alternative<ar::ArtifactError>(result));
        CHECK(std::get<ar::ArtifactError>(result).path=="timing.clock");
        CHECK(clock->wall_reads==0);CHECK(clock->cpu_reads==0);
    }
}
TEST_CASE("matching clock precision and limitations survive portable run publication") {
    for(bool available:{true,false}){
        auto metadata=domain();
        if(available)metadata.calibration=ar::Available<std::string>{"reviewed calibration"};
        else {
            metadata.resolution_ticks=ar::Unavailable{ar::MissingReason::not_supported,"resolution not measured"};
            metadata.calibration=ar::Unavailable{ar::MissingReason::not_instrumented,"not calibrated"};
        }
        auto planned=plan(true,4,false,metadata);auto clock=std::make_shared<FakeClock>();clock->wall_metadata=metadata;
        auto timer=accepted(ob::make_timing_collector(planned,clock,{0},{{1},{2}}));
        for(std::uint64_t id:{0,1,2,3}){auto scope=accepted(timer->start({id}));}
        const auto report=accepted(timer->snapshot());const auto& description=planned.description();
        const ar::Unavailable missing{ar::MissingReason::not_instrumented,{}};
        ar::RunRecord record{description.problem.identity(),{0,0,0},0,description.configuration,description.run,
            ar::UnsupportedFinal{{{DiagnosticCode::unsupported,"timing-fixture","No solver invoked"}}},report.observations,
            {missing,missing,missing,missing,true,ar::MemoryAccounting::unlimited},{},{},ar::ProblemProvenance::problem_revalidated};
        const auto persisted=accepted(ar::decode_run(accepted(ar::encode_run(accepted(ar::publish_run({description.problem,record}))))));
        const auto& saved=persisted.description().statistics.description().clocks[0];
        if(available){
            CHECK(measured(saved.resolution_ticks)==1);CHECK(measured(saved.calibration)=="reviewed calibration");
        }else {
            const auto& resolution=std::get<ar::Unavailable>(saved.resolution_ticks);
            const auto& calibration=std::get<ar::Unavailable>(saved.calibration);
            CHECK(resolution.reason==ar::MissingReason::not_supported);CHECK(resolution.detail=="resolution not measured");
            CHECK(calibration.reason==ar::MissingReason::not_instrumented);CHECK(calibration.detail=="not calibrated");
        }
        CHECK(persisted.description().statistics.description().buckets[0].observed.value==4);
    }
}
