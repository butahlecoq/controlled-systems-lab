#include <csl/adapters/convex/highs.hpp>
#include <Highs.h>
#include <algorithm>
#include <cmath>
#include <iomanip>
#include <limits>
#include <sstream>
#include <stdexcept>
namespace csl::adapters::convex {
namespace {
using namespace optimization;
constexpr const char* version="1.0.0+highs.1.11.0";
static_assert(std::numeric_limits<HighsInt>::is_signed && std::numeric_limits<HighsInt>::digits==31);
using Wide=std::uintmax_t;
constexpr std::optional<Wide> add(Wide a,Wide b) {
    if(b>std::numeric_limits<Wide>::max()-a) return {};
    return a+b;
}
constexpr std::optional<Wide> mul(Wide a,Wide b) {
    if(a && b>std::numeric_limits<Wide>::max()/a) return {};
    return a*b;
}
static_assert(!add(std::numeric_limits<Wide>::max(),1));
static_assert(!mul(std::numeric_limits<Wide>::max(),2));
static_assert(mul(0,std::numeric_limits<Wide>::max())==0);
static_assert(add(std::numeric_limits<Wide>::max()-1,1)==std::numeric_limits<Wide>::max());
Diagnostics unsupported(std::string field,std::string text) {
    return {{DiagnosticCode::unsupported,std::move(field),std::move(text)}};
}
template<class T> bool extent(Wide count) {
    const auto bytes=mul(count,sizeof(T));
    return bytes && count<=std::vector<T>{}.max_size() && count<=std::numeric_limits<std::size_t>::max() &&
        *bytes<=std::numeric_limits<std::size_t>::max() && *bytes<=static_cast<Wide>(std::numeric_limits<std::ptrdiff_t>::max());
}
// Pure representability admission. No native object or size-proportional buffer
// exists here; the declared cap applies to linear objectives as well as QPs.
Diagnostics admission(const ConvexProgram& p) {
    const auto& q=p.quadratic_program();
    const Wide n=q.variables().size(),m=q.rows().size();
    if(n>4096) return unsupported("highs.convex.variables","maximum_variables=4096; actual="+std::to_string(n));
    const auto csr=std::get<numeric::CsrInput>(q.constraints().descriptor());
    // Reserve a private free row and its unit entry whenever effective A is empty.
    // The zero-Q route does not use it; this conservative preflight still precedes translation.
    const bool empty_a=std::none_of(csr.values.begin(),csr.values.end(),[](double value){return value!=0;});
    const Wide padding=n>0 && empty_a?1:0;
    const auto mn=add(m,padding),np=add(n,1),native_nnz=add(csr.values.size(),padding);
    const Wide limit=static_cast<Wide>(kHighsIInf);
    if(!mn || !np || !native_nnz) return unsupported("highs.convex.capacity","dimension or private-entry addition overflow");
    const auto mp=add(*mn,1),total=add(n,*mn),square=mul(n,n),twice_triangle=mul(n,*np),capacity=mul(2,*np);
    if(!mp || !total || !square || !twice_triangle || !capacity) return unsupported("highs.convex.capacity","derived extent overflow");
    const auto factor=mul(*capacity,*capacity);
    if(!factor) return unsupported("highs.convex.capacity","factor square overflow");
    const Wide nnz=*native_nnz;
    for(Wide count:{n,*mn,*np,*mp,*total,nnz,*square,*twice_triangle,*twice_triangle/2,n?*factor:0})
        if(count>limit || !extent<double>(count) || !extent<HighsInt>(count))
            return unsupported("highs.convex.capacity","native integer/container/storage extent exceeded");
    const auto translated_entries=mul(nnz,sizeof(double)+sizeof(HighsInt));
    const auto translated_starts=mul(*np,sizeof(HighsInt));
    const auto translated_bytes=translated_entries && translated_starts?add(*translated_entries,*translated_starts):std::nullopt;
    if(!translated_bytes || !extent<std::byte>(*translated_bytes))
        return unsupported("highs.convex.capacity","translated matrix byte sum exceeded");
    if(n) {
        const auto factor_bytes=mul(*factor,sizeof(double));
        const auto two_factors=factor_bytes?mul(*factor_bytes,2):std::nullopt;
        const auto dense_bytes=mul(*square,sizeof(double)),outer_bytes=mul(n,sizeof(std::vector<double>));
        const auto dense_total=dense_bytes && outer_bytes?add(*dense_bytes,*outer_bytes):std::nullopt;
        const auto entries=mul(*square,sizeof(double)+sizeof(HighsInt));
        const auto starts=mul(*np,sizeof(HighsInt));
        const auto matrix_bytes=entries && starts?add(*entries,*starts):std::nullopt;
        const auto transpose_bytes=matrix_bytes?mul(*matrix_bytes,2):std::nullopt;
        if(!extent<std::vector<double>>(n) || !two_factors || !dense_total || !transpose_bytes ||
            !extent<std::byte>(*two_factors) || !extent<std::byte>(*dense_total) || !extent<std::byte>(*transpose_bytes))
            return unsupported("highs.convex.capacity","transient storage byte sum exceeded");
    }
    for(double value:csr.values) if(value!=0 && std::abs(value)<=1e-12)
        return unsupported("highs.convex.matrix","nonzero coefficient at or below native removal threshold 1e-12");
    // Linear objectives have an owning O(n) empty CSR Hessian. Do not scan n^2.
    if(std::holds_alternative<QuadraticCoefficients>(q.objective().coefficients()))
        for(std::size_t i=0;i<n;++i) for(std::size_t j=0;j<=i;++j)
            if(q.hessian()(i,j)!=0 && std::abs(q.hessian()(i,j))<=1e-12)
                return unsupported("highs.convex.hessian","nonzero coefficient at or below native removal threshold 1e-12");
    return {};
}
Diagnostics admission(const ExecutionContext& c) {
    if(!c.resources) return {{DiagnosticCode::invalid_input,"resources","resource policy is required"}};
    if(auto d=check_resources(*c.resources);!d.empty()) return d;
    if(c.resources->memory_bytes) return unsupported("resources.memory_bytes","native memory admission unavailable");
    if(!std::isfinite(c.numerical.absolute_tolerance) || c.numerical.absolute_tolerance<0 ||
        !std::isfinite(c.numerical.relative_tolerance) || c.numerical.relative_tolerance<0)
        return {{DiagnosticCode::invalid_input,"numerical","finite nonnegative tolerances required"}};
    return {};
}
struct SetupError : std::runtime_error { using std::runtime_error::runtime_error; };
void require(HighsStatus status) {
    if(status!=HighsStatus::kOk) throw SetupError("native configuration/load/start returned non-OK status "+std::to_string(static_cast<int>(status)));
}
bool finite(const Vector& values,std::size_t n) {
    return values.size()==n && std::all_of(values.begin(),values.end(),[](double x){return std::isfinite(x);});
}
ProgramResult result_for(const ConvexProgram& p) {
    return {Termination::numerical_failure,{p.identity(),MathematicalOutcome::undetermined,Unestablished{},
        {"binary64 numerical PSD and original-space KKT checks; no validated outcome certificate"}},{},{},{},{}};
}
struct Capture {
    const ExecutionContext& context;
    std::optional<Termination> stop;
    std::string log;
    void poll() {
        if(stop) return;
        if(context.cancellation.stop_requested()) stop=Termination::cancelled;
        else if(context.deadline && std::chrono::steady_clock::now()>=*context.deadline) stop=Termination::resource_limit;
    }
};
struct Callbacks {
    Highs& h;
    Callbacks(Highs& native,Capture& capture):h(native) {
        require(h.setCallback([](int type,const std::string& message,const HighsCallbackOutput*,HighsCallbackInput* input,void* user) {
            auto& state=*static_cast<Capture*>(user);
            if(type==kCallbackLogging) state.log+=message;
            if(type==kCallbackSimplexInterrupt) { state.poll(); if(input && state.stop) input->user_interrupt=true; }
        },&capture));
        try { require(h.startCallback(kCallbackLogging)); require(h.startCallback(kCallbackSimplexInterrupt)); }
        catch(...) { h.setCallback(HighsCallbackFunctionType{},nullptr); throw; }
    }
    ~Callbacks() { h.setCallback(HighsCallbackFunctionType{},nullptr); }
};
void configure(Highs& h,const ExecutionContext& c,const HighsConvexOptions& options,bool qp) {
    require(h.clear());
    require(h.setOptionValue("output_flag",true)); require(h.setOptionValue("log_to_console",true));
    require(h.setOptionValue("solver",qp?"choose":"simplex")); require(h.setOptionValue("presolve","off"));
    require(h.setOptionValue("parallel","off")); require(h.setOptionValue("threads",HighsInt{1}));
    require(h.setOptionValue("random_seed",HighsInt{0})); require(h.setOptionValue("allow_unbounded_or_infeasible",false));
    require(h.setOptionValue("small_matrix_value",1e-12)); require(h.setOptionValue("large_matrix_value",kHighsInf));
    require(h.setOptionValue("infinite_bound",kHighsInf)); require(h.setOptionValue("infinite_cost",kHighsInf));
    const double tolerance=std::max(c.numerical.absolute_tolerance,1e-10);
    require(h.setOptionValue("primal_feasibility_tolerance",tolerance)); require(h.setOptionValue("dual_feasibility_tolerance",tolerance));
    require(h.setOptionValue("simplex_iteration_limit",static_cast<HighsInt>(options.feasibility_iteration_limit.value_or(kHighsIInf))));
    require(h.setOptionValue("qp_iteration_limit",static_cast<HighsInt>(options.qp_iteration_limit.value_or(kHighsIInf))));
    require(h.setOptionValue("qp_regularization_value",0.0)); require(h.setOptionValue("qp_nullspace_limit",HighsInt{4096}));
    require(h.setOptionValue("use_warm_start",true));
    bool warm=false; HighsInt nullspace=0; double regularization=-1;
    require(h.getOptionValue("use_warm_start",warm)); require(h.getOptionValue("qp_nullspace_limit",nullspace));
    require(h.getOptionValue("qp_regularization_value",regularization));
    if(!warm || nullspace!=4096 || regularization!=0) throw SetupError("native audited profile readback differs");
    h.zeroAllClocks();
}
double deadline(Highs& h,const ExecutionContext& c) {
    const auto remaining=c.deadline?std::max(0.0,std::chrono::duration<double>(*c.deadline-std::chrono::steady_clock::now()).count()):kHighsInf;
    require(h.setOptionValue("time_limit",remaining));
    return remaining;
}
HighsModel translate(const ConvexProgram& p) {
    const auto& q=p.quadratic_program();
    HighsModel model; auto& lp=model.lp_; auto& hessian=model.hessian_;
    lp.num_col_=static_cast<HighsInt>(q.variables().size()); lp.num_row_=static_cast<HighsInt>(q.rows().size());
    lp.sense_=ObjSense::kMinimize;
    std::visit([&](const auto& objective) {
        using T=std::decay_t<decltype(objective)>;
        if constexpr(std::is_same_v<T,LinearCoefficients>) {
            lp.col_cost_.assign(objective.coefficients.values().begin(),objective.coefficients.values().end()); lp.offset_=objective.offset;
        } else if constexpr(std::is_same_v<T,QuadraticCoefficients>) {
            lp.col_cost_.assign(objective.linear.values().begin(),objective.linear.values().end()); lp.offset_=objective.offset;
            hessian.dim_=lp.num_col_; hessian.format_=HessianFormat::kTriangular; hessian.start_.assign(1,0);
            for(std::size_t j=0;j<q.variables().size();++j) {
                for(std::size_t i=j;i<q.variables().size();++i) if(objective.Q(i,j)!=0) {
                    hessian.index_.push_back(static_cast<HighsInt>(i)); hessian.value_.push_back(objective.Q(i,j));
                }
                hessian.start_.push_back(static_cast<HighsInt>(hessian.value_.size()));
            }
            if(hessian.value_.empty()) hessian.clear();
        }
    },q.objective().coefficients());
    for(const auto& b:q.variables()) { lp.col_lower_.push_back(b.lower.value_or(-kHighsInf)); lp.col_upper_.push_back(b.upper.value_or(kHighsInf)); }
    for(const auto& b:q.rows()) { lp.row_lower_.push_back(b.lower.value_or(-kHighsInf)); lp.row_upper_.push_back(b.upper.value_or(kHighsInf)); }
    const auto csr=std::get<numeric::CsrInput>(q.constraints().descriptor());
    const bool private_free_row=!hessian.value_.empty() &&
        std::none_of(csr.values.begin(),csr.values.end(),[](double value){return value!=0;});
    // -inf < x0 < +inf changes neither the feasible x-space nor the objective.
    // Its unit entry avoids the pinned basis empty-transpose invariant; a zero
    // row cannot do that, including when authored rows have only zero entries.
    if(private_free_row) {++lp.num_row_;lp.row_lower_.push_back(-kHighsInf);lp.row_upper_.push_back(kHighsInf);}
    auto& matrix=lp.a_matrix_; matrix.num_row_=lp.num_row_; matrix.num_col_=lp.num_col_; matrix.format_=MatrixFormat::kColwise;
    matrix.start_.assign(q.variables().size()+1,0);
    for(auto j:csr.column_indices) ++matrix.start_[j+1];
    if(private_free_row) ++matrix.start_[1];
    for(std::size_t j=0;j<q.variables().size();++j) matrix.start_[j+1]+=matrix.start_[j];
    auto next=matrix.start_;
    const auto native_entries=csr.values.size()+static_cast<std::size_t>(private_free_row); // checked in admission
    matrix.index_.resize(native_entries);matrix.value_.resize(native_entries);
    for(std::size_t i=0;i<csr.rows;++i) for(auto k=csr.row_offsets[i];k<csr.row_offsets[i+1];++k) {
        const auto slot=static_cast<std::size_t>(next[csr.column_indices[k]]++);
        matrix.index_[slot]=static_cast<HighsInt>(i); matrix.value_[slot]=csr.values[k];
    }
    if(private_free_row) {
        const auto slot=static_cast<std::size_t>(next[0]++);
        matrix.index_[slot]=static_cast<HighsInt>(csr.rows);matrix.value_[slot]=1;
    }
    return model;
}
bool feasible_start(const Highs& h,const HighsLp& lp,const ConvexProgram& p,double tolerance) {
    const auto& s=h.getSolution(); const auto& b=h.getBasis();
    const auto n=static_cast<std::size_t>(lp.num_col_),m=static_cast<std::size_t>(lp.num_row_);
    if(!s.value_valid || !b.valid || !finite(s.col_value,n) || !finite(s.row_value,m) || b.col_status.size()!=n || b.row_status.size()!=m) return false;
    auto feasible=[&](double value,double lower,double upper) {
        double violation=0;
        if(value<lower-tolerance) violation=lower-value;
        else if(value>upper+tolerance) violation=value-upper;
        return violation<=tolerance;
    };
    for(std::size_t j=0;j<n;++j) if(!feasible(s.col_value[j],lp.col_lower_[j],lp.col_upper_[j])) return false;
    const auto csr=std::get<numeric::CsrInput>(p.quadratic_program().constraints().descriptor());
    if(m!=csr.rows && m!=csr.rows+1) return false;
    for(std::size_t i=0;i<m;++i) {
        double activity=0;
        if(i<csr.rows) for(auto k=csr.row_offsets[i];k<csr.row_offsets[i+1];++k) activity+=csr.values[k]*s.col_value[csr.column_indices[k]];
        else activity=s.col_value[0]; // Private free row, separate from every authored activity.
        if(!std::isfinite(activity) || !feasible(s.row_value[i],lp.row_lower_[i],lp.row_upper_[i]) ||
            !feasible(activity,lp.row_lower_[i],lp.row_upper_[i]) || std::abs(activity-s.row_value[i])>tolerance) return false;
    }
    return true;
}
void classify(ProgramResult& result,HighsStatus api,HighsModelStatus status) {
    switch(status) {
        case HighsModelStatus::kTimeLimit: case HighsModelStatus::kIterationLimit: case HighsModelStatus::kMemoryLimit:
        case HighsModelStatus::kObjectiveBound: case HighsModelStatus::kObjectiveTarget: case HighsModelStatus::kSolutionLimit:
            result.termination=Termination::resource_limit; return;
        case HighsModelStatus::kInterrupt: result.termination=Termination::cancelled; return;
        default: break;
    }
    if(api==HighsStatus::kError) return;
    switch(status) {
        case HighsModelStatus::kOptimal: result.termination=Termination::completed; result.outcome.value=MathematicalOutcome::optimal; break;
        case HighsModelStatus::kInfeasible: result.termination=Termination::completed; result.outcome.value=MathematicalOutcome::infeasible; break;
        case HighsModelStatus::kUnbounded: result.termination=Termination::completed; result.outcome.value=MathematicalOutcome::unbounded; break;
        case HighsModelStatus::kUnboundedOrInfeasible: result.termination=Termination::completed; break;
        default: break;
    }
}
bool split(std::span<const double> dual,std::span<const Interval> bounds,Vector& lower,Vector& upper) {
    if(dual.size()!=bounds.size()) return false;
    for(std::size_t i=0;i<bounds.size();++i) {
        if(!std::isfinite(dual[i]) || (dual[i]>0 && !bounds[i].lower) || (dual[i]<0 && !bounds[i].upper)) return false;
        lower.push_back(std::max(dual[i],0.0)); upper.push_back(std::max(-dual[i],0.0));
    }
    return true;
}
bool passes(const ProgramResult& r,NumericalPolicy policy) {
    if(!r.primal || !r.residuals.primal || !r.residuals.dual || !r.residuals.dual->stationarity || !r.residuals.dual->signs || !r.residuals.dual->complementarity) return false;
    for(const auto* m:{&r.residuals.primal->rows,&r.residuals.primal->variables,&*r.residuals.dual->stationarity,&*r.residuals.dual->signs,&*r.residuals.dual->complementarity})
        if(m->violation>policy.absolute_tolerance+policy.relative_tolerance*m->scale) return false;
    return true;
}
void append_attempt_residuals(std::ostringstream& raw,const char* attempt,const ProgramResult& result) {
    auto measure=[&](const char* name,const ResidualMeasure& value) {
        raw<<'\n'<<attempt<<".check."<<name<<".violation="<<value.violation
           <<'\n'<<attempt<<".check."<<name<<".scale="<<value.scale;
    };
    if(result.residuals.primal) {
        measure("rows",result.residuals.primal->rows);
        measure("variables",result.residuals.primal->variables);
    }
    if(result.residuals.dual) {
        if(result.residuals.dual->stationarity) measure("stationarity",*result.residuals.dual->stationarity);
        if(result.residuals.dual->signs) measure("signs",*result.residuals.dual->signs);
        if(result.residuals.dual->complementarity) measure("complementarity",*result.residuals.dual->complementarity);
    }
}
void candidate(ProgramResult& result,const ConvexProgram& p,const ExecutionContext& c,const HighsSolution& s,std::ostringstream& raw,bool allow_dual,bool private_free_row=false) {
    const auto& q=p.quadratic_program();
    if(!s.value_valid || !finite(s.col_value,q.variables().size())) return;
    result.primal=s.col_value;
    auto evaluated=evaluate_primal(p,s.col_value,c.numerical,{{"csl.convex.highs.primal"},"1"});
    const auto* e=std::get_if<ConvexPrimalEvaluation>(&evaluated);
    if(!e) { raw<<"\nprimal.checks_unavailable=original-space arithmetic"; return; }
    result.residuals.primal=e->residuals;
    raw<<"\nobjective.original="<<e->original_objective<<"\nobjective.solver="<<e->solver_objective;
    if(private_free_row && allow_dual) {
        // A free row has no lower/upper multiplier. Dropping a nonzero native
        // value would change stationarity in original coordinates, so withhold it.
        if(!s.dual_valid || s.row_dual.size()!=q.rows().size()+1 || !std::isfinite(s.row_dual.back()) || s.row_dual.back()!=0) {
            raw<<"\ndual.unavailable=private free row multiplier is not zero";return;
        }
        raw<<"\ndual.private_free_row=0";
    }
    DualMultipliers multipliers;
    bool zero_norm=false;
    if(p.reformulation()) {
        const auto coefficients=std::get<ResidualCoefficients>(p.original_objective().coefficients());
        zero_norm=true;
        for(std::size_t i=0;i<coefficients.target.size();++i) {
            double residual=-coefficients.target[i];
            for(std::size_t j=0;j<s.col_value.size();++j) residual+=coefficients.map(i,j)*s.col_value[j];
            zero_norm=zero_norm && residual==0;
        }
    }
    if(zero_norm) {
        multipliers={Vector(q.rows().size(),0),Vector(q.rows().size(),0),Vector(q.variables().size(),0),Vector(q.variables().size(),0)};
        raw<<"\nnorm.subgradient=checked-componentwise-zero";
    } else {
        if(!allow_dual || !s.dual_valid || s.row_dual.size()<q.rows().size() ||
            !split(std::span<const double>(s.row_dual).first(q.rows().size()),q.rows(),multipliers.row_lower,multipliers.row_upper) ||
            !split(s.col_dual,q.variables(),multipliers.variable_lower,multipliers.variable_upper)) {raw<<"\ndual.unavailable=invalid native multiplier mapping";return;}
        if(p.reformulation()) {
            if(!(e->original_objective>0)) {raw<<"\ndual.unavailable=unresolved norm gradient";return;}
            for(auto* values:{&multipliers.row_lower,&multipliers.row_upper,&multipliers.variable_lower,&multipliers.variable_upper})
                for(double& value:*values) {
                    const double converted=(value/e->original_objective)*0.5;
                    if(!std::isfinite(converted) || (value!=0 && converted==0)) {raw<<"\ndual.unavailable=multiplier conversion arithmetic";return;}
                    value=converted;
                }
        }
    }
    auto dual=evaluate_dual(p,*result.primal,multipliers,c.numerical,{{"csl.convex.highs.kkt"},"1"});
    if(auto* d=std::get_if<DualResiduals>(&dual)) result.residuals.dual=*d;
    else raw<<"\ndual.unavailable=original-space KKT arithmetic";
}
class Workspace final : public ConvexWorkspace {
    HighsConvexOptions options_;
    std::unique_ptr<Highs> feasibility_,solver_;
    ProgramOutcome solve_native(const ConvexProgram& p,const ExecutionContext& c) {
        if(auto d=admission(p);!d.empty()) return Unsupported{std::move(d)};
        if(auto d=admission(c);!d.empty()) return Unsupported{std::move(d)};
        auto result=result_for(p); Capture capture{c,{},{}}; std::ostringstream raw;
        raw<<std::setprecision(17)<<"adapter.version="<<version<<"\nnative.version="<<highsVersion()
            <<"\nnative.archive_sha256=2b44b074cf41439325ce4d0bbdac2d51379f56faf17ba15320a410d3c1f07275"
            <<"\nnative.downstream.hvectorbase_sha256="<<CSL_HIGHS_PATCHED_SOURCE_SHA256
            <<"\nprogram.original="<<p.identity().program.value<<"\nprogram.solver="<<p.quadratic_program().identity().program.value
            <<"\nprofile.maximum_variables=4096\nprofile.highs_int_bits=32\noptions.qp_nullspace_limit=4096"
            <<"\noptions.qp_regularization_value=0\noptions.use_warm_start=true\noptions.presolve=off\noptions.threads=1\noptions.parallel=off"
            <<"\noptions.small_matrix_value=1e-12\noptions.infinite_bound=inf\noptions.infinite_cost=inf\noptions.large_matrix_value=inf"
            <<"\noptions.native_tolerance="<<std::max(c.numerical.absolute_tolerance,1e-10)
            <<"\noptions.feasibility_iteration_limit="<<options_.feasibility_iteration_limit.value_or(kHighsIInf)
            <<"\noptions.qp_iteration_limit="<<options_.qp_iteration_limit.value_or(kHighsIInf);
        auto finish=[&]() -> ProgramOutcome {
            capture.poll();
            if(capture.stop) { result.termination=*capture.stop; result.outcome.value=MathematicalOutcome::undetermined; }
            auto measure=[&](const char* name,const ResidualMeasure& value) {
                raw<<"\ncheck."<<name<<".violation="<<value.violation<<"\ncheck."<<name<<".scale="<<value.scale;
            };
            if(result.residuals.primal) {measure("rows",result.residuals.primal->rows);measure("variables",result.residuals.primal->variables);}
            if(result.residuals.dual) {
                if(result.residuals.dual->stationarity) measure("stationarity",*result.residuals.dual->stationarity);
                if(result.residuals.dual->signs) measure("signs",*result.residuals.dual->signs);
                if(result.residuals.dual->complementarity) measure("complementarity",*result.residuals.dual->complementarity);
            }
            raw<<"\ncertificates=unavailable\nbounds=unavailable\nbasis=unavailable\nfamilies=unavailable\nnative.log:\n"<<capture.log;
            result.raw_diagnostics=raw.str(); return result;
        };
        capture.poll(); if(capture.stop) {raw<<"\nnative_run=false\nnative.info=unavailable";return finish();}
        const auto& q=p.quadratic_program();
        if(q.variables().empty()) {
            const bool feasible=std::all_of(q.rows().begin(),q.rows().end(),[](const Interval& b){return (!b.lower || *b.lower<=0) && (!b.upper || *b.upper>=0);});
            result.termination=Termination::completed; result.outcome.value=feasible?MathematicalOutcome::optimal:MathematicalOutcome::infeasible;
            if(feasible) {
                HighsSolution s; s.value_valid=true; s.dual_valid=true; s.row_value.assign(q.rows().size(),0); s.row_dual.assign(q.rows().size(),0);
                candidate(result,p,c,s,raw,true);
                if(!passes(result,c.numerical)) {result.termination=Termination::numerical_failure;result.outcome.value=MathematicalOutcome::undetermined;}
            }
            raw<<"\nnative_run=false\nwrapper.decision=constant_rows\nnative.info=unavailable";return finish();
        }
        // Admission precedes model conversion and both lazy native constructors.
        auto model=translate(p); const bool qp=!model.hessian_.value_.empty();
        const bool private_free_row=static_cast<std::size_t>(model.lp_.num_row_)!=q.rows().size();
        raw<<"\nmodel.private_free_row="<<(private_free_row?"true":"false")
            <<"\nmodel.original_rows="<<q.rows().size()<<"\nmodel.native_rows="<<model.lp_.num_row_;
        try {
            if(qp) {
                if(!feasibility_) feasibility_=std::make_unique<Highs>();
                auto& phase=*feasibility_; configure(phase,c,options_,false); Callbacks phase_callbacks(phase,capture);
                auto lp=model.lp_; lp.col_cost_.assign(q.variables().size(),0); lp.offset_=0;
                require(phase.passModel(lp)); raw<<"\nphase.feasibility.time_limit="<<deadline(phase,c); capture.poll(); if(capture.stop) return finish();
                auto api=phase.run(); const auto status=phase.getModelStatus();
                raw<<"\nphase.feasibility.api_status="<<static_cast<int>(api)<<"\nphase.feasibility.model_status="<<static_cast<int>(status);
                if(api!=HighsStatus::kError && phase.getInfo().valid) raw<<"\nphase.feasibility.iterations="<<phase.getInfo().simplex_iteration_count;
                else raw<<"\nphase.feasibility.info=unavailable";
                capture.poll();
                if(api==HighsStatus::kError || status!=HighsModelStatus::kOptimal || capture.stop) {
                    classify(result,api,status);
                    if(api!=HighsStatus::kError) candidate(result,p,c,phase.getSolution(),raw,false);
                    return finish();
                }
                if(!solver_) solver_=std::make_unique<Highs>();
                auto& h=*solver_; configure(h,c,options_,true); Callbacks qp_callbacks(h,capture);
                require(h.passModel(model));
                HighsSolution start=phase.getSolution(); start.dual_valid=false; start.col_dual.clear(); start.row_dual.clear();
                require(h.setSolution(start)); require(h.setBasis(phase.getBasis()));
                bool warm=false; double tolerance=0;
                require(h.getOptionValue("use_warm_start",warm)); require(h.getOptionValue("dual_feasibility_tolerance",tolerance));
                if(!warm || !feasible_start(h,model.lp_,p,tolerance)) {raw<<"\nqp_run=false\nstart.valid=false";return finish();}
                raw<<"\nstart.valid=true\nstart.default_fallback=false";
                raw<<"\nphase.qp.time_limit="<<deadline(h,c); capture.poll(); if(capture.stop) return finish();
                api=h.run(); const auto qp_status=h.getModelStatus();
                raw<<"\nphase.qp.api_status="<<static_cast<int>(api)<<"\nphase.qp.model_status="<<static_cast<int>(qp_status);
                if(api!=HighsStatus::kError && h.getInfo().valid) raw<<"\nphase.qp.iterations="<<h.getInfo().qp_iteration_count;
                else raw<<"\nphase.qp.info=unavailable";
                classify(result,api,qp_status);
                if(api!=HighsStatus::kError) candidate(result,p,c,h.getSolution(),raw,true,private_free_row);
                if(std::holds_alternative<optimization::QuadraticCoefficients>(p.original_objective().coefficients()) &&
                    result.outcome.value==MathematicalOutcome::optimal && !passes(result,c.numerical)) {
                    raw<<"\nphase.qp.attempt1=optimal_but_original_checks_rejected";
                    append_attempt_residuals(raw,"phase.qp.attempt1",result);
                    result=result_for(p);
                    Highs retry; configure(retry,c,options_,true); Callbacks retry_callbacks(retry,capture);
                    require(retry.passModel(model)); require(retry.setOptionValue("use_warm_start",false));
                    bool retry_warm=true; require(retry.getOptionValue("use_warm_start",retry_warm));
                    if(retry_warm) {raw<<"\nphase.qp.retry=false\nretry.error=warm_start_not_disabled"; return finish();}
                    raw<<"\nphase.qp.retry=cold_fresh_model\nphase.qp.retry.time_limit="<<deadline(retry,c);
                    capture.poll(); if(capture.stop) return finish();
                    const auto retry_api=retry.run(); const auto retry_status=retry.getModelStatus();
                    raw<<"\nphase.qp.retry.api_status="<<static_cast<int>(retry_api)<<"\nphase.qp.retry.model_status="<<static_cast<int>(retry_status);
                    classify(result,retry_api,retry_status);
                    if(retry_api!=HighsStatus::kError) candidate(result,p,c,retry.getSolution(),raw,true,private_free_row);
                }
            } else {
                if(!solver_) solver_=std::make_unique<Highs>();
                auto& h=*solver_; configure(h,c,options_,false); Callbacks callbacks(h,capture);
                require(h.passModel(model.lp_)); raw<<"\nphase.linear.time_limit="<<deadline(h,c); capture.poll(); if(capture.stop) return finish();
                const auto api=h.run(); const auto status=h.getModelStatus();
                raw<<"\nphase.linear.api_status="<<static_cast<int>(api)<<"\nphase.linear.model_status="<<static_cast<int>(status);
                if(api!=HighsStatus::kError && h.getInfo().valid) raw<<"\nphase.linear.iterations="<<h.getInfo().simplex_iteration_count;
                else raw<<"\nphase.linear.info=unavailable";
                classify(result,api,status);
                if(api!=HighsStatus::kError) candidate(result,p,c,h.getSolution(),raw,true);
            }
            if(result.outcome.value==MathematicalOutcome::optimal && !passes(result,c.numerical)) {
                result.termination=Termination::numerical_failure; result.outcome.value=MathematicalOutcome::undetermined;
                raw<<"\noptimality.withheld=original-space checks unavailable or failing";
            }
        } catch(const SetupError& e) { feasibility_.reset(); solver_.reset(); raw<<"\nsetup.error="<<e.what(); }
        return finish();
    }
    ProgramOutcome do_solve(const ConvexProgram& p,const ExecutionContext& c) override {
        try {return solve_native(p,c);} catch(...) {feasibility_.reset();solver_.reset();throw;}
    }
public:
    explicit Workspace(HighsConvexOptions options):options_(options) {}
};
}
HighsConvexRegistrationResult make_highs_registration(HighsConvexOptions options) {
    for(auto cap:{options.feasibility_iteration_limit,options.qp_iteration_limit})
        if(cap && *cap>static_cast<std::size_t>(kHighsIInf)) return unsupported("highs.convex.iteration_limit","native integer width exceeded");
    return registry::Registration<registry::ConvexPort>{{{"csl.convex.highs"},version},
        [](const ConvexProgram& p,const registry::Requirements& request) -> registry::Capability {
            if(request.scalar!=registry::Scalar::binary64) return unsupported("scalar","binary64 required");
            if(auto d=admission(p);!d.empty()) return d;
            return registry::Offer{{{"csl.program-result.v1"},Assurance::numerical,{},{},registry::Completeness::unestablished}};
        },[options](const ConvexProgram&) {return std::make_unique<Workspace>(options);}};
}
}
