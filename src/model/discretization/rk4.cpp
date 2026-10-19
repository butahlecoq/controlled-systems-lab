#include "internal.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <optional>

namespace csl::model::detail {
namespace {
using State=Vector;

OperationStopped failure(StopReason reason,const char* message) {
    return {reason,message};
}
std::optional<State> derivative(const LinearStage& start,const LinearStage& end,
                                Dimensions d,double t0,double t1,double t,
                                const State& state,std::size_t width) {
    const double alpha=std::clamp((t-t0)/(t1-t0),0.0,1.0);
    if(!std::isfinite(alpha))return std::nullopt;
    State result(state.size(),0);
    for(std::size_t row=0;row<d.state;++row) {
        for(std::size_t column=0;column<width;++column) {
            double value=0;
            for(std::size_t k=0;k<d.state;++k) {
                const double a=std::lerp(start.A.values[row*d.state+k],
                                         end.A.values[row*d.state+k],alpha);
                value+=a*state[k*width+column];
                if(!std::isfinite(value))return std::nullopt;
            }
            if(column>=d.state) {
                const auto port=column-d.state;
                double forcing;
                if(port<d.control)
                    forcing=std::lerp(start.B.values[row*d.control+port],
                                      end.B.values[row*d.control+port],alpha);
                else if(port-d.control<d.external) {
                    const auto external=port-d.control;
                    forcing=std::lerp(start.E.values[row*d.external+external],
                                      end.E.values[row*d.external+external],alpha);
                } else forcing=std::lerp(start.offset[row],end.offset[row],alpha);
                value+=forcing;
                if(!std::isfinite(value))return std::nullopt;
            }
            result[row*width+column]=value;
        }
    }
    return result;
}
std::optional<State> add_scaled(const State& base,const State& direction,double scale) {
    State result(base.size());
    for(std::size_t i=0;i<base.size();++i) {
        result[i]=base[i]+scale*direction[i];
        if(!std::isfinite(result[i]))return std::nullopt;
    }
    return result;
}
std::optional<State> rk4(const LinearStage& start,const LinearStage& end,
                         Dimensions d,double t0,double t1,double t,double h,
                         const State& state,std::size_t width) {
    const auto k1=derivative(start,end,d,t0,t1,t,state,width);
    if(!k1)return std::nullopt;
    const auto y2=add_scaled(state,*k1,h/2);
    if(!y2)return std::nullopt;
    const auto k2=derivative(start,end,d,t0,t1,t+h/2,*y2,width);
    if(!k2)return std::nullopt;
    const auto y3=add_scaled(state,*k2,h/2);
    if(!y3)return std::nullopt;
    const auto k3=derivative(start,end,d,t0,t1,t+h/2,*y3,width);
    if(!k3)return std::nullopt;
    const auto y4=add_scaled(state,*k3,h);
    if(!y4)return std::nullopt;
    const auto k4=derivative(start,end,d,t0,t1,t+h,*y4,width);
    if(!k4)return std::nullopt;
    State result(state.size());
    for(std::size_t i=0;i<state.size();++i) {
        result[i]=state[i]+(h/6)*((*k1)[i]+2*(*k2)[i]+2*(*k3)[i]+(*k4)[i]);
        if(!std::isfinite(result[i]))return std::nullopt;
    }
    return result;
}
}

IntegrationResult integrate_stage(const LinearStage& start,const LinearStage& end,
                                  Dimensions d,double t0,double t1,
                                  const IntegrationOptions& options) {
    constexpr auto maximum=std::numeric_limits<std::size_t>::max();
    if(d.state>maximum-d.control)
        return failure(StopReason::resource_limit,"Augmented transition width overflows");
    const auto prefix=d.state+d.control;
    if(prefix==maximum || d.external>maximum-prefix-1)
        return failure(StopReason::resource_limit,"Augmented transition width overflows");
    const auto width=d.state+d.control+d.external+1;
    if(d.state && width>std::numeric_limits<std::size_t>::max()/d.state)
        return failure(StopReason::resource_limit,"Augmented transition storage overflows");
    State state(d.state*width,0);
    for(std::size_t i=0;i<d.state;++i)state[i*width+i]=1;
    StageIntegrationReceipt receipt{t0,t1,0,0,0};
    double t=t0,h=t1-t0;
    while(t<t1 && d.state) {
        if(options.cancellation.stop_requested())
            return failure(StopReason::cancelled,"Continuous-model integration cancelled");
        if(receipt.accepted_steps+receipt.rejected_steps>=options.max_attempts_per_stage)
            return failure(StopReason::resource_limit,"Continuous-model step budget exhausted");
        h=std::min(h,t1-t);
        const double next=std::min(t+h,t1),mid=t+(next-t)/2;
        if(!(next>t) || !(mid>t && mid<next))
            return failure(StopReason::numerical_failure,"Binary64 time cannot resolve the next integration step");
        const double step=next-t;
        const auto full=rk4(start,end,d,t0,t1,t,step,state,width);
        const auto first=rk4(start,end,d,t0,t1,t,mid-t,state,width);
        if(!full || !first)
            return failure(StopReason::numerical_failure,"Continuous-model RK4 produced a nonfinite intermediate");
        const auto two_halves=rk4(start,end,d,t0,t1,mid,next-mid,*first,width);
        if(!two_halves)
            return failure(StopReason::numerical_failure,"Continuous-model RK4 produced a nonfinite intermediate");
        double ratio=0,estimate=0;
        for(std::size_t i=0;i<state.size();++i) {
            const double local=std::abs((*two_halves)[i]-(*full)[i])/15;
            const double scale=options.absolute_tolerance+
                options.relative_tolerance*std::max(std::abs(state[i]),std::abs((*two_halves)[i]));
            if(!std::isfinite(local) || !std::isfinite(scale) || scale<=0)
                return failure(StopReason::numerical_failure,"Continuous-model local estimate is nonfinite");
            estimate=std::max(estimate,local);
            ratio=std::max(ratio,local/scale);
        }
        if(ratio>1) {
            ++receipt.rejected_steps;
            h=step/2;
            continue;
        }
        state=*two_halves;
        t=next;
        ++receipt.accepted_steps;
        receipt.max_local_error_estimate=std::max(receipt.max_local_error_estimate,estimate);
        if(t<t1) {
            const double remaining=t1-t;
            h=ratio<1.0/32 ? (h<=remaining/2?h*2:remaining) : std::min(h,remaining);
        }
    }
    LinearStage output{{d.state,d.state,{}},{d.state,d.control,{}},
                       {d.state,d.external,{}},Vector(d.state)};
    output.A.values.reserve(d.state*d.state);
    output.B.values.reserve(d.state*d.control);
    output.E.values.reserve(d.state*d.external);
    for(std::size_t row=0;row<d.state;++row) {
        for(std::size_t col=0;col<d.state;++col)output.A.values.push_back(state[row*width+col]);
        for(std::size_t col=0;col<d.control;++col)output.B.values.push_back(state[row*width+d.state+col]);
        for(std::size_t col=0;col<d.external;++col)
            output.E.values.push_back(state[row*width+d.state+d.control+col]);
        output.offset[row]=state[row*width+width-1];
    }
    return IntegratedStage{std::move(output),receipt};
}
} // namespace csl::model::detail
