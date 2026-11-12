#include <csl/reachability/inner_template.hpp>

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>

namespace csl::reachability {
namespace {
constexpr double inf=std::numeric_limits<double>::infinity();
struct Range { double lo, hi; };
Range add(Range a,Range b) {
    if(a.lo==0 && a.hi==0) return b;
    if(b.lo==0 && b.hi==0) return a;
    if(a.lo==a.hi && b.lo==b.hi && a.lo==-b.lo) return {0,0};
    return {std::nextafter(a.lo+b.lo,-inf),std::nextafter(a.hi+b.hi,inf)};
}
Range product(double a,double b) {
    if(a==0 || b==0) return {0,0};
    if(a==1) return {b,b};
    if(b==1) return {a,a};
    if(a==-1) return {-b,-b};
    if(b==-1) return {-a,-a};
    const double value=a*b;
    return {std::nextafter(value,-inf),std::nextafter(value,inf)};
}
Range dot(const Matrix& A,std::size_t row,const Vector& x) {
    Range total{0,0};
    for(std::size_t j=0;j<A.cols;++j) total=add(total,product(A.values[row*A.cols+j],x[j]));
    return total;
}
double support(const Matrix& A,std::size_t row,const Matrix& G,InnerTemplateNorm norm) {
    double sum=0;
    for(std::size_t column=0;column<G.cols;++column) {
        Range total{0,0};
        for(std::size_t j=0;j<G.rows;++j)
            total=add(total,product(A.values[row*A.cols+j],G.values[j*G.cols+column]));
        double value=std::max(std::abs(total.lo),std::abs(total.hi));
        if(value==0) continue;
        if(norm==InnerTemplateNorm::euclidean_ball) value=std::nextafter(value*value,inf);
        sum=std::nextafter(sum+value,inf);
    }
    return norm==InnerTemplateNorm::euclidean_ball && sum!=0 ? std::nextafter(std::sqrt(sum),inf) : sum;
}
bool finite(const Vector& x) { return std::all_of(x.begin(),x.end(),[](double v){return std::isfinite(v);}); }
Diagnostic invalid(std::string text) { return {DiagnosticCode::invalid_input,"inner_template",std::move(text)}; }
void validate(const InnerTemplateInput& in) {
    const auto n=in.center.size();
    if(in.norm!=InnerTemplateNorm::independent_intervals && in.norm!=InnerTemplateNorm::euclidean_ball)
        throw std::invalid_argument("unknown inner-template norm");
    const auto maximum=std::numeric_limits<std::size_t>::max();
    if(n && (in.directions.cols>maximum/n || in.inequalities.rows>maximum/n || in.equalities.rows>maximum/n))
        throw std::invalid_argument("inner-template dimensions overflow");
    if(!n || in.directions.rows!=n || in.directions.values.size()!=n*in.directions.cols ||
       in.inequalities.cols!=n || in.inequalities.values.size()!=in.inequalities.rows*n ||
       in.upper_bounds.size()!=in.inequalities.rows || in.equalities.cols!=n ||
       in.equalities.values.size()!=in.equalities.rows*n || in.equality_values.size()!=in.equalities.rows ||
       !finite(in.center) || !finite(in.directions.values) || !finite(in.inequalities.values) ||
       !finite(in.upper_bounds) || !finite(in.equalities.values) || !finite(in.equality_values))
        throw std::invalid_argument("finite dimension-matched center, template and H rows required");
}
}
Diagnostics check_inner_template(const InnerTemplateInput& in,const InnerTemplate& set) {
    Diagnostics errors;
    try { validate(in); } catch(const std::invalid_argument& e) { return {invalid(e.what())}; }
    if(set.center!=in.center || set.factor.rows!=in.center.size() || set.factor.cols!=in.directions.cols ||
       set.factor.values.size()!=in.directions.values.size() || !finite(set.factor.values) || set.norm!=in.norm)
        return {invalid("candidate shape differs from the supplied physical template")};
    for(std::size_t i=0;i<in.inequalities.rows;++i) {
        const auto center=dot(in.inequalities,i,set.center);
        const double radius=support(in.inequalities,i,set.factor,set.norm);
        const auto maximum=add(center,{radius,radius});
        if(!std::isfinite(maximum.hi) || maximum.hi>in.upper_bounds[i])
            errors.push_back({DiagnosticCode::evidence_mismatch,"inner_template.inequality",std::to_string(i)});
    }
    for(std::size_t i=0;i<in.equalities.rows;++i) {
        const auto center=dot(in.equalities,i,set.center);
        const double radius=support(in.equalities,i,set.factor,set.norm);
        if(center.lo!=in.equality_values[i] || center.hi!=in.equality_values[i] || radius!=0)
            errors.push_back({DiagnosticCode::evidence_mismatch,"inner_template.equality",std::to_string(i)});
    }
    return errors;
}
InnerTemplateResult inscribe_template(const InnerTemplateInput& in) {
    try { validate(in); } catch(const std::invalid_argument& e) { return invalid(e.what()); }
    InnerTemplate result{in.center,in.directions,in.norm,0,{},{},0,true};
    for(auto& value:result.factor.values) value=0;
    if(!check_inner_template(in,result).empty()) return invalid("center is not independently admitted in the stored H set");
    bool nonzero=std::any_of(in.directions.values.begin(),in.directions.values.end(),[](double v){return v!=0;});
    if(!nonzero) return result;
    double radius=inf;
    for(std::size_t i=0;i<in.inequalities.rows;++i) {
        const auto center=dot(in.inequalities,i,in.center);
        const double slack=std::nextafter(in.upper_bounds[i]-center.hi,-inf);
        const double width=support(in.inequalities,i,in.directions,in.norm);
        result.row_support_upper.push_back(width);
        result.row_slack_lower.push_back(slack);
        if(width>0) radius=std::min(radius,std::max(0.0,std::nextafter(slack/width,-inf)));
    }
    for(std::size_t i=0;i<in.equalities.rows;++i)
        if(support(in.equalities,i,in.directions,in.norm)!=0) radius=0;
    if(!std::isfinite(radius)) return Diagnostic{DiagnosticCode::unsupported,"inner_template.radius","template scale is unbounded; supply a finite carrier"};
    result.radius=radius;
    for(std::size_t i=0;i<result.factor.values.size();++i) result.factor.values[i]=radius*in.directions.values[i];
    // Admission checks the rounded stored factor, not its unrounded formula.
    while(!check_inner_template(in,result).empty() && result.rounding_shrinks<64) {
        result.radius*=0.5;
        for(auto& value:result.factor.values) value*=0.5;
        ++result.rounding_shrinks;
    }
    if(!check_inner_template(in,result).empty()) return invalid("rounded template could not be admitted");
    result.point=std::all_of(result.factor.values.begin(),result.factor.values.end(),[](double v){return v==0;});
    return result;
}
} // namespace csl::reachability
