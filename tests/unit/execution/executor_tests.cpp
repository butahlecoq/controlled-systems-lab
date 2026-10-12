#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/execution/executor.hpp>
#include <csl/optimization/lp_backend.hpp>
#include <atomic>
#include <cmath>
#include <condition_variable>
#include <future>
#include <limits>
#include <mutex>
#include <thread>
#include <cstdlib>
#include <new>

// Target a caller-sized metadata copy rather than the next arbitrary allocation:
// MSVC Debug containers allocate small iterator proxies in noexcept constructors.
// All other allocations use ordinary malloc/free; faults stay on the caller lane.
namespace allocation_fault {
thread_local std::size_t minimum_size{};
thread_local bool injected{};
struct ScopedFailure {
    explicit ScopedFailure(std::size_t minimum) noexcept { minimum_size=minimum; injected=false; }
    ScopedFailure(const ScopedFailure&)=delete;
    ScopedFailure& operator=(const ScopedFailure&)=delete;
    ~ScopedFailure() { minimum_size=0; }
};
}
void* operator new(std::size_t size) {
    if (allocation_fault::minimum_size && size>=allocation_fault::minimum_size) {
        allocation_fault::minimum_size=0;
        allocation_fault::injected=true;
        throw std::bad_alloc{};
    }
    if (auto* p=std::malloc(size ? size : 1)) return p;
    throw std::bad_alloc{};
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p,std::size_t) noexcept { std::free(p); }

using namespace csl;
namespace ex = csl::execution;
namespace reg = csl::registry;
namespace {
using LPTask = ex::Task<reg::LPPort>;
using LPBatch = ex::BatchResult<reg::LPPort>;
using Action = std::function<void(const ExecutionContext&)>;
struct Counts { std::atomic<int> created{}, invoked{}, destroyed{}, active{}, peak{}; std::function<void()> on_destroy; };
void enter(Counts& c) {
    const int n = ++c.active;
    int old = c.peak.load();
    while (old < n && !c.peak.compare_exchange_weak(old,n)) {}
}
class Analytic final : public LPWorkspace {
    std::shared_ptr<Counts> counts_;
    Action action_;
    bool endpoints_, partial_;
    std::atomic<bool> entered_{false};
public:
    Analytic(std::shared_ptr<Counts> c, Action a, bool e, bool p)
        : counts_(std::move(c)),action_(std::move(a)),endpoints_(e),partial_(p) { ++counts_->created; }
    ~Analytic() override { ++counts_->destroyed; if (counts_->on_destroy) counts_->on_destroy(); }
    ProgramOutcome do_solve(const LinearProgram& p,const ExecutionContext& ctx) override {
        if (entered_.exchange(true)) throw std::logic_error("workspace entered concurrently");
        struct Leave { std::atomic<bool>& entered; ~Leave(){entered=false;} } leave{entered_};
        ++counts_->invoked; enter(*counts_);
        struct Exit { Counts& c; ~Exit() { --c.active; } } exit{*counts_};
        if (action_) action_(ctx);
        if (partial_ && !ctx.cancellation.stop_requested()) throw std::logic_error("cooperative boundary did not see stop");
        double x = p.objective()[0] < 0 ? 4 : -1;
        if (endpoints_) x = std::fma(p.objective()[0],-1,p.offset()) <= std::fma(p.objective()[0],4,p.offset()) ? -1 : 4;
        if (partial_) x = 1;
        const double value = std::fma(p.objective()[0],x,p.offset());
        ProgramBoundEvidence evidence{p.identity(),SymbolicArgument{"fixture",partial_ ? "x=1 is in [-1,4]; 3*1+2=5" : "affine interval endpoint"},{}};
        ProgramResult result{partial_ ? Termination::cancelled : Termination::completed,
            {p.identity(),partial_ ? MathematicalOutcome::undetermined : MathematicalOutcome::optimal,Unestablished{},{}},
            Vector{x},{},"literal fixture"};
        result.objective.upper = ProgramObjectiveBound{value,evidence};
        if (!partial_) result.objective.lower = ProgramObjectiveBound{value,evidence};
        result.objective.upper->evidence.assumptions={"finite interval only"};
        result.residuals.primal=PrimalResiduals{{p.identity(),{{"literal-residual"},"1"},1e-12,2e-12},{0,1},{0,4}};
        return result;
    }
};
ex::ResourceUse use(std::optional<std::size_t> bytes = 6) {
    return {1,"fixture: caller lane only",bytes,ex::CallStopSupport::noninterruptible};
}
LPTask task(std::string id, double coefficient = 3, std::shared_ptr<Counts> counts = std::make_shared<Counts>(),
    Action action = {}, std::function<void()> create = {}, ex::ResourceUse resources = use(), bool endpoints = false, bool partial = false) {
    reg::Registry<reg::LPPort> registry;
    REQUIRE_FALSE(registry.add({{{"analytic"},"1"},[](const LinearProgram&,const reg::Requirements&) -> reg::Capability { return reg::Offer{}; },
        [counts,action,create,endpoints,partial](const LinearProgram&) {
            if (create) create();
            return std::make_unique<Analytic>(counts,action,endpoints,partial);
        }}).has_value());
    LinearProgramInput input{{{"problem"},{id}},{coefficient},2,{0,1,{0},{},{}},{{-1,4}},{}};
    auto program = std::get<LinearProgram>(optimization::make_linear_program(input));
    auto prepared = std::get<reg::PreparedPipeline<reg::LPPort>>(reg::prepare_pipeline(reg::select(registry,{{"analytic"},{}},program)));
    auto result = ex::make_task(ex::TaskId{id},prepared,resources);
    REQUIRE(std::holds_alternative<LPTask>(result));
    input.objective[0] = 900;
    return std::get<LPTask>(result);
}
std::unique_ptr<ex::Executor> executor(ResourcePolicy p = {2,2,1,{}}) {
    auto result = ex::make_executor(p);
    REQUIRE(std::holds_alternative<std::unique_ptr<ex::Executor>>(result));
    return std::get<std::unique_ptr<ex::Executor>>(std::move(result));
}
ExecutionContext context(ex::Executor& e) { return {e.resources(),{},{},{1e-12,1e-12},"execution-test"}; }
LPBatch run(ex::Executor& e,const std::vector<LPTask>& tasks,ExecutionContext ctx,ex::Mode mode = ex::Mode::sequential,ex::AdmissionLimit limit = {}) {
    auto result = e.run<reg::LPPort>(tasks,ctx,mode,limit);
    REQUIRE(std::holds_alternative<LPBatch>(result));
    return std::get<LPBatch>(std::move(result));
}
const ProgramResult& answer(const ex::TaskRecord<reg::LPPort>& r) {
    REQUIRE(std::holds_alternative<ex::Returned<reg::LPPort>>(r.outcome));
    const auto& outcome = std::get<ex::Returned<reg::LPPort>>(r.outcome).value;
    REQUIRE(std::holds_alternative<ProgramResult>(outcome));
    return std::get<ProgramResult>(outcome);
}
void literal(const ex::TaskRecord<reg::LPPort>& r,double x,double value) {
    const auto& p = answer(r); REQUIRE(p.primal.has_value());
    CHECK((*p.primal)[0] == doctest::Approx(x).epsilon(1e-12));
    REQUIRE(p.objective.upper.has_value());
    CHECK(p.objective.upper->value == doctest::Approx(value).epsilon(1e-12));
    CHECK(p.outcome.subject.program.value == r.id.value);
}
}

