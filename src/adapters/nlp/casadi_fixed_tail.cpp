#include <csl/adapters/nlp/casadi_fixed_tail.hpp>
#include <casadi/casadi.hpp>

#include <algorithm>
#include <cmath>
#include <sstream>

namespace csl::adapters::nlp {
namespace {
using namespace reachability;
using casadi::MX;
using casadi::DM;
DM dense(const Matrix& A) {
    DM out=DM::zeros(static_cast<casadi_int>(A.rows),static_cast<casadi_int>(A.cols));
    for(std::size_t i=0;i<A.rows;++i)for(std::size_t j=0;j<A.cols;++j)out(static_cast<casadi_int>(i),static_cast<casadi_int>(j))=A.values[i*A.cols+j];
    return DM::sparsify(out);
}
Vector values(const DM& x) {return static_cast<Vector>(x);}
void subject(casadi::Opti& opti,const MX& expression,bool equality=false) {
    for(casadi_int i=0;i<expression.numel();++i) {
        const auto row=expression(i);
        if(MX::symvar(row).empty()) {
            const double value=static_cast<double>(MX::evalf(row));
            if(!std::isfinite(value) || (equality?value!=0:value>0))throw std::runtime_error("constant native recovered row is infeasible");
            continue;
        }
        opti.subject_to(equality?row==0:row<=0);
    }
}
void constrain(casadi::Opti& opti,const MX& x,const FixedTailHRows& h) {
    if(h.inequalities.rows)subject(opti,MX::mtimes(dense(h.inequalities),x)-DM(h.upper_bounds));
    if(h.equalities.rows)subject(opti,MX::mtimes(dense(h.equalities),x)-DM(h.equality_values),true);
}
class NativeWorkspace final:public FixedTailOptimizerWorkspace {
public:
    FixedTailSolveOutcome solve(const FixedTailSolveRequest& request,const ExecutionContext& context) override {
        if(context.cancellation.stop_requested())return OperationStopped{StopReason::cancelled,"Native fixed-tail NLP cancelled before solve"};
        if(context.deadline && std::chrono::steady_clock::now()>=*context.deadline)return OperationStopped{StopReason::deadline_expired,"Native fixed-tail NLP deadline expired"};
        try {
            const auto primary_size=request.initial_primary.size();
            const auto full_size=request.lift.offset.size();
            casadi::Opti opti;
            auto raw=opti.variable(static_cast<casadi_int>(primary_size));
            std::vector<MX> coordinates;Vector initial_raw=request.initial_primary;
            for(std::size_t i=0;i<primary_size;++i) {
                const bool positive=request.feasibility_only && std::find(request.strictly_positive_history_coordinates.begin(),request.strictly_positive_history_coordinates.end(),i)!=request.strictly_positive_history_coordinates.end();
                if(positive) {
                    if(initial_raw[i]<=0)throw std::runtime_error("strict positive initial coordinate is not positive");
                    initial_raw[i]=std::log(initial_raw[i]);coordinates.push_back(MX::exp(raw(static_cast<casadi_int>(i))));
                } else coordinates.push_back(raw(static_cast<casadi_int>(i)));
            }
            const auto primary=MX::vertcat(coordinates);
            const auto z=MX::mtimes(dense(request.lift.map),primary)+DM(request.lift.offset);
            opti.set_initial(raw,DM(initial_raw));
            constrain(opti,z,request.domain);
            std::vector<std::optional<MX>> factors;
            const auto n=request.source_cost.coordinates.dimensions.state;
            for(const auto& region:request.regions) {
                if(region.stage.value==0) {factors.push_back({});continue;}
                const auto first=static_cast<casadi_int>(region.stage.value*n);
                const auto x=z(casadi::Slice(first,first+static_cast<casadi_int>(n)));
                if(region.family==FixedTailFamily::polytope) {
                    constrain(opti,x,region.reference);factors.push_back({});
                } else {
                    const auto& set=*region.inner;
                    if(set.factor.cols==0 || set.point) {
                        subject(opti,x-DM(set.center));
                        subject(opti,DM(set.center)-x);factors.push_back({});
                    } else {
                        auto f=opti.variable(static_cast<casadi_int>(set.factor.cols));
                        subject(opti,x-DM(set.center)-MX::mtimes(dense(set.factor),f),true);
                        if(set.norm==InnerTemplateNorm::euclidean_ball)opti.subject_to(MX::dot(f,f)<=1);
                        else opti.subject_to(opti.bounded(-1,f,1));
                        opti.set_initial(f,DM::zeros(static_cast<casadi_int>(set.factor.cols)));
                        factors.push_back(f);
                    }
                }
            }
            MX cost=0;
            if(!request.feasibility_only) {
                const auto& q=request.source_cost.quadratic;
                cost=0.5*MX::mtimes(std::vector<MX>{z.T(),dense(q.Q),z})+MX::dot(DM(q.linear),z)+q.offset;
                const auto full_initial=values(opti.debug().value(z,opti.initial()));
                for(const auto& norm:request.source_cost.residual_norms) {
                    auto M=norm.map;auto target=norm.target;
                    for(std::size_t i=0;i<M.rows;++i) {
                        const auto w=std::sqrt(norm.weights[i]);target[i]*=w;
                        for(std::size_t j=0;j<M.cols;++j)M.values[i*M.cols+j]*=w;
                    }
                    const auto residual=MX::mtimes(dense(M),z)-DM(target);
                    auto epigraph=opti.variable();opti.subject_to(epigraph>=0);opti.subject_to(MX::dot(residual,residual)<=epigraph*epigraph);
                    double square=0;
                    for(std::size_t i=0;i<M.rows;++i) {
                        double r=-target[i];for(std::size_t j=0;j<full_size;++j)r+=M.values[i*full_size+j]*full_initial[j];square+=r*r;
                    }
                    opti.set_initial(epigraph,std::sqrt(square)+0.01);cost+=norm.coefficient*epigraph;
                }
            }
            opti.minimize(cost);
            const auto dual_count=opti.g().numel();
            opti.set_initial(opti.lam_g(),DM::zeros(dual_count));
            const auto initial_readback=values(opti.debug().value(primary,opti.initial()));
            const auto dual_readback=values(opti.debug().value(opti.lam_g(),opti.initial()));
            casadi::Dict options{{"sb","yes"},{"print_level",0},{"max_iter",6000},{"tol",1e-11},{"acceptable_tol",1e-10},
                {"bound_relax_factor",0.0},{"warm_start_init_point","yes"}};
            if(context.deadline)options["max_wall_time"]=std::max(0.001,std::chrono::duration<double>(*context.deadline-std::chrono::steady_clock::now()).count());
            opti.solver("ipopt",{{"print_time",false}},options);
            const auto solution=opti.solve();
            if(context.cancellation.stop_requested())return OperationStopped{StopReason::cancelled,"Native fixed-tail NLP cancelled during solve"};
            if(context.deadline && std::chrono::steady_clock::now()>=*context.deadline)return OperationStopped{StopReason::deadline_expired,"Native fixed-tail NLP deadline reached"};
            std::vector<Vector> witnesses;
            for(const auto& f:factors)witnesses.push_back(f?values(solution.value(*f)):Vector{});
            std::ostringstream diagnostics;
            diagnostics<<"native C++ CasADi "<<casadi::CasadiMeta::version()<<"; IPOPT; "<<opti.stats().at("return_status").to_string()
                <<"; primary variables "<<primary_size<<"; total variables "<<opti.nx()<<"; supplied duals zero; local numerical";
            return FixedTailSolveResult{values(solution.value(primary)),values(solution.value(z)),static_cast<double>(solution.value(cost)),
                request.initial_primary,dual_readback,initial_readback,std::move(witnesses),diagnostics.str()};
        }catch(const std::exception& e) {return Diagnostic{DiagnosticCode::unsupported,"fixed_tail.casadi_ipopt",e.what()};}
    }
};
}
registry::Registration<registry::FixedTailOptimizerPort> make_casadi_fixed_tail_registration() {
    return {{{"csl.nlp.casadi-ipopt.fixed-tail"},"1"},
        [](const FixedTailSolveRequest& request,const registry::Requirements&)->registry::Capability {
            auto diagnostics=check_fixed_tail_solve_request(request);
            if(!diagnostics.empty())return diagnostics;
            return registry::Offer{{{"csl.fixed-tail-solve.v1"},Assurance::numerical,{},{},{}}};
        },
        [](const FixedTailSolveRequest&)->std::unique_ptr<FixedTailOptimizerWorkspace> {return std::make_unique<NativeWorkspace>();}};
}
} // namespace csl::adapters::nlp
