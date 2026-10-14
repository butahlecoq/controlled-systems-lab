#pragma once

#include <csl/problem/contracts.hpp>
#include <csl/geometry/contracts.hpp>
#include <csl/optimization/contracts.hpp>
#include <chrono>
#include <cmath>
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
namespace problem { class ResolvedProblem; }
namespace registry { class StrategyRegistry; namespace detail { class VerifiedFamilyAuthority; class VerifiedPartialFamilyAuthority; } }
class JointRelationPayload { public: virtual ~JointRelationPayload() = default; };
struct JointRelation { JointCoordinates coordinates; RepresentationId representation; std::shared_ptr<const JointRelationPayload> payload; };
enum class FamilyTarget { exact_optimal_relation, candidate_relaxation, partial_relation };
struct FamilyRequest {
    std::string profile;
    ProblemId objective; // resolved mathematical identity includes the effective objective
    FamilyTarget target{FamilyTarget::candidate_relaxation};
    NumericalPolicy numerical{1e-8,1e-8};
    Assurance assurance{Assurance::numerical};
    RepresentationId representation;
    std::optional<std::size_t> materialization_limit;
    bool operator==(const FamilyRequest&) const = default;
};
struct TransformStepIdentity {
    RequestId request;
    SetId input, output;
    ModuleId module;
    std::string version;
    bool operator==(const TransformStepIdentity&) const = default;
};
struct FamilyIdentity {
    ProblemId problem;
    FamilyRequest request;
    JointCoordinates coordinates;
    ModuleId strategy;
    std::string strategy_version;
    std::vector<TransformStepIdentity> lineage;
    bool operator==(const FamilyIdentity&) const = default;
};
struct SynthesisIdentityExpectation {
    ProblemId problem;
    FamilyRequest request;
    JointCoordinates coordinates;
    ModuleId strategy;
    std::string strategy_version;
    std::optional<std::vector<TransformStepIdentity>> lineage;
};
struct OptimumEvidence { ClaimEvidence optimum; ObjectiveEvidence bounds; };
struct NumericalCoverageEvidence {
    std::string procedure;
    NumericalPolicy policy;
    ModuleId verifier;
    std::string diagnostics;
};
struct ValidatedCoverageEvidence { std::string certificate; ModuleId verifier; std::string arithmetic_profile; };
// Opaque proof bytes are claims until the compiled verifier selected by the
// registry validates them against the authoritative prepared context.
struct RegisteredCompletenessEvidence {
    ModuleId verifier;
    std::string verifier_version;
    // Opaque verifier-defined serialized text; decoding does not confer trust.
    std::string proof;
};
struct CompletenessEvidence {
    FamilyIdentity binding;
    std::variant<NumericalCoverageEvidence,ValidatedCoverageEvidence,RegisteredCompletenessEvidence> support;
};
struct CompleteOptimalFamily {
    JointRelation relation;
    OptimumEvidence optimum;
    CompletenessEvidence completeness;
    Assurance assurance;
};
// Unpublished complete-family claims are proposals until the selected registry
// entry's verifier accepts them against the prepared problem and request.
struct CompleteFamilyProposal { FamilyIdentity identity; CompleteOptimalFamily family; };
struct InnerSubsetEvidence { ClaimEvidence every_history_optimal; std::string procedure; };
struct CoverageScope { std::string description; };
struct PartialOptimalFamily {
    JointRelation relation;
    OptimumEvidence optimum;
    InnerSubsetEvidence optimal_subset;
    CoverageScope known_scope;
};
// A partial-family proposal is an untrusted strategy result until the verifier
// selected by the prepared registry validates its exact scope and identity.
struct PartialFamilyProposal { FamilyIdentity identity; PartialOptimalFamily family; };
struct OuterCandidateEvidence { ClaimEvidence enclosure; };
struct FeasibleCandidateEvidence { ClaimEvidence feasibility; };
struct HeuristicRelationEvidence { std::string method; };
using FamilyRelationToTarget = std::variant<OuterCandidateEvidence,FeasibleCandidateEvidence,HeuristicRelationEvidence>;
struct Witness { ProblemId problem; std::vector<Vector> states, controls; double original_objective; };
struct RelationFeasibilityEvidence { ClaimEvidence support; };
struct WitnessFeasibilityEvidence { Witness witness; ClaimEvidence support; };
using CandidateFeasibility = std::variant<Unestablished,RelationFeasibilityEvidence,WitnessFeasibilityEvidence>;
struct CandidateFamily {
    JointRelation relation;
    FamilyRelationToTarget relation_to_target;
    CandidateFeasibility feasibility;
};
using OptimalFamilyOutcome = std::variant<CompleteOptimalFamily,PartialOptimalFamily,CandidateFamily>;
class OptimalFamily {
public:
    const FamilyIdentity& identity() const noexcept { return identity_; }
    const OptimalFamilyOutcome& outcome() const noexcept { return outcome_; }
    FamilyTarget target() const noexcept {
        if (std::holds_alternative<CompleteOptimalFamily>(outcome_)) return FamilyTarget::exact_optimal_relation;
        if (std::holds_alternative<PartialOptimalFamily>(outcome_)) return FamilyTarget::partial_relation;
        return FamilyTarget::candidate_relaxation;
    }
    bool registry_verified() const noexcept { return registry_verified_; }
    bool partial_registry_verified() const noexcept { return partial_registry_verified_; }
private:
    FamilyIdentity identity_;
    OptimalFamilyOutcome outcome_;
    bool registry_verified_{};
    bool partial_registry_verified_{};
    OptimalFamily(FamilyIdentity identity, OptimalFamilyOutcome outcome, bool registry_verified = false,
        bool partial_registry_verified = false)
        : identity_(std::move(identity)), outcome_(std::move(outcome)), registry_verified_(registry_verified),
          partial_registry_verified_(partial_registry_verified) {}
    friend class FamilyPublisher;
};
class registry::detail::VerifiedFamilyAuthority {
    ModuleId strategy_;
    std::string version_;
    VerifiedFamilyAuthority(ModuleId strategy,std::string version)
        : strategy_(std::move(strategy)),version_(std::move(version)) {}
    friend class registry::StrategyRegistry;
    friend class FamilyPublisher;
public:
    bool matches(const ModuleId& strategy,const std::string& version) const noexcept {
        return strategy_==strategy&&version_==version&&!strategy_.value.empty()&&!version_.empty();
    }
};
class registry::detail::VerifiedPartialFamilyAuthority {
    ModuleId strategy_;
    std::string strategy_version_;
    ModuleId verifier_;
    std::string verifier_version_;
    VerifiedPartialFamilyAuthority(ModuleId strategy,std::string strategy_version,ModuleId verifier,std::string verifier_version)
        : strategy_(std::move(strategy)),strategy_version_(std::move(strategy_version)),
          verifier_(std::move(verifier)),verifier_version_(std::move(verifier_version)) {}
    friend class registry::StrategyRegistry;
    friend class FamilyPublisher;
public:
    bool matches(const ModuleId& strategy,const std::string& strategy_version,const ModuleId& verifier,
        const std::string& verifier_version) const noexcept {
        return strategy_==strategy&&strategy_version_==strategy_version&&verifier_==verifier&&
            verifier_version_==verifier_version&&!strategy_.value.empty()&&!strategy_version_.empty()&&
            !verifier_.value.empty()&&!verifier_version_.empty();
    }
};
Diagnostics check_family_evidence(const OptimalFamily&, const ProblemId&, Assurance);
class FamilyPublisher {
public:
    static std::variant<OptimalFamily,Diagnostics> publish(FamilyIdentity identity,OptimalFamilyOutcome outcome) {
        OptimalFamily proposed{std::move(identity),std::move(outcome)};
        auto diagnostics=check_family_evidence(proposed,proposed.identity().problem,proposed.identity().request.assurance);
        if(!diagnostics.empty())return diagnostics;
        return proposed;
    }
    static std::variant<OptimalFamily,Diagnostics> publish_verified(FamilyIdentity identity,
        OptimalFamilyOutcome outcome,const registry::detail::VerifiedFamilyAuthority& authority) {
        if(!authority.matches(identity.strategy,identity.strategy_version)||
            !std::holds_alternative<CompleteOptimalFamily>(outcome))
            return Diagnostics{{DiagnosticCode::evidence_mismatch,"family.verifier",
                "A complete family must carry authority from its selected strategy registration"}};
        OptimalFamily proposed{std::move(identity),std::move(outcome),true};
        auto diagnostics=check_family_evidence(proposed,proposed.identity().problem,proposed.identity().request.assurance);
        if(!diagnostics.empty())return diagnostics;
        return proposed;
    }
    static std::variant<OptimalFamily,Diagnostics> publish_verified_partial(FamilyIdentity identity,
        PartialOptimalFamily partial,const registry::detail::VerifiedPartialFamilyAuthority& authority,
        const ModuleId& verifier,const std::string& verifier_version) {
        if(!authority.matches(identity.strategy,identity.strategy_version,verifier,verifier_version)||
            identity.request.target!=FamilyTarget::partial_relation)
            return Diagnostics{{DiagnosticCode::evidence_mismatch,"family.partial.verifier",
                "A partial family requires authority from its selected partial-family verifier and strategy registration"}};
        OptimalFamily proposed{std::move(identity),OptimalFamilyOutcome{std::move(partial)},false,true};
        auto diagnostics=check_family_evidence(proposed,proposed.identity().problem,proposed.identity().request.assurance);
        if(!diagnostics.empty())return diagnostics;
        return proposed;
    }
};
struct FeasibleIncumbent {
    Witness witness;
    ClaimEvidence feasibility;
};
struct WitnessBatch { std::vector<Witness> witnesses; std::size_t requested; ModuleId selector; std::optional<std::size_t> seed; std::optional<FamilyIdentity> source_family{};
    std::vector<Vector> directions{};
    double distinctness_tolerance{};
    // Raw successful query observations, including repeats. Distinctness uses
    // ordered greedy representatives and max-absolute joint-history distance.
    // Shapes must match. The <= tolerance relation is not transitive, so the
    // representative count can depend on observation order.
    std::size_t returned_count() const noexcept { return witnesses.size(); }
    std::size_t distinct_count() const {
        std::vector<std::size_t> representatives;
        const auto close=[&](const Witness& a,const Witness& b) {
            const auto histories_close=[&](const auto& left,const auto& right) {
                if(left.size()!=right.size())return false;
                for(std::size_t t=0;t<left.size();++t) {
                    if(left[t].size()!=right[t].size())return false;
                    for(std::size_t j=0;j<left[t].size();++j)
                        if(!(std::abs(left[t][j]-right[t][j])<=distinctness_tolerance))return false;
                }
                return true;
            };
            return histories_close(a.states,b.states)&&histories_close(a.controls,b.controls);
        };
        for(std::size_t i=0;i<witnesses.size();++i) {
            bool duplicate=false;
            for(const auto representative:representatives)
                if(close(witnesses[i],witnesses[representative])) { duplicate=true; break; }
            if(!duplicate)representatives.push_back(i);
        }
        return representatives.size();
    }
};
struct WitnessRequest { std::size_t count; double distinctness_tolerance; std::vector<Vector> directions; std::optional<std::size_t> seed; };
struct WitnessSelection { WitnessBatch batch; Termination termination; std::string diagnostics; }; // fewer witnesses is not a uniqueness proof
class WitnessSelectorWorkspace : public ExclusiveWorkspace {
public: virtual std::variant<WitnessSelection, Unsupported> select(const OptimalFamily&, const WitnessRequest&, const ExecutionContext&) = 0;
};
struct TimingSpan { std::size_t id; std::optional<std::size_t> parent; ModuleId module; double start_seconds, end_seconds; }; // overlapping intervals, not additive latency
struct RequestProvenance {
    RequestId request;
    std::string port;
    ModuleId requested_module;
    std::optional<std::string> requested_version;
    std::optional<ModuleId> actual_module;
    std::optional<std::string> actual_version;
};
struct RetainedEvidenceScope {
    bool lower_bound{}, upper_bound{};
    std::size_t incumbents{};
    bool partial_or_candidate_family{};
};
struct ScopedOperationStopped {
    OperationStopped stop;
    RequestProvenance request;
    RetainedEvidenceScope retained;
};
struct ScopedRequestRejection {
    RequestProvenance request;
    Diagnostics diagnostics;
    std::vector<TransformStepIdentity> completed_lineage;
    RetainedEvidenceScope retained;
};
using SourceStopEvidence = std::variant<std::monostate,ScopedOperationStopped,ScopedRequestRejection>;
struct ContractValidationFailure {
    Diagnostics diagnostics;
    RetainedEvidenceScope retained;
    SourceStopEvidence source_stop;
};
using SynthesisStopEvidence = std::variant<std::monostate,ScopedOperationStopped,ScopedRequestRejection,ContractValidationFailure>;
struct SynthesisResult {
    Termination termination;
    SynthesisOutcomeClaim outcome;
    ObjectiveEvidence objective;
    std::optional<OptimalFamily> family;
    std::vector<FeasibleIncumbent> incumbents;
    std::vector<TimingSpan> spans;
    SynthesisStopEvidence stop{};
    std::optional<CompleteFamilyProposal> complete_proposal{};
    std::optional<PartialFamilyProposal> partial_proposal{};
};
using SynthesisOutcome = std::variant<SynthesisResult, Unsupported>;
struct StrategyConfiguration {
    ModuleId strategy, lp, convex, hull, geometry, converter, approximation, selector;
    RepresentationId representation;
};
class SynthesisWorkspace : public ExclusiveWorkspace {
public: virtual SynthesisResult solve(const problem::ResolvedProblem&, const FamilyRequest&, const ExecutionContext&) = 0;
};

class SynthesisStrategy {
public:
    virtual ~SynthesisStrategy() = default;
    virtual Diagnostics check_capabilities(const problem::ResolvedProblem&, const FamilyRequest&) const = 0;
    virtual std::unique_ptr<SynthesisWorkspace> make_workspace() const = 0;
};
Diagnostics check_family_request(const FamilyRequest&, const ProblemId&);
Diagnostics check_family_evidence(const OptimalFamily&, const ProblemId&, Assurance);
bool supported_synthesis_bound(const ObjectiveBound&, const ProblemId&);
bool supported_feasible_incumbent(const FeasibleIncumbent&, const FamilyIdentity&);
Diagnostics check_synthesis_result(const SynthesisResult&, const FamilyIdentity&);
Diagnostics check_synthesis_result(const SynthesisResult&, const SynthesisIdentityExpectation&);
} // namespace csl
