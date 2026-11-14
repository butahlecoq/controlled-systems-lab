#include <csl/adapters/nlp/casadi_history_optimizer.hpp>
#include <casadi/casadi.hpp>

#include <algorithm>
#include <cmath>
#include <limits>

namespace csl::adapters::nlp {
namespace {
using casadi::DM;
using casadi::MX;

DM dense(const Matrix& matrix) {
    DM out=DM::zeros(static_cast<casadi_int>(matrix.rows),static_cast<casadi_int>(matrix.cols));
    for(std::size_t i=0;i<matrix.rows;++i)
        for(std::size_t j=0;j<matrix.cols;++j)
            out(static_cast<casadi_int>(i),static_cast<casadi_int>(j))=matrix.values[i*matrix.cols+j];
    return DM::sparsify(out);
}
DM dense(const numeric::MatrixView& matrix) {
    DM out=DM::zeros(static_cast<casadi_int>(matrix.rows()),static_cast<casadi_int>(matrix.cols()));
    for(std::size_t i=0;i<matrix.rows();++i)
        for(std::size_t j=0;j<matrix.cols();++j)
            out(static_cast<casadi_int>(i),static_cast<casadi_int>(j))=matrix(i,j);
    return DM::sparsify(out);
}
bool fits_casadi_dimension(std::size_t dimension) {
    return dimension<=static_cast<std::size_t>(std::numeric_limits<casadi_int>::max());
}
bool fits_casadi_request(const optimization::HistoryOptimizationRequest& request) {
    if(!fits_casadi_dimension(request.initial_history.size()))return false;
    const auto representation=request.feasible_histories.relation.representation();
    if(const auto* h=std::get_if<sets::HRepresentation>(&representation))
        if(!fits_casadi_dimension(h->inequalities.rows())||!fits_casadi_dimension(h->inequalities.cols())||
           !fits_casadi_dimension(h->equalities.rows())||!fits_casadi_dimension(h->equalities.cols()))return false;
    for(const auto& term:request.source_cost.residual_norms)
        if(!fits_casadi_dimension(term.map.rows)||!fits_casadi_dimension(term.map.cols))return false;
    return true;
}
Vector values(const DM& vector) {return static_cast<Vector>(vector);}
Vector values(const numeric::VectorView& vector) {
    return Vector(vector.values().begin(),vector.values().end());
}
void constrain(casadi::Opti& opti,const MX& z,const sets::SetData& domain) {
    const auto representation=domain.representation();
    const auto* h=std::get_if<sets::HRepresentation>(&representation);
    if(!h) {
        if(const auto* point=std::get_if<sets::SingletonRepresentation>(&representation)) {
            const auto rhs=DM(values(point->point));
            opti.subject_to(z==rhs); return;
        }
        if(std::holds_alternative<sets::UniversalRepresentation>(representation))return;
        throw std::runtime_error("empty or unsupported whole-history domain");
    }
    if(h->inequalities.rows())opti.subject_to(MX::mtimes(dense(h->inequalities),z)<=DM(values(h->upper_bounds)));
    if(h->equalities.rows())opti.subject_to(MX::mtimes(dense(h->equalities),z)==DM(values(h->equality_values)));
}
class NativeWorkspace final:public optimization::HistoryOptimizerWorkspace {
public:
    optimization::RawHistorySolveOutcome solve_candidate(const optimization::HistoryOptimizationRequest& request,
        const ExecutionContext& context) override {
        if(!fits_casadi_request(request))
            return Diagnostic{DiagnosticCode::unsupported,"history.casadi_ipopt.dimensions",
                "A canonical history or constraint dimension exceeds CasADi's integer index range."};
        if(context.cancellation.stop_requested())return OperationStopped{StopReason::cancelled,"Native CasADi history optimization cancelled before solve"};
        if(context.deadline&&std::chrono::steady_clock::now()>=*context.deadline)
            return OperationStopped{StopReason::deadline_expired,"Native CasADi history optimization deadline expired before solve"};
        try {
            const auto& cost=request.source_cost;
            const auto size=request.initial_history.size();
            casadi::Opti opti;
            const auto z=opti.variable(static_cast<casadi_int>(size));
            opti.set_initial(z,DM(request.initial_history));
            constrain(opti,z,request.feasible_histories.relation);
            const auto& q=cost.quadratic;
            MX objective=0.5*MX::mtimes(std::vector<MX>{z.T(),dense(q.Q),z})+
                MX::dot(DM(q.linear),z)+q.offset;
            for(const auto& term:cost.residual_norms) {
                Matrix weighted=term.map;
                Vector target=term.target;
                for(std::size_t i=0;i<weighted.rows;++i) {
                    const double factor=std::sqrt(term.weights[i]);
                    target[i]*=factor;
                    for(std::size_t j=0;j<weighted.cols;++j)weighted.values[i*weighted.cols+j]*=factor;
                }
                const auto residual=MX::mtimes(dense(weighted),z)-DM(target);
                const auto epigraph=opti.variable();
                if(term.map.rows==1) {
                    // |r| <= t is exactly linear and implies t >= 0.
                    opti.subject_to(residual(0)<=epigraph);
                    opti.subject_to(-residual(0)<=epigraph);
                } else {
                    opti.subject_to(epigraph>=0);
                    opti.subject_to(MX::dot(residual,residual)<=epigraph*epigraph);
                }
                double squared=0;
                for(std::size_t i=0;i<weighted.rows;++i) {
                    double value=-target[i];
                    for(std::size_t j=0;j<size;++j)value+=weighted.values[i*size+j]*request.initial_history[j];
                    squared+=value*value;
                }
                opti.set_initial(epigraph,std::sqrt(squared)+1e-3);
                objective+=term.coefficient*epigraph;
            }
            opti.minimize(objective);
            const auto dual_count=opti.g().numel();
            opti.set_initial(opti.lam_g(),DM::zeros(dual_count));
            const auto initial_primal=values(opti.debug().value(z,opti.initial()));
            const auto initial_dual=values(opti.debug().value(opti.lam_g(),opti.initial()));
            if(initial_dual.size()!=static_cast<std::size_t>(dual_count)||
               std::any_of(initial_dual.begin(),initial_dual.end(),[](double value){return value!=0;}))
                return Diagnostic{DiagnosticCode::evidence_mismatch,"history.casadi_ipopt.initial_duals",
                    "CasADi initial dual readback differs from this NLP's zero dual vector or constraint dimension."};
            casadi::Dict options{{"sb","yes"},{"print_level",0},{"max_iter",6000},
                {"tol",1e-11},{"acceptable_tol",1e-10},{"bound_relax_factor",0.0},
                {"warm_start_init_point","yes"}};
            if(context.deadline)
                options["max_wall_time"]=std::max(0.001,std::chrono::duration<double>(
                    *context.deadline-std::chrono::steady_clock::now()).count());
            opti.solver("ipopt",{{"print_time",false}},options);
            const auto solution=opti.solve();
            if(context.cancellation.stop_requested())return OperationStopped{StopReason::cancelled,"Native CasADi history optimization cancelled during solve"};
            if(context.deadline&&std::chrono::steady_clock::now()>=*context.deadline)
                return OperationStopped{StopReason::deadline_expired,"Native CasADi history optimization deadline reached"};
            const auto diagnostics="native C++ CasADi "+std::string(casadi::CasadiMeta::version())+
                "; IPOPT; "+opti.stats().at("return_status").to_string()+"; all history coordinates free; local numerical";
            return optimization::RawHistorySolve{values(solution.value(z)),static_cast<double>(solution.value(objective)),
                request.initial_history,initial_primal,Vector(initial_dual.size(),0.0),initial_dual,diagnostics};
        } catch(const std::exception& error) {
            if(context.cancellation.stop_requested())return OperationStopped{StopReason::cancelled,"Native CasADi history optimization cancelled"};
            if(context.deadline&&std::chrono::steady_clock::now()>=*context.deadline)
                return OperationStopped{StopReason::deadline_expired,"Native CasADi history optimization deadline expired"};
            return Diagnostic{DiagnosticCode::unsupported,"history.casadi_ipopt",error.what()};
        }
    }
};
}

registry::Registration<registry::HistoryOptimizerPort> make_casadi_history_optimizer_registration() {
    return {{{"csl.nlp.casadi-ipopt.history-cost"},"1"},
        [](const optimization::HistoryOptimizationRequest& request,const registry::Requirements&)->registry::Capability {
            const auto diagnostics=optimization::check_history_optimization_request(request);
            if(!diagnostics.empty())return diagnostics;
            return registry::Offer{{{"csl.whole-history-source-cost.v1"},Assurance::numerical,{},{},{}}};
        },
        [](const optimization::HistoryOptimizationRequest&)->std::unique_ptr<optimization::HistoryOptimizerWorkspace> {
            return std::make_unique<NativeWorkspace>();
        }};
}
} // namespace csl::adapters::nlp
