#include <csl/artifacts/run_statistics.hpp>
#include <csl/artifacts/h_relation_attachment.hpp>
#include <nlohmann/json.hpp>
#include <algorithm>
#include <array>
#include <bit>
#include <charconv>
#include <cmath>
#include <set>
#include <stdexcept>

namespace csl::artifacts {
std::string_view recorded_json(const RunStatistics&)noexcept;
namespace {
using Json=nlohmann::json;
struct Invalid { std::string path,message; };
void require(bool condition,std::string_view path,std::string_view message) {
    if(!condition) throw Invalid{std::string(path),std::string(message)};
}
bool name(std::string_view value) {
    return !value.empty() && std::all_of(value.begin(),value.end(),[](char c){
        return (c>='a'&&c<='z')||(c>='0'&&c<='9')||c=='_'||c=='.'||c=='-';
    });
}
bool digest(std::string_view value) {
    return value.size()==64 && std::all_of(value.begin(),value.end(),[](char c){return (c>='0'&&c<='9')||(c>='a'&&c<='f');});
}
std::string bits(double value) {
    require(std::isfinite(value),"configuration","Nonfinite configuration number");
    const auto n=std::bit_cast<std::uint64_t>(value);std::string result(16,'0');
    constexpr char hex[]="0123456789abcdef";
    for(std::size_t i=0;i<16;++i) result[15-i]=hex[(n>>(4*i))&15];
    return result;
}
std::string byte_hex(std::span<const std::byte> values) {
    constexpr char hex[]="0123456789abcdef";std::string out;
    for(auto value:values) {const auto v=std::to_integer<unsigned>(value);out+=hex[v>>4];out+=hex[v&15];}
    return out;
}
Json scalar(const OptionScalar& value) {
    return std::visit([](const auto& v)->Json {
        using T=std::decay_t<decltype(v)>;
        if constexpr(std::is_same_v<T,bool>) return {{"type","boolean"},{"value",v}};
        else if constexpr(std::is_same_v<T,std::int64_t>) return {{"type","signed64"},{"value",std::to_string(v)}};
        else if constexpr(std::is_same_v<T,std::uint64_t>) return {{"type","unsigned64"},{"value",std::to_string(v)}};
        else if constexpr(std::is_same_v<T,double>) return {{"type","binary64_bits"},{"value",bits(v)}};
        else if constexpr(std::is_same_v<T,std::string>) return {{"type","string"},{"value",v}};
        else if constexpr(std::is_same_v<T,std::vector<std::byte>>)return {{"type","bytes"},{"value",byte_hex(v)}};
        else {
            require(!v.schema.empty(),"configuration.options.schema","Versioned content schema is required");
            return {{"type","content"},{"value",{{"schema",v.schema},{"sha256",problem::hex(v.content.digest())},
                {"byte_count",std::to_string(v.content.bytes().size())},{"bytes",byte_hex(v.content.bytes())}}}};
        }
    },value);
}
Json options(const std::vector<NamedOption>& values) {
    std::vector<const NamedOption*> sorted;for(const auto& v:values) sorted.push_back(&v);
    std::sort(sorted.begin(),sorted.end(),[](auto a,auto b){return a->name<b->name;});
    Json out=Json::array();std::string previous;
    for(const auto* v:sorted) {
        require(name(v->name)&&v->name!=previous,"configuration.options","Invalid or duplicate option name");previous=v->name;
        Json encoded;
        if(const auto* s=std::get_if<OptionScalar>(&v->value)) encoded=scalar(*s);
        else {
            const auto& list=std::get<std::vector<OptionScalar>>(v->value);Json items=Json::array();
            for(const auto& item:list) {require(item.index()==list.front().index(),"configuration.options","Heterogeneous option list");items.push_back(scalar(item));}
            encoded={{"type","list"},{"value",std::move(items)}};
        }
        out.push_back({{"name",v->name},{"value",std::move(encoded)}});
    }
    return out;
}
Json pin(const PinAvailability& p,bool semantic) {
    if(const auto* a=std::get_if<Available<ModulePin>>(&p)) {
        require(digest(a->value.sha256),"configuration.pin.sha256","Expected lowercase SHA256");
        require(a->value.scope==PinScope::source_archive||a->value.scope==PinScope::build_manifest,"configuration.pin.scope","Unknown pin scope");
        return {{"state","available"},{"value",{{"scope",a->value.scope==PinScope::source_archive?"source_archive":"build_manifest"},{"sha256",a->value.sha256}}}};
    }
    const auto& u=std::get<Unavailable>(p);const char* reason=nullptr;
    switch(u.reason) {
    case MissingReason::not_instrumented:reason="not_instrumented";break;
    case MissingReason::not_exposed_by_adapter:reason="not_exposed_by_adapter";break;
    case MissingReason::not_applicable:reason="not_applicable";break;
    default:throw Invalid{"configuration.pin.reason","Unavailable reason is invalid for a pin"};
    }
    require(u.detail.size()<=256,"configuration.pin.detail","Pin detail exceeds 256 UTF-8 bytes");
    // Validate retained prose even when the identity projection erases it.
    (void)Json(u.detail).dump();
    return {{"state","unavailable"},{"value",nullptr},{"reason",reason},{"detail",semantic?std::string{}:u.detail}};
}
void canonical_string(std::string& out,const std::string& value) {
    (void)Json(value).dump(); // Strict UTF-8 boundary, independent of canonical escaping.
    constexpr char hex[]="0123456789abcdef";out+='"';
    for(unsigned char c:value) {
        if(c=='"'||c=='\\') {out+='\\';out+=static_cast<char>(c);}
        else if(c<32) {out+="\\u00";out+=hex[c>>4];out+=hex[c&15];}
        else out+=static_cast<char>(c);
    }
    out+='"';
}
void canonical(std::string& out,const Json& value) {
    if(value.is_object()) {
        out+='{';bool first=true;
        for(auto it=value.begin();it!=value.end();++it) {if(!first)out+=',';first=false;canonical_string(out,it.key());out+=':';canonical(out,it.value());}out+='}';
    } else if(value.is_array()) {
        out+='[';bool first=true;for(const auto& item:value){if(!first)out+=',';first=false;canonical(out,item);}out+=']';
    } else if(value.is_string()) canonical_string(out,value.get_ref<const std::string&>());
    else out+=value.dump();
}
Json configuration_record(const ConfigurationInput& c,bool semantic) {
    const auto& col=c.collection;
    require(col.mode==CollectionMode::detail||col.mode==CollectionMode::summary,"configuration.collection.mode","Unknown collection mode");
    require(col.detail_spans<=col.plan_spans,"configuration.collection.detail_spans","Detail span capacity exceeds plan");
    require(c.workspace==WorkspacePolicy::fresh||c.workspace==WorkspacePolicy::reused,"configuration.workspace","Unknown workspace policy");
    require(c.resources.total_threads>0&&c.resources.outer_workers>0&&c.resources.threads_per_worker>0,
        "configuration.resources","Thread declarations must be positive");
    require(std::isfinite(c.numerical.absolute_tolerance)&&c.numerical.absolute_tolerance>=0&&
        std::isfinite(c.numerical.relative_tolerance)&&c.numerical.relative_tolerance>=0,"configuration.numerical","Invalid tolerance");
    require(std::isfinite(c.output.witnesses.distinctness_tolerance)&&c.output.witnesses.distinctness_tolerance>=0,"configuration.output","Invalid distinctness tolerance");
    require(c.output.kind==OutputKind::synthesis||c.output.kind==OutputKind::program,"configuration.output","Unknown output kind");
    require(c.output.assurance==Assurance::numerical||c.output.assurance==Assurance::validated,"configuration.output","Unknown assurance");
    const char* family=nullptr;
    switch(c.output.family) {
    case FamilyTarget::exact_optimal_relation:family="exact_optimal_relation";break;
    case FamilyTarget::candidate_relaxation:family="candidate_relaxation";break;
    case FamilyTarget::partial_relation:family="partial_relation";break;
    default:throw Invalid{"configuration.output.family","Unknown family target"};
    }
    const auto& s=c.strategy;
    require(!s.strategy.value.empty()&&!s.representation.value.empty()&&!s.selector.value.empty(),"configuration.strategy","Unresolved strategy configuration");
    require(s.selector.value==c.selector.id.value&&s.representation.value==c.output.representation.value,"configuration","Inconsistent selector or representation");
    require(!c.selector.version.empty(),"configuration.selector.version","Unresolved selector version");
    const std::array<std::pair<const char*,const ModuleId*>,7> roles{{{"strategy",&s.strategy},{"lp",&s.lp},{"convex",&s.convex},{"hull",&s.hull},{"geometry",&s.geometry},{"converter",&s.converter},{"approximation",&s.approximation}}};
    std::vector<const ModuleConfiguration*> sorted;for(const auto& m:c.modules) sorted.push_back(&m);
    std::sort(sorted.begin(),sorted.end(),[](auto a,auto b){return a->role<b->role;});
    Json modules=Json::array();std::string previous;
    for(const auto* m:sorted) {
        require(name(m->role)&&m->role!=previous,"configuration.modules.role","Invalid or duplicate role");previous=m->role;
        const auto selected=std::find_if(roles.begin(),roles.end(),[&](const auto& r){return r.first==m->role;});
        require(!m->implementation.id.value.empty(),"configuration.modules","Unresolved module identity");
        if(selected!=roles.end())require(!selected->second->value.empty()&&selected->second->value==m->implementation.id.value,"configuration.modules","Inconsistent selected module");
        if(m->role=="selector")require(m->implementation.id.value==c.selector.id.value&&m->implementation.version==c.selector.version,"configuration.modules","Inconsistent selector implementation");
        require(!m->implementation.version.empty(),"configuration.modules.version","Unresolved module version");
        modules.push_back({{"role",m->role},{"id",m->implementation.id.value},{"version",m->implementation.version},
            {"pin",pin(m->implementation.pin,semantic)},{"options",options(m->options)}});
    }
    for(const auto& [role,id]:roles) if(!id->value.empty()) require(std::any_of(c.modules.begin(),c.modules.end(),[&](const auto& m){return m.role==role;}),"configuration.modules","Missing selected module");
    Json strategy={{"selector",s.selector.value},{"representation",s.representation.value}};
    for(const auto& [role,id]:roles) strategy[role]=id->value.empty()?Json(nullptr):Json(id->value);
    Json directions=Json::array();for(const auto& d:c.output.witnesses.directions) {Json row=Json::array();for(double v:d)row.push_back(bits(v));directions.push_back(std::move(row));}
    Json stop={{"deadline_budget_ticks",nullptr}};
    if(c.deadline_budget) {
        require(c.deadline_budget->period_numerator>0&&c.deadline_budget->period_denominator>0,"configuration.stop","Invalid deadline tick period");
        stop={{"deadline_budget_ticks",std::to_string(c.deadline_budget->ticks)},
            {"period_numerator",std::to_string(c.deadline_budget->period_numerator)},{"period_denominator",std::to_string(c.deadline_budget->period_denominator)}};
    }
    return {
        {"collection",{{"enabled",col.enabled},{"mode",col.mode==CollectionMode::detail?"detail":"summary"},
            {"plan_spans",std::to_string(col.plan_spans)},{"plan_bytes",std::to_string(col.plan_bytes)},
            {"detail_spans",std::to_string(col.detail_spans)},{"detail_bytes",std::to_string(col.detail_bytes)}}},
        {"modules",std::move(modules)},
        {"numerical",{{"absolute_bits",bits(c.numerical.absolute_tolerance)},{"relative_bits",bits(c.numerical.relative_tolerance)}}},
        {"output",{{"kind",c.output.kind==OutputKind::synthesis?"synthesis":"program"},{"assurance",c.output.assurance==Assurance::numerical?"numerical":"validated"},
            {"family",family},{"representation",c.output.representation.value},{"witness_count",std::to_string(c.output.witnesses.count)},
            {"distinctness_bits",bits(c.output.witnesses.distinctness_tolerance)},{"directions",std::move(directions)},
            {"seed",c.output.witnesses.seed?Json(std::to_string(*c.output.witnesses.seed)):Json(nullptr)}}},
        {"resources",{{"total_threads",std::to_string(c.resources.total_threads)},{"outer_workers",std::to_string(c.resources.outer_workers)},
            {"threads_per_worker",std::to_string(c.resources.threads_per_worker)},{"memory_bytes",c.resources.memory_bytes?Json(std::to_string(*c.resources.memory_bytes)):Json(nullptr)}}},
        {"selector",{{"id",c.selector.id.value},{"version",c.selector.version},{"options",options(c.selector.options)}}},
        {"stop",std::move(stop)},{"strategy",std::move(strategy)},{"workspace_policy",c.workspace==WorkspacePolicy::fresh?"fresh":"reused"}
    };
}
} // namespace
ArtifactResult<std::string> configuration_json(const ConfigurationInput& input,bool semantic) {
    try {std::string out;canonical(out,configuration_record(input,semantic));return out;}
    catch(const Invalid& e){return ArtifactError{ArtifactErrorCode::invalid_input,e.path,e.message};}
    catch(const Json::exception&){return ArtifactError{ArtifactErrorCode::invalid_input,"configuration","Invalid JSON-compatible UTF-8 data"};}
}
} // namespace csl::artifacts

