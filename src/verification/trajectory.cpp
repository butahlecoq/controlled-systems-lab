#include <csl/verification/trajectory.hpp>
#include <csl/optimization/linear_program.hpp>
#include <csl/optimization/lp_backend.hpp>
#include <algorithm>
#include <bit>
#include <cmath>
#include <limits>
#include <type_traits>

namespace csl::verification {
namespace {
struct Stopped {};
std::string indexed(const std::string& name,std::size_t index) {return name+"["+std::to_string(index)+"]";}
bool finite_nonnegative(double x) {return std::isfinite(x)&&x>=0;}
class Check {
    const problem::ResolvedProblem& original_;
    const ExecutionContext& context_;
    TrajectoryReport& report_;
    std::optional<registry::RegisteredLPQueryRunner> runner_;
    bool violated_{false},unknown_{false};
    std::size_t queries_{};
public:
    Check(const problem::ResolvedProblem& p,const ExecutionContext& c,TrajectoryReport& r,
        std::optional<registry::PreparedProvider<registry::LPPort>> provider):original_(p),context_(c),report_(r) {
        if(provider)runner_.emplace(std::move(*provider));
    }
    void diagnose(DiagnosticCode code,std::string field,std::string explanation) {
        report_.diagnostics.push_back({code,std::move(field),std::move(explanation)});
    }
    void stop(Termination termination,const std::string& why) {
        report_.termination=termination;diagnose(DiagnosticCode::unsupported,"verification",why);throw Stopped{};
    }
    void boundary() {
        if(context_.cancellation.stop_requested())stop(Termination::cancelled,"cancellation observed");
        if(context_.deadline&&std::chrono::steady_clock::now()>=*context_.deadline)
            stop(Termination::deadline_expired,"deadline observed");
    }
    double number(double value) {
        if(!std::isfinite(value))stop(Termination::numerical_failure,"nonfinite verification arithmetic");
        return value;
    }
    double product(double a,double b) {
        const auto v=number(a*b);
        if(a!=0&&b!=0&&v==0)stop(Termination::numerical_failure,"nonzero product underflow");
        return v;
    }
    bool residual(std::string field,double violation,double scale,bool feasibility=true) {
        boundary();
        if(report_.residuals.size()>=report_.input.limits.residuals)
            stop(Termination::resource_limit,"residual count limit reached");
        const auto tolerance=number(report_.verification.numerical.absolute_tolerance+
            product(report_.verification.numerical.relative_tolerance,number(scale)));
        const bool satisfied=number(violation)<=tolerance;
        report_.residuals.push_back({std::move(field),{violation,scale},tolerance,satisfied});
        if(feasibility&&!satisfied)violated_=true;
        return satisfied;
    }
    void equal(const std::string& field,double actual,double expected,bool feasibility=true) {
        residual(field,std::abs(number(actual-expected)),std::max(std::abs(actual),std::abs(expected)),feasibility);
    }
    void unavailable(const std::string& field,const std::string& reason) {
        unknown_=true;diagnose(DiagnosticCode::unsupported,field,reason);
    }
    void bindings() {
        bool good=true;
        const auto mismatch=[&](const std::string& field,const std::string& why) {
            good=false;diagnose(DiagnosticCode::evidence_mismatch,field,why);
        };
        const auto id=[&](const ProblemId& subject,const std::string& field) {
            if(subject!=report_.problem)mismatch(field,"problem identity differs from original resolved data");
        };
        const auto support=[&](const EvidenceSupport& evidence,const std::string& field,
            const std::optional<ProgramIdentity>& expected_program) {
            if(const auto* n=std::get_if<NumericalCheck>(&evidence))
                if(!finite_nonnegative(n->absolute_tolerance)||!finite_nonnegative(n->relative_tolerance)||
                    !finite_nonnegative(n->max_residual)||n->verifier.value.empty())mismatch(field,"malformed numerical evidence");
            if(const auto* proof=std::get_if<ExactFarkasEvidence>(&evidence))
                if(!expected_program||proof->subject()!=*expected_program)
                    mismatch(field,"exact Farkas evidence is not bound to the exact expected program");
        };
        const auto claim=[&](const ClaimEvidence& evidence,const std::string& field) {
            id(evidence.problem,field);support(evidence.support,field,std::nullopt);
        };
        id(report_.input.witness.problem,"witness.problem");
        if(const auto& outcome=report_.input.outcome) {id(outcome->subject,"outcome.subject");support(outcome->support,"outcome.support",std::nullopt);}
        if(const auto& family=report_.input.family) {
            const auto& identity=family->identity();
            id(identity.problem,"family.problem");id(identity.request.objective,"family.request.objective");
            const auto expected=original_.constraints().coordinates();
            if(identity.coordinates!=expected)
                mismatch("family.coordinates","family identity coordinates differ from original problem");
            if(const auto& binding=report_.input.expected_synthesis) {
                if(identity.request!=binding->request)
                    mismatch("family.expected_synthesis.request","reported family request differs from the independently supplied effective request");
                if(identity.strategy!=binding->strategy)
                    mismatch("family.expected_synthesis.strategy","reported strategy identity differs from the independently supplied strategy");
                if(identity.strategy_version!=binding->strategy_version)
                    mismatch("family.expected_synthesis.strategy_version","reported strategy version differs from the independently supplied version");
                if(identity.lineage!=binding->lineage)
                    mismatch("family.expected_synthesis.lineage","reported ordered transformation lineage differs from the independently supplied lineage");
            } else mismatch("family.expected_synthesis","an independent expected synthesis binding is required to verify a reported family");
            const auto family_bound=[&](const std::optional<ObjectiveBound>& bound,const std::string& field) {
                if(bound) {claim(bound->evidence,field);if(!std::isfinite(bound->value))mismatch(field,"bound must be finite");}
            };
            std::visit([&](const auto& product) {
                using T=std::decay_t<decltype(product)>;
                if(product.relation.coordinates!=expected)
                    mismatch("family.relation.coordinates","joint relation coordinates differ from original problem");
                if(product.relation.representation!=identity.request.representation)
                    mismatch("family.relation.representation","relation representation differs from effective request");
                if constexpr(std::is_same_v<T,CompleteOptimalFamily>||std::is_same_v<T,PartialOptimalFamily>) {
                    claim(product.optimum.optimum,"family.optimum");
                    family_bound(product.optimum.bounds.lower,"family.bounds.lower");
                    family_bound(product.optimum.bounds.upper,"family.bounds.upper");
                    if constexpr(std::is_same_v<T,CompleteOptimalFamily>) {
                        if(product.completeness.binding!=identity)
                            mismatch("family.completeness.binding","completeness is not bound to the published family identity");
                    } else claim(product.optimal_subset.every_history_optimal,"family.partial.optimal_subset");
                } else {
                    std::visit([&](const auto& relation) {
                        using R=std::decay_t<decltype(relation)>;
                        if constexpr(std::is_same_v<R,OuterCandidateEvidence>)
                            claim(relation.enclosure,"family.candidate.outer");
                        else if constexpr(std::is_same_v<R,FeasibleCandidateEvidence>)
                            claim(relation.feasibility,"family.candidate.inner");
                    },product.relation_to_target);
                    std::visit([&](const auto& feasibility) {
                        using F=std::decay_t<decltype(feasibility)>;
                        if constexpr(std::is_same_v<F,RelationFeasibilityEvidence>)
                            claim(feasibility.support,"family.candidate.feasibility.relation");
                        else if constexpr(std::is_same_v<F,WitnessFeasibilityEvidence>) {
                            id(feasibility.witness.problem,"family.candidate.feasibility.witness");
                            claim(feasibility.support,"family.candidate.feasibility.witness");
                        }
                    },product.feasibility);
                }
            },family->outcome());
        }
        const auto bound=[&](const std::optional<ObjectiveBound>& b,const std::string& field) {
            if(b) {claim(b->evidence,field);if(!std::isfinite(b->value))mismatch(field,"bound must be finite");}
        };
        bound(report_.input.bounds.lower,"bounds.lower");bound(report_.input.bounds.upper,"bounds.upper");
        for(std::size_t i=0;i<report_.input.backend_bounds.size();++i) {
            const auto program_bound=[&](const std::optional<ProgramObjectiveBound>& b,const std::string& suffix) {
                if(!b)return;
                const auto field=indexed("backend_bounds",i)+suffix;
                id(b->evidence.subject.problem,field);support(b->evidence.support,field,b->evidence.subject);
                if(b->evidence.subject.program.value.empty()||!std::isfinite(b->value))mismatch(field,"missing program identity or nonfinite bound");
            };
            program_bound(report_.input.backend_bounds[i].lower,".lower");program_bound(report_.input.backend_bounds[i].upper,".upper");
        }
        report_.bindings=good?CheckStatus::numerical_pass:CheckStatus::invalid_input;
    }
    // A complete byte spelling binds each query to the original V rows and tested
    // point, without depending on mutable labels or a non-cryptographic hash.
    static void encode(std::string& id,double value) {
        constexpr char digits[]="0123456789abcdef";
        const auto bits=std::bit_cast<std::uint64_t>(value);
        for(int shift=60;shift>=0;shift-=4)id.push_back(digits[(bits>>shift)&15]);
    }
    void membership_v(const sets::VRepresentation& v,std::span<const double> point,const std::string& field) {
        const auto vertices=v.vertices.rows(),rays=v.rays.rows();
        if(vertices==0) {violated_=true;diagnose(DiagnosticCode::invalid_claim,field,"empty vertex hull has no member");return;}
        if(!runner_) {unavailable(field,"V membership needs an admitted LP provider");return;}
        boundary();
        if(queries_>=report_.input.limits.membership_queries)stop(Termination::resource_limit,"membership query count limit reached");
        if(vertices>std::numeric_limits<std::size_t>::max()-rays||point.size()==std::numeric_limits<std::size_t>::max())
            stop(Termination::resource_limit,"membership query dimensions overflow");
        const auto cols=vertices+rays,rows=point.size()+1;
        if(cols>Vector{}.max_size()||rows>std::vector<Interval>{}.max_size()||
            (cols&&rows>Vector{}.max_size()/cols))stop(Termination::resource_limit,"membership query storage dimensions overflow");
        SparseMatrix matrix{rows,cols,{0},{},{}};std::vector<Interval> bounds;
        std::string identity="csl.trajectory.membership.v1:"+field+":"+std::to_string(vertices)+":"+std::to_string(rays)+":"+std::to_string(point.size())+":";
        for(double x:point)encode(identity,x);
        for(std::size_t row=0;row<rows;++row) {
            boundary();
            for(std::size_t col=0;col<cols;++col) {
                const double value=row==point.size()?(col<vertices?1.0:0.0):
                    (col<vertices?v.vertices(col,row):v.rays(col-vertices,row));
                encode(identity,value);
                if(value!=0) {matrix.column_indices.push_back(col);matrix.values.push_back(value);}
            }
            matrix.row_offsets.push_back(matrix.values.size());const auto rhs=row==point.size()?1.0:point[row];bounds.push_back({rhs,rhs});
        }
        auto published=optimization::make_linear_program({{report_.problem,{std::move(identity)}},Vector(cols,0),0,
            std::move(matrix),std::vector<Interval>(cols,{0.0,std::nullopt}),std::move(bounds)});
        if(!std::holds_alternative<LinearProgram>(published)) {unavailable(field,"membership program could not be published");return;}
        const auto& program=std::get<LinearProgram>(published);++queries_;
        const auto outcome=runner_->solve(program,context_);
        if(const auto* unsupported=std::get_if<Unsupported>(&outcome)) {
            report_.diagnostics.insert(report_.diagnostics.end(),unsupported->diagnostics.begin(),unsupported->diagnostics.end());
            unavailable(field,"membership provider rejected the concrete query");return;
        }
        const auto& result=std::get<ProgramResult>(outcome);
        if(result.termination!=Termination::completed)stop(result.termination,"membership provider stopped");
        if(auto diagnostics=optimization::check_program_result(result,program,Assurance::numerical);!diagnostics.empty()) {
            report_.diagnostics.insert(report_.diagnostics.end(),diagnostics.begin(),diagnostics.end());
            unavailable(field,"membership provider returned malformed or misbound evidence");return;
        }
        boundary();
        if(!result.primal||result.primal->size()!=cols||result.outcome.value!=MathematicalOutcome::optimal) {
            unavailable(field,"no completed numerical membership witness; backend nonmembership is not independently verified");return;
        }
        const auto& weights=*result.primal;
        if(!std::all_of(weights.begin(),weights.end(),[](double x){return std::isfinite(x);})) {
            unavailable(field,"nonfinite barycentric witness");return;
        }
        bool good=true;
        for(std::size_t col=0;col<cols;++col)
            good=residual(indexed(field+".weights",col),std::max(0.0,-weights[col]),std::abs(weights[col]),false)&&good;
        for(std::size_t row=0;row<rows;++row) {
            double total=0,scale=0;
            for(std::size_t col=0;col<cols;++col) {
                boundary();const auto coefficient=row==point.size()?(col<vertices?1.0:0.0):
                    (col<vertices?v.vertices(col,row):v.rays(col-vertices,row));
                const auto term=product(coefficient,weights[col]);total=number(total+term);scale=number(scale+std::abs(term));
            }
            const double rhs=row==point.size()?1.0:point[row];scale=std::max(scale,std::abs(rhs));
            good=residual(row==point.size()?field+".weights_sum":indexed(field+".reconstruction",row),std::abs(number(total-rhs)),scale,false)&&good;
        }
        if(!good)unavailable(field,"returned barycentric witness fails original-row checks; membership remains unestablished");
    }
    void membership(const AdmissibleSet& set,std::span<const double> point,const std::string& field) {
        boundary();
        std::visit([&](const auto& value) {
            using T=std::decay_t<decltype(value)>;
            if constexpr(std::is_same_v<T,EmptySet>) {violated_=true;diagnose(DiagnosticCode::invalid_claim,field,"point belongs to an empty domain");}
            else if constexpr(std::is_same_v<T,UniversalSet>) {} // all finite points of the checked dimension
            else if constexpr(std::is_same_v<T,Singleton>) {
                for(std::size_t i=0;i<point.size();++i)equal(indexed(field+".singleton",i),point[i],value.point[i]);
            } else {
                auto published=sets::from_handle(value);
                if(const auto* error=std::get_if<Diagnostic>(&published)) {report_.diagnostics.push_back(*error);unavailable(field,"unknown set representation");return;}
                std::visit([&](const auto& representation) {
                    using R=std::decay_t<decltype(representation)>;
                    if constexpr(std::is_same_v<R,sets::EmptyRepresentation>)membership(EmptySet{point.size()},point,field);
                    else if constexpr(std::is_same_v<R,sets::UniversalRepresentation>) {}
                    else if constexpr(std::is_same_v<R,sets::SingletonRepresentation>) {
                        for(std::size_t i=0;i<point.size();++i)equal(indexed(field+".singleton",i),point[i],representation.point[i]);
                    } else if constexpr(std::is_same_v<R,sets::VRepresentation>)membership_v(representation,point,field);
                    else {
                        const auto rows=[&](const numeric::MatrixView& a,const numeric::VectorView& b,bool equality) {
                            for(std::size_t row=0;row<a.rows();++row) {
                                double total=0,scale=0;
                                for(std::size_t col=0;col<point.size();++col) {
                                    boundary();const auto term=product(a(row,col),point[col]);total=number(total+term);scale=number(scale+std::abs(term));
                                }
                                const auto delta=number(total-b[row]);residual(indexed(field+(equality?".equalities":".inequalities"),row),
                                    equality?std::abs(delta):std::max(0.0,delta),std::max(scale,std::abs(b[row])));
                            }
                        };
                        rows(representation.inequalities,representation.upper_bounds,false);rows(representation.equalities,representation.equality_values,true);
                    }
                },std::get<sets::SetData>(published).representation());
            }
        },set);
    }
    bool shape_and_profile() {
        const auto& p=*original_.description();const auto dimensions=original_.model().dimensions();const auto horizon=original_.model().horizon();
        const auto& witness=report_.input.witness;bool valid=true;
        const auto invalid=[&](const std::string& field) {valid=false;diagnose(DiagnosticCode::invalid_input,field,"wrong shape or nonfinite value");};
        if(witness.states.size()!=horizon+1)invalid("witness.states");
        if(witness.controls.size()!=horizon)invalid("witness.controls");
        const auto vectors=[&](const std::vector<Vector>& values,std::size_t size,const std::string& field) {
            for(std::size_t i=0;i<values.size();++i)if(values[i].size()!=size||!std::all_of(values[i].begin(),values[i].end(),[](double x){return std::isfinite(x);}))invalid(indexed(field,i));
        };
        vectors(witness.states,dimensions.state,"witness.states");vectors(witness.controls,dimensions.control,"witness.controls");
        if(!std::isfinite(witness.original_objective))invalid("witness.original_objective");
        if(!valid) {report_.feasibility=CheckStatus::invalid_input;report_.objective=CheckStatus::invalid_input;return false;}
        if(p.model->dynamics.time_domain!=TimeDomain::discrete)unavailable("model.time_domain","continuous-time verification is unsupported");
        if(!std::holds_alternative<KnownInitial>(p.initial))unavailable("initial","set-valued initial semantics are unsupported");
        if(!std::holds_alternative<ContinuousDomain>(p.controls))unavailable("controls","finite and mixed controls are unsupported");
        if(p.information!=InformationPattern::nominal_open_loop)
            unavailable("information","observation-dependent control semantics are unsupported");
        if(p.external&&!std::holds_alternative<KnownExternalSequence>(*p.external))unavailable("external","uncertain external semantics are unsupported");
        if(unknown_) {report_.feasibility=CheckStatus::unsupported;report_.objective=CheckStatus::unsupported;return false;}
        return true;
    }
    void run() {
        bindings();if(report_.bindings!=CheckStatus::numerical_pass)return;
        if(!finite_nonnegative(report_.verification.numerical.absolute_tolerance)||!finite_nonnegative(report_.verification.numerical.relative_tolerance)) {
            report_.feasibility=CheckStatus::invalid_input;report_.objective=CheckStatus::invalid_input;
            diagnose(DiagnosticCode::invalid_input,"numerical","tolerances must be finite and nonnegative");return;
        }
        if(report_.input.assurance!=Assurance::numerical&&report_.input.assurance!=Assurance::validated) {
            report_.feasibility=CheckStatus::invalid_input;report_.objective=CheckStatus::invalid_input;
            diagnose(DiagnosticCode::invalid_input,"assurance","unknown trajectory verification assurance");return;
        }
        if(report_.verification.assurance==Assurance::validated) {
            report_.feasibility=CheckStatus::unsupported;report_.objective=CheckStatus::unsupported;
            diagnose(DiagnosticCode::unsupported,"assurance","validated trajectory verification is not implemented");return;
        }
        boundary();if(!shape_and_profile())return;
        const auto& p=*original_.description();const auto& w=report_.input.witness;
        const auto& initial=std::get<KnownInitial>(p.initial).point;
        for(std::size_t i=0;i<initial.size();++i)equal(indexed("initial",i),w.states[0][i],initial[i]);
        for(std::size_t stage=0;stage<w.states.size();++stage)membership(p.states[stage],w.states[stage],indexed("states",stage));
        const auto& controls=std::get<ContinuousDomain>(p.controls).stages;
        for(std::size_t stage=0;stage<w.controls.size();++stage) {
            membership(controls[stage],w.controls[stage],indexed("controls",stage));
            const auto data=std::get<model::DynamicsStage>(original_.model().stage({stage}));
            for(std::size_t row=0;row<w.states[stage].size();++row) {
                double sum=data.offset[row],scale=std::abs(sum);
                const auto add=[&](const numeric::MatrixView& matrix,std::span<const double> values) {
                    for(std::size_t col=0;col<values.size();++col) {
                        boundary();const auto term=product(matrix(row,col),values[col]);sum=number(sum+term);scale=number(scale+std::abs(term));
                    }
                };
                add(data.A,w.states[stage]);add(data.B,w.controls[stage]);
                if(p.external)add(data.E,std::get<KnownExternalSequence>(*p.external).stages[stage]);
                residual(indexed(indexed("dynamics",stage),row),std::abs(number(w.states[stage+1][row]-sum)),std::max(scale,std::abs(w.states[stage+1][row])));
            }
        }
        if(p.temporal) {
            // Canonical order is x0..xT,u0..u(T-1); no compiled program rows enter here.
            Vector joint;for(const auto& x:w.states)joint.insert(joint.end(),x.begin(),x.end());
            for(const auto& u:w.controls)joint.insert(joint.end(),u.begin(),u.end());
            const auto& a=p.temporal->joint_map;
            for(std::size_t row=0;row<a.rows;++row) {
                double sum=0,scale=0;
                for(auto j=a.row_offsets[row];j<a.row_offsets[row+1];++j) {
                    boundary();const auto term=product(a.values[j],joint[a.column_indices[j]]);sum=number(sum+term);scale=number(scale+std::abs(term));
                }
                const auto& bound=p.temporal->bounds[row];
                if(bound.lower)residual(indexed("temporal",row)+".lower",std::max(0.0,number(*bound.lower-sum)),std::max(scale,std::abs(*bound.lower)));
                if(bound.upper)residual(indexed("temporal",row)+".upper",std::max(0.0,number(sum-*bound.upper)),std::max(scale,std::abs(*bound.upper)));
            }
        }
        boundary();
        const auto evaluated=optimization::evaluate(original_.objective(),w.states.back());
        if(const auto* cost=std::get_if<double>(&evaluated)) {
            report_.recomputed_objective=*cost;
            report_.objective=residual("objective",std::abs(number(*cost-w.original_objective)),std::max(std::abs(*cost),std::abs(w.original_objective)),false)?
                CheckStatus::numerical_pass:CheckStatus::violation;
        } else stop(Termination::numerical_failure,"original objective evaluation failed");
        report_.feasibility=violated_?CheckStatus::violation:(unknown_?CheckStatus::unsupported:CheckStatus::numerical_pass);
    }
    void finish() {if(runner_)report_.membership_queries=runner_->records();}
};
}
TrajectoryReport verify_trajectory(const problem::ResolvedProblem& p,const TrajectoryRequest& input,
    const ExecutionContext& context,std::optional<registry::PreparedProvider<registry::LPPort>> provider) {
    TrajectoryReport report;report.problem=p.identity();report.input=input;
    report.verification=input.verification.value_or(VerificationRequest{context.numerical,input.assurance});
    report.input.verification=report.verification;
    report.input.assurance=report.verification.assurance;
    report.numerical=report.verification.numerical;
    Check check(p,context,report,std::move(provider));
    try {check.run();}catch(const Stopped&) {} // termination is separate from every mathematical scope
    check.finish();return report;
}
} // namespace csl::verification
