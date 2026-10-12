#include <csl/adapters/polyhedral/qhull.hpp>
#include <csl/optimization/linear_program.hpp>
#include <csl/sets/data.hpp>
#include "../../geometry/conversion/affine_coordinates.hpp"
#include <Eigen/Core>
#include <Eigen/SVD>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <limits>
#include <memory>
#include <sstream>
#include <qhull_ra.h>

namespace csl::adapters::polyhedral {
namespace {
using Clock = std::chrono::steady_clock;
constexpr const char* version = "1.0.0+qhull.8.0.2";
constexpr const char* verifier = "csl.conversion.qhull.numeric-audit";

Diagnostics diagnostic(DiagnosticCode code, std::string field, std::string explanation) {
    return {{code,std::move(field),std::move(explanation)}};
}
bool stopped(const ExecutionContext& context, StopReason& reason) {
    if (context.cancellation.stop_requested()) { reason=StopReason::cancelled; return true; }
    if (context.deadline && Clock::now()>=*context.deadline) { reason=StopReason::resource_limit; return true; }
    return false;
}
bool valid_policy(NumericalPolicy p) {
    return std::isfinite(p.absolute_tolerance)&&p.absolute_tolerance>=0&&
           std::isfinite(p.relative_tolerance)&&p.relative_tolerance>=0;
}
StopReason stop_for(Termination termination) {
    if (termination==Termination::cancelled) return StopReason::cancelled;
    if (termination==Termination::resource_limit) return StopReason::resource_limit;
    return StopReason::numerical_failure;
}
std::string result_id(const ConversionRequest& r) {
    return "conversion:"+r.identity.request.value+":"+r.identity.ideal_output.value;
}
Eigen::MatrixXd read_matrix(const numeric::MatrixView& v) {
    Eigen::MatrixXd m(static_cast<Eigen::Index>(v.rows()),static_cast<Eigen::Index>(v.cols()));
    for (std::size_t i=0;i<v.rows();++i) for (std::size_t j=0;j<v.cols();++j)
        m(static_cast<Eigen::Index>(i),static_cast<Eigen::Index>(j))=v(i,j);
    return m;
}
Eigen::VectorXd read_vector(const numeric::VectorView& v) {
    Eigen::VectorXd x(static_cast<Eigen::Index>(v.size()));
    for (std::size_t i=0;i<v.size();++i) x[static_cast<Eigen::Index>(i)]=v[i];
    return x;
}
std::optional<numeric::MatrixView> view(const Eigen::MatrixXd& m) {
    Matrix data{static_cast<std::size_t>(m.rows()),static_cast<std::size_t>(m.cols()),{}};
    if (m.size()>static_cast<Eigen::Index>(data.values.max_size())) return {};
    data.values.reserve(static_cast<std::size_t>(m.size()));
    for (Eigen::Index i=0;i<m.rows();++i) for (Eigen::Index j=0;j<m.cols();++j) data.values.push_back(m(i,j));
    auto made=numeric::snapshot(data);
    if (auto* x=std::get_if<numeric::MatrixView>(&made)) return *x;
    return {};
}
std::optional<numeric::VectorView> view(const Eigen::VectorXd& x) {
    Vector data(static_cast<std::size_t>(x.size()));
    for (Eigen::Index i=0;i<x.size();++i) data[static_cast<std::size_t>(i)]=x[i];
    auto made=numeric::snapshot_vector(data);
    if (auto* v=std::get_if<numeric::VectorView>(&made)) return *v;
    return {};
}
std::optional<sets::SetData> make_h(std::string id,const Eigen::MatrixXd& a,const Eigen::VectorXd& b,
                                    const Eigen::MatrixXd& e,const Eigen::VectorXd& f) {
    auto av=view(a); auto bv=view(b); auto ev=view(e); auto fv=view(f);
    if (!av||!bv||!ev||!fv) return {};
    auto result=sets::make_h({{std::move(id)},static_cast<std::size_t>(a.cols()),{}},{*av,*bv,*ev,*fv});
    if (auto* x=std::get_if<sets::SetData>(&result)) return *x;
    return {};
}
std::optional<sets::SetData> make_v(std::string id,const Eigen::MatrixXd& vertices) {
    Eigen::MatrixXd rays(0,vertices.cols()); auto vv=view(vertices); auto rv=view(rays);
    if (!vv||!rv) return {};
    auto result=sets::make_v({{std::move(id)},static_cast<std::size_t>(vertices.cols()),{}},{*vv,*rv});
    if (auto* x=std::get_if<sets::SetData>(&result)) return *x;
    return {};
}
std::optional<sets::SetData> make_empty(std::string id,std::size_t n,bool h) {
    if (!h) return make_v(std::move(id),Eigen::MatrixXd(0,static_cast<Eigen::Index>(n)));
    Eigen::MatrixXd a(1,static_cast<Eigen::Index>(n)); a.setZero(); Eigen::VectorXd b(1); b[0]=-1;
    return make_h(std::move(id),a,b,Eigen::MatrixXd(0,static_cast<Eigen::Index>(n)),Eigen::VectorXd(0));
}

struct NativeQhull {
    qhT qh{}; bool started{}; FILE* out{std::tmpfile()}; FILE* err{std::tmpfile()};
    NativeQhull() { if (!out||!err) throw std::runtime_error("Unable to create private Qhull diagnostic streams."); }
    ~NativeQhull() {
        if (started) { qh_freeqhull(&qh,!qh_ALL); int current{},total{}; qh_memfreeshort(&qh,&current,&total); }
        if (out) std::fclose(out); if (err) std::fclose(err);
    }
};
struct Facets { std::vector<Eigen::VectorXd> normals; std::vector<double> offsets; std::string error; };
Facets hull_facets(const Eigen::MatrixXd& points) {
    Facets result;
    if (points.cols()<2||points.rows()<=points.cols()) { result.error="Qhull needs more than dimension+1 points."; return result; }
    if (points.cols()>std::numeric_limits<int>::max()||points.rows()>std::numeric_limits<int>::max()) {
        result.error="Qhull's signed-int point or dimension limit is exceeded."; return result;
    }
    std::vector<coordT> coordinates;
    if (points.size()>static_cast<Eigen::Index>(coordinates.max_size())) { result.error="Qhull input exceeds host container capacity."; return result; }
    coordinates.reserve(static_cast<std::size_t>(points.size()));
    for (Eigen::Index i=0;i<points.rows();++i) for (Eigen::Index j=0;j<points.cols();++j) {
        if (!std::isfinite(points(i,j))) { result.error="Qhull input contains nonfinite values."; return result; }
        coordinates.push_back(points(i,j));
    }
    NativeQhull native; qh_zero(&native.qh,native.err); native.started=true;
    qhT* qh=&native.qh;
    char options[]="qhull Qx";
    const auto status=qh_new_qhull(&native.qh,static_cast<int>(points.cols()),static_cast<int>(points.rows()),
                                   coordinates.data(),False,options,native.out,native.err);
    if (status!=qh_ERRnone) { result.error="Qhull 8.0.2 Qx returned error code "+std::to_string(status)+"."; return result; }
    facetT* facet{};
    FORALLfacets {
        if (facet->upperdelaunay) continue;
        Eigen::VectorXd normal(points.cols());
        for (Eigen::Index j=0;j<points.cols();++j) normal[j]=facet->normal[j];
        if (!normal.allFinite()||!std::isfinite(facet->offset)) { result.error="Qhull returned a nonfinite facet."; return result; }
        result.normals.push_back(std::move(normal)); result.offsets.push_back(facet->offset);
    }
    if (result.normals.empty()) result.error="Qhull returned no facets.";
    return result;
}

struct LpAnswer { std::optional<ProgramResult> result; std::string error; std::optional<StopReason> stopped; };
class LpRunner {
    const registry::Registration<registry::LPPort>& registration_;
    const ExecutionContext& context_;
    const ConversionRequest& request_;
    std::size_t sequence_{};
public:
    LpRunner(const registry::Registration<registry::LPPort>& r,const ExecutionContext& c,const ConversionRequest& q)
        : registration_(r),context_(c),request_(q) {}
    LpAnswer solve(const Eigen::MatrixXd& a,const Eigen::VectorXd& lower,const Eigen::VectorXd& upper,
                   const Eigen::VectorXd& objective) {
        StopReason stop{};
        if (stopped(context_,stop)) return {{},"Stopped before generated LP query.",stop};
        if (a.rows()!=lower.size()||a.rows()!=upper.size()||a.cols()!=objective.size()) return {{},"Generated LP dimensions disagree.",{}};
        SparseMatrix csr{static_cast<std::size_t>(a.rows()),static_cast<std::size_t>(a.cols()),{0},{},{}};
        for (Eigen::Index i=0;i<a.rows();++i) {
            for (Eigen::Index j=0;j<a.cols();++j) if (a(i,j)!=0) {
                csr.column_indices.push_back(static_cast<std::size_t>(j)); csr.values.push_back(a(i,j));
            }
            csr.row_offsets.push_back(csr.values.size());
        }
        std::vector<Interval> rows(static_cast<std::size_t>(a.rows())), variables(static_cast<std::size_t>(a.cols()));
        for (Eigen::Index i=0;i<a.rows();++i) {
            if (std::isfinite(lower[i])) rows[static_cast<std::size_t>(i)].lower=lower[i];
            if (std::isfinite(upper[i])) rows[static_cast<std::size_t>(i)].upper=upper[i];
        }
        Vector c(static_cast<std::size_t>(objective.size()));
        for (Eigen::Index i=0;i<objective.size();++i) c[static_cast<std::size_t>(i)]=objective[i];
        auto made=optimization::make_linear_program({{request_.identity.problem,{request_.identity.request.value+":qhull-"+std::to_string(sequence_++)}},
            std::move(c),0.0,std::move(csr),std::move(variables),std::move(rows)});
        if (auto* errors=std::get_if<Diagnostics>(&made)) return {{},errors->empty()?"Generated LP construction failed.":errors->front().explanation,{}};
        registry::Registry<registry::LPPort> backends;
        if (auto rejected=backends.add(registration_)) return {{},rejected->diagnostics.front().explanation,{}};
        registry::Requirements required; required.output.representation={"csl.program-result.v1"}; required.output.assurance=Assurance::numerical;
        auto prepared=registry::prepare_pipeline(registry::select(backends,{registration_.identity.id,registration_.identity.version},
            std::get<LinearProgram>(made),required));
        if (auto* rejection=std::get_if<registry::Rejection>(&prepared))
            return {{},rejection->diagnostics.empty()?"Selected LP implementation rejected a generated query.":rejection->diagnostics.front().explanation,{}};
        auto [worker]=std::get<registry::PreparedPipeline<registry::LPPort>>(std::move(prepared)).create();
        auto outcome=worker->run(context_);
        if (stopped(context_,stop)) return {{},"Stop observed after generated LP query.",stop};
        if (auto* rejection=std::get_if<Unsupported>(&outcome)) return {{},rejection->diagnostics.empty()?"LP query unsupported.":rejection->diagnostics.front().explanation,{}};
        return {std::get<ProgramResult>(std::move(outcome)),{}, {}};
    }
};

} // namespace

namespace {
class Workspace final : public RepresentationConverterWorkspace {
    registry::Registration<registry::LPPort> lp_;
    QhullOptions options_;
    ConversionRequest request_;
    std::shared_ptr<const sets::SetData> input_;
    std::string input_error_;
    std::optional<std::size_t> affine_dimension_;

