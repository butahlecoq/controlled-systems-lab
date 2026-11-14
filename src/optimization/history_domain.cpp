#include <csl/optimization/history_domain.hpp>
#include "../geometry/independent_directions.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <string>
#include <type_traits>
#include <utility>

namespace csl::optimization {
namespace {
Diagnostic invalid(std::string field, std::string explanation) {
    return {DiagnosticCode::invalid_input, std::move(field), std::move(explanation)};
}

bool finite(std::span<const double> values) {
    return std::all_of(values.begin(), values.end(), [](double v) { return std::isfinite(v); });
}

bool same_matrix(const Matrix &left, const Matrix &right) {
    return left.rows == right.rows && left.cols == right.cols &&
           left.values == right.values;
}

bool same_matrix(const numeric::MatrixView &left, const numeric::MatrixView &right) {
    if (left.rows() != right.rows() || left.cols() != right.cols())
        return false;
    for (std::size_t row = 0; row < left.rows(); ++row)
        for (std::size_t column = 0; column < left.cols(); ++column)
            if (left(row, column) != right(row, column))
                return false;
    return true;
}

bool same_vector(const numeric::VectorView &left, const numeric::VectorView &right) {
    return std::equal(left.values().begin(), left.values().end(), right.values().begin(),
                      right.values().end());
}

bool same_set_payload(const sets::SetData &left, const sets::SetData &right) {
    const auto left_metadata = left.metadata();
    const auto right_metadata = right.metadata();
    if (left_metadata->id != right_metadata->id ||
        left_metadata->set.dimension != right_metadata->set.dimension ||
        left_metadata->coordinate_labels != right_metadata->coordinate_labels)
        return false;
    const auto left_representation = left.representation();
    const auto right_representation = right.representation();
    if (left_representation.index() != right_representation.index())
        return false;
    if (const auto *left_h = std::get_if<sets::HRepresentation>(&left_representation)) {
        const auto &right_h = std::get<sets::HRepresentation>(right_representation);
        return same_matrix(left_h->inequalities, right_h.inequalities) &&
               same_vector(left_h->upper_bounds, right_h.upper_bounds) &&
               same_matrix(left_h->equalities, right_h.equalities) &&
               same_vector(left_h->equality_values, right_h.equality_values);
    }
    if (const auto *left_v = std::get_if<sets::VRepresentation>(&left_representation)) {
        const auto &right_v = std::get<sets::VRepresentation>(right_representation);
        return same_matrix(left_v->vertices, right_v.vertices) &&
               same_matrix(left_v->rays, right_v.rays);
    }
    return false;
}

bool same_membership_payload(const HistoryMembershipShape &left,
                             const HistoryMembershipShape &right) {
    return std::visit(
        [&](const auto &left_shape) {
            using T = std::decay_t<decltype(left_shape)>;
            const auto *right_shape = std::get_if<T>(&right);
            if (!right_shape)
                return false;
            if constexpr (std::is_same_v<T, HistoryHMembership> ||
                          std::is_same_v<T, HistoryVSimplexMembership>) {
                return same_set_payload(left_shape.selected, right_shape->selected);
            } else if constexpr (std::is_same_v<T, HistoryAxisBoxMembership>) {
                return left_shape.center == right_shape->center &&
                       left_shape.radii == right_shape->radii;
            } else if constexpr (std::is_same_v<T, HistoryZonotopeMembership>) {
                return left_shape.center == right_shape->center &&
                       same_matrix(left_shape.generators, right_shape->generators);
            } else if constexpr (std::is_same_v<T, HistoryParallelotopeMembership>) {
                return left_shape.center == right_shape->center &&
                       same_matrix(left_shape.frame, right_shape->frame) &&
                       left_shape.lower == right_shape->lower &&
                       left_shape.upper == right_shape->upper;
            } else {
                return left_shape.selected.center == right_shape->selected.center &&
                       same_matrix(left_shape.selected.factor, right_shape->selected.factor);
            }
        },
        left);
}

bool shape(const Matrix &matrix, std::size_t rows) {
    return matrix.rows == rows &&
           (!matrix.cols || matrix.rows <= std::numeric_limits<std::size_t>::max() / matrix.cols) &&
           matrix.values.size() == matrix.rows * matrix.cols && finite(matrix.values);
}

bool valid_relation(SetRelation relation) {
    switch (relation) {
    case SetRelation::equivalent:
    case SetRelation::inner:
    case SetRelation::outer:
    case SetRelation::heuristic:
        return true;
    }
    return false;
}

bool valid_family(HistorySetFamily family) {
    switch (family) {
    case HistorySetFamily::polytope:
    case HistorySetFamily::box:
    case HistorySetFamily::zonotope:
    case HistorySetFamily::parallelotope:
    case HistorySetFamily::ellipsoid:
        return true;
    }
    return false;
}

bool labels_match(const sets::Metadata &original, const sets::Metadata &selected, std::size_t stage,
                  std::size_t state_dimension) {
    if (original.coordinate_labels.empty() || selected.coordinate_labels.empty())
        return true;
    const auto first = stage * state_dimension;
    if (first > original.coordinate_labels.size() ||
        state_dimension > original.coordinate_labels.size() - first ||
        selected.coordinate_labels.size() != state_dimension)
        return false;
    return std::equal(selected.coordinate_labels.begin(), selected.coordinate_labels.end(),
                      original.coordinate_labels.begin() + static_cast<std::ptrdiff_t>(first));
}

bool within(double violation, double scale, NumericalPolicy policy) {
    if (!std::isfinite(violation) || !std::isfinite(scale))
        return false;
    const double limit = policy.absolute_tolerance + policy.relative_tolerance * scale;
    return std::isfinite(limit) && violation <= limit;
}

bool reconstruct(std::span<const double> state, std::span<const double> center,
                 const Matrix &factor, std::span<const double> coefficients,
                 NumericalPolicy policy) {
    for (std::size_t row = 0; row < factor.rows; ++row) {
        double value = center[row];
        double scale = std::max({1.0, std::abs(state[row]), std::abs(center[row])});
        for (std::size_t col = 0; col < factor.cols; ++col) {
            const double term = factor.values[row * factor.cols + col] * coefficients[col];
            value += term;
            scale += std::abs(term);
        }
        if (!std::isfinite(value) || !within(std::abs(value - state[row]), scale, policy))
            return false;
    }
    return true;
}

bool h_contains(const sets::HRepresentation &h, std::span<const double> state,
                NumericalPolicy policy) {
    const auto rows_match = [&](const numeric::MatrixView &matrix, const numeric::VectorView &rhs,
                                bool equality) {
        for (std::size_t row = 0; row < matrix.rows(); ++row) {
            double value = 0.0;
            double scale = std::max(1.0, std::abs(rhs[row]));
            for (std::size_t col = 0; col < matrix.cols(); ++col) {
                const double term = matrix(row, col) * state[col];
                value += term;
                scale += std::abs(term);
            }
            const double residual = value - rhs[row];
            if (!std::isfinite(value) ||
                !within(equality ? std::abs(residual) : std::max(0.0, residual), scale, policy))
                return false;
        }
        return true;
    };
    return rows_match(h.inequalities, h.upper_bounds, false) &&
           rows_match(h.equalities, h.equality_values, true);
}
} // namespace

Diagnostics check_history_domain_memberships(const HistoryDomain &domain) {
    Diagnostics errors;
    const auto &coordinates = domain.original.coordinates;
    const auto state_dimension = coordinates.dimensions.state;
    const auto max = std::numeric_limits<std::size_t>::max();
    const auto control_dimension = coordinates.dimensions.control;
    if (!state_dimension || !control_dimension || !coordinates.horizon ||
        coordinates.dimensions.external || coordinates.horizon == max ||
        state_dimension > max / (coordinates.horizon + 1) ||
        control_dimension > max / coordinates.horizon)
        return {invalid("history.memberships.coordinates", "Invalid state dimensions or horizon.")};
    const auto state_count = state_dimension * (coordinates.horizon + 1);
    const auto control_count = control_dimension * coordinates.horizon;
    if (state_count > max - control_count ||
        domain.original.relation.metadata()->set.dimension != state_count + control_count)
        return {invalid("history.memberships.coordinates",
                        "Original full-history dimension does not match its coordinates.")};
    const auto original_metadata = domain.original.relation.metadata();
    for (std::size_t i = 0; i < domain.memberships.size(); ++i) {
        const auto &member = domain.memberships[i];
        const auto field = "history.memberships[" + std::to_string(i) + "]";
        if (member.stage.value > coordinates.horizon || member.origin.reference.value.empty() ||
            member.origin.selected.value.empty() || domain.state_frame.empty() ||
            member.origin.coordinate_frame != domain.state_frame ||
            member.origin.canonical_state_indices.size() != state_dimension ||
            !valid_family(member.origin.selected_family) ||
            !valid_relation(member.origin.relation)) {
            errors.push_back(invalid(
                field,
                "Membership needs a valid stage, family, relation, set identities, and coordinate frame."));
            continue;
        }
        bool state_indices_match = true;
        for (std::size_t coordinate = 0; coordinate < state_dimension; ++coordinate)
            state_indices_match =
                state_indices_match && member.origin.canonical_state_indices[coordinate] ==
                                           member.stage.value * state_dimension + coordinate;
        if (!state_indices_match) {
            errors.push_back(invalid(
                field, "Membership coordinates do not match the ordered canonical state block."));
            continue;
        }
        const auto check_set = [&](const sets::SetData &geometry, const SetId &expected,
                                   bool h_form) {
            const auto metadata = geometry.metadata();
            if (metadata->id != expected || metadata->set.dimension != state_dimension ||
                !labels_match(*original_metadata, *metadata, member.stage.value, state_dimension))
                return false;
            const auto representation = geometry.representation();
            if (h_form)
                return std::holds_alternative<sets::HRepresentation>(representation);
            const auto *v = std::get_if<sets::VRepresentation>(&representation);
            return v && v->vertices.rows() != 0 && v->rays.rows() == 0;
        };
        const auto valid_geometry = [&](const HistoryMembershipShape &geometry,
                                        const SetId &expected, HistorySetFamily family) {
            return std::visit(
                [&](const auto &item) {
                    using T = std::decay_t<decltype(item)>;
                    if constexpr (std::is_same_v<T, HistoryHMembership>) {
                        return family == HistorySetFamily::polytope &&
                               check_set(item.selected, expected, true);
                    } else if constexpr (std::is_same_v<T, HistoryVSimplexMembership>) {
                        return family == HistorySetFamily::polytope &&
                               check_set(item.selected, expected, false);
                    } else if constexpr (std::is_same_v<T, HistoryAxisBoxMembership>) {
                        return family == HistorySetFamily::box &&
                               item.center.size() == state_dimension && finite(item.center) &&
                               item.radii.size() == state_dimension && finite(item.radii) &&
                               std::all_of(item.radii.begin(), item.radii.end(),
                                           [](double radius) { return radius >= 0.0; });
                    } else if constexpr (std::is_same_v<T, HistoryZonotopeMembership>) {
                        return family == HistorySetFamily::zonotope &&
                               item.center.size() == state_dimension && finite(item.center) &&
                               shape(item.generators, state_dimension);
                    } else if constexpr (std::is_same_v<T, HistoryParallelotopeMembership>) {
                        if (family != HistorySetFamily::parallelotope ||
                            item.center.size() != state_dimension || !finite(item.center) ||
                            !shape(item.frame, state_dimension) ||
                            item.frame.cols != state_dimension ||
                            item.lower.size() != state_dimension ||
                            item.upper.size() != state_dimension || !finite(item.lower) ||
                            !finite(item.upper) ||
                            !geometry::detail::independent_directions(item.frame))
                            return false;
                        for (std::size_t coordinate = 0; coordinate < state_dimension; ++coordinate)
                            if (item.lower[coordinate] > item.upper[coordinate])
                                return false;
                        return true;
                    } else {
                        return family == HistorySetFamily::ellipsoid &&
                               item.selected.center.size() == state_dimension &&
                               finite(item.selected.center) &&
                               shape(item.selected.factor, state_dimension);
                    }
                },
                geometry);
        };
        const bool valid =
            valid_geometry(member.shape, member.origin.selected, member.origin.selected_family) &&
            member.origin.source && member.origin.source->id == member.origin.reference &&
            valid_geometry(member.origin.source->geometry, member.origin.source->id,
                           member.origin.source->family) &&
            (member.origin.reference != member.origin.selected ||
             (member.origin.source->family == member.origin.selected_family &&
              same_membership_payload(member.shape, member.origin.source->geometry)));
        if (!valid)
            errors.push_back(invalid(
                field,
                "Selected or source geometry, family, dimension, or set identity is inconsistent."));
    }
    return errors;
}

Diagnostics check_history_membership_witnesses(const HistoryDomain &domain,
                                               std::span<const double> history,
                                               std::span<const HistoryMembershipWitness> witnesses,
                                               NumericalPolicy policy) {
    auto errors = check_history_domain_memberships(domain);
    if (!errors.empty())
        return errors;
    const auto &coordinates = domain.original.coordinates;
    const auto n = coordinates.dimensions.state;
    const auto history_count =
        n * (coordinates.horizon + 1) + coordinates.dimensions.control * coordinates.horizon;
    if (!std::isfinite(policy.absolute_tolerance) || !std::isfinite(policy.relative_tolerance) ||
        policy.absolute_tolerance < 0.0 || policy.relative_tolerance < 0.0 ||
        history.size() != history_count || !finite(history) ||
        witnesses.size() != domain.memberships.size())
        return {invalid("history.membership_witnesses",
                        "History, tolerance, or membership witness count is invalid.")};
    for (std::size_t i = 0; i < domain.memberships.size(); ++i) {
        const auto &member = domain.memberships[i];
        const auto state = history.subspan(member.stage.value * n, n);
        const bool valid = std::visit(
            [&](const auto &selected) {
                using T = std::decay_t<decltype(selected)>;
                if constexpr (std::is_same_v<T, HistoryHMembership>) {
                    const auto *witness = std::get_if<HistoryHWitness>(&witnesses[i]);
                    const auto representation = selected.selected.representation();
                    return witness && h_contains(std::get<sets::HRepresentation>(representation),
                                                 state, policy);
                } else if constexpr (std::is_same_v<T, HistoryAxisBoxMembership>) {
                    const auto *witness = std::get_if<HistoryAxisBoxWitness>(&witnesses[i]);
                    if (!witness || witness->coefficients.size() != n ||
                        !finite(witness->coefficients))
                        return false;
                    for (std::size_t j = 0; j < n; ++j) {
                        const auto coefficient = witness->coefficients[j];
                        const auto contribution = selected.radii[j] * coefficient;
                        const auto reconstructed = selected.center[j] + contribution;
                        const auto scale =
                            std::max({1.0, std::abs(state[j]), std::abs(selected.center[j])}) +
                            std::abs(contribution);
                        if (!within(std::max(0.0, std::abs(coefficient) - 1.0),
                                    std::max(1.0, std::abs(coefficient)), policy) ||
                            !std::isfinite(reconstructed) ||
                            !within(std::abs(reconstructed - state[j]), scale, policy))
                            return false;
                    }
                    return true;
                } else if constexpr (std::is_same_v<T, HistoryZonotopeMembership>) {
                    const auto *witness = std::get_if<HistoryZonotopeWitness>(&witnesses[i]);
                    if (!witness || witness->coefficients.size() != selected.generators.cols ||
                        !finite(witness->coefficients))
                        return false;
                    for (double value : witness->coefficients)
                        if (!within(std::max(0.0, std::abs(value) - 1.0),
                                    std::max(1.0, std::abs(value)), policy))
                            return false;
                    return reconstruct(state, selected.center, selected.generators,
                                       witness->coefficients, policy);
                } else if constexpr (std::is_same_v<T, HistoryParallelotopeMembership>) {
                    const auto *witness = std::get_if<HistoryParallelotopeWitness>(&witnesses[i]);
                    if (!witness || witness->coefficients.size() != n ||
                        !finite(witness->coefficients))
                        return false;
                    for (std::size_t j = 0; j < n; ++j) {
                        const auto value = witness->coefficients[j];
                        const auto scale =
                            std::max({1.0, std::abs(value), std::abs(selected.lower[j]),
                                      std::abs(selected.upper[j])});
                        if (!within(std::max({0.0, selected.lower[j] - value,
                                              value - selected.upper[j]}),
                                    scale, policy))
                            return false;
                    }
                    return reconstruct(state, selected.center, selected.frame,
                                       witness->coefficients, policy);
                } else if constexpr (std::is_same_v<T, HistoryBallFactorMembership>) {
                    const auto *witness = std::get_if<HistoryBallFactorWitness>(&witnesses[i]);
                    const auto &factor = selected.selected.factor;
                    if (!witness || witness->coefficients.size() != factor.cols ||
                        !finite(witness->coefficients))
                        return false;
                    double norm = 0.0;
                    for (double value : witness->coefficients)
                        norm = std::hypot(norm, value);
                    return within(std::max(0.0, norm - 1.0), std::max(1.0, norm), policy) &&
                           reconstruct(state, selected.selected.center, factor,
                                       witness->coefficients, policy);
                } else {
                    const auto *witness = std::get_if<HistoryVSimplexWitness>(&witnesses[i]);
                    const auto representation = selected.selected.representation();
                    const auto &vertices = std::get<sets::VRepresentation>(representation).vertices;
                    if (!witness || witness->coefficients.size() != vertices.rows() ||
                        !finite(witness->coefficients))
                        return false;
                    double sum = 0.0;
                    for (double value : witness->coefficients) {
                        if (!within(std::max(0.0, -value), std::max(1.0, std::abs(value)), policy))
                            return false;
                        sum += value;
                    }
                    if (!within(std::abs(sum - 1.0), std::max(1.0, std::abs(sum)), policy))
                        return false;
                    for (std::size_t col = 0; col < n; ++col) {
                        double value = 0.0, scale = std::max(1.0, std::abs(state[col]));
                        for (std::size_t row = 0; row < vertices.rows(); ++row) {
                            const double term = vertices(row, col) * witness->coefficients[row];
                            value += term;
                            scale += std::abs(term);
                        }
                        if (!std::isfinite(value) ||
                            !within(std::abs(value - state[col]), scale, policy))
                            return false;
                    }
                    return true;
                }
            },
            member.shape);
        if (!valid)
            errors.push_back(invalid(
                "history.membership_witnesses[" + std::to_string(i) + "]",
                "Witness kind, coefficients, or reconstructed state violates the selected membership."));
    }
    return errors;
}
} // namespace csl::optimization
