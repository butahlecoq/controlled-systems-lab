#pragma once

#include <csl/sets/data.hpp>

namespace csl::sets {

// A factor ID denotes the same scalar in every generator set that carries it.
struct FactorId {
    std::string value;
    bool operator==(const FactorId&) const = default;
};

// {center + generators * xi : -1 <= xi <= 1, equalities * xi = equality_values}.
// Matrix buffers are owning row-major data; factor_ids index their columns.
struct GeneratorInput {
    SetId id;
    Vector center;
    Matrix generators;
    std::vector<FactorId> factor_ids;
    Matrix equalities;
    Vector equality_values;
    std::vector<std::string> coordinate_labels;
};

namespace detail { struct GeneratorStorage; }

class GeneratorSet {
public:
    GeneratorSet(const GeneratorSet&) = default;
    GeneratorSet& operator=(const GeneratorSet&) = default;
    const SetId& id() const noexcept;
    const Vector& center() const noexcept;
    const Matrix& generators() const noexcept;
    const std::vector<FactorId>& factor_ids() const noexcept;
    const Matrix& equalities() const noexcept;
    const Vector& equality_values() const noexcept;
    const std::vector<std::string>& coordinate_labels() const noexcept;
    SetHandle as_handle() const;
private:
    explicit GeneratorSet(std::shared_ptr<const detail::GeneratorStorage> storage);
    std::shared_ptr<const detail::GeneratorStorage> storage_;
    friend std::variant<GeneratorSet, Diagnostics> make_generator_set(GeneratorInput);
    friend std::variant<GeneratorSet, Diagnostics> from_generator_handle(const SetHandle&);
};

using GeneratorResult = std::variant<GeneratorSet, Diagnostics>;
GeneratorResult make_generator_set(GeneratorInput);
GeneratorResult from_generator_handle(const SetHandle&);

struct FactorPolyhedron {
    SetData factors; // exact H form in the factor coordinates, modulo binary64 coefficients
    Matrix map;      // physical x = map * xi + offset
    Vector offset;
};
std::variant<FactorPolyhedron, Diagnostics> factor_polyhedron(const GeneratorSet&);

} // namespace csl::sets
