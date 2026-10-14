#include <csl/core/outcomes.hpp>
#include "detail.hpp"
#include <algorithm>
#include <cmath>
#include <limits>
#include <set>
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
