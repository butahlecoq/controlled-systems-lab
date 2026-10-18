#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <csl/artifacts/run_statistics.hpp>
#include <csl/registry/registry.hpp>
#include <csl/execution/observability.hpp>
#include <csl/optimization/linear_infeasibility_certificate.hpp>
#include <nlohmann/json.hpp>
#include <algorithm>
#include <array>
#include <cmath>
#include <fstream>
#include <limits>
#include <thread>
#include <latch>
#include <cstdlib>
#include <new>
namespace allocation_probe {
thread_local bool enabled=false,injected=false;thread_local std::size_t count=0,max_size=0,failure_minimum=0;
struct ScopedFailure {
    explicit ScopedFailure(std::size_t minimum){count=0;max_size=0;injected=false;failure_minimum=minimum;enabled=true;}
    ~ScopedFailure(){enabled=false;failure_minimum=0;}
    ScopedFailure(const ScopedFailure&)=delete;
    ScopedFailure& operator=(const ScopedFailure&)=delete;
};
}
// Keep replacement allocation/deallocation calls observable as a matched pair.
// Partial inlining otherwise makes GCC diagnose malloc/free inside delete as a
// mismatched caller-side new/delete pair at -O3.
#if defined(_MSC_VER)
#define CSL_ALLOCATION_PROBE_NOINLINE __declspec(noinline)
#else
#define CSL_ALLOCATION_PROBE_NOINLINE __attribute__((noinline))
#endif
CSL_ALLOCATION_PROBE_NOINLINE void* operator new(std::size_t size) {
    if(allocation_probe::enabled){++allocation_probe::count;allocation_probe::max_size=std::max(allocation_probe::max_size,size);
        if(allocation_probe::failure_minimum&&size>=allocation_probe::failure_minimum){allocation_probe::failure_minimum=0;allocation_probe::injected=true;throw std::bad_alloc{};}}
    if(void* result=std::malloc(size?size:1))return result;
    throw std::bad_alloc{};
}
CSL_ALLOCATION_PROBE_NOINLINE void* operator new[](std::size_t size){return ::operator new(size);}
CSL_ALLOCATION_PROBE_NOINLINE void operator delete(void* p)noexcept{std::free(p);}
CSL_ALLOCATION_PROBE_NOINLINE void operator delete[](void* p)noexcept{std::free(p);}
CSL_ALLOCATION_PROBE_NOINLINE void operator delete(void* p,std::size_t)noexcept{std::free(p);}
CSL_ALLOCATION_PROBE_NOINLINE void operator delete[](void* p,std::size_t)noexcept{std::free(p);}
#undef CSL_ALLOCATION_PROBE_NOINLINE
using namespace csl;
namespace ar = csl::artifacts;
namespace ob = csl::execution::observability;
namespace {
template<class T,class... E> T accepted(std::variant<T,E...> value) {
    const auto* error=std::get_if<ar::ArtifactError>(&value);
    INFO((error?error->path+": "+error->message:std::string{}));
    REQUIRE(std::holds_alternative<T>(value));return std::get<T>(std::move(value));
}
ar::ConfigurationInput configuration() {
    ar::ConfigurationInput c;
    c.collection={true,ar::CollectionMode::detail,4,4096,3,4096};
    const ar::PinAvailability pin=ar::Unavailable{ar::MissingReason::not_instrumented,""};
    c.modules={ {"lp",{{"lp-a"},"1",pin},{}}, {"strategy",{{"joint"},"1",pin},{}} };
    c.numerical={0,0};c.resources={2,2,1,{}};
    c.output={ar::OutputKind::synthesis,Assurance::numerical,FamilyTarget::exact_optimal_relation,{"joint"},{1,0,{},{}}};
    c.selector={{"first"},"1",{}};
    c.strategy={{"joint"},{"lp-a"},{},{},{},{},{},{"first"},{"joint"}};
    c.workspace=ar::WorkspacePolicy::fresh;
    return c;
}
}
TEST_CASE("resolved configuration uses independent backend enabled and mode digests") {
    auto input=configuration();const auto a=accepted(ar::resolve_configuration(input));
    CHECK(a.canonical_bytes().size()==1108);
    CHECK(a.identity().value=="csl.config.v1.sha256:e27f771c2d04bb72827ad27eeaa4123a4df58eaea22aaac4b789ee36033e5abf");
    input.modules[0].implementation.id.value="lp-b";input.strategy.lp.value="lp-b";
    const auto b=accepted(ar::resolve_configuration(input));
    CHECK(b.identity().value=="csl.config.v1.sha256:be6229a59f2b2f14b2660dd3437bbbd225f73c808c51c2a93eef795fe62ab49a");
    input=configuration();input.collection.enabled=false;
    CHECK(accepted(ar::resolve_configuration(input)).identity().value=="csl.config.v1.sha256:58af261ea42c3dc78dad8a7d1e037de2df3747a9342b1a4e77d771c6bf598411");
    input=configuration();input.collection.mode=ar::CollectionMode::summary;
    CHECK(accepted(ar::resolve_configuration(input)).identity().value=="csl.config.v1.sha256:f3ad7c39b5afefe7b007ead1d82726540f340a217fac59f33b3db0c221d4b08e");
    input=configuration();std::get<ar::Unavailable>(input.modules[0].implementation.pin).detail="local test module; pin not captured";
    const auto prose=accepted(ar::resolve_configuration(input));CHECK(prose.identity()==a.identity());
    CHECK(std::get<ar::Unavailable>(prose.description().modules[0].implementation.pin).detail=="local test module; pin not captured");
    input.modules[0].implementation.id.value="changed-after-publication";
    CHECK(prose.description().modules[0].implementation.id.value=="lp-a");
}
TEST_CASE("tick durations preserve zero missing and checked differences") {
    ar::TickInterval zero{ar::Available<std::int64_t>{0},ar::Available<std::int64_t>{0}};
    CHECK(std::get<ar::Available<std::uint64_t>>(ar::elapsed_ticks(zero)).value==0);
    ar::TickInterval unfinished{ar::Available<std::int64_t>{1},ar::Unavailable{ar::MissingReason::incomplete_span,""}};
    CHECK(std::get<ar::Unavailable>(ar::elapsed_ticks(unfinished)).reason==ar::MissingReason::incomplete_span);
    ar::TickInterval extreme{ar::Available<std::int64_t>{std::numeric_limits<std::int64_t>::min()},ar::Available<std::int64_t>{std::numeric_limits<std::int64_t>::max()}};
    CHECK(std::get<ar::Unavailable>(ar::elapsed_ticks(extreme)).reason==ar::MissingReason::overflow);
    ar::TickInterval backwards{ar::Available<std::int64_t>{2},ar::Available<std::int64_t>{1}};
    CHECK(std::get<ar::Unavailable>(ar::elapsed_ticks(backwards)).reason==ar::MissingReason::clock_mismatch);
}
TEST_CASE("configuration rejects unresolved contradictory pin and collection data") {
    auto c=configuration();c.collection.detail_spans=5;
    CHECK(std::holds_alternative<ar::ArtifactError>(ar::resolve_configuration(c)));
    c=configuration();c.modules.pop_back();CHECK(std::holds_alternative<ar::ArtifactError>(ar::resolve_configuration(c)));
    c=configuration();c.modules[0].implementation.version="";CHECK(std::holds_alternative<ar::ArtifactError>(ar::resolve_configuration(c)));
    c=configuration();c.modules[0].implementation.pin=ar::Unavailable{ar::MissingReason::execution_unknown,""};
    CHECK(std::holds_alternative<ar::ArtifactError>(ar::resolve_configuration(c)));
    c=configuration();c.modules[0].implementation.pin=ar::Available<ar::ModulePin>{{ar::PinScope::source_archive,"ABC"}};
    CHECK(std::holds_alternative<ar::ArtifactError>(ar::resolve_configuration(c)));
    c=configuration();c.modules[0].implementation.pin=ar::Unavailable{ar::MissingReason::not_instrumented,std::string(257,'x')};
    CHECK(std::holds_alternative<ar::ArtifactError>(ar::resolve_configuration(c)));
    c=configuration();c.numerical.absolute_tolerance=std::numeric_limits<double>::infinity();CHECK(std::holds_alternative<ar::ArtifactError>(ar::resolve_configuration(c)));
    c=configuration();std::reverse(c.modules.begin(),c.modules.end());
    const auto a=accepted(ar::resolve_configuration(c));CHECK(a.identity().value=="csl.config.v1.sha256:e27f771c2d04bb72827ad27eeaa4123a4df58eaea22aaac4b789ee36033e5abf");
    c=configuration();c.numerical.absolute_tolerance=-0.0;CHECK(accepted(ar::resolve_configuration(c)).identity()!=a.identity());
}
namespace {
problem::ResolvedProblem zero_problem() {
    Problem z{{"zero"},std::make_shared<const SystemModel>(SystemModel{{{0,0,0},TimeDomain::discrete,
        LinearStage{{0,0,{}},{0,0,{}},{0,0,{}},{}}},{}}),{0},KnownInitial{{}},ContinuousDomain{{}},
        {UniversalSet{0}},{},{},InformationPattern::nominal_open_loop,LinearTerminal{{},0}};
    auto result=problem::resolve(z,{problem::UncertaintyStructure::stage_product_uncoupled});
    REQUIRE(std::holds_alternative<problem::ResolvedProblem>(result));return std::get<problem::ResolvedProblem>(result);
}
ob::PlanInput plan_input(ar::CollectionMode mode=ar::CollectionMode::detail) {
    auto c=configuration();c.collection.mode=mode;
    ob::PlanInput input{zero_problem(),accepted(ar::resolve_configuration(c)),{"run-a"},
        {{{"wall"},ar::ClockMetric::steady_wall,"run",1,1000,ar::Available<std::uint64_t>{1},"run-origin",ar::Unavailable{ar::MissingReason::not_instrumented,{}}}},{},2};
    for(std::uint64_t i=0;i<4;++i) {
        ar::SpanDescriptor d{};d.id={i};if(i) d.parent=ar::SpanParent{{i==3?1u:0u},ar::ParentKind::nested};
        d.shard=i%2;d.bucket=0;d.task="task";d.operation="solve";d.module=c.modules[0].implementation;
        d.clock={"wall"};d.requested_assurance=Assurance::numerical;d.applied_assurance=ar::Available<Assurance>{Assurance::numerical};
        input.spans.push_back(std::move(d));
    }
    input.tasks={"task"};input.operations={"solve"};
    return input;
}
ob::SpanCompletionView completion(std::uint64_t id) {
    constexpr std::int64_t starts[]{0,2,5,4},ends[]{20,12,17,9};
    return {{id},{true,starts[id],ar::MissingReason::not_requested},{true,ends[id],ar::MissingReason::not_requested},
        ob::ObservationState::returned,ar::NotCalledReason::task_not_admitted,true,Termination::completed,
        {true,0,ar::MissingReason::not_requested},"owned detail"};
}
}
TEST_CASE("bounded collector retains fixed endpoints and deterministically drops fourth detail") {
    auto input=plan_input();CHECK(input.problem.identity().value=="csl.problem.v1.sha256:2320a9f596bfa8f5bdd8aa6d272ca96fe5ff229411b65e1ab3e6f469a27f815e");
    const auto plan=accepted(ob::make_collection_plan(std::move(input)));
    auto even=accepted(ob::make_observation_shard(plan,{0}));auto odd=accepted(ob::make_observation_shard(plan,{1}));
    CHECK(odd.record(completion(3))==ob::RecordDisposition::detail_dropped);
    CHECK(even.record(completion(2))==ob::RecordDisposition::retained);
    CHECK(odd.record(completion(1))==ob::RecordDisposition::retained);
    CHECK(even.record(completion(0))==ob::RecordDisposition::retained);
    std::vector<ob::ObservationShard> shards;shards.push_back(std::move(odd));shards.push_back(std::move(even));
    const auto merged=accepted(ob::merge_observations(plan,std::move(shards)));const auto& record=merged.description();
    REQUIRE(record.spans.size()==4);CHECK(record.spans[3].descriptor.id.value==3);
    CHECK(std::get<ar::Available<std::uint64_t>>(ar::elapsed_ticks(std::get<ar::TickInterval>(record.spans[3].interval))).value==5);
    CHECK(std::get<ar::Unavailable>(record.spans[3].detail).reason==ar::MissingReason::detail_limit);
    CHECK(record.buckets[0].observed.value==4);CHECK(record.buckets[0].detail_dropped.value==1);
    CHECK(std::get<ar::Available<std::uint64_t>>(record.buckets[0].inclusive_ticks).value==47);
    CHECK(std::get<ar::Available<bool>>(record.complete).value);
}
TEST_CASE("portable run codec owns actual problem binding and disabled skipped outcome") {
    auto c=configuration();c.collection.enabled=false;const auto config=accepted(ar::resolve_configuration(c));const auto z=zero_problem();
    const auto plan=accepted(ob::make_collection_plan({z,config,{"disabled-run"},{},{},0}));
    const auto statistics=accepted(ob::merge_observations(plan,{}));
    const ar::Unavailable missing{ar::MissingReason::not_instrumented,""};
    ar::RunRecord record{z.identity(),{0,0,0},0,config,{"disabled-run"},ar::SkippedFinal{ar::SkippedReason::cancelled},statistics,
        {missing,missing,missing,missing,true,ar::MemoryAccounting::unlimited},{},{},ar::ProblemProvenance::problem_revalidated};
    auto owner=accepted(ar::publish_run({z,record}));
    auto wire=accepted(ar::encode_run(owner));CHECK(wire.find("csl.run-statistics/4")!=std::string::npos);
    const auto restored=accepted(ar::decode_run(wire));wire.assign("destroyed producer buffer");
    CHECK(restored.description().problem.value=="csl.problem.v1.sha256:2320a9f596bfa8f5bdd8aa6d272ca96fe5ff229411b65e1ab3e6f469a27f815e");
    CHECK(restored.description().provenance==ar::ProblemProvenance::identity_recorded);
    CHECK(std::get<ar::SkippedFinal>(restored.description().final).reason==ar::SkippedReason::cancelled);
    CHECK(restored.description().configuration.identity().value=="csl.config.v1.sha256:58af261ea42c3dc78dad8a7d1e037de2df3747a9342b1a4e77d771c6bf598411");
    CHECK(std::get<ar::Unavailable>(restored.description().statistics.description().complete).reason==ar::MissingReason::collection_disabled);
    CHECK(accepted(ar::decode_run(accepted(ar::encode_run(restored)),z)).description().provenance==ar::ProblemProvenance::problem_revalidated);
}
TEST_CASE("independent full history fixture retains witnesses family evidence nested clocks and attachments") {
    std::ifstream source(CSL_STATISTICS_FIXTURE);const std::string text{std::istreambuf_iterator<char>{source},std::istreambuf_iterator<char>{}};
    REQUIRE(!text.empty());const auto owner=accepted(ar::decode_run(text));const auto& r=owner.description();
    CHECK(r.horizon==2);REQUIRE(r.statistics.description().spans.size()==4);
    const auto& final=std::get<ar::SynthesisFinal>(r.final);REQUIRE(final.incumbents.size()==2);
    CHECK(final.incumbents[0].witness.states==std::vector<Vector>{{0},{0},{1}});CHECK(final.incumbents[0].witness.controls==std::vector<Vector>{{0},{1}});
    CHECK(final.incumbents[1].witness.states==std::vector<Vector>{{0},{1},{1}});CHECK(final.incumbents[1].witness.controls==std::vector<Vector>{{1},{0}});
    CHECK(final.incumbents[0].witness.original_objective==0);REQUIRE(final.family.has_value());
    CHECK(std::holds_alternative<Unestablished>(std::get<CandidateFamily>(final.family->family.outcome()).feasibility));
    CHECK(std::get<ar::ExternalFamilyPayload>(final.family->payload).attachment.value=="family-relation");
    CHECK(problem::hex(r.attachments[1].content->digest())=="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    const auto encoded=accepted(ar::encode_run(owner));
    const auto restored=accepted(ar::decode_run(encoded));
    CHECK(std::get<ar::SynthesisFinal>(restored.description().final).incumbents[1].witness.controls==std::vector<Vector>{{1},{0}});
    CHECK(std::get<ar::Available<std::uint64_t>>(restored.description().statistics.description().buckets[0].inclusive_ticks).value==47);
}
TEST_CASE("post-join projection preserves earlier failure later cancellation and original deadline") {
    using namespace execution;using Duration=TimePoint::duration;
    const TimePoint origin{};
    BatchTiming timing{origin,origin-Duration{1},AdmissionCloseObservation{BatchStopCause::adapter_exception,origin+Duration{1}},origin+Duration{2},origin+Duration{7},origin+Duration{8}};
    const auto value=ob::project_execution(timing);
    CHECK(std::get<ar::Available<std::int64_t>>(value.configured_deadline).value==-1);
    REQUIRE(value.admission_closed.has_value());CHECK(value.admission_closed->cause==ar::AdmissionCause::adapter_exception);
    CHECK(std::get<ar::Available<std::uint64_t>>(ar::elapsed_ticks({value.external_cancellation,value.completed})).value==6);
    CHECK(std::get<ar::Available<std::uint64_t>>(ar::elapsed_ticks({value.admission_closed->at,value.completed})).value==7);
    timing.started_at=TimePoint::min();timing.completed_at=TimePoint::max();
    CHECK(std::get<ar::Unavailable>(ob::project_execution(timing).completed).reason==ar::MissingReason::overflow);
}
TEST_CASE("canonical final and legacy projections retain portable evidence and precision") {
    const auto z=zero_problem();const ProgramIdentity subject{z.identity(),{"program-a"}};
    ProgramResult program{Termination::completed,{subject,MathematicalOutcome::optimal,Unestablished{},{}},Vector{2},
        {ProgramObjectiveBound{4,{subject,Unestablished{},{}}},ProgramObjectiveBound{4,{subject,Unestablished{},{}}}},"literal diagnostic",
        {PrimalResiduals{{subject,{{"verifier"},"1"},0,0},{0,1},{0,1}},{}}};
    const auto projection=ar::project_final(program);CHECK(projection.result.primal==Vector{2});
    REQUIRE(projection.result.objective.upper.has_value());CHECK(projection.result.objective.upper->value==4);
    REQUIRE(projection.result.residuals.primal.has_value());CHECK(projection.result.residuals.primal->rows.violation==0);
    const auto descriptor=plan_input().spans[0];const auto legacy=accepted(ar::project_legacy_span({0,{}, {"lp-a"},0.125,0.375},descriptor));
    CHECK(std::get<ar::LegacySecondsInterval>(legacy.interval).start==0.125);CHECK(std::get<ar::LegacySecondsInterval>(legacy.interval).end==0.375);
    CHECK(std::holds_alternative<ar::ArtifactError>(ar::project_legacy_span({0,{}, {"foreign"},0.125,0.375},descriptor)));
}
namespace {
std::string fixture_text(){std::ifstream source(CSL_STATISTICS_FIXTURE);return {std::istreambuf_iterator<char>{source},std::istreambuf_iterator<char>{}};}
std::string fixture_v2_text(){std::ifstream source(CSL_STATISTICS_V2_FIXTURE);return {std::istreambuf_iterator<char>{source},std::istreambuf_iterator<char>{}};}
problem::ResolvedProblem integrator_problem();
std::string changed(std::string source,std::string_view from,std::string_view to){const auto position=source.find(from);REQUIRE(position!=std::string::npos);source.replace(position,from.size(),to);return source;}
}
TEST_CASE("serialized registered verifier evidence decodes as untrusted and cannot publish complete family") {
    auto document=nlohmann::json::parse(fixture_text());
    auto& family=document["final"]["value"]["family"]["family"];
    const auto identity=family["identity"];
    const auto problem=identity["problem"];
    const nlohmann::json claim{{"problem",problem},{"support",{{"kind","symbolic_argument"},
        {"value",{{"reference","serialized claim"},{"assumptions","untrusted text"}}}}}};
    const nlohmann::json complete{{"relation",{{"coordinates",identity["coordinates"]},
            {"representation",identity["request"]["representation"]}}},
        {"optimum",{{"optimum",claim},{"bounds",{{"lower",{{"value",0.0},{"evidence",claim}}},
            {"upper",{{"value",0.0},{"evidence",claim}}}}}}},
        {"completeness",{{"binding",identity},{"support",{{"kind","registered_verifier"},
            {"value",{{"verifier","csl.verifier.ts01-analytic"},{"verifier_version","1"},{"proof","TS01-analytic-v1"}}}}}}},
        {"assurance","numerical"}};
    family["outcome"]={{"kind","complete"},{"value",complete}};
    const auto decoded=ar::decode_run(document.dump());
    REQUIRE(std::holds_alternative<ar::ArtifactError>(decoded));
    CHECK(std::get<ar::ArtifactError>(decoded).path=="family.family.publisher");
}
TEST_CASE("historical v1 synthesis record is retained but requires explicit migration") {
    std::ifstream source(CSL_STATISTICS_V1_FIXTURE);
    const std::string historical{std::istreambuf_iterator<char>{source},std::istreambuf_iterator<char>{}};
    REQUIRE(historical.find("csl.run-statistics/1")!=std::string::npos);
    const auto decoded=ar::decode_run(historical);
    REQUIRE(std::holds_alternative<ar::ArtifactError>(decoded));
    CHECK(std::get<ar::ArtifactError>(decoded).path=="schema");
}
TEST_CASE("historical v2 candidate remains unestablished under scoped feasibility") {
    const auto historical=fixture_v2_text();
    REQUIRE(historical.find("csl.run-statistics/2")!=std::string::npos);
    const auto restored=accepted(ar::decode_run(historical,integrator_problem()));
    const auto& final=std::get<ar::SynthesisFinal>(restored.description().final);
    CHECK_FALSE(final.objective.lower.has_value());
    CHECK_FALSE(final.objective.upper.has_value());
    const auto& family=final.family->family;
    CHECK(std::holds_alternative<Unestablished>(std::get<CandidateFamily>(family.outcome()).feasibility));
    CHECK(accepted(ar::encode_run(restored)).find("csl.run-statistics/4")!=std::string::npos);
}
TEST_CASE("historical v2 supported candidate is not promoted to scoped feasibility") {
    auto historical=fixture_v2_text();
    const auto candidate=historical.find("\"relation_to_target\"");
    REQUIRE(candidate!=std::string::npos);
    const auto feasibility=historical.find("\"feasibility\"",candidate);
    REQUIRE(feasibility!=std::string::npos);
    const auto support=historical.find("\"kind\": \"unestablished\"",feasibility);
    REQUIRE(support!=std::string::npos);
    historical.replace(support,std::string{"\"kind\": \"unestablished\""}.size(),"\"kind\": \"symbolic_argument\"");
    const auto value=historical.find("\"value\": {}",support);
    REQUIRE(value!=std::string::npos);
    historical.replace(value,std::string{"\"value\": {}"}.size(),"\"value\": {\"reference\": \"old proof\", \"assumptions\": \"legacy\"}");
    const auto decoded=ar::decode_run(historical);
    REQUIRE(std::holds_alternative<ar::ArtifactError>(decoded));
    CHECK(std::get<ar::ArtifactError>(decoded).path=="schema.migration.candidate.feasibility");
}
TEST_CASE("candidate feasibility rejects an unknown v3 scope discriminator") {
    auto fixture=fixture_text();
    const auto feasibility=fixture.find("\"feasibility\"",fixture.find("\"relation_to_target\""));
    REQUIRE(feasibility!=std::string::npos);
    const auto tag=fixture.find("\"kind\": \"unestablished\"",feasibility);
    REQUIRE(tag!=std::string::npos);
    fixture.replace(tag,std::string{"\"kind\": \"unestablished\""}.size(),"\"kind\": \"unknown_scope\"");
    CHECK(std::holds_alternative<ar::ArtifactError>(ar::decode_run(fixture)));
}
TEST_CASE("strict codec rejects malformed variants duplicate keys forged identity and declared limits") {
    const auto fixture=fixture_text();
    const std::vector<std::pair<std::string,std::string>> cases{
        {"csl.run-statistics/3","csl.run-statistics/9"},
        {"\"schema\": \"csl.run-statistics/3\",","\"schema\": \"csl.run-statistics/3\", \"schema\": \"csl.run-statistics/3\","},
        {"\"horizon\": \"2\"","\"horizon\": \"02\""},
        {"\"horizon\": \"2\"","\"horizon\": \"18446744073709551616\""},
        {"\"horizon\": \"2\"","\"horizon\": \"-1\""},
        {"\"enabled\": true","\"enabled\": \"true\""},
        {"\"mode\": \"detail\"","\"mode\": \"auto\""},
        {"\"reason\": \"not_instrumented\"","\"reason\": \"local_test\""},
        {"\"value\": null","\"value\": 0"},
        {"\"detail\": \"\",","\"unexpected\": \"\","},
        {"\"period_denominator\": \"1000\"","\"period_denominator\": \"0\""},
        {"family/relation.txt","../family.txt"},
        {"\"content\": \"616263\"","\"content\": \"616264\""},
        {"\"requested_assurance\": \"numerical\"","\"requested_assurance\": \"imaginary\""},
        {"\"value\": \"numerical\"","\"value\": \"validated\""},
        {"csl.config.v1.sha256:e27f771c2d04bb72827ad27eeaa4123a4df58eaea22aaac4b789ee36033e5abf","csl.config.v1.sha256:027f771c2d04bb72827ad27eeaa4123a4df58eaea22aaac4b789ee36033e5abf"}
    };
    for(const auto& [from,to]:cases){INFO(from);CHECK(std::holds_alternative<ar::ArtifactError>(ar::decode_run(changed(fixture,from,to))));}
    CHECK(std::holds_alternative<ar::ArtifactError>(ar::decode_run(fixture+" trailing")));
    CHECK(std::holds_alternative<ar::ArtifactError>(ar::decode_run(changed(fixture,"owned detail",std::string(1,static_cast<char>(0xff))))));
    for(const auto limits:{ar::DecodeLimits{1,1000000,64,1000000},ar::DecodeLimits{1000000,1,64,1000000},ar::DecodeLimits{1000000,1000000,1,1000000},ar::DecodeLimits{1000000,1000000,64,1}}){
        const auto result=ar::decode_run(fixture,limits);REQUIRE(std::holds_alternative<ar::ArtifactError>(result));CHECK(std::get<ar::ArtifactError>(result).code==ar::ArtifactErrorCode::limit);
    }
}
TEST_CASE("collection summary disabled counters overflow missing shards and plan tokens stay explicit") {
    auto input=plan_input(ar::CollectionMode::summary);const auto summary_plan=accepted(ob::make_collection_plan(input));
    auto s=accepted(ob::make_observation_shard(summary_plan,{0}));
    CHECK(s.record(completion(0))==ob::RecordDisposition::detail_dropped);
    CHECK(s.record(completion(2))==ob::RecordDisposition::detail_dropped);
    CHECK(s.record(completion(0))==ob::RecordDisposition::duplicate);
    CHECK(s.record(completion(1))==ob::RecordDisposition::wrong_shard);s.record_overflow(0,3);
    std::vector<ob::ObservationShard> shards;shards.push_back(std::move(s));const auto record=accepted(ob::merge_observations(summary_plan,std::move(shards))).description();
    CHECK(record.buckets[0].observed.value==2);CHECK(record.buckets[0].duplicate.value==1);CHECK(record.buckets[0].wrong_shard.value==1);
    CHECK(record.buckets[0].declared_overflow.value==3);CHECK(record.buckets[0].detail_dropped.value==0);
    CHECK(std::get<ar::Unavailable>(record.spans[0].detail).reason==ar::MissingReason::not_requested);
    CHECK(std::get<ar::Unavailable>(record.complete).reason==ar::MissingReason::incomplete_span);
    CHECK(std::holds_alternative<ar::UnknownObservation>(record.spans[1].execution));
    auto overflow=accepted(ob::make_observation_shard(summary_plan,{0}));overflow.record_overflow(0,std::numeric_limits<std::uint64_t>::max());overflow.record_overflow(0,1);
    std::vector<ob::ObservationShard> overflows;overflows.push_back(std::move(overflow));const auto counts=accepted(ob::merge_observations(summary_plan,std::move(overflows))).description().buckets[0].declared_overflow;
    CHECK(counts.value==std::numeric_limits<std::uint64_t>::max());CHECK_FALSE(counts.exact);
    const auto other=accepted(ob::make_collection_plan(input));std::vector<ob::ObservationShard> foreign;foreign.push_back(accepted(ob::make_observation_shard(other,{0})));
    CHECK(std::holds_alternative<ar::ArtifactError>(ob::merge_observations(summary_plan,std::move(foreign))));
    std::vector<ob::ObservationShard> duplicates;duplicates.push_back(accepted(ob::make_observation_shard(summary_plan,{0})));duplicates.push_back(accepted(ob::make_observation_shard(summary_plan,{0})));
    CHECK(std::holds_alternative<ar::ArtifactError>(ob::merge_observations(summary_plan,std::move(duplicates))));
    input.shard_count=std::numeric_limits<std::uint64_t>::max();CHECK(std::holds_alternative<ar::ArtifactError>(ob::make_collection_plan(input)));
}
TEST_CASE("two exclusive producer threads preserve deterministic fixed ordering") {
    const auto plan=accepted(ob::make_collection_plan(plan_input()));auto even=accepted(ob::make_observation_shard(plan,{0}));auto odd=accepted(ob::make_observation_shard(plan,{1}));
    std::latch launch(1);
    std::jthread first([&]{launch.wait();(void)even.record(completion(2));(void)even.record(completion(0));});
    std::optional<std::jthread> second;
    try {second.emplace([&]{launch.wait();(void)odd.record(completion(3));(void)odd.record(completion(1));});}
    catch(...){launch.count_down();throw;} // Release a started producer if second launch fails.
    launch.count_down();first.join();second->join();
    std::vector<ob::ObservationShard> shards;shards.push_back(std::move(even));shards.push_back(std::move(odd));const auto result=accepted(ob::merge_observations(plan,std::move(shards)));
    for(std::size_t i=0;i<4;++i)CHECK(result.description().spans[i].descriptor.id.value==i);
    CHECK(result.description().buckets[0].observed.value==4);CHECK(std::get<ar::Available<std::uint64_t>>(result.description().buckets[0].inclusive_ticks).value==47);
}
TEST_CASE("record owns bounded bytes with zero post-construction allocations") {
    const auto plan=accepted(ob::make_collection_plan(plan_input()));auto even=accepted(ob::make_observation_shard(plan,{0}));auto odd=accepted(ob::make_observation_shard(plan,{1}));
    std::string producer="retained source text";auto retained=completion(0);retained.detail=producer;
    const std::string large_detail(4097,'x');auto oversized=completion(2);oversized.detail=large_detail;
    allocation_probe::count=0;allocation_probe::enabled=true;
    const auto a=even.record(retained);const auto b=odd.record(completion(3));const auto c=even.record(oversized);
    allocation_probe::enabled=false;CHECK(allocation_probe::count==0);
    CHECK(a==ob::RecordDisposition::retained);CHECK(b==ob::RecordDisposition::detail_dropped);CHECK(c==ob::RecordDisposition::detail_rejected);
    producer.assign("destroyed");std::vector<ob::ObservationShard> shards;shards.push_back(std::move(even));shards.push_back(std::move(odd));
    const auto result=accepted(ob::merge_observations(plan,std::move(shards)));
    CHECK(std::get<ar::Available<std::string>>(result.description().spans[0].detail).value=="retained source text");
    CHECK(std::get<ar::Unavailable>(result.description().spans[2].detail).reason==ar::MissingReason::detail_limit);
    CHECK(result.description().spans[0].detail_state==ar::DetailState::retained);
    CHECK(result.description().spans[2].detail_state==ar::DetailState::rejected);
    CHECK(result.description().spans[3].detail_state==ar::DetailState::capacity_dropped);
}
TEST_CASE("literal T2 identity actually resolves and revalidates the independent full fixture") {
    Problem p{{"integrator"},std::make_shared<const SystemModel>(SystemModel{{{1,1,0},TimeDomain::discrete,
        LinearStage{{1,1,{1}},{1,1,{1}},{1,0,{}},{0}}},{}}),{0,1,2},KnownInitial{{0}},ContinuousDomain{{UniversalSet{1},UniversalSet{1}}},
        {UniversalSet{1},UniversalSet{1},Singleton{{1}}},{},{},InformationPattern::nominal_open_loop,LinearTerminal{{0},0}};
    const auto resolution=problem::resolve(p,{problem::UncertaintyStructure::stage_product_uncoupled});REQUIRE(std::holds_alternative<problem::ResolvedProblem>(resolution));
    const auto actual=std::get<problem::ResolvedProblem>(resolution);
    CHECK(actual.identity().value=="csl.problem.v1.sha256:c3eb59c9382beedb7fabcb9682d168f418ae203c34706985de1c7b5d0de9c579");
    const auto artifact=accepted(ar::decode_run(fixture_text(),actual));CHECK(artifact.description().provenance==ar::ProblemProvenance::problem_revalidated);
    CHECK(std::holds_alternative<ar::ArtifactError>(ar::decode_run(fixture_text(),zero_problem())));
}
TEST_CASE("live publication rejects invalid portable enums before producing an owner") {
    auto c=configuration();c.collection.enabled=false;const auto config=accepted(ar::resolve_configuration(c));const auto z=zero_problem();
    const auto plan=accepted(ob::make_collection_plan({z,config,{"bad-run"},{},{},0}));const auto statistics=accepted(ob::merge_observations(plan,{}));const ar::Unavailable u{ar::MissingReason::not_instrumented,""};
    ar::RunRecord record{z.identity(),{0,0,0},0,config,{"bad-run"},ar::SkippedFinal{static_cast<ar::SkippedReason>(255)},statistics,{u,u,u,u,true,ar::MemoryAccounting::unlimited},{},{},ar::ProblemProvenance::problem_revalidated};
    CHECK(std::holds_alternative<ar::ArtifactError>(ar::publish_run({z,record})));
    record.final=ar::SkippedFinal{ar::SkippedReason::cancelled};record.resources.actual_threads=ar::Unavailable{static_cast<ar::MissingReason>(255),""};
    CHECK(std::holds_alternative<ar::ArtifactError>(ar::publish_run({z,record})));
}
TEST_CASE("projection declares its exact clock and retains individual task lifetime observations") {
    using namespace execution;using Duration=TimePoint::duration;const TimePoint origin{};
    const auto summary=ob::project_execution({origin,{}, {},{},origin+Duration{7},origin+Duration{8}});
    CHECK(summary.clock.period_numerator==static_cast<std::uint64_t>(Duration::period::num));
    CHECK(summary.clock.period_denominator==static_cast<std::uint64_t>(Duration::period::den));
    CHECK(summary.clock.metric==ar::ClockMetric::steady_wall);CHECK(summary.clock.origin_label=="batch.started_at");
    CHECK(std::get<ar::Available<std::int64_t>>(summary.started).value==0);
    const TaskTiming timing{origin,origin+Duration{1},origin+Duration{2},origin+Duration{3},origin+Duration{4},origin+Duration{6},origin+Duration{7}};
    const auto task=ob::project_task({"task-a"},timing,origin,ar::FailedSpan{"invoke","adapter_exception"});
    CHECK(task.id=="task-a");CHECK(std::get<ar::Available<std::int64_t>>(task.call_started).value==4);
    CHECK(std::get<ar::Available<std::int64_t>>(task.call_finished).value==6);CHECK(std::get<ar::Available<std::int64_t>>(task.released).value==7);
    CHECK(std::get<ar::FailedSpan>(task.status).phase=="invoke");
}
TEST_CASE("published collection rejects forged aggregates and owns optional descriptor metadata") {
    const auto owner=accepted(ar::decode_run(fixture_text()));auto record=owner.description().statistics.description();
    record.buckets[0].observed.value=5;
    CHECK(std::holds_alternative<ar::ArtifactError>(ar::publish_collection(record)));
    record=owner.description().statistics.description();record.buckets[0].inclusive_ticks=ar::Available<std::uint64_t>{48};
    CHECK(std::holds_alternative<ar::ArtifactError>(ar::publish_collection(record)));
    record=owner.description().statistics.description();
    auto producer=std::make_shared<ar::RepresentationSummary>(ar::RepresentationSummary{{"joint"},3,{{"rows","rows",ar::Available<std::uint64_t>{2}}}});
    record.spans[0].descriptor.input_summary=producer;const auto published=accepted(ar::publish_collection(record));producer->dimension=99;
    CHECK(published.description().spans[0].descriptor.input_summary->dimension==3);
}
TEST_CASE("zero detail capacity preserves endpoints while parent and clock boundaries reject contradictions") {
    auto input=plan_input();auto config=input.configuration.description();config.collection.detail_spans=0;config.collection.detail_bytes=0;input.configuration=accepted(ar::resolve_configuration(config));
    const auto plan=accepted(ob::make_collection_plan(input));auto even=accepted(ob::make_observation_shard(plan,{0}));auto odd=accepted(ob::make_observation_shard(plan,{1}));
    for(std::uint64_t i=0;i<4;++i)CHECK((i%2?odd:even).record(completion(i))==ob::RecordDisposition::detail_dropped);
    std::vector<ob::ObservationShard> shards;shards.push_back(std::move(even));shards.push_back(std::move(odd));const auto record=accepted(ob::merge_observations(plan,std::move(shards))).description();
    CHECK(record.buckets[0].detail_dropped.value==4);CHECK(std::get<ar::Available<std::uint64_t>>(record.buckets[0].inclusive_ticks).value==47);
    auto changed_record=record;std::get<ar::TickInterval>(changed_record.spans[3].interval).end=ar::Available<std::int64_t>{50};changed_record.buckets[0].inclusive_ticks=ar::Available<std::uint64_t>{88};
    CHECK(std::holds_alternative<ar::ArtifactError>(ar::publish_collection(changed_record)));
    changed_record.spans[3].descriptor.parent->kind=ar::ParentKind::spawned;CHECK(std::holds_alternative<ar::CollectedStatistics>(ar::publish_collection(changed_record)));
    changed_record=record;changed_record.spans[0].descriptor.parent=ar::SpanParent{{3},ar::ParentKind::spawned};CHECK(std::holds_alternative<ar::ArtifactError>(ar::publish_collection(changed_record)));
    changed_record=record;changed_record.spans[1].descriptor.clock={"foreign-clock"};CHECK(std::holds_alternative<ar::ArtifactError>(ar::publish_collection(changed_record)));
    config.collection.enabled=false;config.collection.detail_bytes=std::numeric_limits<std::uint64_t>::max();config.collection.plan_bytes=std::numeric_limits<std::uint64_t>::max();
    const auto disabled=accepted(ar::resolve_configuration(config));CHECK(std::holds_alternative<ob::CollectionPlan>(ob::make_collection_plan({zero_problem(),disabled,{"disabled"},{},{},0})));
}
TEST_CASE("allocation failure remains an artifact error and does not rewrite owned final data") {
    auto config_input=configuration();std::optional<ar::ArtifactResult<ar::ResolvedConfiguration>> result;bool escaped=false;
    config_input.modules[0].options.push_back({"failure_payload",ar::OptionScalar{std::string(4096,'p')}});
    { allocation_probe::ScopedFailure failure(4096);
    try {result=ar::resolve_configuration(std::move(config_input));}catch(const std::bad_alloc&){escaped=true;}
    }
    CHECK(allocation_probe::injected);
    CHECK_FALSE(escaped);REQUIRE(result.has_value());REQUIRE(std::holds_alternative<ar::ArtifactError>(*result));CHECK(std::get<ar::ArtifactError>(*result).code==ar::ArtifactErrorCode::allocation);
    auto c=configuration();c.collection.enabled=false;const auto config=accepted(ar::resolve_configuration(c));const auto z=zero_problem();
    const auto plan=accepted(ob::make_collection_plan({z,config,{"failure"},{},{},0}));const auto statistics=accepted(ob::merge_observations(plan,{}));const ar::Unavailable u{ar::MissingReason::not_instrumented,""};
    ar::RunRecord record{z.identity(),{0,0,0},0,config,{"failure"},ar::SkippedFinal{ar::SkippedReason::cancelled},statistics,{u,u,u,u,true,ar::MemoryAccounting::unlimited},{},{},ar::ProblemProvenance::problem_revalidated};
    record.resources.actual_threads=ar::Unavailable{ar::MissingReason::not_instrumented,std::string(4096,'m')};
    ar::RunInput input{z,record};std::optional<ar::ArtifactResult<ar::RunStatistics>> output;escaped=false;
    { allocation_probe::ScopedFailure failure(4096);
    try {output=ar::publish_run(std::move(input));}catch(const std::bad_alloc&){escaped=true;}
    }
    CHECK(allocation_probe::injected);
    CHECK_FALSE(escaped);REQUIRE(output.has_value());CHECK(std::get<ar::ArtifactError>(*output).code==ar::ArtifactErrorCode::allocation);
    CHECK(std::get<ar::SkippedFinal>(record.final).reason==ar::SkippedReason::cancelled);
}
TEST_CASE("encoding rejects a byte limit before allocating output or rewriting the owner") {
    const auto owner=accepted(ar::decode_run(fixture_text()));std::optional<ar::ArtifactResult<std::string>> result;bool escaped=false;
    const auto wire_size=accepted(ar::encode_run(owner)).size();
    { allocation_probe::ScopedFailure failure(wire_size);
    try {result=ar::encode_run(owner,{1});}catch(const std::bad_alloc&){escaped=true;}
    }
    CHECK_FALSE(escaped);REQUIRE(result.has_value());REQUIRE(std::holds_alternative<ar::ArtifactError>(*result));
    CHECK(std::get<ar::ArtifactError>(*result).code==ar::ArtifactErrorCode::limit);CHECK_FALSE(allocation_probe::injected);CHECK(allocation_probe::max_size<wire_size);
    CHECK(std::get<ar::SynthesisFinal>(owner.description().final).incumbents[0].witness.original_objective==0);
}
TEST_CASE("versioned content options carry actual owned bytes and computed digest") {
    const std::array<std::byte,3> abc{std::byte{'a'},std::byte{'b'},std::byte{'c'}};const auto snapshot=problem::snapshot_content(abc);REQUIRE(std::holds_alternative<problem::ResolvedContent>(snapshot));
    auto input=configuration();input.modules[0].options.push_back({"content",ar::OptionScalar{ar::ContentOption{"literal.option/1",std::get<problem::ResolvedContent>(snapshot)}}});
    const auto config=accepted(ar::resolve_configuration(input));const auto bytes=config.canonical_bytes();const std::string canonical(reinterpret_cast<const char*>(bytes.data()),bytes.size());
    CHECK(canonical.find("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")!=std::string::npos);
    CHECK(canonical.find("616263")!=std::string::npos);CHECK(canonical.find("literal.option/1")!=std::string::npos);
    CHECK(config.identity().value!="csl.config.v1.sha256:e27f771c2d04bb72827ad27eeaa4123a4df58eaea22aaac4b789ee36033e5abf");
}
TEST_CASE("oversized optional plan metadata is rejected before proportional allocation") {
    auto input=plan_input();input.spans[0].input_summary=std::make_shared<const ar::RepresentationSummary>(ar::RepresentationSummary{{"joint"},1,{{std::string(100000,'x'),"rows",ar::Available<std::uint64_t>{1}}}});
    allocation_probe::max_size=0;allocation_probe::enabled=true;auto result=ob::make_collection_plan(std::move(input));allocation_probe::enabled=false;
    REQUIRE(std::holds_alternative<ar::ArtifactError>(result));CHECK(std::get<ar::ArtifactError>(result).path=="plan.bytes");CHECK(allocation_probe::max_size<=128);
}
TEST_CASE("known not called remains missing elapsed and checked work sums never wrap") {
    auto input=plan_input();input.spans[0].observation_source="fixture.cpp:10";const auto plan=accepted(ob::make_collection_plan(input));auto shard=accepted(ob::make_observation_shard(plan,{0}));
    auto value=completion(0);value.execution=ob::ObservationState::not_called;value.not_called_reason=ar::NotCalledReason::constant_rows_wrapper;
    value.start={false,0,ar::MissingReason::not_exposed_by_adapter};value.end=value.start;CHECK(shard.record(value)==ob::RecordDisposition::retained);
    std::vector<ob::ObservationShard> one;one.push_back(std::move(shard));const auto result=accepted(ob::merge_observations(plan,std::move(one))).description();
    CHECK(result.buckets[0].not_called.value==1);CHECK(result.buckets[0].duration_contributors.value==0);
    CHECK(std::get<ar::Unavailable>(std::get<ar::TickInterval>(result.spans[0].interval).end).reason==ar::MissingReason::not_exposed_by_adapter);
    CHECK(std::get<ar::NotCalledObservation>(result.spans[0].execution).source_location=="fixture.cpp:10");
    auto a=accepted(ob::make_observation_shard(plan,{0}));auto b=accepted(ob::make_observation_shard(plan,{1}));
    for(std::uint64_t id=0;id<4;++id){auto v=completion(id);v.start.value=0;v.end.value=std::numeric_limits<std::int64_t>::max();(void)(id%2?b:a).record(v);}
    std::vector<ob::ObservationShard> both;both.push_back(std::move(a));both.push_back(std::move(b));const auto overflow=accepted(ob::merge_observations(plan,std::move(both))).description();
    CHECK(overflow.buckets[0].duration_contributors.value==4);CHECK(std::get<ar::Unavailable>(overflow.buckets[0].inclusive_ticks).reason==ar::MissingReason::overflow);
}
TEST_CASE("full fixture preserves actual selector batch separately from incumbent witnesses") {
    const auto owner=accepted(ar::decode_run(fixture_text()));REQUIRE(owner.description().selection.has_value());
    const auto& batch=owner.description().selection->batch;CHECK(batch.requested==1);CHECK(batch.selector.value=="first");REQUIRE(batch.witnesses.size()==1);
    CHECK(batch.witnesses[0].controls==std::vector<Vector>{{0},{1}});CHECK(std::get<ar::SynthesisFinal>(owner.description().final).incumbents.size()==2);
    const auto restored=accepted(ar::decode_run(accepted(ar::encode_run(owner))));CHECK(restored.description().selection->diagnostics=="synthetic selector projection");
}
namespace {
problem::ResolvedProblem integrator_problem(){
    Problem p{{"integrator"},std::make_shared<const SystemModel>(SystemModel{{{1,1,0},TimeDomain::discrete,
        LinearStage{{1,1,{1}},{1,1,{1}},{1,0,{}},{0}}},{}}),{0,1,2},KnownInitial{{0}},ContinuousDomain{{UniversalSet{1},UniversalSet{1}}},
        {UniversalSet{1},UniversalSet{1},Singleton{{1}}},{},{},InformationPattern::nominal_open_loop,LinearTerminal{{0},0}};
    auto result=problem::resolve(p,{problem::UncertaintyStructure::stage_product_uncoupled});REQUIRE(std::holds_alternative<problem::ResolvedProblem>(result));return std::get<problem::ResolvedProblem>(result);
}
}
TEST_CASE("scenario publication rejects foreign module stage geometry and invalid event chronology") {
    const auto owner=accepted(ar::decode_run(fixture_text()));const auto problem=integrator_problem();
    auto record=owner.description();auto collected=record.statistics.description();collected.spans[0].descriptor.module.id={"unselected-module"};record.statistics=accepted(ar::publish_collection(collected));
    CHECK(std::holds_alternative<ar::ArtifactError>(ar::publish_run({problem,record})));
    record=owner.description();collected=record.statistics.description();collected.spans[0].descriptor.stage=3;record.statistics=accepted(ar::publish_collection(collected));
    CHECK(std::holds_alternative<ar::ArtifactError>(ar::publish_run({problem,record})));
    record=owner.description();record.execution->completed=ar::Available<std::int64_t>{-1};CHECK(std::holds_alternative<ar::ArtifactError>(ar::publish_run({problem,record})));
    record=owner.description();record.execution->workers_joined=ar::Available<std::int64_t>{9};CHECK(std::holds_alternative<ar::ArtifactError>(ar::publish_run({problem,record})));
    collected=owner.description().statistics.description();collected.spans[0].descriptor.relation_evidence=std::make_shared<const GeometryEvidence>(GeometryEvidence{{{zero_problem().identity(),{"request"},{"reference"}},{{"input"}}},GeometryClaimScope::set_relation,Unestablished{},{},{}});
    CHECK(std::holds_alternative<ar::ArtifactError>(ar::publish_collection(collected)));
}
TEST_CASE("canonical family projection without exporter preserves metadata and evidence") {
    const auto id=zero_problem().identity();
    FamilyIdentity identity{id,{"nominal",id,FamilyTarget::candidate_relaxation,{0,0},Assurance::numerical,{"joint"},{}},{{0,0,0},0},{"joint"},"1",{}};
    CandidateFamily candidate{{identity.coordinates,{"joint"},{}},HeuristicRelationEvidence{"fixture"},Unestablished{}};
    auto published=FamilyPublisher::publish(identity,candidate);REQUIRE(std::holds_alternative<OptimalFamily>(published));
    SynthesisResult result{Termination::completed,{id,MathematicalOutcome::undetermined,Unestablished{},{}},{},std::get<OptimalFamily>(std::move(published)),{},{}};
    const auto projected=ar::project_final(result);REQUIRE(projected.family.has_value());CHECK(std::holds_alternative<ar::FamilyWithoutExporter>(projected.family->payload));
    CHECK(projected.family->family.identity()==identity);
    CHECK(std::holds_alternative<CandidateFamily>(projected.family->family.outcome()));
    CHECK(std::get<HeuristicRelationEvidence>(std::get<CandidateFamily>(projected.family->family.outcome()).relation_to_target).method=="fixture");
    CHECK(std::holds_alternative<ar::Unavailable>(ar::Metric<std::uint64_t>{}));
}
TEST_CASE("artifact publication refuses an unreviewed complete family") {
    auto record=accepted(ar::decode_run(fixture_text())).description();
    auto& final=std::get<ar::SynthesisFinal>(record.final);
    REQUIRE(final.family.has_value());
    const auto identity=final.family->family.identity();
    const auto relation=std::get<CandidateFamily>(final.family->family.outcome()).relation;
    const auto refused=FamilyPublisher::publish(identity,CompleteOptimalFamily{relation,{{identity.problem,Unestablished{}},final.objective},{identity,NumericalCoverageEvidence{"residual-only",identity.request.numerical,{"fixture"},"no coverage review"}},Assurance::numerical});
    REQUIRE(std::holds_alternative<Diagnostics>(refused));
    CHECK(std::any_of(std::get<Diagnostics>(refused).begin(),std::get<Diagnostics>(refused).end(),[](const Diagnostic& d){return d.field=="family.completeness";}));
}
TEST_CASE("unchecked partial optimality cannot enter a published run") {
    auto record=accepted(ar::decode_run(fixture_text())).description();
    auto& final=std::get<ar::SynthesisFinal>(record.final);
    REQUIRE(final.family.has_value());
    const auto relation=std::get<CandidateFamily>(final.family->family.outcome()).relation;
    const ClaimEvidence supported{record.problem,SymbolicArgument{"analytic endpoints","two-step integrator"}};
    const auto rejected=FamilyPublisher::publish(final.family->family.identity(),PartialOptimalFamily{relation,{supported,final.objective},{supported,"direct substitution"},{"two endpoint histories"}});
    REQUIRE(std::holds_alternative<Diagnostics>(rejected));
    CHECK(std::any_of(std::get<Diagnostics>(rejected).begin(),std::get<Diagnostics>(rejected).end(),[](const Diagnostic& d){return d.field=="family.partial.optimality";}));
}
TEST_CASE("candidate feasibility scope survives portable round trips") {
    auto record=accepted(ar::decode_run(fixture_text())).description();
    auto& final=std::get<ar::SynthesisFinal>(record.final);
    REQUIRE(final.family.has_value());
    const auto identity=final.family->family.identity();
    const auto relation=std::get<CandidateFamily>(final.family->family.outcome()).relation;
    const auto support=final.incumbents.front().feasibility;
    const auto witness=final.incumbents.front().witness;
    const std::array<CandidateFeasibility,2> scopes{CandidateFeasibility{RelationFeasibilityEvidence{support}},CandidateFeasibility{WitnessFeasibilityEvidence{witness,support}}};
    for(const auto& feasibility:scopes) {
        auto published=FamilyPublisher::publish(identity,CandidateFamily{relation,HeuristicRelationEvidence{"fixture"},feasibility});
        REQUIRE(std::holds_alternative<OptimalFamily>(published));
        final.family=ar::FamilyRecord{std::get<OptimalFamily>(std::move(published)),ar::FamilyWithoutExporter{}};
        const auto owner=accepted(ar::publish_run({integrator_problem(),record}));
        const auto restored=accepted(ar::decode_run(accepted(ar::encode_run(owner)),integrator_problem()));
        const auto& candidate=std::get<CandidateFamily>(std::get<ar::SynthesisFinal>(restored.description().final).family->family.outcome());
        CHECK(candidate.feasibility.index()==feasibility.index());
        if(const auto* scoped=std::get_if<WitnessFeasibilityEvidence>(&candidate.feasibility))CHECK(scoped->witness.controls==witness.controls);
    }
    const auto unsupported=FamilyPublisher::publish(identity,CandidateFamily{relation,FeasibleCandidateEvidence{support},WitnessFeasibilityEvidence{witness,support}});
    CHECK(std::holds_alternative<Diagnostics>(unsupported));
}
TEST_CASE("contract rejection retains source stop and surviving evidence") {
    auto record=accepted(ar::decode_run(fixture_text())).description();
    auto& final=std::get<ar::SynthesisFinal>(record.final);
    final.termination=Termination::contract_rejected;
    final.outcome.value=MathematicalOutcome::undetermined;
    const RetainedEvidenceScope scope{true,true,final.incumbents.size(),true};
    const ScopedRequestRejection source{{{"generated-query"},"geometry",{"geometry-a"},{},std::optional<ModuleId>{ModuleId{"geometry-a"}},std::optional<std::string>{"1"}},
        {{DiagnosticCode::unsupported,"projection","provider rejected generated request"}}, {},scope};
    final.stop=ContractValidationFailure{{{DiagnosticCode::invalid_claim,"result.family","publisher refused evidence"}},scope,SourceStopEvidence{source}};
    const auto owner=accepted(ar::publish_run({integrator_problem(),record}));
    const auto encoded=accepted(ar::encode_run(owner));
    const auto restored=accepted(ar::decode_run(encoded));
    const auto& result=std::get<ar::SynthesisFinal>(restored.description().final);
    CHECK(result.termination==Termination::contract_rejected);CHECK(result.family.has_value());CHECK(result.incumbents.size()==2);
    const auto& failure=std::get<ContractValidationFailure>(result.stop);
    CHECK(failure.diagnostics.front().field=="result.family");
    CHECK(std::get<ScopedRequestRejection>(failure.source_stop).request.request.value=="generated-query");
    CHECK(std::holds_alternative<ar::ArtifactError>(ar::decode_run(changed(encoded,"contract_validation_failure","unknown_failure"))));
    CHECK(std::holds_alternative<ar::ArtifactError>(ar::decode_run(changed(encoded,"request_rejected","unknown_source"))));
    std::get<ContractValidationFailure>(final.stop).retained.incumbents=0;
    CHECK(std::holds_alternative<ar::ArtifactError>(ar::publish_run({integrator_problem(),record})));
}
TEST_CASE("strategy boundary preserves a candidate through contradictory-status v3 round trip") {
    auto record=accepted(ar::decode_run(fixture_text())).description();
    auto& source=std::get<ar::SynthesisFinal>(record.final);
    REQUIRE(source.family.has_value());
    const auto incumbents_count=source.incumbents.size();
    const auto identity=source.family->family.identity();
    struct Contradictory final:SynthesisWorkspace {
        SynthesisResult result;
        explicit Contradictory(SynthesisResult value):result(std::move(value)){}
        SynthesisResult solve(const problem::ResolvedProblem&,const FamilyRequest&,const ExecutionContext&) override{return result;}
    } workspace{SynthesisResult{Termination::completed,
        {record.problem,MathematicalOutcome::infeasible,SymbolicArgument{"synthetic contradiction","fixture"},{}},
        source.objective,source.family->family,source.incumbents,{}}};
    const auto problem=integrator_problem();
    registry::StrategyRequest request{problem,configuration().strategy,identity.request,identity.strategy_version,{}};
    const ExecutionContext context{std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}}),{}, {},
        identity.request.numerical,"synthetic-v3"};
    auto observed=registry::StrategyPort::run(workspace,request,context);
    REQUIRE(std::holds_alternative<SynthesisResult>(observed));
    const auto& result=std::get<SynthesisResult>(observed);
    CHECK(result.termination==Termination::contract_rejected);
    CHECK(result.outcome.value==MathematicalOutcome::undetermined);
    REQUIRE(result.family.has_value());
    CHECK(result.incumbents.size()==incumbents_count);
    REQUIRE(std::holds_alternative<ContractValidationFailure>(result.stop));
    CHECK(std::get<ContractValidationFailure>(result.stop).retained.partial_or_candidate_family);
    record.final=ar::project_final(result);
    const auto owner=accepted(ar::publish_run({problem,record}));
    const auto restored=accepted(ar::decode_run(accepted(ar::encode_run(owner)),problem));
    const auto& final=std::get<ar::SynthesisFinal>(restored.description().final);
    CHECK(final.outcome.value==MathematicalOutcome::undetermined);
    REQUIRE(final.family.has_value());
    CHECK(final.incumbents.size()==incumbents_count);
    auto illegal=record;
    std::get<ar::SynthesisFinal>(illegal.final).outcome.value=MathematicalOutcome::infeasible;
    CHECK(std::holds_alternative<ar::ArtifactError>(ar::publish_run({problem,illegal})));
}
TEST_CASE("strategy boundary retains a feasible incumbent against a no-family infeasibility claim") {
    auto record=accepted(ar::decode_run(fixture_text())).description();
    const auto& source=std::get<ar::SynthesisFinal>(record.final);
    REQUIRE(source.family.has_value());
    const auto identity=source.family->family.identity();
    const auto incumbents_count=source.incumbents.size();
    struct Contradictory final:SynthesisWorkspace {
        SynthesisResult result;
        explicit Contradictory(SynthesisResult value):result(std::move(value)){}
        SynthesisResult solve(const problem::ResolvedProblem&,const FamilyRequest&,const ExecutionContext&) override{return result;}
    } workspace{SynthesisResult{Termination::completed,
        {record.problem,MathematicalOutcome::infeasible,SymbolicArgument{"synthetic contradiction","fixture"},{}},
        source.objective,{},source.incumbents,{}}};
    const auto problem=integrator_problem();
    registry::StrategyRequest request{problem,configuration().strategy,identity.request,identity.strategy_version,{}};
    const ExecutionContext context{std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}}),{}, {},
        identity.request.numerical,"synthetic-v3-no-family"};
    auto observed=registry::StrategyPort::run(workspace,request,context);
    REQUIRE(std::holds_alternative<SynthesisResult>(observed));
    const auto& result=std::get<SynthesisResult>(observed);
    CHECK(result.termination==Termination::contract_rejected);
    CHECK(result.outcome.value==MathematicalOutcome::undetermined);
    CHECK_FALSE(result.family.has_value());
    CHECK(result.incumbents.size()==incumbents_count);
    REQUIRE(std::holds_alternative<ContractValidationFailure>(result.stop));
    const auto& failure=std::get<ContractValidationFailure>(result.stop);
    CHECK(failure.retained.incumbents==incumbents_count);
    CHECK(std::any_of(failure.diagnostics.begin(),failure.diagnostics.end(),[](const Diagnostic& diagnostic){
        return diagnostic.field=="result.outcome.infeasible";
    }));
    record.selection.reset();
    record.final=ar::project_final(result);
    const auto owner=accepted(ar::publish_run({problem,record}));
    const auto restored=accepted(ar::decode_run(accepted(ar::encode_run(owner)),problem));
    const auto& final=std::get<ar::SynthesisFinal>(restored.description().final);
    CHECK(final.termination==Termination::contract_rejected);
    CHECK(final.outcome.value==MathematicalOutcome::undetermined);
    CHECK_FALSE(final.family.has_value());
    CHECK(final.incumbents.size()==incumbents_count);
    auto illegal=record;
    std::get<ar::SynthesisFinal>(illegal.final).outcome.value=MathematicalOutcome::infeasible;
    CHECK(std::holds_alternative<ar::ArtifactError>(ar::publish_run({problem,illegal})));
}
TEST_CASE("strategy boundary sanitizes contradictory bounds and malformed incumbent histories before v3 publication") {
    const auto problem=integrator_problem();
    for (const int case_id:{0,1,2}) {
        auto record=accepted(ar::decode_run(fixture_text())).description();
        const auto& source=std::get<ar::SynthesisFinal>(record.final);
        REQUIRE(source.family.has_value());
        const auto identity=source.family->family.identity();
        SynthesisResult raw{Termination::completed,
            {record.problem,MathematicalOutcome::undetermined,Unestablished{},{}},
            source.objective,{},source.incumbents,{}};
        if (case_id==0) {
            REQUIRE(raw.objective.lower.has_value());
            raw.objective.lower->value=10;
            raw.objective.upper.reset();
        } else if (case_id==1) {
            raw.incumbents[0].witness.states.pop_back();
        } else {
            REQUIRE(raw.objective.lower.has_value());
            raw.objective.lower->evidence.support=Unestablished{};
        }
        auto illegal=record;
        illegal.selection.reset();
        illegal.final=ar::project_final(raw);
        CHECK(std::holds_alternative<ar::ArtifactError>(ar::publish_run({problem,illegal})));
        struct Fixture final:SynthesisWorkspace {
            SynthesisResult value;
            explicit Fixture(SynthesisResult result):value(std::move(result)){}
            SynthesisResult solve(const problem::ResolvedProblem&,const FamilyRequest&,const ExecutionContext&) override{return value;}
        } workspace{std::move(raw)};
        registry::StrategyRequest request{problem,configuration().strategy,identity.request,identity.strategy_version,{}};
        const ExecutionContext context{std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}}),{}, {},
            identity.request.numerical,"synthetic-v3-evidence"};
        auto observed=registry::StrategyPort::run(workspace,request,context);
        REQUIRE(std::holds_alternative<SynthesisResult>(observed));
        const auto& result=std::get<SynthesisResult>(observed);
        CHECK(result.termination==Termination::contract_rejected);
        if (case_id==1) {
            CHECK(result.incumbents.size()==1);
            REQUIRE(result.objective.lower.has_value());
            CHECK(result.objective.lower->value==0);
        } else {
            CHECK(result.incumbents.size()==2);
            CHECK_FALSE(result.objective.lower.has_value());
        }
        record.selection.reset();
        record.final=ar::project_final(result);
        const auto owner=accepted(ar::publish_run({problem,record}));
        const auto restored=accepted(ar::decode_run(accepted(ar::encode_run(owner)),problem));
        const auto& final=std::get<ar::SynthesisFinal>(restored.description().final);
        CHECK(final.termination==Termination::contract_rejected);
        CHECK(final.objective.lower.has_value()==(case_id==1));
        CHECK(final.incumbents.size()==(case_id==1?1u:2u));
    }
}
TEST_CASE("late request rejection retains bounds incumbent evidence and candidate relation") {
    auto record=accepted(ar::decode_run(fixture_text())).description();
    auto& final=std::get<ar::SynthesisFinal>(record.final);
    final.termination=Termination::operation_rejected;
    final.outcome.value=MathematicalOutcome::undetermined;
    final.stop=ScopedRequestRejection{{{"generated-query"},"geometry",{"geometry-a"},{},std::optional<ModuleId>{ModuleId{"geometry-a"}},std::optional<std::string>{"1"}},
        {{DiagnosticCode::unsupported,"projection","provider rejected generated request"}},
        {},{true,true,final.incumbents.size(),true}};
    const auto owner=accepted(ar::publish_run({integrator_problem(),record}));
    const auto restored=accepted(ar::decode_run(accepted(ar::encode_run(owner)),integrator_problem()));
    const auto& retained=std::get<ar::SynthesisFinal>(restored.description().final);
    CHECK(retained.termination==Termination::operation_rejected);
    CHECK(retained.objective.lower.has_value());CHECK(retained.objective.upper.has_value());
    CHECK(retained.incumbents.size()==2);CHECK(retained.family.has_value());
    CHECK(std::get<ScopedRequestRejection>(retained.stop).request.request.value=="generated-query");
    std::get<ScopedRequestRejection>(final.stop).retained.incumbents=0;
    CHECK(std::holds_alternative<ar::ArtifactError>(ar::publish_run({integrator_problem(),record})));
}
TEST_CASE("family identity and request tampering is rejected on decode") {
    const auto fixture=fixture_text();
    CHECK(std::holds_alternative<ar::ArtifactError>(ar::decode_run(changed(fixture,"\"strategy_version\": \"1\"","\"strategy_version\": \"2\""))));
    CHECK(std::holds_alternative<ar::ArtifactError>(ar::decode_run(changed(fixture,"\"profile\": \"nominal\"","\"profile\": \"\""))));
    CHECK(std::holds_alternative<ar::ArtifactError>(ar::decode_run(changed(fixture,"\"materialization_limit\": null","\"materialization_limit\": \"-1\""))));
    CHECK(std::holds_alternative<ar::ArtifactError>(ar::decode_run(changed(fixture,"\"stop\": {\n        \"kind\": \"none\"","\"stop\": {\n        \"kind\": \"request_rejected\""))));
}
TEST_CASE("resolved auxiliary backend provenance participates in configuration identity") {
    auto c=configuration();c.modules.push_back({"native",{{"native-lp"},"1.11",ar::Unavailable{ar::MissingReason::not_exposed_by_adapter,""}}, {}});
    const auto resolved=accepted(ar::resolve_configuration(c));CHECK(resolved.identity().value!="csl.config.v1.sha256:e27f771c2d04bb72827ad27eeaa4123a4df58eaea22aaac4b789ee36033e5abf");
    CHECK(resolved.description().modules[2].implementation.version=="1.11");
}
TEST_CASE("publication rejects contradictory disabled detail and attachment role states") {
    auto config_input=configuration();config_input.collection.enabled=false;const auto config=accepted(ar::resolve_configuration(config_input));
    const auto plan=accepted(ob::make_collection_plan({zero_problem(),config,{"disabled"},{},{},0}));
    auto disabled=accepted(ob::merge_observations(plan,{})).description();disabled.complete=ar::Available<bool>{true};
    CHECK(std::holds_alternative<ar::ArtifactError>(ar::publish_collection(disabled)));
    const auto owner=accepted(ar::decode_run(fixture_text()));auto collected=owner.description().statistics.description();
    collected.spans[3].detail_state=ar::DetailState::not_requested;
    CHECK(std::holds_alternative<ar::ArtifactError>(ar::publish_collection(collected)));
    auto record=owner.description();record.attachments[0].role=ar::AttachmentRole::diagnostics;
    CHECK(std::holds_alternative<ar::ArtifactError>(ar::publish_run({integrator_problem(),record})));
}
TEST_CASE("derived program final and available pin content options survive an owned round trip") {
    const auto z=zero_problem();auto input=configuration();input.collection.enabled=false;input.output.kind=ar::OutputKind::program;
    input.modules[0].implementation.pin=ar::Available<ar::ModulePin>{{ar::PinScope::source_archive,std::string(64,'a')}};
    const std::array<std::byte,3> bytes{std::byte{'a'},std::byte{'b'},std::byte{'c'}};
    const auto content=std::get<problem::ResolvedContent>(problem::snapshot_content(bytes));
    input.modules[0].options.push_back({"content",ar::OptionScalar{ar::ContentOption{"fixture.option/1",content}}});
    const auto config=accepted(ar::resolve_configuration(input));const auto plan=accepted(ob::make_collection_plan({z,config,{"program"},{},{},0}));
    const auto statistics=accepted(ob::merge_observations(plan,{}));const ProgramIdentity subject{z.identity(),{"derived-program"}};
    const ar::Unavailable unknown{ar::MissingReason::not_instrumented,""};
    ProgramResult result{Termination::cancelled,{subject,MathematicalOutcome::undetermined,Unestablished{},{}},Vector{2},
        {{},ProgramObjectiveBound{4,{subject,Unestablished{},{}}}},"literal raw diagnostic",
        {PrimalResiduals{{subject,{{"fixture-verifier"},"1"},0,0},{0,2},{0,2}},{}}};
    ar::RunRecord record{z.identity(),{0,0,0},0,config,{"program"},ar::project_final(result),statistics,
        {unknown,unknown,unknown,unknown,true,ar::MemoryAccounting::unlimited},{},{},ar::ProblemProvenance::problem_revalidated};
    const auto restored=accepted(ar::decode_run(accepted(ar::encode_run(accepted(ar::publish_run({z,record})))),z));
    const auto& final=std::get<ar::ProgramFinal>(restored.description().final).result;
    CHECK(final.termination==Termination::cancelled);CHECK(final.primal==Vector{2});REQUIRE(final.objective.upper.has_value());CHECK(final.objective.upper->value==4);
    CHECK(final.raw_diagnostics=="literal raw diagnostic");REQUIRE(final.residuals.primal.has_value());CHECK(final.residuals.primal->rows.scale==2);
    const auto& module=restored.description().configuration.description().modules[0];CHECK(std::get<ar::Available<ar::ModulePin>>(module.implementation.pin).value.sha256==std::string(64,'a'));
    const auto& option=std::get<ar::ContentOption>(std::get<ar::OptionScalar>(module.options[0].value));
    CHECK(option.schema=="fixture.option/1");CHECK(problem::hex(option.content.digest())=="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");CHECK(option.content.bytes().size()==3);
}
TEST_CASE("serialized exact Farkas evidence is downgraded until reverified against an LP") {
    const auto source=zero_problem();
    const ProgramIdentity identity{source.identity(),{"constant-row-proof"}};
    const auto program=std::get<LinearProgram>(optimization::make_linear_program({identity,{},0,
        {1,0,{0,0},{},{}},{},{{1,{}}}}));
    const LinearInfeasibilityCertificate certificate{identity,{1},{0},{},{}};
    const auto verified=optimization::verify_linear_infeasibility_certificate(program,certificate);
    REQUIRE(std::holds_alternative<ExactFarkasEvidence>(verified));

    auto input=configuration();input.collection.enabled=false;input.output.kind=ar::OutputKind::program;
    const auto config=accepted(ar::resolve_configuration(input));
    const auto plan=accepted(ob::make_collection_plan({source,config,{"farkas-wire"},{},{},0}));
    const auto statistics=accepted(ob::merge_observations(plan,{}));
    ProgramResult result{Termination::completed,
        {identity,MathematicalOutcome::infeasible,std::get<ExactFarkasEvidence>(verified),{}},
        {},{},"exact certificate",{}};
    const ar::Unavailable unknown{ar::MissingReason::not_instrumented,""};
    ar::RunRecord record{source.identity(),{0,0,0},0,config,{"farkas-wire"},ar::project_final(result),statistics,
        {unknown,unknown,unknown,unknown,true,ar::MemoryAccounting::unlimited},{},{},ar::ProblemProvenance::problem_revalidated};
    const auto published=accepted(ar::publish_run({source,record}));
    const auto encoded=accepted(ar::encode_run(published));
    const auto restored=accepted(ar::decode_run(encoded,source));
    const auto& support=std::get<ar::ProgramFinal>(restored.description().final).result.outcome.support;
    REQUIRE(std::holds_alternative<CertificateReference>(support));
    CHECK(std::get<CertificateReference>(support).verifier=="csl.optimization.farkas-exact.unverified/1");
    CHECK(std::get<CertificateReference>(support).artifact.find("unverified-exact-farkas:")==0);
}
TEST_CASE("wire dictionary references and escaped UTF8 byte limits are checked independently") {
    const auto fixture=fixture_text();
    CHECK(std::holds_alternative<ar::ArtifactError>(ar::decode_run(changed(fixture,"\"task\": \"task\"","\"task\": \"missing-task\""))));
    CHECK(std::holds_alternative<ar::ArtifactError>(ar::decode_run(changed(fixture,"\"operation\": \"solve\"","\"operation\": \"missing-operation\""))));
    const std::string id="csl.problem.v1.sha256:c3eb59c9382beedb7fabcb9682d168f418ae203c34706985de1c7b5d0de9c579";
    constexpr char digits[]="0123456789abcdef";std::string escaped;
    for(const unsigned char c:id){escaped+="\\u00";escaped+=digits[c>>4];escaped+=digits[c&15];}
    CHECK(std::holds_alternative<ar::RunStatistics>(ar::decode_run(fixture,{1000000,1000000,64,86})));
    CHECK(std::holds_alternative<ar::RunStatistics>(ar::decode_run(changed(fixture,id,escaped),{1000000,1000000,64,86})));
    const auto bad_version=ar::decode_run(changed(fixture,"csl.run-statistics/3","csl.run-statistics/9"));
    REQUIRE(std::holds_alternative<ar::ArtifactError>(bad_version));CHECK(std::get<ar::ArtifactError>(bad_version).path=="schema");
    const auto bad_integer=ar::decode_run(changed(fixture,"\"horizon\": \"2\"","\"horizon\": \"02\""));
    REQUIRE(std::holds_alternative<ar::ArtifactError>(bad_integer));CHECK(std::get<ar::ArtifactError>(bad_integer).path=="json.integer");
}
TEST_CASE("canonical relation evidence and requested assurance remain independent portable fields") {
    const auto owner=accepted(ar::decode_run(fixture_text()));
    for(const auto relation:{SetRelation::equivalent,SetRelation::inner,SetRelation::outer,SetRelation::heuristic}){
        auto record=owner.description();auto collected=record.statistics.description();auto& descriptor=collected.spans[0].descriptor;
        descriptor.relation=relation;descriptor.requested_assurance=Assurance::validated;descriptor.applied_assurance=ar::Unavailable{ar::MissingReason::not_supported,"no checked verifier"};
        EvidenceSupport support=relation==SetRelation::heuristic?EvidenceSupport{Unestablished{}}:EvidenceSupport{NumericalCheck{0,0,0,{"literal-verifier"}}};
        descriptor.relation_evidence=std::make_shared<const GeometryEvidence>(GeometryEvidence{{{record.problem,{"request"},{"reference"}},{{"input/left"},{"input/right"}}},GeometryClaimScope::set_relation,support,{},{}});
        record.statistics=accepted(ar::publish_collection(collected));const auto result=accepted(ar::decode_run(accepted(ar::encode_run(accepted(ar::publish_run({integrator_problem(),record}))))));
        const auto& actual=result.description().statistics.description().spans[0].descriptor;
        CHECK(actual.relation==relation);CHECK(actual.requested_assurance==Assurance::validated);CHECK(std::get<ar::Unavailable>(actual.applied_assurance).reason==ar::MissingReason::not_supported);
        REQUIRE(actual.relation_evidence);
        CHECK(actual.relation_evidence->reference.identity.problem==record.problem);
        CHECK(actual.relation_evidence->reference.identity.request==RequestId{"request"});
        CHECK(actual.relation_evidence->reference.identity.ideal_output==ReferenceId{"reference"});
        CHECK(actual.relation_evidence->reference.inputs==std::vector<SetId>{SetId{"input/left"},SetId{"input/right"}});
    }
}
TEST_CASE("pin wire variants are closed and semantic option changes leave mathematics unchanged") {
    const auto fixture=fixture_text();const auto prefix=fixture.find("\"pin\":");REQUIRE(prefix!=std::string::npos);const auto end=fixture.find('}',prefix);REQUIRE(end!=std::string::npos);
    const std::vector<std::string> invalid{
        R"({"state":"unavailable","reason":"local_test"})",
        R"({"state":"unavailable","value":null,"reason":"local_test","detail":""})",
        R"({"state":"unavailable","value":null,"reason":"not_instrumented"})",
        R"({"state":"unavailable","reason":"not_instrumented","detail":""})",
        R"({"state":"unavailable","value":"not-null","reason":"not_instrumented","detail":""})",
        R"({"state":"available","value":{"scope":"source_archive","sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},"reason":"not_instrumented"})",
        R"({"state":"available","value":{"scope":"unknown_scope","sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}})",
        R"({"state":"available","value":{"scope":"source_archive","sha256":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"}})",
        R"({"state":"available","value":{"scope":"source_archive","sha256":"gggggggggggggggggggggggggggggggggggggggggggggggggggggggggggggggg"}})"};
    for(const auto& pin:invalid){auto text=fixture;text.replace(prefix,end-prefix+1,"\"pin\":"+pin);CHECK(std::holds_alternative<ar::ArtifactError>(ar::decode_run(text)));}
    const auto baseline=accepted(ar::resolve_configuration(configuration()));const auto z=zero_problem();
    for(int change=0;change<5;++change){auto c=configuration();
        if(change==0)c.modules[0].implementation.version="2";
        if(change==1)c.modules[0].options.push_back({"presolve",ar::OptionScalar{true}});
        if(change==2)c.output.witnesses.seed=42;
        if(change==3)c.numerical.absolute_tolerance=0.125;
        if(change==4)c.modules[0].implementation.pin=ar::Unavailable{ar::MissingReason::not_exposed_by_adapter,""};
        CHECK(accepted(ar::resolve_configuration(c)).identity()!=baseline.identity());
        CHECK(z.identity().value=="csl.problem.v1.sha256:2320a9f596bfa8f5bdd8aa6d272ca96fe5ff229411b65e1ab3e6f469a27f815e");
    }
}
TEST_CASE("failure publication records explicit diagnostic-reference availability") {
    auto record=accepted(ar::decode_run(fixture_text())).description();
    record.final=ar::FailedFinal{ar::FailurePhase::invoke,ar::FailureReason::adapter_exception,"literal failure"};
    const auto wire=accepted(ar::encode_run(accepted(ar::publish_run({integrator_problem(),record}))));
    CHECK(wire.find("\"raw_diagnostics\":null")!=std::string::npos);
    const auto restored=accepted(ar::decode_run(wire));CHECK(std::get<ar::FailedFinal>(restored.description().final).message=="literal failure");
    std::get<ar::FailedFinal>(record.final).raw_diagnostics=ar::AttachmentId{"raw-diagnostics"};
    const auto attached=accepted(ar::decode_run(accepted(ar::encode_run(accepted(ar::publish_run({integrator_problem(),record}))))));
    REQUIRE(std::get<ar::FailedFinal>(attached.description().final).raw_diagnostics.has_value());
    CHECK(std::get<ar::FailedFinal>(attached.description().final).raw_diagnostics->value=="raw-diagnostics");
    std::get<ar::FailedFinal>(record.final).raw_diagnostics=ar::AttachmentId{"family-relation"};
    CHECK(std::holds_alternative<ar::ArtifactError>(ar::publish_run({integrator_problem(),record})));
}
TEST_CASE("unrepresentable native detail arena is rejected before proportional allocation") {
    auto input=plan_input();auto config=input.configuration.description();config.collection.detail_spans=1;
    config.collection.detail_bytes=static_cast<std::uint64_t>(std::numeric_limits<std::ptrdiff_t>::max())+1;
    input.configuration=accepted(ar::resolve_configuration(config));input.shard_count=1;for(auto& span:input.spans)span.shard=0;
    allocation_probe::max_size=0;allocation_probe::enabled=true;auto result=ob::make_collection_plan(std::move(input));allocation_probe::enabled=false;
    REQUIRE(std::holds_alternative<ar::ArtifactError>(result));CHECK(std::get<ar::ArtifactError>(result).path=="plan.bytes");CHECK(allocation_probe::max_size<=128);
}
TEST_CASE("backend program and representation metadata own independent aliases through round trip") {
    auto record=accepted(ar::decode_run(fixture_text())).description();auto config=record.configuration.description();
    ar::ModuleIdentity native{{"literal-native"},"fixture-1",ar::Unavailable{ar::MissingReason::not_instrumented,"synthetic test provenance"}};
    config.modules.push_back({"native",native,{}});record.configuration=accepted(ar::resolve_configuration(config));
    auto collected=record.statistics.description();collected.configuration=record.configuration.identity();
    auto backend=std::make_shared<ar::ModuleIdentity>(native);auto program=std::make_shared<ProgramIdentity>(ProgramIdentity{record.problem,{"literal-derived"}});
    auto representation=std::make_shared<RepresentationId>(RepresentationId{"literal-input"});
    collected.spans[3].descriptor.backend=backend;collected.spans[3].descriptor.program=program;collected.spans[3].descriptor.input_representation=representation;
    record.statistics=accepted(ar::publish_collection(collected));backend->version="mutated";program->program.value="mutated";representation->value="mutated";
    const auto restored=accepted(ar::decode_run(accepted(ar::encode_run(accepted(ar::publish_run({integrator_problem(),record}))))));
    const auto& span=restored.description().statistics.description().spans[3].descriptor;
    REQUIRE(span.backend);REQUIRE(span.program);REQUIRE(span.input_representation);
    CHECK(span.backend->id.value=="literal-native");CHECK(span.backend->version=="fixture-1");CHECK(span.program->program.value=="literal-derived");CHECK(span.input_representation->value=="literal-input");
}

