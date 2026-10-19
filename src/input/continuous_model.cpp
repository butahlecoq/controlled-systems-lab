#include <csl/input/continuous_model.hpp>
#include "scenario_json.hpp"

#include <cmath>
#include <limits>

namespace csl::input {
namespace {
using detail::Json;

class Reader {
    const LoadOptions& options_;
    std::size_t coefficients_{},expanded_{};
    void charge(std::size_t count,const std::string& path) {
        detail::poll(options_);
        if(count>options_.limits.expanded_scalars-expanded_)
            detail::fail(path,"expanded scalar quota exceeded","bounded continuous model",InputCategory::limit);
        expanded_+=count;
    }
public:
    explicit Reader(const LoadOptions& options):options_(options) {}
    std::size_t dimension(const Json& value,const std::string& path) {
        const auto size=detail::count(value,path);
        if(size>options_.limits.dimension)
            detail::fail(path,"dimension exceeds quota","bounded dimension",InputCategory::limit);
        return size;
    }
    Vector vector(const Json& value,std::size_t size,const std::string& path) {
        if(!value.is_array() || value.size()!=size)
            detail::fail(path,"wrong vector shape","array matching the declared dimension");
        charge(size,path);
        Vector result;result.reserve(size);
        for(std::size_t i=0;i<size;++i) {
            detail::poll(options_);
            result.push_back(detail::number(value[i],detail::child(path,std::to_string(i))));
        }
        return result;
    }
    Matrix matrix(const Json& value,std::size_t rows,std::size_t cols,const std::string& path) {
        const Json* flat=nullptr;
        if(value.is_object()) {
            detail::object(value,path,{"rows","cols","values"});
            const auto actual_rows=dimension(detail::member(value,"rows",path),detail::child(path,"rows"));
            const auto actual_cols=dimension(detail::member(value,"cols",path),detail::child(path,"cols"));
            if(actual_rows!=rows || actual_cols!=cols)
                detail::fail(path,"wrong matrix extent","declared continuous coefficient dimensions");
            flat=&detail::member(value,"values",path);
        } else if(!value.is_array())
            detail::fail(path,value.type_name(),"rectangular row arrays or explicit rows/cols/values");
        if(rows && cols>std::numeric_limits<std::size_t>::max()/rows)
            detail::fail(path,"matrix extent overflow","representable matrix",InputCategory::limit);
        const auto entries=rows*cols;
        if(entries>options_.limits.matrix_coefficients-coefficients_)
            detail::fail(path,"coefficient quota exceeded","bounded matrix coefficients",InputCategory::limit);
        coefficients_+=entries;charge(entries,path);
        if(flat) {
            if(!flat->is_array() || flat->size()!=entries)
                detail::fail(detail::child(path,"values"),"wrong flat value count","rows*cols coefficients");
        } else if(value.size()!=rows)
            detail::fail(path,"wrong matrix row count","declared continuous coefficient dimensions");
        Matrix result{rows,cols,{}};result.values.reserve(entries);
        if(flat) {
            for(std::size_t i=0;i<entries;++i) {
                detail::poll(options_);
                result.values.push_back(detail::number((*flat)[i],detail::child(detail::child(path,"values"),std::to_string(i))));
            }
        } else for(std::size_t row=0;row<rows;++row) {
            const auto row_path=detail::child(path,std::to_string(row));
            if(!value[row].is_array() || value[row].size()!=cols)
                detail::fail(row_path,"ragged row","declared matrix width");
            for(std::size_t col=0;col<cols;++col) {
                detail::poll(options_);
                result.values.push_back(detail::number(value[row][col],detail::child(row_path,std::to_string(col))));
            }
        }
        return result;
    }
    LinearStage stage(const Json& value,Dimensions dims,const std::string& path,bool with_kind) {
        if(with_kind)detail::object(value,path,{"kind","A","B","E","offset"});
        else detail::object(value,path,{"A","B","E","offset"});
        return {matrix(detail::member(value,"A",path),dims.state,dims.state,detail::child(path,"A")),
                matrix(detail::member(value,"B",path),dims.state,dims.control,detail::child(path,"B")),
                matrix(detail::member(value,"E",path),dims.state,dims.external,detail::child(path,"E")),
                vector(detail::member(value,"offset",path),dims.state,detail::child(path,"offset"))};
    }
    model::ContinuousCoefficients coefficients(const Json& value,Dimensions dims,
                                                std::size_t intervals) {
        constexpr auto path="/coefficients";
        if(!value.is_object())detail::fail(path,value.type_name(),"continuous coefficient object");
        const auto kind=detail::string(detail::member(value,"kind",path),"/coefficients/kind");
        if(kind=="continuous_descriptor" || kind=="continuous_nonlinear")
            throw UnsupportedInput{kind,"/coefficients/kind",kind,"continuous affine ODE without a mass matrix"};
        if(kind=="continuous_lti")return stage(value,dims,path,true);
        if(kind!="continuous_piecewise_linear_ltv")
            detail::fail("/coefficients/kind",kind,"continuous_lti or continuous_piecewise_linear_ltv");
        detail::object(value,path,{"kind","stages"});
        const auto& stages=detail::member(value,"stages",path);
        if(!stages.is_array() || stages.size()!=intervals)
            detail::fail("/coefficients/stages","wrong interval count","one endpoint pair per physical interval");
        std::vector<model::CoefficientEndpoints> result;result.reserve(intervals);
        for(std::size_t i=0;i<intervals;++i) {
            detail::poll(options_);
            const auto entry=detail::child("/coefficients/stages",std::to_string(i));
            detail::object(stages[i],entry,{"start","end"});
            result.push_back({stage(detail::member(stages[i],"start",entry),dims,detail::child(entry,"start"),false),
                              stage(detail::member(stages[i],"end",entry),dims,detail::child(entry,"end"),false)});
        }
        return result;
    }
};
}

ContinuousModelLoadResult load_continuous_model(std::span<const std::byte> bytes,
                                                const LoadOptions& options) {
    try {
        const auto root=detail::parse(bytes,options);
        detail::object(root,"",{"schema","dimensions","times","hold","coefficients","integration"});
        const auto schema=detail::string(detail::member(root,"schema",""),"/schema");
        if(schema!="csl.continuous-model/1")
            detail::fail("/schema",schema,"csl.continuous-model/1",InputCategory::schema);
        Reader reader(options);
        const auto& dimensions=detail::member(root,"dimensions","");
        detail::object(dimensions,"/dimensions",{"state","control","external"});
        const Dimensions dims{
            reader.dimension(detail::member(dimensions,"state","/dimensions"),"/dimensions/state"),
            reader.dimension(detail::member(dimensions,"control","/dimensions"),"/dimensions/control"),
            reader.dimension(detail::member(dimensions,"external","/dimensions"),"/dimensions/external")};
        const auto& times=detail::member(root,"times","");
        if(!times.is_array() || times.empty() || times.size()>options.limits.horizon+1)
            detail::fail("/times","wrong grid size","one to horizon+1 physical state times",InputCategory::limit);
        Vector grid;grid.reserve(times.size());
        for(std::size_t i=0;i<times.size();++i) {
            detail::poll(options);
            const auto path=detail::child("/times",std::to_string(i));
            const double current=detail::number(times[i],path);
            if(i && (!(grid.back()<current) || !std::isfinite(current-grid.back())))
                detail::fail(path,"nonincreasing or unrepresentable physical duration","strictly increasing finite physical times");
            grid.push_back(current);
        }
        const auto hold=detail::string(detail::member(root,"hold",""),"/hold");
        if(hold!="zero_order_hold")detail::fail("/hold",hold,"zero_order_hold");
        const auto& integration=detail::member(root,"integration","");
        detail::object(integration,"/integration",{"absolute_tolerance","relative_tolerance","max_attempts_per_stage"});
        model::IntegrationOptions numeric;
        numeric.absolute_tolerance=detail::number(detail::member(integration,"absolute_tolerance","/integration"),"/integration/absolute_tolerance");
        numeric.relative_tolerance=detail::number(detail::member(integration,"relative_tolerance","/integration"),"/integration/relative_tolerance");
        numeric.max_attempts_per_stage=detail::count(detail::member(integration,"max_attempts_per_stage","/integration"),"/integration/max_attempts_per_stage");
        if(numeric.absolute_tolerance<=0 || numeric.relative_tolerance<=0 || numeric.max_attempts_per_stage==0)
            detail::fail("/integration","nonpositive setting","positive tolerances and attempt budget");
        numeric.cancellation=options.cancellation;
        auto coefficients=reader.coefficients(detail::member(root,"coefficients",""),dims,grid.size()-1);
        auto content=detail::canonical<problem::ResolvedContent>(problem::snapshot_content(bytes),"");
        detail::poll(options);
        return ContinuousModelInput{{dims,std::move(grid),model::HoldConvention::zero_order_hold,
            std::move(coefficients)},numeric,std::move(content),schema};
    } catch(const InputFailure& failure) {return failure;}
      catch(const UnsupportedInput& unsupported) {return unsupported;}
      catch(const OperationStopped& stopped) {return stopped;}
}
} // namespace csl::input
