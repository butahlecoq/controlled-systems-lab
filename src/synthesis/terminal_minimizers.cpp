#include <csl/synthesis/terminal_minimizers.hpp>
#include <csl/optimization/linear_program.hpp>
#include <csl/execution/timing_collector.hpp>
#include <cmath>
#include <type_traits>

namespace csl::synthesis {
namespace {
namespace ar = csl::artifacts;
namespace ob = csl::execution::observability;
TerminalMinimizers rejected(DiagnosticCode code,std::string field,std::string message) {
    TerminalMinimizers r;r.termination=code==DiagnosticCode::unsupported?Termination::operation_rejected:Termination::contract_rejected;
    r.diagnostics={{code,std::move(field),std::move(message)}};return r;
}
bool same_module(const ar::ModuleIdentity& planned,const registry::Identity& actual) noexcept {
    return planned.id==actual.id&&planned.version==actual.version;
}
std::optional<ob::TimingScope> start_solver_scope(const ExecutionContext& context,
    const ProgramIdentity& program,const registry::Provenance& provider) noexcept {
    if(!context.timing||!context.timing->enabled()||!provider.actual)return {};
    try {
        auto snapshot=context.timing->snapshot();
        const auto* report=std::get_if<ob::TimingReport>(&snapshot);
        if(!report)return {};
        const ar::SpanDescriptor* match=nullptr;
        for(const auto& span:report->observations.description().spans) {
            const auto& descriptor=span.descriptor;
            if(descriptor.operation!="terminal.program.solve"||!descriptor.program||
                *descriptor.program!=program||!descriptor.backend||
                !same_module(*descriptor.backend,*provider.actual))continue;
            if(match)return {};
            match=&descriptor;
        }
        if(!match)return {};
        auto started=ob::start_timing(context,match->id);
        if(auto* scope=std::get_if<ob::TimingScope>(&started))return std::move(*scope);
    } catch(...) { return {}; }
    return {};
}
TerminalObjective objective_description(const optimization::Objective& objective) {
    return std::visit([](const auto& c)->TerminalObjective {
        using T=std::decay_t<decltype(c)>;
        auto copy=[](numeric::VectorView v){return Vector(v.values().begin(),v.values().end());};
        auto dense=[](numeric::MatrixView m){Matrix r{m.rows(),m.cols(),{}};for(std::size_t i=0;i<m.rows();++i)for(std::size_t j=0;j<m.cols();++j)r.values.push_back(m(i,j));return r;};
        if constexpr(std::is_same_v<T,optimization::LinearCoefficients>)return LinearTerminal{copy(c.coefficients),c.offset};
        else if constexpr(std::is_same_v<T,optimization::QuadraticCoefficients>)return QuadraticTerminal{dense(c.Q),copy(c.linear),c.offset};
        else return ResidualNormTerminal{dense(c.map),copy(c.target)};
    },objective.coefficients());
}
struct Rows { SparseMatrix matrix; std::vector<Interval> bounds; };
Rows constraints(const sets::HRepresentation& h,std::size_t n) {
    Rows r{{0,n,{0},{},{}},{}};
    auto add=[&](numeric::MatrixView m,numeric::VectorView b,bool equality) {
        for(std::size_t i=0;i<m.rows();++i) {
            for(std::size_t j=0;j<n;++j)if(m(i,j)!=0){r.matrix.column_indices.push_back(j);r.matrix.values.push_back(m(i,j));}
            r.matrix.row_offsets.push_back(r.matrix.values.size());r.bounds.push_back({equality?std::optional<double>{b[i]}:std::nullopt,b[i]});++r.matrix.rows;
        }
    };
    add(h.inequalities,h.upper_bounds,false);add(h.equalities,h.equality_values,true);return r;
}
OptimumEvidence evidence(const ProgramResult& r,ProblemId id) {
    // Program evidence alone does not prove this is the complete terminal slice.
    OptimumEvidence e{{id,Unestablished{}},{}};
    if(r.objective.lower)e.bounds.lower=ObjectiveBound{r.objective.lower->value,{id,Unestablished{}}};
    if(r.objective.upper)e.bounds.upper=ObjectiveBound{r.objective.upper->value,{id,Unestablished{}}};
    return e;
}
}
TerminalOptimizer::TerminalOptimizer(registry::PreparedProvider<registry::LPPort> lp,registry::PreparedProvider<registry::ConvexPort> convex)
    :lp_(std::move(lp)),convex_(std::move(convex)){}
TerminalMinimizers TerminalOptimizer::solve(const problem::ResolvedProblem& problem,const FamilyRequest& request,
    const TerminalSlice& slice,const ExecutionContext& context) const {
    if(slice.problem!=problem.identity() || request.objective!=problem.identity())
        return rejected(DiagnosticCode::evidence_mismatch,"terminal.problem","resolved problem, slice and objective identities must agree");
    if(request.assurance!=Assurance::numerical)
        return rejected(DiagnosticCode::unsupported,"terminal.assurance","no validated terminal relation construction is available");
    if(!std::isfinite(request.numerical.absolute_tolerance)||request.numerical.absolute_tolerance<0||
       !std::isfinite(request.numerical.relative_tolerance)||request.numerical.relative_tolerance<0)
        return rejected(DiagnosticCode::invalid_input,"terminal.numerical","invalid effective numerical policy");
    const auto objective=problem.objective();const auto n=objective.dimension();
    if(slice.feasible.metadata()->set.dimension!=n)
        return rejected(DiagnosticCode::invalid_input,"terminal.dimension","slice dimension differs from the resolved objective");
    const auto representation=slice.feasible.representation();
    if(!std::holds_alternative<sets::HRepresentation>(representation))
        return rejected(DiagnosticCode::unsupported,"terminal.representation","provide an H-polyhedral terminal slice through the selected set/conversion providers");
    const auto h=std::get<sets::HRepresentation>(representation);auto rows=constraints(h,n);
    auto execution=context;execution.numerical=request.numerical;
    TerminalMinimizers result;result.construction.feasible_slice=slice.feasible.metadata()->id;
    if(context.cancellation.stop_requested()||(context.deadline&&std::chrono::steady_clock::now()>=*context.deadline)) {
        result.termination=context.cancellation.stop_requested()?Termination::cancelled:Termination::resource_limit;return result;
    }
    const ProgramIdentity identity{problem.identity(),{"syn02-terminal:"+slice.feasible.metadata()->id.value}};
    const auto description=objective_description(objective);
    auto run=[&]<class Program,class Port>(const Program& program,const registry::PreparedProvider<Port>& provider)->bool {
        result.provider=provider.provenance();auto admitted=provider.prepare(program);
        if(const auto* reject=std::get_if<registry::Rejection>(&admitted)) {
            result.termination=Termination::operation_rejected;result.provider=reject->provenance;result.diagnostics=reject->diagnostics;return false;
        }
        auto workers=std::get<registry::PreparedPipeline<Port>>(std::move(admitted)).create();
        auto solver_scope=start_solver_scope(context,program.identity(),provider.provenance());
        auto outcome=std::get<0>(workers)->run(execution);
        if(const auto* unsupported=std::get_if<Unsupported>(&outcome)) {
            if(solver_scope)solver_scope->close(Termination::operation_rejected);
            result.termination=Termination::operation_rejected;result.diagnostics=unsupported->diagnostics;return false;
        }
        const auto& solved=std::get<ProgramResult>(outcome);
        if(solver_scope)solver_scope->close(solved.termination);
        auto diagnostics=optimization::check_program_result(solved,program,request.assurance);
        if(!diagnostics.empty()){result.termination=Termination::contract_rejected;result.diagnostics=std::move(diagnostics);return false;}
        result.optimization=solved;result.termination=solved.termination;result.outcome=solved.outcome.value;result.optimum=evidence(solved,problem.identity());
        // Retain bounds and mathematical outcome even when an execution phase stopped.
        if(solved.outcome.value!=MathematicalOutcome::optimal||!solved.primal)return false;
        auto evaluation=optimization::evaluate_primal(program,*solved.primal,request.numerical,Verifier{{"syn02-terminal-primal"},"1"});
        if(!std::holds_alternative<typename std::conditional_t<std::is_same_v<Program,LinearProgram>,optimization::PrimalEvaluation,optimization::ConvexPrimalEvaluation>>(evaluation)) {
            result.diagnostics={{DiagnosticCode::invalid_claim,"terminal.anchor","cannot evaluate returned optimizer anchor"}};return false;
        }
        const auto& checked=std::get<std::conditional_t<std::is_same_v<Program,LinearProgram>,optimization::PrimalEvaluation,optimization::ConvexPrimalEvaluation>>(evaluation);
        for(const auto measure:{checked.residuals.rows,checked.residuals.variables})
            if(measure.violation>request.numerical.absolute_tolerance+request.numerical.relative_tolerance*measure.scale) {
                result.diagnostics={{DiagnosticCode::invalid_claim,"terminal.anchor","returned optimizer anchor violates the terminal slice"}};return false;
            }
        return true;
    };
    bool anchored=false;
    if(const auto* linear=std::get_if<LinearTerminal>(&description)) {
        auto program=optimization::make_linear_program({identity,linear->coefficients,linear->offset,rows.matrix,std::vector<Interval>(n),rows.bounds});
        if(const auto* d=std::get_if<Diagnostics>(&program)){result.termination=Termination::contract_rejected;result.diagnostics=*d;return result;}
        anchored=run(std::get<LinearProgram>(program),lp_);
    } else {
        const auto squared=std::holds_alternative<ResidualNormTerminal>(description)?std::optional<ProgramId>{{identity.program.value+":squared"}}:std::nullopt;
        auto program=optimization::make_convex_program({identity,description,rows.matrix,std::vector<Interval>(n),rows.bounds,squared},{request.assurance,request.numerical});
        if(const auto* d=std::get_if<Diagnostics>(&program)){result.termination=Termination::contract_rejected;result.diagnostics=*d;return result;}
        if(const auto* stop=std::get_if<OperationStopped>(&program)){result.termination=Termination::numerical_failure;result.diagnostics={{DiagnosticCode::unsupported,"terminal.objective",stop->diagnostics}};return result;}
        anchored=run(std::get<ConvexProgram>(program),convex_);
    }
    if(!anchored)return result;
    const auto& a=*result.optimization->primal;
    Matrix eq{h.equalities.rows(),n,{}};Vector rhs(h.equality_values.values().begin(),h.equality_values.values().end());
    for(std::size_t i=0;i<h.equalities.rows();++i)for(std::size_t j=0;j<n;++j)eq.values.push_back(h.equalities(i,j));
    auto append=[&](const Vector& row){double value=0;for(std::size_t j=0;j<n;++j)value+=row[j]*a[j];eq.values.insert(eq.values.end(),row.begin(),row.end());rhs.push_back(value);++eq.rows;};
    std::visit([&](const auto& c) {
        using T=std::decay_t<decltype(c)>;
        if constexpr(std::is_same_v<T,LinearTerminal>) {append(c.coefficients);result.construction.characterization="C intersect {x: c'x=c'a}";}
        else if constexpr(std::is_same_v<T,QuadraticTerminal>) {
            for(std::size_t i=0;i<n;++i){Vector row(n);for(std::size_t j=0;j<n;++j)row[j]=c.Q.values[i*n+j]/2+c.Q.values[j*n+i]/2;append(row);}
            append(c.linear);result.construction.characterization="C intersect {x: Hx=Ha, q'x=q'a}, H=(Q+Q')/2";
        } else {
            for(std::size_t i=0;i<c.map.rows;++i){Vector row(n);for(std::size_t j=0;j<n;++j)row[j]=c.map.values[i*n+j];append(row);}
            result.construction.characterization="C intersect {x: Lx=La}";
        }
    },description);
    auto m=numeric::snapshot(eq);auto b=numeric::snapshot_vector(rhs);
    if(!std::holds_alternative<numeric::MatrixView>(m)||!std::holds_alternative<numeric::VectorView>(b)) {
        result.diagnostics={{DiagnosticCode::invalid_claim,"terminal.arithmetic","nonfinite optimal-level construction; optimum evidence retained"}};return result;
    }
    auto set=sets::make_h({{slice.feasible.metadata()->id.value+":terminal-candidate"},n,slice.feasible.metadata()->coordinate_labels},
        {h.inequalities,h.upper_bounds,std::get<numeric::MatrixView>(m),std::get<numeric::VectorView>(b)});
    if(const auto* d=std::get_if<Diagnostic>(&set)){result.diagnostics={*d};return result;}
    result.relation=std::get<sets::SetData>(std::move(set));
    result.construction.assumptions={"convex feasible slice","finite attained optimum with a true global optimizer anchor",
        "symmetric part of quadratic objective is PSD","binary64 construction has no established coverage procedure"};
    return result;
}
}
