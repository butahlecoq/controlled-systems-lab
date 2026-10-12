#include <csl/optimization/phase_one.hpp>
#include <Eigen/LU>
#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>
#include <sstream>

namespace csl::optimization::phase_one {
namespace {
using Matrix = Eigen::MatrixXd;
using Vec = Eigen::VectorXd;
using LU = Eigen::FullPivLU<Matrix>;
using Index = Eigen::Index;
struct Failure { Reason reason; };
void finite(double value) {if(!std::isfinite(value)) throw Failure{Reason::arithmetic};}
Diagnostics error(DiagnosticCode code,const char* field,const char* message) {return {{code,field,message}};}
bool add(std::size_t a,std::size_t b,std::size_t& out) {
    if(b>std::numeric_limits<std::size_t>::max()-a) return false;
    out=a+b;return true;
}
bool multiply(std::size_t a,std::size_t b,std::size_t& out) {
    if(a && b>std::numeric_limits<std::size_t>::max()/a) return false;
    out=a*b;return true;
}
std::optional<std::size_t> estimate(std::size_t m,std::size_t n,const Options& o) {
    std::size_t sum{},mn{},mm{},entries{},doubles{},indices{},bytes{},term{};
    const auto limit=static_cast<std::size_t>(std::numeric_limits<Index>::max());
    const auto permutation_limit=static_cast<std::size_t>(std::numeric_limits<LU::PermutationPType::StorageIndex>::max());
    if(m>permutation_limit || !add(m,n,sum) || sum>limit || !multiply(m,sum,entries) || entries>o.dense_entry_limit ||
       !multiply(m,n,mn) || !multiply(m,m,mm) || mn>limit || mm>limit) return {};
    doubles=mn;
    for(auto [count,width]:{std::pair{mm,std::size_t{8}},std::pair{m,std::size_t{16}},std::pair{n,std::size_t{4}}})
        if(!multiply(count,width,term) || !add(doubles,term,doubles)) return {};
    if(!multiply(m,8,indices) || !multiply(n,2,term) || !add(indices,term,indices) ||
       !multiply(doubles,sizeof(double),bytes) || !multiply(indices,sizeof(std::size_t),term) || !add(bytes,term,bytes)) return {};
    const auto trace=static_cast<std::size_t>(std::min<std::uint64_t>(o.trace_limit,o.pivot_limit));
    if(!multiply(trace,sizeof(PivotEvent),term) || !add(bytes,term,bytes)) return {};
    return bytes;
}
Diagnostics profile(const LinearProgram& p,const Options& o) {
    if(p.offset()!=0) return error(DiagnosticCode::unsupported,"phase_one.objective","Only zero objective and offset are supported");
    for(double v:p.objective().values()) if(v!=0) return error(DiagnosticCode::unsupported,"phase_one.objective","Only zero objective is supported");
    for(const auto& v:p.variables()) if(!v.lower || *v.lower!=0 || v.upper)
        return error(DiagnosticCode::unsupported,"phase_one.variables","Variables must have exactly [0,+infinity) bounds");
    for(const auto& r:p.rows()) if(!r.lower || !r.upper || *r.lower!=*r.upper)
        return error(DiagnosticCode::unsupported,"phase_one.rows","Only equality rows are supported");
    if(!estimate(p.rows().size(),p.variables().size(),o))
        return error(DiagnosticCode::unsupported,"phase_one.capacity","Dense profile or checked arithmetic extent exceeded");
    return {};
}
struct Frame {
    Matrix b;
    LU lu;
    Vec z;
    bool identity{false};
};
struct State {
    Matrix n;
    Vec q;
    Frame frame;
    std::vector<std::size_t> basis;
    std::optional<PivotEvent> last;
    bool basis_valid{false};
};
struct Candidate {Vector x;AuxiliaryState auxiliary;PrimalResiduals residuals;bool feasible;};
class Worker final : public LPWorkspace {
    Options options_;
    std::optional<Snapshot> report_;
    std::unique_ptr<State> state_;
    NumericalPolicy policy_{};
    double eta_{};
    std::size_t m_{},n_{};
    static constexpr Verifier verifier() {return {{"phase-one-bland.original-residual"},"1"};}
    void poll(const ExecutionContext& c) const {
        if(c.cancellation.stop_requested()) throw Failure{Reason::cancelled};
        if(c.deadline && std::chrono::steady_clock::now()>=*c.deadline) throw Failure{Reason::deadline};
    }
    double threshold(double scale) const {
        finite(scale);const double t=policy_.absolute_tolerance+policy_.relative_tolerance*scale;finite(t);return t;
    }
    bool passes(ResidualMeasure r) const {return r.violation<=threshold(r.scale);}
    ResidualMeasure residual(const Matrix& a,const Vec& x,const Vec& rhs,bool transpose=false) const {
        ResidualMeasure r{0,1};
        for(Index i=0;i<rhs.size();++i) {
            double v=0;
            for(Index j=0;j<x.size();++j) {const double product=(transpose?a(j,i):a(i,j))*x[j];finite(product);v+=product;finite(v);}
            const double difference=v-rhs[i];finite(difference);
            r.violation=std::max(r.violation,std::abs(difference));r.scale=std::max({r.scale,std::abs(v),std::abs(rhs[i])});
        }
        return r;
    }
    void factor(Frame& frame,const ExecutionContext& c) {
        poll(c);++report_->factorizations;frame.lu.compute(frame.b);poll(c);
        frame.lu.setThreshold(eta_);
        const double condition=frame.lu.rcond();finite(condition);
        if(frame.lu.rank()!=static_cast<Index>(m_) || condition<=eta_) throw Failure{Reason::ill_conditioned_basis};
        poll(c);frame.z=frame.lu.solve(state_->q);poll(c);
        if(!frame.z.allFinite()) throw Failure{Reason::arithmetic};
        if(!passes(residual(frame.b,frame.z,state_->q))) throw Failure{Reason::invalid_basic_point};
    }
    Candidate candidate(const LinearProgram& p,const Frame& f,
                        std::optional<std::pair<std::size_t,std::size_t>> replacement={}) const {
        Candidate result{Vector(n_,0),{Vector(m_,0),0,{0,1},{0,1},{},{}},
            {{p.identity(),verifier(),policy_.absolute_tolerance,policy_.relative_tolerance},{0,1},{0,1}},false};
        double scale=1;
        for(Index i=0;i<f.z.size();++i) {finite(f.z[i]);scale=std::max(scale,std::abs(f.z[i]));}
        const double tolerance=threshold(scale);
        for(std::size_t i=0;i<m_;++i) {
            const double raw=f.z[static_cast<Index>(i)];
            result.auxiliary.nonnegativity.violation=std::max(result.auxiliary.nonnegativity.violation,-raw);
            if(raw < -tolerance) throw Failure{Reason::invalid_basic_point};
            const double v=std::max(0.0,raw);
            const auto id=replacement && replacement->first==i?replacement->second:state_->basis[i];
            if(id<n_) result.x[id]=v;else result.auxiliary.artificial[id-n_]=v;
        }
        result.auxiliary.nonnegativity.scale=scale;
        for(std::size_t i=0;i<m_;++i) {
            double activity=result.auxiliary.artificial[i];
            for(std::size_t j=0;j<n_;++j) {const double product=state_->n(static_cast<Index>(i),static_cast<Index>(j))*result.x[j];finite(product);activity+=product;finite(activity);}
            const double q=state_->q[static_cast<Index>(i)];const double difference=activity-q;finite(difference);
            const ResidualMeasure row{std::abs(difference),std::max({1.,std::abs(activity),q})};
            if(!passes(row)) throw Failure{Reason::invalid_basic_point};
            result.auxiliary.equations.violation=std::max(result.auxiliary.equations.violation,row.violation);
            result.auxiliary.equations.scale=std::max(result.auxiliary.equations.scale,row.scale);
            result.auxiliary.value+=result.auxiliary.artificial[i];finite(result.auxiliary.value);
        }
        auto check=evaluate_primal(p,result.x,policy_,verifier());
        if(!std::holds_alternative<PrimalEvaluation>(check)) throw Failure{Reason::arithmetic};
        result.residuals=std::get<PrimalEvaluation>(check).residuals;
        result.feasible=passes(result.residuals.rows) && passes(result.residuals.variables);
        const auto csr=std::get<numeric::CsrInput>(p.constraints().descriptor());
        for(std::size_t i=0;i<m_;++i) {
            double v=0;
            for(auto k=csr.row_offsets[i];k<csr.row_offsets[i+1];++k) {const double product=csr.values[k]*result.x[csr.column_indices[k]];finite(product);v+=product;finite(v);}
            const double b=*p.rows()[i].lower,difference=v-b;finite(difference);
            if(!passes({std::abs(difference),std::max({1.,std::abs(v),std::abs(b)})})) result.feasible=false;
        }
        return result;
    }
    Vec column(std::size_t j) const {
        if(j<n_) return state_->n.col(static_cast<Index>(j));
        Vec a=Vec::Zero(static_cast<Index>(m_));a[static_cast<Index>(j-n_)]=1;return a;
    }
    Variable variable(std::size_t j) const {
        if(j<n_) return StructuralVariable{j};
        return ArtificialVariable{j-n_};
    }
    BasisColumn basis_column(std::size_t j) const {
        if(j<n_) return StructuralColumn{j};
        Vector v(m_,0);v[j-n_]=report_->normalization->signs[j-n_];return AuxiliaryColumn{j-n_,std::move(v)};
    }
    std::vector<BasisColumn> basis_columns(const std::vector<std::size_t>& ids) const {
        std::vector<BasisColumn> result;result.reserve(ids.size());for(auto j:ids) result.push_back(basis_column(j));return result;
    }
    std::size_t index(const Variable& v) const {
        if(const auto* j=std::get_if<StructuralVariable>(&v)) return j->column;
        return n_+std::get<ArtificialVariable>(v).row;
    }
    bool current() const {
        return report_ && last_attempt() && last_attempt()->state==SolveAttemptState::returned_result && report_->solve==last_attempt()->stamp;
    }
    BasisUnavailable unavailable() const {
        return {last_attempt()?BasisUnavailableReason::unavailable_result:BasisUnavailableReason::not_solved,"No current verified phase-I basis"};
    }
public:
    explicit Worker(Options options):options_(std::move(options)) {}
    SnapshotResult report() const {if(!current()) return unavailable();return *report_;}
    BasisSnapshotResult basis() const {
        if(!current() || !state_ || !state_->basis_valid) return unavailable();
        const BasisReference reference{report_->solve,report_->pivots};
        BasisSnapshot result{reference,basis_columns(state_->basis),{}};
        if(state_->last) {
            const auto& p=*state_->last;
            // Reconstruct the owning historical value only when requested; the
            // worker retains one index vector plus the compact committed event.
            auto before=basis_columns(state_->basis);
            before[p.leaving_position]=basis_column(index(p.leaving));
            result.last_pivot=PivotRecord{{report_->solve,report_->pivots-1},reference,std::move(before),
                basis_column(index(p.entering)),basis_column(index(p.leaving)),p.leaving_position,p.coefficient};
        }
        return result;
    }
    BasisCoordinatesResult coordinates(const BasisReference& reference,std::span<const double> rhs) const {
        if(!current() || !state_ || !state_->basis_valid) return unavailable();
        if(reference!=BasisReference{report_->solve,report_->pivots}) return BasisUnavailable{BasisUnavailableReason::stale_reference,"Different basis or solve attempt"};
        if(rhs.size()!=m_ || std::any_of(rhs.begin(),rhs.end(),[](double v){return !std::isfinite(v);}))
            return error(DiagnosticCode::invalid_input,"phase_one.basis.rhs","Expected finite original-row vector");
        try {
            Vec normalized(static_cast<Index>(m_));
            for(std::size_t i=0;i<m_;++i) normalized[static_cast<Index>(i)]=rhs[i]*report_->normalization->signs[i];
            Vec x=state_->frame.identity?normalized:Vec(state_->frame.lu.solve(normalized));
            if(!x.allFinite() || !passes(residual(state_->frame.b,x,normalized)))
                return BasisUnavailable{BasisUnavailableReason::unavailable_result,"Basis coordinate residual failed"};
            Vector output(m_);for(std::size_t i=0;i<m_;++i) output[i]=x[static_cast<Index>(i)];
            // Multiplication by D preserves absolute residuals and scales in original rows.
            return BasisCoordinates{reference,std::move(output)};
        } catch(const Failure&) {return BasisUnavailable{BasisUnavailableReason::unavailable_result,"Nonfinite coordinate arithmetic"};}
    }
protected:
    ProgramOutcome do_solve(const LinearProgram& p,const ExecutionContext& c) override;
};
class View final : public DiagnosticsView {
    const Worker& worker_;
public:
    explicit View(const Worker& worker):worker_(worker) {}
    BasisCapabilities capabilities() const override {return {true,true,true};}
    SnapshotResult phase_one_snapshot() const override {return worker_.report();}
    BasisSnapshotResult snapshot() const override {return worker_.basis();}
    BasisCoordinatesResult coordinates(const BasisReference& ref,std::span<const double> rhs) const override {return worker_.coordinates(ref,rhs);}
};
ProgramOutcome Worker::do_solve(const LinearProgram& p,const ExecutionContext& c) {
    report_.reset();state_.reset();m_=p.rows().size();n_=p.variables().size();policy_=c.numerical;
    report_.emplace(Snapshot{last_attempt()->stamp,Termination::numerical_failure,Reason::arithmetic,0,0,0,0,{},{},{},false,0});
    ProgramResult answer{Termination::numerical_failure,{p.identity(),MathematicalOutcome::undetermined,Unestablished{},{}},{},{},{},{}};
    auto finish=[&](Reason reason)->ProgramOutcome {
        if(c.cancellation.stop_requested()) reason=Reason::cancelled;
        else if(c.deadline && std::chrono::steady_clock::now()>=*c.deadline) reason=Reason::deadline;
        Termination termination=Termination::numerical_failure;
        if(reason==Reason::feasible || reason==Reason::positive_auxiliary_optimum) termination=Termination::completed;
        else if(reason==Reason::cancelled) termination=Termination::cancelled;
        else if(reason==Reason::deadline || reason==Reason::pivot_limit || reason==Reason::capacity) termination=Termination::resource_limit;
        report_->termination=termination;report_->reason=reason;answer.termination=termination;
        answer.outcome.value=reason==Reason::feasible?MathematicalOutcome::optimal:
            (reason==Reason::positive_auxiliary_optimum?MathematicalOutcome::infeasible:MathematicalOutcome::undetermined);
        std::ostringstream log;
        log<<"module=phase-one-bland\nversion=1\nauxiliary=sum-artificial/v1\nactual_threads=1\nreason="<<static_cast<int>(reason)
           <<"\npivots="<<report_->pivots<<"\ndegenerate_pivots="<<report_->degenerate_pivots<<"\nfactorizations="<<report_->factorizations
           <<"\npricing_passes="<<report_->pricing_passes<<"\npivot_limit="<<options_.pivot_limit<<"\ndense_entry_limit="<<options_.dense_entry_limit
           <<"\ntrace_limit="<<options_.trace_limit<<"\npivot_relative_tolerance="<<options_.pivot_relative_tolerance
           <<"\nabsolute_tolerance="<<policy_.absolute_tolerance<<"\nrelative_tolerance="<<policy_.relative_tolerance
           <<"\naccounted_workspace_bytes="<<report_->accounted_workspace_bytes<<"\ncertificates=unavailable\nbounds=unavailable";
        if(report_->auxiliary) log<<"\nauxiliary_value="<<report_->auxiliary->value;
        answer.raw_diagnostics=log.str();return answer;
    };
    try {
        poll(c);
        if(!std::isfinite(policy_.absolute_tolerance) || policy_.absolute_tolerance<0 ||
           !std::isfinite(policy_.relative_tolerance) || policy_.relative_tolerance<0)
            return Unsupported{error(DiagnosticCode::invalid_input,"numerical","Finite nonnegative tolerances required")};
        if(c.resources) {auto e=check_resources(*c.resources);if(!e.empty()) return Unsupported{std::move(e)};}
        if(auto e=profile(p,options_);!e.empty()) return Unsupported{std::move(e)};
        const auto bytes=estimate(m_,n_,options_);
        if(!bytes) throw Failure{Reason::capacity};
        report_->accounted_workspace_bytes=*bytes;
        if(c.resources && c.resources->memory_bytes && *bytes>*c.resources->memory_bytes) throw Failure{Reason::capacity};
        eta_=std::max(options_.pivot_relative_tolerance,64*std::numeric_limits<double>::epsilon()*static_cast<double>(std::max<std::size_t>(1,m_)));
        if(eta_>=1) throw Failure{Reason::ill_conditioned_basis};
        poll(c);
        report_->normalization=Normalization{std::vector<int>(m_,1)};
        report_->trace.reserve(static_cast<std::size_t>(std::min<std::uint64_t>(options_.trace_limit,options_.pivot_limit)));
        state_=std::make_unique<State>();auto& s=*state_;
        s.n=Matrix::Zero(static_cast<Index>(m_),static_cast<Index>(n_));s.q.resize(static_cast<Index>(m_));
        const auto csr=std::get<numeric::CsrInput>(p.constraints().descriptor());
        double qsum=0;
        for(std::size_t i=0;i<m_;++i) {
            if(i%64==0) poll(c);
            const int sign=*p.rows()[i].lower<0?-1:1;report_->normalization->signs[i]=sign;
            s.q[static_cast<Index>(i)]=std::abs(*p.rows()[i].lower);qsum+=s.q[static_cast<Index>(i)];finite(qsum);
            for(auto k=csr.row_offsets[i];k<csr.row_offsets[i+1];++k)
                s.n(static_cast<Index>(i),static_cast<Index>(csr.column_indices[k]))=sign*csr.values[k];
        }
        const double zero_threshold=threshold(std::max(1.,qsum));
        s.basis.resize(m_);std::iota(s.basis.begin(),s.basis.end(),n_);
        s.frame.b=Matrix::Identity(static_cast<Index>(m_),static_cast<Index>(m_));s.frame.z=s.q;s.frame.identity=true;
        auto initial=candidate(p,s.frame);bool original_feasible=initial.feasible;
        answer.primal=std::move(initial.x);answer.residuals.primal=std::move(initial.residuals);report_->auxiliary=std::move(initial.auxiliary);
        s.basis_valid=true;poll(c);
        for(;;) {
            poll(c);
            if(report_->auxiliary->value<=zero_threshold) {
                if(!original_feasible) throw Failure{Reason::invalid_basic_point};
                return finish(Reason::feasible);
            }
            Vec costs(static_cast<Index>(m_));
            for(std::size_t i=0;i<m_;++i) costs[static_cast<Index>(i)]=s.basis[i]<n_?0:1;
            poll(c);Vec y=s.frame.identity?costs:Vec(s.frame.lu.transpose().solve(costs));poll(c);
            if(!y.allFinite()) throw Failure{Reason::arithmetic};
            const auto dual=residual(s.frame.b,y,costs,true);
            if(!passes(dual)) throw Failure{Reason::ill_conditioned_basis};
            report_->auxiliary->dual_equations=dual;
            if(report_->pricing_passes==std::numeric_limits<std::uint64_t>::max()) throw Failure{Reason::capacity};
            ++report_->pricing_passes;
            std::optional<std::size_t> entering;std::optional<double> minimum;bool negative=false;
            for(std::size_t j=0;j<n_+m_;++j) {
                if(j%64==0) poll(c);
                if(std::find(s.basis.begin(),s.basis.end(),j)!=s.basis.end()) continue;
                double sum=0,scale=0;
                if(j<n_) for(std::size_t i=0;i<m_;++i) {
                    const double product=s.n(static_cast<Index>(i),static_cast<Index>(j))*y[static_cast<Index>(i)];finite(product);
                    sum+=product;scale+=std::abs(product);finite(sum);finite(scale);
                }
                else {sum=y[static_cast<Index>(j-n_)];scale=std::abs(sum);}
                const double cost=j<n_?0:1,price=cost-sum;finite(price);
                if(!minimum || price<*minimum) minimum=price;
                if(price<0) negative=true;
                if(!entering && price < -threshold(std::max({1.,cost,scale}))) entering=j;
            }
            report_->auxiliary->minimum_reduced_cost=minimum;poll(c);
            if(!entering) {
                if(negative) throw Failure{Reason::uncertain_pricing};
                return finish(Reason::positive_auxiliary_optimum);
            }
            if(report_->pivots==options_.pivot_limit) throw Failure{Reason::pivot_limit};
            Vec a=column(*entering);poll(c);
            Vec direction=s.frame.identity?a:Vec(s.frame.lu.solve(a));poll(c);
            if(!direction.allFinite()) throw Failure{Reason::arithmetic};
            if(!passes(residual(s.frame.b,direction,a))) throw Failure{Reason::uncertain_pivot};
            double direction_scale=1;for(Index i=0;i<direction.size();++i) direction_scale=std::max(direction_scale,std::abs(direction[i]));
            const double guard=eta_*direction_scale;finite(guard);
            std::optional<std::size_t> leaving;double step=0;
            for(std::size_t i=0;i<m_;++i) {
                const double d=direction[static_cast<Index>(i)];
                if(d<=0) continue;
                if(d<=guard) throw Failure{Reason::uncertain_pivot};
                const double ratio=std::max(0.,s.frame.z[static_cast<Index>(i)])/d;finite(ratio);
                if(!leaving || ratio<step || (ratio==step && s.basis[i]<s.basis[*leaving])) {leaving=i;step=ratio;}
            }
            if(!leaving) throw Failure{Reason::uncertain_pivot};
            const std::size_t slot=*leaving;
            Frame proposed;proposed.b=s.frame.b;proposed.b.col(static_cast<Index>(slot))=a;
            factor(proposed,c);auto checked=candidate(p,proposed,std::pair{slot,*entering});poll(c);
            const PivotEvent event{report_->pivots+1,variable(*entering),variable(s.basis[slot]),slot,
                direction[static_cast<Index>(slot)],step,report_->auxiliary->value,checked.auxiliary.value};
            s.basis[slot]=*entering;s.frame=std::move(proposed);s.last=event;
            ++report_->pivots;if(step==0) ++report_->degenerate_pivots;
            original_feasible=checked.feasible;answer.primal=std::move(checked.x);answer.residuals.primal=std::move(checked.residuals);
            report_->auxiliary=std::move(checked.auxiliary);
            if(report_->trace.size()<options_.trace_limit) report_->trace.push_back(event);else report_->trace_truncated=true;
            if(options_.pivot_observer) options_.pivot_observer(event);
            poll(c);
        }
    } catch(const Failure& f) {
        if(state_ && (f.reason==Reason::ill_conditioned_basis || f.reason==Reason::invalid_basic_point)) state_->basis_valid=false;
        return finish(f.reason);
    }
}
} // namespace
RegistrationResult make_registration(Options options) {
    if(!std::isfinite(options.pivot_relative_tolerance) || options.pivot_relative_tolerance<0 || options.pivot_relative_tolerance>=1)
        return error(DiagnosticCode::invalid_input,"phase_one.options.pivot_relative_tolerance","Expected finite value in [0,1)");
    return registry::Registration<registry::LPPort>{{{"phase-one-bland"},"1"},
        [options](const LinearProgram& p,const registry::Requirements& r)->registry::Capability {
            if(r.scalar!=registry::Scalar::binary64 || r.output.assurance!=Assurance::numerical)
                return error(DiagnosticCode::unsupported,"phase_one.arithmetic","Only numerical binary64 is supported");
            if(auto e=profile(p,options);!e.empty()) return e;
            return registry::Offer{{{"csl.program-result.v1"},Assurance::numerical,{},{},{}}};
        },
        [options](const LinearProgram&){return std::make_unique<Worker>(options);},
        [](const LinearProgram&,LPWorkspace& worker)->std::unique_ptr<BasisDiagnostics> {
            return std::make_unique<View>(dynamic_cast<Worker&>(worker));
        }};
}
} // namespace csl::optimization::phase_one
