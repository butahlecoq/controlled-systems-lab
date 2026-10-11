#include <csl/optimization/linear_program.hpp>
#include <algorithm>
#include <cmath>
namespace csl {
struct LinearProgram::Storage {
    ProgramIdentity identity;
    numeric::VectorView objective;
    double offset;
    numeric::MatrixView constraints;
    std::vector<Interval> variables, rows;
};
const ProgramIdentity& LinearProgram::identity() const noexcept { return storage_->identity; }
const numeric::VectorView& LinearProgram::objective() const noexcept { return storage_->objective; }
double LinearProgram::offset() const noexcept { return storage_->offset; }
const numeric::MatrixView& LinearProgram::constraints() const noexcept { return storage_->constraints; }
std::span<const Interval> LinearProgram::variables() const noexcept { return storage_->variables; }
std::span<const Interval> LinearProgram::rows() const noexcept { return storage_->rows; }
namespace optimization {
namespace {
Diagnostics error(std::string field, std::string message) {
    return {{DiagnosticCode::invalid_input,std::move(field),std::move(message)}};
}
bool valid_interval(const Interval& b) {
    return (!b.lower || std::isfinite(*b.lower)) && (!b.upper || std::isfinite(*b.upper)) &&
        (!b.lower || !b.upper || *b.lower <= *b.upper);
}
void accumulate(ResidualMeasure& measure, double value, const Interval& bound) {
    measure.scale=std::max(measure.scale,std::abs(value));
    if (bound.lower) {
        measure.scale=std::max(measure.scale,std::abs(*bound.lower));
        measure.violation=std::max(measure.violation,*bound.lower-value);
    }
    if (bound.upper) {
        measure.scale=std::max(measure.scale,std::abs(*bound.upper));
        measure.violation=std::max(measure.violation,value-*bound.upper);
    }
}
}
struct ProgramAccess {
    static LinearProgram create(const LinearProgramInput& input, numeric::VectorView objective, numeric::MatrixView matrix) {
        return LinearProgram{std::make_shared<const LinearProgram::Storage>(LinearProgram::Storage{
            input.identity,objective,input.offset,matrix,input.variables,input.rows})};
    }
};
LPDataResult<LinearProgram> make_linear_program(const LinearProgramInput& input) {
    if (input.identity.problem.value.empty() || input.identity.program.value.empty())
        return error("lp.identity","problem and program IDs must be nonempty");
    if (input.objective.size()!=input.constraints.cols || input.variables.size()!=input.constraints.cols ||
        input.rows.size()!=input.constraints.rows) return error("lp.shape","objective, bounds and CSR shapes disagree");
    if (!std::isfinite(input.offset)) return error("lp.offset","offset must be finite");
    for (const auto& b:input.variables) if (!valid_interval(b)) return error("lp.variables","invalid variable interval");
    for (const auto& b:input.rows) if (!valid_interval(b)) return error("lp.rows","invalid row interval");
    auto objective=numeric::snapshot_vector(input.objective);
    if (auto* d=std::get_if<Diagnostic>(&objective)) return Diagnostics{*d};
    auto matrix=numeric::snapshot(input.constraints);
    if (auto* d=std::get_if<Diagnostic>(&matrix)) return Diagnostics{*d};
    return ProgramAccess::create(input,std::get<numeric::VectorView>(objective),std::get<numeric::MatrixView>(matrix));
}
LPDataResult<PrimalEvaluation> evaluate_primal(const LinearProgram& p,std::span<const double> x,NumericalPolicy policy,const Verifier& verifier) {
    if (x.size()!=p.objective().size()) return error("lp.primal.shape","candidate dimension differs");
    if (!std::isfinite(policy.absolute_tolerance) || policy.absolute_tolerance<0 ||
        !std::isfinite(policy.relative_tolerance) || policy.relative_tolerance<0 ||
        verifier.id.value.empty() || verifier.version.empty()) return error("lp.residual.context","invalid check metadata");
    for (double value:x) if (!std::isfinite(value)) return error("lp.primal.values","candidate must be finite");
    PrimalEvaluation output{p.offset(),{{p.identity(),verifier,policy.absolute_tolerance,policy.relative_tolerance},{0,1},{0,1}}};
    for (std::size_t j=0;j<x.size();++j) {
        output.objective+=p.objective()[j]*x[j];
        accumulate(output.residuals.variables,x[j],p.variables()[j]);
    }
    const auto csr=std::get<numeric::CsrInput>(p.constraints().descriptor());
    for (std::size_t i=0;i<csr.rows;++i) {
        double activity=0;
        for (auto k=csr.row_offsets[i];k<csr.row_offsets[i+1];++k) activity+=csr.values[k]*x[csr.column_indices[k]];
        if (!std::isfinite(activity)) return error("lp.primal.arithmetic","nonfinite row activity");
        accumulate(output.residuals.rows,activity,p.rows()[i]);
    }
    if (!std::isfinite(output.objective) || !std::isfinite(output.residuals.rows.violation) ||
        !std::isfinite(output.residuals.variables.violation) ||
        !std::isfinite(policy.absolute_tolerance+policy.relative_tolerance*output.residuals.rows.scale) ||
        !std::isfinite(policy.absolute_tolerance+policy.relative_tolerance*output.residuals.variables.scale)) return error("lp.primal.arithmetic","nonfinite objective or residual");
    return output;
}
}}
