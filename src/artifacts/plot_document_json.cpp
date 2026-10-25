#include <csl/artifacts/plot_document_json.hpp>
#include <nlohmann/json.hpp>

#include <cmath>
#include <algorithm>

namespace csl::artifacts {
namespace {
using Json=nlohmann::json;

ArtifactError error(ArtifactErrorCode code,std::string path,std::string message) {
    return {code,std::move(path),std::move(message)};
}
bool digest(std::string_view value) {
    return value.size()==64&&std::all_of(value.begin(),value.end(),[](char c){return (c>='0'&&c<='9')||(c>='a'&&c<='f');});
}
const char* status(verification::CheckStatus value) {
    switch(value) {
    case verification::CheckStatus::not_checked:return "not_checked";
    case verification::CheckStatus::numerical_pass:return "numerical_pass";
    case verification::CheckStatus::violation:return "violation";
    case verification::CheckStatus::invalid_input:return "invalid_input";
    case verification::CheckStatus::unsupported:return "unsupported";
    }
    return "unsupported";
}
Json coordinates(const std::vector<CoordinateAnnotation>& values,std::string_view prefix) {
    Json out=Json::array();
    for(std::size_t i=0;i<values.size();++i) {
        const auto& value=values[i];
        out.push_back({{"id",std::string(prefix)+std::to_string(i)},
            {"name",value.label.value_or(std::string(prefix)+std::to_string(i))},
            {"unit",value.unit?Json(*value.unit):Json(nullptr)}});
    }
    return out;
}
Json axis(const PlotAxis& value,bool controls) {
    Json result={{"kind",value.kind==PlotAxis::Kind::physical_time?"physical_time":"stage"},
                 {"points",value.points},{"label",value.kind==PlotAxis::Kind::physical_time?"time":"stage"}};
    if(controls)result["interval_ends"]=value.interval_ends;
    return result;
}
}

ArtifactResult<std::string> encode_plot_document_json(const PlotData& data,
    std::string_view source_record_schema,std::string_view source_record_sha256) {
    if(source_record_schema.empty())return error(ArtifactErrorCode::invalid_input,"source_record_schema","Source record schema is required");
    if(!digest(source_record_sha256))return error(ArtifactErrorCode::invalid_input,"source_record_sha256","Expected lowercase SHA-256 digest");
    if(data.problem.value.empty()||data.run.value.empty()||data.strategy.value.empty()||data.strategy_version.empty())
        return error(ArtifactErrorCode::invalid_input,"plot_data.identity","Problem, run, strategy and version identities are required");
    if(data.states.coordinates.size()==0||data.state_axis.points.empty())
        return error(ArtifactErrorCode::invalid_input,"plot_data.states","State coordinates and state axis are required");
    if(data.paths.empty())return error(ArtifactErrorCode::invalid_input,"plot_data.paths","At least one selected witness is required");
    if(data.state_axis.points.size()!=data.control_axis.points.size()+1||
       data.control_axis.interval_ends.size()!=data.control_axis.points.size())
        return error(ArtifactErrorCode::invalid_input,"plot_data.axes","Expected T+1 state points and T control intervals");
    for(double value:data.state_axis.points)if(!std::isfinite(value))return error(ArtifactErrorCode::invalid_input,"plot_data.state_axis","Nonfinite axis value");
    for(std::size_t i=0;i<data.control_axis.points.size();++i)
        if(!std::isfinite(data.control_axis.points[i])||!std::isfinite(data.control_axis.interval_ends[i])||data.control_axis.interval_ends[i]<=data.control_axis.points[i])
            return error(ArtifactErrorCode::invalid_input,"plot_data.control_axis","Control intervals must be finite and ordered");
    Json series=Json::array();
    for(std::size_t p=0;p<data.paths.size();++p) {
        const auto& path=data.paths[p];
        if(path.run!=data.run||path.states.size()!=data.state_axis.points.size()||path.controls.size()!=data.control_axis.points.size())
            return error(ArtifactErrorCode::reference,"plot_data.paths["+std::to_string(p)+"]","Trajectory identity or stage count does not match PlotData");
        for(std::size_t t=0;t<path.states.size();++t) {
            if(path.states[t].size()!=data.states.coordinates.size())return error(ArtifactErrorCode::invalid_input,"plot_data.states","State coordinate count mismatch");
            for(double value:path.states[t])if(!std::isfinite(value))return error(ArtifactErrorCode::invalid_input,"plot_data.states","Nonfinite state value");
        }
        for(std::size_t t=0;t<path.controls.size();++t) {
            if(path.controls[t].size()!=data.controls.coordinates.size())return error(ArtifactErrorCode::invalid_input,"plot_data.controls","Control coordinate count mismatch");
            for(double value:path.controls[t])if(!std::isfinite(value))return error(ArtifactErrorCode::invalid_input,"plot_data.controls","Nonfinite control value");
        }
        if(!std::isfinite(path.objective))return error(ArtifactErrorCode::invalid_input,"plot_data.objective","Nonfinite objective");
        Json states=Json::array(),controls=Json::array();
        for(const auto& row:path.states)states.push_back(row);
        for(const auto& row:path.controls)controls.push_back(row);
        const auto& e=path.evidence;
        series.push_back({{"kind","trajectory"},
            {"source",{{"kind","run"},{"id",path.run.value},{"method_id",path.strategy.value},{"method_version",path.strategy_version}}},
            {"witness_id","witness-"+std::to_string(path.source_ordinal)},
            {"state_coordinate_ids",[&](){Json ids=Json::array();for(std::size_t i=0;i<data.states.coordinates.size();++i)ids.push_back("x"+std::to_string(i));return ids;}()},
            {"control_coordinate_ids",[&](){Json ids=Json::array();for(std::size_t i=0;i<data.controls.coordinates.size();++i)ids.push_back("u"+std::to_string(i));return ids;}()},
            {"states",std::move(states)},{"controls",std::move(controls)},
            {"objective",path.objective},{"objective_label","selected witness objective"},
            {"objective_evidence",status(e.objective)},
            {"evidence",std::string("bindings=")+status(e.bindings)+", feasibility="+status(e.feasibility)+", objective="+status(e.objective)+", optimality="+status(e.optimality)+", completeness="+status(e.completeness)},
            {"assurance",status(e.validated)},
            {"approximation","selected witness only; not the full feasible or optimal family"}});
    }
    Json document={{"schema","csl.plot-document/1"},
        {"provenance",{{"record_schema",source_record_schema},{"record_id",data.run.value},
            {"source_sha256",source_record_sha256},{"scenario_id",data.problem.value},
            {"method_id",data.strategy.value},{"method_version",data.strategy_version}}},
        {"coordinates",{{"states",coordinates(data.states.coordinates,"x")},{"controls",coordinates(data.controls.coordinates,"u")}}},
        {"axes",{{"states",axis(data.state_axis,false)},{"controls",axis(data.control_axis,true)}}},
        {"series",std::move(series)}};
    return document.dump(2)+"\n";
}
} // namespace csl::artifacts