namespace csl::artifacts {
namespace {
template<class T>struct Codec;
template<class T>Json put(const T& value){return Codec<T>::put(value);}
template<class T>T get(const Json& value){return Codec<T>::get(value);}
void closed(const Json& value,std::initializer_list<std::string_view> keys) {
    require(value.is_object()&&value.size()==keys.size(),"json.object","Missing or unknown object fields");
    for(auto key:keys)require(value.contains(std::string(key)),"json.object","Missing required object field");
}
template<class T>struct Field {std::string_view name;T& value;};
template<class T>Field<T> field(std::string_view key,T& value){return {key,value};}
template<class... F>Json object(F... f){Json j=Json::object();((j[std::string(f.name)]=put(f.value)),...);return j;}
template<class... F>void fields(const Json& j,F... f){closed(j,{f.name...});([&]{try{f.value=get<std::remove_cvref_t<decltype(f.value)>>(j.at(std::string(f.name)));}catch(Invalid& error){error.path=std::string(f.name)+"."+error.path;throw;}}(),...);}
template<>struct Codec<std::string>{static Json put(const std::string& v){return v;}static std::string get(const Json& j){require(j.is_string(),"json.string","Expected string");return j.get<std::string>();}};
template<>struct Codec<bool>{static Json put(bool v){return v;}static bool get(const Json& j){require(j.is_boolean(),"json.boolean","Expected boolean");return j.get<bool>();}};
template<class T>T integer(const Json& j) {
    const auto text=get<std::string>(j);T value{};
    require(!text.empty()&&(text=="0"||text.front()!='0')&&text!="-0"&&text.front()!='+',"json.integer","Noncanonical integer");
    if(text.front()=='-')require(std::is_signed_v<T>&&text.size()>1&&text[1]!='0',"json.integer","Invalid signed integer");
    const auto result=std::from_chars(text.data(),text.data()+text.size(),value);
    require(result.ec==std::errc{}&&result.ptr==text.data()+text.size(),"json.integer","Integer range or grammar error");return value;
}
template<>struct Codec<std::uint64_t>{static Json put(std::uint64_t v){return std::to_string(v);}static auto get(const Json& j){return integer<std::uint64_t>(j);}};
template<>struct Codec<std::int64_t>{static Json put(std::int64_t v){return std::to_string(v);}static auto get(const Json& j){return integer<std::int64_t>(j);}};
template<>struct Codec<double>{static Json put(double v){require(std::isfinite(v),"json.number","Nonfinite number");return v;}static double get(const Json& j){require(j.is_number(),"json.number","Expected finite number");const auto v=j.get<double>();require(std::isfinite(v),"json.number","Nonfinite number");return v;}};
template<class T>struct Codec<std::optional<T>>{static Json put(const std::optional<T>& v){return v?artifacts::put(*v):Json(nullptr);}static std::optional<T>get(const Json& j){return j.is_null()?std::optional<T>{}:artifacts::get<T>(j);}};
template<class T>struct Codec<std::shared_ptr<const T>>{static Json put(const std::shared_ptr<const T>& v){return v?artifacts::put(*v):Json(nullptr);}static std::shared_ptr<const T>get(const Json& j){return j.is_null()?std::shared_ptr<const T>{}:std::make_shared<const T>(artifacts::get<T>(j));}};
template<class T>struct Codec<std::vector<T>>{static Json put(const std::vector<T>& v){Json j=Json::array();for(const auto& item:v)j.push_back(artifacts::put(item));return j;}static std::vector<T>get(const Json& j){require(j.is_array(),"json.array","Expected array");std::vector<T> out;out.reserve(j.size());for(const auto& item:j)out.push_back(artifacts::get<T>(item));return out;}};
template<class T>struct Tag;
template<class... T>struct Codec<std::variant<T...>>{
    static Json put(const std::variant<T...>& v){return std::visit([](const auto& x)->Json{return {{"kind",Tag<std::decay_t<decltype(x)>>::value},{"value",artifacts::put(x)}};},v);}
    static std::variant<T...>get(const Json& j){closed(j,{"kind","value"});const auto kind=artifacts::get<std::string>(j.at("kind"));std::optional<std::variant<T...>> result;
        ([&]{if(kind==Tag<T>::value)result=artifacts::get<T>(j.at("value"));}(),...);require(result.has_value(),"json.kind","Unknown variant kind");return std::move(*result);}
};
template<class E>Json enum_put(E value,std::initializer_list<std::pair<const char*,E>> values){for(const auto& [name,item]:values)if(item==value)return name;throw Invalid{"json.enum","Unknown enum value"};}
template<class E>E enum_get(const Json& j,std::initializer_list<std::pair<const char*,E>> values){const auto name=get<std::string>(j);for(const auto& [key,item]:values)if(key==name)return item;throw Invalid{"json.enum","Unknown enum name"};}
#define EN(Type,...) template<>struct Codec<Type>{static Json put(Type value){return enum_put<Type>(value,{__VA_ARGS__});}static Type get(const Json& j){return enum_get<Type>(j,{__VA_ARGS__});}};
#define EV(Type,Name) {#Name,Type::Name}
#define F(Name) field(#Name,v.Name)
#define ST(Type,...) template<>struct Codec<Type>{static Json put(const Type& v){return object(__VA_ARGS__);}static Type get(const Json& j){Type v{};fields(j,__VA_ARGS__);return v;}};
#define EMPTY(Type) template<>struct Codec<Type>{static Json put(const Type&){return Json::object();}static Type get(const Json& j){closed(j,{});return {};}};
#define TAG(Type,Name) template<>struct Tag<Type>{static constexpr const char* value=Name;};
EN(MissingReason,EV(MissingReason,not_requested),EV(MissingReason,not_instrumented),EV(MissingReason,not_supported),EV(MissingReason,not_exposed_by_adapter),EV(MissingReason,execution_unknown),EV(MissingReason,incomplete_span),EV(MissingReason,clock_unavailable),EV(MissingReason,clock_mismatch),EV(MissingReason,overflow),EV(MissingReason,detail_limit),EV(MissingReason,collection_disabled),EV(MissingReason,not_applicable))
ST(Unavailable,F(reason),F(detail))
template<class T>struct Codec<Metric<T>> {
    static Json put(const Metric<T>& v){if(const auto* a=std::get_if<Available<T>>(&v))return {{"state","available"},{"value",artifacts::put(a->value)}};const auto& u=std::get<Unavailable>(v);return {{"state","unavailable"},{"value",nullptr},{"reason",artifacts::put(u.reason)},{"detail",u.detail}};}
    static Metric<T>get(const Json& j){require(j.is_object()&&j.contains("state"),"json.metric","Missing metric state");const auto state=artifacts::get<std::string>(j.at("state"));if(state=="available"){closed(j,{"state","value"});return Available<T>{artifacts::get<T>(j.at("value"))};}require(state=="unavailable","json.metric","Unknown availability state");closed(j,{"state","value","reason","detail"});require(j.at("value").is_null(),"json.metric","Unavailable value must be null");return Unavailable{artifacts::get<MissingReason>(j.at("reason")),artifacts::get<std::string>(j.at("detail"))};}
};
EN(PinScope,EV(PinScope,source_archive),EV(PinScope,build_manifest))
ST(ModulePin,F(scope),F(sha256))
#define ID(Type) template<>struct Codec<Type>{static Json put(const Type& v){return v.value;}static Type get(const Json& j){return {artifacts::get<std::string>(j)};}};
ID(ProblemId) ID(ProgramId) ID(ModuleId) ID(RepresentationId) ID(ConfigId) ID(RunId) ID(ClockId) ID(AttachmentId) ID(RequestId) ID(ReferenceId) ID(SetId)
#undef ID
ST(ProgramIdentity,F(problem),F(program))
ST(ModuleIdentity,F(id),F(version),F(pin))
ST(SpanId,F(value))
EN(CollectionMode,EV(CollectionMode,detail),EV(CollectionMode,summary))
ST(CollectionSettings,F(enabled),F(mode),F(plan_spans),F(plan_bytes),F(detail_spans),F(detail_bytes))
EN(Assurance,EV(Assurance,numerical),EV(Assurance,validated))
EN(SetRelation,EV(SetRelation,equivalent),EV(SetRelation,inner),EV(SetRelation,outer),EV(SetRelation,heuristic))
EN(Termination,EV(Termination,completed),EV(Termination,cancelled),EV(Termination,resource_limit),EV(Termination,numerical_failure),EV(Termination,operation_rejected),EV(Termination,contract_rejected))
EN(StopReason,EV(StopReason,cancelled),EV(StopReason,deadline_expired),EV(StopReason,resource_limit),EV(StopReason,numerical_failure))
EN(MathematicalOutcome,EV(MathematicalOutcome,optimal),EV(MathematicalOutcome,infeasible),EV(MathematicalOutcome,unbounded),EV(MathematicalOutcome,infimum_not_attained),EV(MathematicalOutcome,undetermined))
EN(FamilyTarget,EV(FamilyTarget,exact_optimal_relation),EV(FamilyTarget,candidate_relaxation),EV(FamilyTarget,partial_relation))
EN(ClockMetric,EV(ClockMetric,steady_wall),EV(ClockMetric,thread_cpu),EV(ClockMetric,process_cpu))
EN(ParentKind,EV(ParentKind,nested),EV(ParentKind,spawned))
EN(DetailState,EV(DetailState,not_observed),EV(DetailState,retained),EV(DetailState,capacity_dropped),EV(DetailState,rejected),EV(DetailState,not_requested))
EN(NotCalledReason,EV(NotCalledReason,capability_rejected),EV(NotCalledReason,task_not_admitted),EV(NotCalledReason,before_public_entry),EV(NotCalledReason,explicit_pre_entry_stop),EV(NotCalledReason,constant_rows_wrapper),EV(NotCalledReason,stopped_before_phase_call),EV(NotCalledReason,earlier_phase_exit),EV(NotCalledReason,invalid_qp_start),EV(NotCalledReason,route_not_selected))
EN(AttachmentRole,EV(AttachmentRole,diagnostics),EV(AttachmentRole,family),EV(AttachmentRole,certificate),EV(AttachmentRole,profiler))
EN(SkippedReason,EV(SkippedReason,cancelled),EV(SkippedReason,deadline),EV(SkippedReason,task_limit),EV(SkippedReason,reservation_exceeds_budget),EV(SkippedReason,batch_failed))
EN(FailurePhase,EV(FailurePhase,create),EV(FailurePhase,invoke),EV(FailurePhase,launch),EV(FailurePhase,publication))
EN(FailureReason,EV(FailureReason,allocation),EV(FailureReason,adapter_exception),EV(FailureReason,thread_launch))
EN(AdmissionCause,EV(AdmissionCause,cancelled),EV(AdmissionCause,deadline),EV(AdmissionCause,task_limit),EV(AdmissionCause,allocation),EV(AdmissionCause,adapter_exception),EV(AdmissionCause,thread_launch))
EN(MemoryAccounting,EV(MemoryAccounting,unlimited),EV(MemoryAccounting,active_reservations))
EN(ProblemProvenance,EV(ProblemProvenance,problem_revalidated),EV(ProblemProvenance,identity_recorded))
EN(DiagnosticCode,EV(DiagnosticCode,invalid_input),EV(DiagnosticCode,unsupported),EV(DiagnosticCode,evidence_mismatch),EV(DiagnosticCode,invalid_claim))
ST(Diagnostic,F(code),F(field),F(explanation))
ST(ClockDomain,F(id),F(metric),F(scope),F(period_numerator),F(period_denominator),F(resolution_ticks),F(origin_label),F(calibration))
ST(TickInterval,F(start),F(end)) ST(LegacySecondsInterval,F(start),F(end))
TAG(TickInterval,"ticks") TAG(LegacySecondsInterval,"legacy_seconds")
ST(SpanParent,F(id),F(kind))
EMPTY(ReturnedObservation) EMPTY(UnknownObservation) ST(NotCalledObservation,F(reason),F(source_location),F(source_version))
TAG(ReturnedObservation,"observed_return") TAG(NotCalledObservation,"known_not_called") TAG(UnknownObservation,"unknown")
ST(RepresentationSize,F(quantity),F(unit),F(value))
ST(RepresentationSummary,F(representation),F(dimension),F(sizes))
ST(SpanDescriptor,F(id),F(parent),F(shard),F(bucket),F(task),F(operation),F(module),F(backend),F(clock),F(program),F(stage),F(query),F(input_representation),F(output_representation),F(input_size),F(output_size),F(requested_assurance),F(applied_assurance),F(relation),F(relation_evidence),F(input_summary),F(output_summary),F(observation_source))
EMPTY(IncompleteSpan) ST(ReturnedSpan,F(termination),F(outcome)) ST(RejectedSpan,F(reason)) ST(SkippedSpan,F(reason)) ST(FailedSpan,F(phase),F(reason))
TAG(IncompleteSpan,"incomplete") TAG(ReturnedSpan,"returned") TAG(RejectedSpan,"capability_rejected") TAG(SkippedSpan,"skipped") TAG(FailedSpan,"failed")
ST(SpanRecord,F(descriptor),F(interval),F(execution),F(termination),F(iterations),F(detail),F(status),F(completion_observed),F(detail_state))
ST(ExactCount,F(value),F(exact))
ST(BucketSummary,F(id),F(clock),F(observed),F(detail_dropped),F(duplicate),F(wrong_shard),F(declared_overflow),F(duration_contributors),F(inclusive_ticks),F(failed),F(not_called),F(unknown),F(incomplete))
ST(CollectionRecord,F(problem),F(configuration),F(run),F(settings),F(clocks),F(spans),F(buckets),F(complete),F(tasks),F(operations))
EMPTY(Unestablished) ST(NumericalCheck,F(absolute_tolerance),F(relative_tolerance),F(max_residual),F(verifier))
ST(SymbolicArgument,F(reference),F(assumptions)) ST(CertificateReference,F(artifact),F(verifier))
TAG(Unestablished,"unestablished") TAG(NumericalCheck,"numerical_check") TAG(SymbolicArgument,"symbolic_argument") TAG(CertificateReference,"certificate_reference")
ST(LinearInfeasibilityCertificate,F(subject),F(row_lower),F(row_upper),F(variable_lower),F(variable_upper))
TAG(ExactFarkasEvidence,"exact_farkas")
template<>struct Codec<ExactFarkasEvidence>{
    static Json put(const ExactFarkasEvidence& value){return {{"subject",artifacts::put(value.subject())},
        {"certificate",artifacts::put(value.certificate())}};}
    static ExactFarkasEvidence get(const Json&){throw Invalid{"support.exact_farkas",
        "Exact Farkas evidence must be reverified against its immutable LP before reconstruction"};}
};
template<>struct Codec<EvidenceSupport>{
    static Json put(const EvidenceSupport& value){return std::visit([](const auto& item)->Json{
        using T=std::decay_t<decltype(item)>;
        return {{"kind",Tag<T>::value},{"value",artifacts::put(item)}};
    },value);}
    static EvidenceSupport get(const Json& j){
        closed(j,{"kind","value"});
        const auto kind=artifacts::get<std::string>(j.at("kind"));
        if(kind==Tag<ExactFarkasEvidence>::value)
            return CertificateReference{"unverified-exact-farkas:"+j.at("value").dump(),
                "csl.optimization.farkas-exact.unverified/1"};
        if(kind==Tag<Unestablished>::value)return artifacts::get<Unestablished>(j.at("value"));
        if(kind==Tag<NumericalCheck>::value)return artifacts::get<NumericalCheck>(j.at("value"));
        if(kind==Tag<SymbolicArgument>::value)return artifacts::get<SymbolicArgument>(j.at("value"));
        if(kind==Tag<CertificateReference>::value)return artifacts::get<CertificateReference>(j.at("value"));
        throw Invalid{"support.kind","Unknown evidence support kind"};
    }
};
EN(GeometryClaimScope,EV(GeometryClaimScope,set_relation),EV(GeometryClaimScope,support_value),EV(GeometryClaimScope,containment))
ST(GeometryRequestIdentity,F(problem),F(request),F(ideal_output)) ST(GeometryReference,F(identity),F(inputs))
ST(GeometryErrorBound,F(metric),F(bound),F(units))
ST(GeometryEvidence,F(reference),F(scope),F(support),F(assumptions),F(error_bound))
ST(ClaimEvidence,F(problem),F(support)) ST(FamilyEvidence,F(feasibility),F(optimality),F(completeness))
ST(NumericalPolicy,F(absolute_tolerance),F(relative_tolerance))
ST(FamilyRequest,F(profile),F(objective),F(target),F(numerical),F(assurance),F(representation),F(materialization_limit))
ST(TransformStepIdentity,F(request),F(input),F(output),F(module),F(version))
ST(FamilyIdentity,F(problem),F(request),F(coordinates),F(strategy),F(strategy_version),F(lineage))
ST(OptimumEvidence,F(optimum),F(bounds))
ST(NumericalCoverageEvidence,F(procedure),F(policy),F(verifier),F(diagnostics))
ST(ValidatedCoverageEvidence,F(certificate),F(verifier),F(arithmetic_profile))
TAG(NumericalCoverageEvidence,"numerical") TAG(ValidatedCoverageEvidence,"validated")
ST(RegisteredCompletenessEvidence,F(verifier),F(verifier_version),F(proof))
TAG(RegisteredCompletenessEvidence,"registered_verifier")
ST(CompletenessEvidence,F(binding),F(support))
ST(JointRelation,F(coordinates),F(representation))
ST(CompleteOptimalFamily,F(relation),F(optimum),F(completeness),F(assurance))
ST(InnerSubsetEvidence,F(every_history_optimal),F(procedure)) ST(CoverageScope,F(description))
ST(PartialOptimalFamily,F(relation),F(optimum),F(optimal_subset),F(known_scope))
ST(OuterCandidateEvidence,F(enclosure)) ST(FeasibleCandidateEvidence,F(feasibility)) ST(HeuristicRelationEvidence,F(method))
TAG(OuterCandidateEvidence,"outer") TAG(FeasibleCandidateEvidence,"feasible") TAG(HeuristicRelationEvidence,"heuristic")
ST(RelationFeasibilityEvidence,F(support)) ST(WitnessFeasibilityEvidence,F(witness),F(support))
TAG(RelationFeasibilityEvidence,"relation") TAG(WitnessFeasibilityEvidence,"witness")
ST(CandidateFamily,F(relation),F(relation_to_target),F(feasibility))
TAG(CompleteOptimalFamily,"complete") TAG(PartialOptimalFamily,"partial") TAG(CandidateFamily,"candidate")
template<>struct Codec<OptimalFamily>{
    static Json put(const OptimalFamily& v){return object(field("identity",v.identity()),field("outcome",v.outcome()));}
    static OptimalFamily get(const Json& j){
        closed(j,{"identity","outcome"});
        auto published=FamilyPublisher::publish(artifacts::get<FamilyIdentity>(j.at("identity")),artifacts::get<OptimalFamilyOutcome>(j.at("outcome")));
        require(std::holds_alternative<OptimalFamily>(published),"family.publisher","Decoded family fails the publication boundary");
        return std::get<OptimalFamily>(std::move(published));
    }
};
ST(OperationStopped,F(reason),F(diagnostics))
ST(RequestProvenance,F(request),F(port),F(requested_module),F(requested_version),F(actual_module),F(actual_version))
ST(RetainedEvidenceScope,F(lower_bound),F(upper_bound),F(incumbents),F(partial_or_candidate_family))
ST(ScopedOperationStopped,F(stop),F(request),F(retained))
ST(ScopedRequestRejection,F(request),F(diagnostics),F(completed_lineage),F(retained))
EMPTY(std::monostate) TAG(std::monostate,"none") TAG(ScopedOperationStopped,"operation_stopped") TAG(ScopedRequestRejection,"request_rejected")
ST(ContractValidationFailure,F(diagnostics),F(retained),F(source_stop))
TAG(ContractValidationFailure,"contract_validation_failure")
template<class Subject>struct Codec<OutcomeClaim<Subject>>{static Json put(const OutcomeClaim<Subject>& v){return object(F(subject),F(value),F(support),F(assumptions));}static OutcomeClaim<Subject>get(const Json& j){OutcomeClaim<Subject>v{};fields(j,F(subject),F(value),F(support),F(assumptions));return v;}};
ST(ObjectiveBound,F(value),F(evidence)) ST(ObjectiveEvidence,F(lower),F(upper))
ST(ProgramBoundEvidence,F(subject),F(support),F(assumptions)) ST(ProgramObjectiveBound,F(value),F(evidence)) ST(ProgramObjectiveEvidence,F(lower),F(upper))
ST(Verifier,F(id),F(version)) ST(ResidualMeasure,F(violation),F(scale)) ST(ResidualContext,F(subject),F(verifier),F(absolute_tolerance),F(relative_tolerance))
ST(PrimalResiduals,F(context),F(rows),F(variables)) ST(DualResiduals,F(context),F(stationarity),F(signs),F(complementarity)) ST(ProgramResiduals,F(primal),F(dual))
ST(ProgramResult,F(termination),F(outcome),F(primal),F(objective),F(raw_diagnostics),F(residuals))
ST(Dimensions,F(state),F(control),F(external)) ST(JointCoordinates,F(dimensions),F(horizon)) ST(Witness,F(problem),F(states),F(controls),F(original_objective))
ST(FeasibleIncumbent,F(witness),F(feasibility))
ST(WitnessBatch,F(witnesses),F(requested),F(selector),F(seed),F(source_family),F(directions),F(distinctness_tolerance)) ST(WitnessSelection,F(batch),F(termination),F(diagnostics))
ST(ExternalFamilyPayload,F(attachment)) EMPTY(FamilyWithoutExporter)
TAG(ExternalFamilyPayload,"external_reference") TAG(FamilyWithoutExporter,"unavailable_no_exporter")
template<>struct Codec<FamilyRecord>{
    static Json put(const FamilyRecord& v){return object(field("family",v.family),field("payload",v.payload));}
    static FamilyRecord get(const Json& j){closed(j,{"family","payload"});return {artifacts::get<OptimalFamily>(j.at("family")),artifacts::get<FamilyPayload>(j.at("payload"))};}
};
ST(SynthesisFinal,F(termination),F(outcome),F(objective),F(family),F(incumbents),F(stop)) ST(ProgramFinal,F(result),F(raw_diagnostics)) ST(UnsupportedFinal,F(diagnostics)) ST(SkippedFinal,F(reason)) ST(FailedFinal,F(phase),F(reason),F(message),F(raw_diagnostics))
TAG(SynthesisFinal,"synthesis") TAG(ProgramFinal,"program") TAG(UnsupportedFinal,"unsupported") TAG(SkippedFinal,"skipped") TAG(FailedFinal,"failed")
ST(AdmissionObservation,F(cause),F(at))
ST(ExecutionSummary::Task,F(id),F(queued),F(admitted),F(create_started),F(create_finished),F(call_started),F(call_finished),F(released),F(status))
ST(ExecutionSummary,F(configured_deadline),F(admission_closed),F(external_cancellation),F(workers_joined),F(completed),F(clock),F(started),F(tasks))
ST(ResourceObservation,F(peak_active_tasks),F(peak_reserved_threads),F(peak_reserved_bytes),F(actual_threads),F(outer_admission_enforced),F(memory))
#undef TAG
#undef EMPTY
#undef ST
#undef F
#undef EV
#undef EN
std::vector<std::byte> parse_hex(const Json& j) {
    const auto text=get<std::string>(j);require(text.size()%2==0,"json.hex","Odd byte string");std::vector<std::byte> out;out.reserve(text.size()/2);
    const auto digit=[](char c)->unsigned{if(c>='0'&&c<='9')return static_cast<unsigned>(c-'0');if(c>='a'&&c<='f')return static_cast<unsigned>(c-'a'+10);throw Invalid{"json.hex","Noncanonical hexadecimal byte string"};};
    for(std::size_t i=0;i<text.size();i+=2)out.push_back(static_cast<std::byte>(digit(text[i])*16+digit(text[i+1])));
    return out;
}
template<>struct Codec<problem::ContentDigest>{static Json put(problem::ContentDigest v){return problem::hex(v);}static problem::ContentDigest get(const Json& j){auto bytes=parse_hex(j);require(bytes.size()==32,"attachment.digest","Expected SHA256");problem::ContentDigest out{};std::copy(bytes.begin(),bytes.end(),out.bytes.begin());return out;}};
template<>struct Codec<problem::ResolvedContent>{static Json put(const problem::ResolvedContent& v){return byte_hex(v.bytes());}static problem::ResolvedContent get(const Json& j){const auto bytes=parse_hex(j);auto owner=problem::snapshot_content(bytes);require(std::holds_alternative<problem::ResolvedContent>(owner),"attachment.content","Cannot own content");return std::get<problem::ResolvedContent>(owner);}};
template<>struct Codec<Attachment>{static Json put(const Attachment& v){return object(field("id",v.id),field("role",v.role),field("digest",v.digest),field("byte_count",v.byte_count),field("media_type",v.media_type),field("schema",v.schema),field("relative_path",v.relative_path),field("content",v.content));}
static Attachment get(const Json& j){Attachment v{};fields(j,field("id",v.id),field("role",v.role),field("digest",v.digest),field("byte_count",v.byte_count),field("media_type",v.media_type),field("schema",v.schema),field("relative_path",v.relative_path),field("content",v.content));return v;}};
double parse_bits(const Json& j) {const auto bytes=parse_hex(j);require(bytes.size()==8,"configuration.bits","Expected 16 binary64 hexadecimal digits");std::uint64_t bits_value=0;for(auto b:bytes)bits_value=(bits_value<<8)|std::to_integer<unsigned>(b);const auto v=std::bit_cast<double>(bits_value);require(std::isfinite(v),"configuration.bits","Nonfinite configuration number");return v;}
OptionScalar parse_scalar(const Json& j) {
    closed(j,{"type","value"});const auto type=get<std::string>(j.at("type"));const auto& v=j.at("value");
    if(type=="boolean")return get<bool>(v);
    if(type=="signed64")return get<std::int64_t>(v);
    if(type=="unsigned64")return get<std::uint64_t>(v);
    if(type=="binary64_bits")return parse_bits(v);
    if(type=="string")return get<std::string>(v);
    if(type=="bytes")return parse_hex(v);
    if(type=="content"){
        closed(v,{"schema","sha256","byte_count","bytes"});auto owned=get<problem::ResolvedContent>(v.at("bytes"));
        require(owned.digest()==get<problem::ContentDigest>(v.at("sha256"))&&owned.bytes().size()==get<std::uint64_t>(v.at("byte_count")),"configuration.options.content","Content digest or byte count mismatch");
        return ContentOption{get<std::string>(v.at("schema")),std::move(owned)};
    }
    throw Invalid{"configuration.options","Unknown option type"};
}
std::vector<NamedOption> parse_options(const Json& j) {
    require(j.is_array(),"configuration.options","Expected options array");std::vector<NamedOption> out;
    for(const auto& item:j){closed(item,{"name","value"});const auto key=get<std::string>(item.at("name"));const auto& value=item.at("value");closed(value,{"type","value"});
        if(value.at("type")=="list"){require(value.at("value").is_array(),"configuration.options","Expected list");std::vector<OptionScalar> items;for(const auto& element:value.at("value"))items.push_back(parse_scalar(element));out.push_back({key,std::move(items)});}
        else out.push_back({key,parse_scalar(value)});
    }return out;
}
ConfigurationInput parse_configuration(const Json& j) {
    closed(j,{"collection","modules","numerical","output","resources","selector","stop","strategy","workspace_policy"});ConfigurationInput c{};
    c.collection=get<CollectionSettings>(j.at("collection"));const auto& modules=j.at("modules");require(modules.is_array(),"configuration.modules","Expected module array");
    for(const auto& m:modules){closed(m,{"role","id","version","pin","options"});c.modules.push_back({get<std::string>(m.at("role")),{get<ModuleId>(m.at("id")),get<std::string>(m.at("version")),get<PinAvailability>(m.at("pin"))},parse_options(m.at("options"))});}
    const auto& n=j.at("numerical");closed(n,{"absolute_bits","relative_bits"});c.numerical={parse_bits(n.at("absolute_bits")),parse_bits(n.at("relative_bits"))};
    const auto& o=j.at("output");closed(o,{"kind","assurance","family","representation","witness_count","distinctness_bits","directions","seed"});
    const auto kind=get<std::string>(o.at("kind"));require(kind=="synthesis"||kind=="program","configuration.output.kind","Unknown output kind");c.output.kind=kind=="synthesis"?OutputKind::synthesis:OutputKind::program;
    c.output.assurance=get<Assurance>(o.at("assurance"));c.output.family=get<FamilyTarget>(o.at("family"));c.output.representation=get<RepresentationId>(o.at("representation"));
    c.output.witnesses.count=get<std::uint64_t>(o.at("witness_count"));c.output.witnesses.distinctness_tolerance=parse_bits(o.at("distinctness_bits"));c.output.witnesses.seed=get<std::optional<std::uint64_t>>(o.at("seed"));
    require(o.at("directions").is_array(),"configuration.output.directions","Expected directions array");for(const auto& row:o.at("directions")){require(row.is_array(),"configuration.output.directions","Expected direction");Vector v;for(const auto& x:row)v.push_back(parse_bits(x));c.output.witnesses.directions.push_back(std::move(v));}
    const auto& r=j.at("resources");closed(r,{"total_threads","outer_workers","threads_per_worker","memory_bytes"});c.resources={get<std::uint64_t>(r.at("total_threads")),get<std::uint64_t>(r.at("outer_workers")),get<std::uint64_t>(r.at("threads_per_worker")),get<std::optional<std::uint64_t>>(r.at("memory_bytes"))};
    const auto& selector=j.at("selector");closed(selector,{"id","version","options"});c.selector={get<ModuleId>(selector.at("id")),get<std::string>(selector.at("version")),parse_options(selector.at("options"))};
    const auto& stop=j.at("stop");require(stop.is_object()&&stop.contains("deadline_budget_ticks"),"configuration.stop","Missing deadline budget");
    if(stop.at("deadline_budget_ticks").is_null())closed(stop,{"deadline_budget_ticks"});else {closed(stop,{"deadline_budget_ticks","period_numerator","period_denominator"});c.deadline_budget=DeadlineBudget{get<std::int64_t>(stop.at("deadline_budget_ticks")),get<std::uint64_t>(stop.at("period_numerator")),get<std::uint64_t>(stop.at("period_denominator"))};}
    const auto& s=j.at("strategy");closed(s,{"strategy","lp","convex","hull","geometry","converter","approximation","selector","representation"});
    const auto role=[&](const char* key)->ModuleId{return s.at(key).is_null()?ModuleId{}:get<ModuleId>(s.at(key));};
    c.strategy={role("strategy"),role("lp"),role("convex"),role("hull"),role("geometry"),role("converter"),role("approximation"),role("selector"),get<RepresentationId>(s.at("representation"))};
    const auto workspace=get<std::string>(j.at("workspace_policy"));require(workspace=="fresh"||workspace=="reused","configuration.workspace_policy","Unknown workspace policy");c.workspace=workspace=="fresh"?WorkspacePolicy::fresh:WorkspacePolicy::reused;return c;
}
} // namespace
} // namespace csl::artifacts

