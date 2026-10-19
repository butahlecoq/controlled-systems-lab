#include <csl/synthesis/hybrid_path_program.hpp>
#include "hybrid_family_verifier_internal.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <optional>

namespace csl::synthesis {
namespace {
using namespace model;
constexpr std::size_t kMaximumAdmissibleRows=100'000;

struct Interval {
    double lower{-std::numeric_limits<double>::infinity()};
    double upper{std::numeric_limits<double>::infinity()};
    bool empty{};
};

struct ScalarBranch {
    enum class State { feasible, infeasible, unsupported } state{State::unsupported};
    Interval controls;
    double initial{};
    double pre_offset{};
    double pre_control{};
    double post_offset{};
    double post_control{};
    double objective_slope{};
    double objective_offset{};
    double minimum{};
    std::string reason;
};

double tolerance(NumericalPolicy policy,double scale=1.0) {
    return policy.absolute_tolerance+policy.relative_tolerance*std::max(1.0,std::abs(scale));
}

bool exact_product(double left,double right,double& result) {
    result=left*right;
    if(!std::isfinite(result)) return false;
    if(left==0||right==0) return result==0;
    if(result==0||std::abs(result)<std::numeric_limits<double>::min()) return false;
    int left_exponent=0,right_exponent=0;
    static_cast<void>(std::frexp(left,&left_exponent));
    static_cast<void>(std::frexp(right,&right_exponent));
    // A 53-bit significand product can have meaningful bits below the
    // subnormal range even when its rounded result is normal. In that range
    // an inexact FMA residual could itself round to zero.
    if(left_exponent+right_exponent-106<std::numeric_limits<double>::min_exponent-
       std::numeric_limits<double>::digits) return false;
    return std::fma(left,right,-result)==0;
}

bool exact_sum(double left,double right,double& result) {
    result=left+right;
    if(!std::isfinite(result)) return false;
    const double right_virtual=result-left;
    const double left_virtual=result-right_virtual;
    const double right_roundoff=right-right_virtual;
    const double left_roundoff=left-left_virtual;
    return left_roundoff+right_roundoff==0;
}

bool exact_division(double numerator,double denominator,double& result) {
    if(!std::isfinite(numerator)||!std::isfinite(denominator)||denominator==0) return false;
    result=numerator/denominator;
    double reconstructed=0;
    return std::isfinite(result)&&exact_product(result,denominator,reconstructed)&&
        reconstructed==numerator;
}

bool exact_dot(numeric::MatrixView matrix,std::size_t row,const Vector& vector,double& result) {
    if(matrix.cols()!=vector.size()||row>=matrix.rows()) return false;
    result=0;
    for(std::size_t col=0;col<vector.size();++col) {
        double product=0,next=0;
        if(!exact_product(matrix(row,col),vector[col],product)||!exact_sum(result,product,next)) return false;
        result=next;
    }
    return true;
}

bool valid_interval(const Interval& interval) {
    return interval.empty || ((std::isfinite(interval.lower)||std::isinf(interval.lower)) &&
        (std::isfinite(interval.upper)||std::isinf(interval.upper)) && interval.lower<=interval.upper);
}

void intersect(Interval& target,const Interval& source) {
    if(target.empty||source.empty) { target.empty=true; return; }
    target.lower=std::max(target.lower,source.lower);
    target.upper=std::min(target.upper,source.upper);
    if(target.lower>target.upper) target.empty=true;
}

std::optional<Interval> set_interval(const AdmissibleSet& set,std::stop_token cancellation,
    bool& cancelled) {
    return std::visit([&](const auto& value)->std::optional<Interval> {
        using T=std::decay_t<decltype(value)>;
        if constexpr(std::is_same_v<T,EmptySet>) {
            return value.dimension==1?std::optional<Interval>{Interval{0,0,true}}:std::nullopt;
        } else if constexpr(std::is_same_v<T,UniversalSet>) {
            return value.dimension==1?std::optional<Interval>{Interval{}}:std::nullopt;
        } else if constexpr(std::is_same_v<T,Singleton>) {
            if(value.point.size()!=1||!std::isfinite(value.point[0])) return {};
            return Interval{value.point[0],value.point[0],false};
        } else {
            const auto decoded=sets::from_handle(value);
            if(const auto* diagnostic=std::get_if<Diagnostic>(&decoded)) {
                static_cast<void>(diagnostic);
                return {};
            }
            const auto representation=std::get<sets::SetData>(decoded).representation();
            if(std::holds_alternative<sets::EmptyRepresentation>(representation))
                return Interval{0,0,true};
            if(std::holds_alternative<sets::UniversalRepresentation>(representation)) return Interval{};
            if(const auto* singleton=std::get_if<sets::SingletonRepresentation>(&representation)) {
                if(singleton->point.size()!=1||!std::isfinite(singleton->point[0])) return {};
                return Interval{singleton->point[0],singleton->point[0],false};
            }
            const auto* h=std::get_if<sets::HRepresentation>(&representation);
            if(!h||h->equalities.cols()!=1||h->inequalities.cols()!=1||
               h->equalities.rows()>kMaximumAdmissibleRows||
               h->inequalities.rows()>kMaximumAdmissibleRows||
               h->equality_values.size()!=h->equalities.rows()||
               h->upper_bounds.size()!=h->inequalities.rows()) return {};
            Interval result;
            for(std::size_t row=0;row<h->equalities.rows();++row) {
                if((row&255U)==0&&cancellation.stop_requested()) { cancelled=true; return {}; }
                const double coefficient=h->equalities(row,0);
                const double rhs=h->equality_values[row];
                if(!std::isfinite(coefficient)||!std::isfinite(rhs)) return {};
                if(coefficient==0) {
                    if(rhs!=0) result.empty=true;
                } else {
                    double point=0;
                    if(!exact_division(rhs,coefficient,point)) return {};
                    intersect(result,{point,point,false});
                }
            }
            for(std::size_t row=0;row<h->inequalities.rows();++row) {
                if((row&255U)==0&&cancellation.stop_requested()) { cancelled=true; return {}; }
                const double coefficient=h->inequalities(row,0);
                const double rhs=h->upper_bounds[row];
                if(!std::isfinite(coefficient)||!std::isfinite(rhs)) return {};
                if(coefficient>0) {
                    double bound=0;
                    if(!exact_division(rhs,coefficient,bound)) return {};
                    result.upper=std::min(result.upper,bound);
                } else if(coefficient<0) {
                    double bound=0;
                    if(!exact_division(rhs,coefficient,bound)) return {};
                    result.lower=std::max(result.lower,bound);
                }
                else if(rhs<0) result.empty=true;
                if(result.lower>result.upper) result.empty=true;
            }
            if(!valid_interval(result)) return {};
            return result;
        }
    },set);
}

bool scalar_affine_reset(const SetHandle& handle,double& offset,double& gain) {
    const auto decoded=sets::from_handle(handle);
    if(std::holds_alternative<Diagnostic>(decoded)) return false;
    const auto representation=std::get<sets::SetData>(decoded).representation();
    const auto* h=std::get_if<sets::HRepresentation>(&representation);
    if(!h||h->equalities.rows()!=1||h->equalities.cols()!=2||
       h->inequalities.rows()!=0||h->inequalities.cols()!=2||
       h->equality_values.size()!=1||h->upper_bounds.size()!=0) return false;
    const double pre=h->equalities(0,0),post=h->equalities(0,1),rhs=h->equality_values[0];
    return std::isfinite(pre)&&std::isfinite(post)&&std::isfinite(rhs)&&post!=0&&
        exact_division(rhs,post,offset)&&exact_division(-pre,post,gain);
}

const HybridMode* find_mode(const HybridSystem& system,const HybridModeId& id) {
    const auto found=std::find_if(system.modes.begin(),system.modes.end(),
        [&](const auto& mode){return mode.id==id;});
    return found==system.modes.end()?nullptr:&*found;
}

const HybridTransitionEdge* find_edge(const HybridSystem& system,const HybridEdgeId& id) {
    const auto found=std::find_if(system.edges.begin(),system.edges.end(),
        [&](const auto& edge){return edge.id==id;});
    return found==system.edges.end()?nullptr:&*found;
}

const LinearStage* flow_at(const HybridMode& mode,std::size_t stage) {
    if(const auto* fixed=std::get_if<LinearStage>(&mode.flow)) return stage==0?fixed:nullptr;
    const auto& stages=std::get<std::vector<LinearStage>>(mode.flow);
    return stage<stages.size()?&stages[stage]:nullptr;
}

bool contains_value(const AdmissibleSet& set,double value,NumericalPolicy policy,bool& supported,
    std::stop_token cancellation,bool& cancelled) {
    static_cast<void>(policy);
    const auto interval=set_interval(set,cancellation,cancelled);
    if(!interval) { supported=false; return false; }
    if(interval->empty) return false;
    return value>=interval->lower&&value<=interval->upper;
}

bool constrain_affine_preimage(Interval& controls,const Interval& states,double offset,double gain) {
    if(controls.empty||states.empty) { controls.empty=true; return true; }
    if(gain==0) {
        if(offset<states.lower||offset>states.upper) controls.empty=true;
        return true;
    }
    const auto preimage=[&](double state,double& control) {
        if(std::isinf(state)) {
            control=(std::signbit(state)!=std::signbit(gain))?
                -std::numeric_limits<double>::infinity():std::numeric_limits<double>::infinity();
            return true;
        }
        double numerator=0;
        return exact_sum(state,-offset,numerator)&&exact_division(numerator,gain,control);
    };
    double lower=0,upper=0;
    if(!preimage(states.lower,lower)||!preimage(states.upper,upper)) return false;
    if(gain<0) std::swap(lower,upper);
    if(std::isnan(lower)||std::isnan(upper)) return false;
    intersect(controls,{lower,upper,false});
    return true;
}

ScalarBranch evaluate(const HybridSystem& system,const HybridRequest& request,const HybridPath& path,
    NumericalPolicy policy,std::stop_token cancellation) {
    ScalarBranch result;
    const auto unsupported=[&](const char* reason) {
        result.reason=reason;
        result.state=ScalarBranch::State::unsupported;
        return result;
    };
    const auto infeasible=[&]() {
        result.state=ScalarBranch::State::infeasible;
        result.controls.empty=true;
        return result;
    };
    if(cancellation.stop_requested()) return unsupported("Verification cancelled");
    if(system.horizon!=1||path.modes.size()!=2||path.edges.size()!=1||request.initial.state.size()!=1)
        return unsupported("Verifier supports one-stage paths with one-dimensional states");
    const auto* source=find_mode(system,path.modes[0]);
    const auto* target=find_mode(system,path.modes[1]);
    const auto* edge=find_edge(system,path.edges[0]);
    if(!source||!target||!edge||source->state_dimension!=1||source->control_dimension!=1||
       target->state_dimension!=1||edge->source!=source->id||edge->target!=target->id)
        return unsupported("Verifier supports one-dimensional source/target states and scalar controls");
    if(!std::isfinite(request.initial.state[0])||source->invariants.size()!=2||
       target->invariants.size()!=2||source->control_sets.size()!=1||edge->guards.size()!=1||
       edge->reset_relations.size()!=1)
        return unsupported("Hybrid profile stage arrays are outside the verifier domain");
    result.initial=request.initial.state[0];
    bool set_supported=true,cancelled=false;
    const bool initial_allowed=contains_value(source->invariants[0],result.initial,policy,set_supported,
        cancellation,cancelled);
    if(cancelled) return unsupported("Verification cancelled while reading an initial invariant");
    if(!initial_allowed)
        return set_supported?infeasible():unsupported("Initial invariant representation is unsupported");
    if(!set_supported) return unsupported("Initial invariant representation is unsupported");
    auto control_interval=set_interval(source->control_sets[0],cancellation,cancelled);
    auto source_pre=set_interval(source->invariants[1],cancellation,cancelled);
    auto guard=set_interval(edge->guards[0],cancellation,cancelled);
    auto target_post=set_interval(target->invariants[1],cancellation,cancelled);
    if(cancelled) return unsupported("Verification cancelled while reading scalar interval sets");
    if(!control_interval||!source_pre||!guard||!target_post)
        return unsupported("Only scalar interval, singleton, empty, and universal sets are supported");
    if(control_interval->empty||source_pre->empty||guard->empty||target_post->empty) return infeasible();
    const auto* flow=flow_at(*source,0);
    if(!flow||flow->A.rows!=1||flow->A.cols!=1||flow->B.rows!=1||flow->B.cols!=1||
       flow->E.rows!=1||flow->E.cols!=0||flow->offset.size()!=1)
        return unsupported("Flow shape is outside the scalar verifier domain");
    if(!std::isfinite(flow->A.values[0])||!std::isfinite(flow->B.values[0])||
       !std::isfinite(flow->offset[0]))
        return unsupported("Flow contains nonfinite coefficients");
    double reset_offset=0,reset_gain=0;
    if(!scalar_affine_reset(edge->reset_relations[0],reset_offset,reset_gain))
        return unsupported("Verifier supports only exactly representable scalar affine H-relation resets");
    double fixed_product=0,fixed=0;
    if(!exact_product(flow->A.values[0],result.initial,fixed_product)||
       !exact_sum(fixed_product,flow->offset[0],fixed))
        return unsupported("Exactness could not be established for scalar flow arithmetic");
    const double gain=flow->B.values[0];
    if(!std::isfinite(gain)) return unsupported("Flow evaluation overflowed");
    Interval allowed_state=*source_pre;
    intersect(allowed_state,*guard);
    if(!constrain_affine_preimage(allowed_state,*target_post,reset_offset,reset_gain))
        return unsupported("Reset preimage is not exactly representable as a finite interval");
    if(allowed_state.empty) return infeasible();
    if(!constrain_affine_preimage(*control_interval,allowed_state,fixed,gain))
        return unsupported("Flow preimage is not representable as a finite interval");
    if(control_interval->empty) return infeasible();
    if(!std::isfinite(control_interval->lower)||!std::isfinite(control_interval->upper))
        return unsupported("Verifier requires a bounded feasible control interval");
    double lower_flow_increment=0,upper_flow_increment=0,lower_state=0,upper_state=0;
    if(!exact_product(gain,control_interval->lower,lower_flow_increment)||
       !exact_product(gain,control_interval->upper,upper_flow_increment)||
       !exact_sum(fixed,lower_flow_increment,lower_state)||
       !exact_sum(fixed,upper_flow_increment,upper_state))
        return unsupported("Exactness could not be established for feasible interval flow endpoints");
    double lower_reset_increment=0,upper_reset_increment=0,lower_post=0,upper_post=0;
    if(!exact_product(reset_gain,lower_state,lower_reset_increment)||
       !exact_product(reset_gain,upper_state,upper_reset_increment)||
       !exact_sum(reset_offset,lower_reset_increment,lower_post)||
       !exact_sum(reset_offset,upper_reset_increment,upper_post))
        return unsupported("Exactness could not be established for reset image endpoints");
    const auto objective=std::find_if(request.terminal_objectives.begin(),request.terminal_objectives.end(),
        [&](const auto& candidate){return candidate.mode==target->id;});
    if(objective==request.terminal_objectives.end()) return unsupported("Missing terminal objective");
    const auto* linear=std::get_if<LinearTerminal>(&objective->objective);
    if(!linear||linear->coefficients.size()!=1||!std::isfinite(linear->coefficients[0])||
       !std::isfinite(linear->offset)) return unsupported("Only scalar linear terminal objectives are supported");
    result.controls=*control_interval;
    result.pre_offset=fixed;
    result.pre_control=gain;
    double reset_fixed=0,reset_control=0;
    if(!exact_product(reset_gain,fixed,reset_fixed)||
       !exact_sum(reset_offset,reset_fixed,result.post_offset)||
       !exact_product(reset_gain,gain,reset_control))
        return unsupported("Exactness could not be established for the affine reset image");
    result.post_control=reset_control;
    double objective_base=0;
    if(!exact_product(linear->coefficients[0],result.post_control,result.objective_slope)||
       !exact_product(linear->coefficients[0],result.post_offset,objective_base)||
       !exact_sum(objective_base,linear->offset,result.objective_offset))
        return unsupported("Exactness could not be established for objective arithmetic");
    const double optimal_control=result.objective_slope>0?control_interval->lower:
        (result.objective_slope<0?control_interval->upper:control_interval->lower);
    double objective_increment=0;
    if(!exact_product(result.objective_slope,optimal_control,objective_increment)||
       !exact_sum(result.objective_offset,objective_increment,result.minimum))
        return unsupported("Exactness could not be established for the optimal objective value");
    result.state=ScalarBranch::State::feasible;
    return result;
}

std::optional<std::size_t> exact_rank(numeric::MatrixView matrix,std::stop_token cancellation,
    bool& cancelled) {
    std::vector<Vector> values(matrix.rows(),Vector(matrix.cols()));
    for(std::size_t row=0;row<matrix.rows();++row) {
        if((row&255U)==0&&cancellation.stop_requested()) { cancelled=true; return {}; }
        for(std::size_t col=0;col<matrix.cols();++col) values[row][col]=matrix(row,col);
    }
    std::size_t result=0;
    for(std::size_t col=0;col<matrix.cols()&&result<values.size();++col) {
        if(cancellation.stop_requested()) { cancelled=true; return {}; }
        auto pivot=result;
        while(pivot<values.size()&&values[pivot][col]==0) {
            if((pivot&255U)==0&&cancellation.stop_requested()) { cancelled=true; return {}; }
            ++pivot;
        }
        if(pivot==values.size()) continue;
        std::swap(values[pivot],values[result]);
        const double scale=values[result][col];
        for(std::size_t row=result+1;row<values.size();++row) {
            if((row&255U)==0&&cancellation.stop_requested()) { cancelled=true; return {}; }
            if(values[row][col]==0) continue;
            double factor=0;
            if(!exact_division(values[row][col],scale,factor)) return {};
            for(std::size_t j=col+1;j<matrix.cols();++j) {
                double product=0,remainder=0;
                if(!exact_product(factor,values[result][j],product)||
                   !exact_sum(values[row][j],-product,remainder)) return {};
                values[row][j]=remainder;
            }
            values[row][col]=0;
        }
        ++result;
    }
    return result;
}

bool same(double left,double right,NumericalPolicy policy) {
    if(!std::isfinite(left)||!std::isfinite(right)) return false;
    if(left==right) return true;
    const double allowed=tolerance(policy,std::max(std::abs(left),std::abs(right)));
    const double difference=std::abs(left-right);
    return std::isfinite(allowed)&&std::isfinite(difference)&&difference<=allowed;
}

bool relation_domain_supported(const sets::SetData& data,HybridRelationLimits limits) {
    if(data.metadata()->set.dimension!=4||limits.max_variables<4) return false;
    const auto representation=data.representation();
    if(const auto* singleton=std::get_if<sets::SingletonRepresentation>(&representation))
        return singleton->point.size()==4;
    const auto* h=std::get_if<sets::HRepresentation>(&representation);
    if(!h||h->inequalities.rows()>std::numeric_limits<std::size_t>::max()-h->equalities.rows())
        return false;
    const auto total_rows=h->equalities.rows()+h->inequalities.rows();
    return h->equalities.cols()==4&&h->inequalities.cols()==4&&
        h->equalities.rows()<=limits.max_rows&&h->inequalities.rows()<=limits.max_rows&&
        total_rows<=limits.max_rows&&total_rows<=kMaximumAdmissibleRows&&
        total_rows<=limits.max_matrix_elements/4&&
        h->equality_values.size()==h->equalities.rows()&&
        h->upper_bounds.size()==h->inequalities.rows();
}

bool relation_is_line_interval(const sets::SetData& data,double initial,double pre_offset,
    double pre_gain,double post_offset,double post_gain,Interval interval,HybridRelationLimits limits,
    std::stop_token cancellation,bool& cancelled,bool& exactness_established) {
    if(interval.empty||!relation_domain_supported(data,limits)) return false;
    const auto representation=data.representation();
    if(const auto* singleton=std::get_if<sets::SingletonRepresentation>(&representation)) {
        if(singleton->point.size()!=4||
           interval.lower!=interval.upper) return false;
        double pre_increment=0,pre=0,post_increment=0,post=0;
        if(!exact_product(pre_gain,interval.lower,pre_increment)||
           !exact_sum(pre_offset,pre_increment,pre)||
           !exact_product(post_gain,interval.lower,post_increment)||
           !exact_sum(post_offset,post_increment,post)) {
            exactness_established=false;
            return false;
        }
        const Vector expected{initial,interval.lower,pre,post};
        for(std::size_t i=0;i<expected.size();++i)
            if(singleton->point[i]!=expected[i]) return false;
        return true;
    }
    const auto* h=std::get_if<sets::HRepresentation>(&representation);
    if(!h) return false;
    Vector base{initial,0,pre_offset,post_offset};
    Vector direction{0,1,pre_gain,post_gain};
    Vector lower_point=base,upper_point=base;
    for(std::size_t j=0;j<4;++j) {
        double lower_increment=0,upper_increment=0;
        if(!exact_product(direction[j],interval.lower,lower_increment)||
           !exact_product(direction[j],interval.upper,upper_increment)||
           !exact_sum(base[j],lower_increment,lower_point[j])||
           !exact_sum(base[j],upper_increment,upper_point[j])) {
            exactness_established=false;
            return false;
        }
    }
    for(std::size_t row=0;row<h->equalities.rows();++row) {
        if((row&255U)==0&&cancellation.stop_requested()) { cancelled=true; return false; }
        double lower_value=0,upper_value=0;
        if(!exact_dot(h->equalities,row,lower_point,lower_value)||
           !exact_dot(h->equalities,row,upper_point,upper_value)) {
            exactness_established=false;
            return false;
        }
        const double rhs=h->equality_values[row];
        if(!std::isfinite(rhs)||lower_value!=rhs||upper_value!=rhs) return false;
    }
    const auto equality_rank=exact_rank(h->equalities,cancellation,cancelled);
    if(cancelled) return false;
    if(!equality_rank) {
        exactness_established=false;
        return false;
    }
    if(interval.upper>interval.lower) {
        if(*equality_rank!=3) return false;
    } else {
        // A rank-three affine line can be rotated slightly away from the true
        // trajectory while remaining tolerance-close. Require a point-defining
        // equality system for a singleton relation.
        if(*equality_rank!=4) return false;
        Vector point=base;
        for(std::size_t column=0;column<point.size();++column) {
            double increment=0;
            if(!exact_product(direction[column],interval.lower,increment)||
               !exact_sum(point[column],increment,point[column])) {
                exactness_established=false;
                return false;
            }
        }
        for(std::size_t row=0;row<h->inequalities.rows();++row) {
            if((row&255U)==0&&cancellation.stop_requested()) { cancelled=true; return false; }
            double value=0;
            if(!exact_dot(h->inequalities,row,point,value)) {
                exactness_established=false;
                return false;
            }
            if(!std::isfinite(h->upper_bounds[row])||value>h->upper_bounds[row]) return false;
        }
        return true;
    }
    double lower=-std::numeric_limits<double>::infinity();
    double upper=std::numeric_limits<double>::infinity();
    for(std::size_t row=0;row<h->inequalities.rows();++row) {
        if((row&255U)==0&&cancellation.stop_requested()) { cancelled=true; return false; }
        double constant=0,slope=0;
        if(!exact_dot(h->inequalities,row,base,constant)||
           !exact_dot(h->inequalities,row,direction,slope)) {
            exactness_established=false;
            return false;
        }
        const double bound=h->upper_bounds[row];
        if(!std::isfinite(bound)||!std::isfinite(constant)||!std::isfinite(slope)) return false;
        if(slope>0||slope<0) {
            double difference=0,parameter=0;
            if(!exact_sum(bound,-constant,difference)||!exact_division(difference,slope,parameter)) {
                exactness_established=false;
                return false;
            }
            if(slope>0) upper=std::min(upper,parameter);
            else lower=std::max(lower,parameter);
        }
        else if(constant>bound) return false;
    }
    return lower==interval.lower&&upper==interval.upper;
}

bool program_objective_matches(const HybridPathProgram& program,const ScalarBranch& branch,
    double terminal_coefficient,double terminal_offset,NumericalPolicy policy) {
    const auto* linear=std::get_if<LinearProgram>(&program.program);
    if(!linear||linear->objective().size()!=4) return false;
    const Vector expected{0,0,0,terminal_coefficient};
    for(std::size_t i=0;i<expected.size();++i)
        if(!same(linear->objective()[i],expected[i],policy)) return false;
    return same(linear->offset(),terminal_offset,policy)&&
        same(branch.objective_offset,terminal_coefficient*branch.post_offset+terminal_offset,policy);
}

struct TwoStageScalarBranch {
    enum class State { feasible, infeasible, unsupported } state{State::unsupported};
    Interval parameter_interval;
    Vector base;
    Vector direction;
    std::size_t parameter_control_coordinate{};
    double objective_slope{};
    double objective_offset{};
    double minimum{};
    std::string reason;
};

bool relation_domain_supported_for_width(const sets::SetData& data,std::size_t width,
    HybridRelationLimits limits) {
    if(data.metadata()->set.dimension!=width||limits.max_variables<width) return false;
    const auto representation=data.representation();
    if(const auto* singleton=std::get_if<sets::SingletonRepresentation>(&representation))
        return singleton->point.size()==width;
    const auto* h=std::get_if<sets::HRepresentation>(&representation);
    if(!h||h->inequalities.rows()>std::numeric_limits<std::size_t>::max()-h->equalities.rows())
        return false;
    const auto total_rows=h->equalities.rows()+h->inequalities.rows();
    return h->equalities.cols()==width&&h->inequalities.cols()==width&&
        h->equalities.rows()<=limits.max_rows&&h->inequalities.rows()<=limits.max_rows&&
        total_rows<=limits.max_rows&&total_rows<=kMaximumAdmissibleRows&&
        (width==0||total_rows<=limits.max_matrix_elements/width)&&
        h->equality_values.size()==h->equalities.rows()&&
        h->upper_bounds.size()==h->inequalities.rows();
}

bool relation_is_parameter_interval(const sets::SetData& data,const Vector& base,
    const Vector& direction,Interval interval,HybridRelationLimits limits,
    std::stop_token cancellation,bool& cancelled,bool& exactness_established) {
    const auto width=base.size();
    if(interval.empty||direction.size()!=width||!relation_domain_supported_for_width(data,width,limits))
        return false;
    const auto representation=data.representation();
    const auto point_at=[&](double parameter,Vector& point) {
        point.assign(base.begin(),base.end());
        for(std::size_t column=0;column<width;++column) {
            double increment=0;
            if(!exact_product(direction[column],parameter,increment)||
               !exact_sum(point[column],increment,point[column])) {
                exactness_established=false;
                return false;
            }
        }
        return true;
    };
    if(const auto* singleton=std::get_if<sets::SingletonRepresentation>(&representation)) {
        if(interval.lower!=interval.upper) return false;
        Vector expected;
        if(!point_at(interval.lower,expected)) return false;
        return std::equal(expected.begin(),expected.end(),singleton->point.values().begin());
    }
    const auto* h=std::get_if<sets::HRepresentation>(&representation);
    if(!h) return false;
    Vector lower_point,upper_point;
    if(!point_at(interval.lower,lower_point)||!point_at(interval.upper,upper_point)) return false;
    for(std::size_t row=0;row<h->equalities.rows();++row) {
        if((row&255U)==0&&cancellation.stop_requested()) { cancelled=true; return false; }
        double lower_value=0,upper_value=0;
        if(!exact_dot(h->equalities,row,lower_point,lower_value)||
           !exact_dot(h->equalities,row,upper_point,upper_value)) {
            exactness_established=false;
            return false;
        }
        if(!std::isfinite(h->equality_values[row])||
           lower_value!=h->equality_values[row]||upper_value!=h->equality_values[row]) return false;
    }
    const auto rank=exact_rank(h->equalities,cancellation,cancelled);
    if(cancelled) return false;
    if(!rank) { exactness_established=false; return false; }
    if(interval.lower==interval.upper) {
        if(*rank==width) {
            for(std::size_t row=0;row<h->inequalities.rows();++row) {
                if((row&255U)==0&&cancellation.stop_requested()) { cancelled=true; return false; }
                double value=0;
                if(!exact_dot(h->inequalities,row,lower_point,value)) {
                    exactness_established=false;
                    return false;
                }
                if(!std::isfinite(h->upper_bounds[row])||value>h->upper_bounds[row]) return false;
            }
            return true;
        }
        if(*rank!=width-1) return false;
        for(std::size_t row=0;row<h->equalities.rows();++row) {
            if((row&255U)==0&&cancellation.stop_requested()) { cancelled=true; return false; }
            double direction_value=0;
            if(!exact_dot(h->equalities,row,direction,direction_value)) {
                exactness_established=false;
                return false;
            }
            if(direction_value!=0) return false;
        }
    } else if(*rank!=width-1) return false;
    double lower=-std::numeric_limits<double>::infinity();
    double upper=std::numeric_limits<double>::infinity();
    for(std::size_t row=0;row<h->inequalities.rows();++row) {
        if((row&255U)==0&&cancellation.stop_requested()) { cancelled=true; return false; }
        double constant=0,slope=0;
        if(!exact_dot(h->inequalities,row,base,constant)||
           !exact_dot(h->inequalities,row,direction,slope)) {
            exactness_established=false;
            return false;
        }
        const double bound=h->upper_bounds[row];
        if(!std::isfinite(bound)||!std::isfinite(constant)||!std::isfinite(slope)) return false;
        if(slope!=0) {
            double difference=0,parameter=0;
            if(!exact_sum(bound,-constant,difference)||!exact_division(difference,slope,parameter)) {
                exactness_established=false;
                return false;
            }
            if(slope>0) upper=std::min(upper,parameter);
            else lower=std::max(lower,parameter);
        } else if(constant>bound) return false;
    }
    return lower==interval.lower&&upper==interval.upper;
}

bool two_stage_program_objective_matches(const HybridPathProgram& program,std::size_t width,
    double terminal_coefficient,double terminal_offset,NumericalPolicy policy) {
    const auto* linear=std::get_if<LinearProgram>(&program.program);
    if(!linear||linear->objective().size()!=width||width!=7) return false;
    for(std::size_t i=0;i<width;++i) {
        const double expected=i==6?terminal_coefficient:0;
        if(!same(linear->objective()[i],expected,policy)) return false;
    }
    return same(linear->offset(),terminal_offset,policy);
}

TwoStageScalarBranch evaluate_two_stage_scalar(const HybridSystem& system,const HybridRequest& request,
    const HybridPath& path,std::stop_token cancellation) {
    TwoStageScalarBranch result;
    const auto unsupported=[&](const char* reason) {
        result.reason=reason;
        result.state=TwoStageScalarBranch::State::unsupported;
        return result;
    };
    const auto infeasible=[&]() {
        result.state=TwoStageScalarBranch::State::infeasible;
        result.parameter_interval.empty=true;
        return result;
    };
    if(cancellation.stop_requested()) return unsupported("Verification cancelled");
    if(system.horizon!=2||path.modes.size()!=3||path.edges.size()!=2||
       request.initial.state.size()!=1||!std::isfinite(request.initial.state[0]))
        return unsupported("Verifier supports two-stage paths with one-dimensional states");
    std::array<const HybridMode*,3> modes{};
    std::array<const HybridTransitionEdge*,2> edges{};
    for(std::size_t i=0;i<modes.size();++i) {
        modes[i]=find_mode(system,path.modes[i]);
        if(!modes[i]||modes[i]->state_dimension!=1||modes[i]->control_dimension!=1||
           modes[i]->invariants.size()!=3||modes[i]->control_sets.size()!=2)
            return unsupported("Verifier supports scalar modes with two stage-indexed interval controls and invariants");
    }
    for(std::size_t i=0;i<edges.size();++i) {
        edges[i]=find_edge(system,path.edges[i]);
        if(!edges[i]||edges[i]->source!=modes[i]->id||edges[i]->target!=modes[i+1]->id||
           edges[i]->guards.size()!=2||edges[i]->reset_relations.size()!=2)
            return unsupported("Transition edges are outside the two-stage scalar verifier domain");
    }
    bool set_supported=true,cancelled=false;
    if(!contains_value(modes[0]->invariants[0],request.initial.state[0],{},set_supported,
        cancellation,cancelled)) {
        if(cancelled) return unsupported("Verification cancelled while reading initial invariant");
        return set_supported?infeasible():unsupported("Initial invariant representation is unsupported");
    }
    if(!set_supported) return unsupported("Initial invariant representation is unsupported");

    std::array<Interval,2> control_intervals{};
    std::size_t free_control_stage=2;
    for(std::size_t stage=0;stage<2;++stage) {
        auto parsed=set_interval(modes[stage]->control_sets[stage],cancellation,cancelled);
        if(cancelled) return unsupported("Verification cancelled while reading scalar control intervals");
        if(!parsed) return unsupported("Control set is outside the scalar interval verifier domain");
        control_intervals[stage]=*parsed;
        if(parsed->empty) return infeasible();
        if(!std::isfinite(parsed->lower)||!std::isfinite(parsed->upper))
            return unsupported("Verifier requires bounded scalar control intervals");
        if(parsed->lower<parsed->upper) {
            if(free_control_stage!=2)
                return unsupported("Verifier supports exactly one non-singleton interval control");
            free_control_stage=stage;
        }
    }
    if(free_control_stage==2)
        return unsupported("Verifier requires one continuous scalar interval control parameter");
    Interval parameters=control_intervals[free_control_stage];
    result.parameter_control_coordinate=free_control_stage==0?1:4;
    result.base.assign(7,0);
    result.direction.assign(7,0);
    result.base[0]=request.initial.state[0];
    double state_offset=request.initial.state[0],state_gain=0;
    std::size_t coordinate=1;
    for(std::size_t stage=0;stage<2;++stage) {
        if(cancellation.stop_requested()) return unsupported("Verification cancelled between scalar stages");
        const auto& mode=*modes[stage];
        const auto& flow_value=mode.flow;
        const LinearStage* flow=nullptr;
        if(const auto* stages=std::get_if<std::vector<LinearStage>>(&flow_value)) {
            if(stages->size()!=2) return unsupported("Verifier requires two explicit scalar flow stages");
            flow=&(*stages)[stage];
        } else if(stage==0) flow=std::get_if<LinearStage>(&flow_value);
        if(!flow||flow->A.rows!=1||flow->A.cols!=1||flow->B.rows!=1||flow->B.cols!=1||
           flow->E.rows!=1||flow->E.cols!=0||flow->offset.size()!=1||
           !std::isfinite(flow->A.values[0])||!std::isfinite(flow->B.values[0])||
           !std::isfinite(flow->offset[0]))
            return unsupported("Flow shape is outside the scalar verifier domain");
        double control_offset=control_intervals[stage].lower;
        double control_gain=0;
        if(stage==free_control_stage) { control_offset=0; control_gain=1; }
        result.base[coordinate]=control_offset;
        result.direction[coordinate]=control_gain;
        ++coordinate;

        auto current_parsed=set_interval(mode.invariants[stage],cancellation,cancelled);
        if(cancelled) return unsupported("Verification cancelled while reading stage invariants");
        if(!current_parsed) return unsupported("Stage invariant representation is unsupported");
        const Interval current_invariant=*current_parsed;
        if(current_invariant.empty) return infeasible();
        if(!constrain_affine_preimage(parameters,current_invariant,state_offset,state_gain))
            return unsupported("Stage invariant preimage is not exactly representable");
        if(parameters.empty) return infeasible();

        double state_product=0,control_product=0,pre_offset=0,pre_gain=0;
        if(!exact_product(flow->A.values[0],state_offset,state_product)||
           !exact_product(flow->B.values[0],control_offset,control_product)||
           !exact_sum(state_product,control_product,pre_offset)||
           !exact_sum(pre_offset,flow->offset[0],pre_offset)||
           !exact_product(flow->A.values[0],state_gain,pre_gain))
            return unsupported("Flow composition is not exactly representable");
        double control_gain_product=0;
        if(!exact_product(flow->B.values[0],control_gain,control_gain_product)||
           !exact_sum(pre_gain,control_gain_product,pre_gain))
            return unsupported("Flow parameter gain is not exactly representable");

        result.base[coordinate]=pre_offset;
        result.direction[coordinate]=pre_gain;
        ++coordinate;
        auto constrain_set=[&](const AdmissibleSet& set,double offset,double gain,
            const char* unsupported_reason)->bool {
            auto interval=set_interval(set,cancellation,cancelled);
            if(cancelled) return false;
            if(!interval) { result.reason=unsupported_reason; return false; }
            if(interval->empty) { parameters.empty=true; return true; }
            return constrain_affine_preimage(parameters,*interval,offset,gain);
        };
        if(!constrain_set(mode.invariants[stage+1],pre_offset,pre_gain,
            "Pre-reset invariant representation is unsupported"))
            if(result.reason.empty()) return unsupported("Pre-reset invariant preimage is not exactly representable");
            else { const auto reason=result.reason; return unsupported(reason.c_str()); }
        if(parameters.empty) return infeasible();
        if(!constrain_set(edges[stage]->guards[stage],pre_offset,pre_gain,
            "Transition guard representation is unsupported"))
            if(result.reason.empty()) return unsupported("Transition guard preimage is not exactly representable");
            else { const auto reason=result.reason; return unsupported(reason.c_str()); }
        if(parameters.empty) return infeasible();

        double reset_offset=0,reset_gain=0;
        if(!scalar_affine_reset(edges[stage]->reset_relations[stage],reset_offset,reset_gain))
            return unsupported("Verifier supports exactly representable deterministic scalar affine resets");
        double reset_increment=0,post_offset=0,post_gain=0;
        if(!exact_product(reset_gain,pre_offset,reset_increment)||
           !exact_sum(reset_offset,reset_increment,post_offset)||
           !exact_product(reset_gain,pre_gain,post_gain))
            return unsupported("Reset composition is not exactly representable");
        result.base[coordinate]=post_offset;
        result.direction[coordinate]=post_gain;
        ++coordinate;
        state_offset=post_offset;
        state_gain=post_gain;
        if(parameters.empty) return infeasible();
    }
    auto terminal_set=set_interval(modes[2]->invariants[2],cancellation,cancelled);
    if(cancelled) return unsupported("Verification cancelled while reading terminal invariant");
    if(!terminal_set) return unsupported("Terminal invariant representation is unsupported");
    if(terminal_set->empty) return infeasible();
    if(!constrain_affine_preimage(parameters,*terminal_set,state_offset,state_gain))
        return unsupported("Terminal invariant preimage is not exactly representable");
    if(parameters.empty) return infeasible();
    if(!std::isfinite(parameters.lower)||!std::isfinite(parameters.upper))
        return unsupported("Verifier requires a bounded feasible control parameter interval");

    const auto objective=std::find_if(request.terminal_objectives.begin(),request.terminal_objectives.end(),
        [&](const auto& item){return item.mode==modes[2]->id;});
    if(objective==request.terminal_objectives.end()) return unsupported("Missing terminal objective");
    const auto* linear=std::get_if<LinearTerminal>(&objective->objective);
    if(!linear||linear->coefficients.size()!=1||!std::isfinite(linear->coefficients[0])||
       !std::isfinite(linear->offset)) return unsupported("Only scalar linear terminal objectives are supported");
    double objective_base=0,objective_offset=0;
    if(!exact_product(linear->coefficients[0],state_gain,result.objective_slope)||
       !exact_product(linear->coefficients[0],state_offset,objective_base)||
       !exact_sum(objective_base,linear->offset,objective_offset))
        return unsupported("Objective composition is not exactly representable");
    result.objective_offset=objective_offset;
    const double minimizing_parameter=result.objective_slope>0?parameters.lower:
        (result.objective_slope<0?parameters.upper:parameters.lower);
    double objective_increment=0;
    if(!exact_product(result.objective_slope,minimizing_parameter,objective_increment)||
       !exact_sum(result.objective_offset,objective_increment,result.minimum))
        return unsupported("Minimum objective arithmetic is not exactly representable");
    result.parameter_interval=parameters;
    result.state=TwoStageScalarBranch::State::feasible;
    return result;
}

} // namespace

HybridFamilyVerificationCapabilities OneStepScalarIntervalHybridFamilyVerifier::capabilities() const noexcept {
    return {true,true,true,Assurance::numerical};
}

HybridFamilyVerificationResult OneStepScalarIntervalHybridFamilyVerifier::verify(
    const HybridSystem& system,const HybridRequest& request,std::span<const HybridPath> paths,
    std::span<const HybridPathProgram> programs,
    std::span<const HybridPathOptimalFaceCandidate> candidates,NumericalPolicy policy,
    std::stop_token cancellation) const {
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,"Scalar interval hybrid verification cancelled before traversal"};
    if(!std::isfinite(policy.absolute_tolerance)||!std::isfinite(policy.relative_tolerance)||
       policy.absolute_tolerance<0||policy.relative_tolerance<0)
        return Diagnostics{{DiagnosticCode::invalid_input,"hybrid.verification.scalar_interval_policy",
            "Numerical tolerances must be finite and nonnegative"}};
    const auto profile_diagnostics=check_hybrid_profile(system,request);
    if(!profile_diagnostics.empty()) return profile_diagnostics;
    if(system.horizon!=1)
        return Diagnostics{{DiagnosticCode::unsupported,"hybrid.verification.scalar_interval_horizon",
            "OneStepScalarIntervalHybridFamilyVerifier supports horizon one only"}};
    auto inventory=detail::independently_enumerate_paths(system,request,paths.size(),
        std::max<std::size_t>(64,(system.edges.size()+1)*16),[&]{return cancellation.stop_requested();});
    if(cancellation.stop_requested()||inventory.cancelled)
        return OperationStopped{StopReason::cancelled,"Scalar interval hybrid verification cancelled during path traversal"};
    if(inventory.resource_limit)
        return Diagnostics{{DiagnosticCode::unsupported,"hybrid.verification.scalar_interval_path_limit",
            "Independent path inventory exceeded its bounded traversal"}};
    if(inventory.paths!=std::vector<HybridPath>(paths.begin(),paths.end()))
        return Diagnostics{{DiagnosticCode::evidence_mismatch,"hybrid.verification.scalar_interval_paths",
            "Independent path traversal disagrees with the supplied path inventory"}};
    if(programs.size()!=paths.size())
        return Diagnostics{{DiagnosticCode::evidence_mismatch,"hybrid.verification.scalar_interval_programs",
            "A branch program is required for every enumerated path"}};