TEST_CASE("review F1 run binding is admitted before proportional plan copies") {
    auto input=plan_input();input.run.value=std::string(100000,'r');
    allocation_probe::max_size=0;allocation_probe::enabled=true;
    const auto result=ob::make_collection_plan(std::move(input));allocation_probe::enabled=false;
    CHECK(allocation_probe::max_size<=128);
    REQUIRE(std::holds_alternative<ar::ArtifactError>(result));
    CHECK(std::get<ar::ArtifactError>(result).code==ar::ArtifactErrorCode::limit);
    CHECK(std::get<ar::ArtifactError>(result).path=="plan.bytes");
}
TEST_CASE("review F2 direct collection admission rejects zero budget before cloning") {
    auto record=accepted(ar::decode_run(fixture_text())).description().statistics.description();
    record.settings.plan_bytes=0;
    allocation_probe::max_size=0;allocation_probe::enabled=true;
    const auto result=ar::publish_collection(std::move(record));allocation_probe::enabled=false;
    CHECK(allocation_probe::max_size<=128);
    REQUIRE(std::holds_alternative<ar::ArtifactError>(result));
    CHECK(std::get<ar::ArtifactError>(result).code==ar::ArtifactErrorCode::limit);
    CHECK(std::get<ar::ArtifactError>(result).path=="collection.plan_bytes");
}
TEST_CASE("review F2 independently resealed wire cannot bypass the metadata budget") {
    auto text=fixture_text();
    for(int i=0;i<2;++i)text=changed(std::move(text),"\"plan_bytes\": \"4096\"","\"plan_bytes\": \"0\"");
    constexpr auto before="csl.config.v1.sha256:e27f771c2d04bb72827ad27eeaa4123a4df58eaea22aaac4b789ee36033e5abf";
    constexpr auto after="csl.config.v1.sha256:bb7967e0a8bbfc7bd8acefb5395659c1e096b97817c23b0fda101d0cbef341cf";
    for(int i=0;i<2;++i)text=changed(std::move(text),before,after);
    const auto result=ar::decode_run(text);
    REQUIRE(std::holds_alternative<ar::ArtifactError>(result));
    CHECK(std::get<ar::ArtifactError>(result).code==ar::ArtifactErrorCode::limit);
    CHECK(std::get<ar::ArtifactError>(result).path=="collection.plan_bytes");
}
TEST_CASE("review F2 large retained summary text is rejected before its clone") {
    auto record=accepted(ar::decode_run(fixture_text())).description().statistics.description();
    record.spans[0].descriptor.input_summary=std::make_shared<const ar::RepresentationSummary>(ar::RepresentationSummary{{"joint"},1,{{std::string(100000,'q'),"rows",ar::Available<std::uint64_t>{1}}}});
    allocation_probe::max_size=0;allocation_probe::enabled=true;
    const auto result=ar::publish_collection(std::move(record));allocation_probe::enabled=false;
    CHECK(allocation_probe::max_size<=128);
    REQUIRE(std::holds_alternative<ar::ArtifactError>(result));
    CHECK(std::get<ar::ArtifactError>(result).code==ar::ArtifactErrorCode::limit);
    CHECK(std::get<ar::ArtifactError>(result).path=="collection.plan_bytes");
}
TEST_CASE("review F3 legacy projection keeps the active incomplete alternative") {
    const auto result=accepted(ar::project_legacy_span({9,{}, {"lp-a"},0.125,0.375},plan_input().spans[0]));
    CHECK(result.descriptor.id.value==9);CHECK_FALSE(result.descriptor.parent);
    CHECK(std::get<ar::LegacySecondsInterval>(result.interval).start==0.125);
    CHECK(std::get<ar::LegacySecondsInterval>(result.interval).end==0.375);
    CHECK(std::holds_alternative<ar::UnknownObservation>(result.execution));
    CHECK(std::holds_alternative<ar::IncompleteSpan>(result.status));CHECK_FALSE(result.completion_observed);
    CHECK(result.detail_state==ar::DetailState::not_observed);
    CHECK(std::get<ar::Unavailable>(result.termination).reason==ar::MissingReason::not_instrumented);
    CHECK(std::get<ar::Unavailable>(result.iterations).reason==ar::MissingReason::not_instrumented);
    CHECK(std::get<ar::Unavailable>(result.detail).reason==ar::MissingReason::not_instrumented);
}

