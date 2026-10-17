#pragma once

#include <csl/controllers/observed_replay.hpp>
#include <csl/problem/contracts.hpp>

#include <span>

namespace csl::controllers {

// A policy rule is keyed by the complete observation history released by the
// requested stage. State, external-input, and measurement-error samples are
// never policy inputs.
struct FinitePolicyRule {
    StageIndex stage;
    std::vector<ReleasedObservation> history;
    Vector action;
};

class FiniteObservationPolicy {
public:
    FiniteObservationPolicy(const FiniteObservationPolicy&) = default;
    FiniteObservationPolicy& operator=(const FiniteObservationPolicy&) = default;
    std::span<const FinitePolicyRule> rules() const noexcept { return rules_; }

private:
    explicit FiniteObservationPolicy(std::vector<FinitePolicyRule> rules);
    std::vector<FinitePolicyRule> rules_;
    friend std::variant<FiniteObservationPolicy, Diagnostic>
        make_finite_observation_policy(std::vector<FinitePolicyRule>);
    friend struct FinitePolicyEvaluator;
};

using FinitePolicyBuildResult = std::variant<FiniteObservationPolicy, Diagnostic>;
FinitePolicyBuildResult make_finite_observation_policy(std::vector<FinitePolicyRule> rules);

struct FinitePolicyFamilyRequest {
    // The quantifier is mandatory. Its scope is exactly the enumerated rows
    // below; this request cannot represent a continuous initial set.
    SetQuantifier initial_quantifier{SetQuantifier::unspecified};
    std::vector<ReplayInputs> scenarios;
};

struct FinitePolicyDecisionEvidence {
    StageIndex stage;
    std::vector<ReleasedObservation> available;
    Vector action;
};

struct FinitePolicyScenarioEvidence {
    ReplayInputs inputs;
    std::vector<Vector> states;
    std::vector<FinitePolicyDecisionEvidence> decisions;
    std::vector<ReleasedObservation> released;
};

struct FinitePolicyFamilyEvidence {
    SetQuantifier initial_quantifier;
    std::vector<FinitePolicyScenarioEvidence> scenarios;
};

using FinitePolicyFamilyResult =
    std::variant<FinitePolicyFamilyEvidence, Diagnostic, OperationStopped>;

// Replays one finite table policy over every listed scenario. Equal released
// histories at a stage have one table entry and therefore one action. The
// evidence covers only these authored scenarios; it proves no constraint,
// optimality, continuous-set, or unlisted-disturbance claim.
FinitePolicyFamilyResult replay_finite_policy_family(const model::LinearSystem&,
    const FinitePolicyFamilyRequest&, const FiniteObservationPolicy&);

} // namespace csl::controllers
