#pragma once

#include <csl/artifacts/run_statistics.hpp>
#include <csl/verification/trajectory.hpp>

namespace csl::artifacts {

struct CoordinateAnnotation {
    std::optional<std::string> label, unit;
    struct ReferencedValue { double value; std::string source; };
    std::optional<ReferencedValue> target;
    std::optional<std::pair<ReferencedValue, ReferencedValue>> bounds;
};
struct PlotMetadata {
    std::optional<std::string> time_unit;
    std::vector<CoordinateAnnotation> states, controls;
};
struct PlotAxis {
    enum class Kind { stage, physical_time } kind{Kind::stage};
    std::vector<double> points;
    std::vector<double> interval_ends;
    std::optional<std::string> unit;
};
enum class ControlHold { left };
struct PlotCoordinates { std::vector<CoordinateAnnotation> coordinates; };
struct PlotEvidence {
    verification::CheckStatus bindings, feasibility, objective, optimality, completeness, validated;
    std::vector<verification::NamedResidual> residuals;
};
struct PlotPath {
    RunId run;
    std::size_t source_ordinal;
    ModuleId strategy;
    std::string strategy_version;
    std::vector<Vector> states, controls;
    double objective;
    PlotEvidence evidence;
};
struct PlotSelectionCounts {
    std::size_t requested{}, returned{}, distinct{}, duplicates{};
    double distinctness_tolerance{};
    std::string diagnostics;
};
struct PlotFamilyEvidence { bool recorded_claim{}; bool current_process_verified{}; };
struct PlotData {
    ProblemId problem;
    RunId run;
    ModuleId strategy;
    std::string strategy_version;
    PlotAxis state_axis, control_axis;
    ControlHold control_hold{ControlHold::left};
    PlotCoordinates states, controls;
    std::vector<PlotPath> paths;
    PlotSelectionCounts selection;
    PlotFamilyEvidence family_evidence;
};

ArtifactResult<PlotData> prepare_plot_data(const problem::ResolvedProblem&, const RunStatistics&,
    std::span<const verification::TrajectoryReport>, const PlotMetadata& = {});

}