namespace csl::artifacts {
ArtifactResult<RunStatistics> publish_record(RunRecord);
namespace {
void preflight(std::string_view text,const DecodeLimits& limits) {
    if(text.size()>limits.bytes)throw ArtifactError{ArtifactErrorCode::limit,"json.bytes","Input byte capacity exceeded"};
    std::uint64_t depth=0,nodes=0;
    const auto node=[&](){if(++nodes>limits.nodes)throw ArtifactError{ArtifactErrorCode::limit,"json.nodes","Node capacity exceeded"};};
    for(std::size_t i=0;i<text.size();++i){const char c=text[i];
        if(c=='"') {node();std::uint64_t length=0;bool closed_string=false;
            for(++i;i<text.size();++i){const char ch=text[i];if(ch=='"'){closed_string=true;break;}
                if(ch=='\\'){
                    if(++i>=text.size())break;
                    if(text[i]=='u'){
                        if(text.size()-i<5)break;
                        const auto hex4=[&](std::size_t begin){std::uint32_t value=0;for(std::size_t k=0;k<4;++k){const char h=text[begin+k];const auto digit=h>='0'&&h<='9'?h-'0':h>='a'&&h<='f'?h-'a'+10:h>='A'&&h<='F'?h-'A'+10:-1;require(digit>=0,"json.syntax","Invalid Unicode escape");value=(value<<4)|static_cast<unsigned>(digit);}return value;};
                        const auto code=hex4(i+1);
                        if(code>=0xd800&&code<=0xdbff&&text.size()-i>=11&&text[i+5]=='\\'&&text[i+6]=='u'){
                            const auto low=hex4(i+7);require(low>=0xdc00&&low<=0xdfff,"json.syntax","Invalid Unicode surrogate pair");length+=4;i+=10;
                        }else {length+=code<=0x7f?1:code<=0x7ff?2:3;i+=4;}
                    }else ++length;
                }else ++length;
                if(length>limits.string_bytes)throw ArtifactError{ArtifactErrorCode::limit,"json.string","String capacity exceeded"};
            }require(closed_string,"json.syntax","Unterminated string");
        }else if(c=='{'||c=='['){node();if(++depth>limits.depth)throw ArtifactError{ArtifactErrorCode::limit,"json.depth","Depth capacity exceeded"};}
        else if(c=='}'||c==']'){require(depth>0,"json.syntax","Unexpected close");--depth;}
        else if(c=='t'||c=='f'||c=='n'||c=='-'||(c>='0'&&c<='9')){node();while(i+1<text.size()&&text[i+1]!=','&&text[i+1]!=']'&&text[i+1]!='}'&&text[i+1]!=' '&&text[i+1]!='\n'&&text[i+1]!='\r'&&text[i+1]!='\t')++i;}
    }
}
Json parse_document(std::string_view text,const DecodeLimits& limits) {
    preflight(text,limits);std::vector<std::set<std::string>> keys;
    return Json::parse(text.begin(),text.end(),[&](int,Json::parse_event_t event,Json& parsed){
        if(event==Json::parse_event_t::object_start)keys.emplace_back();
        else if(event==Json::parse_event_t::key){require(!keys.empty(),"json.object","Key outside object");require(keys.back().insert(parsed.get<std::string>()).second,"json.duplicate_key","Duplicate object key");}
        else if(event==Json::parse_event_t::object_end)keys.pop_back();
        return true;
    });
}
Json run_json(const RunRecord& r) {
    return {{"schema","csl.run-statistics/4"},{"problem",put(r.problem)},{"dimensions",put(r.dimensions)},
        {"horizon",put(r.horizon)},{"configuration",{{"id",put(r.configuration.identity())},{"value",configuration_record(r.configuration.description(),false)}}},
        {"run",put(r.run)},{"final",put(r.final)},{"statistics",put(r.statistics.description())},{"resources",put(r.resources)},
        {"execution",put(r.execution)},{"attachments",put(r.attachments)},{"provenance",put(r.provenance)},{"selection",put(r.selection)}};
}
ArtifactResult<RunStatistics> read_run(const Json& j) {
    closed(j,{"schema","problem","dimensions","horizon","configuration","run","final","statistics","resources","execution","attachments","provenance","selection"});
    const auto version=get<std::string>(j.at("schema"));
    require(version=="csl.run-statistics/2"||version=="csl.run-statistics/3"||version=="csl.run-statistics/4","schema","Unsupported run statistics version");
    Json current=j;
    if(version=="csl.run-statistics/2") {
        // V2 did not say whether a feasibility claim covered the relation or a witness.
        // Only the explicitly unestablished case can be migrated without invention.
        auto& final=current.at("final");
        if(final.at("kind")=="synthesis") {
            // V2 allowed finite numbers labelled as bounds without support. They
            // cannot become mathematical bounds in V3. Drop only that unsupported
            // payload; a stopped V2 record whose retained scope refers to it
            // needs a reviewed migration rather than an invented scope rewrite.
            auto& value=final.at("value");
            auto& objective=value.at("objective");
            for(const char* side:{"lower","upper"}) {
                auto& bound=objective.at(side);
                if(!bound.is_null()&&std::holds_alternative<Unestablished>(
                    get<ClaimEvidence>(bound.at("evidence")).support)) {
                    require(value.at("stop").at("kind")=="none","schema.migration.objective",
                        "V2 stopped record has unsupported bounds and cannot be migrated without changing its retained scope");
                    bound=nullptr;
                }
            }
            auto& family=final.at("value").at("family");
            if(!family.is_null()&&family.at("family").at("outcome").at("kind")=="candidate") {
                auto& feasibility=family.at("family").at("outcome").at("value").at("feasibility");
                const auto old=get<ClaimEvidence>(feasibility);
                require(old.problem==get<ProblemId>(current.at("problem"))&&std::holds_alternative<Unestablished>(old.support),
                    "schema.migration.candidate.feasibility","V2 feasibility cannot be assigned relation or witness scope");
                feasibility={{"kind","unestablished"},{"value",Json::object()}};
            }
        }
        current["schema"]="csl.run-statistics/3";
    }
    const auto& config=current.at("configuration");closed(config,{"id","value"});auto resolved=resolve_configuration(parse_configuration(config.at("value")));
    if(const auto* error=std::get_if<ArtifactError>(&resolved))return *error;
    const auto configuration=std::get<ResolvedConfiguration>(resolved);
    if(version!="csl.run-statistics/4"&&!current.at("selection").is_null()) {
        auto& batch=current.at("selection").at("batch");
        closed(batch,{"witnesses","requested","selector","seed","source_family"});
        // Older closed formats stored the request facts in configuration only.
        const auto& query=configuration.description().output.witnesses;
        batch["directions"]=put(query.directions);
        batch["distinctness_tolerance"]=put(query.distinctness_tolerance);
    }
    if(configuration.identity()!=get<ConfigId>(config.at("id")))return ArtifactError{ArtifactErrorCode::identity,"configuration.id","Configuration digest mismatch"};
    auto collection=publish_collection(get<CollectionRecord>(current.at("statistics")));if(const auto* error=std::get_if<ArtifactError>(&collection))return *error;
    (void)get<ProblemProvenance>(current.at("provenance"));
    return publish_record({get<ProblemId>(current.at("problem")),get<Dimensions>(current.at("dimensions")),get<std::uint64_t>(current.at("horizon")),configuration,
        get<RunId>(current.at("run")),get<FinalOutcome>(current.at("final")),std::get<CollectedStatistics>(collection),get<ResourceObservation>(current.at("resources")),
        get<std::optional<ExecutionSummary>>(current.at("execution")),get<std::vector<Attachment>>(current.at("attachments")),ProblemProvenance::identity_recorded,get<std::optional<WitnessSelection>>(current.at("selection"))});
}
}
ArtifactResult<RunStatistics> decode_run(std::string_view text,DecodeLimits limits) {
    try {return read_run(parse_document(text,limits));}
    catch(const ArtifactError& e){return e;}
    catch(const Invalid& e){return ArtifactError{ArtifactErrorCode::invalid_input,e.path,e.message};}
    catch(const Json::exception&){return ArtifactError{ArtifactErrorCode::invalid_input,"json.syntax","Malformed JSON document"};}
    catch(const std::bad_alloc&){return ArtifactError{ArtifactErrorCode::allocation,{},{}};}
}
ArtifactResult<RunStatistics> decode_run(std::string_view text,const problem::ResolvedProblem& problem,DecodeLimits limits) {
    try {
    auto result=decode_run(text,limits);if(const auto* error=std::get_if<ArtifactError>(&result))return *error;
    return publish_run({problem,std::get<RunStatistics>(result).description()});
    }catch(const std::bad_alloc&){return ArtifactError{ArtifactErrorCode::allocation,{},{}};}
}
ArtifactResult<std::string> encode_run(const RunStatistics& owner,EncodeLimits limits) {
    const auto* synthesis=std::get_if<SynthesisFinal>(&owner.description().final);
    if(synthesis&&synthesis->family) {
        const auto* complete=std::get_if<CompleteOptimalFamily>(&synthesis->family->family.outcome());
        if(complete&&std::holds_alternative<RegisteredCompletenessEvidence>(complete->completeness.support))
            return ArtifactError{ArtifactErrorCode::unsupported,"run.final.family.completeness.support",
                "run-statistics-v3 does not persist registry-verified completeness payloads"};
    }
    const auto wire=recorded_json(owner);
    if(wire.size()>limits.bytes)return ArtifactError{ArtifactErrorCode::limit,{},{}};
    try {return std::string(wire);}
    catch(const Invalid& e){return ArtifactError{ArtifactErrorCode::invalid_input,e.path,e.message};}
    catch(const Json::exception&){return ArtifactError{ArtifactErrorCode::invalid_input,"json","Invalid portable data"};}
    catch(const std::bad_alloc&){return ArtifactError{ArtifactErrorCode::allocation,{},{}};}
}
ArtifactResult<RecordedRunArtifact> encode_recorded_run(const RunStatistics& owner,EncodeLimits limits) {
    try {
        const auto& record=owner.description();
        const auto* synthesis=std::get_if<SynthesisFinal>(&record.final);
        const CompleteOptimalFamily* complete=nullptr;
        const FamilyRecord* family_record=nullptr;
        bool registered_claim=false;
        if(synthesis&&synthesis->family) {
            family_record=&*synthesis->family;
            complete=std::get_if<CompleteOptimalFamily>(&family_record->family.outcome());
            registered_claim=complete&&std::holds_alternative<RegisteredCompletenessEvidence>(complete->completeness.support);
        }
        if(registered_claim) {
            if(!family_record->family.registry_verified())
                return ArtifactError{ArtifactErrorCode::unsupported,"run.final.family","Only a current-process registry-verified family can be recorded"};
            const auto* external=std::get_if<ExternalFamilyPayload>(&family_record->payload);
            if(!external)return ArtifactError{ArtifactErrorCode::unsupported,"run.final.family.attachment","Registered family claim requires an exported relation attachment"};
            const auto attachment=std::find_if(record.attachments.begin(),record.attachments.end(),[&](const auto& item){return item.id==external->attachment;});
            if(attachment==record.attachments.end()||attachment->role!=AttachmentRole::family||!attachment->content||
                attachment->schema!="csl.h-relation-attachment/1"||attachment->content->digest()!=attachment->digest||
                attachment->content->bytes().size()!=attachment->byte_count)
                return ArtifactError{ArtifactErrorCode::reference,"run.final.family.attachment","Registered family claim requires an owned, integrity-checked H-relation attachment"};
            const HRelationAttachmentLimits relation_limits{limits.bytes,100000,1000000,limits.bytes};
            const auto decoded=decode_h_relation_attachment(attachment->content->bytes(),relation_limits,attachment->digest);
            if(const auto* error=std::get_if<ArtifactError>(&decoded))return *error;
        }
        auto wire=Json::parse(recorded_json(owner));
        require(wire.at("schema")=="csl.run-statistics/4","schema","Live run is not in the current v4 wire form");
        wire["schema"]="csl.run-statistics/5";
        wire["recorded_state"]="unverified_recorded_data";
        const auto text=wire.dump();
        if(text.size()>limits.bytes)return ArtifactError{ArtifactErrorCode::limit,"json.bytes","Encoded recorded artifact exceeds byte limit"};
        std::vector<std::byte> bytes;bytes.reserve(text.size());
        for(const unsigned char value:text)bytes.push_back(static_cast<std::byte>(value));
        auto content=problem::snapshot_content(bytes);
        if(const auto* owned=std::get_if<problem::ResolvedContent>(&content))return RecordedRunArtifact{*owned};
        return ArtifactError{ArtifactErrorCode::allocation,"recorded.content","Could not own recorded artifact bytes"};
    } catch(const ArtifactError& error) { return error; }
    catch(const Invalid& error) { return ArtifactError{ArtifactErrorCode::invalid_input,error.path,error.message}; }
    catch(const Json::exception&) { return ArtifactError{ArtifactErrorCode::invalid_input,"recorded.json","Invalid portable recorded data"}; }
    catch(const std::bad_alloc&) { return ArtifactError{ArtifactErrorCode::allocation,{},{}}; }
}
static ArtifactResult<RecordedRunArtifact> decode_recorded_run_impl(std::string_view text,DecodeLimits limits,
    const problem::ProblemId* expected_problem) {
    try {
        auto wire=parse_document(text,limits);
        closed(wire,{"schema","problem","dimensions","horizon","configuration","run","final","statistics","resources","execution","attachments","provenance","selection","recorded_state"});
        require(wire.at("schema")=="csl.run-statistics/5","schema","Unsupported recorded run schema");
        require(wire.at("recorded_state")=="unverified_recorded_data","recorded_state","Recorded claims are always untrusted");
        require(wire.dump()==text,"recorded.canonical","Recorded artifact is not in canonical form or contains trailing bytes");
        if(expected_problem&&get<ProblemId>(wire.at("problem"))!=*expected_problem)
            return ArtifactError{ArtifactErrorCode::identity,"run.problem","Recorded run does not match the supplied resolved problem"};
        const auto attachments=get<std::vector<Attachment>>(wire.at("attachments"));
        std::set<std::string> ids;
        for(const auto& attachment:attachments) {
            require(!attachment.id.value.empty()&&ids.insert(attachment.id.value).second,"attachment.id","Empty or duplicate attachment ID");
            if(attachment.content)require(attachment.content->digest()==attachment.digest&&attachment.content->bytes().size()==attachment.byte_count,
                "attachment.content","Attachment digest or byte count mismatch");
            if(attachment.role==AttachmentRole::family&&attachment.schema=="csl.h-relation-attachment/1") {
                require(attachment.content.has_value(),"attachment.content","H-relation attachment bytes are required for import");
                const HRelationAttachmentLimits relation_limits{limits.bytes,100000,1000000,limits.string_bytes};
                const auto decoded=decode_h_relation_attachment(attachment.content->bytes(),relation_limits,attachment.digest);
                if(const auto* error=std::get_if<ArtifactError>(&decoded))throw *error;
            }
        }
        const auto is_registered_claim=[&]() {
            if(wire.at("final").at("kind")!="synthesis")return false;
            const auto& synthesis=wire.at("final").at("value");
            if(synthesis.at("family").is_null())return false;
            const auto& family=synthesis.at("family").at("family");
            return family.at("outcome").at("kind")=="complete"&&
                family.at("outcome").at("value").at("completeness").at("support").at("kind")=="registered_verifier";
        };
        if(is_registered_claim()) {
            const auto& synthesis=wire.at("final").at("value");
            const auto& family_record=synthesis.at("family");
            const auto& payload=family_record.at("payload");
            require(payload.at("kind")=="external_reference","run.final.family.payload",
                "Recorded complete-family claim requires an external relation attachment");
            const auto attachment_id=get<AttachmentId>(payload.at("value").at("attachment"));
            const auto attachment=std::find_if(attachments.begin(),attachments.end(),[&](const auto& item){return item.id==attachment_id;});
            require(attachment!=attachments.end()&&attachment->role==AttachmentRole::family&&attachment->schema=="csl.h-relation-attachment/1"&&
                attachment->content.has_value(),"run.final.family.attachment","Registered family claim has no owned H-relation attachment");
        }
        std::vector<std::byte> bytes;bytes.reserve(text.size());
        for(const unsigned char value:text)bytes.push_back(static_cast<std::byte>(value));
        auto content=problem::snapshot_content(bytes);
        if(const auto* owned=std::get_if<problem::ResolvedContent>(&content))return RecordedRunArtifact{*owned};
        return ArtifactError{ArtifactErrorCode::allocation,"recorded.content","Could not own imported artifact bytes"};
    } catch(const ArtifactError& error) { return error; }
    catch(const Invalid& error) { return ArtifactError{ArtifactErrorCode::invalid_input,error.path,error.message}; }
    catch(const Json::exception&) { return ArtifactError{ArtifactErrorCode::invalid_input,"recorded.json","Malformed recorded artifact"}; }
    catch(const std::bad_alloc&) { return ArtifactError{ArtifactErrorCode::allocation,{},{}}; }
}
ArtifactResult<RecordedRunArtifact> decode_recorded_run(std::string_view text,DecodeLimits limits) {
    return decode_recorded_run_impl(text,limits,nullptr);
}
ArtifactResult<RecordedRunArtifact> decode_recorded_run(std::string_view text,const problem::ResolvedProblem& problem,DecodeLimits limits) {
    const auto expected_problem=problem.identity();
    return decode_recorded_run_impl(text,limits,&expected_problem);
}
ArtifactResult<std::string> check_record_portability(const RunRecord& record) {
    try {return run_json(record).dump();}
    catch(const Invalid& e){return ArtifactError{ArtifactErrorCode::invalid_input,e.path,e.message};}
    catch(const Json::exception&){return ArtifactError{ArtifactErrorCode::invalid_input,"run","Invalid UTF-8 portable value"};}
    catch(const std::bad_alloc&){return ArtifactError{ArtifactErrorCode::allocation,{},{}};}
}
ArtifactResult<bool> check_collection_portability(const CollectionRecord& record) {
    try {
        for(const auto& s:record.spans){(void)pin(s.descriptor.module.pin,false);if(s.descriptor.backend)(void)pin(s.descriptor.backend->pin,false);}
        (void)put(record).dump();return true;
    }catch(const Invalid& e){return ArtifactError{ArtifactErrorCode::invalid_input,e.path,e.message};}
    catch(const Json::exception&){return ArtifactError{ArtifactErrorCode::invalid_input,"collection","Invalid UTF-8 portable value"};}
    catch(const std::bad_alloc&){return ArtifactError{ArtifactErrorCode::allocation,{},{}};}
}
} // namespace csl::artifacts
