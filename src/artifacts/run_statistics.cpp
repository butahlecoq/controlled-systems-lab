#include <csl/artifacts/run_statistics.hpp>
#include <limits>
#include <algorithm>
#include <cmath>
#include <set>
#include <unordered_map>

namespace csl::artifacts {
namespace {bool support_valid(const EvidenceSupport&);bool identity(std::string_view,std::string_view);}
ArtifactResult<std::string> check_record_portability(const RunRecord&);
ArtifactResult<bool> check_collection_portability(const CollectionRecord&);
struct RunStatistics::Storage {RunRecord record;std::string wire;};
RunStatistics::RunStatistics(std::shared_ptr<const Storage> p):storage_(std::move(p)){}
const RunRecord& RunStatistics::description()const noexcept{return storage_->record;}
CollectedStatistics::CollectedStatistics(std::shared_ptr<const CollectionRecord> p):storage_(std::move(p)){}
const CollectionRecord& CollectedStatistics::description()const noexcept{return *storage_;}
ArtifactResult<std::string> configuration_json(const ConfigurationInput&,bool);
struct ResolvedConfiguration::Storage { ConfigurationInput input; ConfigId identity; std::vector<std::byte> bytes; };
struct ArtifactAccess {
    static RunStatistics run(RunRecord input,std::string wire) {
        return RunStatistics(std::make_shared<const RunStatistics::Storage>(RunStatistics::Storage{std::move(input),std::move(wire)}));
    }
    static std::string_view wire(const RunStatistics& owner)noexcept{return owner.storage_->wire;}
    static CollectedStatistics collection(CollectionRecord input) {
        return CollectedStatistics(std::make_shared<const CollectionRecord>(std::move(input)));
    }
    static ResolvedConfiguration configuration(ConfigurationInput input,ConfigId id,std::vector<std::byte> bytes) {
        return ResolvedConfiguration(std::make_shared<const ResolvedConfiguration::Storage>(
            ResolvedConfiguration::Storage{std::move(input),std::move(id),std::move(bytes)}));
    }
};
std::string_view recorded_json(const RunStatistics& owner)noexcept{return ArtifactAccess::wire(owner);}
ResolvedConfiguration::ResolvedConfiguration(std::shared_ptr<const Storage> p):storage_(std::move(p)) {}
const ConfigId& ResolvedConfiguration::identity() const noexcept {return storage_->identity;}
const ConfigurationInput& ResolvedConfiguration::description() const noexcept {return storage_->input;}
std::span<const std::byte> ResolvedConfiguration::canonical_bytes() const noexcept {return storage_->bytes;}
ArtifactResult<ResolvedConfiguration> resolve_configuration(ConfigurationInput input) {
    try {
        auto encoded=configuration_json(input,true);
        if(auto* e=std::get_if<ArtifactError>(&encoded)) return *e;
        constexpr char prefix[]="CSL.RESOLVED.CONFIG\0v1\0";
        std::vector<std::byte> bytes;
        bytes.reserve(sizeof(prefix)-1+std::get<std::string>(encoded).size());
        for(std::size_t i=0;i<sizeof(prefix)-1;++i) bytes.push_back(static_cast<std::byte>(prefix[i]));
        for(unsigned char c:std::get<std::string>(encoded)) bytes.push_back(static_cast<std::byte>(c));
        auto content=problem::snapshot_content(bytes);
        if(const auto* owned=std::get_if<problem::ResolvedContent>(&content)) {
            ConfigId id{"csl.config.v1.sha256:"+problem::hex(owned->digest())};
            return ArtifactAccess::configuration(std::move(input),std::move(id),std::move(bytes));
        }
        return ArtifactError{ArtifactErrorCode::allocation,"configuration","Cannot own canonical content"};
    } catch(const std::bad_alloc&) {
        return ArtifactError{ArtifactErrorCode::allocation,{},{}};
    }
}
Metric<std::uint64_t> elapsed_ticks(const TickInterval& interval) noexcept {
    const auto* start=std::get_if<Available<std::int64_t>>(&interval.start);
    const auto* end=std::get_if<Available<std::int64_t>>(&interval.end);
    if(!start||!end) return Unavailable{MissingReason::incomplete_span,{}};
    if(end->value<start->value) return Unavailable{MissingReason::clock_mismatch,{}};
    const auto difference=static_cast<std::uint64_t>(end->value)-static_cast<std::uint64_t>(start->value);
    if(difference>static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max()))
        return Unavailable{MissingReason::overflow,{}};
    return Available<std::uint64_t>{difference};
}
}

