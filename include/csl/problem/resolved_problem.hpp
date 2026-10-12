#pragma once

#include <csl/problem/constraints.hpp>
#include <csl/problem/initial_information.hpp>
#include <csl/optimization/objectives.hpp>
#include <array>

namespace csl::problem {
// Immutable source and mathematical identity, independent of strategy admission.
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
    std::string source_location;
};
enum class UncertaintyStructure {
    unspecified, stage_product_uncoupled, correlated_history, fixed_parameter,
    initial_external_coupling, state_or_parameter_dependent_dynamics
};
struct ResolutionContext {
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
    std::shared_ptr<const Problem> description() const noexcept;
    model::LinearSystem model() const;
    ControlDomains controls() const;
    InitialData initial() const;
    ExternalData external() const;
    Constraints constraints() const;
    optimization::Objective objective() const;
    std::shared_ptr<const std::vector<ContentBinding>> content() const noexcept;
    std::vector<std::byte> canonical_bytes() const;
private:
    explicit ResolvedProblem(std::shared_ptr<const detail::ResolvedStorage>);
    std::shared_ptr<const detail::ResolvedStorage> storage_;
    friend struct detail::ResolvedAccess;
};
using Resolution = std::variant<ResolvedProblem,Diagnostic,OperationStopped>;
Resolution resolve(const Problem&,const ResolutionContext&);
} // namespace csl::problem
