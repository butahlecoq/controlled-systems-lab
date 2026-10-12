#include "report_runtime.hpp"
#include "ReportBuildInfo.hpp"
#include <bit>
#include <cmath>
#include <iomanip>
#include <locale>
#include <sstream>
namespace csl::reporting {
Clock::rep now() { return Clock::now().time_since_epoch().count(); }
std::string diagnostic_text(const Diagnostics& diagnostics) {
    std::string out;
    for(const auto& d:diagnostics) out+=d.field+": "+d.explanation+"\n";
    return out;
}
Rejected::Rejected(Diagnostics d):std::runtime_error(diagnostic_text(d)),diagnostics(std::move(d)) {}
bool close(double a, double b) { return std::isfinite(a) && std::isfinite(b) && std::abs(a-b)<=1e-8+1e-8*std::max(std::abs(a),std::abs(b)); }
bool passes(const ResidualMeasure& m, const ResidualContext& c) {
    return std::isfinite(m.violation) && std::isfinite(m.scale) && m.violation>=0 && m.scale>=0 &&
        m.violation<=c.absolute_tolerance+c.relative_tolerance*m.scale;
}
void observe(std::uint64_t& token, std::uint64_t value) { token ^= value; token *= UINT64_C(1099511628211); }
std::uint64_t observe(const ProgramOutcome& outcome) {
    std::uint64_t token=UINT64_C(14695981039346656037);
    observe(token,outcome.index());
    if (const auto* r=std::get_if<ProgramResult>(&outcome)) {
        observe(token,static_cast<std::uint64_t>(r->termination));
        observe(token,static_cast<std::uint64_t>(r->outcome.value));
        if (r->primal) for (double x:*r->primal) observe(token,std::bit_cast<std::uint64_t>(x));
        observe(token,r->residuals.primal.has_value()); observe(token,r->residuals.dual.has_value());
        observe(token,r->raw_diagnostics.size());
    }
    return token;
}
const char* outcome_name(MathematicalOutcome value) {
    switch(value) {
    case MathematicalOutcome::optimal:return "optimal";
    case MathematicalOutcome::infeasible:return "infeasible";
    case MathematicalOutcome::unbounded:return "unbounded";
    case MathematicalOutcome::infimum_not_attained:return "infimum_not_attained";
    case MathematicalOutcome::undetermined:return "undetermined";
    }
    throw std::logic_error("unknown outcome");
}
const char* termination_name(Termination value) {
    switch(value) {
    case Termination::completed:return "completed";
    case Termination::cancelled:return "cancelled";
    case Termination::resource_limit:return "resource_limit";
    case Termination::numerical_failure:return "numerical_failure";
    case Termination::operation_rejected:return "operation_rejected";
    case Termination::contract_rejected:return "contract_rejected";
    }
    throw std::logic_error("unknown termination");
}
std::string identity_json(const ProgramIdentity& id) { return "{\"problem\":"+json_string(id.problem.value)+",\"program\":"+json_string(id.program.value)+"}"; }
std::string numbers(const Vector& values) { return array(values,[](double x){return json_number(x);}); }
std::string optional_number(const std::optional<double>& value) { return value ? json_number(*value) : "null"; }
std::string measure(const ResidualMeasure& value) { return "{\"violation\":"+json_number(value.violation)+",\"scale\":"+json_number(value.scale)+"}"; }
std::string context(const ResidualContext& c) { return "{\"subject\":"+identity_json(c.subject)+",\"verifier\":{\"id\":"+json_string(c.verifier.id.value)+",\"version\":"+json_string(c.verifier.version)+"},\"absolute_tolerance\":"+json_number(c.absolute_tolerance)+",\"relative_tolerance\":"+json_number(c.relative_tolerance)+"}"; }
std::string primal_json(const std::optional<PrimalResiduals>& p) {
    return p ? "{\"context\":"+context(p->context)+",\"rows\":"+measure(p->rows)+",\"variables\":"+measure(p->variables)+"}" : "null";
}
std::string dual_json(const std::optional<DualResiduals>& d) {
    if (!d) return "null";
    const auto optional=[](const std::optional<ResidualMeasure>& m){return m ? measure(*m) : "null";};
    return "{\"context\":"+context(d->context)+",\"stationarity\":"+optional(d->stationarity)+",\"signs\":"+optional(d->signs)+",\"complementarity\":"+optional(d->complementarity)+"}";
}std::int64_t Interval::nanoseconds() const { return std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::duration(end-start)).count(); }

std::string json_string(const std::string& text) {
    constexpr char hex[]="0123456789abcdef";
    std::string out="\"";
    for (unsigned char c:text) {
        switch(c) {
        case '"':out+="\\\"";break; case '\\':out+="\\\\";break;
        case '\n':out+="\\n";break;case '\r':out+="\\r";break;case '\t':out+="\\t";break;
        default:if(c<32) {out+="\\u00";out+=hex[c>>4];out+=hex[c&15];} else out+=static_cast<char>(c);
        }
    }
    return out+'"';
}
std::string json_number(double value) {
    if (!std::isfinite(value)) throw std::invalid_argument("cannot serialize nonfinite binary64");
    std::ostringstream out;out.imbue(std::locale::classic());out<<std::setprecision(std::numeric_limits<double>::max_digits10)<<value;
    auto text=out.str(); if (text.find_first_of(".eE")==std::string::npos) text+=".0";return text;
}
std::string build_info_json() {
#ifdef NDEBUG
    constexpr bool ndebug=true;
#else
    constexpr bool ndebug=false;
#endif
    return "{\"source_commit\":"+json_string(build::source_commit)+",\"build_owner_sha256\":"+json_string(build::build_owner_sha256)+",\"compiler\":"+json_string(build::compiler)+",\"compiler_version\":"+json_string(build::compiler_version)+",\"generator\":"+json_string(build::generator)+",\"architecture\":"+json_string(build::architecture)+",\"configuration\":"+json_string(CSL_REPORT_CONFIG)+",\"cxx_standard\":20,\"ndebug\":"+(ndebug?"true":"false")+",\"configured_flags\":"+json_string(build::configured_flags)+",\"release_flags\":"+json_string(build::release_flags)+"}";
}
}
