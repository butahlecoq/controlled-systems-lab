#pragma once

#include <chrono>
#include <cstddef>
#include <memory>
#include <optional>
#include <stop_token>
#include <string>
#include <variant>
#include <vector>

namespace csl {
// Revision 1.1. This is a source contract, not a stable binary ABI.
struct ProblemId { std::string value; bool operator==(const ProblemId&) const = default; };
struct ProgramId { std::string value; bool operator==(const ProgramId&) const = default; };
struct ProgramIdentity { ProblemId problem; ProgramId program; bool operator==(const ProgramIdentity&) const = default; };
struct SetId { std::string value; bool operator==(const SetId&) const = default; };
struct RequestId { std::string value; bool operator==(const RequestId&) const = default; };
struct ReferenceId { std::string value; bool operator==(const ReferenceId&) const = default; };
struct ModuleId { std::string value; };
struct RepresentationId { std::string value; };
struct StageIndex { std::size_t value; };
struct Dimensions { std::size_t state, control, external; };
using Vector = std::vector<double>;
// Owning row-major buffer. Empty rows/columns are legal; shape validated at entry.
struct Matrix { std::size_t rows, cols; Vector values; };
struct SparseMatrix {
    std::size_t rows, cols;
    std::vector<std::size_t> row_offsets, column_indices; // CSR, sorted columns
    Vector values;
};
struct Interval { std::optional<double> lower, upper; }; // null means infinite
struct LinearStage { Matrix A, B, E; Vector offset; };
using Coefficients = std::variant<LinearStage, std::vector<LinearStage>>;
enum class TimeDomain { discrete, continuous };
struct Dynamics { Dimensions dimensions; TimeDomain time_domain; Coefficients stages; };
enum class ObservationTiming { before_decision, after_decision };
struct Observation { Matrix state_map, control_map, error_map; Vector offset; ObservationTiming timing; };
struct SystemModel { Dynamics dynamics; std::vector<Observation> observations; };

enum class SetProperty { unknown, yes, no };
struct SetMetadata {
    std::size_t dimension;
    RepresentationId representation;
    SetProperty convex, polyhedral, bounded;
};
class SetPayload { public: virtual ~SetPayload() = default; };
struct SetHandle { SetMetadata metadata; std::shared_ptr<const SetPayload> payload; SetId id; };
struct EmptySet { std::size_t dimension; };
struct UniversalSet { std::size_t dimension; };
struct Singleton { Vector point; };
using AdmissibleSet = std::variant<EmptySet, UniversalSet, Singleton, SetHandle>;
struct ContinuousDomain { std::vector<AdmissibleSet> stages; };
struct FiniteDomain { std::vector<Vector> catalogue; };
struct MixedDomain { ContinuousDomain continuous; FiniteDomain discrete; };
using ControlDomain = std::variant<ContinuousDomain, FiniteDomain, MixedDomain>;
struct LinearTerminal { Vector coefficients; double offset; };
struct QuadraticTerminal { Matrix Q; Vector linear; double offset; }; // 1/2 x'Qx+q'x+c
struct ResidualNormTerminal { Matrix map; Vector target; }; // ||Lx-r||_2, rectangular L
using TerminalObjective = std::variant<LinearTerminal, QuadraticTerminal, ResidualNormTerminal>;
struct TemporalConstraints { SparseMatrix joint_map; std::vector<Interval> bounds; };
struct KnownInitial { Vector point; };
struct InitialSet { AdmissibleSet set; };
enum class InformationPattern { nominal_open_loop, feedback };
struct Problem {
    ProblemId id;
    std::shared_ptr<const SystemModel> model;
    std::vector<double> times; // T+1 strictly increasing; controls indexed [0,T)
    std::variant<KnownInitial, InitialSet> initial;
    ControlDomain controls;
    std::vector<AdmissibleSet> states; // T+1; use UniversalSet explicitly
    std::optional<TemporalConstraints> temporal;
    std::optional<AdmissibleSet> external;
    InformationPattern information;
    TerminalObjective objective;
};

enum class DiagnosticCode { invalid_input, unsupported, evidence_mismatch, invalid_claim };
struct Diagnostic { DiagnosticCode code; std::string field, explanation; };
using Diagnostics = std::vector<Diagnostic>;
enum class Assurance { numerical, validated };
struct Unestablished {};
struct NumericalCheck { double absolute_tolerance, relative_tolerance, max_residual; ModuleId verifier; };
struct SymbolicArgument { std::string reference, assumptions; };
struct CertificateReference { std::string artifact, verifier; }; // Unchecked reference, NOT validated evidence.
using EvidenceSupport = std::variant<Unestablished, NumericalCheck, SymbolicArgument, CertificateReference>;
struct ClaimEvidence { ProblemId problem; EvidenceSupport support; };
struct FamilyEvidence { ClaimEvidence feasibility, optimality, completeness; };
enum class SetRelation { equivalent, inner, outer, heuristic };
struct GeometryRequestIdentity {
    ProblemId problem;
    RequestId request; // identifies the complete immutable request, including operands
    ReferenceId ideal_output; // exact mathematical set, support value or containment proposition
    bool operator==(const GeometryRequestIdentity&) const = default;
};
struct GeometryReference {
    GeometryRequestIdentity identity;
    std::vector<SetId> inputs; // ordered, extracted from operation operands
    bool operator==(const GeometryReference&) const = default;
};
enum class GeometryClaimScope { set_relation, support_value, containment };
struct GeometryErrorBound { ModuleId metric; double bound; std::string units; };
struct GeometryEvidence {
    GeometryReference reference;
    GeometryClaimScope scope;
    EvidenceSupport support;
    std::vector<std::string> assumptions;
    std::optional<GeometryErrorBound> error_bound; // justified only by this claim's support
};
struct AffineImage { SetHandle input; Matrix map; Vector offset; }; // y=Mx+b
struct MinkowskiSum { SetHandle left, right; };
struct Intersection { SetHandle left, right; };
struct Projection { SetHandle input; std::vector<std::size_t> coordinates; }; // ordered zero-based indices
struct AffinePreimage { SetHandle target; Matrix map; Vector offset; }; // {x: Mx+b in target}
struct SupportQuery { SetHandle input; Vector direction; }; // sup d'x
struct ContainmentQuery { SetHandle subset, superset; };
using GeometryOperation = std::variant<AffineImage, MinkowskiSum, Intersection, Projection,
    AffinePreimage, SupportQuery, ContainmentQuery>;
struct OperationRequest {
    GeometryRequestIdentity identity;
    ModuleId implementation;
    GeometryOperation operation;
    SetRelation required_relation; // set-valued operations only; query values use their own evidence
    Assurance assurance;
};
struct OperationResult { SetHandle output; SetRelation relation; GeometryEvidence evidence; };
struct EmptySupport {};
struct UnboundedSupport {};
struct SupportResult { std::variant<double, EmptySupport, UnboundedSupport> value; std::optional<Vector> maximizer; GeometryEvidence evidence; };
enum class ContainmentDecision { contained, not_contained, undetermined };
struct ContainmentResult { ContainmentDecision decision; std::optional<Vector> counterexample; GeometryEvidence evidence; };
struct ConversionRequest { GeometryRequestIdentity identity; SetHandle input; RepresentationId output; Assurance assurance; };
struct ApproximationRequest { GeometryRequestIdentity identity; SetHandle input; RepresentationId output; SetRelation direction; std::size_t size_budget; Assurance assurance; };

struct LinearProgram {
    ProgramIdentity identity;
    Vector objective; double offset;
    SparseMatrix constraints;
    std::vector<Interval> variables, rows;
};
struct QuadraticProgram { LinearProgram linear; SparseMatrix hessian; }; // full symmetric Q
using ConvexProgram = std::variant<QuadraticProgram>; // conic forms require a revision
enum class Termination { completed, cancelled, resource_limit, numerical_failure };
enum class MathematicalOutcome { optimal, infeasible, unbounded, infimum_not_attained, undetermined };
template<class Subject> struct OutcomeClaim {
    Subject subject;
    MathematicalOutcome value;
    EvidenceSupport support;
    std::vector<std::string> assumptions;
};
using ProgramOutcomeClaim = OutcomeClaim<ProgramIdentity>;
using SynthesisOutcomeClaim = OutcomeClaim<ProblemId>;
struct ObjectiveBound { double value; ClaimEvidence evidence; };
struct ObjectiveEvidence { std::optional<ObjectiveBound> lower, upper; };
enum class StopReason { cancelled, resource_limit, numerical_failure };
struct OperationStopped { StopReason reason; std::string diagnostics; }; // no successful set/guarantee
struct ProgramResult {
    Termination termination;
    ProgramOutcomeClaim outcome;
    std::optional<Vector> primal;
    ObjectiveEvidence objective;
    std::string raw_diagnostics;
};
struct Unsupported { Diagnostics diagnostics; };
using ProgramOutcome = std::variant<ProgramResult, Unsupported>;
using SetTransformOutcome = std::variant<OperationResult, OperationStopped, Unsupported>;
using OperationOutcome = std::variant<OperationResult, SupportResult, ContainmentResult, OperationStopped, Unsupported>;

struct ResourcePolicy {
    std::size_t total_threads, outer_workers, threads_per_worker;
    std::optional<std::size_t> memory_bytes; // admission/accounting, not enforced by this revision
};
struct NumericalPolicy { double absolute_tolerance, relative_tolerance; };
struct ExecutionContext {
    std::shared_ptr<const ResourcePolicy> resources; // same policy for all workers
    std::stop_token cancellation;
    std::optional<std::chrono::steady_clock::time_point> deadline;
    NumericalPolicy numerical{1e-8,1e-8};
    std::string run_id;
};
class ExclusiveWorkspace {
public:
    ExclusiveWorkspace() = default;
    ExclusiveWorkspace(const ExclusiveWorkspace&) = delete;
    ExclusiveWorkspace& operator=(const ExclusiveWorkspace&) = delete;
    virtual ~ExclusiveWorkspace() = default;
};
struct BackendCapabilities { ModuleId id; std::string version; bool linear, convex_quadratic, basis_diagnostics; };
class LPWorkspace : public ExclusiveWorkspace {
public: virtual ProgramOutcome solve(const LinearProgram&, const ExecutionContext&) = 0;
};
class LPBackend {
public:
    virtual ~LPBackend() = default;
    virtual BackendCapabilities capabilities() const = 0;
    virtual std::unique_ptr<LPWorkspace> make_workspace() const = 0;
};
class ConvexWorkspace : public ExclusiveWorkspace {
public: virtual ProgramOutcome solve(const ConvexProgram&, const ExecutionContext&) = 0;
};
class ConvexBackend {
public:
    virtual ~ConvexBackend() = default;
    virtual BackendCapabilities capabilities() const = 0;
    virtual std::unique_ptr<ConvexWorkspace> make_workspace() const = 0;
};
// Basis is an optional separate port, never a requirement of LPWorkspace.
class BasisDiagnostics { public: virtual ~BasisDiagnostics() = default; virtual std::string describe_basis() const = 0; };
class SetOperatorWorkspace : public ExclusiveWorkspace {
public: virtual OperationOutcome apply(const OperationRequest&, const ExecutionContext&) = 0;
};
class RepresentationConverterWorkspace : public ExclusiveWorkspace {
public: virtual SetTransformOutcome convert(const ConversionRequest&, const ExecutionContext&) = 0;
};
class SetApproximatorWorkspace : public ExclusiveWorkspace {
public: virtual SetTransformOutcome approximate(const ApproximationRequest&, const ExecutionContext&) = 0;
};

// Canonical joint order: x0,...,xT,u0,...,u(T-1); a lifted payload retains this map.
struct JointCoordinates { Dimensions dimensions; std::size_t horizon; };
class JointRelationPayload { public: virtual ~JointRelationPayload() = default; };
struct JointRelation { JointCoordinates coordinates; RepresentationId representation; std::shared_ptr<const JointRelationPayload> payload; };
enum class FamilyTarget { exact_optimal_relation, candidate_relaxation, partial_relation };
struct OptimalFamily { ProblemId problem; JointRelation relation; FamilyTarget target; FamilyEvidence evidence; };
struct Witness { ProblemId problem; std::vector<Vector> states, controls; double original_objective; };
struct WitnessBatch { std::vector<Witness> witnesses; std::size_t requested; ModuleId selector; std::optional<std::size_t> seed; };
struct WitnessRequest { std::size_t count; double distinctness_tolerance; std::vector<Vector> directions; std::optional<std::size_t> seed; };
struct WitnessSelection { WitnessBatch batch; Termination termination; std::string diagnostics; }; // fewer witnesses is not a uniqueness proof
class WitnessSelectorWorkspace : public ExclusiveWorkspace {
public: virtual std::variant<WitnessSelection, Unsupported> select(const OptimalFamily&, const WitnessRequest&, const ExecutionContext&) = 0;
};
struct TimingSpan { std::size_t id; std::optional<std::size_t> parent; ModuleId module; double start_seconds, end_seconds; }; // overlapping intervals, not additive latency
struct SynthesisResult {
    Termination termination;
    SynthesisOutcomeClaim outcome;
    ObjectiveEvidence objective;
    std::optional<OptimalFamily> family;
    std::vector<Witness> incumbents;
    std::vector<TimingSpan> spans;
};
using SynthesisOutcome = std::variant<SynthesisResult, Unsupported>;
struct StrategyConfiguration {
    ModuleId strategy, lp, convex, hull, geometry, converter, approximation, selector;
    RepresentationId representation;
};
class SynthesisWorkspace : public ExclusiveWorkspace {
public: virtual SynthesisOutcome solve(const Problem&, const ExecutionContext&) = 0;
};
class SynthesisStrategy {
public:
    virtual ~SynthesisStrategy() = default;
    virtual Diagnostics check_capabilities(const Problem&, Assurance) const = 0;
    virtual std::unique_ptr<SynthesisWorkspace> make_workspace() const = 0;
};

// Small executable guards. These are not the full MODEL-01 validator/CORE-04 registry.
Diagnostics check_model_shape(const Dynamics&, std::size_t horizon);
Diagnostics check_nominal_profile(const Problem&, bool requires_inverse, Assurance);
Diagnostics check_family_evidence(const OptimalFamily&, const ProblemId&, Assurance);
Diagnostics check_resources(const ResourcePolicy&);
Diagnostics check_outcome_evidence(const ProgramOutcomeClaim&, const ProgramIdentity&, Assurance);
Diagnostics check_outcome_evidence(const SynthesisOutcomeClaim&, const ProblemId&, Assurance);
Diagnostics check_operation_shape(const OperationRequest&);
Diagnostics check_geometry_evidence(const GeometryEvidence&, const OperationRequest&);
Diagnostics check_geometry_evidence(const GeometryEvidence&, const ConversionRequest&);
Diagnostics check_geometry_evidence(const GeometryEvidence&, const ApproximationRequest&);
} // namespace csl