TEST_CASE("literal interval tasks retain prepared data and stable order in both modes") {
    auto e = executor();
    for (bool endpoint : {false,true}) {
        auto counts = std::make_shared<Counts>();
        std::vector<LPTask> tasks{task("positive",3,counts,{}, {},use(),endpoint), task("negative",-2,counts,{}, {},use(),endpoint),task("constant",0,counts,{}, {},use(),endpoint)};
        for (auto mode : {ex::Mode::sequential,ex::Mode::bounded_parallel}) {
            auto report = run(*e,tasks,context(*e),mode);
            REQUIRE(report.tasks.size()==3);
            CHECK(report.tasks[0].id.value=="positive"); CHECK(report.tasks[1].id.value=="negative"); CHECK(report.tasks[2].id.value=="constant");
            literal(report.tasks[0],-1,-1); literal(report.tasks[1],4,-6); literal(report.tasks[2],-1,2);
            CHECK(report.resources==e->resources()); CHECK(report.numerical.absolute_tolerance==1e-12);
            CHECK(report.tasks[0].provenance[0].actual->id.value=="analytic");
            CHECK(report.timing.started_at <= report.timing.workers_joined_at);
            CHECK(report.timing.workers_joined_at <= report.timing.completed_at);
            CHECK_FALSE(report.timing.admission_closed.has_value());
        }
        CHECK(counts->created==6); CHECK(counts->destroyed==6);
    }
}
TEST_CASE("resource policy is copied and unsupported hard enforcement rejects") {
    ResourcePolicy p{4,2,2,10}; auto e=executor(p); p.total_threads=1;
    CHECK(e->resources()->total_threads==4);
    CHECK(std::holds_alternative<Diagnostics>(ex::make_executor({3,2,2,{}})));
    CHECK(std::holds_alternative<Diagnostics>(ex::make_executor({1,1,1,{}},{true,false})));
    CHECK(std::holds_alternative<Diagnostics>(ex::make_executor({1,1,1,{}},{false,true})));
    std::vector<LPTask> tasks{task("one")}; auto ctx=context(*e);
    ctx.resources=std::make_shared<const ResourcePolicy>(*e->resources());
    CHECK(std::holds_alternative<Diagnostics>(e->run<reg::LPPort>(tasks,ctx,ex::Mode::sequential)));
    ctx=context(*e);ctx.numerical.absolute_tolerance=std::numeric_limits<double>::quiet_NaN();
    CHECK(std::holds_alternative<Diagnostics>(e->run<reg::LPPort>(tasks,ctx,ex::Mode::sequential)));
}
TEST_CASE("all declarations are checked before any factory") {
    auto e=executor({2,2,1,10});auto counts=std::make_shared<Counts>();
    for (auto resources : {ex::ResourceUse{2,"two threads",6,ex::CallStopSupport::unspecified},use({})}) {
        std::vector<LPTask> tasks{task("first",3,counts),task("invalid",3,counts,{},{},resources)};
        CHECK(std::holds_alternative<Diagnostics>(e->run<reg::LPPort>(tasks,context(*e),ex::Mode::sequential)));
    }
    CHECK(counts->created==0);
}
TEST_CASE("pre-cancel expired deadline zero creation limit and empty batches") {
    auto e=executor();auto counts=std::make_shared<Counts>();std::vector<LPTask> tasks{task("a",3,counts),task("b",3,counts)};
    std::stop_source stop;stop.request_stop();auto ctx=context(*e);ctx.cancellation=stop.get_token();
    auto cancelled=run(*e,tasks,ctx);CHECK(std::get<ex::Skipped>(cancelled.tasks[0].outcome).reason==ex::SkipReason::cancelled);
    CHECK(cancelled.timing.external_cancellation_observed_at.has_value());
    ctx=context(*e);ctx.deadline=ex::TimePoint::min();auto expired=run(*e,tasks,ctx);
    CHECK(expired.timing.configured_deadline==ctx.deadline);CHECK_FALSE(expired.timing.external_cancellation_observed_at);
    CHECK(expired.timing.admission_closed->cause==ex::BatchStopCause::deadline);
    CHECK(std::get<ex::Skipped>(expired.tasks[1].outcome).reason==ex::SkipReason::deadline);
    auto capped=run(*e,tasks,context(*e),ex::Mode::bounded_parallel,{0});
    CHECK(std::get<ex::Skipped>(capped.tasks[0].outcome).reason==ex::SkipReason::task_limit);
    CHECK_FALSE(capped.tasks[0].timing.admitted_at);CHECK(counts->created==0);
    CHECK(run(*e,{},context(*e)).tasks.empty());
}
TEST_CASE("reservation credits serialize six plus six under ten and skip eleven") {
    auto e=executor({2,2,1,10});auto counts=std::make_shared<Counts>();
    std::vector<LPTask> tasks{task("a",3,counts),task("b",-2,counts),task("oversize",0,counts,{},{},use(11))};
    auto r=run(*e,tasks,context(*e),ex::Mode::bounded_parallel);
    literal(r.tasks[0],-1,-1);literal(r.tasks[1],4,-6);
    CHECK(std::get<ex::Skipped>(r.tasks[2].outcome).reason==ex::SkipReason::reservation_exceeds_budget);
    CHECK(r.enforcement.peak_workspace_reservation_bytes==6);CHECK(r.enforcement.peak_active_tasks==1);
    CHECK(r.enforcement.memory==ex::MemoryEnforcement::active_reservations_only);
    CHECK(r.enforcement.native_threads==ex::NativeThreadEnforcement::declared_only);
    CHECK(counts->created==2);CHECK(counts->destroyed==2);CHECK(counts->peak==1);
    auto capped=run(*e,tasks,context(*e),ex::Mode::sequential,{1});literal(capped.tasks[0],-1,-1);
    CHECK(std::get<ex::Skipped>(capped.tasks[1].outcome).reason==ex::SkipReason::task_limit);
}
TEST_CASE("factory allocation failure retains earlier canonical answer and drains") {
    auto e=executor();auto counts=std::make_shared<Counts>();
    std::vector<LPTask> tasks{task("ok",3,counts),task("oom",3,counts,{},[]{throw std::bad_alloc{};}),task("later",3,counts)};
    auto r=run(*e,tasks,context(*e));literal(r.tasks[0],-1,-1);
    const auto& f=std::get<ex::TaskFailure>(r.tasks[1].outcome);
    CHECK(f.stage==ex::FailureStage::create);CHECK(f.kind==ex::FailureKind::allocation);
    CHECK_THROWS_AS(std::rethrow_exception(f.exception),std::bad_alloc);
    CHECK(std::get<ex::Skipped>(r.tasks[2].outcome).reason==ex::SkipReason::batch_failed);
    CHECK(r.timing.admission_closed->cause==ex::BatchStopCause::allocation);
    CHECK_FALSE(r.timing.external_cancellation_observed_at);CHECK(counts->destroyed==1);
}