namespace csl::artifacts {
static ArtifactResult<CollectedStatistics> checked_collection(CollectionRecord input,bool aggregates) {
    try {
        const auto error=[](std::string path,std::string message)->ArtifactResult<CollectedStatistics>{return ArtifactError{ArtifactErrorCode::invalid_input,std::move(path),std::move(message)};};
        const auto& settings=input.settings;
        if(input.problem.value.size()!=86||!input.problem.value.starts_with("csl.problem.v1.sha256:")||
            !std::all_of(input.problem.value.begin()+22,input.problem.value.end(),[](char c){return (c>='0'&&c<='9')||(c>='a'&&c<='f');}))return error("collection.problem","Expected a MODEL03 identity");
        if(!identity(input.configuration.value,"csl.config.v1.sha256:")||input.run.value.empty())return error("collection.identity","Invalid configuration or run identity");
        if(settings.mode!=CollectionMode::detail&&settings.mode!=CollectionMode::summary)return error("collection.mode","Unknown collection mode");
        if(settings.detail_spans>settings.plan_spans||input.spans.size()>settings.plan_spans)return error("collection.spans","Capacity exceeded");
        if(!settings.enabled&&(!input.spans.empty()||!input.buckets.empty()||!input.clocks.empty()||!input.tasks.empty()||!input.operations.empty()))return error("collection.disabled","Disabled collection contains observations");
        std::set<std::string> tasks,operations;
        if(input.tasks.size()>input.spans.size()||input.operations.size()>input.spans.size())return error("collection.dictionary","Dictionary exceeds declared layout");
        for(const auto& task:input.tasks)if(task.empty()||!tasks.insert(task).second)return error("collection.tasks","Empty or duplicate declared task");
        for(const auto& operation:input.operations)if(operation.empty()||!operations.insert(operation).second)return error("collection.operations","Empty or duplicate declared operation");
        if(aggregates&&!settings.enabled){const auto* complete=std::get_if<Unavailable>(&input.complete);if(!complete||complete->reason!=MissingReason::collection_disabled)return error("collection.complete","Disabled collection has no observed completeness");}
        std::set<std::string> clocks;
        for(const auto& c:input.clocks){
            if(c.id.value.empty()||c.scope.empty()||c.origin_label.empty()||!clocks.insert(c.id.value).second||!c.period_numerator||!c.period_denominator||
                c.metric<ClockMetric::steady_wall||c.metric>ClockMetric::process_cpu)return error("collection.clocks","Invalid or duplicate clock");
        }
        std::unordered_map<std::uint64_t,std::size_t> ids;std::uint64_t retained=0,detail_bytes=0;
        ids.reserve(input.spans.size());
        for(auto& s:input.spans){
            auto& d=s.descriptor;
            if(d.backend)d.backend=std::make_shared<const ModuleIdentity>(*d.backend);
            if(d.program)d.program=std::make_shared<const ProgramIdentity>(*d.program);
            if(d.input_representation)d.input_representation=std::make_shared<const RepresentationId>(*d.input_representation);
            if(d.output_representation)d.output_representation=std::make_shared<const RepresentationId>(*d.output_representation);
            if(d.relation_evidence)d.relation_evidence=std::make_shared<const GeometryEvidence>(*d.relation_evidence);
            if(d.input_summary)d.input_summary=std::make_shared<const RepresentationSummary>(*d.input_summary);
            if(d.output_summary)d.output_summary=std::make_shared<const RepresentationSummary>(*d.output_summary);
            if(!ids.emplace(d.id.value,ids.size()).second)return error("collection.spans.id","Duplicate span");
            if(!clocks.contains(d.clock.value))return error("collection.spans.clock","Unknown clock");
            if(d.task.empty()||d.operation.empty()||d.module.id.value.empty()||d.module.version.empty())return error("collection.spans.module","Unresolved span provenance");
            if(!tasks.contains(d.task)||!operations.contains(d.operation))return error("collection.spans.reference","Undeclared task or operation");
            if(d.program&&d.program->problem!=input.problem)return error("collection.spans.program","Foreign operation problem");
            if(d.bucket==std::numeric_limits<std::uint64_t>::max())return error("collection.spans.bucket","Reserved unclassified bucket cannot own a planned span");
            if(d.relation_evidence){const auto& e=*d.relation_evidence;
                if(e.reference.identity.problem!=input.problem||e.reference.identity.request.value.empty()||e.reference.identity.ideal_output.value.empty()||!support_valid(e.support)||(d.relation&&e.scope!=GeometryClaimScope::set_relation))return error("collection.spans.evidence","Foreign or invalid geometry reference");
                for(const auto& set:e.reference.inputs)if(set.value.empty())return error("collection.spans.evidence","Empty input set reference");
                if(e.error_bound&&(!std::isfinite(e.error_bound->bound)||e.error_bound->bound<0||e.error_bound->metric.value.empty()||e.error_bound->units.empty()))return error("collection.spans.evidence","Invalid error bound");
            }
            if(const auto* not_called=std::get_if<NotCalledObservation>(&s.execution);not_called&&(not_called->source_location.empty()||not_called->source_version.empty()))return error("collection.spans.execution","Not-called observation needs source provenance");
            if(!s.completion_observed&&(!std::holds_alternative<IncompleteSpan>(s.status)||!std::holds_alternative<UnknownObservation>(s.execution)))return error("collection.spans.status","Unobserved completion cannot claim returned status");
            if(!s.completion_observed&&s.detail_state!=DetailState::not_observed)return error("collection.spans.detail","Unobserved completion cannot retain detail");
            if(s.detail_state==DetailState::retained&&!std::holds_alternative<Available<std::string>>(s.detail))return error("collection.spans.detail","Retained detail is unavailable");
            if(std::holds_alternative<Available<std::string>>(s.detail)&&s.detail_state!=DetailState::retained)return error("collection.spans.detail","Available detail lacks retained disposition");
            if(s.completion_observed&&s.detail_state==DetailState::not_observed)return error("collection.spans.detail","Observed completion needs an explicit detail disposition");
            if(s.detail_state==DetailState::not_requested&&(settings.mode!=CollectionMode::summary||!std::holds_alternative<Unavailable>(s.detail)||std::get<Unavailable>(s.detail).reason!=MissingReason::not_requested))return error("collection.spans.detail","Not-requested detail requires summary mode and reason");
            if((s.detail_state==DetailState::capacity_dropped||s.detail_state==DetailState::rejected)&&(settings.mode!=CollectionMode::detail||!std::holds_alternative<Unavailable>(s.detail)||std::get<Unavailable>(s.detail).reason!=MissingReason::detail_limit))return error("collection.spans.detail","Dropped detail requires detail mode and limit reason");
            if(d.requested_assurance!=Assurance::numerical&&d.requested_assurance!=Assurance::validated)return error("collection.spans.assurance","Unknown assurance");
            if(const auto* a=std::get_if<Available<Assurance>>(&d.applied_assurance);a&&a->value!=Assurance::numerical)return error("collection.spans.assurance","Validated application is unsupported");
            if(d.relation&&(*d.relation<SetRelation::equivalent||*d.relation>SetRelation::heuristic))return error("collection.spans.relation","Unknown relation");
            if(const auto* ticks=std::get_if<TickInterval>(&s.interval)){
                const auto* start=std::get_if<Available<std::int64_t>>(&ticks->start);const auto* end=std::get_if<Available<std::int64_t>>(&ticks->end);
                if((start&&start->value<0)||(end&&end->value<0)||(start&&end&&end->value<start->value))return error("collection.spans.interval","Invalid measured interval");
            }else {const auto& legacy=std::get<LegacySecondsInterval>(s.interval);if(!std::isfinite(legacy.start)||!std::isfinite(legacy.end)||legacy.start<0||legacy.end<legacy.start)return error("collection.spans.interval","Invalid legacy seconds");}
            if(const auto* detail=std::get_if<Available<std::string>>(&s.detail)){
                if(settings.mode!=CollectionMode::detail)return error("collection.detail","Summary mode forbids variable detail");
                ++retained;if(detail->value.size()>settings.detail_bytes-detail_bytes)return error("collection.detail","Detail byte capacity exceeded");detail_bytes+=detail->value.size();
            }
        }
        if(retained>settings.detail_spans)return error("collection.detail","Detail span capacity exceeded");
        const auto none=std::numeric_limits<std::size_t>::max();
        std::vector<std::size_t> parents(input.spans.size(),none);
        for(std::size_t index=0;index<input.spans.size();++index){
            const auto& current=input.spans[index];
            if(!current.descriptor.parent)continue;
            const auto parent=*current.descriptor.parent;
            if(parent.kind!=ParentKind::nested&&parent.kind!=ParentKind::spawned)return error("collection.spans.parent","Unknown parent kind");
            const auto found=ids.find(parent.id.value);
            if(found==ids.end())return error("collection.spans.parent","Dangling span parent");
            parents[index]=found->second;const auto& outer_span=input.spans[found->second];
            if(parent.kind==ParentKind::nested&&current.descriptor.clock==outer_span.descriptor.clock){
                const auto* child=std::get_if<TickInterval>(&current.interval);const auto* outer=std::get_if<TickInterval>(&outer_span.interval);
                if(child&&outer){const auto* cs=std::get_if<Available<std::int64_t>>(&child->start);const auto* ce=std::get_if<Available<std::int64_t>>(&child->end);
                    const auto* ps=std::get_if<Available<std::int64_t>>(&outer->start);const auto* pe=std::get_if<Available<std::int64_t>>(&outer->end);
                    if((cs&&ps&&cs->value<ps->value)||(ce&&pe&&ce->value>pe->value))return error("collection.spans.parent","Nested span lies outside parent");}
                const auto* legacy_child=std::get_if<LegacySecondsInterval>(&current.interval);const auto* legacy_parent=std::get_if<LegacySecondsInterval>(&outer_span.interval);
                if(legacy_child&&legacy_parent&&(legacy_child->start<legacy_parent->start||legacy_child->end>legacy_parent->end))return error("collection.spans.parent","Legacy nested span lies outside parent");
            }
        }
        // Each node is colored twice at most; each declared parent edge is walked twice.
        std::vector<unsigned char> colors(input.spans.size(),0);
        for(std::size_t index=0;index<input.spans.size();++index){
            auto current=index;
            while(current!=none&&colors[current]==0){colors[current]=1;current=parents[current];}
            if(current!=none&&colors[current]==1)return error("collection.spans.parent","Cyclic span parentage");
            current=index;while(current!=none&&colors[current]==1){colors[current]=2;current=parents[current];}
        }
        if(aggregates){
            if(input.buckets.size()>input.spans.size()+1)return error("collection.buckets","Bucket layout exceeds admitted spans");
            std::unordered_map<std::uint64_t,std::vector<const SpanRecord*>> groups;
            groups.reserve(input.buckets.size());
            for(const auto& bucket:input.buckets)if(!groups.emplace(bucket.id,std::vector<const SpanRecord*>{}).second)return error("collection.buckets","Duplicate bucket");
            for(const auto& span:input.spans){const auto group=groups.find(span.descriptor.bucket);if(group==groups.end())return error("collection.buckets","Missing declared span bucket");group->second.push_back(&span);}
            for(const auto& bucket:input.buckets){
                std::uint64_t observed=0,dropped=0,contributors=0,sum=0,failed=0,not_called=0,unknown=0,incomplete=0;
                bool overflow=false,mismatch=false;std::string clock;
                for(const auto* entry:groups.at(bucket.id)){
                    const auto& span=*entry;
                    if(clock.empty())clock=span.descriptor.clock.value;
                    if(!span.completion_observed){++incomplete;++unknown;continue;}
                    ++observed;
                    if(std::holds_alternative<FailedSpan>(span.status))++failed;
                    if(std::holds_alternative<IncompleteSpan>(span.status))++incomplete;
                    if(std::holds_alternative<NotCalledObservation>(span.execution))++not_called;
                    if(std::holds_alternative<UnknownObservation>(span.execution))++unknown;
                    if(const auto* detail=std::get_if<Unavailable>(&span.detail);detail&&detail->reason==MissingReason::detail_limit)++dropped;
                    if(settings.mode==CollectionMode::summary&&(!std::holds_alternative<Unavailable>(span.detail)||std::get<Unavailable>(span.detail).reason!=MissingReason::not_requested))return error("collection.detail","Summary omission must be not_requested");
                    if(const auto* ticks=std::get_if<TickInterval>(&span.interval)){
                        const auto duration=elapsed_ticks(*ticks);
                        if(const auto* value=std::get_if<Available<std::uint64_t>>(&duration)){
                            ++contributors;if(clock!=span.descriptor.clock.value)mismatch=true;
                            if(value->value>std::numeric_limits<std::uint64_t>::max()-sum)overflow=true;else if(!overflow)sum+=value->value;
                        }
                    }
                }
                const auto exact=[](const ExactCount& count,std::uint64_t value){return count.exact&&count.value==value;};
                if(!exact(bucket.observed,observed)||!exact(bucket.detail_dropped,dropped)||!exact(bucket.duration_contributors,contributors)||!exact(bucket.failed,failed)||!exact(bucket.not_called,not_called)||!exact(bucket.unknown,unknown)||!exact(bucket.incomplete,incomplete))return error("collection.buckets.counts","Summary disagrees with retained observations");
                if(!clock.empty()&&bucket.clock.value!=clock)return error("collection.buckets.clock","Summary clock differs from declared bucket");
                if(mismatch||overflow){const auto* u=std::get_if<Unavailable>(&bucket.inclusive_ticks);if(!u||u->reason!=(mismatch?MissingReason::clock_mismatch:MissingReason::overflow))return error("collection.buckets.duration","Invalid unavailable work sum");}
                else {const auto* value=std::get_if<Available<std::uint64_t>>(&bucket.inclusive_ticks);if(!value||value->value!=sum)return error("collection.buckets.duration","Work sum differs from retained intervals");}
                for(const auto* count:{&bucket.duplicate,&bucket.wrong_shard,&bucket.declared_overflow})if(!count->exact&&count->value!=std::numeric_limits<std::uint64_t>::max())return error("collection.buckets.counts","Nonexact counter must be saturated");
            }
            if(const auto* complete=std::get_if<Available<bool>>(&input.complete);complete&&complete->value&&std::any_of(input.spans.begin(),input.spans.end(),[](const auto& s){return !s.completion_observed;}))return error("collection.complete","Missing completions cannot be complete");
        }
        const auto portable=check_collection_portability(input);
        if(const auto* e=std::get_if<ArtifactError>(&portable))return *e;
        return ArtifactAccess::collection(std::move(input));
    }catch(const std::bad_alloc&){return ArtifactError{ArtifactErrorCode::allocation,{},{}};}
}
ArtifactResult<CollectedStatistics> publish_collection(CollectionRecord input){return checked_collection(std::move(input),true);}
ArtifactResult<bool> check_collection_layout(CollectionRecord input){auto checked=checked_collection(std::move(input),false);if(const auto* error=std::get_if<ArtifactError>(&checked))return *error;return true;}
} // namespace csl::artifacts