    bool admission(std::size_t dimension,std::size_t rows,std::string& reason) const {
        if (options_.max_ambient_dimension&&dimension>*options_.max_ambient_dimension) {
            reason="Caller-configured ambient-dimension limit exceeded."; return false;
        }
        if (options_.max_input_rows&&rows>*options_.max_input_rows) {
            reason="Caller-configured input-row limit exceeded."; return false;
        }
        if (dimension>static_cast<std::size_t>(std::numeric_limits<int>::max())||
            rows>static_cast<std::size_t>(std::numeric_limits<int>::max())) {
            reason="Qhull's signed-int dimension or input-count limit is exceeded."; return false;
        }
        return true;
    }
    GeometryEvidence evidence(const ExecutionContext& context,double residual,std::vector<std::string> assumptions) const {
        GeometryEvidence e;
        e.reference={request_.identity,{request_.input.id}};
        e.scope=GeometryClaimScope::set_relation;
        e.support=NumericalCheck{context.numerical.absolute_tolerance,context.numerical.relative_tolerance,
                                 residual,{verifier}};
        e.assumptions=std::move(assumptions);
        return e;
    }
    SetTransformOutcome unsupported(std::string field,std::string reason) const {
        return Unsupported{diagnostic(DiagnosticCode::unsupported,std::move(field),std::move(reason))};
    }
    std::optional<sets::SetData> empty_output(bool h) const {
        return make_empty(result_id(request_),request_.input.metadata.dimension,h);
    }
    std::optional<sets::SetData> singleton_output(const Eigen::VectorXd& p,bool h) const {
        if (!h) { Eigen::MatrixXd x(1,p.size()); x.row(0)=p.transpose(); return make_v(result_id(request_),x); }
        Eigen::MatrixXd e(p.size(),p.size()); e.setIdentity();
        return make_h(result_id(request_),Eigen::MatrixXd(0,p.size()),Eigen::VectorXd(0),e,p);
    }
    std::optional<sets::SetData> universal_output(bool h) const {
        const auto n=static_cast<Eigen::Index>(request_.input.metadata.dimension);
        if (!h&&n!=0) return {};
        if (!h) return make_v(result_id(request_),Eigen::MatrixXd(1,0));
        return make_h(result_id(request_),Eigen::MatrixXd(0,n),Eigen::VectorXd(0),Eigen::MatrixXd(0,n),Eigen::VectorXd(0));
    }
    SetTransformOutcome publish(const sets::SetData& set,const ExecutionContext& context,double residual,
                                std::vector<std::string> assumptions) const {
        auto ev=evidence(context,residual,std::move(assumptions));
        auto errors=check_geometry_evidence(ev,request_);
        if (!errors.empty()) return Unsupported{std::move(errors)};
        return OperationResult{set.as_handle(),SetRelation::equivalent,std::move(ev)};
    }