TEST_CASE("review F2 portable metadata boundary is independent of native object sizes") {
    const auto z=zero_problem();
    // Three framed bindings: (8+86)+(8+85)+(8+1)=196 bytes.
    // Settings34, five empty array counts40, available completeness2: total272.
    for(const std::uint64_t cap:{272U,271U}) {
        auto c=configuration();c.collection={true,ar::CollectionMode::detail,0,cap,0,0};
        const auto config=accepted(ar::resolve_configuration(c));
        ar::CollectionRecord record{z.identity(),config.identity(),{"r"},c.collection,{},{},{},ar::Available<bool>{true}};
        const auto result=ar::publish_collection(std::move(record));
        if(cap==272)CHECK(std::holds_alternative<ar::CollectedStatistics>(result));
        else {REQUIRE(std::holds_alternative<ar::ArtifactError>(result));CHECK(std::get<ar::ArtifactError>(result).code==ar::ArtifactErrorCode::limit);}
    }
    auto c=configuration();c.collection={true,ar::CollectionMode::summary,std::numeric_limits<std::uint64_t>::max(),272,std::numeric_limits<std::uint64_t>::max(),std::numeric_limits<std::uint64_t>::max()};
    const auto config=accepted(ar::resolve_configuration(c));
    ar::CollectionRecord record{z.identity(),config.identity(),{"r"},c.collection,{},{},{},ar::Available<bool>{true}};
    CHECK(std::holds_alternative<ar::CollectedStatistics>(ar::publish_collection(record)));
    record.run.value="\xc3\xa9";CHECK(std::holds_alternative<ar::ArtifactError>(ar::publish_collection(record)));
    record.settings.plan_bytes=273;CHECK(std::holds_alternative<ar::CollectedStatistics>(ar::publish_collection(record)));
}
TEST_CASE("review budgets retain disabled dormant settings and reject real native extent overflow") {
    auto c=configuration();c.collection={false,ar::CollectionMode::detail,0,0,0,std::numeric_limits<std::uint64_t>::max()};
    const auto config=accepted(ar::resolve_configuration(c));
    const auto plan=accepted(ob::make_collection_plan({zero_problem(),config,{"disabled-zero"},{},{},0}));
    const auto record=accepted(ob::merge_observations(plan,{}));CHECK(record.description().settings==c.collection);
    CHECK(std::get<ar::Unavailable>(record.description().complete).reason==ar::MissingReason::collection_disabled);
    auto input=plan_input();input.shard_count=std::numeric_limits<std::uint64_t>::max();
    allocation_probe::max_size=0;allocation_probe::enabled=true;const auto result=ob::make_collection_plan(std::move(input));allocation_probe::enabled=false;
    CHECK(allocation_probe::max_size<=128);REQUIRE(std::holds_alternative<ar::ArtifactError>(result));CHECK(std::get<ar::ArtifactError>(result).code==ar::ArtifactErrorCode::limit);
}

