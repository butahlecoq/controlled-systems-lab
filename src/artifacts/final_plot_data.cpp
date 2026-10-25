#include <csl/artifacts/plot_data.hpp>

#include <cmath>
#include <algorithm>

namespace csl::artifacts {
namespace {
ArtifactError error(ArtifactErrorCode code, std::string path, std::string message) {
    return {code, std::move(path), std::move(message)};
}
bool equal_history(const std::vector<Vector>& a, const std::vector<Vector>& b) {
    if (a.size()!=b.size()) return false;
    for (std::size_t i=0;i<a.size();++i) if (a[i]!=b[i]) return false;
    return true;
}
}

ArtifactResult<PlotData> prepare_plot_data(const problem::ResolvedProblem& problem,
    const RunStatistics& statistics, std::span<const verification::TrajectoryReport> reports,
    const PlotMetadata& metadata) {
    const auto& record=statistics.description();
    const auto dimensions=problem.model().dimensions();
    const auto horizon=problem.model().horizon();
    if (record.problem!=problem.identity()) return error(ArtifactErrorCode::identity,"run.problem","run belongs to a different problem");
    if (record.statistics.description().problem!=problem.identity() || record.statistics.description().run!=record.run) return error(ArtifactErrorCode::identity,"run.statistics.identity","collection statistics do not bind to this problem and run");
    if (record.dimensions!=dimensions || record.horizon!=horizon) return error(ArtifactErrorCode::identity,"run.dimensions","run dimensions or horizon do not match the resolved problem");
    if (!record.selection) return error(ArtifactErrorCode::invalid_input,"run.selection","run contains no selected witness batch");
    const auto& batch=record.selection->batch;
    if (metadata.states.size() && metadata.states.size()!=dimensions.state) return error(ArtifactErrorCode::invalid_input,"metadata.states","state metadata count does not match state dimension");
    if (metadata.controls.size() && metadata.controls.size()!=dimensions.control) return error(ArtifactErrorCode::invalid_input,"metadata.controls","control metadata count does not match control dimension");
    const auto validate_annotations=[](const std::vector<CoordinateAnnotation>& coordinates, const std::string& path) -> std::optional<ArtifactError> {
        for(std::size_t i=0;i<coordinates.size();++i) {
            const auto& c=coordinates[i]; const auto p=path+"["+std::to_string(i)+"]";
            if(c.target && (!std::isfinite(c.target->value) || c.target->source.empty())) return error(ArtifactErrorCode::invalid_input,p+".target","target must be finite and have a source reference");
            if(c.bounds && (!std::isfinite(c.bounds->first.value)||!std::isfinite(c.bounds->second.value)||c.bounds->first.value>c.bounds->second.value||c.bounds->first.source.empty()||c.bounds->second.source.empty())) return error(ArtifactErrorCode::invalid_input,p+".bounds","bounds must be finite, ordered, and have source references");
        }
        return {};
    };
    if(auto e=validate_annotations(metadata.states,"metadata.states")) return *e;
    if(auto e=validate_annotations(metadata.controls,"metadata.controls")) return *e;
    auto strategy=record.configuration.description().strategy.strategy;
    auto module=std::find_if(record.configuration.description().modules.begin(),record.configuration.description().modules.end(),[&](const auto& m){return m.role=="strategy"&&m.implementation.id==strategy;});
    if (module==record.configuration.description().modules.end()) return error(ArtifactErrorCode::reference,"run.configuration.strategy","strategy identity is absent from configuration");
    PlotData result; result.problem=problem.identity(); result.run=record.run; result.strategy=strategy; result.strategy_version=module->implementation.version;
    const auto* final=std::get_if<SynthesisFinal>(&record.final);
    result.family_evidence.recorded_claim=false;
    result.family_evidence.current_process_verified=false;
    if(final && final->family) {
        const auto& identity=final->family->family.identity();
        if(identity.problem!=problem.identity() || identity.strategy!=strategy || identity.strategy_version!=module->implementation.version)
            return error(ArtifactErrorCode::identity,"run.final.family.identity","recorded family identity does not match the resolved problem and strategy configuration");
        if(batch.source_family && *batch.source_family!=identity)
            return error(ArtifactErrorCode::reference,"run.selection.source_family","selected witnesses do not match the run's recorded family");
        result.family_evidence.recorded_claim=batch.source_family.has_value();
        result.family_evidence.current_process_verified=batch.source_family.has_value() &&
            final->family->family.registry_verified() &&
            record.provenance==ProblemProvenance::problem_revalidated;
    } else if(batch.source_family) {
        return error(ArtifactErrorCode::reference,"run.selection.source_family","selected witnesses refer to a family absent from the run record");
    }
    result.states.coordinates=metadata.states; result.controls.coordinates=metadata.controls;
    if (result.states.coordinates.empty()) result.states.coordinates.resize(dimensions.state);
    if (result.controls.coordinates.empty()) result.controls.coordinates.resize(dimensions.control);
    result.state_axis.points.resize(horizon+1); result.control_axis.points.resize(horizon); result.control_axis.interval_ends.resize(horizon);
    bool have_times=metadata.time_unit.has_value();
    std::vector<double> times; times.reserve(horizon+1);
    if (have_times) for (std::size_t i=0;i<=horizon;++i) {
        auto time=problem.model().time(StageIndex{i});
        if (!std::holds_alternative<double>(time)) { have_times=false; break; }
        times.push_back(std::get<double>(time));
    }
    if (have_times) {
        result.state_axis.kind=PlotAxis::Kind::physical_time; result.state_axis.points=times; result.state_axis.unit=metadata.time_unit;
        result.control_axis.kind=PlotAxis::Kind::physical_time; result.control_axis.unit=metadata.time_unit;
        for (std::size_t i=0;i<horizon;++i) { result.control_axis.points[i]=times[i]; result.control_axis.interval_ends[i]=times[i+1]; }
    } else {
        result.state_axis.kind=PlotAxis::Kind::stage; result.control_axis.kind=PlotAxis::Kind::stage;
        for(std::size_t i=0;i<=horizon;++i) result.state_axis.points[i]=static_cast<double>(i);
        for(std::size_t i=0;i<horizon;++i) { result.control_axis.points[i]=static_cast<double>(i); result.control_axis.interval_ends[i]=static_cast<double>(i+1); }
    }
    if(reports.size()!=batch.witnesses.size()) return error(ArtifactErrorCode::reference,"reports","report count must match selected witness count");
    for(std::size_t i=0;i<batch.witnesses.size();++i) {
        const auto& witness=batch.witnesses[i]; const auto& report=reports[i];
        if(witness.problem!=problem.identity() || report.problem!=problem.identity() || report.input.witness.problem!=problem.identity()) return error(ArtifactErrorCode::identity,"witnesses["+std::to_string(i)+"].problem","witness or verifier report belongs to a different problem");
        if(!equal_history(witness.states,report.input.witness.states)||!equal_history(witness.controls,report.input.witness.controls)) return error(ArtifactErrorCode::reference,"reports["+std::to_string(i)+"].input.witness","verifier report does not bind the selected witness at this source ordinal");
        if(witness.original_objective!=report.input.witness.original_objective) return error(ArtifactErrorCode::reference,"reports["+std::to_string(i)+"].input.witness.objective","verifier report objective does not bind the selected witness");
        if(report.input.expected_synthesis) {
            if(report.input.expected_synthesis->strategy!=strategy || report.input.expected_synthesis->strategy_version!=module->implementation.version) return error(ArtifactErrorCode::identity,"reports["+std::to_string(i)+"].input.expected_synthesis","verifier report strategy binding does not match the run configuration");
            if(!final || !final->family) return error(ArtifactErrorCode::reference,"reports["+std::to_string(i)+"].input.expected_synthesis","verifier family binding has no recorded run family");
            const auto& family=final->family->family.identity(); const auto& expected=*report.input.expected_synthesis;
            if(expected.request!=family.request || expected.lineage!=family.lineage)
                return error(ArtifactErrorCode::reference,"reports["+std::to_string(i)+"].input.expected_synthesis","verifier request or lineage does not match the recorded family");
        }
        if(report.input.family) {
            if(!final || !final->family || report.input.family->identity()!=final->family->family.identity()) return error(ArtifactErrorCode::reference,"reports["+std::to_string(i)+"].input.family","verifier report family does not match the run's recorded family");
        }
        if(witness.states.size()!=horizon+1) return error(ArtifactErrorCode::invalid_input,"witnesses["+std::to_string(i)+"].states","expected T+1 state points");
        if(witness.controls.size()!=horizon) return error(ArtifactErrorCode::invalid_input,"witnesses["+std::to_string(i)+"].controls","expected T control intervals");
        for(std::size_t t=0;t<witness.states.size();++t) {
            if(witness.states[t].size()!=dimensions.state) return error(ArtifactErrorCode::invalid_input,"witnesses["+std::to_string(i)+"].states["+std::to_string(t)+"]","state coordinate count mismatch");
            for(std::size_t c=0;c<dimensions.state;++c) if(!std::isfinite(witness.states[t][c])) return error(ArtifactErrorCode::invalid_input,"witnesses["+std::to_string(i)+"].states["+std::to_string(t)+"]["+std::to_string(c)+"]","nonfinite plotted value");
        }
        for(std::size_t t=0;t<witness.controls.size();++t) {
            if(witness.controls[t].size()!=dimensions.control) return error(ArtifactErrorCode::invalid_input,"witnesses["+std::to_string(i)+"].controls["+std::to_string(t)+"]","control coordinate count mismatch");
            for(std::size_t c=0;c<dimensions.control;++c) if(!std::isfinite(witness.controls[t][c])) return error(ArtifactErrorCode::invalid_input,"witnesses["+std::to_string(i)+"].controls["+std::to_string(t)+"]["+std::to_string(c)+"]","nonfinite plotted value");
        }
        if(!std::isfinite(witness.original_objective)) return error(ArtifactErrorCode::invalid_input,"witnesses["+std::to_string(i)+"].objective","nonfinite objective");
        result.paths.push_back({record.run,i,strategy,module->implementation.version,witness.states,witness.controls,witness.original_objective,
            {report.bindings,report.feasibility,report.objective,report.optimality,report.completeness,report.validated,report.residuals}});
    }
    result.selection={batch.requested,batch.returned_count(),batch.distinct_count(),batch.returned_count()-batch.distinct_count(),batch.distinctness_tolerance,record.selection->diagnostics};
    return result;
}
}
