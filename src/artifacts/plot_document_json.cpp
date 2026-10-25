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
const char* relation(SetRelation value) {
    switch(value) {
    case SetRelation::equivalent:return "equivalent";
    case SetRelation::inner:return "inner";
    case SetRelation::outer:return "outer";
    case SetRelation::heuristic:return "heuristic";
    }
    return "unknown";
}
std::string support_kind(const EvidenceSupport& support) {
    return std::visit([](const auto& value)->std::string {
        using T=std::decay_t<decltype(value)>;
        if constexpr(std::is_same_v<T,Unestablished>)return "unestablished";
        else if constexpr(std::is_same_v<T,NumericalCheck>)return "numerical_check";
        else if constexpr(std::is_same_v<T,SymbolicArgument>)return "symbolic_argument";
        else if constexpr(std::is_same_v<T,CertificateReference>)return "unchecked_certificate_reference";
        else return "exact_farkas_evidence";
    },support);
}
std::optional<std::size_t> coordinate_index(const std::vector<CoordinateAnnotation>& values,
    const CoordinateAnnotation& selected) {
    std::optional<std::size_t> found;
    for(std::size_t i=0;i<values.size();++i) {
        if(values[i].label==selected.label&&values[i].unit==selected.unit) {
            if(found)return {};
            found=i;
        }
    }
    return found;
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

ArtifactResult<std::string> encode_plot_document_json(const PlotData& data,const PlotOutcome& outcome,
    std::string_view source_record_schema,std::string_view source_record_sha256) {
    const auto* projection=std::get_if<PlotSetProjection>(&outcome);
    const auto* samples=std::get_if<PlotSupportSamples>(&outcome);
    if(!projection&&!samples)return error(ArtifactErrorCode::unsupported,"plot_outcome",
        "only completed projection and support-sample outcomes can be persisted by this overload");
    const auto& problem=projection?projection->problem:samples->problem;
    const auto& source=projection?projection->source:samples->source;
    const auto stage=projection?projection->stage:samples->stage;
    const auto& selected_coordinates=projection?projection->coordinates:samples->coordinates;
    const auto& provider_provenance=projection?projection->provider:samples->provider;
    if(problem!=data.problem)return error(ArtifactErrorCode::reference,"plot_outcome.problem",
        "plot outcome and plot data must refer to the same problem");
    const auto first=coordinate_index(data.states.coordinates,selected_coordinates[0]);
    const auto second=coordinate_index(data.states.coordinates,selected_coordinates[1]);
    if(!first||!second||*first==*second)return error(ArtifactErrorCode::reference,"plot_outcome.coordinates",
        "projection coordinates must uniquely match two distinct PlotData state coordinates");
    if(!provider_provenance.actual)return error(ArtifactErrorCode::reference,"plot_outcome.provider",
        "projection provider identity is required");
    if(source.problem!=data.problem)return error(ArtifactErrorCode::reference,"plot_outcome.source",
        "projection source must refer to the PlotData problem");
    if(stage.value>=data.state_axis.points.size())return error(ArtifactErrorCode::reference,
        "plot_outcome.stage","projection stage is outside the saved state axis");

    auto encoded=encode_plot_document_json(data,source_record_schema,source_record_sha256);
    if(const auto* failure=std::get_if<ArtifactError>(&encoded))return *failure;
    auto document=Json::parse(std::get<std::string>(encoded));
    const auto owner=std::visit([](const auto& identity)->std::pair<std::string,std::string> {
        using T=std::decay_t<decltype(identity)>;
        if constexpr(std::is_same_v<T,SetId>)return {"set",identity.value};
        else return {"optimal_family",identity.strategy.value+"@"+identity.strategy_version};
    },source.identity);
    const auto& provider=*provider_provenance.actual;
    Json item;
    if(projection) {
        if(projection->reference.identity.problem!=data.problem)return error(ArtifactErrorCode::reference,
            "plot_outcome.geometry_reference","geometry reference must refer to the PlotData problem");
        if(projection->projected_relation.metadata.dimension!=2)return error(ArtifactErrorCode::reference,
            "plot_outcome.projected_relation","projection output must be two-dimensional");
        const auto set=sets::from_handle(projection->projected_relation);
        if(const auto* failure=std::get_if<Diagnostic>(&set))return error(ArtifactErrorCode::unsupported,
            "plot_outcome.projected_relation",failure->field+": "+failure->explanation);
        const auto representation=std::get<sets::SetData>(set).representation();
        Json points=Json::array();
        if(const auto* vertices=std::get_if<sets::VRepresentation>(&representation)) {
            if(vertices->vertices.cols()!=2||vertices->rays.rows()!=0)
                return error(ArtifactErrorCode::unsupported,"plot_outcome.projected_relation",
                    "only bounded finite 2D vertex representations are supported");
            for(std::size_t i=0;i<vertices->vertices.rows();++i) {
                const double x=vertices->vertices(i,0),y=vertices->vertices(i,1);
                if(!std::isfinite(x)||!std::isfinite(y))return error(ArtifactErrorCode::invalid_input,
                    "plot_outcome.projected_relation.vertices","projection contains a nonfinite coordinate");
                points.push_back({x,y});
            }
        } else if(const auto* singleton=std::get_if<sets::SingletonRepresentation>(&representation)) {
            if(singleton->point.size()!=2)return error(ArtifactErrorCode::unsupported,
                "plot_outcome.projected_relation","singleton projection must have dimension two");
            points.push_back({singleton->point[0],singleton->point[1]});
        } else return error(ArtifactErrorCode::unsupported,"plot_outcome.projected_relation",
            "projection representation has no finite point list");
        if(points.empty())return error(ArtifactErrorCode::unsupported,"plot_outcome.projected_relation",
            "empty projection has no points to draw");
        item={{"kind","projection"},
            {"source",{{"kind",owner.first},{"id",owner.second},{"method_id",provider.id.value},{"method_version",provider.version}}},
            {"title","Saved 2D set projection at stage "+std::to_string(stage.value)},
            {"scenario_id",problem.value},{"coordinate_ids",{"x"+std::to_string(*first),"x"+std::to_string(*second)}},
            {"points",std::move(points)},{"relation",relation(projection->relation)},
            {"evidence","geometry evidence support: "+support_kind(projection->support)},
            {"limitation","persisted finite projection points; rendering does not compute geometry"},
            {"objective_context","not applicable to a set projection"},
            {"geometry_reference",{{"problem",projection->reference.identity.problem.value},
                {"request",projection->reference.identity.request.value},{"ideal_output",projection->reference.identity.ideal_output.value}}},
            {"assumptions",projection->assumptions},
            {"geometry_operation_elapsed_ns",projection->cost.geometry_operation_elapsed.count()}};
    } else {
        Json points=Json::array(),records=Json::array();
        std::size_t without_point=0;
        for(std::size_t i=0;i<samples->samples.size();++i) {
            const auto& sample=samples->samples[i];
            if(sample.reference.identity.problem!=data.problem)return error(ArtifactErrorCode::reference,
                "plot_outcome.samples["+std::to_string(i)+"].reference","support sample reference problem mismatch");
            if(!std::isfinite(sample.direction[0])||!std::isfinite(sample.direction[1])||
                (sample.direction[0]==0.0&&sample.direction[1]==0.0))return error(ArtifactErrorCode::invalid_input,
                    "plot_outcome.samples["+std::to_string(i)+"].direction","support direction must be finite and nonzero");
            Json record={{"direction",sample.direction},
                {"evidence_support",support_kind(sample.support)},
                {"assumptions",sample.assumptions},
                {"geometry_reference",{{"request",sample.reference.identity.request.value},
                    {"ideal_output",sample.reference.identity.ideal_output.value}}}};
            if(const auto* value=std::get_if<double>(&sample.value)) {
                if(!std::isfinite(*value))return error(ArtifactErrorCode::invalid_input,
                    "plot_outcome.samples["+std::to_string(i)+"].value","support value must be finite");
                record["value"]={{"kind","finite"},{"value",*value}};
            } else if(std::holds_alternative<EmptySupport>(sample.value))record["value"]={{"kind","empty"}};
            else record["value"]={{"kind","unbounded"}};
            if(sample.point) {
                if(!std::isfinite((*sample.point)[0])||!std::isfinite((*sample.point)[1]))return error(ArtifactErrorCode::invalid_input,
                    "plot_outcome.samples["+std::to_string(i)+"].point","support point must be finite");
                record["point"]={(*sample.point)[0],(*sample.point)[1]};
                points.push_back(record["point"]);
            } else ++without_point;
            records.push_back(std::move(record));
        }
        if(records.empty())return error(ArtifactErrorCode::invalid_input,"plot_outcome.samples",
            "at least one support sample is required");
        item={{"kind","support_samples"},
            {"source",{{"kind",owner.first},{"id",owner.second},{"method_id",provider.id.value},{"method_version",provider.version}}},
            {"title","Support samples at stage "+std::to_string(stage.value)},
            {"scenario_id",problem.value},{"coordinate_ids",{"x"+std::to_string(*first),"x"+std::to_string(*second)}},
            {"points",std::move(points)},{"samples",std::move(records)},
            {"relation","directional support samples"},
            {"evidence","geometry support values returned by the selected provider"},
            {"limitation","finite directional samples are not a complete boundary; "+std::to_string(without_point)+" samples have no finite maximizing point"},
            {"objective_context","not applicable to support samples"},
            {"assumptions",Json::array()},
            {"geometry_operation_elapsed_ns",samples->cost.geometry_operation_elapsed.count()}};
    }
    document["series"].push_back(std::move(item));
    return document.dump(2)+"\n";
}
} // namespace csl::artifacts
