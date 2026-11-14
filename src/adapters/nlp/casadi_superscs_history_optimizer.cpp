#include <csl/adapters/nlp/casadi_superscs_history_optimizer.hpp>
#include <casadi/casadi.hpp>

#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>

namespace csl::adapters::nlp {
namespace {
using casadi::DM;
using casadi::MX;

DM dense(const Matrix& matrix) {
    DM out=DM::zeros(static_cast<casadi_int>(matrix.rows),static_cast<casadi_int>(matrix.cols));
    for(std::size_t i=0;i<matrix.rows;++i)
        for(std::size_t j=0;j<matrix.cols;++j)
            out(static_cast<casadi_int>(i),static_cast<casadi_int>(j))=matrix.values[i*matrix.cols+j];
    return out;
}
Vector values(const DM& vector) {return static_cast<Vector>(vector);}
bool fits_casadi_dimension(std::size_t dimension) {
    return dimension<=static_cast<std::size_t>(std::numeric_limits<casadi_int>::max());
}

struct LinearDomain {
    Matrix coefficients;
    Vector lower;
    Vector upper;
};
LinearDomain linear_domain(const optimization::HistoryOptimizationRequest& request) {
    const auto n=request.source_cost.quadratic.dimension;
    const auto representation=request.feasible_histories.relation.representation();
    if(const auto* h=std::get_if<sets::HRepresentation>(&representation)) {
        const auto rows=h->inequalities.rows()+h->equalities.rows();
        Matrix a{rows,n,Vector(rows*n,0.0)};
        Vector lower(rows,-std::numeric_limits<double>::infinity()),upper(rows);
        std::size_t row=0;
        for(std::size_t i=0;i<h->inequalities.rows();++i,++row) {
            for(std::size_t j=0;j<n;++j)a.values[row*n+j]=h->inequalities(i,j);
            upper[row]=h->upper_bounds[i];
        }
        for(std::size_t i=0;i<h->equalities.rows();++i,++row) {
            for(std::size_t j=0;j<n;++j)a.values[row*n+j]=h->equalities(i,j);
            lower[row]=upper[row]=h->equality_values[i];
        }
        return {std::move(a),std::move(lower),std::move(upper)};
    }
    if(const auto* point=std::get_if<sets::SingletonRepresentation>(&representation)) {
        Matrix a{n,n,Vector(n*n,0.0)};
        for(std::size_t i=0;i<n;++i)a.values[i*n+i]=1.0;
        return {std::move(a),point->point,point->point};
    }
    return {Matrix{0,n,{}},{},{}};
}

class SuperSCSWorkspace final:public optimization::HistoryOptimizerWorkspace {
public:
    optimization::RawHistorySolveOutcome solve_candidate(const optimization::HistoryOptimizationRequest& request,
        const ExecutionContext& context) override {
        if(!std::holds_alternative<optimization::ColdStart>(request.start))
            return Diagnostic{DiagnosticCode::unsupported,"history.start",
                "SuperSCS supports an explicitly requested backend cold start and does not accept a supplied primal start."};
        if(!std::all_of(request.source_cost.quadratic.Q.values.begin(),request.source_cost.quadratic.Q.values.end(),
                [](double value){return value==0.0;}))
            return Diagnostic{DiagnosticCode::unsupported,"history.superscs.quadratic",
                "The SuperSCS history provider currently accepts only affine-plus-norm source objectives."};
        if(!casadi::has_conic("superscs"))
            return Diagnostic{DiagnosticCode::unsupported,"history.superscs.plugin",
                "The installed CasADi package does not expose its SuperSCS conic plugin."};
        if(context.cancellation.stop_requested())
            return OperationStopped{StopReason::cancelled,"SuperSCS history optimization cancelled before solve"};
        if(context.deadline&&std::chrono::steady_clock::now()>=*context.deadline)
            return OperationStopped{StopReason::deadline_expired,"SuperSCS history optimization deadline expired before solve"};
        try {
            const auto& cost=request.source_cost;
            const auto history_size=cost.quadratic.dimension;
            std::vector<const optimization::WeightedHistoryResidualNorm*> terms;
            std::size_t psd_dimension=0;
            for(const auto& term:cost.residual_norms) {
                if(term.map.rows==0)continue;
                if(term.map.rows>=std::numeric_limits<std::size_t>::max()-psd_dimension)
                    return Diagnostic{DiagnosticCode::unsupported,"history.superscs.dimensions","SOC block dimension overflows addressable storage."};
                psd_dimension+=term.map.rows+1;
                terms.push_back(&term);
            }
            if(terms.size()>std::numeric_limits<std::size_t>::max()-history_size)
                return Diagnostic{DiagnosticCode::unsupported,"history.superscs.dimensions","History and epigraph dimensions overflow addressable storage."};
            const auto variables=history_size+terms.size();
            if(!fits_casadi_dimension(variables)||!fits_casadi_dimension(psd_dimension)||
               (psd_dimension&&psd_dimension>std::numeric_limits<std::size_t>::max()/psd_dimension)||
               !fits_casadi_dimension(psd_dimension*psd_dimension))
                return Diagnostic{DiagnosticCode::unsupported,"history.superscs.dimensions","Conic variable or PSD dimensions exceed CasADi's index range."};

            const auto domain=linear_domain(request);
            const auto constraint_rows=domain.coefficients.rows;
            if(!fits_casadi_dimension(constraint_rows))
                return Diagnostic{DiagnosticCode::unsupported,"history.superscs.constraints","Linear constraint count exceeds CasADi's index range."};
            const auto z=MX::sym("history_and_epigraphs",static_cast<casadi_int>(variables));
            std::vector<MX> cones;
            cones.reserve(terms.size());
            DM objective_linear=DM::zeros(static_cast<casadi_int>(variables),1);
            for(std::size_t i=0;i<history_size;++i)
                objective_linear(static_cast<casadi_int>(i))=cost.quadratic.linear[i];
            for(std::size_t i=0;i<terms.size();++i) {
                const auto& term=*terms[i];
                Matrix weighted=term.map;
                Vector target=term.target;
                for(std::size_t row=0;row<weighted.rows;++row) {
                    const double scale=std::sqrt(term.weights[row]);
                    target[row]*=scale;
                    for(std::size_t column=0;column<history_size;++column)
                        weighted.values[row*history_size+column]*=scale;
                }
                const auto residual=MX::mtimes(dense(weighted),z(casadi::Slice(0,static_cast<casadi_int>(history_size))))-DM(target);
                cones.push_back(casadi::soc(residual,z(static_cast<casadi_int>(history_size+i))));
                objective_linear(static_cast<casadi_int>(history_size+i))=term.coefficient;
            }
            const auto hessian=DM::zeros(static_cast<casadi_int>(variables),static_cast<casadi_int>(variables));
            MX psd;
            DM q_matrix,p_matrix;
            if(!cones.empty()) {
                psd=casadi::diagcat(cones);
                const auto flattened=MX::reshape(psd,static_cast<casadi_int>(psd_dimension*psd_dimension),1);
                const casadi::Function build_conic_data("history_soc_data",{z},
                    {MX::jacobian(flattened,z),psd});
                const auto data=build_conic_data(std::vector<DM>{DM::zeros(static_cast<casadi_int>(variables),1)});
                q_matrix=data[0];p_matrix=data[1];
            } else {
                q_matrix=DM::zeros(0,static_cast<casadi_int>(variables));
                p_matrix=DM::zeros(0,0);
            }
            const auto a_matrix=dense(domain.coefficients);
            const auto lower=DM(domain.lower),upper=DM(domain.upper);
            casadi::SpDict sparsities{{"h",hessian.sparsity()},{"a",a_matrix.sparsity()},
                {"q",q_matrix.sparsity()},{"p",p_matrix.sparsity()}};
            casadi::Dict superscs_options{{"verbose",false},{"eps",1e-8},{"max_iters",100000}};
            casadi::Dict options{{"print_time",false},{"superscs",superscs_options}};
            // A new solver function is made for every request. No x0 or dual warm-start input is supplied.
            const auto solver=casadi::conic("history_superscs","superscs",sparsities,options);
            casadi::DMDict inputs{{"h",hessian},{"g",objective_linear},{"a",a_matrix},
                {"lba",lower},{"uba",upper},
                {"lbx",DM::repmat(-DM::inf(),static_cast<casadi_int>(variables),1)},
                {"ubx",DM::repmat(DM::inf(),static_cast<casadi_int>(variables),1)},
                {"q",q_matrix},{"p",p_matrix}};
            const auto output=solver(inputs);
            const auto stats=solver.stats();
            const auto status=stats.at("unified_return_status").to_string();
            if(!stats.at("success").to_bool())
                return Diagnostic{DiagnosticCode::unsupported,"history.superscs.solve","SuperSCS returned "+status+"."};
            if(context.cancellation.stop_requested())
                return OperationStopped{StopReason::cancelled,"SuperSCS history optimization cancelled during solve"};
            if(context.deadline&&std::chrono::steady_clock::now()>=*context.deadline)
                return OperationStopped{StopReason::deadline_expired,"SuperSCS history optimization deadline reached"};
            const auto solution=values(output.at("x"));
            if(solution.size()!=variables)
                return Diagnostic{DiagnosticCode::evidence_mismatch,"history.superscs.primal","SuperSCS returned a primal vector with the wrong layout."};
            const auto diagnostics="native C++ CasADi "+std::string(casadi::CasadiMeta::version())+
                "; SuperSCS; "+status+"; exact PSD/SOC formulation; cold start; affine-plus-norm; local numerical";
            return optimization::RawHistorySolve{Vector(solution.begin(),solution.begin()+static_cast<std::ptrdiff_t>(history_size)),
                static_cast<double>(output.at("cost"))+cost.quadratic.offset,
                optimization::BackendColdStartEvidence{"csl.conic.superscs.history-cost@1",
                    "fresh SuperSCS conic function; no primal or dual warm-start inputs supplied",
                    "CasADi conic outputs do not expose internal cold-start primal or dual readbacks"},diagnostics};
        } catch(const std::exception& error) {
            if(context.cancellation.stop_requested())return OperationStopped{StopReason::cancelled,"SuperSCS history optimization cancelled"};
            if(context.deadline&&std::chrono::steady_clock::now()>=*context.deadline)
                return OperationStopped{StopReason::deadline_expired,"SuperSCS history optimization deadline expired"};
            return Diagnostic{DiagnosticCode::unsupported,"history.superscs",error.what()};
        }
    }
};
}

registry::Registration<registry::HistoryOptimizerPort> make_casadi_superscs_history_optimizer_registration() {
    return {{{"csl.conic.superscs.history-cost"},"1"},
        [](const optimization::HistoryOptimizationRequest& request,const registry::Requirements&)->registry::Capability {
            const auto diagnostics=optimization::check_history_optimization_request(request);
            if(!diagnostics.empty())return diagnostics;
            if(!std::holds_alternative<optimization::ColdStart>(request.start))
                return Diagnostics{{DiagnosticCode::unsupported,"history.start",
                    "SuperSCS requires an explicitly selected backend cold start."}};
            if(!std::all_of(request.source_cost.quadratic.Q.values.begin(),request.source_cost.quadratic.Q.values.end(),
                    [](double value){return value==0.0;}))
                return Diagnostics{{DiagnosticCode::unsupported,"history.superscs.quadratic",
                    "SuperSCS accepts only affine-plus-norm source objectives."}};
            return registry::Offer{{{"csl.whole-history-source-cost.v1"},Assurance::numerical,{},{},{}}};
        },
        [](const optimization::HistoryOptimizationRequest&)->std::unique_ptr<optimization::HistoryOptimizerWorkspace> {
            return std::make_unique<SuperSCSWorkspace>();
        }};
}
} // namespace csl::adapters::nlp
