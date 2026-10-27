#pragma once

#include <csl/artifacts/run_statistics.hpp>
#include <csl/registry/provider.hpp>
#include <csl/verification/trajectory.hpp>
#include <array>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <optional>
#include <span>
#include <string>
#include <variant>
#include <vector>

namespace csl::application {

struct ComparisonRequest {
    problem::ResolvedProblem problem;
    FamilyRequest family;
    std::array<StrategyConfiguration, 2> strategies;
};

struct SelectedMethod {
    StrategyConfiguration configuration;
    std::optional<std::string> requested_version;
};

class SelectedMethods {
public:
    static std::variant<SelectedMethods, Diagnostics> make(std::vector<SelectedMethod> methods);
    std::span<const SelectedMethod> values() const noexcept { return methods_; }
private:
    explicit SelectedMethods(std::vector<SelectedMethod> methods) : methods_(std::move(methods)) {}
    std::vector<SelectedMethod> methods_;
};

struct SelectedRunRequest {
    problem::ResolvedProblem problem;
    FamilyRequest family;
    SelectedMethods methods;
};

struct UnsupportedSelection { Diagnostics diagnostics; };
struct RejectedSelection {
    struct Entry { std::size_t index; registry::Rejection rejection; };
    std::vector<Entry> methods;
};
struct ComparisonPreparationObservation;

class PreparedSelection {
public:
    PreparedSelection(const PreparedSelection&) = default;
    PreparedSelection& operator=(const PreparedSelection&) = default;
    const problem::ResolvedProblem& problem() const noexcept { return problem_; }
    const FamilyRequest& family() const noexcept { return family_; }
    const std::vector<SelectedMethod>& methods() const noexcept { return methods_; }
    SynthesisIdentityExpectation expected_synthesis_identity(std::size_t index) const {
        return prepared_.at(index).expected_synthesis_identity();
    }
    std::vector<std::unique_ptr<registry::BoundWorkspace<registry::StrategyPort>>> create() const;
private:
    static std::variant<PreparedSelection, UnsupportedSelection, RejectedSelection>
        prepare_impl(const SelectedRunRequest&, const registry::StrategyRegistry&,
            ComparisonPreparationObservation*);
    PreparedSelection(problem::ResolvedProblem problem, FamilyRequest family,
        std::vector<SelectedMethod> methods, std::vector<registry::PreparedStrategy> prepared)
        : problem_(std::move(problem)), family_(std::move(family)),
          methods_(std::move(methods)), prepared_(std::move(prepared)) {}
    problem::ResolvedProblem problem_;
    FamilyRequest family_;
    std::vector<SelectedMethod> methods_;
    std::vector<registry::PreparedStrategy> prepared_;
    friend std::variant<PreparedSelection, UnsupportedSelection, RejectedSelection>
        prepare_selected_run(const SelectedRunRequest&, const registry::StrategyRegistry&);
    friend class PreparedComparison;
};

struct UnsupportedComparison {
    Diagnostics diagnostics;
};

struct RejectedComparison {
    std::vector<registry::Rejection> strategies;
    // Each entry identifies the corresponding zero-based request strategy.
    std::vector<std::size_t> strategy_indices;
};

enum class PreparationObservationStatus { not_entered, passed, rejected, threw };
struct ComparisonPreparationObservation {
    PreparationObservationStatus common_guard_status{PreparationObservationStatus::not_entered};
    std::uint64_t common_guards_ns{};
    std::array<registry::StrategyPreparationObservation, 2> registry_attempts{};
};

class PreparedComparison {
public:
    PreparedComparison(const PreparedComparison&) = default;
    PreparedComparison& operator=(const PreparedComparison&) = default;

    const problem::ResolvedProblem& problem() const noexcept { return selection_.problem(); }
    const FamilyRequest& family() const noexcept { return selection_.family(); }
    const std::array<StrategyConfiguration, 2>& strategies() const noexcept { return configurations_; }
    SynthesisIdentityExpectation expected_synthesis_identity(std::size_t index) const {
        return selection_.expected_synthesis_identity(index);
    }

    // Both exclusive workspaces are created before either strategy starts.
    std::array<std::unique_ptr<registry::BoundWorkspace<registry::StrategyPort>>, 2> create() const;

private:
    static std::variant<PreparedComparison, UnsupportedComparison, RejectedComparison>
        prepare_impl(const ComparisonRequest&, const registry::StrategyRegistry&,
            ComparisonPreparationObservation*);
    PreparedComparison(PreparedSelection selection,
        std::array<StrategyConfiguration, 2> configurations)
        : selection_(std::move(selection)), configurations_(std::move(configurations)) {}

    PreparedSelection selection_;
    std::array<StrategyConfiguration, 2> configurations_;
    friend std::variant<PreparedComparison, UnsupportedComparison, RejectedComparison>
        prepare_comparison(const ComparisonRequest&, const registry::StrategyRegistry&);
    friend std::variant<PreparedComparison, UnsupportedComparison, RejectedComparison>
        prepare_comparison_observed(const ComparisonRequest&, const registry::StrategyRegistry&,
            ComparisonPreparationObservation&);
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

struct SelectedMethodExecution {
    StrategyConfiguration configuration;
    StrategyExecution execution;
};
struct SelectedRunExecution { std::vector<SelectedMethodExecution> methods; };

using SelectionPreparation = std::variant<PreparedSelection, UnsupportedSelection, RejectedSelection>;
SelectionPreparation prepare_selected_run(const SelectedRunRequest&, const registry::StrategyRegistry&);
SelectedRunExecution run_selected(const PreparedSelection&,
    const registry::Registry<registry::SelectorPort>&, registry::Method selector,
    const WitnessRequest&, const registry::Requirements& selector_requirements,
    const ExecutionContext&,
    std::optional<registry::PreparedProvider<registry::LPPort>> membership_provider = std::nullopt);

using Preparation = std::variant<PreparedComparison, UnsupportedComparison, RejectedComparison>;

// Admits guarded T-S01/T-S02/T-S03 complete-family pairs and nominal-open-loop
// candidate generality runs against one immutable problem/request. No workspace
// is created on rejection.
Preparation prepare_comparison(const ComparisonRequest&, const registry::StrategyRegistry&);
Preparation prepare_comparison_observed(const ComparisonRequest&,
    const registry::StrategyRegistry&, ComparisonPreparationObservation&);

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
// comparison metadata remains in memory; trajectory results are stored as a
// versioned certificate-role attachment bound to the saved witness selection.
artifacts::ArtifactResult<std::string> encode_strategy_run(
    const problem::ResolvedProblem&, const StrategyExecution&,
    artifacts::ResolvedConfiguration, artifacts::RunId,
    artifacts::CollectedStatistics, artifacts::ResourceObservation);

} // namespace csl::application
