#pragma once

#include <csl/artifacts/run_statistics.hpp>
#include <csl/registry/provider.hpp>
#include <csl/verification/trajectory.hpp>
#include <array>
#include <memory>
#include <optional>
#include <variant>
#include <vector>

namespace csl::application {

struct ComparisonRequest {
    problem::ResolvedProblem problem;
    FamilyRequest family;
    std::array<StrategyConfiguration, 2> strategies;
};

struct UnsupportedComparison {
    Diagnostics diagnostics;
};

struct RejectedComparison {
    std::vector<registry::Rejection> strategies;
    // Each entry identifies the corresponding zero-based request strategy.
    std::vector<std::size_t> strategy_indices;
};

class PreparedComparison {
public:
    PreparedComparison(const PreparedComparison&) = default;
    PreparedComparison& operator=(const PreparedComparison&) = default;

    const problem::ResolvedProblem& problem() const noexcept { return problem_; }
    const FamilyRequest& family() const noexcept { return family_; }
    const std::array<StrategyConfiguration, 2>& strategies() const noexcept { return configurations_; }
    SynthesisIdentityExpectation expected_synthesis_identity(std::size_t index) const {
        return prepared_.at(index).expected_synthesis_identity();
    }

    // Both exclusive workspaces are created before either strategy starts.
    std::array<std::unique_ptr<registry::BoundWorkspace<registry::StrategyPort>>, 2> create() const;

private:
    PreparedComparison(problem::ResolvedProblem problem, FamilyRequest family,
        std::array<StrategyConfiguration, 2> configurations,
        std::array<registry::PreparedStrategy, 2> prepared)
        : problem_(std::move(problem)), family_(std::move(family)),
          configurations_(std::move(configurations)), prepared_(std::move(prepared)) {}

    problem::ResolvedProblem problem_;
    FamilyRequest family_;
    std::array<StrategyConfiguration, 2> configurations_;
    std::array<registry::PreparedStrategy, 2> prepared_;
    friend std::variant<PreparedComparison, UnsupportedComparison, RejectedComparison>
        prepare_comparison(const ComparisonRequest&, const registry::StrategyRegistry&);
};

using SelectionOutcome = std::variant<std::monostate, registry::Rejection, Unsupported,
    WitnessSelection>;

struct StrategyExecution {
    SynthesisOutcome outcome;
    artifacts::FinalOutcome final_projection;
    SelectionOutcome selection;
    std::vector<verification::TrajectoryReport> verification;
};

struct ComparisonExecution {
    std::array<StrategyExecution, 2> strategies;
};

using Preparation = std::variant<PreparedComparison, UnsupportedComparison, RejectedComparison>;

// Admits guarded T-S01/T-S02/T-S03 pairs against one immutable mathematical
// problem and one effective request. No workspace is created on rejection.
Preparation prepare_comparison(const ComparisonRequest&, const registry::StrategyRegistry&);

// Executes both admitted strategies on the same problem/request. Complete
// families may be queried through SelectorPort; candidate/partial results are
// retained without selection. Returned witnesses are independently checked
// against the original problem and expected family binding.
ComparisonExecution run_comparison(const PreparedComparison&,
    const registry::Registry<registry::SelectorPort>&, registry::Method selector,
    const WitnessRequest&, const registry::Requirements& selector_requirements,
    const ExecutionContext&,
    std::optional<registry::PreparedProvider<registry::LPPort>> membership_provider = std::nullopt);

// Encodes one strategy final through the versioned publisher and codec. Paired
// comparison metadata and verifier reports remain in memory.
artifacts::ArtifactResult<std::string> encode_strategy_run(
    const problem::ResolvedProblem&, const StrategyExecution&,
    artifacts::ResolvedConfiguration, artifacts::RunId,
    artifacts::CollectedStatistics, artifacts::ResourceObservation);

} // namespace csl::application
