#include <csl/model/hybrid_system.hpp>
#include <csl/optimization/objectives.hpp>
#include <csl/sets/data.hpp>

#include <algorithm>
#include <cmath>
#include <functional>
#include <limits>
#include <optional>
#include <type_traits>
#include <unordered_map>
#include <unordered_set>

namespace csl::model {
namespace {
Diagnostic invalid(const char* field, const char* message) {
    return {DiagnosticCode::invalid_input, field, message};
}

const HybridMode* find_mode(const HybridSystem& system, const HybridModeId& id) {
    const auto found = std::find_if(system.modes.begin(), system.modes.end(),
        [&](const HybridMode& mode) { return mode.id == id; });
    return found == system.modes.end() ? nullptr : &*found;
}

bool finite(const Matrix& matrix) {
    if (matrix.rows != 0 && matrix.cols > std::numeric_limits<std::size_t>::max()/matrix.rows)
        return false;
    return matrix.values.size() == matrix.rows * matrix.cols &&
        std::all_of(matrix.values.begin(), matrix.values.end(),
            [](double value) { return std::isfinite(value); });
}

std::optional<std::size_t> set_dimension(const AdmissibleSet& set) {
    return std::visit([](const auto& value) -> std::optional<std::size_t> {
        using T = std::decay_t<decltype(value)>;
        if constexpr (std::is_same_v<T, EmptySet> || std::is_same_v<T, UniversalSet>)
            return value.dimension;
        else if constexpr (std::is_same_v<T, Singleton>)
            return value.point.size();
        else {
            const auto frozen = sets::from_handle(value);
            if (const auto* data = std::get_if<sets::SetData>(&frozen))
                return data->metadata()->set.dimension;
            return std::nullopt;
        }
    }, set);
}

void check_set(Diagnostics& errors, const AdmissibleSet& set, std::size_t dimension,
    const std::string& field) {
    const auto actual = set_dimension(set);
    if (!actual || *actual != dimension)
        errors.push_back(invalid(field.c_str(), "Set must be valid and match the declared coordinate dimension"));
    if (const auto* handle = std::get_if<SetHandle>(&set)) {
        const auto frozen = sets::from_handle(*handle);
        if (const auto* data = std::get_if<sets::SetData>(&frozen)) {
            if (data->metadata()->set.polyhedral != SetProperty::yes)
                errors.push_back({DiagnosticCode::unsupported,field,
                    "The initial hybrid profile requires exact polyhedral admissible sets"});
        }
    }
}

void check_stage(Diagnostics& errors, const LinearStage& stage, const HybridMode& mode,
    const std::string& field) {
    const auto n = mode.state_dimension;
    const auto m = mode.control_dimension;
    if (stage.A.rows != n || stage.A.cols != n || !finite(stage.A) ||
        stage.B.rows != n || stage.B.cols != m || !finite(stage.B) ||
        stage.E.rows != n || stage.E.cols != 0 || !finite(stage.E) ||
        stage.offset.size() != n || !std::all_of(stage.offset.begin(), stage.offset.end(),
            [](double value) { return std::isfinite(value); }))
        errors.push_back(invalid(field.c_str(), "Mode flow must be finite with A(n,n), B(n,m), zero external dimension, and offset(n)"));
}

template<class T>
bool unique_nonempty_labels(const std::vector<T>& labels, std::size_t dimension) {
    if (labels.empty()) return true;
    if (labels.size() != dimension) return false;
    std::unordered_set<std::string> seen;
    for (const auto& label : labels)
        if (label.empty() || !seen.insert(label).second) return false;
    return true;
}

}

HybridPathEnumeration enumerate_hybrid_paths(const HybridSystem& system,
    const HybridModeId& initial_mode, const std::vector<HybridModeId>& allowed_terminal_modes,
    HybridEnumerationLimits limits) {
    if (system.horizon == std::numeric_limits<std::size_t>::max())
        return invalid("hybrid.horizon", "Horizon is too large to represent T+1 state stages");
    if (system.horizon > limits.max_horizon)
        return Diagnostic{DiagnosticCode::unsupported,"hybrid.horizon.limit",
            "The requested horizon exceeds the caller's admitted stage limit"};
    std::unordered_set<std::string> mode_ids;
    for (const auto& mode : system.modes) {
        if (mode.id.value.empty() || !mode_ids.insert(mode.id.value).second)
            return invalid("hybrid.modes", "Mode IDs must be unique and nonempty");
    }
    if (!find_mode(system, initial_mode))
        return invalid("hybrid.initial_mode", "The request initial mode is not in the system catalogue");

    std::unordered_set<std::string> edge_ids;
    for (const auto& edge : system.edges) {
        if (edge.id.value.empty() || !edge_ids.insert(edge.id.value).second)
            return invalid("hybrid.edges", "Transition-edge IDs must be unique and nonempty");
        if (!find_mode(system, edge.source) || !find_mode(system, edge.target))
            return invalid("hybrid.edges", "Each transition edge must reference catalogued source and target modes");
    }

    std::unordered_set<std::string> terminal_ids;
    for (const auto& mode : allowed_terminal_modes) {
        if (!find_mode(system, mode))
            return invalid("hybrid.terminal_modes", "Each allowed terminal mode must be in the system catalogue");
        if (!terminal_ids.insert(mode.value).second)
            return invalid("hybrid.terminal_modes", "Allowed terminal modes must not be duplicated");
    }
    if (allowed_terminal_modes.empty())
        return invalid("hybrid.terminal_modes", "At least one terminal mode must be allowed");

    std::vector<std::unordered_set<std::string>> can_reach(system.horizon+1);
    can_reach[0] = terminal_ids;
    for (std::size_t remaining = 1; remaining <= system.horizon; ++remaining) {
        for (const auto& edge : system.edges)
            if (can_reach[remaining-1].contains(edge.target.value))
                can_reach[remaining].insert(edge.source.value);
    }
    if (!can_reach[system.horizon].contains(initial_mode.value))
        return std::vector<HybridPath>{};

    std::vector<HybridPath> result;
    HybridPath path{{initial_mode}, {}};
    struct Frame { std::size_t stage; HybridModeId mode; std::size_t next_edge; };
    std::vector<Frame> stack{{0,initial_mode,0}};
    while (!stack.empty()) {
        auto& frame = stack.back();
        if (frame.stage == system.horizon) {
            if (terminal_ids.contains(frame.mode.value)) {
                if (result.size() == limits.max_paths)
                    return Diagnostic{DiagnosticCode::unsupported,"hybrid.paths.limit",
                        "The complete hybrid path family exceeds the caller's path limit"};
                result.push_back(path);
            }
            stack.pop_back();
            if (!stack.empty()) {
                path.modes.pop_back();
                path.edges.pop_back();
            }
            continue;
        }

        const auto remaining = system.horizon - frame.stage - 1;
        while (frame.next_edge < system.edges.size()) {
            const auto& candidate = system.edges[frame.next_edge];
            if (candidate.source == frame.mode && can_reach[remaining].contains(candidate.target.value))
                break;
            ++frame.next_edge;
        }
        if (frame.next_edge == system.edges.size()) {
            stack.pop_back();
            if (!stack.empty()) {
                path.modes.pop_back();
                path.edges.pop_back();
            }
            continue;
        }

        const auto& edge = system.edges[frame.next_edge++];
        path.edges.push_back(edge.id);
        path.modes.push_back(edge.target);
        stack.push_back({frame.stage+1,edge.target,0});
    }
    return result;
}

Diagnostics check_hybrid_profile(const HybridSystem& system, const HybridRequest& request) {
    Diagnostics errors;
    if (system.horizon == std::numeric_limits<std::size_t>::max()) {
        errors.push_back(invalid("hybrid.horizon", "Horizon is too large to represent T+1 state stages"));
        return errors;
    }

    std::unordered_map<std::string, const HybridMode*> modes;
    for (const auto& mode : system.modes) {
        if (mode.id.value.empty() || !modes.emplace(mode.id.value, &mode).second) {
            errors.push_back(invalid("hybrid.modes", "Mode IDs must be unique and nonempty"));
            continue;
        }
        if (!unique_nonempty_labels(mode.state_coordinate_labels, mode.state_dimension) ||
            !unique_nonempty_labels(mode.control_coordinate_labels, mode.control_dimension))
            errors.push_back(invalid("hybrid.mode.coordinates", "Coordinate labels must be absent or unique, nonempty, and dimension-matched"));
        if (mode.control_sets.size() != system.horizon)
            errors.push_back(invalid("hybrid.mode.controls", "Each mode requires exactly T control sets"));
        for (const auto& set : mode.control_sets)
            check_set(errors, set, mode.control_dimension, "hybrid.mode.controls");
        if (mode.invariants.size() != system.horizon + 1)
            errors.push_back(invalid("hybrid.mode.invariants", "Each mode requires exactly T+1 stage-indexed invariants"));
        for (const auto& set : mode.invariants)
            check_set(errors, set, mode.state_dimension, "hybrid.mode.invariants");

        auto validate_stage = [&](const LinearStage& stage) {
            check_stage(errors, stage, mode, "hybrid.mode.flow");
        };
        if (const auto* constant = std::get_if<LinearStage>(&mode.flow)) validate_stage(*constant);
        else {
            const auto& stages = std::get<std::vector<LinearStage>>(mode.flow);
            if (stages.size() != system.horizon)
                errors.push_back(invalid("hybrid.mode.flow", "Indexed mode flow must have exactly T stages"));
            for (const auto& stage : stages) validate_stage(stage);
        }
    }

    if (!modes.contains(request.initial.mode.value))
        errors.push_back(invalid("hybrid.initial.mode", "Initial mode must be in the mode catalogue"));
    else if (request.initial.state.size() != modes.at(request.initial.mode.value)->state_dimension ||
        !std::all_of(request.initial.state.begin(), request.initial.state.end(),
            [](double value) { return std::isfinite(value); }))
        errors.push_back(invalid("hybrid.initial.state", "Known initial state must be finite and match its initial mode dimension"));

    std::unordered_set<std::string> terminal_modes;
    for (const auto& mode : request.allowed_terminal_modes) {
        if (!modes.contains(mode.value))
            errors.push_back(invalid("hybrid.terminal_modes", "Allowed terminal modes must be in the mode catalogue"));
        if (!terminal_modes.insert(mode.value).second)
            errors.push_back(invalid("hybrid.terminal_modes", "Allowed terminal modes must be unique"));
    }
    if (request.allowed_terminal_modes.empty())
        errors.push_back(invalid("hybrid.terminal_modes", "At least one terminal mode must be allowed"));

    std::unordered_set<std::string> objective_modes;
    std::optional<std::string> quantity;
    std::optional<std::string> units;
    for (const auto& objective : request.terminal_objectives) {
        const auto mode = modes.find(objective.mode.value);
        if (mode == modes.end() || !terminal_modes.contains(objective.mode.value)) {
            errors.push_back(invalid("hybrid.terminal_objectives", "Each objective must belong to an allowed terminal mode"));
            continue;
        }
        if (!objective_modes.insert(objective.mode.value).second)
            errors.push_back(invalid("hybrid.terminal_objectives", "Each allowed terminal mode requires exactly one objective"));
        if (objective.quantity.empty() || objective.units.empty())
            errors.push_back(invalid("hybrid.terminal_objectives", "Objective quantity and units must be explicit"));
        if (!quantity) quantity = objective.quantity;
        if (!units) units = objective.units;
        if (*quantity != objective.quantity || *units != objective.units)
            errors.push_back(invalid("hybrid.terminal_objectives", "All mode-indexed objectives must share quantity and units"));
        const auto frozen = optimization::snapshot(objective.objective);
        if (const auto* data = std::get_if<optimization::Objective>(&frozen)) {
            if (data->dimension() != mode->second->state_dimension)
                errors.push_back(invalid("hybrid.terminal_objectives", "Terminal objective dimension must match its mode"));
        } else if (const auto* diagnostic = std::get_if<Diagnostic>(&frozen)) {
            errors.push_back(invalid("hybrid.terminal_objectives", diagnostic->explanation.c_str()));
        } else {
            errors.push_back({DiagnosticCode::unsupported,"hybrid.terminal_objectives",
                "Objective validation stopped before a compatible mode profile could be selected"});
        }
    }
    if (objective_modes.size() != terminal_modes.size())
        errors.push_back(invalid("hybrid.terminal_objectives", "Every allowed terminal mode requires exactly one objective"));

    std::unordered_set<std::string> edge_ids;
    for (const auto& edge : system.edges) {
        if (edge.id.value.empty() || !edge_ids.insert(edge.id.value).second) {
            errors.push_back(invalid("hybrid.edges", "Transition-edge IDs must be unique and nonempty"));
            continue;
        }
        const auto source = modes.find(edge.source.value);
        const auto target = modes.find(edge.target.value);
        if (source == modes.end() || target == modes.end()) {
            errors.push_back(invalid("hybrid.edges", "Each transition edge must reference catalogued source and target modes"));
            continue;
        }
        if (edge.guards.size() != system.horizon || edge.reset_relations.size() != system.horizon)
            errors.push_back(invalid("hybrid.edge.stages", "Each edge requires exactly T guards and reset relations"));
        for (const auto& guard : edge.guards)
            check_set(errors, guard, source->second->state_dimension, "hybrid.edge.guard");
        for (const auto& reset : edge.reset_relations) {
            const auto relation = sets::from_handle(reset);
            if (source->second->state_dimension > std::numeric_limits<std::size_t>::max() -
                    target->second->state_dimension) {
                errors.push_back(invalid("hybrid.edge.reset", "Reset relation dimension overflows the supported coordinate count"));
                continue;
            }
            const auto expected_dimension = source->second->state_dimension + target->second->state_dimension;
            if (!std::holds_alternative<sets::SetData>(relation) ||
                reset.metadata.dimension != expected_dimension) {
                errors.push_back(invalid("hybrid.edge.reset", "Reset relation must be valid and have source plus destination state dimension"));
            } else if (std::get<sets::SetData>(relation).metadata()->set.polyhedral != SetProperty::yes) {
                errors.push_back({DiagnosticCode::unsupported,"hybrid.edge.reset",
                    "The initial hybrid profile requires exact polyhedral reset relations"});
            }
        }
    }
    return errors;
}

} // namespace csl::model
