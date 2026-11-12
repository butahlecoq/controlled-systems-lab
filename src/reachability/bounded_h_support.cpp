#include <csl/reachability/bounded_h_support.hpp>

#include <algorithm>
#include <cmath>
#include <limits>

namespace csl::reachability {
namespace {
struct Range { double lo, hi; };
constexpr double inf = std::numeric_limits<double>::infinity();
double down(double x) { return std::nextafter(x, -inf); }
double up(double x) { return std::nextafter(x, inf); }
Range add(Range a, Range b) { return {down(a.lo+b.lo), up(a.hi+b.hi)}; }
Range negate(Range a) { return {-a.hi, -a.lo}; }
Range multiply(Range a, Range b) {
    const double p[] = {a.lo*b.lo, a.lo*b.hi, a.hi*b.lo, a.hi*b.hi};
    return {down(*std::min_element(p,p+4)), up(*std::max_element(p,p+4))};
}
Range exact(double x) { return {x,x}; }
bool finite(const Vector& v) {
    return std::all_of(v.begin(), v.end(), [](double x) { return std::isfinite(x); });
}
Diagnostics invalid(const char* message) {
    return {{DiagnosticCode::invalid_input, "bounded_h_support", message}};
}
}

std::variant<SupportUpperBound, Diagnostics> residual_corrected_support(
        const BoundedHSupportInput& in, const Vector& lambda, const Vector& mu) {
    const auto n=in.direction.size();
    if (in.inequalities.cols!=n || in.equalities.cols!=n ||
        in.inequalities.rows!=in.upper_bounds.size() || in.equalities.rows!=in.equality_values.size() ||
        lambda.size()!=in.inequalities.rows || mu.size()!=in.equalities.rows ||
        in.lower.size()!=n || in.upper.size()!=n ||
        (n && (in.inequalities.rows>std::numeric_limits<std::size_t>::max()/n ||
               in.equalities.rows>std::numeric_limits<std::size_t>::max()/n)) ||
        in.inequalities.values.size()!=in.inequalities.rows*n ||
        in.equalities.values.size()!=in.equalities.rows*n)
        return invalid("Inconsistent dimensions or matrix storage.");
    if (!finite(in.inequalities.values) || !finite(in.upper_bounds) ||
        !finite(in.equalities.values) || !finite(in.equality_values) ||
        !finite(in.lower) || !finite(in.upper) || !finite(in.direction) ||
        !finite(lambda) || !finite(mu)) return invalid("All coefficients and carrier bounds must be finite.");
    for (std::size_t i=0;i<n;++i) if (in.lower[i]>in.upper[i])
        return invalid("Carrier lower bound exceeds upper bound.");
    for (double x:lambda) if (x<0) return invalid("Inequality multipliers must be nonnegative.");
    Range sum=exact(0);
    for (std::size_t i=0;i<lambda.size();++i)
        sum=add(sum,multiply(exact(lambda[i]),exact(in.upper_bounds[i])));
    for (std::size_t i=0;i<mu.size();++i)
        sum=add(sum,multiply(exact(mu[i]),exact(in.equality_values[i])));
    if (!std::isfinite(sum.lo) || !std::isfinite(sum.hi)) return invalid("Dual constant overflowed.");
    for (std::size_t j=0;j<n;++j) {
        Range residual=exact(in.direction[j]);
        for (std::size_t i=0;i<lambda.size();++i)
            residual=add(residual,negate(multiply(exact(lambda[i]),exact(in.inequalities.values[i*n+j]))));
        for (std::size_t i=0;i<mu.size();++i)
            residual=add(residual,negate(multiply(exact(mu[i]),exact(in.equalities.values[i*n+j]))));
        if (!std::isfinite(residual.lo) || !std::isfinite(residual.hi)) return invalid("Dual residual overflowed.");
        sum=add(sum,multiply(residual,{in.lower[j],in.upper[j]}));
        if (!std::isfinite(sum.lo) || !std::isfinite(sum.hi)) return invalid("Residual bound overflowed.");
    }
    if (!std::isfinite(sum.hi)) return invalid("Residual bound overflowed.");
    return SupportUpperBound{sum.hi};
}
} // namespace csl::reachability

#include <csl/optimization/linear_program.hpp>

