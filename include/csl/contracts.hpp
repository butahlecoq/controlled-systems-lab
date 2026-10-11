#pragma once

#include <chrono>
#include <cstddef>
#include <cstdint>
#include <span>
#include <memory>
#include <optional>
#include <stop_token>
#include <string>
#include <variant>
#include <utility>
#include <vector>

namespace csl {
// Revision 1.4. This is a source contract, not a stable binary ABI.
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
// after_decision(k) follows transition k; before_decision(T) is terminal only.
enum class ObservationTiming { before_decision, after_decision };
struct ObservationPoint { StageIndex stage; ObservationTiming timing; };
struct ObservationStage { Matrix state_map, control_map, external_map, error_map; Vector offset; };
// Indexed records follow authored sample order, not global transition index.
using ObservationCoefficients = std::variant<ObservationStage, std::vector<ObservationStage>>;
struct ObservationSample {
    StageIndex state_stage;
    ObservationPoint measured_at, available_at;
    std::optional<StageIndex> input_stage;
};
struct Observation { ObservationCoefficients coefficients; std::vector<ObservationSample> schedule; };
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
// Ordered stage-invariant choices, including an explicitly dimensioned empty catalogue.
struct FiniteDomain { std::size_t dimension; std::vector<Vector> catalogue; };
// Product coordinates are [continuous, discrete]; neither alternative denotes hybrid dynamics.
struct MixedDomain { ContinuousDomain continuous; FiniteDomain discrete; };
using ControlDomain = std::variant<ContinuousDomain, FiniteDomain, MixedDomain>;
struct LinearTerminal { Vector coefficients; double offset; };
struct QuadraticTerminal { Matrix Q; Vector linear; double offset; }; // 1/2 x'Qx+q'x+c
struct ResidualNormTerminal { Matrix map; Vector target; }; // ||Lx-r||_2, rectangular L
using TerminalObjective = std::variant<LinearTerminal, QuadraticTerminal, ResidualNormTerminal>;
struct TemporalConstraints { SparseMatrix joint_map; std::vector<Interval> bounds; };
struct KnownInitial { Vector point; };
enum class SetQuantifier { unspecified, existential, universal };
struct InitialSet { AdmissibleSet set; SetQuantifier quantifier{SetQuantifier::unspecified}; };
using InitialInformation = std::variant<KnownInitial, InitialSet>;
struct KnownExternalSequence { std::vector<Vector> stages; };
// T factors mean their Cartesian product; the quantifier scopes the whole sequence.
// No correlation, fixed-parameter reuse or initial/external coupling is encoded.
// At T=0 the product contains exactly the empty sequence. Boundedness is not implied.
struct ExogenousExternalInput {
    std::vector<AdmissibleSet> stages;
    SetQuantifier quantifier{SetQuantifier::unspecified};
};
struct AdversarialExternalInput {
    std::vector<AdmissibleSet> stages;
    SetQuantifier quantifier{SetQuantifier::unspecified};
    std::string semantics_reference; // Deferred objective/policy/information; cannot override product.
};
using ExternalInput = std::variant<KnownExternalSequence, ExogenousExternalInput, AdversarialExternalInput>;
enum class InformationPattern { nominal_open_loop, feedback };
struct Problem {
    ProblemId id;
    std::shared_ptr<const SystemModel> model;
    std::vector<double> times; // T+1 strictly increasing; controls indexed [0,T)
    InitialInformation initial;
    ControlDomain controls;
    std::vector<AdmissibleSet> states; // T+1; use UniversalSet explicitly
    std::optional<TemporalConstraints> temporal;
    std::optional<ExternalInput> external; // absent requires a zero-dimensional external port
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

struct LinearProgramInput {
    ProgramIdentity identity;
    Vector objective; double offset;
    SparseMatrix constraints;
    std::vector<Interval> variables, rows;
};
namespace numeric { class MatrixView; class VectorView; }
namespace optimization { struct ProgramAccess; }
class LinearProgram {
public:
    LinearProgram(const LinearProgram&) noexcept = default;
    LinearProgram& operator=(const LinearProgram&) noexcept = default;
    const ProgramIdentity& identity() const noexcept;
    const numeric::VectorView& objective() const noexcept;
    double offset() const noexcept;
    const numeric::MatrixView& constraints() const noexcept;
    std::span<const Interval> variables() const noexcept;
    std::span<const Interval> rows() const noexcept;
private:
    struct Storage;
    std::shared_ptr<const Storage> storage_;
    explicit LinearProgram(std::shared_ptr<const Storage> storage) : storage_(std::move(storage)) {}
    friend struct optimization::ProgramAccess;
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
struct ProgramBoundEvidence { ProgramIdentity subject; EvidenceSupport support; std::vector<std::string> assumptions; };
struct ProgramObjectiveBound { double value; ProgramBoundEvidence evidence; };
struct ProgramObjectiveEvidence { std::optional<ProgramObjectiveBound> lower, upper; };
struct Verifier { ModuleId id; std::string version; };
struct ResidualMeasure { double violation, scale; };
// All checks use binary64 and violation <= absolute + relative * scale.
struct ResidualContext { ProgramIdentity subject; Verifier verifier; double absolute_tolerance, relative_tolerance; };
struct PrimalResiduals { ResidualContext context; ResidualMeasure rows, variables; };
struct DualResiduals { ResidualContext context; std::optional<ResidualMeasure> stationarity, signs, complementarity; };
struct ProgramResiduals { std::optional<PrimalResiduals> primal; std::optional<DualResiduals> dual; };

enum class StopReason { cancelled, resource_limit, numerical_failure };
struct OperationStopped { StopReason reason; std::string diagnostics; }; // no successful set/guarantee
struct ProgramResult {
    Termination termination;
    ProgramOutcomeClaim outcome;
    std::optional<Vector> primal;
    ProgramObjectiveEvidence objective;
    std::string raw_diagnostics;
    ProgramResiduals residuals{};
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
class WorkspaceIdentity {
    struct Token {};
    std::shared_ptr<const Token> token_;
    WorkspaceIdentity() : token_(std::make_shared<const Token>()) {}
    friend class LPWorkspace;
public:
    bool operator==(const WorkspaceIdentity&) const = default;
};
class SolveStamp {
    LinearProgram program_;
    WorkspaceIdentity workspace_;
    std::uint64_t attempt_;
    SolveStamp(const LinearProgram& p, const WorkspaceIdentity& w, std::uint64_t a) noexcept
        : program_(p), workspace_(w), attempt_(a) {}
    friend class LPWorkspace;
public:
    const LinearProgram& program() const noexcept { return program_; }
    const WorkspaceIdentity& workspace() const noexcept { return workspace_; }
    std::uint64_t attempt() const noexcept { return attempt_; }
    bool operator==(const SolveStamp& other) const noexcept {
        return workspace_ == other.workspace_ && attempt_ == other.attempt_;
    }
};
enum class SolveAttemptState { running, returned_result, unsupported, exception };
struct SolveAttempt { SolveStamp stamp; SolveAttemptState state; };
class LPWorkspace : public ExclusiveWorkspace {
    WorkspaceIdentity identity_;
    std::uint64_t sequence_{};
    std::optional<SolveAttempt> attempt_;
public:
    ProgramOutcome solve(const LinearProgram&, const ExecutionContext&);
    const WorkspaceIdentity& workspace_identity() const noexcept { return identity_; }
    const std::optional<SolveAttempt>& last_attempt() const noexcept { return attempt_; }
protected:
    virtual ProgramOutcome do_solve(const LinearProgram&, const ExecutionContext&) = 0;
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
struct StructuralColumn { std::size_t index; bool operator==(const StructuralColumn&) const = default; };
struct RowActivityColumn { std::size_t index; bool operator==(const RowActivityColumn&) const = default; };
struct AuxiliaryColumn { std::size_t id; Vector coefficients; bool operator==(const AuxiliaryColumn&) const = default; };
using BasisColumn = std::variant<StructuralColumn, RowActivityColumn, AuxiliaryColumn>;
struct BasisReference { SolveStamp solve; std::uint64_t iteration; bool operator==(const BasisReference&) const = default; };
struct PivotRecord {
    BasisReference before, after;
    std::vector<BasisColumn> before_basis;
    BasisColumn entering, leaving;
    std::size_t position;
    double coefficient; // signed (B_before^-1 * entering)[position]
};
struct BasisSnapshot { BasisReference reference; std::vector<BasisColumn> columns; std::optional<PivotRecord> last_pivot; };
struct BasisCoordinates { BasisReference reference; Vector values; };
enum class BasisUnavailableReason { unsupported, not_solved, unavailable_result, stale_reference };
struct BasisUnavailable { BasisUnavailableReason reason; std::string explanation; };
struct BasisCapabilities { bool snapshot, pivots, coordinates; };
using BasisSnapshotResult = std::variant<BasisSnapshot, BasisUnavailable>;
using BasisCoordinatesResult = std::variant<BasisCoordinates, BasisUnavailable, Diagnostics>;
class BasisDiagnostics {
public:
    virtual ~BasisDiagnostics() = default;
    virtual BasisCapabilities capabilities() const = 0;
    virtual BasisSnapshotResult snapshot() const = 0;
    virtual BasisCoordinatesResult coordinates(const BasisReference&, std::span<const double>) const {
        return BasisUnavailable{BasisUnavailableReason::unsupported, "basis coordinates unavailable"};
    }
    virtual std::string describe_basis() const { return {}; }
};
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
