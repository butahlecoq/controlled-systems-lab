#include <csl/model/discretization.hpp>
#include "internal.hpp"

#include <cmath>
#include <limits>
#include <utility>

namespace csl::model {
namespace {
Diagnostic invalid(const char* field,const char* explanation) {
    return {DiagnosticCode::invalid_input,field,explanation};
}
bool valid(const Matrix& matrix,std::size_t rows,std::size_t cols) {
    if(matrix.rows!=rows || matrix.cols!=cols ||
       (rows && cols>std::numeric_limits<std::size_t>::max()/rows) ||
       matrix.values.size()!=rows*cols)return false;
    for(double value:matrix.values)if(!std::isfinite(value))return false;
    return true;
}
bool valid(const LinearStage& stage,Dimensions d) {
    if(!valid(stage.A,d.state,d.state) || !valid(stage.B,d.state,d.control) ||
       !valid(stage.E,d.state,d.external) || stage.offset.size()!=d.state)return false;
    for(double value:stage.offset)if(!std::isfinite(value))return false;
    return true;
}
}

DiscretizationResult discretize(const ContinuousAffineModel& source,
                                const IntegrationOptions& options) {
    if(options.cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,"Continuous-model discretization cancelled"};
    if(source.hold!=HoldConvention::zero_order_hold)
        return Diagnostic{DiagnosticCode::unsupported,"model.hold","Only zero-order hold is supported"};
    if(!std::isfinite(options.absolute_tolerance) || options.absolute_tolerance<=0 ||
       !std::isfinite(options.relative_tolerance) || options.relative_tolerance<=0 ||
       options.max_attempts_per_stage==0)
        return invalid("model.integration","Positive finite tolerances and a positive attempt budget are required");
    if(source.times.empty())return invalid("model.times","At least one physical state time is required");
    for(std::size_t i=0;i<source.times.size();++i) {
        if(!std::isfinite(source.times[i]))
            return invalid("model.times","Physical state times must be finite");
        if(i && (!(source.times[i-1]<source.times[i]) ||
                 !std::isfinite(source.times[i]-source.times[i-1])))
            return invalid("model.times","Physical intervals must have finite positive duration");
    }
    const auto count=source.times.size()-1;
    if(const auto* constant=std::get_if<LinearStage>(&source.coefficients)) {
        if(!valid(*constant,source.dimensions))
            return invalid("model.coefficients","Constant continuous coefficients must be finite and dimensionally valid");
    } else {
        const auto& indexed=std::get<std::vector<CoefficientEndpoints>>(source.coefficients);
        if(indexed.size()!=count)
            return invalid("model.coefficients","LTV endpoint count must match the physical intervals");
        for(const auto& interval:indexed)
            if(!valid(interval.start,source.dimensions) || !valid(interval.end,source.dimensions))
                return invalid("model.coefficients","LTV endpoints must be finite and dimensionally valid");
    }
    std::vector<LinearStage> stages;
    stages.reserve(count);
    DiscretizationReceipt receipt{TimeDomain::continuous,TimeDomain::discrete,
        source.hold,std::holds_alternative<LinearStage>(source.coefficients)
            ? CoefficientVariation::constant_lti
            : CoefficientVariation::piecewise_linear_ltv,
        source.coefficients,
        "rk4_step_doubling",
        "Observed RK4 step-doubling local difference divided by 15; not a certified global error bound",
        options.absolute_tolerance,options.relative_tolerance,{}};
    receipt.stages.reserve(count);
    for(std::size_t i=0;i<count;++i) {
        if(options.cancellation.stop_requested())
            return OperationStopped{StopReason::cancelled,"Continuous-model discretization cancelled"};
        const LinearStage* start;
        const LinearStage* end;
        if(const auto* constant=std::get_if<LinearStage>(&source.coefficients)) {
            start=end=constant;
        } else {
            const auto& interval=std::get<std::vector<CoefficientEndpoints>>(source.coefficients)[i];
            start=&interval.start;end=&interval.end;
        }
        auto integrated=detail::integrate_stage(*start,*end,source.dimensions,
            source.times[i],source.times[i+1],options);
        if(const auto* stopped=std::get_if<OperationStopped>(&integrated))return *stopped;
        auto result=std::get<detail::IntegratedStage>(std::move(integrated));
        stages.push_back(std::move(result.coefficients));
        receipt.stages.push_back(result.receipt);
    }
    return DiscretizedModel{SystemModel{{source.dimensions,TimeDomain::discrete,
        std::move(stages)},{}},source.times,std::move(receipt)};
}
} // namespace csl::model