    SetTransformOutcome h_to_v(const sets::HRepresentation& h,const ExecutionContext& context) {
        const auto n=static_cast<Eigen::Index>(request_.input.metadata.dimension);
        const Eigen::MatrixXd a=read_matrix(h.inequalities), e=read_matrix(h.equalities);
        const Eigen::VectorXd b=read_vector(h.upper_bounds), f=read_vector(h.equality_values);
        if (!a.allFinite()||!b.allFinite()||!e.allFinite()||!f.allFinite()) return unsupported("conversion.input","H data must be finite.");
        std::string reason;
        if (!admission(static_cast<std::size_t>(n),static_cast<std::size_t>(a.rows()+e.rows()),reason)) return unsupported("conversion.capacity",reason);
        if (n==0) {
            bool feasible=true;
            for (Eigen::Index i=0;i<b.size();++i) feasible=feasible&&(b[i]>=-context.numerical.absolute_tolerance);
            for (Eigen::Index i=0;i<f.size();++i) feasible=feasible&&(std::abs(f[i])<=context.numerical.absolute_tolerance);
            if (!feasible) return publish(*empty_output(false),context,0,{"zero-dimensional structural feasibility check"});
            return publish(*singleton_output(Eigen::VectorXd(0),false),context,0,{"R^0 contains exactly one empty-coordinate point"});
        }
        Eigen::MatrixXd constraints(a.rows()+e.rows(),n);
        constraints.topRows(a.rows())=a; constraints.bottomRows(e.rows())=e;
        Eigen::VectorXd lower=Eigen::VectorXd::Constant(constraints.rows(),-std::numeric_limits<double>::infinity());
        Eigen::VectorXd upper(constraints.rows()); upper.head(a.rows())=b;
        lower.tail(e.rows())=f; upper.tail(e.rows())=f;
        LpRunner lp(lp_,context,request_);
        auto feasible=lp.solve(constraints,lower,upper,Eigen::VectorXd::Zero(n));
        if (feasible.stopped) return OperationStopped{*feasible.stopped,feasible.error};
        if (!feasible.result) return unsupported("conversion.lp.feasibility",feasible.error);
        if (feasible.result->termination!=Termination::completed) return OperationStopped{stop_for(feasible.result->termination),"Selected LP did not complete the feasibility query."};
        if (feasible.result->outcome.value==MathematicalOutcome::infeasible)
            return publish(*empty_output(false),context,0,{"empty classification uses the selected LP report; outcome support remains unestablished"});
        if (feasible.result->outcome.value!=MathematicalOutcome::optimal||!feasible.result->primal)
            return unsupported("conversion.lp.feasibility","Selected LP did not return an optimal feasibility witness.");
        if (feasible.result->primal->size()!=static_cast<std::size_t>(n))
            return unsupported("conversion.lp.feasibility","Selected LP returned a witness with the wrong dimension.");
        const Eigen::Map<const Eigen::VectorXd> witness(feasible.result->primal->data(),n);
        double residual=0;
        for (Eigen::Index i=0;i<a.rows();++i) residual=std::max(residual,a.row(i).dot(witness)-b[i]);
        for (Eigen::Index i=0;i<e.rows();++i) residual=std::max(residual,std::abs(e.row(i).dot(witness)-f[i]));
        for (Eigen::Index j=0;j<n;++j) for (double sign:{-1.0,1.0}) {
            Eigen::VectorXd objective=Eigen::VectorXd::Zero(n); objective[j]=sign;
            auto bound=lp.solve(constraints,lower,upper,objective);
            if (bound.stopped) return OperationStopped{*bound.stopped,bound.error};
            if (bound.result&&bound.result->termination!=Termination::completed)
                return OperationStopped{stop_for(bound.result->termination),"Selected LP did not complete a boundedness query."};
            if (!bound.result||
                bound.result->outcome.value!=MathematicalOutcome::optimal||!bound.result->primal)
                return unsupported("conversion.lp.boundedness",bound.error.empty()?"All signed coordinate LPs must complete with finite optima.":bound.error);
            if (bound.result->primal->size()!=static_cast<std::size_t>(n))
                return unsupported("conversion.lp.boundedness","Selected LP returned a witness with the wrong dimension.");
            const Eigen::Map<const Eigen::VectorXd> x(bound.result->primal->data(),n);
            for (Eigen::Index i=0;i<a.rows();++i) residual=std::max(residual,a.row(i).dot(x)-b[i]);
            for (Eigen::Index i=0;i<e.rows();++i) residual=std::max(residual,std::abs(e.row(i).dot(x)-f[i]));
        }
        Eigen::VectorXd p=Eigen::VectorXd::Zero(n);
        Eigen::MatrixXd basis=Eigen::MatrixXd::Identity(n,n);
        double rank_tolerance=0;
        if (e.rows()>0) {
            Eigen::JacobiSVD<Eigen::MatrixXd> svd(e,Eigen::ComputeFullU|Eigen::ComputeFullV);
            if (svd.info()!=Eigen::Success) return unsupported("conversion.equalities","Equality rank decomposition failed.");
            rank_tolerance=128*std::numeric_limits<double>::epsilon()*static_cast<double>(std::max(e.rows(),e.cols()))*std::max(1.0,e.cwiseAbs().maxCoeff());
            std::size_t rank=0;
            for (Eigen::Index i=0;i<svd.singularValues().size();++i) {
                const double s=svd.singularValues()[i]; if (s>rank_tolerance) ++rank;
                else if (s>0) return unsupported("conversion.rank","Equality rank is numerically ambiguous; no dimension was discarded.");
            }
            p=svd.solve(f);
            if (!p.allFinite()||(e*p-f).norm()>context.numerical.absolute_tolerance+context.numerical.relative_tolerance*std::max(1.0,f.norm()))
                return unsupported("conversion.equalities","Equalities are inconsistent or unresolved in binary64.");
            basis=svd.matrixV().rightCols(n-static_cast<Eigen::Index>(rank));
        }
        const Eigen::Index r=basis.cols();
        affine_dimension_=static_cast<std::size_t>(r);
        if (r==0) {
            for (Eigen::Index i=0;i<a.rows();++i) if (a.row(i).dot(p)>b[i]+context.numerical.absolute_tolerance)
                return publish(*empty_output(false),context,residual,{"zero-dimensional reduced infeasibility classification"});
            Eigen::MatrixXd vertex(1,n); vertex.row(0)=p.transpose();
            auto set=make_v(result_id(request_),vertex);
            if (!set) return unsupported("conversion.output","Could not construct zero-dimensional V output.");
            return publish(*set,context,std::max(residual,rank_tolerance),{"explicit equality null-space reduction","LP feasibility and boundedness prerequisites","zero-dimensional case; Qhull not used"});
        }
        const Eigen::MatrixXd reduced=a*basis; const Eigen::VectorXd rhs=b-a*p;
        std::vector<Eigen::Index> rows;
        for (Eigen::Index i=0;i<reduced.rows();++i) {
            const double norm=reduced.row(i).norm();
            if (!std::isfinite(norm)||!std::isfinite(rhs[i])) return unsupported("conversion.reduction","Nonfinite reduced inequality.");
            const double row_scale=a.row(i).norm();
            const double reduced_row_tolerance=128*std::numeric_limits<double>::epsilon()*
                static_cast<double>(std::max<Eigen::Index>(n,r))*row_scale;
            if (norm<=reduced_row_tolerance) {
                if (rhs[i]<-context.numerical.absolute_tolerance) return publish(*empty_output(false),context,residual,{"constant inequality proves numerical infeasibility after equality reduction"});
            } else rows.push_back(i);
        }
        Eigen::MatrixXd c(rows.size(),r); Eigen::VectorXd d(rows.size());
        for (std::size_t i=0;i<rows.size();++i) { c.row(i)=reduced.row(rows[i]); d[static_cast<Eigen::Index>(i)]=rhs[rows[i]]; }
        if (r==1) {
            double lo=-std::numeric_limits<double>::infinity(),hi=std::numeric_limits<double>::infinity();
            for (Eigen::Index i=0;i<c.rows();++i) {
                const double coefficient=c(i,0);
                if (coefficient>0) hi=std::min(hi,d[i]/coefficient);
                else if (coefficient<0) lo=std::max(lo,d[i]/coefficient);
                else if (d[i]<-context.numerical.absolute_tolerance)
                    return publish(*empty_output(false),context,residual,{"constant-row reduced infeasibility classification"});
            }
            if (!std::isfinite(lo)||!std::isfinite(hi)||lo>hi)
                return unsupported("conversion.interval","Reduced one-dimensional endpoints were not resolved as finite and ordered.");
            if (hi>lo&&hi-lo<=context.numerical.absolute_tolerance)
                return unsupported("conversion.interval.rank","Nonzero interval width is below the configured numerical resolution.");
            const std::size_t count=hi==lo?1:2;
            Eigen::MatrixXd points(static_cast<Eigen::Index>(count),n);
            points.row(0)=(p+basis.col(0)*lo).transpose();
            if (count==2) points.row(1)=(p+basis.col(0)*hi).transpose();
            for (Eigen::Index k=0;k<points.rows();++k) {
                for (Eigen::Index i=0;i<a.rows();++i) residual=std::max(residual,a.row(i).dot(points.row(k))-b[i]);
                for (Eigen::Index i=0;i<e.rows();++i) residual=std::max(residual,std::abs(e.row(i).dot(points.row(k))-f[i]));
            }
            if (residual>context.numerical.absolute_tolerance+context.numerical.relative_tolerance*std::max(1.0,points.norm()))
                return unsupported("conversion.interval.audit","Reduced interval endpoints fail original-space checks.");
            auto set=make_v(result_id(request_),points);
            if (!set) return unsupported("conversion.output","Could not construct reduced interval V output.");
            return publish(*set,context,residual,{"explicit equality null-space reduction","one-dimensional interval endpoints from reduced inequalities","LP feasibility and coordinate-boundedness prerequisites","numerical evidence only"});
        }
        Eigen::MatrixXd interior(c.rows()+1,r+1); interior.setZero(); interior.topLeftCorner(c.rows(),r)=c;
        for (Eigen::Index i=0;i<c.rows();++i) interior(i,r)=c.row(i).norm();
        Eigen::VectorXd interior_upper(c.rows()+1); interior_upper.head(c.rows())=d; interior_upper[c.rows()]=0;
        Eigen::VectorXd objective=Eigen::VectorXd::Zero(r+1); objective[r]=-1;
        auto center=lp.solve(interior,Eigen::VectorXd::Constant(c.rows()+1,-std::numeric_limits<double>::infinity()),interior_upper,objective);
        if (center.stopped) return OperationStopped{*center.stopped,center.error};
        if (center.result&&center.result->termination!=Termination::completed)
            return OperationStopped{stop_for(center.result->termination),"Selected LP did not complete relative-interior maximization."};
        if (!center.result||center.result->outcome.value!=MathematicalOutcome::optimal||!center.result->primal)
            return unsupported("conversion.relative_interior",center.error.empty()?"Selected LP did not complete relative-interior maximization.":center.error);
        if (center.result->primal->size()!=static_cast<std::size_t>(r+1)) return unsupported("conversion.relative_interior","LP returned a wrong-sized center.");
        const Eigen::Map<const Eigen::VectorXd> center_x(center.result->primal->data(),r+1);
        const double margin=center_x[r];
        if (!std::isfinite(margin)||margin<=context.numerical.absolute_tolerance) return unsupported("conversion.relative_interior","No positive relative-interior margin was numerically resolved.");
        const Eigen::VectorXd zc=center_x.head(r);
        Eigen::MatrixXd polar(c.rows(),r);
        for (Eigen::Index i=0;i<c.rows();++i) {
            const double denominator=d[i]-c.row(i).dot(zc);
            if (!std::isfinite(denominator)||denominator<=0) return unsupported("conversion.polar","A polar denominator is nonpositive or nonfinite.");
            polar.row(i)=c.row(i)/denominator;
        }
        auto facets=hull_facets(polar);
        StopReason stop{}; if (stopped(context,stop)) return OperationStopped{stop,"Stopped after Qhull returned; no converted set is published."};
        if (!facets.error.empty()) return unsupported("conversion.qhull",facets.error);
        std::vector<Eigen::VectorXd> vertices;
        for (std::size_t i=0;i<facets.normals.size();++i) {
            const double beta=facets.offsets[i];
            if (!std::isfinite(beta)||beta>=-std::numeric_limits<double>::epsilon()) return unsupported("conversion.polar","A polar facet cannot produce a finite primal vertex.");
            Eigen::VectorXd x=p+basis*(zc+facets.normals[i]/(-beta));
            if (!x.allFinite()) return unsupported("conversion.vertex","Recovered vertex is nonfinite.");
            for (Eigen::Index j=0;j<a.rows();++j) residual=std::max(residual,a.row(j).dot(x)-b[j]);
            for (Eigen::Index j=0;j<e.rows();++j) residual=std::max(residual,std::abs(e.row(j).dot(x)-f[j]));
            const double allowed=context.numerical.absolute_tolerance+context.numerical.relative_tolerance*std::max(1.0,x.norm());
            if (residual>allowed) return unsupported("conversion.vertex.audit","Recovered vertex fails original H-row/equality residual checks.");
            bool duplicate=false; for (const auto& v:vertices) if ((v-x).norm()<=allowed) { duplicate=true; break; }
            if (!duplicate) vertices.push_back(std::move(x));
        }
        if (vertices.empty()) return unsupported("conversion.vertex","No finite vertices were recovered.");
        Eigen::MatrixXd output(vertices.size(),n);
        for (std::size_t i=0;i<vertices.size();++i) output.row(i)=vertices[i].transpose();
        auto set=make_v(result_id(request_),output);
        if (!set) return unsupported("conversion.output","Could not create the converted V representation.");
        return publish(*set,context,residual,{"boundedness classified by selected LP coordinate objectives","feasibility and relative interior from selected LP; reports are unestablished","Qhull 8.0.2 Qx polar enumeration","binary64 affine reduction and original H residual audits","numerical equivalence claim only; no validated global error bound"});
    }

