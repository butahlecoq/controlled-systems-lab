#include <csl/core/outcomes.hpp>
#include "detail.hpp"
#include <algorithm>
#include <cmath>
#include <limits>
#include <set>
#include <type_traits>
#include <utility>

namespace csl {
namespace {
using contracts_detail::Overloaded;
using contracts_detail::matrix_matches;
template<class Subject>
Diagnostics check_outcome(const OutcomeClaim<Subject>& claim, const Subject& expected, Assurance assurance) {
    Diagnostics result;
    if (claim.subject != expected)
        result.push_back({DiagnosticCode::evidence_mismatch,"outcome.subject","Outcome claim does not belong to the expected problem/program"});
    if(const auto* proof=std::get_if<ExactFarkasEvidence>(&claim.support)) {
        if(claim.value!=MathematicalOutcome::infeasible)
            result.push_back({DiagnosticCode::invalid_claim,"outcome.support","Exact Farkas evidence supports only an infeasible outcome"});
        if constexpr(std::is_same_v<Subject,ProgramIdentity>) {
            if(proof->subject()!=expected)
                result.push_back({DiagnosticCode::evidence_mismatch,"outcome.support.subject","Exact Farkas evidence belongs to another generated program"});
        } else {
            if(proof->subject().problem!=expected)
                result.push_back({DiagnosticCode::evidence_mismatch,"outcome.support.problem","Exact Farkas evidence belongs to another source problem"});
        }
        return result;
    }
    if (assurance == Assurance::validated)
        result.push_back({DiagnosticCode::unsupported,"outcome.assurance","Outcome support is unestablished, numerical, symbolic provenance or an unchecked certificate, not validated evidence"});
    return result;
}
}
Diagnostics check_outcome_evidence(const ProgramOutcomeClaim& claim, const ProgramIdentity& expected, Assurance assurance) {
    return check_outcome(claim,expected,assurance);
}
Diagnostics check_outcome_evidence(const SynthesisOutcomeClaim& claim, const ProblemId& expected, Assurance assurance) {
    return check_outcome(claim,expected,assurance);
}
} // namespace csl
