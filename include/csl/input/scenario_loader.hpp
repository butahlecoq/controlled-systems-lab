#pragma once
#include <csl/problem/validator.hpp>
#include <filesystem>
#include <map>

namespace csl::input {
enum class InputCategory { syntax, encoding, schema, field, io, limit };
struct InputFailure {
    InputCategory category;
    std::string path, observed, expected;
    std::optional<std::size_t> byte_offset{};
    std::optional<Diagnostic> canonical{};
};
struct UnsupportedInput {
    std::string feature, path, observed, expected;
    std::optional<Diagnostic> canonical{};
};
struct LoadLimits {
    std::size_t input_bytes{4*1024*1024}, depth{32}, nodes{524288};
    std::size_t string_bytes{4096}, description_bytes{16384};
    std::size_t matrix_coefficients{262144}, dimension{256}, horizon{4096};
    std::size_t expanded_scalars{1048576}, identity_bytes{64*1024*1024};
};
struct LoadOptions {
    LoadLimits limits{};
    optimization::ObjectivePolicy objective_policy{};
    std::stop_token cancellation{};
};
struct ModuleRequest { ModuleId id; std::optional<std::string> version; };
enum class ComparisonRequest { historical_reachability_vs_joint_trajectory };
enum class BackendRole { lp, convex, hull, geometry, converter, approximation, selector };
struct WitnessOptions {
    std::optional<std::size_t> count;
    std::optional<double> distinctness_tolerance;
    std::optional<std::vector<Vector>> directions;
};
// Requested intent only: no resolved module version or effective configuration.
struct RequestedRun {
    std::variant<ComparisonRequest,std::vector<ModuleRequest>> selection{ComparisonRequest::historical_reachability_vs_joint_trajectory};
    std::map<BackendRole,ModuleRequest> backends;
    std::optional<RepresentationId> representation;
    std::optional<WitnessOptions> witnesses;
    std::optional<NumericalPolicy> numerical;
    std::optional<ResourcePolicy> resources;
    std::optional<std::size_t> seed;
};
struct DefaultRecord { std::string path, meaning; bool authored; };
struct ScenarioMetadata {
    std::string id;
    std::optional<std::string> title, description, time_unit;
    std::optional<std::vector<std::string>> state_labels, control_labels, state_units, control_units;
};
struct SourceProvenance {
    problem::ResolvedContent content;
    std::filesystem::path location;
    std::string schema, defaults_revision;
    optimization::ObjectivePolicy publication_policy;
};
struct HistoricalRecord {
    std::string id, restoration_status, execution_gate;
    std::vector<std::string> unresolved;
};
namespace detail { struct ScenarioStorage; struct HistoricalStorage; struct Access; }
class LoadedScenario {
public:
    LoadedScenario(const LoadedScenario&) = default;
    LoadedScenario& operator=(const LoadedScenario&) = default;
    problem::ResolvedProblem problem() const;
    std::shared_ptr<const RequestedRun> requested_run() const noexcept;
    std::shared_ptr<const std::vector<DefaultRecord>> defaults() const noexcept;
    std::shared_ptr<const ScenarioMetadata> metadata() const noexcept;
    std::shared_ptr<const SourceProvenance> source() const noexcept;
private:
    explicit LoadedScenario(std::shared_ptr<const detail::ScenarioStorage>);
    std::shared_ptr<const detail::ScenarioStorage> storage_;
    friend struct detail::Access;
};
class HistoricalScenario {
public:
    HistoricalScenario(const HistoricalScenario&) = default;
    HistoricalScenario& operator=(const HistoricalScenario&) = default;
    std::shared_ptr<const HistoricalRecord> record() const noexcept;
    std::shared_ptr<const SourceProvenance> source() const noexcept;
private:
    explicit HistoricalScenario(std::shared_ptr<const detail::HistoricalStorage>);
    std::shared_ptr<const detail::HistoricalStorage> storage_;
    friend struct detail::Access;
};
using LoadResult=std::variant<LoadedScenario,HistoricalScenario,InputFailure,UnsupportedInput,OperationStopped>;
LoadResult load_scenario(std::span<const std::byte>,const LoadOptions& = {});
LoadResult load_scenario_file(const std::filesystem::path&,const LoadOptions& = {});
} // namespace csl::input