namespace csl::artifacts {
namespace {
bool identity(std::string_view value,std::string_view prefix) {
    return value.starts_with(prefix)&&value.size()==prefix.size()+64&&std::all_of(value.begin()+static_cast<std::ptrdiff_t>(prefix.size()),value.end(),[](char c){return (c>='0'&&c<='9')||(c>='a'&&c<='f');});
}
bool relative_path(std::string_view value){
    if(value.empty()||value.front()=='/'||value.back()=='/')return false;
    for(char c:value)if(static_cast<unsigned char>(c)<32||c=='\\'||c==':')return false;
    std::size_t begin=0;while(begin<value.size()){const auto end=value.find('/',begin);const auto part=value.substr(begin,end==std::string_view::npos?value.size()-begin:end-begin);if(part.empty()||part=="."||part=="..")return false;if(end==std::string_view::npos)break;begin=end+1;}return true;
}
bool finite_vector(const Vector& v){return std::all_of(v.begin(),v.end(),[](double x){return std::isfinite(x);});}
bool support_valid(const EvidenceSupport& support){
    if(const auto* n=std::get_if<NumericalCheck>(&support))return std::isfinite(n->absolute_tolerance)&&n->absolute_tolerance>=0&&std::isfinite(n->relative_tolerance)&&n->relative_tolerance>=0&&std::isfinite(n->max_residual)&&n->max_residual>=0&&!n->verifier.value.empty();
    return true;
}
}
ArtifactResult<RunStatistics> publish_record(RunRecord input) {
    try {
        const auto reject=[](std::string path,std::string message)->ArtifactResult<RunStatistics>{return ArtifactError{ArtifactErrorCode::invalid_input,std::move(path),std::move(message)};};
        if(!identity(input.problem.value,"csl.problem.v1.sha256:")||input.run.value.empty())return reject("run.problem","Invalid run or mathematical identity");
        const auto& statistics=input.statistics.description();
        if(statistics.problem!=input.problem||statistics.configuration!=input.configuration.identity()||statistics.run!=input.run||statistics.settings!=input.configuration.description().collection)return reject("run.statistics","Foreign problem, configuration, run or collection policy");
        const auto same_pin=[](const PinAvailability& a,const PinAvailability& b){
            const auto* left=std::get_if<Available<ModulePin>>(&a);const auto* right=std::get_if<Available<ModulePin>>(&b);
            if(left||right)return left&&right&&left->value.scope==right->value.scope&&left->value.sha256==right->value.sha256;
            return std::get<Unavailable>(a).reason==std::get<Unavailable>(b).reason;
        };
        const auto selected=[&](const ModuleIdentity& module){return std::any_of(input.configuration.description().modules.begin(),input.configuration.description().modules.end(),[&](const auto& m){return m.implementation.id.value==module.id.value&&m.implementation.version==module.version&&same_pin(m.implementation.pin,module.pin);});};
        for(const auto& span:statistics.spans){
            if(!selected(span.descriptor.module)||(span.descriptor.backend&&!selected(*span.descriptor.backend)))return reject("run.statistics.module","Span implementation is outside the resolved configuration");
            if(span.descriptor.stage&&*span.descriptor.stage>input.horizon)return reject("run.statistics.stage","Stage exceeds the supplied horizon");
        }
        if(input.execution){const auto& execution=*input.execution;
            if(!execution.clock.period_numerator||!execution.clock.period_denominator||execution.clock.id.value.empty()||execution.clock.scope.empty()||execution.clock.origin_label.empty())return reject("run.execution.clock","Incomplete execution clock");
            const auto event=[](const Metric<std::int64_t>& value){const auto* a=std::get_if<Available<std::int64_t>>(&value);return !a||a->value>=0;};
            const auto ordered=[](const Metric<std::int64_t>& a,const Metric<std::int64_t>& b){const auto* av=std::get_if<Available<std::int64_t>>(&a);const auto* bv=std::get_if<Available<std::int64_t>>(&b);return !av||!bv||av->value<=bv->value;};
            for(const auto* value:{&execution.started,&execution.external_cancellation,&execution.workers_joined,&execution.completed})if(!event(*value))return reject("run.execution.timing","Negative observed event");
            if(!ordered(execution.started,execution.workers_joined)||!ordered(execution.workers_joined,execution.completed)||!ordered(execution.started,execution.external_cancellation)||!ordered(execution.external_cancellation,execution.completed))return reject("run.execution.timing","Contradictory batch chronology");
            if(execution.admission_closed&&(!event(execution.admission_closed->at)||!ordered(execution.started,execution.admission_closed->at)||!ordered(execution.admission_closed->at,execution.completed)))return reject("run.execution.timing","Contradictory admission-close observation");
            std::set<std::string> tasks;
            for(const auto& task:execution.tasks){
                if(task.id.empty()||!tasks.insert(task.id).second)return reject("run.execution.tasks","Empty or duplicate task ID");
                const Metric<std::int64_t>* previous=&execution.started;
                for(const auto* value:{&task.queued,&task.admitted,&task.create_started,&task.create_finished,&task.call_started,&task.call_finished,&task.released}){
                    if(!event(*value)||!ordered(*previous,*value)||!ordered(*value,execution.completed))return reject("run.execution.tasks","Contradictory task chronology");
                    if(std::holds_alternative<Available<std::int64_t>>(*value))previous=value;
                }
            }
        }
        std::set<std::string> attachments;
        for(const auto& a:input.attachments){
            if(a.id.value.empty()||!attachments.insert(a.id.value).second||a.media_type.empty()||a.schema.empty())return reject("run.attachments","Invalid attachment identity or schema");
            if(a.relative_path&&!relative_path(*a.relative_path))return reject("run.attachments.path","Unsafe relative attachment path");
            if(a.content&&(a.content->digest()!=a.digest||a.content->bytes().size()!=a.byte_count))return reject("run.attachments.content","Content digest or size mismatch");
        }
        const auto attachment_role=[&](const AttachmentId& id,AttachmentRole role){return std::any_of(input.attachments.begin(),input.attachments.end(),[&](const auto& a){return a.id==id&&a.role==role;});};
        if(const auto* failed=std::get_if<FailedFinal>(&input.final);failed&&failed->raw_diagnostics&&!attachment_role(*failed->raw_diagnostics,AttachmentRole::diagnostics))return reject("run.final.failure.diagnostics","Missing diagnostics-role attachment");
        const auto claim=[&](const ClaimEvidence& e){return e.problem==input.problem&&support_valid(e.support);};
        if(input.selection){
            const auto& batch=input.selection->batch;const auto& config=input.configuration.description();
            if(batch.selector.value!=config.selector.id.value||batch.requested!=config.output.witnesses.count||batch.seed!=config.output.witnesses.seed||batch.witnesses.size()>batch.requested)return reject("run.selection","Selection disagrees with the resolved request");
            for(const auto& w:batch.witnesses){
                if(w.problem!=input.problem||input.horizon==std::numeric_limits<std::uint64_t>::max()||w.states.size()!=input.horizon+1||w.controls.size()!=input.horizon||!std::isfinite(w.original_objective))return reject("run.selection.witnesses","Invalid selected witness shape or subject");
                for(const auto& state:w.states)if(state.size()!=input.dimensions.state||!finite_vector(state))return reject("run.selection.witnesses","Invalid selected state");
                for(const auto& control:w.controls)if(control.size()!=input.dimensions.control||!finite_vector(control))return reject("run.selection.witnesses","Invalid selected control");
            }
        }
        if(const auto* s=std::get_if<SynthesisFinal>(&input.final)){
            if(s->outcome.subject!=input.problem||!support_valid(s->outcome.support))return reject("run.final.outcome","Foreign or invalid synthesis claim");
            for(const auto* bound:{&s->objective.lower,&s->objective.upper})if(*bound&&(!std::isfinite((*bound)->value)||!claim((*bound)->evidence)))return reject("run.final.objective","Foreign or nonfinite objective evidence");
            for(const auto& w:s->incumbents){
                if(w.problem!=input.problem||input.horizon==std::numeric_limits<std::uint64_t>::max()||w.states.size()!=input.horizon+1||w.controls.size()!=input.horizon||!std::isfinite(w.original_objective))return reject("run.final.witnesses","Invalid witness subject or full-history shape");
                for(const auto& state:w.states)if(state.size()!=input.dimensions.state||!finite_vector(state))return reject("run.final.witnesses.states","Invalid state shape or value");
                for(const auto& control:w.controls)if(control.size()!=input.dimensions.control||!finite_vector(control))return reject("run.final.witnesses.controls","Invalid control shape or value");
            }
            if(s->family){const auto& f=*s->family;
                if(f.problem!=input.problem||f.coordinates.horizon!=input.horizon||f.coordinates.dimensions.state!=input.dimensions.state||f.coordinates.dimensions.control!=input.dimensions.control||f.coordinates.dimensions.external!=input.dimensions.external||!claim(f.evidence.feasibility)||!claim(f.evidence.optimality)||!claim(f.evidence.completeness))return reject("run.final.family","Foreign family subject, evidence or shape");
                if(const auto* p=std::get_if<ExternalFamilyPayload>(&f.payload);p&&!attachment_role(p->attachment,AttachmentRole::family))return reject("run.final.family.attachment","Missing family-role attachment");
            }
        } else if(const auto* p=std::get_if<ProgramFinal>(&input.final)){
            const auto& r=p->result;const auto& subject=r.outcome.subject;
            if(subject.problem!=input.problem||subject.program.value.empty()||!support_valid(r.outcome.support)||(r.primal&&!finite_vector(*r.primal)))return reject("run.final.program","Foreign or invalid program result");
            for(const auto* bound:{&r.objective.lower,&r.objective.upper})if(*bound&&(!std::isfinite((*bound)->value)||(*bound)->evidence.subject!=subject||!support_valid((*bound)->evidence.support)))return reject("run.final.program.objective","Foreign or invalid objective evidence");
            const auto context=[&](const ResidualContext& c){return c.subject==subject&&!c.verifier.id.value.empty()&&!c.verifier.version.empty()&&std::isfinite(c.absolute_tolerance)&&c.absolute_tolerance>=0&&std::isfinite(c.relative_tolerance)&&c.relative_tolerance>=0;};
            const auto measure=[](const ResidualMeasure& r){return std::isfinite(r.violation)&&r.violation>=0&&std::isfinite(r.scale)&&r.scale>=0;};
            if(r.residuals.primal&&(!context(r.residuals.primal->context)||!measure(r.residuals.primal->rows)||!measure(r.residuals.primal->variables)))return reject("run.final.program.residuals","Invalid primal residuals");
            if(r.residuals.dual){const auto& d=*r.residuals.dual;if(!context(d.context))return reject("run.final.program.residuals","Foreign dual residuals");for(const auto* m:{&d.stationarity,&d.signs,&d.complementarity})if(*m&&!measure(**m))return reject("run.final.program.residuals","Invalid dual residuals");}
            if(p->raw_diagnostics&&!attachment_role(*p->raw_diagnostics,AttachmentRole::diagnostics))return reject("run.final.program.diagnostics","Missing diagnostics-role attachment");
        }
        auto portable=check_record_portability(input);
        if(const auto* e=std::get_if<ArtifactError>(&portable))return *e;
        return ArtifactAccess::run(std::move(input),std::get<std::string>(std::move(portable)));
    }catch(const std::bad_alloc&){return ArtifactError{ArtifactErrorCode::allocation,{},{}};}
}
ArtifactResult<RunStatistics> publish_run(RunInput input) {
    try {
    const auto description=input.problem.description();
    if(input.record.problem!=input.problem.identity()||input.record.dimensions.state!=description->model->dynamics.dimensions.state||input.record.dimensions.control!=description->model->dynamics.dimensions.control||input.record.dimensions.external!=description->model->dynamics.dimensions.external||input.record.horizon!=description->times.size()-1)
        return ArtifactError{ArtifactErrorCode::identity,"run.problem","Record does not match actual immutable problem"};
    input.record.provenance=ProblemProvenance::problem_revalidated;return publish_record(std::move(input.record));
    }catch(const std::bad_alloc&){return ArtifactError{ArtifactErrorCode::allocation,{},{}};}
}
} // namespace csl::artifacts
namespace csl::artifacts {
ProgramFinal project_final(const ProgramResult& result,std::optional<AttachmentId> diagnostics){return {result,std::move(diagnostics)};}
SynthesisFinal project_final(const SynthesisResult& result,std::optional<AttachmentId> attachment){
    std::optional<FamilyRecord> family;
    if(result.family){const auto& f=*result.family;FamilyPayload payload=FamilyWithoutExporter{};
        if(attachment)payload=ExternalFamilyPayload{std::move(*attachment)};
        family=FamilyRecord{f.problem,f.relation.coordinates,f.relation.representation,f.target,f.evidence,std::move(payload)};
    }
    return {result.termination,result.outcome,result.objective,std::move(family),result.incumbents};
}
ArtifactResult<SpanRecord> project_legacy_span(const TimingSpan& value,SpanDescriptor descriptor){
    try {
    if(descriptor.module.id.value!=value.module.value||descriptor.module.version.empty()||descriptor.clock.value.empty()||descriptor.task.empty()||descriptor.operation.empty()||!std::isfinite(value.start_seconds)||!std::isfinite(value.end_seconds)||value.start_seconds<0||value.end_seconds<value.start_seconds)
        return ArtifactError{ArtifactErrorCode::invalid_input,"legacy","Missing/mismatched provenance or invalid legacy interval"};
    descriptor.id={value.id};descriptor.parent=value.parent?std::optional<SpanParent>{{{*value.parent},ParentKind::nested}}:std::optional<SpanParent>{};
    return SpanRecord{std::move(descriptor),LegacySecondsInterval{value.start_seconds,value.end_seconds},UnknownObservation{},Unavailable{MissingReason::not_instrumented,{}},Unavailable{MissingReason::not_instrumented,{}},Unavailable{MissingReason::not_instrumented,{}}};
    }catch(const std::bad_alloc&){return ArtifactError{ArtifactErrorCode::allocation,{},{}};}
}
}