namespace {
class Gate {
    std::mutex mutex_; std::condition_variable changed_; bool open_{};
public:
    void open() noexcept { { std::lock_guard lock(mutex_); open_=true; } changed_.notify_all(); }
    void wait(std::stop_token stop = {}) {
        std::stop_callback callback(stop,[this]() noexcept { open(); });
        std::unique_lock lock(mutex_); changed_.wait(lock,[this]{return open_;});
    }
};
struct Cleanup { std::function<void()> action; ~Cleanup() { action(); } };
}
TEST_CASE("parallel completion order differs while records remain in input order") {
    auto e=executor();auto first=std::make_shared<Counts>(),second=std::make_shared<Counts>();auto gate=std::make_shared<Gate>();
    second->on_destroy=[gate]{gate->open();};
    std::vector<LPTask> tasks{task("slow",3,first,[gate](const ExecutionContext& c){gate->wait(c.cancellation);}),task("fast",-2,second)};
    auto r=run(*e,tasks,context(*e),ex::Mode::bounded_parallel);
    literal(r.tasks[0],-1,-1);literal(r.tasks[1],4,-6);
    CHECK(*r.tasks[1].timing.call_finished_at<=*r.tasks[0].timing.call_finished_at);
    CHECK(r.enforcement.peak_active_tasks==2);
}
TEST_CASE("two private lanes each with a helper honor one aggregate four-participant policy") {
    auto e=executor({4,2,2,{}});auto policy=e->resources();
    auto actual=std::make_shared<Counts>();auto ready=std::make_shared<Gate>();auto arrivals=std::make_shared<std::atomic<int>>(0);auto same=std::make_shared<std::atomic<bool>>(true);
    Action action=[actual,ready,arrivals,same,policy](const ExecutionContext& c) {
        if (c.resources!=policy) same->store(false);
        auto participant=[&] {
            enter(*actual); if (++*arrivals==4) ready->open(); ready->wait(c.cancellation); --actual->active;
        };
        std::jthread inner;
        Cleanup release{[&]{ready->open();}};
        inner=std::jthread(participant);participant();inner.join();
    };
    auto declared=use();declared.peak_compute_threads=2;declared.thread_assumptions="fixture lane plus one helper";
    std::vector<LPTask> tasks{task("a",3,std::make_shared<Counts>(),action,{},declared),task("b",-2,std::make_shared<Counts>(),action,{},declared)};
    auto r=run(*e,tasks,context(*e),ex::Mode::bounded_parallel);
    CHECK(same->load());CHECK(actual->peak==4);CHECK(actual->active==0);
    CHECK(r.enforcement.peak_active_tasks==2);CHECK(r.enforcement.peak_reserved_threads==4);
}
TEST_CASE("cancellation during factory skips invocation and cleans exactly once") {
    auto e=executor();auto counts=std::make_shared<Counts>();Gate entered,release;std::stop_source stop;
    auto ctx=context(*e);ctx.cancellation=stop.get_token();
    std::vector<LPTask> tasks{task("creating",3,counts,{},[&]{entered.open();release.wait();})};
    std::optional<LPBatch> report;std::exception_ptr failure;std::jthread runner;
    Cleanup cleanup{[&]{stop.request_stop();release.open();entered.open();if(runner.joinable())runner.join();}};
    runner=std::jthread([&]{try { report=std::get<LPBatch>(e->run<reg::LPPort>(tasks,ctx,ex::Mode::sequential)); } catch (...) {failure=std::current_exception();} entered.open();});
    entered.wait();stop.request_stop();release.open();runner.join();
    REQUIRE_FALSE(failure);REQUIRE(report);CHECK(counts->created==1);CHECK(counts->destroyed==1);CHECK(counts->invoked==0);
    CHECK(std::get<ex::Skipped>(report->tasks[0].outcome).reason==ex::SkipReason::cancelled);
    CHECK(report->tasks[0].timing.create_finished_at);CHECK_FALSE(report->tasks[0].timing.call_started_at);
}
TEST_CASE("cooperative partial incumbent and completed noninterruptible return retain original evidence") {
    for (bool partial : {false,true}) {
        auto e=executor({1,1,1,{}});auto counts=std::make_shared<Counts>();Gate entered,release;std::stop_source stop;
        auto ctx=context(*e);ctx.cancellation=stop.get_token();
        Action action=[&](const ExecutionContext&){entered.open();release.wait();};
        auto declaration=use();declaration.call_stop_support=partial ? ex::CallStopSupport::cooperative_boundaries : ex::CallStopSupport::noninterruptible;
        std::vector<LPTask> tasks{task("running",3,counts,action,{},declaration,false,partial),task("queued",0,counts)};
        std::optional<LPBatch> report;std::exception_ptr failure;std::jthread runner;
        Cleanup cleanup{[&]{stop.request_stop();release.open();entered.open();if(runner.joinable())runner.join();}};
        runner=std::jthread([&]{try {report=std::get<LPBatch>(e->run<reg::LPPort>(tasks,ctx,ex::Mode::bounded_parallel));}catch(...){failure=std::current_exception();}entered.open();});
        entered.wait();stop.request_stop();release.open();runner.join();
        REQUIRE_FALSE(failure);REQUIRE(report);literal(report->tasks[0],partial?1:-1,partial?5:-1);
        const auto& p=answer(report->tasks[0]);CHECK(p.termination==(partial?Termination::cancelled:Termination::completed));
        CHECK(p.outcome.value==(partial?MathematicalOutcome::undetermined:MathematicalOutcome::optimal));
        CHECK(p.objective.lower.has_value()==!partial);CHECK(p.raw_diagnostics=="literal fixture");
        CHECK(std::get<SymbolicArgument>(p.objective.upper->evidence.support).reference=="fixture");
        CHECK(p.objective.upper->evidence.assumptions==std::vector<std::string>{"finite interval only"});
        REQUIRE(p.residuals.primal);CHECK(p.residuals.primal->context.subject.program.value=="running");
        CHECK(p.residuals.primal->context.relative_tolerance==2e-12);CHECK(p.residuals.primal->variables.scale==4);
        CHECK(std::get<ex::Skipped>(report->tasks[1].outcome).reason==ex::SkipReason::cancelled);
        const auto& t=report->timing;const auto& call=report->tasks[0].timing;
        REQUIRE(t.external_cancellation_observed_at);CHECK(call.call_started_at<=t.external_cancellation_observed_at);
        CHECK(t.external_cancellation_observed_at<=call.call_finished_at);
        CHECK(*call.call_finished_at<=t.workers_joined_at);CHECK(t.workers_joined_at<=t.completed_at);
        CHECK(counts->created==1);CHECK(counts->destroyed==1);
    }
}
TEST_CASE("failure then external cancellation then late return retains all timing authorities after owners die") {
    auto report=[] {
        auto e=executor();std::stop_source caller;auto ctx=context(*e);ctx.cancellation=caller.get_token();ctx.deadline=ex::TimePoint::max();
        Gate entered,release;std::atomic<bool> handshake{}, fallback{};auto counts=std::make_shared<Counts>();
        std::vector<LPTask> tasks;
        tasks.push_back(task("fails",3,counts,[&](const ExecutionContext& c){entered.wait(c.cancellation);throw std::runtime_error("deliberate invocation failure");}));
        tasks.push_back(task("late",3,counts,[&](const ExecutionContext& c){
            std::stop_callback observe(c.cancellation,[&]() noexcept {caller.request_stop();handshake=true;release.open();});
            entered.open();release.wait();
        }));
        tasks.push_back(task("never",0,counts));
        Cleanup cleanup{[&]{if(!handshake.load())fallback=true;caller.request_stop();entered.open();release.open();}};
        auto r=run(*e,tasks,ctx,ex::Mode::bounded_parallel);
        CHECK(handshake.load());CHECK_FALSE(fallback.load());CHECK(counts->created==2);CHECK(counts->destroyed==2);
        return r;
    }();
    const auto& f=std::get<ex::TaskFailure>(report.tasks[0].outcome);
    CHECK(f.stage==ex::FailureStage::invoke);CHECK(f.kind==ex::FailureKind::adapter_exception);
    CHECK_THROWS_WITH(std::rethrow_exception(f.exception),"deliberate invocation failure");
    literal(report.tasks[1],-1,-1);CHECK(answer(report.tasks[1]).termination==Termination::completed);
    CHECK(std::get<ex::Skipped>(report.tasks[2].outcome).reason==ex::SkipReason::batch_failed);
    CHECK_FALSE(report.tasks[2].timing.admitted_at);
    const auto& t=report.timing;REQUIRE(t.admission_closed);REQUIRE(t.external_cancellation_observed_at);
    CHECK(t.admission_closed->cause==ex::BatchStopCause::adapter_exception);
    CHECK(t.configured_deadline==ex::TimePoint::max());
    CHECK(*report.tasks[1].timing.call_started_at<=t.admission_closed->observed_at);
    CHECK(t.admission_closed->observed_at<=*t.external_cancellation_observed_at);
    CHECK(t.external_cancellation_observed_at<=report.tasks[1].timing.call_finished_at);
    CHECK(*report.tasks[1].timing.call_finished_at<=t.workers_joined_at);CHECK(t.workers_joined_at<=t.completed_at);
    CHECK(*report.tasks[1].timing.call_finished_at<*t.configured_deadline); // zero lateness, no extreme subtraction
    CHECK(t.workers_joined_at-t.admission_closed->observed_at>=std::chrono::steady_clock::duration::zero());
    CHECK(*report.tasks[1].timing.call_finished_at-*t.external_cancellation_observed_at>=std::chrono::steady_clock::duration::zero());
}
TEST_CASE("overlapping and recursive runs reject immediately and executor remains reusable") {
    auto e=executor({1,1,1,{}});auto ctx=context(*e);Gate entered,release;std::stop_source stop;ctx.cancellation=stop.get_token();
    std::atomic<bool> recursive_rejected{};
    std::vector<LPTask> tasks{task("one",3,std::make_shared<Counts>(),[&](const ExecutionContext&){
        auto recursive=e->run<reg::LPPort>({},ctx,ex::Mode::sequential);
        recursive_rejected=std::holds_alternative<Diagnostics>(recursive)&&std::get<Diagnostics>(recursive)[0].field=="execution.busy";
        entered.open();release.wait();
    })};
    std::optional<LPBatch> result;std::exception_ptr failure;std::jthread runner;
    Cleanup cleanup{[&]{stop.request_stop();release.open();entered.open();if(runner.joinable())runner.join();}};
    runner=std::jthread([&]{try{result=std::get<LPBatch>(e->run<reg::LPPort>(tasks,ctx,ex::Mode::sequential));}catch(...){failure=std::current_exception();}entered.open();});
    entered.wait();auto overlap=e->run<reg::LPPort>(tasks,ctx,ex::Mode::bounded_parallel);release.open();runner.join();
    REQUIRE_FALSE(failure);CHECK(recursive_rejected.load());REQUIRE(std::holds_alternative<Diagnostics>(overlap));
    CHECK(std::get<Diagnostics>(overlap)[0].field=="execution.busy");REQUIRE(result);literal(result->tasks[0],-1,-1);
    CHECK(run(*e,{},context(*e)).tasks.empty());
}