namespace csl::reachability {
BoundedHSupportOutcome bounded_h_support(const BoundedHSupportInput& in,
        ProgramIdentity id, const registry::PreparedProvider<registry::LPPort>& provider,
        const ExecutionContext& context) {
    const std::size_t n=in.direction.size(), m=in.upper_bounds.size(), q=in.equality_values.size();
    // Validate the dimensions and finite carrier even when the zero dual is used.
    auto validation=residual_corrected_support(in,Vector(m,0),Vector(q,0));
    if (auto* diagnostics=std::get_if<Diagnostics>(&validation))
        return BoundedHSupportFailure{*diagnostics,{}};
    const auto max=std::numeric_limits<std::size_t>::max();
    if (m>max-q || m+q>max-n || n>max/2)
        return BoundedHSupportFailure{invalid("Dual LP dimensions overflow."),{}};
    const auto columns=m+q+n;
    SparseMatrix a{2*n,columns,{0},{},{}};
    std::vector<Interval> rows;
    for (std::size_t j=0;j<n;++j) {
        for (double endpoint : {in.lower[j], in.upper[j]}) {
            for (std::size_t i=0;i<m;++i) {
                const double value=-endpoint*in.inequalities.values[i*n+j];
                if (!std::isfinite(value)) return BoundedHSupportFailure{invalid("Dual LP coefficient overflowed."),{}};
                if (value!=0) { a.column_indices.push_back(i); a.values.push_back(value); }
            }
            for (std::size_t i=0;i<q;++i) {
                const double value=-endpoint*in.equalities.values[i*n+j];
                if (!std::isfinite(value)) return BoundedHSupportFailure{invalid("Dual LP coefficient overflowed."),{}};
                if (value!=0) { a.column_indices.push_back(m+i); a.values.push_back(value); }
            }
            a.column_indices.push_back(m+q+j); a.values.push_back(-1);
            a.row_offsets.push_back(a.values.size());
            const double rhs=-endpoint*in.direction[j];
            if (!std::isfinite(rhs)) return BoundedHSupportFailure{invalid("Dual LP right hand side overflowed."),{}};
            rows.push_back({{},rhs});
        }
    }
    Vector objective; objective.reserve(columns);
    objective.insert(objective.end(),in.upper_bounds.begin(),in.upper_bounds.end());
    objective.insert(objective.end(),in.equality_values.begin(),in.equality_values.end());
    objective.insert(objective.end(),n,1.0);
    std::vector<Interval> variables(columns);
    for (std::size_t i=0;i<m;++i) variables[i].lower=0;
    auto made=optimization::make_linear_program({std::move(id),std::move(objective),0,
        std::move(a),std::move(variables),std::move(rows)});
    if (auto* diagnostics=std::get_if<Diagnostics>(&made)) return BoundedHSupportFailure{*diagnostics,{}};
    const auto& program=std::get<LinearProgram>(made);
    registry::RegisteredLPQueryRunner runner(provider);
    auto answer=runner.solve(program,context);
    auto records=runner.records();
    if (auto* unsupported=std::get_if<Unsupported>(&answer))
        return BoundedHSupportFailure{*unsupported,std::move(records)};
    const auto& result=std::get<ProgramResult>(answer);
    if (result.termination!=Termination::completed || result.outcome.value!=MathematicalOutcome::optimal ||
        result.outcome.subject!=program.identity() || !result.primal || result.primal->size()!=columns || !finite(*result.primal)) {
        StopReason reason=StopReason::numerical_failure;
        if (result.termination==Termination::cancelled) reason=StopReason::cancelled;
        else if (result.termination==Termination::deadline_expired) reason=StopReason::deadline_expired;
        else if (result.termination==Termination::resource_limit) reason=StopReason::resource_limit;
        return BoundedHSupportFailure{OperationStopped{reason,"Dual candidate LP did not return a usable optimum."},std::move(records)};
    }
    Vector lambda(result.primal->begin(),result.primal->begin()+m);
    for (auto& x:lambda) x=std::max(0.0,x);
    Vector mu(result.primal->begin()+m,result.primal->begin()+m+q);
    auto corrected=residual_corrected_support(in,lambda,mu);
    if (auto* diagnostics=std::get_if<Diagnostics>(&corrected))
        return BoundedHSupportFailure{*diagnostics,std::move(records)};
    return BoundedHSupportResult{std::get<SupportUpperBound>(corrected),std::move(records)};
}
} // namespace csl::reachability

namespace csl::reachability {
BoundedHAxisOutcome bounded_h_axis_cover(const BoundedHSupportInput& input,
        ProgramIdentity identity, const registry::PreparedProvider<registry::LPPort>& provider,
        const ExecutionContext& context) {
    BoundedHAxisCover cover;
    const auto n=input.direction.size();
    cover.lower.reserve(n);
    cover.upper.reserve(n);
    auto validation=residual_corrected_support(input, Vector(input.upper_bounds.size(),0),
        Vector(input.equality_values.size(),0));
    if (auto* diagnostics=std::get_if<Diagnostics>(&validation))
        return BoundedHAxisFailure{std::move(cover),0,false,*diagnostics};
    auto query=input;
    for (std::size_t j=0;j<n;++j) {
        for (bool upper : {false,true}) {
            query.direction.assign(n,0);
            query.direction[j]=upper ? 1 : -1;
            ProgramIdentity id=identity;
            id.program.value += "/axis/"+std::to_string(j)+(upper ? "/upper" : "/lower");
            auto answer=bounded_h_support(query,std::move(id),provider,context);
            if (auto* failure=std::get_if<BoundedHSupportFailure>(&answer)) {
                cover.lp_calls.insert(cover.lp_calls.end(),failure->lp_calls.begin(),failure->lp_calls.end());
                return BoundedHAxisFailure{std::move(cover),j,upper,std::move(failure->cause)};
            }
            auto result=std::get<BoundedHSupportResult>(std::move(answer));
            cover.lp_calls.insert(cover.lp_calls.end(),result.lp_calls.begin(),result.lp_calls.end());
            if (upper) cover.upper.push_back(result.bound.value);
            else cover.lower.push_back(-result.bound.value);
        }
        if (cover.lower.back()>cover.upper.back())
            return BoundedHAxisFailure{std::move(cover),j,true,
                OperationStopped{StopReason::numerical_failure,"Axis bounds are inconsistent; no emptiness conclusion is drawn."}};
    }
    return cover;
}
} // namespace csl::reachability
