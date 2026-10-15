#include <csl/adapters/lp/highs.hpp>
#include <csl/optimization/lp_backend.hpp>
#include <csl/optimization/linear_infeasibility_certificate.hpp>
#include "../certificate_verification.hpp"
#include "../highs_session.hpp"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <limits>
#include <sstream>
#include <stdexcept>

namespace csl::adapters::lp {
namespace {
using namespace optimization;
constexpr const char* adapter_version = "1.0.0+highs.1.11.0";
constexpr const char* archive_hash = "2b44b074cf41439325ce4d0bbdac2d51379f56faf17ba15320a410d3c1f07275";
Diagnostics diagnostic(DiagnosticCode code, std::string field, std::string message) {
    return {{code,std::move(field),std::move(message)}};
}
Diagnostics admission(const LinearProgram& p) {
    const auto max = static_cast<std::size_t>(kHighsIInf);
    const auto csr = std::get<numeric::CsrInput>(p.constraints().descriptor());
    if (csr.rows > max || csr.cols > max || csr.rows > max-csr.cols || csr.values.size() > max)
        return diagnostic(DiagnosticCode::unsupported,"highs.dimensions","Native integer width exceeded");
    for (const double a : csr.values)
        if (a != 0 && std::abs(a) <= 1e-12)
            return diagnostic(DiagnosticCode::unsupported,"highs.matrix","Nonzero coefficient at or below native removal threshold 1e-12");
    return {};
}
Diagnostics admission(const ExecutionContext& c) {
    const auto a = c.numerical.absolute_tolerance, r = c.numerical.relative_tolerance;
    if (!std::isfinite(a) || !std::isfinite(r) || a < 0 || r < 0)
        return diagnostic(DiagnosticCode::invalid_input,"numerical","Finite nonnegative tolerances required");
    if (a < 1e-10)
        return diagnostic(DiagnosticCode::unsupported,"numerical.absolute_tolerance","Native feasibility tolerance minimum is 1e-10");
    if (c.resources) {
        auto errors = check_resources(*c.resources);
        if (!errors.empty()) return errors;
        if (c.resources->memory_bytes)
            return diagnostic(DiagnosticCode::unsupported,"resources.memory_bytes","Native memory admission is unavailable");
    }
    return {};
}
ProgramResult result_for(const LinearProgram& p) {
    return {Termination::numerical_failure,{p.identity(),MathematicalOutcome::undetermined,Unestablished{},
        {"HiGHS binary64 report; no independent mathematical outcome certificate"}}, {}, {}, {}, {}};
}
using highs_detail::CallbackState;
void require_option(HighsStatus status) {
    if (status == HighsStatus::kError) throw std::runtime_error("Pinned HiGHS option rejected");
}
HighsLp translate(const LinearProgram& p) {
    HighsLp lp;
    lp.num_col_ = static_cast<HighsInt>(p.variables().size());
    lp.num_row_ = static_cast<HighsInt>(p.rows().size());
    lp.col_cost_.assign(p.objective().values().begin(),p.objective().values().end());
    lp.offset_ = p.offset();
    lp.sense_ = ObjSense::kMinimize;
    for (const auto& v : p.variables()) {
        lp.col_lower_.push_back(v.lower.value_or(-kHighsInf));
        lp.col_upper_.push_back(v.upper.value_or(kHighsInf));
    }
    for (const auto& row : p.rows()) {
        lp.row_lower_.push_back(row.lower.value_or(-kHighsInf));
        lp.row_upper_.push_back(row.upper.value_or(kHighsInf));
    }
    const auto csr = std::get<numeric::CsrInput>(p.constraints().descriptor());
    lp.a_matrix_.num_row_ = lp.num_row_;
    lp.a_matrix_.num_col_ = lp.num_col_;
    lp.a_matrix_.format_ = MatrixFormat::kRowwise;
    lp.a_matrix_.start_.clear();
    for (const auto index : csr.row_offsets) lp.a_matrix_.start_.push_back(static_cast<HighsInt>(index));
    for (const auto index : csr.column_indices) lp.a_matrix_.index_.push_back(static_cast<HighsInt>(index));
    lp.a_matrix_.value_.assign(csr.values.begin(),csr.values.end());
    return lp;
}
bool finite(const std::vector<double>& values, std::size_t size) {
    return values.size() == size && std::all_of(values.begin(),values.end(),[](double v){return std::isfinite(v);});
}
bool split(const std::vector<double>& signed_dual,std::span<const Interval> intervals,Vector& lower,Vector& upper) {
    if (!finite(signed_dual,intervals.size())) return false;
    for (std::size_t i=0;i<intervals.size();++i) {
        const auto& b = intervals[i];
        const double d = signed_dual[i];
        if (b.lower && b.upper) { lower.push_back(std::max(d,0.0)); upper.push_back(std::max(-d,0.0)); }
        else if (b.lower) { lower.push_back(d); upper.push_back(0); }
        else if (b.upper) { lower.push_back(0); upper.push_back(-d); }
        else { if (d != 0) return false; lower.push_back(0); upper.push_back(0); }
    }
    return true;
}
std::optional<ExactFarkasEvidence> exact_farkas_from_ray(const LinearProgram& p,
    std::span<const double> signed_ray) {
    const auto csr=std::get<numeric::CsrInput>(p.constraints().descriptor());
    for(const bool reverse:{false,true}) {
        std::vector<double> signed_dual(signed_ray.begin(),signed_ray.end());
        if(reverse) for(auto& value:signed_dual)value=-value;
        LinearInfeasibilityCertificate certificate{p.identity(),{},{},{},{}};
        if(!split(signed_dual,p.rows(),certificate.row_lower,certificate.row_upper))continue;
        const auto n=p.variables().size();certificate.variable_lower.assign(n,0);certificate.variable_upper.assign(n,0);
        Vector residual(n,0);
        for(std::size_t i=0;i<p.rows().size();++i)
            for(auto k=csr.row_offsets[i];k<csr.row_offsets[i+1];++k) {
                const auto j=csr.column_indices[k];
                residual[j]+=csr.values[k]*(certificate.row_upper[i]-certificate.row_lower[i]);
            }
        bool representable=true;
        for(std::size_t j=0;j<n;++j) {
            if(!std::isfinite(residual[j])) {representable=false;break;}
            if(residual[j]>0) {
                if(!p.variables()[j].lower) {representable=false;break;}
                certificate.variable_lower[j]=residual[j];
            } else if(residual[j]<0) {
                if(!p.variables()[j].upper) {representable=false;break;}
                certificate.variable_upper[j]=-residual[j];
            }
        }
        if(!representable)continue;
        auto verified=verify_linear_infeasibility_certificate(p,certificate);
        if(auto* evidence=std::get_if<ExactFarkasEvidence>(&verified))return *evidence;
    }
    return std::nullopt;
}
void classify(ProgramResult& r,HighsStatus api,HighsModelStatus model,const CallbackState& state) {
    // A recognized resource model status can accompany kError (notably memory
    // exhaustion). Preserve termination, but never trust its native solution.
    switch (model) {
    case HighsModelStatus::kTimeLimit:
    case HighsModelStatus::kIterationLimit:
    case HighsModelStatus::kMemoryLimit:
    case HighsModelStatus::kObjectiveBound:
    case HighsModelStatus::kObjectiveTarget:
    case HighsModelStatus::kSolutionLimit:
        r.termination = Termination::resource_limit; return;
    case HighsModelStatus::kInterrupt:
        r.termination = state.stop.value_or(Termination::numerical_failure); return;
    default: break;
    }
    if (api == HighsStatus::kError) return;
    switch (model) {
    case HighsModelStatus::kOptimal:
        r.termination = Termination::completed; r.outcome.value = MathematicalOutcome::optimal; break;
    case HighsModelStatus::kInfeasible:
        r.termination = Termination::completed; r.outcome.value = MathematicalOutcome::infeasible; break;
    case HighsModelStatus::kUnbounded:
        r.termination = Termination::completed; r.outcome.value = MathematicalOutcome::unbounded; break;
    case HighsModelStatus::kUnboundedOrInfeasible:
        r.termination = Termination::completed; break;
    case HighsModelStatus::kNotset: case HighsModelStatus::kLoadError:
    case HighsModelStatus::kModelError: case HighsModelStatus::kPresolveError:
    case HighsModelStatus::kSolveError: case HighsModelStatus::kPostsolveError:
    case HighsModelStatus::kModelEmpty: case HighsModelStatus::kUnknown:
        break;
    default: break; // Resource/interrupt cases returned above.
    }
}
class HighsLPWorkspace final : public LPWorkspace {
    HighsLPOptions options_;
    std::unique_ptr<Highs> native_;
    std::optional<LinearProgram> loaded_;
    ProgramOutcome solve_native(const LinearProgram& p,const ExecutionContext& c) {
        if (auto d = admission(p); !d.empty()) return Unsupported{std::move(d)};
        if (auto d = admission(c); !d.empty()) return Unsupported{std::move(d)};
        auto result = result_for(p);
        std::ostringstream raw;
        raw << std::setprecision(17) << "adapter.version=" << adapter_version
            << "\nnative.version=" << highsVersion() << "\nnative.githash=" << highsGithash()
            << "\nnative.archive_sha256=" << archive_hash
            << "\nnative.downstream.hvectorbase_sha256=" << CSL_HIGHS_PATCHED_SOURCE_SHA256
            << "\nprogram.problem=" << p.identity().problem.value << "\nprogram.id=" << p.identity().program.value
            << "\noptions.solver=simplex\noptions.presolve=off\noptions.parallel=off\noptions.threads=1"
            << "\noptions.random_seed=0\noptions.allow_unbounded_or_infeasible=false\noptions.log_to_console=true\nlogging.destination=callback"
            << "\noptions.absolute_tolerance=" << c.numerical.absolute_tolerance
            << "\nresidual.relative_tolerance=" << c.numerical.relative_tolerance
            << "\noptions.small_matrix_value=1e-12\noptions.infinite_bound=inf\noptions.infinite_cost=inf\noptions.large_matrix_value=inf"
            << "\noptions.iteration_limit=" << options_.simplex_iteration_limit.value_or(static_cast<std::size_t>(kHighsIInf));
        CallbackState state{c,{}, {}};
        state.poll();
        if (state.stop) {
            result.termination = *state.stop;
            raw << "\nnative_run=false\nstop=" << (*state.stop == Termination::cancelled ? "cancelled" : "deadline")
                << "\nnative.info=unavailable";
            result.raw_diagnostics = raw.str(); return result;
        }
        // HiGHS reports ModelEmpty for zero columns without checking constant
        // rows. Evaluate these exact comparisons explicitly in original space.
        if (p.variables().empty()) {
            bool feasible = true;
            for (const auto& row : p.rows())
                feasible = feasible && (!row.lower || *row.lower <= 0) && (!row.upper || *row.upper >= 0);
            result.termination = Termination::completed;
            result.outcome.value = feasible ? MathematicalOutcome::optimal : MathematicalOutcome::infeasible;
            if (feasible) {
                result.primal = Vector{};
                auto evaluation = evaluate_primal(p,*result.primal,c.numerical,{{"csl.lp.highs.primal"},"1"});
                if (const auto* e = std::get_if<PrimalEvaluation>(&evaluation)) result.residuals.primal = e->residuals;
                else { result = result_for(p); raw << "\nwrapper.error=nonfinite primal evaluation"; }
            }
            raw << "\nnative_run=false\nwrapper.decision=constant_rows\nnative.info=unavailable";
            result.raw_diagnostics = raw.str(); return result;
        }
        if (!native_) native_ = std::make_unique<Highs>();
        auto& h = *native_;
        highs_detail::CallbackGuard guard(h,state,require_option);
        highs_detail::configure_common(h,require_option);
        require_option(h.setOptionValue("solver","simplex"));
        require_option(h.setOptionValue("primal_feasibility_tolerance",c.numerical.absolute_tolerance));
        require_option(h.setOptionValue("dual_feasibility_tolerance",c.numerical.absolute_tolerance));
        require_option(h.setOptionValue("simplex_iteration_limit",static_cast<HighsInt>(options_.simplex_iteration_limit.value_or(static_cast<std::size_t>(kHighsIInf)))));
        h.zeroAllClocks();
        const double remaining=highs_detail::deadline(h,c,require_option);
        raw << "\noptions.time_limit=" << remaining;
        const bool reused = loaded_ && loaded_->identity() == p.identity();
        raw << "\nmodel.reused=" << (reused ? "true" : "false");
        if (!reused) {
            loaded_.reset();
            const auto status = h.passModel(translate(p));
            raw << "\nnative.load_status=" << static_cast<int>(status);
            if (status == HighsStatus::kError) {
                raw << "\nnative_run=false\nnative.info=unavailable\nnative.log:\n" << state.log;
                result.raw_diagnostics = raw.str(); return result;
            }
            loaded_ = p;
        }
        state.poll();
        if (state.stop) {
            result.termination = *state.stop;
            raw << "\nnative_run=false\nstop=" << (*state.stop == Termination::cancelled ? "cancelled" : "deadline");
            result.raw_diagnostics = raw.str(); return result;
        }
        const auto api = h.run();
        const auto model = h.getModelStatus();
        classify(result,api,model,state);
        raw << "\nnative_run=true\nnative.call_status=" << static_cast<int>(api)
            << "\nnative.call_status_name=" << highsStatusToString(api)
            << "\nnative.model_status=" << static_cast<int>(model)
            << "\nnative.model_status_name=" << h.modelStatusToString(model)
            << "\nstop=" << (state.stop ? (*state.stop == Termination::cancelled ? "cancelled" : "deadline") : "none");
        const bool trusted = api != HighsStatus::kError && result.termination != Termination::numerical_failure;
        const auto& info = h.getInfo();
        if (trusted && info.valid) {
            raw << "\nnative.info=available\nnative.objective=" << info.objective_function_value
                << "\nnative.primal_infeasibility=" << info.max_primal_infeasibility
                << "\nnative.dual_infeasibility=" << info.max_dual_infeasibility
                << "\nnative.simplex_iterations=" << info.simplex_iteration_count;
        } else raw << "\nnative.info=unavailable";
        const auto& solution = h.getSolution();
        if (trusted && solution.value_valid) {
            if (finite(solution.col_value,p.variables().size())) {
                auto evaluated = evaluate_primal(p,solution.col_value,c.numerical,{{"csl.lp.highs.primal"},"1"});
                if (const auto* e = std::get_if<PrimalEvaluation>(&evaluated)) {
                    result.primal = solution.col_value;
                    result.residuals.primal = e->residuals;
                    raw << "\noriginal.objective=" << e->objective;
                } else { result = result_for(p); raw << "\nwrapper.error=nonfinite primal evaluation"; }
            } else { result = result_for(p); raw << "\nwrapper.error=invalid native primal"; }
        }
        if (trusted && result.termination != Termination::numerical_failure && solution.dual_valid) {
            DualMultipliers multipliers;
            if (split(solution.row_dual,p.rows(),multipliers.row_lower,multipliers.row_upper) &&
                split(solution.col_dual,p.variables(),multipliers.variable_lower,multipliers.variable_upper)) {
                auto evaluated = evaluate_dual(p,multipliers,c.numerical,{{"csl.lp.highs.dual"},"1"});
                if (const auto* e = std::get_if<DualEvaluation>(&evaluated)) result.residuals.dual = e->residuals;
                else raw << "\ndual.unavailable=nonfinite neutral evaluation";
            } else raw << "\ndual.unavailable=invalid dimensions, nonfinite values or nonzero free-interval multiplier";
        }
        raw << "\ncomplementarity=unavailable\nbasis=unavailable";
        if(result.termination==Termination::completed&&result.outcome.value==MathematicalOutcome::infeasible) {
            const auto extraction_start=std::chrono::steady_clock::now();
            state.poll();
            if(state.stop) {
                result.termination=*state.stop;result.outcome.value=MathematicalOutcome::undetermined;
                raw << "\ncertificate.extraction=stopped_before_ray";
            } else {
                const auto certificate_remaining=highs_detail::deadline(h,c,require_option);
                if(certificate_remaining<=0)state.poll();
                if(state.stop) {
                    result.termination=*state.stop;result.outcome.value=MathematicalOutcome::undetermined;
                    raw << "\ncertificate.extraction=stopped_before_ray";
                } else {
                    std::vector<double> ray(p.rows().size());bool has_ray=false;
                    const auto ray_status=h.getDualRay(has_ray,ray.data());
                    state.poll();
                    if(state.stop) {
                        result.termination=*state.stop;result.outcome.value=MathematicalOutcome::undetermined;
                        raw << "\ncertificate.extraction=stopped_during_ray";
                    } else if(ray_status==HighsStatus::kOk&&has_ray) {
                        const auto verification=highs_detail::verify_then_poll(
                            [&] { return exact_farkas_from_ray(p,ray); },
                            [&] { state.poll();return state.stop; });
                        if(verification.stop) {
                            result.termination=*verification.stop;result.outcome.value=MathematicalOutcome::undetermined;
                            result.outcome.support=Unestablished{};
                            raw << "\ncertificate.extraction=stopped_during_verification";
                        } else if(verification.evidence) {
                            result.outcome.support=*verification.evidence;
                            raw << "\ncertificate.extraction=exact_farkas_verified";
                        } else raw << "\ncertificate.extraction=ray_rejected_by_exact_verifier";
                    } else raw << "\ncertificate.extraction=ray_unavailable";
                }
            }
            const auto elapsed=std::chrono::duration<double>(std::chrono::steady_clock::now()-extraction_start).count();
            raw << "\ncertificate.extraction_seconds=" << std::setprecision(17) << elapsed;
        } else raw << "\ncertificate.extraction=not_requested";
        raw << "\ncertificates=" << (std::holds_alternative<ExactFarkasEvidence>(result.outcome.support)?"exact_farkas":"unavailable")
            << "\nnative.log:\n" << state.log;
        result.raw_diagnostics = raw.str();
        return result;
    }
    ProgramOutcome do_solve(const LinearProgram& p,const ExecutionContext& c) override {
        try { return solve_native(p,c); }
        catch (...) { loaded_.reset(); native_.reset(); throw; }
    }
public:
    explicit HighsLPWorkspace(HighsLPOptions options) : options_(options) {}
};
class HighsLPBackend final : public LPBackend {
    HighsLPOptions options_;
public:
    explicit HighsLPBackend(HighsLPOptions options) : options_(options) {}
    BackendCapabilities capabilities() const override { return {{"csl.lp.highs"},adapter_version,true,false,false}; }
    std::unique_ptr<LPWorkspace> make_workspace() const override { return std::make_unique<HighsLPWorkspace>(options_); }
};
} // namespace
HighsLPRegistrationResult make_highs_registration(HighsLPOptions options) {
    if (options.simplex_iteration_limit && *options.simplex_iteration_limit > static_cast<std::size_t>(kHighsIInf))
        return diagnostic(DiagnosticCode::unsupported,"highs.simplex_iteration_limit","Native integer width exceeded");
    auto backend = std::make_shared<const HighsLPBackend>(options);
    return registry::Registration<registry::LPPort>{
        {{"csl.lp.highs"},adapter_version},
        [](const LinearProgram& p,const registry::Requirements& request) -> registry::Capability {
            if (request.scalar != registry::Scalar::binary64)
                return diagnostic(DiagnosticCode::unsupported,"scalar","HiGHS adapter requires binary64");
            if (auto d = admission(p); !d.empty()) return d;
            return registry::Offer{{{"csl.program-result.v1"},Assurance::numerical,{},{},registry::Completeness::unestablished}};
        },
        [backend=std::move(backend)](const LinearProgram&) { return backend->make_workspace(); }, {}};
}
} // namespace csl::adapters::lp