namespace {
struct StrategyAudit { std::mutex mutex; std::vector<std::vector<SolveStamp>> attempts; };
class TwoCalls final : public SynthesisWorkspace {
    std::unique_ptr<reg::BoundWorkspace<reg::LPPort>> lp_;
    std::shared_ptr<StrategyAudit> audit_;
public:
    TwoCalls(std::unique_ptr<reg::BoundWorkspace<reg::LPPort>> lp,std::shared_ptr<StrategyAudit> audit)
        : lp_(std::move(lp)),audit_(std::move(audit)) {}
    SynthesisResult solve(const csl::problem::ResolvedProblem& problem,const FamilyRequest&,const ExecutionContext& ctx) override {
        std::vector<SolveStamp> stamps;
        auto answer=std::get<ProgramResult>(lp_->run(ctx));stamps.push_back(lp_->last_attempt()->stamp);
        if (!ctx.cancellation.stop_requested()) {
            answer=std::get<ProgramResult>(lp_->run(ctx));stamps.push_back(lp_->last_attempt()->stamp);
        }
        { std::lock_guard lock(audit_->mutex);audit_->attempts.push_back(std::move(stamps)); }
        const auto id=problem.identity();
        SynthesisResult result{ctx.cancellation.stop_requested()?Termination::cancelled:Termination::completed,
            {id,MathematicalOutcome::undetermined,Unestablished{},{}},{},{},
            {{{id,{{0},*answer.primal}, {*answer.primal},answer.objective.upper->value},
                {id,SymbolicArgument{"fixture", "bounded LP point"}}}}, {}};
        if (ctx.cancellation.stop_requested())
            result.stop=ScopedOperationStopped{{StopReason::cancelled,"fixture cancellation"},
                RequestProvenance{{"fixture/two-calls"},"strategy",{"two-calls"},std::string{"1"},
                    ModuleId{"two-calls"},std::string{"1"}}, {false,false,1,false}};
        return result;
    }
};
ex::Task<reg::StrategyPort> strategy_task(std::shared_ptr<StrategyAudit> audit,std::shared_ptr<Counts> counts,Action action={},std::string id="strategy") {
    reg::Registry<reg::LPPort> lp;
    REQUIRE_FALSE(lp.add({{{"analytic"},"1"},[](const auto&,const auto&)->reg::Capability{return reg::Offer{};},
        [counts,action](const LinearProgram&){return std::make_unique<Analytic>(counts,action,false,false);}}));
    auto operand=std::make_shared<const LinearProgram>(std::get<LinearProgram>(optimization::make_linear_program(
        LinearProgramInput{{{"problem"},{"interval"}},{3},2,{0,1,{0},{},{}},{{-1,4}},{}})));
    reg::StrategyRegistry strategies;
    REQUIRE_FALSE(strategies.add({{{"two-calls"},"1"},[](const auto&,const auto&)->reg::Capability{return reg::Offer{};},
        [&lp,operand,audit](const reg::StrategyRequest&,const reg::Requirements&)->std::variant<reg::StrategyPlan,reg::Rejection> {
            auto checked=reg::check_pipeline(reg::select(lp,{{"analytic"},{}},*operand));
            return reg::compose_strategy(std::get<reg::CheckedPipeline<reg::LPPort>>(checked),
                [operand,audit](auto workers,const auto&,const auto&){return std::make_unique<TwoCalls>(std::move(std::get<0>(workers)),audit);});
        }}));
    LinearStage stage{{1,1,{0}},{1,1,{1}},{1,0,{}},{0}};
    Problem problem{{"problem"},std::make_shared<const SystemModel>(SystemModel{{{1,1,0},TimeDomain::discrete,stage},{}}),
        {0,1},KnownInitial{{0}},ContinuousDomain{{UniversalSet{1}}},{UniversalSet{1},UniversalSet{1}},{},{},
        InformationPattern::nominal_open_loop,LinearTerminal{{3},2}};
    auto resolved=std::get<csl::problem::ResolvedProblem>(csl::problem::resolve(problem,
        {csl::problem::UncertaintyStructure::stage_product_uncoupled,{},{}}));
    reg::StrategyRequest request{resolved,{{"two-calls"},{"analytic"},{},{},{},{},{},{},{}},
        {"nominal_open_loop",resolved.identity(),FamilyTarget::candidate_relaxation,{1e-12,1e-12},
            Assurance::numerical,{},{}}};
    auto prepared=std::get<reg::PreparedStrategy>(strategies.prepare(request));
    return std::get<ex::Task<reg::StrategyPort>>(ex::make_task({std::move(id)},prepared,use()));
}
}
TEST_CASE("retained strategy owns private LP attempts and never promotes an incumbent to a family") {
    auto e=executor();auto audit=std::make_shared<StrategyAudit>();auto counts=std::make_shared<Counts>();
    std::vector<ex::Task<reg::StrategyPort>> tasks{strategy_task(audit,counts)};
    for (auto mode:{ex::Mode::sequential,ex::Mode::bounded_parallel}) {
        auto batch=std::get<ex::BatchResult<reg::StrategyPort>>(e->run<reg::StrategyPort>(tasks,context(*e),mode));
        const auto& value=std::get<SynthesisResult>(std::get<ex::Returned<reg::StrategyPort>>(batch.tasks[0].outcome).value);
        CHECK(value.termination==Termination::completed);CHECK_FALSE(value.family);REQUIRE(value.incumbents.size()==1);
        CHECK(value.incumbents[0].witness.controls==std::vector<Vector>{{-1}});CHECK(value.incumbents[0].witness.original_objective==-1);
        CHECK(value.incumbents[0].witness.states==std::vector<Vector>{{0},{-1}});
        CHECK(value.outcome.value==MathematicalOutcome::undetermined);CHECK(std::holds_alternative<Unestablished>(value.outcome.support));
        CHECK(batch.tasks[0].provenance.size()==2);
    }
    REQUIRE(audit->attempts.size()==2);
    for(const auto& attempts:audit->attempts) {REQUIRE(attempts.size()==2);CHECK(attempts[0].attempt()==1);CHECK(attempts[1].attempt()==2);CHECK(attempts[0].workspace()==attempts[1].workspace());}
    CHECK_FALSE(audit->attempts[0][0].workspace()==audit->attempts[1][0].workspace());
    CHECK(counts->created==2);CHECK(counts->invoked==4);CHECK(counts->destroyed==2);
    std::stop_source stop;auto ctx=context(*e);ctx.cancellation=stop.get_token();
    std::vector<ex::Task<reg::StrategyPort>> cancelled{strategy_task(audit,counts,[&](const ExecutionContext&){stop.request_stop();})};
    auto batch=std::get<ex::BatchResult<reg::StrategyPort>>(e->run<reg::StrategyPort>(cancelled,ctx,ex::Mode::sequential));
    const auto& value=std::get<SynthesisResult>(std::get<ex::Returned<reg::StrategyPort>>(batch.tasks[0].outcome).value);
    CHECK(value.termination==Termination::cancelled);CHECK_FALSE(value.family);CHECK(value.incumbents[0].witness.original_objective==-1);
    CHECK(value.incumbents[0].witness.states==std::vector<Vector>{{0},{-1}});CHECK(value.incumbents[0].witness.controls==std::vector<Vector>{{-1}});
    CHECK(std::holds_alternative<Unestablished>(value.outcome.support));CHECK(audit->attempts.back().size()==1);
}
namespace {
class Geometry final:public SetOperatorWorkspace {
public: OperationOutcome apply(const OperationRequest& r,const ExecutionContext&) override {
    return OperationStopped{StopReason::resource_limit,r.identity.request.value};
}};
class Selector final:public WitnessSelectorWorkspace {
public: std::variant<WitnessSelection,Unsupported> select(const OptimalFamily& f,const WitnessRequest& r,const ExecutionContext&) override {
    if (!r.count) return Unsupported{{{DiagnosticCode::unsupported,"selector.count","fixture requires a positive request"}}};
    return WitnessSelection{{{{f.identity.problem,{{7}},{{2}},17}},r.count,{"literal-selector"},r.seed,f.identity},Termination::resource_limit,"one witness only"};
}};
class CustomWorkspace:public ExclusiveWorkspace { public: int calls{}; };
struct CustomPort {
    using Request=int;using Workspace=CustomWorkspace;
    static constexpr const char* name="custom";
    static int snapshot(int r){return r;}
    static int run(Workspace& w,int r,const ExecutionContext&){return r+ ++w.calls;}
};
template<class Port> ex::Task<Port> port_task(typename Port::Request request,reg::Registration<Port> registration) {
    reg::Registry<Port> registry;auto method=registration.identity.id;
    REQUIRE_FALSE(registry.add(std::move(registration)));
    auto prepared=std::get<reg::PreparedPipeline<Port>>(reg::prepare_pipeline(reg::select(registry,{method,{}},request)));
    return std::get<ex::Task<Port>>(ex::make_task({"other"},prepared,use()));
}
}
TEST_CASE("geometry selector and custom outcomes retain their distinct public types") {
    auto e=executor();auto capability=[](const auto&,const auto&)->reg::Capability{return reg::Offer{};};
    SetHandle set{{1,{"fixture"},SetProperty::yes,SetProperty::yes,SetProperty::yes},std::make_shared<const SetPayload>(),{"set"}};
    std::vector<ex::Task<reg::GeometryPort>> geometry{port_task<reg::GeometryPort>(
        {{{"p"},{"stopped-query"},{"ideal"}},{"geometry"},SupportQuery{set,{1}},SetRelation::equivalent,Assurance::numerical},
        {{{"geometry"},"1"},capability,[](const auto&){return std::make_unique<Geometry>();}})};
    auto g=std::get<ex::BatchResult<reg::GeometryPort>>(e->run<reg::GeometryPort>(geometry,context(*e),ex::Mode::bounded_parallel));
    const auto& stopped=std::get<OperationStopped>(std::get<ex::Returned<reg::GeometryPort>>(g.tasks[0].outcome).value);
    CHECK(stopped.reason==StopReason::resource_limit);CHECK(stopped.diagnostics=="stopped-query");
    FamilyRequest family_request{"nominal_open_loop",{"p"},FamilyTarget::candidate_relaxation,
        {1e-8,1e-8},Assurance::numerical,{"joint"},{}};
    FamilyIdentity identity{{"p"},family_request,{{1,1,0},1},{"strategy"},"1",{}};
    reg::SelectorRequest request{{identity,CandidateFamily{
        {identity.coordinates,{"joint"},std::make_shared<const JointRelationPayload>()},
        HeuristicRelationEvidence{"fixture"},{{"p"},Unestablished{}}}},{3,0.1,{},42}};
    for (auto count:{3u,0u}) {
        request.selection.count=count;
        std::vector<ex::Task<reg::SelectorPort>> selectors{port_task<reg::SelectorPort>(request,
            {{{"selector"},"1"},capability,[](const auto&){return std::make_unique<Selector>();}})};
        auto s=std::get<ex::BatchResult<reg::SelectorPort>>(e->run<reg::SelectorPort>(selectors,context(*e),ex::Mode::sequential));
        const auto& result=std::get<ex::Returned<reg::SelectorPort>>(s.tasks[0].outcome).value;
        if(count) {
            const auto& v=std::get<WitnessSelection>(result);CHECK(v.batch.requested==3);CHECK(v.batch.seed==42);REQUIRE(v.batch.witnesses.size()==1);
            CHECK(v.batch.witnesses[0].states==std::vector<Vector>{{7}});CHECK(v.batch.witnesses[0].original_objective==17);
            CHECK(v.batch.selector.value=="literal-selector");CHECK(v.termination==Termination::resource_limit);CHECK(v.diagnostics=="one witness only");
        } else { CHECK(std::get<Unsupported>(result).diagnostics[0].field=="selector.count"); }
    }
    std::vector<ex::Task<CustomPort>> custom{port_task<CustomPort>(41,{{{"custom"},"1"},capability,[](int){return std::make_unique<CustomWorkspace>();}})};
    for(auto mode:{ex::Mode::sequential,ex::Mode::bounded_parallel}) {
        auto c=std::get<ex::BatchResult<CustomPort>>(e->run<CustomPort>(custom,context(*e),mode));
        CHECK(std::get<ex::Returned<CustomPort>>(c.tasks[0].outcome).value==42);
    }
}
TEST_CASE("prework allocation failure releases busy state without invoking a factory") {
    auto e=executor();auto counts=std::make_shared<Counts>();std::vector<LPTask> tasks{task("allocation-boundary",3,counts)};auto ctx=context(*e);
    // Construct outside the fault window; freezing this public context must copy
    // an owned non-SSO string before any workspace factory can run.
    ctx.run_id.assign(4096,'r');
    bool threw=false;
    {
        allocation_fault::ScopedFailure failure(ctx.run_id.size());
        try{(void)e->run<reg::LPPort>(tasks,ctx,ex::Mode::sequential);}catch(const std::bad_alloc&){threw=true;}
    }
    CHECK(allocation_fault::injected);CHECK(threw);
    CHECK(counts->created==0);CHECK(counts->invoked==0);CHECK(counts->destroyed==0);
    auto batch=run(*e,tasks,ctx);CHECK(batch.run_id==ctx.run_id);
    literal(batch.tasks[0],-1,-1);
    CHECK(counts->created==1);CHECK(counts->invoked==1);CHECK(counts->destroyed==1);
}
TEST_CASE("zero and unknown reservation accounting and duplicate task validation") {
    auto e=executor();auto counts=std::make_shared<Counts>();
    std::vector<LPTask> unknown{task("unknown",3,counts,{},{},use({}))};auto r=run(*e,unknown,context(*e));
    literal(r.tasks[0],-1,-1);CHECK_FALSE(r.enforcement.peak_workspace_reservation_bytes);
    std::vector<LPTask> zero{task("zero",3,counts,{},{},use(0))};auto z=run(*e,zero,context(*e));CHECK(z.enforcement.peak_workspace_reservation_bytes==0);
    std::vector<LPTask> duplicate{zero[0],zero[0]};CHECK(std::holds_alternative<Diagnostics>(e->run<reg::LPPort>(duplicate,context(*e),ex::Mode::sequential)));
    auto ctx=context(*e);ctx.run_id.clear();CHECK(std::holds_alternative<Diagnostics>(e->run<reg::LPPort>(zero,ctx,ex::Mode::sequential)));
    CHECK(std::holds_alternative<Diagnostics>(e->run<reg::LPPort>(zero,context(*e),static_cast<ex::Mode>(99))));
    CHECK(counts->created==2);
}
TEST_CASE("task publication validates identity declarations and freezes caller-owned values") {
    reg::Registry<CustomPort> registry;
    REQUIRE_FALSE(registry.add({{{"custom"},"1"},[](int,const auto&)->reg::Capability{return reg::Offer{};},[](int){return std::make_unique<CustomWorkspace>();}}));
    int request=41;
    auto prepared=std::get<reg::PreparedPipeline<CustomPort>>(reg::prepare_pipeline(reg::select(registry,{{"custom"},{}},request)));
    CHECK(std::holds_alternative<Diagnostic>(ex::make_task(ex::TaskId{""},prepared,use())));
    auto invalid=use();invalid.peak_compute_threads=0;CHECK(std::holds_alternative<Diagnostic>(ex::make_task(ex::TaskId{"zero"},prepared,invalid)));
    invalid=use();invalid.thread_assumptions.clear();CHECK(std::holds_alternative<Diagnostic>(ex::make_task(ex::TaskId{"missing"},prepared,invalid)));
    invalid=use();invalid.call_stop_support=static_cast<ex::CallStopSupport>(99);CHECK(std::holds_alternative<Diagnostic>(ex::make_task(ex::TaskId{"unknown"},prepared,invalid)));
    auto declaration=use(6);auto retained=std::get<ex::Task<CustomPort>>(ex::make_task(ex::TaskId{"retained"},prepared,declaration));
    declaration.workspace_reservation_bytes=900;declaration.thread_assumptions="mutated";request=900;
    CHECK(retained.resources().workspace_reservation_bytes==6);CHECK(retained.resources().thread_assumptions=="fixture: caller lane only");
    auto e=executor();std::vector<ex::Task<CustomPort>> tasks{retained};
    auto batch=std::get<ex::BatchResult<CustomPort>>(e->run<CustomPort>(tasks,context(*e),ex::Mode::sequential));
    CHECK(std::get<ex::Returned<CustomPort>>(batch.tasks[0].outcome).value==42);
}
TEST_CASE("two concurrent strategy tasks have separate LP identities and local one-two attempt histories") {
    auto e=executor();auto audit=std::make_shared<StrategyAudit>();auto counts=std::make_shared<Counts>();
    auto gate=std::make_shared<Gate>();auto arrivals=std::make_shared<std::atomic<int>>(0);
    Action action=[gate,arrivals](const ExecutionContext& ctx){if(++*arrivals==2)gate->open();gate->wait(ctx.cancellation);};
    std::vector<ex::Task<reg::StrategyPort>> tasks{strategy_task(audit,counts,action,"left"),strategy_task(audit,counts,action,"right")};
    auto batch=std::get<ex::BatchResult<reg::StrategyPort>>(e->run<reg::StrategyPort>(tasks,context(*e),ex::Mode::bounded_parallel));
    REQUIRE(batch.tasks.size()==2);CHECK(batch.tasks[0].id.value=="left");CHECK(batch.tasks[1].id.value=="right");
    for(const auto& record:batch.tasks) {
        const auto& result=std::get<SynthesisResult>(std::get<ex::Returned<reg::StrategyPort>>(record.outcome).value);
        CHECK(result.incumbents[0].witness.original_objective==-1);CHECK_FALSE(result.family);
    }
    REQUIRE(audit->attempts.size()==2);
    for(const auto& attempts:audit->attempts) {REQUIRE(attempts.size()==2);CHECK(attempts[0].attempt()==1);CHECK(attempts[1].attempt()==2);CHECK(attempts[0].workspace()==attempts[1].workspace());}
    CHECK_FALSE(audit->attempts[0][0].workspace()==audit->attempts[1][0].workspace());
    CHECK(counts->peak==2);CHECK(counts->created==2);CHECK(counts->invoked==4);CHECK(counts->destroyed==2);
}