    SetTransformOutcome v_to_h(const sets::VRepresentation& v,const ExecutionContext& context) {
        const auto n=static_cast<Eigen::Index>(request_.input.metadata.dimension);
        if (v.vertices.rows()==0) return publish(*empty_output(true),context,0,{"conv(V)+cone(R) is empty when V has no rows by the declared set convention"});
        if (v.rays.rows()!=0) return unsupported("conversion.rays","Nonempty ray descriptions are not converted to a bounded H set.");
        const Eigen::MatrixXd vertices=read_matrix(v.vertices);
        std::string reason;
        geometry::conversion::detail::AffineCoordinates coords;
        if (!geometry::conversion::detail::affine_coordinates(vertices,coords,reason)) return unsupported("conversion.affine_rank",reason);
        if (!admission(static_cast<std::size_t>(n),static_cast<std::size_t>(vertices.rows()),reason)) return unsupported("conversion.capacity",reason);
        const Eigen::Index r=static_cast<Eigen::Index>(coords.dimension);
        affine_dimension_=coords.dimension;
        Eigen::MatrixXd a(0,n); Eigen::VectorXd b(0);
        Eigen::MatrixXd e(n-r,n); Eigen::VectorXd f(n-r);
        if (n>r) {
            Eigen::JacobiSVD<Eigen::MatrixXd> svd(coords.basis,Eigen::ComputeFullU);
            e=svd.matrixU().rightCols(n-r).transpose(); f=e*coords.origin;
        }
        double residual=coords.maximum_residual;
        if (r==0) { e=Eigen::MatrixXd::Identity(n,n); f=coords.origin; }
        else if (r==1) {
            const Eigen::VectorXd axis=coords.basis.col(0);
            double lo=std::numeric_limits<double>::infinity(),hi=-lo;
            for (Eigen::Index i=0;i<vertices.rows();++i) { const double z=axis.dot(vertices.row(i).transpose()-coords.origin); lo=std::min(lo,z); hi=std::max(hi,z); }
            if (!(lo<hi)||!std::isfinite(lo)||!std::isfinite(hi)) return unsupported("conversion.rank","Segment width is not numerically resolved.");
            a.resize(2,n); a.row(0)=axis.transpose(); a.row(1)=-axis.transpose();
            b.resize(2); b[0]=axis.dot(coords.origin)+hi; b[1]=-axis.dot(coords.origin)-lo;
        } else {
            Eigen::MatrixXd points(vertices.rows(),r);
            for (Eigen::Index i=0;i<vertices.rows();++i) points.row(i)=(coords.basis.transpose()*(vertices.row(i).transpose()-coords.origin)).transpose();
            auto facets=hull_facets(points);
            StopReason stop{}; if (stopped(context,stop)) return OperationStopped{stop,"Stopped after Qhull returned; no converted set is published."};
            if (!facets.error.empty()) return unsupported("conversion.qhull",facets.error);
            a.resize(facets.normals.size(),n); b.resize(facets.normals.size());
            for (std::size_t i=0;i<facets.normals.size();++i) {
                const Eigen::VectorXd normal=coords.basis*facets.normals[i];
                a.row(i)=normal.transpose(); b[static_cast<Eigen::Index>(i)]=normal.dot(coords.origin)-facets.offsets[i];
            }
        }
        for (Eigen::Index i=0;i<vertices.rows();++i) {
            const Eigen::VectorXd x=vertices.row(i).transpose();
            for (Eigen::Index j=0;j<a.rows();++j) residual=std::max(residual,a.row(j).dot(x)-b[j]);
            for (Eigen::Index j=0;j<e.rows();++j) residual=std::max(residual,std::abs(e.row(j).dot(x)-f[j]));
        }
        const double allowed=context.numerical.absolute_tolerance+context.numerical.relative_tolerance*std::max(1.0,vertices.norm());
        if (!std::isfinite(residual)||residual>allowed) return unsupported("conversion.audit","Input vertices fail output H residual checks.");
        auto set=make_h(result_id(request_),a,b,e,f);
        if (!set) return unsupported("conversion.output","Could not create converted H representation.");
        return publish(*set,context,residual,{"affine rank from binary64 SVD; ambiguous small singular values rejected","Qhull 8.0.2 Qx facet enumeration in affine coordinates","source vertices checked against output H constraints","numerical evidence only; finite samples do not prove global containment"});
    }

