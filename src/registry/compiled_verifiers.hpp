#pragma once
#include <csl/registry/registry.hpp>
#include <memory>
#include "runtime_lineage.hpp"

namespace csl::synthesis::strategy_ts01 { class ExactJointRelation; }

namespace csl::registry::detail {
class CompiledCompleteFamilyVerifier {
public:
    virtual ~CompiledCompleteFamilyVerifier() = default;
    virtual const ModuleId& id() const noexcept = 0;
    virtual const std::string& version() const noexcept = 0;
    virtual Diagnostics verify(const StrategyRequest&, const CompleteFamilyProposal&) const = 0;
};
class CompiledPartialFamilyVerifier {
public:
    virtual ~CompiledPartialFamilyVerifier() = default;
    virtual const ModuleId& id() const noexcept = 0;
    virtual const std::string& version() const noexcept = 0;
    virtual Diagnostics verify(const StrategyRequest&, const PartialFamilyProposal&) const = 0;
};
std::shared_ptr<const CompiledCompleteFamilyVerifier> find_compiled_verifier(
    const ModuleId&, const std::string& version);
std::shared_ptr<const CompiledPartialFamilyVerifier> find_compiled_partial_verifier(
    const ModuleId&, const std::string& version);
bool ts01_profile_valid(const problem::ResolvedProblem&, const StrategyRequest&);
bool ts01_partial_profile_valid(const problem::ResolvedProblem&, const StrategyRequest&);
bool ts01_case_valid(const problem::ResolvedProblem&, const FamilyRequest&, const RepresentationId&,
    FamilyTarget target=FamilyTarget::exact_optimal_relation);
bool ts02_case_valid(const problem::ResolvedProblem&, const FamilyRequest&, const RepresentationId&);
bool ts03_case_valid(const problem::ResolvedProblem&, const FamilyRequest&, const RepresentationId&);
bool strategy_b_ts01_profile_valid(const problem::ResolvedProblem&, const StrategyRequest&);
bool strategy_a_ts01_profile_valid(const problem::ResolvedProblem&, const StrategyRequest&);
bool strategy_b_ts02_profile_valid(const problem::ResolvedProblem&, const StrategyRequest&);
bool strategy_a_ts02_profile_valid(const problem::ResolvedProblem&, const StrategyRequest&);
bool strategy_b_ts03_profile_valid(const problem::ResolvedProblem&, const StrategyRequest&);
bool strategy_a_ts03_profile_valid(const problem::ResolvedProblem&, const StrategyRequest&);
std::variant<std::shared_ptr<const ::csl::synthesis::strategy_ts01::ExactJointRelation>, Diagnostics> make_ts01_relation();
}
