#pragma once
#include <csl/problem/constraints.hpp>
#include <csl/problem/initial_information.hpp>
#include <csl/optimization/objectives.hpp>
#include <csl/registry/registry.hpp>
#include <array>

namespace csl::problem {
// A value only. Successful content owners can be created only from actual bytes.
struct ContentDigest {
    std::array<std::byte,32> bytes;
    bool operator==(const ContentDigest&) const = default;
};
std::string hex(ContentDigest);
namespace detail { struct ContentStorage; struct ResolvedStorage; struct ResolvedAccess; }
class ResolvedContent {
public:
    ResolvedContent(const ResolvedContent&) = default;
    ResolvedContent& operator=(const ResolvedContent&) = default;
    ContentDigest digest() const noexcept;
    // Borrow while retaining this owner or a copy. Rvalues copy non-destructively.
    std::span<const std::byte> bytes() const noexcept;
private:
    explicit ResolvedContent(std::shared_ptr<const detail::ContentStorage>);
    std::shared_ptr<const detail::ContentStorage> storage_;
    friend struct detail::ResolvedAccess;
};
Result<ResolvedContent> snapshot_content(std::span<const std::byte>,std::optional<ContentDigest> expected = {});
struct ContentBinding {
    std::string key;
    ResolvedContent content;
    std::string source_location; // Display only; excluded from identity and never opened.
};
enum class UncertaintyStructure {
    unspecified, stage_product_uncoupled, correlated_history, fixed_parameter,
    initial_external_coupling, state_or_parameter_dependent_dynamics
};
struct ResolutionContext {
    // Explicit intake; no inference from already-erased marginal set descriptions.
    UncertaintyStructure uncertainty{UncertaintyStructure::unspecified};
    optimization::ObjectivePolicy objective_policy{};
    std::span<const ContentBinding> external_content{};
};
class ResolvedProblem {
public:
    ResolvedProblem(const ResolvedProblem&) = default;
    ResolvedProblem& operator=(const ResolvedProblem&) = default;
    ProblemId identity() const;
    std::string authored_label() const;
    // Retains the immutable canonical DTO, with computed identity replacing its label.
    std::shared_ptr<const Problem> description() const noexcept;
    model::LinearSystem model() const;
    ControlDomains controls() const;
    InitialData initial() const;
    ExternalData external() const;
    Constraints constraints() const;
    optimization::Objective objective() const;
    std::shared_ptr<const std::vector<ContentBinding>> content() const noexcept;
    // Materializes the documented v1 encoding; normal publication hashes a stream.
    std::vector<std::byte> canonical_bytes() const;
private:
    explicit ResolvedProblem(std::shared_ptr<const detail::ResolvedStorage>);
    std::shared_ptr<const detail::ResolvedStorage> storage_;
    friend struct detail::ResolvedAccess;
};
using Resolution = std::variant<ResolvedProblem,Diagnostic,OperationStopped>;
// Valid data publication, independent of feasibility and configured strategy support.
Resolution resolve(const Problem&,const ResolutionContext&);
class PreparedResolvedStrategy {
public:
    PreparedResolvedStrategy(const PreparedResolvedStrategy&) = default;
    PreparedResolvedStrategy& operator=(const PreparedResolvedStrategy&) = default;
    ResolvedProblem problem() const;
    registry::PreparedStrategy preparation() const;
private:
    PreparedResolvedStrategy(ResolvedProblem,registry::PreparedStrategy);
    ResolvedProblem problem_;
    registry::PreparedStrategy preparation_;
    friend struct detail::ResolvedAccess;
};
using StrategyAdmission = std::variant<PreparedResolvedStrategy,registry::Rejection>;
// Delegates admission to the actual registry; retains resolved content in the wrapper.
StrategyAdmission prepare_strategy(const ResolvedProblem&,const registry::StrategyRegistry&,
    const StrategyConfiguration&,const registry::Requirements& = {},std::optional<std::string> strategy_version = {});
} // namespace csl::problem
