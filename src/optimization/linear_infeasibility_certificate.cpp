#include <csl/optimization/linear_infeasibility_certificate.hpp>
#include "exact_dyadic_sum.hpp"
#include <cmath>
#include <vector>

namespace csl::optimization {
ExactFarkasEvidence FarkasEvidenceFactory::create(LinearInfeasibilityCertificate certificate) {
    return ExactFarkasEvidence(std::move(certificate));
}
namespace {
Diagnostics failure(DiagnosticCode code,std::string field,std::string explanation) {
    return {{code,std::move(field),std::move(explanation)}};
}
Diagnostics invalid(std::string field,std::string explanation) {
    return failure(DiagnosticCode::invalid_claim,std::move(field),std::move(explanation));
}

bool finite_nonnegative(std::span<const double> values) {
    for(double value:values)if(!std::isfinite(value)||value<0)return false;
    return true;
}
}

std::variant<ExactFarkasEvidence,Diagnostics> verify_linear_infeasibility_certificate(
    const LinearProgram& program,const LinearInfeasibilityCertificate& certificate) {
    if(certificate.subject!=program.identity())
        return failure(DiagnosticCode::evidence_mismatch,"lp.infeasibility.subject",
            "Certificate belongs to a different immutable linear program.");
    const auto row_count=program.rows().size(),variable_count=program.variables().size();
    if(certificate.row_lower.size()!=row_count||certificate.row_upper.size()!=row_count||
       certificate.variable_lower.size()!=variable_count||certificate.variable_upper.size()!=variable_count)
        return invalid("lp.infeasibility.shape","Farkas multiplier dimensions must match every row and variable endpoint.");
    if(!finite_nonnegative(certificate.row_lower)||!finite_nonnegative(certificate.row_upper)||
       !finite_nonnegative(certificate.variable_lower)||!finite_nonnegative(certificate.variable_upper))
        return invalid("lp.infeasibility.signs","Farkas multipliers must be finite and nonnegative.");
    for(std::size_t i=0;i<row_count;++i)
        if((!program.rows()[i].lower&&certificate.row_lower[i]!=0)||
           (!program.rows()[i].upper&&certificate.row_upper[i]!=0))
            return invalid("lp.infeasibility.absent_row_bound","An absent row endpoint must have zero multiplier.");
    for(std::size_t j=0;j<variable_count;++j)
        if((!program.variables()[j].lower&&certificate.variable_lower[j]!=0)||
           (!program.variables()[j].upper&&certificate.variable_upper[j]!=0))
            return invalid("lp.infeasibility.absent_variable_bound","An absent variable endpoint must have zero multiplier.");

    const auto csr=std::get<numeric::CsrInput>(program.constraints().descriptor());
    std::vector<detail::ExactDyadicSum> stationarity(variable_count);
    for(std::size_t i=0;i<row_count;++i)
        for(auto k=csr.row_offsets[i];k<csr.row_offsets[i+1];++k) {
            const auto j=csr.column_indices[k];
            stationarity[j].add_product(csr.values[k],certificate.row_lower[i],true);
            stationarity[j].add_product(csr.values[k],certificate.row_upper[i]);
        }
    for(std::size_t j=0;j<variable_count;++j) {
        stationarity[j].add_product(1.0,certificate.variable_lower[j],true);
        stationarity[j].add_product(1.0,certificate.variable_upper[j]);
        if(!stationarity[j].zero())
            return invalid("lp.infeasibility.stationarity","Exact dyadic Farkas stationarity is nonzero.");
    }

    detail::ExactDyadicSum contradiction;
    for(std::size_t i=0;i<row_count;++i) {
        if(program.rows()[i].lower)
            contradiction.add_product(certificate.row_lower[i],*program.rows()[i].lower);
        if(program.rows()[i].upper)
            contradiction.add_product(certificate.row_upper[i],*program.rows()[i].upper,true);
    }
    for(std::size_t j=0;j<variable_count;++j) {
        if(program.variables()[j].lower)
            contradiction.add_product(certificate.variable_lower[j],*program.variables()[j].lower);
        if(program.variables()[j].upper)
            contradiction.add_product(certificate.variable_upper[j],*program.variables()[j].upper,true);
    }
    if(!contradiction.positive())
        return invalid("lp.infeasibility.contradiction","Exact dyadic contradiction constant must be strictly positive.");
    return FarkasEvidenceFactory::create(certificate);
}
} // namespace csl::optimization