    void observe(ConversionObservation& o,const SetTransformOutcome& outcome,Clock::time_point start) const {
        o.elapsed_seconds=std::chrono::duration<double>(Clock::now()-start).count();
        o.affine_dimension=affine_dimension_;
        if (const auto* r=std::get_if<OperationResult>(&outcome)) {
            o.outcome="success"; o.output_representation=r->output.metadata.representation.value;
            if (const auto* check=std::get_if<NumericalCheck>(&r->evidence.support)) o.numerical_check=*check;
            auto data=sets::from_handle(r->output);
            if (auto* set=std::get_if<sets::SetData>(&data)) {
                const auto rep=set->representation();
                if (const auto* h=std::get_if<sets::HRepresentation>(&rep)) { o.output_inequalities=h->inequalities.rows(); o.output_equalities=h->equalities.rows(); }
                if (const auto* v=std::get_if<sets::VRepresentation>(&rep)) { o.output_vertices=v->vertices.rows(); o.output_rays=v->rays.rows(); }
            }
        } else if (const auto* s=std::get_if<OperationStopped>(&outcome)) { o.outcome="stopped"; o.diagnostics=s->diagnostics; }
        else { o.outcome="unsupported"; const auto& ds=std::get<Unsupported>(outcome).diagnostics; if (!ds.empty()) o.diagnostics=ds.front().explanation; }
        if (options_.observe) options_.observe(o);
    }
public:
    Workspace(registry::Registration<registry::LPPort> lp,QhullOptions options,ConversionRequest request)
        : lp_(std::move(lp)),options_(std::move(options)),request_(std::move(request)) {
        auto data=sets::from_handle(request_.input);
        if (auto* set=std::get_if<sets::SetData>(&data)) input_=std::make_shared<const sets::SetData>(*set);
        else input_error_=std::get<Diagnostic>(data).explanation;
    }
    SetTransformOutcome convert(const ConversionRequest& request,const ExecutionContext& context) override {
        const auto start=Clock::now();
        ConversionObservation observation;
        observation.request=request.identity; observation.converter={{"csl.conversion.qhull"},version}; observation.lp_backend=lp_.identity;
        auto finish=[&](SetTransformOutcome result) { observe(observation,result,start); return result; };
        if (!input_) return finish(unsupported("conversion.input",input_error_));
        if (request.identity!=request_.identity||request.input.id!=request_.input.id||request.output.value!=request_.output.value)
            return finish(Unsupported{diagnostic(DiagnosticCode::evidence_mismatch,"conversion.request","Request changed after workspace creation.")});
        if (!valid_policy(context.numerical)) return finish(Unsupported{diagnostic(DiagnosticCode::invalid_input,"conversion.numeric_policy","Tolerances must be finite and nonnegative.")});
        if (request.assurance!=Assurance::numerical) return finish(unsupported("conversion.assurance","Numerical Qhull operations do not support validated assurance."));
        StopReason reason{}; if (stopped(context,reason)) return finish(OperationStopped{reason,"Stopped before conversion."});
        const auto rep=input_->representation();
        affine_dimension_.reset();
        observation.input_representation=request.input.metadata.representation.value;
        if (const auto* h=std::get_if<sets::HRepresentation>(&rep)) { observation.input_inequalities=h->inequalities.rows(); observation.input_equalities=h->equalities.rows(); }
        if (const auto* v=std::get_if<sets::VRepresentation>(&rep)) { observation.input_vertices=v->vertices.rows(); observation.input_rays=v->rays.rows(); }
        const bool want_h=request.output.value=="csl.polyhedron.h";
        if (!want_h&&request.output.value!="csl.polyhedron.v") return finish(unsupported("conversion.output","Only native H and V outputs are supported."));
        if (request.input.metadata.representation.value==request.output.value) {
            const auto metadata=input_->metadata();
            if (metadata->affine_dimension) if (const auto* dim=std::get_if<sets::DimensionValue>(&metadata->affine_dimension->claim.value)) affine_dimension_=dim->value;
            return finish(publish(*input_,context,0,{"same-representation identity transform"}));
        }
        if (std::holds_alternative<sets::EmptyRepresentation>(rep)) return finish(publish(*empty_output(want_h),context,0,{"structural empty representation"}));
        if (std::holds_alternative<sets::UniversalRepresentation>(rep)) {
            affine_dimension_=request.input.metadata.dimension;
            auto set=universal_output(want_h);
            if (!set) return finish(unsupported("conversion.unbounded","R^n for n>0 has no finite V representation."));
            return finish(publish(*set,context,0,{"structural universal representation"}));
        }
        if (const auto* singleton=std::get_if<sets::SingletonRepresentation>(&rep)) {
            affine_dimension_=0;
            auto set=singleton_output(read_vector(singleton->point),want_h);
            if (!set) return finish(unsupported("conversion.singleton","Could not construct singleton output."));
            return finish(publish(*set,context,0,{"structural singleton representation"}));
        }
        SetTransformOutcome result=std::holds_alternative<sets::HRepresentation>(rep)
            ? (want_h ? publish(*input_,context,0,{"same-representation identity transform"}) : h_to_v(std::get<sets::HRepresentation>(rep),context))
            : (want_h ? v_to_h(std::get<sets::VRepresentation>(rep),context) : publish(*input_,context,0,{"same-representation identity transform"}));
        if (stopped(context,reason)) return finish(OperationStopped{reason,"Stopped before publishing conversion output."});
        return finish(std::move(result));
    }
};

registry::Capability check_capability(const ConversionRequest& request,const registry::Requirements& required,
                                      const QhullOptions& options) {
    if (request.assurance!=Assurance::numerical||required.output.assurance!=Assurance::numerical)
        return diagnostic(DiagnosticCode::unsupported,"conversion.assurance","Qhull conversion supports numerical assurance only.");
    if (!required.output.relation||*required.output.relation!=SetRelation::equivalent)
        return diagnostic(DiagnosticCode::unsupported,"conversion.relation","H/V conversion is equivalent-only.");
    if (request.output.value!="csl.polyhedron.h"&&request.output.value!="csl.polyhedron.v")
        return diagnostic(DiagnosticCode::unsupported,"conversion.output","Only csl.polyhedron.h and csl.polyhedron.v are supported.");
    auto data=sets::from_handle(request.input);
    if (const auto* error=std::get_if<Diagnostic>(&data)) return diagnostic(DiagnosticCode::unsupported,error->field,error->explanation);
    std::size_t rows=0;
    const auto rep=std::get<sets::SetData>(data).representation();
    if (const auto* h=std::get_if<sets::HRepresentation>(&rep)) rows=h->inequalities.rows()+h->equalities.rows();
    if (const auto* v=std::get_if<sets::VRepresentation>(&rep)) rows=v->vertices.rows()+v->rays.rows();
    if (options.max_ambient_dimension&&request.input.metadata.dimension>*options.max_ambient_dimension)
        return diagnostic(DiagnosticCode::unsupported,"conversion.capacity","Caller-configured ambient dimension limit exceeded.");
    if (options.max_input_rows&&rows>*options.max_input_rows)
        return diagnostic(DiagnosticCode::unsupported,"conversion.capacity","Caller-configured input-row limit exceeded.");
    if (request.input.metadata.dimension>static_cast<std::size_t>(std::numeric_limits<int>::max())||
        rows>static_cast<std::size_t>(std::numeric_limits<int>::max()))
        return diagnostic(DiagnosticCode::unsupported,"conversion.capacity","Qhull's signed-int dimension or point-count limit is exceeded.");
    return registry::Offer{{request.output,Assurance::numerical,SetRelation::equivalent,{},{}}};
}
} // namespace

QhullRegistrationResult make_qhull_registration(registry::Registration<registry::LPPort> lp,QhullOptions options) {
    if (lp.identity.id.value.empty()||lp.identity.version.empty()||!lp.capabilities||!lp.factory)
        return diagnostic(DiagnosticCode::invalid_input,"conversion.lp_registration","A complete LP registration is required.");
    registry::Registration<registry::ConversionPort> entry;
    entry.identity={{"csl.conversion.qhull"},version};
    entry.capabilities=[options](const ConversionRequest& request,const registry::Requirements& required) {
        return check_capability(request,required,options);
    };
    entry.factory=[lp=std::move(lp),options](const ConversionRequest& request) {
        return std::make_unique<Workspace>(lp,options,request);
    };
    return entry;
}

} // namespace csl::adapters::polyhedral
