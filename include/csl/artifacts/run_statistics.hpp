#pragma once
#include <csl/problem/validator.hpp>
#include <cstdint>
#include <string_view>

namespace csl::artifacts {
enum class ArtifactErrorCode { invalid_input, unsupported, limit, identity, reference, allocation };
struct ArtifactError { ArtifactErrorCode code; std::string path, message; };
template<class T> using ArtifactResult = std::variant<T,ArtifactError>;
enum class MissingReason { not_requested, not_instrumented, not_supported, not_exposed_by_adapter,
    execution_unknown, incomplete_span, clock_unavailable, clock_mismatch, overflow, detail_limit,
    collection_disabled, not_applicable };
struct Unavailable { MissingReason reason; std::string detail; };
template<class T> struct Available { T value; };
template<class T> using Metric = std::variant<Unavailable,Available<T>>;
enum class PinScope { source_archive, build_manifest };
struct ModulePin { PinScope scope; std::string sha256; };
using PinAvailability = Metric<ModulePin>;
struct ModuleIdentity { ModuleId id; std::string version; PinAvailability pin; };
struct ContentOption {std::string schema;problem::ResolvedContent content;};
using OptionScalar = std::variant<bool,std::int64_t,std::uint64_t,double,std::string,std::vector<std::byte>,ContentOption>;
using OptionValue = std::variant<OptionScalar,std::vector<OptionScalar>>;
struct NamedOption { std::string name; OptionValue value; };
struct ModuleConfiguration { std::string role; ModuleIdentity implementation; std::vector<NamedOption> options; };
struct SelectorConfiguration { ModuleId id; std::string version; std::vector<NamedOption> options; };
enum class CollectionMode { detail, summary };
struct CollectionSettings {
    bool enabled; CollectionMode mode;
    std::uint64_t plan_spans, plan_bytes, detail_spans, detail_bytes;
    bool operator==(const CollectionSettings&) const = default;
};
enum class OutputKind { synthesis, program };
struct OutputRequest {
    OutputKind kind; Assurance assurance; FamilyTarget family;
    RepresentationId representation; WitnessRequest witnesses;
};
enum class WorkspacePolicy { fresh, reused };
struct DeadlineBudget { std::int64_t ticks; std::uint64_t period_numerator,period_denominator; };
struct ConfigurationInput {
    CollectionSettings collection{};
    std::vector<ModuleConfiguration> modules;
    NumericalPolicy numerical{};
    ResourcePolicy resources{};
    OutputRequest output{};
    SelectorConfiguration selector;
    std::optional<DeadlineBudget> deadline_budget;
    StrategyConfiguration strategy;
    WorkspacePolicy workspace{};
};
struct ConfigId { std::string value; bool operator==(const ConfigId&) const = default; };
struct ArtifactAccess;
class ResolvedConfiguration {
public:
    ResolvedConfiguration(const ResolvedConfiguration&) = default;
    ResolvedConfiguration& operator=(const ResolvedConfiguration&) = default;
    const ConfigId& identity() const noexcept;
    const ConfigurationInput& description() const noexcept;
    std::span<const std::byte> canonical_bytes() const noexcept;
private:
    struct Storage;
    std::shared_ptr<const Storage> storage_;
    explicit ResolvedConfiguration(std::shared_ptr<const Storage>);
    friend struct ArtifactAccess;
};
ArtifactResult<ResolvedConfiguration> resolve_configuration(ConfigurationInput);

struct RunId { std::string value; bool operator==(const RunId&) const = default; };
struct SpanId { std::uint64_t value; bool operator==(const SpanId&) const = default; };
struct ClockId { std::string value; bool operator==(const ClockId&) const = default; };
enum class ClockMetric { steady_wall, thread_cpu, process_cpu };
struct ClockDomain {
    ClockId id; ClockMetric metric; std::string scope;
    std::uint64_t period_numerator,period_denominator;
    Metric<std::uint64_t> resolution_ticks;
    std::string origin_label;
    Metric<std::string> calibration{Unavailable{MissingReason::not_instrumented,{}}};
};
struct TickInterval { Metric<std::int64_t> start,end; };
struct LegacySecondsInterval { double start,end; };
using SpanInterval=std::variant<TickInterval,LegacySecondsInterval>;
Metric<std::uint64_t> elapsed_ticks(const TickInterval&) noexcept;
enum class ParentKind { nested, spawned };
struct SpanParent { SpanId id; ParentKind kind; };
enum class ExecutionObservation { observed_return, known_not_called, unknown };
enum class NotCalledReason { capability_rejected, task_not_admitted, before_public_entry,
    explicit_pre_entry_stop, constant_rows_wrapper, stopped_before_phase_call,
    earlier_phase_exit, invalid_qp_start, route_not_selected };
struct ReturnedObservation {};
struct NotCalledObservation { NotCalledReason reason; std::string source_location,source_version; };
struct UnknownObservation {};
using CallObservation=std::variant<ReturnedObservation,NotCalledObservation,UnknownObservation>;
struct RepresentationSize { std::string quantity,unit; Metric<std::uint64_t> value; };
struct RepresentationSummary {
    RepresentationId representation; std::uint64_t dimension;
    std::vector<RepresentationSize> sizes;
};
struct SpanDescriptor {
    SpanId id; std::optional<SpanParent> parent;
    std::uint64_t shard,bucket; std::string task,operation;
    ModuleIdentity module; std::shared_ptr<const ModuleIdentity> backend;
    ClockId clock; std::shared_ptr<const ProgramIdentity> program;
    std::optional<std::uint64_t> stage,query;
    std::shared_ptr<const RepresentationId> input_representation,output_representation;
    std::optional<std::uint64_t> input_size,output_size;
    Assurance requested_assurance; Metric<Assurance> applied_assurance;
    std::optional<SetRelation> relation;
    std::shared_ptr<const GeometryEvidence> relation_evidence;
    std::shared_ptr<const RepresentationSummary> input_summary,output_summary;
    std::string observation_source;
};
struct IncompleteSpan {};
struct ReturnedSpan { Termination termination; Metric<MathematicalOutcome> outcome; };
struct RejectedSpan { std::string reason; };
struct SkippedSpan { std::string reason; };
struct FailedSpan { std::string phase,reason; };
using SpanStatus=std::variant<IncompleteSpan,ReturnedSpan,RejectedSpan,SkippedSpan,FailedSpan>;
enum class DetailState { not_observed, retained, capacity_dropped, rejected, not_requested };
struct SpanRecord {
    SpanDescriptor descriptor; SpanInterval interval; CallObservation execution{UnknownObservation{}};
    Metric<Termination> termination; Metric<std::uint64_t> iterations;
    Metric<std::string> detail;
    SpanStatus status{IncompleteSpan{}};
    bool completion_observed{false};
    DetailState detail_state{DetailState::not_observed};
};
struct ExactCount { std::uint64_t value{}; bool exact{true}; };
struct BucketSummary {
    std::uint64_t id; ClockId clock;
    ExactCount observed,detail_dropped,duplicate,wrong_shard,declared_overflow;
    ExactCount duration_contributors;
    Metric<std::uint64_t> inclusive_ticks;
    ExactCount failed,not_called,unknown,incomplete;
};
struct CollectionRecord {
    ProblemId problem; ConfigId configuration; RunId run;
    CollectionSettings settings; std::vector<ClockDomain> clocks;
    std::vector<SpanRecord> spans; std::vector<BucketSummary> buckets;
    Metric<bool> complete;
    std::vector<std::string> tasks{},operations{};
};
class CollectedStatistics {
public:
    CollectedStatistics(const CollectedStatistics&)=default;
    CollectedStatistics& operator=(const CollectedStatistics&)=default;
    const CollectionRecord& description() const noexcept;
private:
    std::shared_ptr<const CollectionRecord> storage_;
    explicit CollectedStatistics(std::shared_ptr<const CollectionRecord>);
    friend struct ArtifactAccess;
};
// Also used to check decoded records; successful publication never grants a live collector token.
ArtifactResult<CollectedStatistics> publish_collection(CollectionRecord);

struct AttachmentId { std::string value; bool operator==(const AttachmentId&) const = default; };
enum class AttachmentRole { diagnostics, family, certificate, profiler };
struct Attachment {
    AttachmentId id; AttachmentRole role; problem::ContentDigest digest;
    std::uint64_t byte_count; std::string media_type,schema;
    std::optional<std::string> relative_path;
    std::optional<problem::ResolvedContent> content;
};
struct ExternalFamilyPayload { AttachmentId attachment; };
struct FamilyWithoutExporter {};
using FamilyPayload=std::variant<ExternalFamilyPayload,FamilyWithoutExporter>;
struct FamilyRecord {
    ProblemId problem; JointCoordinates coordinates; RepresentationId representation;
    FamilyTarget target; FamilyEvidence evidence; FamilyPayload payload;
};
struct SynthesisFinal {
    Termination termination; SynthesisOutcomeClaim outcome; ObjectiveEvidence objective;
    std::optional<FamilyRecord> family; std::vector<Witness> incumbents;
};
struct ProgramFinal { ProgramResult result; std::optional<AttachmentId> raw_diagnostics; };
struct UnsupportedFinal { Diagnostics diagnostics; };
enum class SkippedReason { cancelled, deadline, task_limit, reservation_exceeds_budget, batch_failed };
struct SkippedFinal { SkippedReason reason; };
enum class FailurePhase { create, invoke, launch, publication };
enum class FailureReason { allocation, adapter_exception, thread_launch };
struct FailedFinal { FailurePhase phase; FailureReason reason; std::string message; std::optional<AttachmentId> raw_diagnostics{}; };
using FinalOutcome=std::variant<SynthesisFinal,ProgramFinal,UnsupportedFinal,SkippedFinal,FailedFinal>;
SynthesisFinal project_final(const SynthesisResult&,std::optional<AttachmentId> family_attachment={});
ProgramFinal project_final(const ProgramResult&,std::optional<AttachmentId> diagnostics={});
ArtifactResult<SpanRecord> project_legacy_span(const TimingSpan&,SpanDescriptor);

enum class AdmissionCause { cancelled, deadline, task_limit, allocation, adapter_exception, thread_launch };
struct AdmissionObservation { AdmissionCause cause; Metric<std::int64_t> at; };
struct ExecutionSummary {
    Metric<std::int64_t> configured_deadline;
    std::optional<AdmissionObservation> admission_closed;
    Metric<std::int64_t> external_cancellation,workers_joined,completed;
    ClockDomain clock;
    Metric<std::int64_t> started;
    struct Task {
        std::string id;
        Metric<std::int64_t> queued,admitted,create_started,create_finished,call_started,call_finished,released;
        SpanStatus status;
    };
    std::vector<Task> tasks;
};
enum class MemoryAccounting { unlimited, active_reservations };
struct ResourceObservation {
    Metric<std::uint64_t> peak_active_tasks,peak_reserved_threads,peak_reserved_bytes,actual_threads;
    bool outer_admission_enforced;
    MemoryAccounting memory;
};
enum class ProblemProvenance { problem_revalidated, identity_recorded };
struct RunRecord {
    ProblemId problem; Dimensions dimensions; std::uint64_t horizon;
    ResolvedConfiguration configuration; RunId run; FinalOutcome final;
    CollectedStatistics statistics; ResourceObservation resources;
    std::optional<ExecutionSummary> execution; std::vector<Attachment> attachments;
    ProblemProvenance provenance;
    std::optional<WitnessSelection> selection{};
};
struct RunInput { problem::ResolvedProblem problem; RunRecord record; };
class RunStatistics {
public:
    RunStatistics(const RunStatistics&)=default;
    RunStatistics& operator=(const RunStatistics&)=default;
    const RunRecord& description() const noexcept;
private:
    struct Storage;
    std::shared_ptr<const Storage> storage_;
    explicit RunStatistics(std::shared_ptr<const Storage>);
    friend struct ArtifactAccess;
};
struct DecodeLimits {
    std::uint64_t bytes{16*1024*1024},nodes{1000000},depth{64},string_bytes{1024*1024};
};
struct EncodeLimits { std::uint64_t bytes{16*1024*1024}; };
ArtifactResult<RunStatistics> publish_run(RunInput);
ArtifactResult<RunStatistics> decode_run(std::string_view,DecodeLimits={});
ArtifactResult<RunStatistics> decode_run(std::string_view,const problem::ResolvedProblem&,DecodeLimits={});
ArtifactResult<std::string> encode_run(const RunStatistics&,EncodeLimits={});
}