TEST_CASE("review dormant zero caps do not admit hidden disabled metadata") {
    auto c=configuration();c.collection={false,ar::CollectionMode::summary,0,0,0,0};
    const auto config=accepted(ar::resolve_configuration(c));
    ar::CollectionRecord record{zero_problem().identity(),config.identity(),{"disabled"},c.collection,{},{},{},ar::Unavailable{ar::MissingReason::collection_disabled,std::string(100000,'h')}};
    allocation_probe::max_size=0;allocation_probe::enabled=true;const auto result=ar::publish_collection(std::move(record));allocation_probe::enabled=false;
    CHECK(allocation_probe::max_size<=128);REQUIRE(std::holds_alternative<ar::ArtifactError>(result));
    CHECK(std::get<ar::ArtifactError>(result).path=="collection.disabled");
}

TEST_CASE("v4 selection preserves direction tolerance and raw distinct counts") {
    auto record=accepted(ar::decode_run(fixture_text())).description();
    auto config=record.configuration.description(); config.output.witnesses={2,0.25,{{1,-1},{-1,1},{1,-1}},17};
    record.configuration=accepted(ar::resolve_configuration(config));
    auto& batch=record.selection->batch; batch.requested=2; batch.seed=17;
    batch.directions=config.output.witnesses.directions; batch.distinctness_tolerance=0.25;
    auto first=batch.witnesses.front(); auto second=first;
    second.states[1][0]+=1; second.controls[0][0]+=1;
    batch.witnesses={first,second,first};
    auto collection=record.statistics.description(); collection.configuration=record.configuration.identity();
    record.statistics=accepted(ar::publish_collection(collection));
    auto published=accepted(ar::publish_run({integrator_problem(),record}));
    auto encoded=accepted(ar::encode_run(published));
    CHECK(encoded.find("csl.run-statistics/4")!=std::string::npos);
    auto decoded=accepted(ar::decode_run(encoded)); const auto& restored=decoded.description().selection->batch;
    CHECK(restored.directions==std::vector<Vector>{{1,-1},{-1,1},{1,-1}});
    CHECK(restored.distinctness_tolerance==0.25); CHECK(restored.returned_count()==3); CHECK(restored.distinct_count()==2);
}

