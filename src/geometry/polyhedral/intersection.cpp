#include <csl/geometry/polyhedral_intersection.hpp>

#include <limits>
#include <utility>

namespace csl::geometry::polyhedral {
namespace {
Diagnostic invalid(const char* field, const char* explanation) {
    return {DiagnosticCode::invalid_input, field, explanation};
}
std::optional<sets::SetData> make_h(const SetId& id, std::size_t dimension,
        std::vector<std::string> labels, const Matrix& a, const Vector& b,
        const Matrix& e, const Vector& f) {
    auto av = numeric::snapshot(a);
    auto bv = numeric::snapshot_vector(b);
    auto ev = numeric::snapshot(e);
    auto fv = numeric::snapshot_vector(f);
    if (!std::holds_alternative<numeric::MatrixView>(av) ||
        !std::holds_alternative<numeric::VectorView>(bv) ||
        !std::holds_alternative<numeric::MatrixView>(ev) ||
        !std::holds_alternative<numeric::VectorView>(fv)) return {};
    auto made = sets::make_h({id, dimension, std::move(labels)},
        {std::get<numeric::MatrixView>(av), std::get<numeric::VectorView>(bv),
         std::get<numeric::MatrixView>(ev), std::get<numeric::VectorView>(fv)});
    if (auto* set = std::get_if<sets::SetData>(&made)) return *set;
    return {};
}
} // namespace

SetResult intersect_h(const sets::SetData& left, const sets::SetData& right, SetId output_id) {
    if (output_id.value.empty()) return Diagnostics{invalid("geometry.intersection.id", "Output set identity must be nonempty.")};
    const auto left_metadata = left.metadata();
    const auto right_metadata = right.metadata();
    if (left_metadata->set.dimension != right_metadata->set.dimension)
        return Diagnostics{invalid("geometry.intersection.dimension", "H operands must have the same ambient dimension.")};
    if (left_metadata->coordinate_labels != right_metadata->coordinate_labels)
        return Diagnostics{invalid("geometry.intersection.coordinates", "H operands must use the same coordinate labels and ordering.")};
    const auto left_representation = left.representation();
    const auto right_representation = right.representation();
    const auto* a = std::get_if<sets::HRepresentation>(&left_representation);
    const auto* b = std::get_if<sets::HRepresentation>(&right_representation);
    if (!a || !b)
        return Diagnostics{{DiagnosticCode::unsupported, "geometry.intersection.representation",
            "This operation accepts native H representations; convert other representations first."}};
    if (a->inequalities.rows() > std::numeric_limits<std::size_t>::max() - b->inequalities.rows() ||
        a->equalities.rows() > std::numeric_limits<std::size_t>::max() - b->equalities.rows())
        return Diagnostics{invalid("geometry.intersection.capacity", "Combined row count overflows size_t.")};
    const auto dimension = left_metadata->set.dimension;
    const auto inequality_count = a->inequalities.rows() + b->inequalities.rows();
    const auto equality_count = a->equalities.rows() + b->equalities.rows();
    if (dimension && inequality_count > std::numeric_limits<std::size_t>::max() / dimension)
        return Diagnostics{invalid("geometry.intersection.capacity", "Combined inequality matrix size overflows size_t.")};
    if (dimension && equality_count > std::numeric_limits<std::size_t>::max() / dimension)
        return Diagnostics{invalid("geometry.intersection.capacity", "Combined equality matrix size overflows size_t.")};

    Matrix inequalities{inequality_count, dimension, {}};
    inequalities.values.reserve(inequality_count * dimension);
    Vector bounds; bounds.reserve(inequality_count);
    for (const auto* h : {a, b}) {
        for (std::size_t i = 0; i < h->inequalities.rows(); ++i) {
            for (std::size_t j = 0; j < dimension; ++j) inequalities.values.push_back(h->inequalities(i,j));
            bounds.push_back(h->upper_bounds[i]);
        }
    }
    Matrix equalities{equality_count, dimension, {}};
    equalities.values.reserve(equality_count * dimension);
    Vector values; values.reserve(equality_count);
    for (const auto* h : {a, b}) {
        for (std::size_t i = 0; i < h->equalities.rows(); ++i) {
            for (std::size_t j = 0; j < dimension; ++j) equalities.values.push_back(h->equalities(i,j));
            values.push_back(h->equality_values[i]);
        }
    }
    auto result = make_h(output_id, dimension, left_metadata->coordinate_labels,
        inequalities, bounds, equalities, values);
    if (!result) return Diagnostics{invalid("geometry.intersection.storage", "Could not create immutable intersection data.")};
    return *result;
}
} // namespace csl::geometry::polyhedral
