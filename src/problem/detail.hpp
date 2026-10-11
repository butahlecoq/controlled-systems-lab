#pragma once

#include <csl/problem/domains.hpp>
#include <algorithm>
#include <cmath>
#include <utility>

namespace csl::problem::detail {
template<class... T> struct Visitor : T... { using T::operator()...; };
template<class... T> Visitor(T...) -> Visitor<T...>;

inline Diagnostic invalid(std::string field, std::string explanation) {
    return {DiagnosticCode::invalid_input,std::move(field),std::move(explanation)};
}
inline std::string indexed(const std::string& field, std::size_t index) {
    return field+"["+std::to_string(index)+"]";
}
inline bool finite(std::span<const double> point) {
    return std::all_of(point.begin(),point.end(),[](double x) { return std::isfinite(x); });
}
inline std::optional<Diagnostic> check_point(const Vector& point, std::size_t dimension,
                                            const std::string& field) {
    if (point.size()!=dimension) return invalid(field+".dimension","Point dimension must match the model port.");
    if (!finite(point)) return invalid(field+".point","Point coordinates must be finite.");
    return {};
}
inline std::optional<Diagnostic> check_dimension(std::size_t actual, std::size_t expected,
                                                const std::string& field) {
    if (actual!=expected) return invalid(field+".dimension","Set ambient dimension must match the model port.");
    return {};
}
inline std::optional<Diagnostic> check_set(const AdmissibleSet& set, std::size_t dimension,
                                          const std::string& field) {
    return std::visit(Visitor{
        [&](const EmptySet& value) { return check_dimension(value.dimension,dimension,field); },
        [&](const UniversalSet& value) { return check_dimension(value.dimension,dimension,field); },
        [&](const Singleton& value) { return check_point(value.point,dimension,field); },
        [&](const SetHandle& value) -> std::optional<Diagnostic> {
            auto imported=sets::from_handle(value);
            if (const auto* error=std::get_if<Diagnostic>(&imported))
                return Diagnostic{error->code,field+"."+error->field,error->explanation};
            return check_dimension(value.metadata.dimension,dimension,field);
        }
    },set);
}
inline std::optional<Diagnostic> check_sets(std::span<const AdmissibleSet> sets,
    std::size_t count, std::size_t dimension, const std::string& field) {
    if (sets.size()!=count) return invalid(field,"Set stage count must match the model horizon.");
    for (std::size_t i=0;i<sets.size();++i)
        if (auto error=check_set(sets[i],dimension,indexed(field,i))) return error;
    return {};
}
inline std::optional<Diagnostic> check_quantifier(SetQuantifier quantifier, const std::string& field) {
    switch (quantifier) {
    case SetQuantifier::existential:
    case SetQuantifier::universal: return {};
    case SetQuantifier::unspecified: break;
    }
    return invalid(field,"Declare an existential or universal quantifier explicitly.");
}
} // namespace csl::problem::detail