TEST_CASE("historical v2 and v3 migrate nondefault recorded query facts and source identity") {
    for(const bool v2:{true,false}) {
        // Alter owning copies only; the archival fixture bytes remain unchanged.
        auto legacy=nlohmann::json::parse(v2?fixture_v2_text():fixture_text());
        const auto original=accepted(ar::decode_run(legacy.dump()));
        auto config=original.description().configuration.description();
        config.output.witnesses.directions={{1,-1},{-1,1}};
        config.output.witnesses.distinctness_tolerance=0.125;
        const auto resolved=accepted(ar::resolve_configuration(config));
        legacy["configuration"]["id"]=resolved.identity().value;
        legacy["configuration"]["value"]["output"]["directions"]=nlohmann::json::array({nlohmann::json::array({"3ff0000000000000","bff0000000000000"}),nlohmann::json::array({"bff0000000000000","3ff0000000000000"})});
        legacy["configuration"]["value"]["output"]["distinctness_bits"]="3fc0000000000000";
        legacy["statistics"]["configuration"]=resolved.identity().value;
        legacy["selection"]["batch"]["source_family"]=legacy["final"]["value"]["family"]["family"]["identity"];
        const auto expected_source=std::get<ar::SynthesisFinal>(original.description().final).family->family.identity();
        const auto migrated=accepted(ar::decode_run(legacy.dump()));
        const auto& batch=migrated.description().selection->batch;
        CHECK(batch.directions==std::vector<Vector>{{1,-1},{-1,1}});
        CHECK(batch.distinctness_tolerance==0.125);CHECK(batch.source_family==expected_source);
        CHECK(batch.returned_count()==1);CHECK(batch.distinct_count()==1);
        const auto encoded=accepted(ar::encode_run(migrated));
        CHECK(encoded.find("csl.run-statistics/4")!=std::string::npos);
        const auto restored=accepted(ar::decode_run(encoded));const auto& restored_batch=restored.description().selection->batch;
        CHECK(restored_batch.directions==batch.directions);CHECK(restored_batch.distinctness_tolerance==0.125);
        CHECK(restored_batch.source_family==expected_source);CHECK(restored_batch.returned_count()==1);
    }
}
