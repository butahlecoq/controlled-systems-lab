#pragma once

#include "hybrid_exact_polytope.hpp"
#include <csl/model/hybrid_system.hpp>

#include <algorithm>
#include <limits>
#include <optional>
#include <string>
#include <vector>

namespace csl::synthesis::detail::hybrid_exact {

enum class RawRelationState { built, unsupported, cancelled };

struct RawRelationResult {
    RawRelationState state{RawRelationState::unsupported};
    std::size_t variables{};
    std::vector<Row> rows;
    std::string reason;
};

// Reconstruct the path relation directly from the model's stage data. This
// deliberately does not call the production joint-H composer or use its trace.
inline RawRelationResult reconstruct_path_relation(
    const model::HybridSystem& system, const model::HybridRequest& request,
    const model::HybridPath& path, model::HybridRelationLimits relation_limits,
    Limits exact_limits = {}, std::stop_token cancellation = {}) {
    const auto unsupported = [](const char* reason) {
        return RawRelationResult{RawRelationState::unsupported, 0, {}, reason};
    };
    const auto cancelled = [] {
        return RawRelationResult{RawRelationState::cancelled, 0, {},
                                 "Raw hybrid relation reconstruction was cancelled"};
    };
    if (cancellation.stop_requested())
        return cancelled();
    exact_limits.max_variables =
        std::min(exact_limits.max_variables, relation_limits.max_variables);
    exact_limits.max_rows = std::min(exact_limits.max_rows,
                                     relation_limits.max_rows);
    if (system.horizon == std::numeric_limits<std::size_t>::max() ||
        system.horizon > exact_limits.max_stages)
        return unsupported("Hybrid horizon exceeds the raw relation resource limit");
    const auto profile_errors = model::check_hybrid_profile(system, request);
    if (cancellation.stop_requested())
        return cancelled();
    if (!profile_errors.empty())
        return unsupported("Hybrid model profile is invalid");
    if (path.modes.size() != system.horizon + 1 ||
        path.edges.size() != system.horizon || path.modes.empty() ||
        path.modes.front() != request.initial.mode ||
        std::find(request.allowed_terminal_modes.begin(),
                  request.allowed_terminal_modes.end(), path.modes.back()) ==
            request.allowed_terminal_modes.end())
        return unsupported("Path does not match the request horizon or endpoints");

    const auto find_mode = [&](const model::HybridModeId& id)
        -> const model::HybridMode* {
        const auto found = std::find_if(system.modes.begin(), system.modes.end(),
            [&](const auto& mode) { return mode.id == id; });
        return found == system.modes.end() ? nullptr : &*found;
    };
    const auto find_edge = [&](const model::HybridEdgeId& id)
        -> const model::HybridTransitionEdge* {
        const auto found = std::find_if(system.edges.begin(), system.edges.end(),
            [&](const auto& edge) { return edge.id == id; });
        return found == system.edges.end() ? nullptr : &*found;
    };
    std::vector<const model::HybridMode*> modes;
    std::vector<const model::HybridTransitionEdge*> edges;
    modes.reserve(path.modes.size());
    edges.reserve(path.edges.size());
    for (const auto& id : path.modes) {
        if (cancellation.stop_requested())
            return cancelled();
        const auto* mode = find_mode(id);
        if (!mode)
            return unsupported("Path references an unknown mode");
        modes.push_back(mode);
    }
    for (std::size_t stage = 0; stage < path.edges.size(); ++stage) {
        if (cancellation.stop_requested())
            return cancelled();
        const auto* edge = find_edge(path.edges[stage]);
        if (!edge || edge->source != path.modes[stage] ||
            edge->target != path.modes[stage + 1])
            return unsupported("Path references an unknown or disconnected edge");
        edges.push_back(edge);
    }

    std::size_t width = modes.front()->state_dimension;
    std::vector<std::size_t> state_offsets(system.horizon + 1),
        control_offsets(system.horizon), pre_offsets(system.horizon);
    const auto reserve = [&](std::size_t count, std::size_t& offset) {
        if (count > std::numeric_limits<std::size_t>::max() - width)
            return false;
        offset = width;
        width += count;
        return true;
    };
    state_offsets.front() = 0;
    for (std::size_t stage = 0; stage < system.horizon; ++stage) {
        if (!reserve(modes[stage]->control_dimension, control_offsets[stage]) ||
            !reserve(modes[stage]->state_dimension, pre_offsets[stage]) ||
            !reserve(modes[stage + 1]->state_dimension, state_offsets[stage + 1]))
            return unsupported("Joint relation dimension overflows size_t");
    }
    if (width > exact_limits.max_variables)
        return unsupported("Joint relation exceeds the exact variable limit");
    RawRelationResult result{RawRelationState::built, width, {}, {}};

    const auto append_row = [&](std::span<const double> coefficients,
                                double bound, bool equality) {
        const std::size_t additions = equality ? 2 : 1;
        if (result.rows.size() > exact_limits.max_rows ||
            additions > exact_limits.max_rows - result.rows.size())
            return false;
        const auto max_elements = relation_limits.max_matrix_elements;
        if (width != 0 &&
            (result.rows.size() + additions > max_elements / width))
            return false;
        if (equality)
            return append_equality(coefficients, bound,
                                   exact_limits.max_integer_bits, result.rows);
        return append_inequality(coefficients, bound, false,
                                 exact_limits.max_integer_bits, result.rows);
    };
    const auto add_set_rows = [&](const auto& matrix, const auto& rhs,
                                  bool equality, std::size_t offset,
                                  std::size_t dimension) {
        if (matrix.cols() != dimension || rhs.size() != matrix.rows())
            return false;
        for (std::size_t row = 0; row < matrix.rows(); ++row) {
            if (cancellation.stop_requested())
                return false;
            std::vector<double> coefficients(width, 0.0);
            for (std::size_t column = 0; column < dimension; ++column)
                coefficients[offset + column] = matrix(row, column);
            if (!append_row(coefficients, rhs[row], equality))
                return false;
        }
        return true;
    };
    const auto add_admissible = [&](const AdmissibleSet& set,
                                    std::size_t offset,
                                    std::size_t dimension) {
        const auto add_empty = [&] {
            const std::vector<double> zero(width, 0.0);
            return append_row(zero, -1.0, false);
        };
        const auto add_singleton = [&](std::span<const double> point) {
            if (point.size() != dimension)
                return false;
            std::vector<double> row(width, 0.0);
            for (std::size_t column = 0; column < dimension; ++column) {
                if (cancellation.stop_requested())
                    return false;
                row[offset + column] = 1.0;
                const bool appended = append_row(row, point[column], true);
                row[offset + column] = 0.0;
                if (!appended)
                    return false;
            }
            return true;
        };
        if (const auto* empty = std::get_if<EmptySet>(&set))
            return empty->dimension == dimension && add_empty();
        if (const auto* universal = std::get_if<UniversalSet>(&set))
            return universal->dimension == dimension;
        if (const auto* singleton = std::get_if<Singleton>(&set))
            return add_singleton(singleton->point);
        const auto& handle = std::get<SetHandle>(set);
        if (handle.metadata.dimension != dimension)
            return false;
        const auto frozen = sets::from_handle(handle);
        if (!std::holds_alternative<sets::SetData>(frozen))
            return false;
        const auto representation =
            std::get<sets::SetData>(frozen).representation();
        if (const auto* h = std::get_if<sets::HRepresentation>(&representation))
            return add_set_rows(h->inequalities, h->upper_bounds, false,
                                offset, dimension) &&
                   add_set_rows(h->equalities, h->equality_values, true,
                                offset, dimension);
        if (const auto* singleton =
                std::get_if<sets::SingletonRepresentation>(&representation))
            return add_singleton(singleton->point.values());
        if (std::holds_alternative<sets::EmptyRepresentation>(representation))
            return add_empty();
        return std::holds_alternative<sets::UniversalRepresentation>(representation);
    };
    const auto add_reset = [&](const SetHandle& handle,
                               std::size_t pre_offset,
                               std::size_t post_offset,
                               std::size_t source_dimension,
                               std::size_t target_dimension) {
        if (target_dimension > std::numeric_limits<std::size_t>::max() -
                                   source_dimension)
            return false;
        const auto dimension = source_dimension + target_dimension;
        if (handle.metadata.dimension != dimension)
            return false;
        const auto frozen = sets::from_handle(handle);
        if (!std::holds_alternative<sets::SetData>(frozen))
            return false;
        const auto representation =
            std::get<sets::SetData>(frozen).representation();
        if (std::holds_alternative<sets::UniversalRepresentation>(representation))
            return true;
        if (std::holds_alternative<sets::EmptyRepresentation>(representation)) {
            const std::vector<double> zero(width, 0.0);
            return append_row(zero, -1.0, false);
        }
        const auto add_reset_rows = [&](const auto& matrix, const auto& rhs,
                                        bool equality) {
            if (matrix.cols() != dimension || rhs.size() != matrix.rows())
                return false;
            for (std::size_t row = 0; row < matrix.rows(); ++row) {
                if (cancellation.stop_requested())
                    return false;
                std::vector<double> coefficients(width, 0.0);
                for (std::size_t column = 0; column < source_dimension; ++column)
                    coefficients[pre_offset + column] = matrix(row, column);
                for (std::size_t column = 0; column < target_dimension; ++column)
                    coefficients[post_offset + column] =
                        matrix(row, source_dimension + column);
                if (!append_row(coefficients, rhs[row], equality))
                    return false;
            }
            return true;
        };
        if (const auto* h = std::get_if<sets::HRepresentation>(&representation))
            return add_reset_rows(h->inequalities, h->upper_bounds, false) &&
                   add_reset_rows(h->equalities, h->equality_values, true);
        if (const auto* singleton =
                std::get_if<sets::SingletonRepresentation>(&representation)) {
            if (singleton->point.size() != dimension)
                return false;
            for (std::size_t column = 0; column < dimension; ++column) {
                if (cancellation.stop_requested())
                    return false;
                std::vector<double> coefficients(width, 0.0);
                const auto at = column < source_dimension
                    ? pre_offset + column
                    : post_offset + column - source_dimension;
                coefficients[at] = 1.0;
                if (!append_row(coefficients, singleton->point[column], true))
                    return false;
            }
            return true;
        }
        return false;
    };

    std::vector<double> zero_row(width, 0.0);
    for (std::size_t column = 0; column < request.initial.state.size(); ++column) {
        if (cancellation.stop_requested())
            return cancelled();
        std::fill(zero_row.begin(), zero_row.end(), 0.0);
        zero_row[state_offsets.front() + column] = 1.0;
        if (!append_row(zero_row, request.initial.state[column], true))
            return cancellation.stop_requested() ? cancelled() :
                unsupported("Initial state rows exceed relation limits");
    }
    for (std::size_t stage = 0; stage <= system.horizon; ++stage) {
        if (cancellation.stop_requested())
            return cancelled();
        const auto& mode = *modes[stage];
        if (!add_admissible(mode.invariants[stage], state_offsets[stage],
                            mode.state_dimension))
            return cancellation.stop_requested() ? cancelled() :
                unsupported("Invariant is unsupported or exceeds relation limits");
        if (stage == system.horizon)
            continue;
        const auto& source = *modes[stage];
        const auto& target = *modes[stage + 1];
        const auto& edge = *edges[stage];
        const auto& flow = std::holds_alternative<LinearStage>(source.flow)
            ? std::get<LinearStage>(source.flow)
            : std::get<std::vector<LinearStage>>(source.flow)[stage];
        for (std::size_t row = 0; row < source.state_dimension; ++row) {
            if (cancellation.stop_requested())
                return cancelled();
            std::vector<double> coefficients(width, 0.0);
            coefficients[pre_offsets[stage] + row] = 1.0;
            for (std::size_t column = 0; column < source.state_dimension; ++column)
                coefficients[state_offsets[stage] + column] -=
                    flow.A.values[row * flow.A.cols + column];
            for (std::size_t column = 0; column < source.control_dimension; ++column)
                coefficients[control_offsets[stage] + column] -=
                    flow.B.values[row * flow.B.cols + column];
            if (!append_row(coefficients, flow.offset[row], true))
                return cancellation.stop_requested() ? cancelled() :
                    unsupported("Flow rows exceed exact relation limits");
        }
        if (!add_admissible(source.control_sets[stage], control_offsets[stage],
                            source.control_dimension) ||
            !add_admissible(source.invariants[stage + 1], pre_offsets[stage],
                            source.state_dimension) ||
            !add_admissible(edge.guards[stage], pre_offsets[stage],
                            source.state_dimension) ||
            !add_reset(edge.reset_relations[stage], pre_offsets[stage],
                       state_offsets[stage + 1], source.state_dimension,
                       target.state_dimension))
            return cancellation.stop_requested() ? cancelled() :
                unsupported("Control, invariant, guard, or reset is unsupported or exceeds relation limits");
    }
    if (cancellation.stop_requested())
        return cancelled();
    return result;
}

} // namespace csl::synthesis::detail::hybrid_exact
