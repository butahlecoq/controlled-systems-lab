#pragma once

#include <csl/sets/data.hpp>

#include <cmath>
#include <limits>
#include <span>
#include <utility>

namespace csl::reachability::detail {

// The support callback returns conservative lower and upper activities of an
// outer set in the requested direction. False means the available enclosure
// could not certify containment; it is not evidence of a reachable violation.
template<class Support>
bool outer_set_inside(const sets::SetData& safe, std::size_t dimension, Support&& support) {
    const auto metadata = safe.metadata();
    if(metadata->set.dimension != dimension) return false;
    const auto representation = safe.representation();
    if(std::holds_alternative<sets::UniversalRepresentation>(representation)) return true;
    if(const auto* h = std::get_if<sets::HRepresentation>(&representation)) {
        if(h->inequalities.cols() != dimension || h->equalities.cols() != dimension) return false;
        for(std::size_t row = 0; row < h->inequalities.rows(); ++row) {
            Vector normal(dimension);
            for(std::size_t j = 0; j < dimension; ++j) normal[j] = h->inequalities(row, j);
            const auto activities = support(normal);
            if(!std::isfinite(activities.second) || activities.second > h->upper_bounds[row]) return false;
        }
        for(std::size_t row = 0; row < h->equalities.rows(); ++row) {
            Vector normal(dimension);
            for(std::size_t j = 0; j < dimension; ++j) normal[j] = h->equalities(row, j);
            const auto [lower, upper] = support(normal);
            const auto value = h->equality_values[row];
            if(!std::isfinite(lower) || !std::isfinite(upper) || lower != value || upper != value) return false;
        }
        return true;
    }
    if(const auto* singleton = std::get_if<sets::SingletonRepresentation>(&representation)) {
        for(std::size_t j = 0; j < dimension; ++j) {
            Vector normal(dimension, 0.0);
            normal[j] = 1.0;
            const auto [lower, upper] = support(normal);
            if(lower != singleton->point[j] || upper != singleton->point[j]) return false;
        }
        return true;
    }
    return false;
}

inline double outward_lower(double value) {
    return std::nextafter(value, -std::numeric_limits<double>::infinity());
}
inline double outward_upper(double value) {
    return std::nextafter(value, std::numeric_limits<double>::infinity());
}

} // namespace csl::reachability::detail
