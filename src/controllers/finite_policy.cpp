#include <csl/controllers/finite_policy.hpp>

#include <algorithm>
#include <cmath>
#include <utility>

namespace csl::controllers {
namespace {
Diagnostic invalid(std::string field, std::string explanation) {
    return {DiagnosticCode::invalid_input, std::move(field), std::move(explanation)};
}

bool finite(std::span<const double> values) {
    return std::all_of(values.begin(), values.end(), [](double value) {
        return std::isfinite(value);
    });
}

bool same_event(ObservationPoint left, ObservationPoint right) {
    return left.stage.value == right.stage.value && left.timing == right.timing;
}

bool same_observation(const ReleasedObservation& left, const ReleasedObservation& right) {
    return left.channel.value == right.channel.value
        && left.sample.value == right.sample.value
        && same_event(left.released_at, right.released_at)
        && left.value.values == right.value.values;
}

bool same_history(std::span<const ReleasedObservation> left,
    std::span<const ReleasedObservation> right) {
    return left.size() == right.size()
        && std::equal(left.begin(), left.end(), right.begin(), same_observation);
}

bool same_key(const FinitePolicyRule& left, const FinitePolicyRule& right) {
    return left.stage.value == right.stage.value
        && same_history(left.history, right.history);
}

bool valid_quantifier(SetQuantifier quantifier) {
    return quantifier == SetQuantifier::existential
        || quantifier == SetQuantifier::universal;
}

bool valid_rule(const FinitePolicyRule& rule) {
    if (!finite(rule.action)) return false;
    for (const auto& observation : rule.history) {
        if (!finite(observation.value.values)) return false;
        if (observation.released_at.timing != ObservationTiming::before_decision
            && observation.released_at.timing != ObservationTiming::after_decision)
            return false;
    }
    return true;
}
}

FiniteObservationPolicy::FiniteObservationPolicy(std::vector<FinitePolicyRule> rules)
    : rules_(std::move(rules)) {}

FinitePolicyBuildResult make_finite_observation_policy(std::vector<FinitePolicyRule> rules) {
    for (const auto& rule : rules)
        if (!valid_rule(rule))
            return invalid("controllers.policy.rule",
                "Policy histories and actions must contain finite values and valid release timings.");

    std::vector<FinitePolicyRule> unique;
    unique.reserve(rules.size());
    for (auto& rule : rules) {
        const auto found = std::find_if(unique.begin(), unique.end(), [&](const auto& existing) {
            return same_key(existing, rule);
        });
        if (found == unique.end()) {
            unique.push_back(std::move(rule));
        } else if (found->action != rule.action) {
            return invalid("controllers.policy.nonanticipativity",
                "One stage and released observation history cannot prescribe different actions.");
        }
    }
    return FiniteObservationPolicy(std::move(unique));
}

struct FinitePolicyEvaluator {
    static std::optional<std::size_t> find_rule(const FiniteObservationPolicy& policy,
        StageIndex stage, std::span<const ReleasedObservation> history) {
        for (std::size_t i = 0; i < policy.rules_.size(); ++i) {
            const auto& rule = policy.rules_[i];
            if (rule.stage.value == stage.value && same_history(rule.history, history)) return i;
        }
        return std::nullopt;
    }
};

FinitePolicyFamilyResult replay_finite_policy_family(const model::LinearSystem& system,
    const FinitePolicyFamilyRequest& request, const FiniteObservationPolicy& policy) {
    if (!valid_quantifier(request.initial_quantifier))
        return invalid("controllers.policy.initial_quantifier",
            "Finite policy evaluation requires an explicit existential or universal initial quantifier.");
    if (request.scenarios.empty())
        return invalid("controllers.policy.scenarios", "At least one finite scenario is required.");
    if (request.initial_quantifier == SetQuantifier::existential
        && request.scenarios.size() != 1)
        return invalid("controllers.policy.existential_scenario_count",
            "Existential evaluation requires exactly one caller-selected witness scenario.");

    std::vector<bool> used(policy.rules().size(), false);
    FinitePolicyFamilyEvidence evidence{request.initial_quantifier, {}};
    evidence.scenarios.reserve(request.scenarios.size());
    for (const auto& inputs : request.scenarios) {
        std::optional<Diagnostic> missing_rule;
        const auto estimator = [&](StageIndex, std::span<const ReleasedObservation>) {
            // The finite policy depends on released observations alone. The
            // replay interface requires an estimate, so supply an unused zero
            // hypothesis and omit it from the policy-family evidence.
            return Vector(system.dimensions().state, 0.0);
        };
        const auto controller = [&](StageIndex stage,
            std::span<const ReleasedObservation> history, std::span<const double>) {
            const auto index = FinitePolicyEvaluator::find_rule(policy, stage, history);
            if (!index) {
                missing_rule = invalid("controllers.policy.missing_rule",
                    "The finite policy has no action for a released history in an enumerated scenario.");
                return Vector(system.dimensions().control + 1, 0.0);
            }
            used[*index] = true;
            return policy.rules()[*index].action;
        };
        auto replay = replay_observed_policy(system, inputs, estimator, controller);
        if (missing_rule) return *missing_rule;
        if (const auto* failure = std::get_if<Diagnostic>(&replay)) return *failure;
        if (const auto* stopped = std::get_if<OperationStopped>(&replay)) return *stopped;

        auto record = std::get<ReplayRecord>(std::move(replay));
        FinitePolicyScenarioEvidence scenario{record.inputs, record.states, {}, record.released};
        scenario.decisions.reserve(record.decisions.size());
        for (const auto& decision : record.decisions)
            scenario.decisions.push_back({decision.stage, decision.available, decision.action});
        evidence.scenarios.push_back(std::move(scenario));
    }

    if (std::find(used.begin(), used.end(), false) != used.end())
        return invalid("controllers.policy.unused_rule",
            "Every finite policy rule must be exercised by at least one enumerated scenario.");
    return evidence;
}

} // namespace csl::controllers