    std::vector<ScalarBranch> evaluated;
    evaluated.reserve(paths.size());
    std::optional<double> global_minimum;
    bool unsupported=false;
    for(std::size_t i=0;i<paths.size();++i) {
        if(cancellation.stop_requested())
            return OperationStopped{StopReason::cancelled,"Scalar interval hybrid verification cancelled between branches"};
        auto branch=evaluate(system,request,paths[i],policy,cancellation);
        if(cancellation.stop_requested())
            return OperationStopped{StopReason::cancelled,"Scalar interval hybrid verification cancelled during branch reconstruction"};
        if(branch.state==ScalarBranch::State::unsupported) unsupported=true;
        if(branch.state==ScalarBranch::State::feasible&&
           (!global_minimum||branch.minimum<*global_minimum)) global_minimum=branch.minimum;
        evaluated.push_back(std::move(branch));
    }
    HybridFamilyVerificationReport report{"csl.hybrid.one-step-scalar-interval","1",policy,
        Assurance::numerical,std::vector<HybridPath>(paths.begin(),paths.end()),{},
        HybridVerificationStatus::not_checked,HybridVerificationStatus::not_checked};
    report.branches.reserve(paths.size());
    bool family_covered=true;
    bool coverage_unsupported=false;
    for(std::size_t i=0;i<paths.size();++i) {
        if(cancellation.stop_requested())
            return OperationStopped{StopReason::cancelled,"Scalar interval hybrid verification cancelled while checking branch evidence"};
        const auto& branch=evaluated[i];
        HybridPathVerificationRecord record{};
        record.path=paths[i];
        const auto candidate=std::find_if(candidates.begin(),candidates.end(),
            [&](const auto& item){return item.path==paths[i];});
        if(branch.state==ScalarBranch::State::unsupported) {
            record.feasibility=HybridVerificationStatus::unsupported;
            record.objective_optimality=HybridVerificationStatus::unsupported;
            record.continuous_coverage=HybridVerificationStatus::unsupported;
            record.diagnostics.push_back({DiagnosticCode::unsupported,"hybrid.verification.scalar_interval_domain",branch.reason});
            family_covered=false;
            coverage_unsupported=true;
        } else if(branch.state==ScalarBranch::State::infeasible) {
            record.feasibility=HybridVerificationStatus::refuted;
            record.objective_optimality=HybridVerificationStatus::refuted;
            record.continuous_coverage=candidate==candidates.end()?HybridVerificationStatus::established:
                HybridVerificationStatus::refuted;
            if(candidate!=candidates.end()) {
                family_covered=false;
                record.diagnostics.push_back({DiagnosticCode::evidence_mismatch,"hybrid.verification.scalar_interval_infeasible_face",
                    "A candidate face is supplied for an independently infeasible edge path"});
            }
        } else {
            record.feasibility=HybridVerificationStatus::established;
            // A tolerance-based comparison could publish a strictly worse path
            // as tied. Near ties remain ordered by the computed scalar values.
            const bool optimal=global_minimum&&branch.minimum==*global_minimum;
            const auto objective_it=std::find_if(request.terminal_objectives.begin(),request.terminal_objectives.end(),
                [&](const auto& item){return item.mode==paths[i].modes.back();});
            const auto* linear=objective_it==request.terminal_objectives.end()?nullptr:
                std::get_if<LinearTerminal>(&objective_it->objective);
            Interval optimal_controls=branch.controls;
            if(optimal&&branch.objective_slope>0)
                optimal_controls.upper=optimal_controls.lower;
            else if(optimal&&branch.objective_slope<0)
                optimal_controls.lower=optimal_controls.upper;
            bool relation_cancelled=false,relation_exactness=true;
            const bool program_domain=relation_domain_supported(
                programs[i].joint_relation,programs[i].relation_limits);
            const bool program_valid=program_domain&&linear&&programs[i].path==paths[i]&&
                relation_is_line_interval(programs[i].joint_relation,branch.initial,branch.pre_offset,
                    branch.pre_control,branch.post_offset,branch.post_control,branch.controls,
                    programs[i].relation_limits,cancellation,
                    relation_cancelled,relation_exactness)&&
                program_objective_matches(programs[i],branch,linear->coefficients[0],linear->offset,policy);
            if(cancellation.stop_requested())
                return OperationStopped{StopReason::cancelled,"Scalar interval hybrid verification cancelled while checking a program relation"};
            if(!program_valid) {
                family_covered=false;
                if(program_domain&&relation_exactness) {
                    record.diagnostics.push_back({DiagnosticCode::evidence_mismatch,"hybrid.verification.scalar_interval_program",
                        "Program relation or lifted objective disagrees with the independent scalar reconstruction"});
                } else {
                    record.continuous_coverage=HybridVerificationStatus::unsupported;
                    coverage_unsupported=true;
                    record.diagnostics.push_back({DiagnosticCode::unsupported,"hybrid.verification.scalar_interval_program_domain",
                        "Program relation is outside the verifier's supported representation, exact arithmetic, or resource limits"});
                }
            }
            record.objective_optimality=unsupported&&!optimal?HybridVerificationStatus::unsupported:
                (optimal?HybridVerificationStatus::established:HybridVerificationStatus::refuted);
            if(optimal&&unsupported) {
                record.objective_optimality=HybridVerificationStatus::unsupported;
                record.diagnostics.push_back({DiagnosticCode::unsupported,"hybrid.verification.scalar_interval_global_optimum",
                    "An unsupported branch could change the global optimum"});
            }
            bool covered=program_valid&&!optimal;
            if(optimal&&candidate!=candidates.end()&&linear) {
                const double anchor_control=candidate->anchor.size()==4?candidate->anchor[1]:
                    std::numeric_limits<double>::quiet_NaN();
                const auto& solver=candidate->solver_result;
                bool solver_anchor_matches=solver.termination==Termination::completed&&
                    solver.outcome.value==MathematicalOutcome::optimal&&solver.primal&&
                    solver.primal->size()==candidate->anchor.size();
                if(solver_anchor_matches) {
                    for(std::size_t j=0;j<candidate->anchor.size();++j)
                        solver_anchor_matches=solver_anchor_matches&&
                            same((*solver.primal)[j],candidate->anchor[j],policy);
                }
                const bool face_domain=relation_domain_supported(candidate->relation,programs[i].relation_limits);
                covered=program_valid&&solver_anchor_matches&&std::isfinite(anchor_control)&&
                    anchor_control>=optimal_controls.lower-tolerance(policy,anchor_control)&&
                    anchor_control<=optimal_controls.upper+tolerance(policy,anchor_control)&&
                    same(candidate->anchor[0],branch.initial,policy)&&
                    same(candidate->anchor[2],branch.pre_offset+branch.pre_control*anchor_control,policy)&&
                    same(candidate->anchor[3],branch.post_offset+branch.post_control*anchor_control,policy)&&
                    face_domain&&relation_is_line_interval(candidate->relation,branch.initial,branch.pre_offset,
                        branch.pre_control,branch.post_offset,branch.post_control,optimal_controls,
                        programs[i].relation_limits,cancellation,
                        relation_cancelled,relation_exactness);
                if(cancellation.stop_requested())
                    return OperationStopped{StopReason::cancelled,"Scalar interval hybrid verification cancelled while checking a candidate face"};
                if(covered) record.continuous_coverage=HybridVerificationStatus::established;
                else if(!face_domain||!relation_exactness) {
                    record.continuous_coverage=HybridVerificationStatus::unsupported;
                    coverage_unsupported=true;
                    record.diagnostics.push_back({DiagnosticCode::unsupported,"hybrid.verification.scalar_interval_face_domain",
                        "Candidate relation is outside the supported representation, exact arithmetic, or resource limits"});
                } else record.diagnostics.push_back({DiagnosticCode::evidence_mismatch,"hybrid.verification.scalar_interval_face",
                    "Optimal interval candidate does not equal the independently reconstructed minimizer set"});
            } else if(optimal) {
                covered=false;
                record.diagnostics.push_back({DiagnosticCode::evidence_mismatch,"hybrid.verification.scalar_interval_missing_face",
                    "An optimal edge path has no candidate continuous minimizer relation"});
            } else if(candidate!=candidates.end()) {
                covered=false;
                record.diagnostics.push_back({DiagnosticCode::evidence_mismatch,"hybrid.verification.scalar_interval_suboptimal_face",
                    "A candidate face is supplied for a globally suboptimal edge path"});
            }
            if(record.objective_optimality==HybridVerificationStatus::unsupported) {
                record.continuous_coverage=HybridVerificationStatus::unsupported;
                covered=false;
                coverage_unsupported=true;
            } else if(record.continuous_coverage==HybridVerificationStatus::unsupported) {
                covered=false;
            } else if(record.continuous_coverage==HybridVerificationStatus::not_checked) {
                record.continuous_coverage=covered?HybridVerificationStatus::established:
                    HybridVerificationStatus::refuted;
            }
            family_covered=family_covered&&covered;
        }
        report.branches.push_back(std::move(record));
    }
    if(unsupported) {
        report.global_objective_optimality=HybridVerificationStatus::unsupported;
        report.complete_family_coverage=HybridVerificationStatus::unsupported;
    } else if(!global_minimum) {
        report.global_objective_optimality=HybridVerificationStatus::refuted;
        report.complete_family_coverage=HybridVerificationStatus::refuted;
    } else {
        report.global_objective_optimality=HybridVerificationStatus::established;
        report.complete_family_coverage=family_covered?HybridVerificationStatus::established:
            (coverage_unsupported?HybridVerificationStatus::unsupported:HybridVerificationStatus::refuted);
    }
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,"Scalar interval hybrid verification cancelled before report publication"};
    return report;
}

