#include <csl/execution/timing_collector.hpp>
#include <algorithm>
#include <limits>
#include <mutex>
#include <utility>

namespace csl::execution::observability {
namespace {
namespace ar=artifacts;
using Ticks=ar::Metric<std::uint64_t>;
using Reading=ar::Metric<std::int64_t>;
constexpr auto maximum=std::numeric_limits<std::uint64_t>::max();
ar::Unavailable missing(ar::MissingReason reason){return {reason,{}};}
ar::ArtifactError error(std::string path,std::string message){return {ar::ArtifactErrorCode::invalid_input,std::move(path),std::move(message)};}
Ticks duration(const Reading& start,const Reading& end){
    if(const auto* unavailable=std::get_if<ar::Unavailable>(&start))return *unavailable;
    if(const auto* unavailable=std::get_if<ar::Unavailable>(&end))return *unavailable;
    return ar::elapsed_ticks({start,end});
}
struct Slot {
    enum class State { unstarted,open,closed } state{State::unstarted};
    Reading start=missing(ar::MissingReason::incomplete_span),end=missing(ar::MissingReason::incomplete_span);
    Reading cpu_start=missing(ar::MissingReason::not_supported),cpu_end=missing(ar::MissingReason::not_supported);
    std::thread::id thread;
    Termination termination{Termination::completed};
    bool failed{},wall_regressed{},cpu_regressed{},cpu_thread_changed{};
};
class SteadyClock final:public TimingClock {
    std::chrono::steady_clock::time_point origin_=std::chrono::steady_clock::now();
public:
    ar::ClockDomain wall_domain() const override {
        using Clock=std::chrono::steady_clock;
        return {{"steady-wall"},ar::ClockMetric::steady_wall,"run",Clock::period::num,Clock::period::den,
            missing(ar::MissingReason::not_supported),"collector-created"};
    }
    std::optional<ar::ClockDomain> cpu_domain() const override{return {};}
    Reading wall_now() noexcept override {
        return ar::Available<std::int64_t>{(std::chrono::steady_clock::now()-origin_).count()};
    }
    Reading cpu_now() noexcept override{return missing(ar::MissingReason::not_supported);}
};
bool compatible(const ar::ClockDomain& a,const ar::ClockDomain& b){
    return a.id==b.id&&a.metric==b.metric&&a.scope==b.scope&&a.period_numerator==b.period_numerator&&
        a.period_denominator==b.period_denominator&&a.origin_label==b.origin_label;
}
bool valid_cpu(const ar::ClockDomain& d){
    return !d.id.value.empty()&&!d.scope.empty()&&!d.origin_label.empty()&&d.period_numerator&&d.period_denominator&&
        (d.metric==ar::ClockMetric::process_cpu||d.metric==ar::ClockMetric::thread_cpu);
}
Ticks exclusive(const Slot& parent,const std::vector<Slot>& slots,const std::vector<std::size_t>& children,const std::vector<std::vector<std::size_t>>& graph){
    auto inclusive=duration(parent.start,parent.end);
    if(std::holds_alternative<ar::Unavailable>(inclusive))return inclusive;
    const auto begin=std::get<ar::Available<std::int64_t>>(parent.start).value;
    const auto end=std::get<ar::Available<std::int64_t>>(parent.end).value;
    std::vector<std::pair<std::int64_t,std::int64_t>> intervals;
    std::vector<std::size_t> descendants=children;
    for(std::size_t i=0;i<descendants.size();++i){
        const auto& next=graph[descendants[i]];descendants.insert(descendants.end(),next.begin(),next.end());
    }
    intervals.reserve(descendants.size());
    for(auto index:descendants){
        const auto& child=slots[index];auto elapsed=duration(child.start,child.end);
        if(auto* unavailable=std::get_if<ar::Unavailable>(&elapsed))return *unavailable;
        const auto first=std::max(begin,std::get<ar::Available<std::int64_t>>(child.start).value);
        const auto last=std::min(end,std::get<ar::Available<std::int64_t>>(child.end).value);
        if(first<last)intervals.emplace_back(first,last);
    }
    std::sort(intervals.begin(),intervals.end());
    std::uint64_t covered=0;
    if(!intervals.empty()){
        auto [first,last]=intervals.front();
        for(std::size_t i=1;i<intervals.size();++i){
            if(intervals[i].first<=last)last=std::max(last,intervals[i].second);
            else {covered+=static_cast<std::uint64_t>(last-first);first=intervals[i].first;last=intervals[i].second;}
        }
        covered+=static_cast<std::uint64_t>(last-first);
    }
    return ar::Available<std::uint64_t>{std::get<ar::Available<std::uint64_t>>(inclusive).value-covered};
}
TickValue tick(const Reading& reading){
    if(const auto* value=std::get_if<ar::Available<std::int64_t>>(&reading))return {true,value->value,ar::MissingReason::not_requested};
    return {false,0,std::get<ar::Unavailable>(reading).reason};
}
}
struct TimingScope::Owner {
    CollectionPlan plan;
    std::shared_ptr<TimingClock> clock;
    std::optional<ar::ClockDomain> cpu;
    std::size_t run{};
    std::vector<std::size_t> workers;
    std::vector<Slot> slots;
    std::vector<std::vector<std::size_t>> children;
    mutable std::mutex mutex;
    std::optional<std::int64_t> last_wall;
    bool wall_invalid{};
    explicit Owner(CollectionPlan p):plan(std::move(p)){}
    Reading wall(std::size_t index){
        auto reading=clock->wall_now();
        if(auto* value=std::get_if<ar::Available<std::int64_t>>(&reading)){
            if(value->value<0||(last_wall&&value->value<*last_wall)){
                slots[index].wall_regressed=true;wall_invalid=true;
            }
            last_wall=value->value;
        }else reading=missing(ar::MissingReason::clock_unavailable);
        return reading;
    }
    bool cpu_applies(std::size_t index) const noexcept{return cpu&&(cpu->metric==ar::ClockMetric::thread_cpu||index==run);}
    void close(std::size_t index,Termination termination,bool failed) noexcept {
        std::lock_guard lock{mutex};auto& slot=slots[index];
        slot.end=wall(index);slot.termination=termination;slot.failed=failed;
        if(cpu_applies(index)){
            if(cpu->metric==ar::ClockMetric::thread_cpu&&slot.thread!=std::this_thread::get_id()){
                slot.cpu_thread_changed=true;slot.cpu_end=missing(ar::MissingReason::clock_mismatch);
            }else {
                slot.cpu_end=clock->cpu_now();
                const auto* a=std::get_if<ar::Available<std::int64_t>>(&slot.cpu_start);
                const auto* b=std::get_if<ar::Available<std::int64_t>>(&slot.cpu_end);
                if(a&&b&&(a->value<0||b->value<a->value))slot.cpu_regressed=true;
            }
        }
        slot.state=Slot::State::closed;
    }
};
std::shared_ptr<TimingClock> make_steady_timing_clock(){return std::make_shared<SteadyClock>();}
TimingScope::TimingScope(std::shared_ptr<Owner> p,std::size_t i,const ExecutionContext& c)
    :owner_(std::move(p)),slot_(i),cancellation_(c.cancellation),deadline_(c.deadline),exceptions_(std::uncaught_exceptions()){}
TimingScope::TimingScope(TimingScope&& other) noexcept
    :owner_(std::move(other.owner_)),slot_(other.slot_),cancellation_(other.cancellation_),deadline_(other.deadline_),exceptions_(other.exceptions_){}
TimingScope& TimingScope::operator=(TimingScope&& other) noexcept {
    if(this!=&other){close();owner_=std::move(other.owner_);slot_=other.slot_;cancellation_=other.cancellation_;deadline_=other.deadline_;exceptions_=other.exceptions_;}
    return *this;
}
TimingScope::~TimingScope(){close();}
void TimingScope::close(Termination termination) noexcept {
    if(auto owner=std::exchange(owner_,{}))owner->close(slot_,termination,false);
}
void TimingScope::close() noexcept {
    if(!owner_)return;
    const bool failed=std::uncaught_exceptions()>exceptions_;
    const bool stopped=cancellation_.stop_requested()||(deadline_&&std::chrono::steady_clock::now()>=*deadline_);
    auto owner=std::exchange(owner_,{});
    owner->close(slot_,failed?Termination::numerical_failure:stopped?Termination::cancelled:Termination::completed,failed);
}
TimingCollector::TimingCollector(std::shared_ptr<TimingScope::Owner> p):owner_(std::move(p)){}
bool TimingCollector::enabled() const noexcept{return owner_->plan.description().configuration.description().collection.enabled;}
CollectionResult<TimingScope> TimingCollector::start(ar::SpanId id,const ExecutionContext& context){
    if(!enabled())return TimingScope{};
    if(!context.run_id.empty()&&context.run_id!=owner_->plan.description().run.value)return error("timing.run","Context belongs to a different run" );
    const auto& spans=owner_->plan.description().spans;
    auto found=std::lower_bound(spans.begin(),spans.end(),id.value,[](const auto& span,auto value){return span.id.value<value;});
    if(found==spans.end()||found->id!=id)return error("timing.span","Unknown planned span ID");
    const auto index=static_cast<std::size_t>(found-spans.begin());
    std::lock_guard lock{owner_->mutex};auto& slot=owner_->slots[index];
    if(slot.state!=Slot::State::unstarted)return error("timing.span","Span already started; each planned ID has one owner");
    slot.state=Slot::State::open;slot.thread=std::this_thread::get_id();slot.start=owner_->wall(index);
    if(owner_->cpu_applies(index))slot.cpu_start=owner_->clock->cpu_now();
    else if(owner_->cpu)slot.cpu_start=slot.cpu_end=missing(ar::MissingReason::not_applicable);
    return TimingScope{owner_,index,context};
}
CollectionResult<TimingReport> TimingCollector::snapshot() const {
    try {
        if(!enabled()){
            auto result=merge_observations(owner_->plan,{});if(auto* e=std::get_if<ar::ArtifactError>(&result))return *e;
            return TimingReport{std::get<ar::CollectedStatistics>(std::move(result)),missing(ar::MissingReason::collection_disabled),missing(ar::MissingReason::collection_disabled),{},{},{}};
        }
        std::vector<Slot> slots;bool wall_invalid;
        {std::lock_guard lock{owner_->mutex};slots=owner_->slots;wall_invalid=owner_->wall_invalid;}
        const auto& spans=owner_->plan.description().spans;
        std::vector<TimingDiagnostic> diagnostics;
        bool incomplete=false;
        for(std::size_t i=0;i<slots.size();++i){
            const auto& slot=slots[i];const auto id=spans[i].id;
            if(slot.state!=Slot::State::closed){diagnostics.push_back({id,TimingDiagnosticCode::incomplete_span});incomplete=true;}
            if(slot.wall_regressed)diagnostics.push_back({id,TimingDiagnosticCode::wall_clock_regressed});
            if(slot.cpu_regressed)diagnostics.push_back({id,TimingDiagnosticCode::cpu_clock_regressed});
            if(slot.cpu_thread_changed)diagnostics.push_back({id,TimingDiagnosticCode::cpu_thread_changed});
            const auto elapsed=duration(slot.start,slot.end);
            if(const auto* u=std::get_if<ar::Unavailable>(&elapsed);u&&u->reason==ar::MissingReason::clock_unavailable)
                diagnostics.push_back({id,TimingDiagnosticCode::clock_unavailable});
            if(i!=owner_->run){
                const auto* a=std::get_if<ar::Available<std::int64_t>>(&slots[owner_->run].start);
                const auto* b=std::get_if<ar::Available<std::int64_t>>(&slots[owner_->run].end);
                const auto* c=std::get_if<ar::Available<std::int64_t>>(&slot.start);
                const auto* d=std::get_if<ar::Available<std::int64_t>>(&slot.end);
                if((a&&c&&c->value<a->value)||(b&&d&&d->value>b->value)){
                    diagnostics.push_back({id,TimingDiagnosticCode::child_outside_parent});wall_invalid=true;
                }
            }
            for(auto child:owner_->children[i])if(spans[child].parent->kind==ar::ParentKind::nested){
                const auto* a=std::get_if<ar::Available<std::int64_t>>(&slot.start);
                const auto* b=std::get_if<ar::Available<std::int64_t>>(&slot.end);
                const auto* c=std::get_if<ar::Available<std::int64_t>>(&slots[child].start);
                const auto* d=std::get_if<ar::Available<std::int64_t>>(&slots[child].end);
                if((a&&c&&c->value<a->value)||(b&&d&&d->value>b->value)){
                    diagnostics.push_back({spans[child].id,TimingDiagnosticCode::child_outside_parent});wall_invalid=true;
                }
            }
        }
        if(wall_invalid)for(auto& slot:slots)slot.start=slot.end=missing(ar::MissingReason::clock_mismatch);
        std::vector<ObservationShard> shards;
        for(std::uint64_t id=0;id<owner_->plan.description().shard_count;++id){
            auto result=make_observation_shard(owner_->plan,{id});if(auto* e=std::get_if<ar::ArtifactError>(&result))return *e;
            shards.push_back(std::get<ObservationShard>(std::move(result)));
        }
        std::vector<SpanTiming> timings;timings.reserve(slots.size());
        for(std::size_t i=0;i<slots.size();++i){
            const auto& slot=slots[i];
            auto cpu=owner_->cpu_applies(i)?duration(slot.cpu_start,slot.cpu_end):Ticks{missing(owner_->cpu?ar::MissingReason::not_applicable:ar::MissingReason::not_supported)};
            if(owner_->cpu_applies(i)&&slot.state!=Slot::State::closed)cpu=missing(ar::MissingReason::incomplete_span);
            if(slot.cpu_regressed)cpu=missing(ar::MissingReason::clock_mismatch);
            timings.push_back({spans[i].id,duration(slot.start,slot.end),exclusive(slot,slots,owner_->children[i],owner_->children),cpu,
                owner_->cpu&&owner_->cpu->metric==ar::ClockMetric::thread_cpu&&slot.state!=Slot::State::unstarted?std::optional<std::thread::id>{slot.thread}:std::nullopt});
            if(slot.state!=Slot::State::closed)continue;
            SpanCompletionView completion{spans[i].id,tick(slot.start),tick(slot.end),
                slot.failed?ObservationState::unknown:ObservationState::returned,ar::NotCalledReason::task_not_admitted,
                !slot.failed,slot.termination,{false,0,ar::MissingReason::not_instrumented},{}};
            completion.status=slot.failed?CompletionStatus::failed:CompletionStatus::returned;
            shards[static_cast<std::size_t>(spans[i].shard)].record(completion);
        }
        auto result=merge_observations(owner_->plan,std::move(shards));if(auto* e=std::get_if<ar::ArtifactError>(&result))return *e;
        Ticks run=timings[owner_->run].inclusive_wall_ticks;
        if(!wall_invalid&&incomplete)run=missing(ar::MissingReason::incomplete_span);
        Ticks work=ar::Available<std::uint64_t>{0};
        for(auto i:owner_->workers){
            const auto& elapsed=timings[i].inclusive_wall_ticks;
            if(auto* u=std::get_if<ar::Unavailable>(&elapsed)){work=*u;break;}
            auto& total=std::get<ar::Available<std::uint64_t>>(work).value;
            const auto value=std::get<ar::Available<std::uint64_t>>(elapsed).value;
            if(value>maximum-total){work=missing(ar::MissingReason::overflow);break;}total+=value;
        }
        return TimingReport{std::get<ar::CollectedStatistics>(std::move(result)),run,work,std::move(timings),owner_->cpu,std::move(diagnostics)};
    }catch(const std::bad_alloc&){return ar::ArtifactError{ar::ArtifactErrorCode::allocation,"timing.snapshot","Allocation failed"};}
}
CollectionResult<std::shared_ptr<TimingCollector>> make_timing_collector(CollectionPlan plan,std::shared_ptr<TimingClock> clock,ar::SpanId run,std::vector<ar::SpanId> workers){
    try {
        auto owner=std::make_shared<TimingScope::Owner>(std::move(plan));
        const auto& input=owner->plan.description();
        if(input.configuration.description().collection.enabled){
            if(!clock)return error("timing.clock","Enabled collection requires a clock");
            const auto wall=clock->wall_domain();
            if(input.clocks.size()!=1||wall.metric!=ar::ClockMetric::steady_wall||!compatible(input.clocks[0],wall))
                return error("timing.clock","Plan and source must describe the same monotonic wall domain");
            owner->clock=std::move(clock);owner->cpu=owner->clock->cpu_domain();
            if(owner->cpu&&(!valid_cpu(*owner->cpu)||owner->cpu->id==wall.id))return error("timing.cpu","Invalid separate CPU clock domain");
            const auto& spans=input.spans;
            auto index=[&](ar::SpanId id)->std::optional<std::size_t>{
                auto found=std::lower_bound(spans.begin(),spans.end(),id.value,[](const auto& d,auto value){return d.id.value<value;});
                if(found==spans.end()||found->id!=id)return {};return static_cast<std::size_t>(found-spans.begin());
            };
            auto root=index(run);if(!root||spans[*root].parent)return error("timing.run","Run span must be a planned root");
            owner->run=*root;owner->slots.resize(spans.size());owner->children.resize(spans.size());
            auto ancestor=[&](std::size_t candidate,std::size_t descendant){
                auto parent=spans[descendant].parent;
                while(parent){auto at=*index(parent->id);if(at==candidate)return true;parent=spans[at].parent;}return false;
            };
            for(std::size_t i=0;i<spans.size();++i){
                if(spans[i].clock!=wall.id)return error("timing.clock","Every span must use the wall domain");
                if(i!=*root&&!ancestor(*root,i))return error("timing.run","Every span must descend from the run span");
                if(spans[i].parent)owner->children[*index(spans[i].parent->id)].push_back(i);
            }
            for(auto id:workers){
                auto at=index(id);if(!at||*at==*root)return error("timing.workers","Worker spans must be planned descendants");
                for(auto other:owner->workers)if(other==*at||ancestor(other,*at)||ancestor(*at,other))
                    return error("timing.workers","Worker spans must be unique with no ancestor/descendant pair");
                owner->workers.push_back(*at);
            }
        }
        return std::shared_ptr<TimingCollector>{new TimingCollector{std::move(owner)}};
    }catch(const std::bad_alloc&){return ar::ArtifactError{ar::ArtifactErrorCode::allocation,"timing.plan","Allocation failed"};}
}
CollectionResult<TimingScope> start_timing(const ExecutionContext& c,ar::SpanId id){return c.timing?c.timing->start(id,c):CollectionResult<TimingScope>{TimingScope{}};}
}
