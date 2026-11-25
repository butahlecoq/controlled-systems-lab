#include <csl/reachability/parallelotope_frame.hpp>

#include <cmath>
#include <limits>

namespace csl::reachability {

std::string_view parallelotope_frame_rule_name(ParallelotopeFrameRule rule) noexcept {
    switch (rule) {
    case ParallelotopeFrameRule::axis:
        return "axis";
    case ParallelotopeFrameRule::fixed_rotation_45:
        return "fixed-rotation-45";
    case ParallelotopeFrameRule::support_selected:
        return "support-selected";
    }
    return "unknown";
}

Matrix identity_parallelotope_frame(std::size_t dimension) {
    Matrix frame{dimension, dimension, Vector(dimension * dimension, 0)};
    for (std::size_t i = 0; i < dimension; ++i)
        frame.values[i * dimension + i] = 1;
    return frame;
}

Matrix fixed_rotation_45_frame(std::size_t dimension) {
    auto frame = identity_parallelotope_frame(dimension);
    constexpr double root_half = 0.707106781186547524400844362104849039;
    for (std::size_t i = 0; i + 1 < dimension; i += 2) {
        frame.values[i * dimension + i] = root_half;
        frame.values[i * dimension + i + 1] = -root_half;
        frame.values[(i + 1) * dimension + i] = root_half;
        frame.values[(i + 1) * dimension + i + 1] = root_half;
    }
    return frame;
}

ParallelotopeFrame parallelotope_frame(ParallelotopeFrameRule rule, std::size_t dimension) {
    switch (rule) {
    case ParallelotopeFrameRule::axis:
        return {identity_parallelotope_frame(dimension), rule, 0};
    case ParallelotopeFrameRule::fixed_rotation_45:
        return {fixed_rotation_45_frame(dimension), rule, 45};
    case ParallelotopeFrameRule::support_selected:
        break;
    }
    return {identity_parallelotope_frame(dimension), ParallelotopeFrameRule::axis, 0};
}

std::vector<ParallelotopeFrame> parallelotope_frame_candidates(ParallelotopeFrameRule rule,
                                                               std::size_t dimension) {
    std::vector<ParallelotopeFrame> candidates;
    if (rule == ParallelotopeFrameRule::support_selected) {
        candidates.push_back(parallelotope_frame(ParallelotopeFrameRule::axis, dimension));
        candidates.push_back(parallelotope_frame(ParallelotopeFrameRule::fixed_rotation_45, dimension));
    } else {
        candidates.push_back(parallelotope_frame(rule, dimension));
    }
    return candidates;
}

std::size_t select_parallelotope_frame(std::span<const double> excess) noexcept {
    std::size_t best = 0;
    double best_value = std::numeric_limits<double>::infinity();
    for (std::size_t i = 0; i < excess.size(); ++i) {
        const auto value = excess[i];
        if (!std::isfinite(value))
            continue;
        if (value < best_value) {
            best_value = value;
            best = i;
        }
    }
    return best;
}

} // namespace csl::reachability