HybridFamilyVerificationCapabilities TwoStageScalarIntervalHybridFamilyVerifier::capabilities() const noexcept {
    return {true,true,true,Assurance::numerical};
}

HybridFamilyVerificationResult TwoStageScalarIntervalHybridFamilyVerifier::verify(
    const HybridSystem& system,const HybridRequest& request,std::span<const HybridPath> paths,
    std::span<const HybridPathProgram> programs,
    std::span<const HybridPathOptimalFaceCandidate> candidates,NumericalPolicy policy,
    std::stop_token cancellation) const {
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,
            "Two-stage scalar interval verification cancelled before traversal"};
    if(!std::isfinite(policy.absolute_tolerance)||!std::isfinite(policy.relative_tolerance)||
       policy.absolute_tolerance<0||policy.relative_tolerance<0)
        return Diagnostics{{DiagnosticCode::invalid_input,"hybrid.verification.two_stage_policy",
            "Numerical tolerances must be finite and nonnegative"}};
    const auto profile_diagnostics=check_hybrid_profile(system,request);
    if(!profile_diagnostics.empty()) return profile_diagnostics;
    if(system.horizon!=2)
        return Diagnostics{{DiagnosticCode::unsupported,"hybrid.verification.two_stage_horizon",
            "TwoStageScalarIntervalHybridFamilyVerifier supports horizon two only"}};
    auto inventory=detail::independently_enumerate_paths(system,request,paths.size(),
        std::max<std::size_t>(64,(system.edges.size()+1)*16),
        [&]{return cancellation.stop_requested();});
    if(cancellation.stop_requested()||inventory.cancelled)
        return OperationStopped{StopReason::cancelled,
            "Two-stage scalar interval verification cancelled during path traversal"};
    if(inventory.resource_limit)
        return Diagnostics{{DiagnosticCode::unsupported,"hybrid.verification.two_stage_path_limit",
            "Independent path inventory exceeded its bounded traversal"}};
    if(inventory.paths!=std::vector<HybridPath>(paths.begin(),paths.end()))
        return Diagnostics{{DiagnosticCode::evidence_mismatch,"hybrid.verification.two_stage_paths",
            "Independent path traversal disagrees with the supplied path inventory"}};
    if(programs.size()!=paths.size())
        return Diagnostics{{DiagnosticCode::evidence_mismatch,"hybrid.verification.two_stage_programs",
            "A branch program is required for every enumerated path"}};

    std::vector<TwoStageScalarBranch> evaluated;
    evaluated.reserve(paths.size());
    std::optional<double> global_minimum;
    bool unsupported=false;
    for(const auto& path:paths) {
        if(cancellation.stop_requested())
            return OperationStopped{StopReason::cancelled,
                "Two-stage scalar interval verification cancelled between branches"};
        auto branch=evaluate_two_stage_scalar(system,request,path,cancellation);
        if(cancellation.stop_requested())
            return OperationStopped{StopReason::cancelled,
                "Two-stage scalar interval verification cancelled during branch reconstruction"};
        if(branch.state==TwoStageScalarBranch::State::unsupported) unsupported=true;
        if(branch.state==TwoStageScalarBranch::State::feasible&&
           (!global_minimum||branch.minimum<*global_minimum)) global_minimum=branch.minimum;
        evaluated.push_back(std::move(branch));
    }

    HybridFamilyVerificationReport report{"csl.hybrid.two-stage-scalar-interval","1",policy,
        Assurance::numerical,std::vector<HybridPath>(paths.begin(),paths.end()),{},
        HybridVerificationStatus::not_checked,HybridVerificationStatus::not_checked};
    report.branches.reserve(paths.size());
    bool family_covered=true;
    bool coverage_unsupported=false;
    for(std::size_t i=0;i<paths.size();++i) {
        if(cancellation.stop_requested())
            return OperationStopped{StopReason::cancelled,
                "Two-stage scalar interval verification cancelled while checking branch evidence"};
        const auto& branch=evaluated[i];
        HybridPathVerificationRecord record{};
        record.path=paths[i];
        const auto candidate=std::find_if(candidates.begin(),candidates.end(),
            [&](const auto& item){return item.path==paths[i];});
        if(branch.state==TwoStageScalarBranch::State::unsupported) {
            record.feasibility=HybridVerificationStatus::unsupported;
            record.objective_optimality=HybridVerificationStatus::unsupported;
            record.continuous_coverage=HybridVerificationStatus::unsupported;
            record.diagnostics.push_back({DiagnosticCode::unsupported,
                "hybrid.verification.two_stage_domain",branch.reason});
            family_covered=false;
            coverage_unsupported=true;
        } else if(branch.state==TwoStageScalarBranch::State::infeasible) {
            const auto program_representation=programs[i].joint_relation.representation();
            const bool explicitly_empty=programs[i].joint_relation.metadata()->set.dimension==7&&
                std::holds_alternative<sets::EmptyRepresentation>(program_representation);
            if(explicitly_empty) {
                record.feasibility=HybridVerificationStatus::refuted;
                record.objective_optimality=HybridVerificationStatus::refuted;
                record.continuous_coverage=candidate==candidates.end()?HybridVerificationStatus::established:
                    HybridVerificationStatus::refuted;
            } else {
                // A contradiction in the independently reconstructed interval is
                // not enough to certify that the supplied joint relation is empty.
                // H-relation emptiness needs its own exact feasibility check.
                record.feasibility=HybridVerificationStatus::unsupported;
                record.objective_optimality=HybridVerificationStatus::unsupported;
                record.continuous_coverage=HybridVerificationStatus::unsupported;
                unsupported=true;
                coverage_unsupported=true;
                family_covered=false;
                record.diagnostics.push_back({DiagnosticCode::unsupported,
                    "hybrid.verification.two_stage_empty_relation",
                    "Infeasible scalar branch is not represented by an explicit empty relation"});
            }
            if(candidate!=candidates.end()) {
                family_covered=false;
                record.diagnostics.push_back({DiagnosticCode::evidence_mismatch,
                    "hybrid.verification.two_stage_infeasible_face",
                    "A candidate face is supplied for an independently infeasible edge path"});
            }
        } else {
            record.feasibility=HybridVerificationStatus::established;
            const bool optimal=global_minimum&&branch.minimum==*global_minimum;
            const auto objective=std::find_if(request.terminal_objectives.begin(),
                request.terminal_objectives.end(),[&](const auto& item){
                    return item.mode==paths[i].modes.back();
                });
            const auto* linear=objective==request.terminal_objectives.end()?nullptr:
                std::get_if<LinearTerminal>(&objective->objective);
            bool relation_cancelled=false,relation_exactness=true;
            const bool program_domain=relation_domain_supported_for_width(
                programs[i].joint_relation,7,programs[i].relation_limits);
            const bool program_valid=program_domain&&linear&&programs[i].path==paths[i]&&
                relation_is_parameter_interval(programs[i].joint_relation,branch.base,
                    branch.direction,branch.parameter_interval,programs[i].relation_limits,
                    cancellation,relation_cancelled,relation_exactness)&&
                two_stage_program_objective_matches(programs[i],7,linear->coefficients[0],
                    linear->offset,policy);
            if(cancellation.stop_requested())
                return OperationStopped{StopReason::cancelled,
                    "Two-stage scalar interval verification cancelled while checking a program relation"};
            if(!program_valid) {
                family_covered=false;
                if(program_domain&&relation_exactness) {
                    record.diagnostics.push_back({DiagnosticCode::evidence_mismatch,
                        "hybrid.verification.two_stage_program",
                        "Program relation or lifted objective disagrees with the independent reconstruction"});
                } else {
                    record.continuous_coverage=HybridVerificationStatus::unsupported;
                    coverage_unsupported=true;
                    record.diagnostics.push_back({DiagnosticCode::unsupported,
                        "hybrid.verification.two_stage_program_domain",
                        "Program relation is outside the verifier's supported representation, exact arithmetic, or resource limits"});
                }
            }
            record.objective_optimality=unsupported&&!optimal?HybridVerificationStatus::unsupported:
                (optimal?HybridVerificationStatus::established:HybridVerificationStatus::refuted);
            if(optimal&&unsupported) {
                record.objective_optimality=HybridVerificationStatus::unsupported;
                record.diagnostics.push_back({DiagnosticCode::unsupported,
                    "hybrid.verification.two_stage_global_optimum",
                    "An unsupported branch could change the global optimum"});
            }
            bool covered=program_valid&&!optimal;
            if(optimal&&candidate!=candidates.end()&&linear) {
                const auto parameter_coordinate=branch.parameter_control_coordinate;
                const double parameter=parameter_coordinate<candidate->anchor.size()?
                    candidate->anchor[parameter_coordinate]:std::numeric_limits<double>::quiet_NaN();
                Interval minimizing_interval=branch.parameter_interval;
                if(branch.objective_slope>0) minimizing_interval.upper=minimizing_interval.lower;
                else if(branch.objective_slope<0) minimizing_interval.lower=minimizing_interval.upper;
                Vector expected_anchor=branch.base;
                bool anchor_exact=true;
                for(std::size_t j=0;j<expected_anchor.size();++j) {
                    double increment=0;
                    if(!exact_product(branch.direction[j],parameter,increment)||
                       !exact_sum(expected_anchor[j],increment,expected_anchor[j])) {
                        anchor_exact=false;
                        relation_exactness=false;
                        break;
                    }
                }
                const auto& solver=candidate->solver_result;
                bool solver_matches=solver.termination==Termination::completed&&
                    solver.outcome.value==MathematicalOutcome::optimal&&solver.primal&&
                    solver.primal->size()==candidate->anchor.size()&&
                    candidate->anchor.size()==expected_anchor.size();
                if(solver_matches) {
                    for(std::size_t j=0;j<candidate->anchor.size();++j)
                        solver_matches=solver_matches&&same((*solver.primal)[j],candidate->anchor[j],policy);
                }
                bool anchor_matches=anchor_exact&&std::isfinite(parameter)&&
                    parameter>=minimizing_interval.lower-tolerance(policy,parameter)&&
                    parameter<=minimizing_interval.upper+tolerance(policy,parameter);
                if(anchor_matches) {
                    for(std::size_t j=0;j<candidate->anchor.size();++j)
                        anchor_matches=anchor_matches&&same(candidate->anchor[j],expected_anchor[j],policy);
                }
                const bool face_domain=relation_domain_supported_for_width(
                    candidate->relation,7,programs[i].relation_limits);
                covered=program_valid&&solver_matches&&anchor_matches&&face_domain&&
                    relation_is_parameter_interval(candidate->relation,branch.base,
                        branch.direction,minimizing_interval,programs[i].relation_limits,
                        cancellation,relation_cancelled,relation_exactness);
                if(cancellation.stop_requested())
                    return OperationStopped{StopReason::cancelled,
                        "Two-stage scalar interval verification cancelled while checking a candidate face"};
                if(covered) record.continuous_coverage=HybridVerificationStatus::established;
                else if(!face_domain||!relation_exactness) {
                    record.continuous_coverage=HybridVerificationStatus::unsupported;
                    coverage_unsupported=true;
                    record.diagnostics.push_back({DiagnosticCode::unsupported,
                        "hybrid.verification.two_stage_face_domain",
                        "Candidate relation is outside the supported representation, exact arithmetic, or resource limits"});
                } else record.diagnostics.push_back({DiagnosticCode::evidence_mismatch,
                    "hybrid.verification.two_stage_face",
                    "Optimal candidate does not equal the independently reconstructed minimizer family"});
            } else if(optimal) {
                covered=false;
                record.diagnostics.push_back({DiagnosticCode::evidence_mismatch,
                    "hybrid.verification.two_stage_missing_face",
                    "An optimal edge path has no candidate continuous minimizer relation"});
            } else if(candidate!=candidates.end()) {
                covered=false;
                record.diagnostics.push_back({DiagnosticCode::evidence_mismatch,
                    "hybrid.verification.two_stage_suboptimal_face",
                    "A candidate face is supplied for a globally suboptimal edge path"});
            }
            if(record.objective_optimality==HybridVerificationStatus::unsupported) {
                record.continuous_coverage=HybridVerificationStatus::unsupported;
                covered=false;
                coverage_unsupported=true;
            } else if(record.continuous_coverage==HybridVerificationStatus::unsupported) {
                covered=false;
            } else if(record.continuous_coverage==HybridVerificationStatus::not_checked) {
                record.continuous_coverage=covered?HybridVerificationStatus::established:
                    HybridVerificationStatus::refuted;
            }
            family_covered=family_covered&&covered;
        }
        report.branches.push_back(std::move(record));
    }
    if(unsupported) {
        report.global_objective_optimality=HybridVerificationStatus::unsupported;
        report.complete_family_coverage=HybridVerificationStatus::unsupported;
    } else if(!global_minimum) {
        report.global_objective_optimality=HybridVerificationStatus::refuted;
        report.complete_family_coverage=HybridVerificationStatus::refuted;
    } else {
        report.global_objective_optimality=HybridVerificationStatus::established;
        report.complete_family_coverage=family_covered?HybridVerificationStatus::established:
            (coverage_unsupported?HybridVerificationStatus::unsupported:HybridVerificationStatus::refuted);
    }
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,
            "Two-stage scalar interval verification cancelled before report publication"};
    return report;
}

} // namespace csl::synthesis
