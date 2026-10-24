#include <csl/execution/observability.hpp>
#include "../artifacts/collection_budget.hpp"
#include <algorithm>
#include <cstring>
#include <limits>

namespace csl::artifacts { ArtifactResult<bool> check_collection_layout(CollectionRecord); }

namespace csl::execution::observability {
namespace {
namespace ar=artifacts;
constexpr auto maximum=std::numeric_limits<std::uint64_t>::max();
struct Rejection {ar::ArtifactError error;};
void check(bool ok,std::string_view field,std::string_view message) {if(!ok)throw Rejection{{ar::ArtifactErrorCode::invalid_input,std::string(field),std::string(message)}};}
std::uint64_t add(std::uint64_t a,std::uint64_t b) {if(b>maximum-a)throw Rejection{{ar::ArtifactErrorCode::limit,"plan.bytes","Storage addition overflows"}};return a+b;}
std::uint64_t multiply(std::uint64_t a,std::uint64_t b) {if(a&&b>maximum/a)throw Rejection{{ar::ArtifactErrorCode::limit,"plan.bytes","Storage multiplication overflows"}};return a*b;}
void increment(ar::ExactCount& count,std::uint64_t n=1) noexcept {if(n>maximum-count.value){count.value=maximum;count.exact=false;}else count.value+=n;}
void combine(ar::ExactCount& to,const ar::ExactCount& from) noexcept {increment(to,from.value);to.exact=to.exact&&from.exact;}
bool utf8(std::string_view s) noexcept {
    for(std::size_t i=0;i<s.size();) {
        auto c=static_cast<unsigned char>(s[i++]);if(c<128)continue;
        unsigned count{};std::uint32_t cp{},min{};
        if(c>=0xc2&&c<=0xdf){count=1;cp=c&31;min=128;}
        else if(c>=0xe0&&c<=0xef){count=2;cp=c&15;min=2048;}
        else if(c>=0xf0&&c<=0xf4){count=3;cp=c&7;min=65536;}else return false;
        if(count>s.size()-i)return false;
        while(count--){c=static_cast<unsigned char>(s[i++]);if((c&0xc0)!=0x80)return false;cp=(cp<<6)|(c&63);}
        if(cp<min||cp>0x10ffff||(cp>=0xd800&&cp<=0xdfff))return false;
    }return true;
}
bool valid_termination(Termination value) noexcept {
    switch(value){
    case Termination::completed:
    case Termination::cancelled:
    case Termination::resource_limit:
    case Termination::numerical_failure:
    case Termination::operation_rejected:
    case Termination::contract_rejected:return true;
    }
    return false;
}
bool missing(ar::MissingReason reason)noexcept {return reason>=ar::MissingReason::not_requested&&reason<=ar::MissingReason::not_applicable;}
ar::Metric<std::int64_t> tick(TickValue value) {if(value.available)return ar::Available<std::int64_t>{value.value};return ar::Unavailable{value.missing,{}};}
struct Slot {
    std::size_t global;bool observed{};SpanCompletionView value{};
    std::size_t offset{},capacity{},size{};RecordDisposition disposition{RecordDisposition::unknown_span};
};
struct Counts {std::uint64_t id;ar::ExactCount duplicate,wrong,overflow;};

}
struct CollectionPlan::Storage {
    PlanInput input;
    std::vector<std::size_t> local;
    std::vector<std::uint64_t> bucket_ids;
};
struct ObservationShard::Storage {
    std::shared_ptr<const CollectionPlan::Storage> plan;
    ShardId id;std::vector<Slot> slots;std::vector<char> arena;std::vector<Counts> counts;
};
struct CollectionAccess {
    using ShardStorage=ObservationShard::Storage;
    static const auto& plan(const CollectionPlan& p){return p.storage_;}
    static auto& shard(ObservationShard& s){return s.storage_;}
    static CollectionPlan plan(PlanInput input,std::vector<std::size_t> local,std::vector<std::uint64_t> buckets){
        return CollectionPlan(std::make_shared<const CollectionPlan::Storage>(CollectionPlan::Storage{std::move(input),std::move(local),std::move(buckets)}));
    }
    static ObservationShard shard(const CollectionPlan& p,ShardId id) {
        auto s=std::make_unique<ObservationShard::Storage>();s->plan=p.storage_;s->id=id;
        const auto& input=p.description();const auto& settings=input.configuration.description().collection;
        const auto retained=std::min<std::uint64_t>(settings.detail_spans,input.spans.size());
        const auto each=retained?settings.detail_bytes/retained:0;
        std::size_t bytes=0;
        const auto owned=static_cast<std::size_t>(std::count_if(input.spans.begin(),input.spans.end(),[&](const auto& d){return d.shard==id.value;}));
        s->slots.reserve(owned);s->counts.reserve(owned+1);
        for(std::size_t i=0;i<input.spans.size();++i)if(input.spans[i].shard==id.value){
            Slot slot{};slot.global=i;slot.offset=bytes;
            slot.capacity=settings.mode==ar::CollectionMode::detail&&i<retained?static_cast<std::size_t>(each):0;
            bytes+=slot.capacity;s->slots.push_back(slot);
            const auto bucket=input.spans[i].bucket;
            if(std::none_of(s->counts.begin(),s->counts.end(),[&](const auto& b){return b.id==bucket;}))s->counts.push_back({bucket,{},{},{}});
        }
        s->counts.push_back({maximum,{},{},{}});std::sort(s->counts.begin(),s->counts.end(),[](const auto& a,const auto& b){return a.id<b.id;});s->arena.resize(bytes);
        return ObservationShard(std::move(s));
    }
};
CollectionPlan::CollectionPlan(std::shared_ptr<const Storage> p):storage_(std::move(p)){}
const PlanInput& CollectionPlan::description()const noexcept{return storage_->input;}
ObservationShard::ObservationShard(std::unique_ptr<Storage> p):storage_(std::move(p)){}
ObservationShard::ObservationShard(ObservationShard&&)noexcept=default;
ObservationShard& ObservationShard::operator=(ObservationShard&&)noexcept=default;
ObservationShard::~ObservationShard()=default;
RecordDisposition ObservationShard::record(SpanCompletionView value)noexcept {
    if(!storage_)return RecordDisposition::unknown_span;
    auto& s=*storage_;const auto& input=s.plan->input;
    const auto found=std::lower_bound(input.spans.begin(),input.spans.end(),value.id.value,[](const auto& d,auto id){return d.id.value<id;});
    if(found==input.spans.end()||found->id!=value.id)return RecordDisposition::unknown_span;
    auto bucket=std::lower_bound(s.counts.begin(),s.counts.end(),found->bucket,[](const auto& b,auto id){return b.id<id;});
    if(bucket==s.counts.end()||bucket->id!=found->bucket)bucket=std::prev(s.counts.end());
    if(found->shard!=s.id.value){increment(bucket->wrong);return RecordDisposition::wrong_shard;}
    const auto global=static_cast<std::size_t>(found-input.spans.begin());auto& slot=s.slots[s.plan->local[global]];
    if(slot.observed){increment(bucket->duplicate);return RecordDisposition::duplicate;}
    slot.observed=true;slot.value=value;slot.value.detail={};
    const bool fixed_valid=(value.execution>=ObservationState::returned&&value.execution<=ObservationState::unknown)&&
        (!value.start.available||value.start.value>=0)&&(!value.end.available||value.end.value>=0)&&
        (!value.start.available||!value.end.available||value.end.value>=value.start.value)&&
        (value.start.available||missing(value.start.missing))&&(value.end.available||missing(value.end.missing))&&
        (value.iterations.available||missing(value.iterations.missing))&&
        (!value.has_termination||valid_termination(value.termination))&&
        (value.execution!=ObservationState::not_called||(value.not_called_reason>=ar::NotCalledReason::capability_rejected&&value.not_called_reason<=ar::NotCalledReason::route_not_selected))&&
        (value.status>=CompletionStatus::returned&&value.status<=CompletionStatus::incomplete)&&
        (value.status!=CompletionStatus::returned||value.has_termination)&&
        (!value.has_outcome||(value.outcome>=MathematicalOutcome::optimal&&value.outcome<=MathematicalOutcome::undetermined));
    if(!fixed_valid){
        slot.value={{value.id.value},{false,0,ar::MissingReason::incomplete_span},{false,0,ar::MissingReason::incomplete_span},
            ObservationState::unknown,ar::NotCalledReason::task_not_admitted,false,Termination::numerical_failure,
            {false,0,ar::MissingReason::not_instrumented},{},CompletionStatus::incomplete,false,
            MathematicalOutcome::undetermined,{}, {}};
        return slot.disposition=RecordDisposition::detail_rejected;
    }
    if(input.configuration.description().collection.mode==ar::CollectionMode::summary)return slot.disposition=RecordDisposition::detail_dropped;
    if(global>=input.configuration.description().collection.detail_spans)return slot.disposition=RecordDisposition::detail_dropped;
    if(value.detail.size()>slot.capacity||!utf8(value.detail))return slot.disposition=RecordDisposition::detail_rejected;
    if(!value.detail.empty())std::memcpy(s.arena.data()+slot.offset,value.detail.data(),value.detail.size());
    slot.size=value.detail.size();return slot.disposition=RecordDisposition::retained;
}
void ObservationShard::record_overflow(std::uint64_t id,std::uint64_t count)noexcept {
    if(!storage_)return;
    auto& counts=storage_->counts;auto found=std::lower_bound(counts.begin(),counts.end(),id,[](const auto& b,auto value){return b.id<value;});
    if(found==counts.end()||found->id!=id)found=std::prev(counts.end());
    increment(found->overflow,count);
}
CollectionResult<CollectionPlan> make_collection_plan(PlanInput input) {
    try {
        const auto& settings=input.configuration.description().collection;
        check(input.run.value.size()>0,"plan.run","Run ID is required");
        check(input.spans.size()<=settings.plan_spans,"plan.spans","Plan span capacity exceeded");
        check(settings.enabled||(input.spans.empty()&&input.clocks.empty()&&input.shard_count==0&&input.tasks.empty()&&input.operations.empty()),"plan.disabled","Disabled collection admits no layout");
        auto bytes=multiply(input.shard_count,sizeof(std::size_t)+sizeof(Counts));
        bytes=add(bytes,multiply(input.spans.size(),sizeof(std::size_t)));
        if(settings.enabled&&settings.mode==ar::CollectionMode::detail){
            const auto retained=std::min<std::uint64_t>(settings.detail_spans,input.spans.size());
            const auto reserved=retained?multiply(settings.detail_bytes/retained,retained):0;
            check(reserved<=std::vector<char>{}.max_size(),"plan.bytes","Detail reservation exceeds native vector extent");
            bytes=add(bytes,reserved);
        }
        check(bytes<=std::numeric_limits<std::size_t>::max(),"plan.bytes","Storage exceeds platform width");
        check(input.shard_count<=input.spans.size()+1,"plan.shards","Shard layout must be bounded by admitted spans");
        if(settings.enabled&&!ar::collection_budget::planned(input.problem.identity(),input.configuration.identity(),input.run,
                input.clocks,input.spans,input.tasks,input.operations).fits(settings.plan_bytes))
            return ar::ArtifactError{ar::ArtifactErrorCode::limit,"plan.bytes","Planned metadata exceeds budget"};
        // Producer-only native slot/index/counter reservations are checked for
        // representability separately; portable metadata never uses sizeof.
        auto native=multiply(input.spans.size(),sizeof(ar::SpanDescriptor)+sizeof(ar::SpanRecord)+sizeof(Slot)+sizeof(std::size_t)+sizeof(std::uint64_t)+sizeof(Counts)+sizeof(ar::BucketSummary));
        native=add(native,multiply(input.shard_count,sizeof(std::size_t)+sizeof(Counts)));
        native=add(native,multiply(input.clocks.size(),sizeof(ar::ClockDomain)));
        native=add(native,multiply(add(input.tasks.size(),input.operations.size()),sizeof(std::string)));
        native=add(native,bytes);
        check(native<=std::numeric_limits<std::size_t>::max(),"plan.bytes","Native storage exceeds platform width");
        // Copy logical values after admission so moved-in spare vector/string capacity
        // is not retained by the immutable plan. Deep optional metadata is cloned below.
        input=PlanInput(input);
        std::sort(input.spans.begin(),input.spans.end(),[](const auto& a,const auto& b){return a.id.value<b.id.value;});
        std::vector<std::size_t> counts(static_cast<std::size_t>(input.shard_count),0),local;
        std::vector<std::uint64_t> buckets;
        local.reserve(input.spans.size());buckets.reserve(input.spans.size()+1);
        ar::CollectionRecord validation{input.problem.identity(),input.configuration.identity(),input.run,settings,input.clocks,{},{},ar::Unavailable{settings.enabled?ar::MissingReason::incomplete_span:ar::MissingReason::collection_disabled,{}}};
        validation.tasks=input.tasks;validation.operations=input.operations;
        for(auto& d:input.spans){
            if(d.backend)d.backend=std::make_shared<const ar::ModuleIdentity>(*d.backend);
            if(d.program)d.program=std::make_shared<const ProgramIdentity>(*d.program);
            if(d.input_representation)d.input_representation=std::make_shared<const RepresentationId>(*d.input_representation);
            if(d.output_representation)d.output_representation=std::make_shared<const RepresentationId>(*d.output_representation);
            if(d.relation_evidence)d.relation_evidence=std::make_shared<const GeometryEvidence>(*d.relation_evidence);
            if(d.input_summary)d.input_summary=std::make_shared<const ar::RepresentationSummary>(*d.input_summary);
            if(d.output_summary)d.output_summary=std::make_shared<const ar::RepresentationSummary>(*d.output_summary);
            check(d.shard<input.shard_count,"plan.shard","Span refers to an undeclared shard");
            check(d.bucket!=maximum,"plan.bucket","UINT64_MAX is reserved for unclassified observations");
            local.push_back(counts[static_cast<std::size_t>(d.shard)]++);
            if(std::find(buckets.begin(),buckets.end(),d.bucket)==buckets.end())buckets.push_back(d.bucket);
            validation.spans.push_back({d,ar::TickInterval{ar::Unavailable{ar::MissingReason::incomplete_span,{}},ar::Unavailable{ar::MissingReason::incomplete_span,{}}},ar::UnknownObservation{},
                ar::Unavailable{ar::MissingReason::incomplete_span,{}},ar::Unavailable{ar::MissingReason::not_instrumented,{}},ar::Unavailable{ar::MissingReason::incomplete_span,{}}});
        }
        auto checked=ar::check_collection_layout(std::move(validation));if(const auto* e=std::get_if<ar::ArtifactError>(&checked))return *e;
        std::sort(buckets.begin(),buckets.end());buckets.push_back(maximum);
        return CollectionAccess::plan(std::move(input),std::move(local),std::move(buckets));
    }catch(const Rejection& e){return e.error;}catch(const std::bad_alloc&){return ar::ArtifactError{ar::ArtifactErrorCode::allocation,{},{}};}
}
CollectionResult<ObservationShard> make_observation_shard(const CollectionPlan& p,ShardId id) {
    try {
        check(p.description().configuration.description().collection.enabled,"shard","Collection is disabled");
        check(id.value<p.description().shard_count,"shard.id","Unknown shard");
        return CollectionAccess::shard(p,id);
    }catch(const Rejection& e){return e.error;}catch(const std::bad_alloc&){return ar::ArtifactError{ar::ArtifactErrorCode::allocation,{},{}};}
}
CollectionResult<ar::CollectedStatistics> merge_observations(const CollectionPlan& plan,std::vector<ObservationShard> shards) {
    try {
        const auto& input=plan.description();const auto& settings=input.configuration.description().collection;
        std::vector<CollectionAccess::ShardStorage*> owners(static_cast<std::size_t>(input.shard_count),nullptr);
        for(auto& shard:shards){auto& s=CollectionAccess::shard(shard);check(s&&s->plan==CollectionAccess::plan(plan),"merge.owner","Foreign or moved shard");
            auto& slot=owners[static_cast<std::size_t>(s->id.value)];check(slot==nullptr,"merge.shard","Duplicate shard");slot=s.get();}
        ar::CollectionRecord result{input.problem.identity(),input.configuration.identity(),input.run,settings,input.clocks,{},{},
            settings.enabled?ar::Metric<bool>{ar::Available<bool>{true}}:ar::Metric<bool>{ar::Unavailable{ar::MissingReason::collection_disabled,{}}}};
        result.tasks=input.tasks;result.operations=input.operations;
        if(!settings.enabled)return ar::publish_collection(std::move(result));
        for(auto id:CollectionAccess::plan(plan)->bucket_ids)result.buckets.push_back({id,{},{},{},{},{},{},{},ar::Available<std::uint64_t>{0},{},{},{},{}});
        for(std::size_t i=0;i<input.spans.size();++i){
            const auto& d=input.spans[i];auto* owner=owners[static_cast<std::size_t>(d.shard)];
            const auto* slot=owner?&owner->slots[CollectionAccess::plan(plan)->local[i]]:nullptr;
            ar::SpanRecord record{d,ar::TickInterval{ar::Unavailable{ar::MissingReason::incomplete_span,{}},ar::Unavailable{ar::MissingReason::incomplete_span,{}}},ar::UnknownObservation{},
                ar::Unavailable{ar::MissingReason::incomplete_span,{}},ar::Unavailable{ar::MissingReason::not_instrumented,{}},ar::Unavailable{ar::MissingReason::incomplete_span,{}}};
            auto& bucket=*std::lower_bound(result.buckets.begin(),result.buckets.end(),d.bucket,[](const auto& b,auto id){return b.id<id;});
            if(bucket.clock.value.empty())bucket.clock=d.clock;
            if(slot&&slot->observed){
                record.completion_observed=true;
                const auto& v=slot->value;record.interval=ar::TickInterval{tick(v.start),tick(v.end)};
                if(v.execution==ObservationState::returned)record.execution=ar::ReturnedObservation{};
                else if(v.execution==ObservationState::not_called){record.execution=ar::NotCalledObservation{v.not_called_reason,d.observation_source,d.module.version};increment(bucket.not_called);}
                else increment(bucket.unknown);
                if(v.status==CompletionStatus::returned){
                    ar::Metric<MathematicalOutcome> outcome=ar::Unavailable{ar::MissingReason::not_instrumented,{}};
                    if(v.has_outcome)outcome=ar::Available<MathematicalOutcome>{v.outcome};
                    record.status=ar::ReturnedSpan{v.termination,std::move(outcome)};
                }else if(v.status==CompletionStatus::rejected)record.status=ar::RejectedSpan{
                    slot->size?std::string(owner->arena.data()+slot->offset,slot->size):"capability_rejected"};
                else if(v.status==CompletionStatus::skipped)record.status=ar::SkippedSpan{"task_not_admitted"};
                else if(v.status==CompletionStatus::failed){record.status=ar::FailedSpan{"unspecified","producer_reported"};increment(bucket.failed);}
                else increment(bucket.incomplete);
                if(v.has_termination)record.termination=ar::Available<Termination>{v.termination};
                if(v.relation_evidence)record.descriptor.relation_evidence=v.relation_evidence;
                record.descriptor.applied_relation=v.applied_relation;
                if(v.iterations.available)record.iterations=ar::Available<std::uint64_t>{v.iterations.value};else record.iterations=ar::Unavailable{v.iterations.missing,{}};
                increment(bucket.observed);
                if(slot->disposition==RecordDisposition::retained){record.detail=ar::Available<std::string>{slot->size?std::string(owner->arena.data()+slot->offset,slot->size):std::string{}};record.detail_state=ar::DetailState::retained;}
                else if(settings.mode==ar::CollectionMode::summary){record.detail=ar::Unavailable{ar::MissingReason::not_requested,{}};record.detail_state=ar::DetailState::not_requested;}
                else {record.detail=ar::Unavailable{ar::MissingReason::detail_limit,{}};record.detail_state=slot->disposition==RecordDisposition::detail_rejected?ar::DetailState::rejected:ar::DetailState::capacity_dropped;increment(bucket.detail_dropped);}
                const auto duration=ar::elapsed_ticks(std::get<ar::TickInterval>(record.interval));
                if(const auto* value=std::get_if<ar::Available<std::uint64_t>>(&duration)){
                    increment(bucket.duration_contributors);
                    if(bucket.clock!=d.clock)bucket.inclusive_ticks=ar::Unavailable{ar::MissingReason::clock_mismatch,{}};
                    else if(auto* sum=std::get_if<ar::Available<std::uint64_t>>(&bucket.inclusive_ticks)){
                        if(value->value>maximum-sum->value)bucket.inclusive_ticks=ar::Unavailable{ar::MissingReason::overflow,{}};
                        else sum->value+=value->value;
                    }
                }
            }else {result.complete=ar::Unavailable{ar::MissingReason::incomplete_span,{}};increment(bucket.incomplete);increment(bucket.unknown);}
            result.spans.push_back(std::move(record));
        }
        for(const auto* owner:owners)if(owner)for(const auto& counts:owner->counts){
            auto& b=*std::lower_bound(result.buckets.begin(),result.buckets.end(),counts.id,[](const auto& x,auto id){return x.id<id;});
            combine(b.duplicate,counts.duplicate);combine(b.wrong_shard,counts.wrong);combine(b.declared_overflow,counts.overflow);
        }
        return ar::publish_collection(std::move(result));
    }catch(const Rejection& e){return e.error;}catch(const std::bad_alloc&){return ar::ArtifactError{ar::ArtifactErrorCode::allocation,{},{}};}
}
} // namespace csl::execution::observability
namespace csl::execution::observability {
artifacts::ExecutionSummary project_execution(const BatchTiming& value) {
    static_assert(std::is_signed_v<TimePoint::duration::rep> && sizeof(TimePoint::duration::rep)<=sizeof(std::int64_t));
    const auto relative=[&](TimePoint point)->artifacts::Metric<std::int64_t>{
        const auto a=static_cast<std::int64_t>(point.time_since_epoch().count());
        const auto b=static_cast<std::int64_t>(value.started_at.time_since_epoch().count());
        if((b>0&&a<std::numeric_limits<std::int64_t>::min()+b)||(b<0&&a>std::numeric_limits<std::int64_t>::max()+b))
            return artifacts::Unavailable{artifacts::MissingReason::overflow,{}};
        return artifacts::Available<std::int64_t>{a-b};
    };
    const auto optional=[&](std::optional<TimePoint> p)->artifacts::Metric<std::int64_t>{
        if(p)return relative(*p);
        return artifacts::Unavailable{artifacts::MissingReason::not_requested,{}};
    };
    std::optional<artifacts::AdmissionObservation> closed;
    if(value.admission_closed){
        artifacts::AdmissionCause cause{};
        switch(value.admission_closed->cause){
        case BatchStopCause::cancelled:cause=artifacts::AdmissionCause::cancelled;break;
        case BatchStopCause::deadline:cause=artifacts::AdmissionCause::deadline;break;
        case BatchStopCause::task_limit:cause=artifacts::AdmissionCause::task_limit;break;
        case BatchStopCause::allocation:cause=artifacts::AdmissionCause::allocation;break;
        case BatchStopCause::adapter_exception:cause=artifacts::AdmissionCause::adapter_exception;break;
        case BatchStopCause::thread_launch:cause=artifacts::AdmissionCause::thread_launch;break;
        }
        closed=artifacts::AdmissionObservation{cause,relative(value.admission_closed->observed_at)};
    }
    artifacts::ClockDomain clock{{"steady"},artifacts::ClockMetric::steady_wall,"batch",
        static_cast<std::uint64_t>(TimePoint::duration::period::num),static_cast<std::uint64_t>(TimePoint::duration::period::den),
        artifacts::Unavailable{artifacts::MissingReason::not_instrumented,{}},"batch.started_at",artifacts::Unavailable{artifacts::MissingReason::not_instrumented,{}}};
    return {optional(value.configured_deadline),std::move(closed),optional(value.external_cancellation_observed_at),relative(value.workers_joined_at),relative(value.completed_at),std::move(clock),artifacts::Available<std::int64_t>{0},{}};
}
artifacts::ResourceObservation project_resources(const EnforcementReport& value) {
    artifacts::Metric<std::uint64_t> bytes=artifacts::Unavailable{artifacts::MissingReason::not_requested,{}};
    if(value.peak_workspace_reservation_bytes)bytes=artifacts::Available<std::uint64_t>{*value.peak_workspace_reservation_bytes};
    return {artifacts::Available<std::uint64_t>{value.peak_active_tasks},artifacts::Available<std::uint64_t>{value.peak_reserved_threads},std::move(bytes),
        artifacts::Unavailable{artifacts::MissingReason::not_instrumented,{}},true,
        value.memory==MemoryEnforcement::unlimited_accounting?artifacts::MemoryAccounting::unlimited:artifacts::MemoryAccounting::active_reservations};
}
}
namespace csl::execution::observability {
artifacts::ExecutionSummary::Task project_task(const TaskId& id,const TaskTiming& value,TimePoint origin,artifacts::SpanStatus status) {
    const auto relative=[&](std::optional<TimePoint> p)->artifacts::Metric<std::int64_t>{
        if(!p)return artifacts::Unavailable{artifacts::MissingReason::not_requested,{}};
        const auto a=static_cast<std::int64_t>(p->time_since_epoch().count());const auto b=static_cast<std::int64_t>(origin.time_since_epoch().count());
        if((b>0&&a<std::numeric_limits<std::int64_t>::min()+b)||(b<0&&a>std::numeric_limits<std::int64_t>::max()+b))return artifacts::Unavailable{artifacts::MissingReason::overflow,{}};
        return artifacts::Available<std::int64_t>{a-b};
    };
    return {id.value,relative(value.queued_at),relative(value.admitted_at),relative(value.create_started_at),relative(value.create_finished_at),relative(value.call_started_at),relative(value.call_finished_at),relative(value.released_at),std::move(status)};
}
}
