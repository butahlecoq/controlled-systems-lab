#include <csl/model/hybrid_system.hpp>
#include <csl/optimization/objectives.hpp>
#include <csl/sets/data.hpp>
#include <csl/numeric/data.hpp>

#include <algorithm>
#include <cmath>
#include <functional>
#include <limits>
#include <optional>
#include <stop_token>
#include <type_traits>
#include <unordered_map>
#include <unordered_set>

namespace csl::model {

HybridOperationPlanResult plan_hybrid_operations(
    std::span<const HybridPath> paths) {
    std::vector<HybridPlannedOperation> plan;
    for(std::size_t path_index=0;path_index<paths.size();++path_index) {
        const auto& path=paths[path_index];
        if(path.modes.empty() || path.edges.size()==std::numeric_limits<std::size_t>::max() ||
           path.modes.size()!=path.edges.size()+1)
            return Diagnostic{DiagnosticCode::invalid_input,"hybrid.operation_plan.path",
                "Operation plans require one more mode than edge and at least one mode"};
        if(std::any_of(path.modes.begin(),path.modes.end(),[](const auto& mode) {
               return mode.value.empty();
           }) || std::any_of(path.edges.begin(),path.edges.end(),[](const auto& edge) {
               return edge.value.empty();
           }))
            return Diagnostic{DiagnosticCode::invalid_input,"hybrid.operation_plan.identities",
                "Operation plans require nonempty mode and edge identities"};
        plan.push_back(HybridPlannedModeOperation{path_index,
            HybridPlannedModeOperationKind::initial_state,0,path.modes.front()});
        for(std::size_t stage=0;stage<path.edges.size();++stage) {
            plan.push_back(HybridPlannedModeOperation{path_index,
                HybridPlannedModeOperationKind::post_state_invariant,stage,path.modes[stage]});
            plan.push_back(HybridPlannedModeOperation{path_index,
                HybridPlannedModeOperationKind::mode_flow,stage,path.modes[stage]});
            plan.push_back(HybridPlannedModeOperation{path_index,
                HybridPlannedModeOperationKind::continuous_control,stage,path.modes[stage]});
            plan.push_back(HybridPlannedModeOperation{path_index,
                HybridPlannedModeOperationKind::pre_reset_invariant,stage+1,path.modes[stage]});
            plan.push_back(HybridPlannedEdgeOperation{path_index,
                HybridPlannedEdgeOperationKind::transition_guard,stage,path.edges[stage]});
            plan.push_back(HybridPlannedEdgeOperation{path_index,
                HybridPlannedEdgeOperationKind::reset_relation,stage,path.edges[stage]});
        }
        plan.push_back(HybridPlannedModeOperation{path_index,
            HybridPlannedModeOperationKind::post_state_invariant,path.edges.size(),path.modes.back()});
    }
    return plan;
}

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
    if (dimension == 0 && labels.empty()) return true;
    if (labels.size() != dimension) return false;
    std::unordered_set<std::string> seen;
    for (const auto& label : labels)
        if (label.empty() || !seen.insert(label).second) return false;
    return true;
}

}

HybridPathEnumeration enumerate_hybrid_paths(const HybridSystem& system,
    const HybridModeId& initial_mode, const std::vector<HybridModeId>& allowed_terminal_modes,
    HybridEnumerationLimits limits,std::stop_token cancellation) {
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,"Hybrid path enumeration was cancelled before validation"};
    if (system.horizon == std::numeric_limits<std::size_t>::max())
        return invalid("hybrid.horizon", "Horizon is too large to represent T+1 state stages");
    if (system.horizon > limits.max_horizon)
        return Diagnostic{DiagnosticCode::unsupported,"hybrid.horizon.limit",
            "The requested horizon exceeds the caller's admitted stage limit"};
    std::unordered_set<std::string> mode_ids;
    for (const auto& mode : system.modes) {
        if(cancellation.stop_requested())
            return OperationStopped{StopReason::cancelled,"Hybrid path enumeration was cancelled while validating modes"};
        if (mode.id.value.empty() || !mode_ids.insert(mode.id.value).second)
            return invalid("hybrid.modes", "Mode IDs must be unique and nonempty");
    }
    if (!find_mode(system, initial_mode))
        return invalid("hybrid.initial_mode", "The request initial mode is not in the system catalogue");

    std::unordered_set<std::string> edge_ids;
    for (const auto& edge : system.edges) {
        if(cancellation.stop_requested())
            return OperationStopped{StopReason::cancelled,"Hybrid path enumeration was cancelled while validating edges"};
        if (edge.id.value.empty() || !edge_ids.insert(edge.id.value).second)
            return invalid("hybrid.edges", "Transition-edge IDs must be unique and nonempty");
        if (!find_mode(system, edge.source) || !find_mode(system, edge.target))
            return invalid("hybrid.edges", "Each transition edge must reference catalogued source and target modes");
    }

    std::unordered_set<std::string> terminal_ids;
    for (const auto& mode : allowed_terminal_modes) {
        if(cancellation.stop_requested())
            return OperationStopped{StopReason::cancelled,"Hybrid path enumeration was cancelled while validating terminal modes"};
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
        if(cancellation.stop_requested())
            return OperationStopped{StopReason::cancelled,"Hybrid path enumeration was cancelled while computing reachable modes"};
        for (const auto& edge : system.edges) {
            if(cancellation.stop_requested())
                return OperationStopped{StopReason::cancelled,"Hybrid path enumeration was cancelled while computing reachable modes"};
            if (can_reach[remaining-1].contains(edge.target.value))
                can_reach[remaining].insert(edge.source.value);
        }
    }
    if (!can_reach[system.horizon].contains(initial_mode.value))
        return std::vector<HybridPath>{};

    std::vector<HybridPath> result;
    HybridPath path{{initial_mode}, {}};
    struct Frame { std::size_t stage; HybridModeId mode; std::size_t next_edge; };
    std::vector<Frame> stack{{0,initial_mode,0}};
    while (!stack.empty()) {
        if(cancellation.stop_requested())
            return OperationStopped{StopReason::cancelled,"Hybrid path enumeration stopped; no partial path list was returned"};
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

HybridCapabilityReportResult report_hybrid_capability(const HybridSystem& system,
    const HybridRequest& request,HybridEnumerationLimits limits,std::stop_token cancellation) {
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,"Hybrid capability reporting was cancelled before inspection"};
    HybridCapabilityReport report;
    report.horizon=system.horizon;
    report.mode_count=system.modes.size();
    report.edge_count=system.edges.size();
    report.limits=limits;
    report.modes.reserve(system.modes.size());
    for(const auto& mode:system.modes) {
        if(cancellation.stop_requested())
            return OperationStopped{StopReason::cancelled,"Hybrid capability reporting was cancelled while collecting mode dimensions"};
        report.maximum_state_dimension=std::max(report.maximum_state_dimension,mode.state_dimension);
        report.maximum_control_dimension=std::max(report.maximum_control_dimension,mode.control_dimension);
        report.modes.push_back({mode.id,mode.state_dimension,mode.control_dimension});
    }
    report.diagnostics=check_hybrid_profile(system,request);
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,"Hybrid capability reporting was cancelled during profile admission"};
    report.profile_admitted=report.diagnostics.empty();
    if(!report.profile_admitted) return report;
    if(cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled,"Hybrid capability reporting was cancelled before path enumeration"};
    const auto paths=enumerate_hybrid_paths(system,request.initial.mode,
        request.allowed_terminal_modes,limits,cancellation);
    if(const auto* stopped=std::get_if<OperationStopped>(&paths)) return *stopped;
    if(const auto* diagnostic=std::get_if<Diagnostic>(&paths)) {
        report.diagnostics.push_back(*diagnostic);
        return report;
    }
    report.complete_allowed_path_count=std::get<std::vector<HybridPath>>(paths).size();
    report.path_enumeration_completed=true;
    return report;
}

HybridRelationPreflightResult preflight_hybrid_path_relations(
    const HybridSystem& system,const HybridRequest& request,
    std::span<const HybridPath> paths,HybridRelationLimits limits,
    std::stop_token cancellation) {
    const auto profile_errors=check_hybrid_profile(system,request);
    if(!profile_errors.empty()) return profile_errors;
    const auto stopped=[] {
        return HybridRelationPreflightResult{OperationStopped{StopReason::cancelled,
            "Hybrid relation preflight was cancelled; no path relations were constructed"}};
    };
    const auto max=std::numeric_limits<std::size_t>::max();
    for(const auto& path:paths) {
        if(cancellation.stop_requested()) return stopped();
        std::string path_context="Path";
        for(const auto& edge:path.edges)
            path_context += " edge "+edge.value;
        auto fail=[&](Diagnostic diagnostic)->HybridRelationPreflightResult {
            diagnostic.explanation=path_context+": "+diagnostic.explanation;
            return HybridPathCompositionFailureReport{path,limits,{},std::move(diagnostic)};
        };
        auto fail_stage=[&](Diagnostic diagnostic,std::size_t stage,
            std::optional<HybridEdgeId> edge=std::nullopt)->HybridRelationPreflightResult {
            diagnostic.explanation="stage "+std::to_string(stage)+
                (edge?" edge "+edge->value:std::string{})+": "+diagnostic.explanation;
            return fail(std::move(diagnostic));
        };
        if(path.modes.size()!=system.horizon+1 || path.edges.size()!=system.horizon ||
           path.modes.empty() || path.modes.front()!=request.initial.mode ||
           std::find(request.allowed_terminal_modes.begin(),request.allowed_terminal_modes.end(),path.modes.back())==
               request.allowed_terminal_modes.end())
            return fail(invalid("hybrid.path","Path must match the horizon and request endpoints"));
        std::vector<const HybridMode*> modes;
        std::vector<const HybridTransitionEdge*> edges;
        modes.reserve(path.modes.size());
        edges.reserve(path.edges.size());
        for(const auto& id:path.modes) {
            const auto* mode=find_mode(system,id);
            if(!mode) return fail(invalid("hybrid.path.modes","Path references an unknown mode"));
            modes.push_back(mode);
        }
        std::size_t width=modes.front()->state_dimension;
        if(width>limits.max_variables)
            return fail_stage({DiagnosticCode::unsupported,"hybrid.relation.variables","Joint relation exceeds its variable limit"},0);
        for(std::size_t stage=0;stage<system.horizon;++stage) {
            if(cancellation.stop_requested()) return stopped();
            const auto found=std::find_if(system.edges.begin(),system.edges.end(),[&](const auto& edge) {
                return edge.id==path.edges[stage];
            });
            if(found==system.edges.end() || found->source!=path.modes[stage] ||
               found->target!=path.modes[stage+1])
                return fail(invalid("hybrid.path.edges","Each path edge must connect adjacent modes"));
            edges.push_back(&*found);
            for(const auto amount:{modes[stage]->control_dimension,modes[stage]->state_dimension,
                                   modes[stage+1]->state_dimension}) {
                if(width>max-amount || width+amount>limits.max_variables)
                    return fail_stage({DiagnosticCode::unsupported,"hybrid.relation.variables","Joint relation exceeds its variable limit"},stage,path.edges[stage]);
                width+=amount;
            }
        }
        std::size_t rows=0;
        auto add_rows=[&](std::size_t amount)->bool {
            if(rows>max-amount || rows+amount>limits.max_rows) return false;
            rows+=amount;
            return width==0 || rows<=limits.max_matrix_elements/width;
        };
        auto h_rows=[&](const sets::HRepresentation& h)->std::variant<std::size_t,Diagnostic> {
            const auto inequalities=h.inequalities.rows();
            const auto equalities=h.equalities.rows();
            if(inequalities>max-equalities)
                return Diagnostic{DiagnosticCode::unsupported,"hybrid.relation.rows",
                    "H-representation row count overflows the supported size range"};
            return inequalities+equalities;
        };
        auto set_rows=[&](const AdmissibleSet& set,const char* field)->std::variant<std::size_t,Diagnostic> {
            if(std::holds_alternative<EmptySet>(set)) return std::size_t{1};
            if(std::holds_alternative<UniversalSet>(set)) return std::size_t{0};
            if(const auto* singleton=std::get_if<Singleton>(&set)) return singleton->point.size();
            const auto frozen=sets::from_handle(std::get<SetHandle>(set));
            if(const auto* diagnostic=std::get_if<Diagnostic>(&frozen)) return *diagnostic;
            const auto& representation=std::get<sets::SetData>(frozen).representation();
            if(const auto* h=std::get_if<sets::HRepresentation>(&representation))
                return h_rows(*h);
            if(const auto* singleton=std::get_if<sets::SingletonRepresentation>(&representation))
                return singleton->point.size();
            if(std::holds_alternative<sets::EmptyRepresentation>(representation)) return std::size_t{1};
            if(std::holds_alternative<sets::UniversalRepresentation>(representation)) return std::size_t{0};
            return Diagnostic{DiagnosticCode::unsupported,field,
                "Direct joint composition requires H, empty, universal, or singleton sets; V conversion is not implicit"};
        };
        auto reset_rows=[&](const SetHandle& handle)->std::variant<std::size_t,Diagnostic> {
            const auto frozen=sets::from_handle(handle);
            if(const auto* diagnostic=std::get_if<Diagnostic>(&frozen)) return *diagnostic;
            const auto& representation=std::get<sets::SetData>(frozen).representation();
            if(const auto* h=std::get_if<sets::HRepresentation>(&representation))
                return h_rows(*h);
            if(const auto* singleton=std::get_if<sets::SingletonRepresentation>(&representation))
                return singleton->point.size();
            if(std::holds_alternative<sets::EmptyRepresentation>(representation)) return std::size_t{1};
            if(std::holds_alternative<sets::UniversalRepresentation>(representation)) return std::size_t{0};
            return Diagnostic{DiagnosticCode::unsupported,"hybrid.reset.representation",
                "Direct joint composition requires reset relations in H form"};
        };
        auto admit_set=[&](const AdmissibleSet& set,const char* field)->std::optional<Diagnostic> {
            const auto count=set_rows(set,field);
            if(const auto* diagnostic=std::get_if<Diagnostic>(&count)) return *diagnostic;
            if(!add_rows(std::get<std::size_t>(count)))
                return Diagnostic{DiagnosticCode::unsupported,"hybrid.relation.rows",
                    "Joint relation exceeds its row or matrix-element limit"};
            return std::nullopt;
        };
        if(!add_rows(modes.front()->state_dimension))
            return fail_stage({DiagnosticCode::unsupported,"hybrid.relation.rows","Joint relation exceeds its row or matrix-element limit"},0);
        for(std::size_t stage=0;stage<system.horizon;++stage) {
            if(cancellation.stop_requested()) return stopped();
            const auto& mode=*modes[stage];
            const auto& edge=*edges[stage];
            if(auto d=admit_set(mode.invariants[stage],"hybrid.invariant.representation"))
                return fail_stage(*d,stage,edge.id);
            const auto& flow=std::holds_alternative<LinearStage>(mode.flow)?
                std::get<LinearStage>(mode.flow):std::get<std::vector<LinearStage>>(mode.flow)[stage];
            if(!add_rows(flow.A.rows))
                return fail_stage({DiagnosticCode::unsupported,"hybrid.relation.rows","Joint relation exceeds its row or matrix-element limit"},stage,edge.id);
            if(auto d=admit_set(mode.control_sets[stage],"hybrid.control.representation"))
                return fail_stage(*d,stage,edge.id);
            if(auto d=admit_set(mode.invariants[stage+1],"hybrid.invariant.representation"))
                return fail_stage(*d,stage+1,edge.id);
            if(auto d=admit_set(edge.guards[stage],"hybrid.guard.representation"))
                return fail_stage(*d,stage,edge.id);
            const auto reset=reset_rows(edge.reset_relations[stage]);
            if(const auto* diagnostic=std::get_if<Diagnostic>(&reset))
                return fail_stage(*diagnostic,stage,edge.id);
            if(!add_rows(std::get<std::size_t>(reset)))
                return fail_stage({DiagnosticCode::unsupported,"hybrid.relation.rows","Joint relation exceeds its row or matrix-element limit"},stage,edge.id);
        }
        if(auto d=admit_set(modes.back()->invariants[system.horizon],"hybrid.invariant.representation"))
            return fail_stage(*d,system.horizon);
    }
    if(cancellation.stop_requested()) return stopped();
    return std::monostate{};
}

namespace {
HybridRelationResult compose_hybrid_path_relation_impl(const HybridSystem& system,
    const HybridRequest& request, const HybridPath& path, HybridRelationLimits limits,
    std::stop_token cancellation,std::vector<HybridRelationOperationRecord>* operations) {
    const auto errors = check_hybrid_profile(system, request);
    if (!errors.empty()) return errors.front();
    const auto stopped = [] { return OperationStopped{StopReason::cancelled,
        "Hybrid joint-relation construction was cancelled; no relation was returned"}; };
    if (cancellation.stop_requested()) return stopped();
    if (path.modes.size() != system.horizon + 1 || path.edges.size() != system.horizon ||
        path.modes.front() != request.initial.mode ||
        std::find(request.allowed_terminal_modes.begin(), request.allowed_terminal_modes.end(), path.modes.back()) == request.allowed_terminal_modes.end())
        return invalid("hybrid.path", "Path must match the horizon and request endpoints");
    const auto max = std::numeric_limits<std::size_t>::max();
    std::vector<const HybridMode*> modes;
    std::vector<const HybridTransitionEdge*> edges;
    for (const auto& id : path.modes) {
        const auto* mode = find_mode(system, id);
        if (!mode) return invalid("hybrid.path.modes", "Path references an unknown mode");
        modes.push_back(mode);
    }
    std::vector<std::size_t> state_offsets(system.horizon + 1), control_offsets(system.horizon), pre_offsets(system.horizon);
    std::size_t width = 0;
    auto reserve = [&](std::size_t amount, std::size_t& offset) {
        if (width > max - amount) return false;
        offset = width; width += amount; return width <= limits.max_variables;
    };
    if (!reserve(modes[0]->state_dimension, state_offsets[0]))
        return Diagnostic{DiagnosticCode::unsupported,"hybrid.relation.variables","Joint relation exceeds its variable limit"};
    for (std::size_t t=0; t<system.horizon; ++t) {
        const auto found = std::find_if(system.edges.begin(),system.edges.end(),[&](const auto& e){return e.id==path.edges[t];});
        if (found==system.edges.end() || found->source!=path.modes[t] || found->target!=path.modes[t+1])
            return invalid("hybrid.path.edges", "Each path edge must connect its adjacent modes");
        edges.push_back(&*found);
        if (!reserve(modes[t]->control_dimension,control_offsets[t]) ||
            !reserve(modes[t]->state_dimension,pre_offsets[t]) ||
            !reserve(modes[t+1]->state_dimension,state_offsets[t+1]))
            return Diagnostic{DiagnosticCode::unsupported,"hybrid.relation.variables","Joint relation exceeds its variable limit"};
    }
    auto preflight = [](const SetHandle& handle, const char* field) -> std::optional<Diagnostic> {
        const auto frozen=sets::from_handle(handle);
        if(const auto* d=std::get_if<Diagnostic>(&frozen)) return *d;
        const auto rep=std::get<sets::SetData>(frozen).representation();
        if(std::holds_alternative<sets::HRepresentation>(rep) ||
           std::holds_alternative<sets::EmptyRepresentation>(rep) ||
           std::holds_alternative<sets::UniversalRepresentation>(rep) ||
           std::holds_alternative<sets::SingletonRepresentation>(rep)) return std::nullopt;
        return Diagnostic{DiagnosticCode::unsupported,field,
            "Direct joint composition requires H, empty, universal, or singleton sets; V conversion is not implicit"};
    };
    auto preflight_set = [&](const AdmissibleSet& set, const char* field) -> std::optional<Diagnostic> {
        if(const auto* handle=std::get_if<SetHandle>(&set)) return preflight(*handle,field);
        return std::nullopt;
    };
    for(std::size_t t=0;t<system.horizon;++t) {
        if(auto d=preflight_set(modes[t]->control_sets[t],"hybrid.control.representation")) return *d;
        if(auto d=preflight_set(modes[t]->invariants[t],"hybrid.invariant.representation")) return *d;
        if(auto d=preflight_set(modes[t]->invariants[t+1],"hybrid.invariant.representation")) return *d;
        if(auto d=preflight_set(edges[t]->guards[t],"hybrid.guard.representation")) return *d;
        if(auto d=preflight(edges[t]->reset_relations[t],"hybrid.reset.representation")) return *d;
    }
    if(auto d=preflight_set(modes.back()->invariants[system.horizon],"hybrid.invariant.representation")) return *d;
    std::vector<Vector> inequalities, equalities;
    Vector bounds, equality_values;
    auto append = [&](Vector row, double rhs, bool equality) -> bool {
        if(cancellation.stop_requested()) return false;
        const auto row_count = inequalities.size()+equalities.size();
        if (row_count >= limits.max_rows ||
            (width != 0 && row_count + 1 > limits.max_matrix_elements / width)) return false;
        (equality ? equalities : inequalities).push_back(std::move(row));
        (equality ? equality_values : bounds).push_back(rhs); return true;
    };
    auto add_set = [&](const AdmissibleSet& set, std::size_t offset, std::size_t dimension) -> std::optional<Diagnostic> {
        auto empty = [&] { Vector row(width); if(!append(std::move(row),-1,false)) return false; return true; };
        auto singleton = [&](std::span<const double> point) {
            for (std::size_t j=0;j<dimension;++j) { Vector row(width); row[offset+j]=1; if(!append(std::move(row),point[j],true)) return false; }
            return true;
        };
        auto hrep = [&](const sets::HRepresentation& h) {
            for(std::size_t i=0;i<h.inequalities.rows();++i) { Vector row(width); for(std::size_t j=0;j<dimension;++j) row[offset+j]=h.inequalities(i,j); if(!append(std::move(row),h.upper_bounds[i],false)) return false; }
            for(std::size_t i=0;i<h.equalities.rows();++i) { Vector row(width); for(std::size_t j=0;j<dimension;++j) row[offset+j]=h.equalities(i,j); if(!append(std::move(row),h.equality_values[i],true)) return false; }
            return true;
        };
        bool supported = true;
        if (std::holds_alternative<EmptySet>(set)) supported=empty();
        else if (std::holds_alternative<UniversalSet>(set)) { }
        else if (const auto* point=std::get_if<Singleton>(&set)) supported=singleton(point->point);
        else {
            const auto frozen=sets::from_handle(std::get<SetHandle>(set));
            if(const auto* d=std::get_if<Diagnostic>(&frozen)) return *d;
            const auto rep=std::get<sets::SetData>(frozen).representation();
            if(const auto* h=std::get_if<sets::HRepresentation>(&rep)) supported=hrep(*h);
            else if(const auto* singleton_rep=std::get_if<sets::SingletonRepresentation>(&rep)) supported=singleton(singleton_rep->point.values());
            else if(std::holds_alternative<sets::EmptyRepresentation>(rep)) supported=empty();
            else if(!std::holds_alternative<sets::UniversalRepresentation>(rep))
                return Diagnostic{DiagnosticCode::unsupported,"hybrid.relation.set_representation","Direct joint composition requires H, empty, universal, or singleton sets; V conversion is not implicit"};
        }
        if (!supported) return Diagnostic{DiagnosticCode::unsupported,"hybrid.relation.rows","Joint relation exceeds its row limit"};
        return std::nullopt;
    };
    auto add_linear = [&](const LinearStage& step,std::size_t x,std::size_t u,std::size_t pre) -> bool {
        for(std::size_t i=0;i<step.A.rows;++i) {
            Vector row(width); row[pre+i]=1;
            for(std::size_t j=0;j<step.A.cols;++j) row[x+j]-=step.A.values[i*step.A.cols+j];
            for(std::size_t j=0;j<step.B.cols;++j) row[u+j]-=step.B.values[i*step.B.cols+j];
            if(!append(std::move(row),step.offset[i],true)) return false;
        }
        return true;
    };
    auto add_reset = [&](const SetHandle& handle,std::size_t pre,std::size_t post,std::size_t npre,std::size_t npost)->std::optional<Diagnostic> {
        const auto frozen=sets::from_handle(handle);
        if(const auto* d=std::get_if<Diagnostic>(&frozen)) return *d;
        const auto rep=std::get<sets::SetData>(frozen).representation();
        if(std::holds_alternative<sets::UniversalRepresentation>(rep)) return std::nullopt;
        if(std::holds_alternative<sets::EmptyRepresentation>(rep)) {
            if(!append(Vector(width),-1,false)) return Diagnostic{DiagnosticCode::unsupported,"hybrid.relation.rows","Joint relation exceeds its row limit"};
            return std::nullopt;
        }
        if(const auto* point=std::get_if<sets::SingletonRepresentation>(&rep)) {
            for(std::size_t j=0;j<npre+npost;++j) {
                Vector row(width);
                if(j<npre) row[pre+j]=1; else row[post+(j-npre)]=1;
                if(!append(std::move(row),point->point[j],true)) return Diagnostic{DiagnosticCode::unsupported,"hybrid.relation.rows","Joint relation exceeds its row limit"};
            }
            return std::nullopt;
        }
        const auto* h=std::get_if<sets::HRepresentation>(&rep);
        if(!h) return Diagnostic{DiagnosticCode::unsupported,"hybrid.reset.representation","Direct joint composition requires reset relations in H form"};
        auto add_rows=[&](numeric::MatrixView matrix,numeric::VectorView rhs,bool eq) {
            for(std::size_t i=0;i<matrix.rows();++i) { Vector row(width);
                for(std::size_t j=0;j<npre;++j) row[pre+j]=matrix(i,j);
                for(std::size_t j=0;j<npost;++j) row[post+j]=matrix(i,npre+j);
                if(!append(std::move(row),rhs[i],eq)) return false;
            } return true;
        };
        if(!add_rows(h->inequalities,h->upper_bounds,false)||!add_rows(h->equalities,h->equality_values,true))
            return Diagnostic{DiagnosticCode::unsupported,"hybrid.relation.rows","Joint relation exceeds its row limit"};
        return std::nullopt;
    };
    auto row_count=[&] { return inequalities.size()+equalities.size(); };
    auto record_operation=[&](HybridRelationOperationKind operation,std::size_t stage,
        std::optional<HybridModeId> mode,std::optional<HybridEdgeId> edge,std::size_t rows_before) {
        if(!operations) return;
        const auto total_rows=row_count();
        operations->push_back({operation,stage,std::move(mode),std::move(edge),
            "csl.model.hybrid.joint-h-composer","1",width,total_rows-rows_before,
            total_rows,total_rows*width});
    };
    auto rows_before=row_count();
    auto initial_error=add_set(Singleton{request.initial.state},state_offsets[0],modes[0]->state_dimension);
    if(initial_error) return cancellation.stop_requested()?HybridRelationResult{stopped()}:HybridRelationResult{*initial_error};
    record_operation(HybridRelationOperationKind::initial_state,0,modes[0]->id,{},rows_before);
    for(std::size_t t=0;t<=system.horizon;++t) {
        if(cancellation.stop_requested()) return stopped();
        rows_before=row_count();
        if(auto e=add_set(modes[t]->invariants[t],state_offsets[t],modes[t]->state_dimension))
            return cancellation.stop_requested()?HybridRelationResult{stopped()}:HybridRelationResult{*e};
        record_operation(HybridRelationOperationKind::post_state_invariant,t,modes[t]->id,{},rows_before);
        if(t==system.horizon) continue;
        const auto& mode=*modes[t];
        const auto& flow=std::holds_alternative<LinearStage>(mode.flow)?std::get<LinearStage>(mode.flow):std::get<std::vector<LinearStage>>(mode.flow)[t];
        rows_before=row_count();
        if(!add_linear(flow,state_offsets[t],control_offsets[t],pre_offsets[t])) {
            if(cancellation.stop_requested()) return stopped();
            return Diagnostic{DiagnosticCode::unsupported,"hybrid.relation.rows","Joint relation exceeds its row limit"};
        }
        record_operation(HybridRelationOperationKind::mode_flow,t,mode.id,{},rows_before);
        rows_before=row_count();
        if(auto e=add_set(mode.control_sets[t],control_offsets[t],mode.control_dimension))
            return cancellation.stop_requested()?HybridRelationResult{stopped()}:HybridRelationResult{*e};
        record_operation(HybridRelationOperationKind::continuous_control,t,mode.id,{},rows_before);
        rows_before=row_count();
        if(auto e=add_set(mode.invariants[t+1],pre_offsets[t],mode.state_dimension))
            return cancellation.stop_requested()?HybridRelationResult{stopped()}:HybridRelationResult{*e};
        record_operation(HybridRelationOperationKind::pre_reset_invariant,t+1,mode.id,{},rows_before);
        rows_before=row_count();
        if(auto e=add_set(edges[t]->guards[t],pre_offsets[t],mode.state_dimension))
            return cancellation.stop_requested()?HybridRelationResult{stopped()}:HybridRelationResult{*e};
        record_operation(HybridRelationOperationKind::transition_guard,t,{},edges[t]->id,rows_before);
        rows_before=row_count();
        if(auto e=add_reset(edges[t]->reset_relations[t],pre_offsets[t],state_offsets[t+1],mode.state_dimension,modes[t+1]->state_dimension))
            return cancellation.stop_requested()?HybridRelationResult{stopped()}:HybridRelationResult{*e};
        record_operation(HybridRelationOperationKind::reset_relation,t,{},edges[t]->id,rows_before);
    }
    if(cancellation.stop_requested()) return stopped();
    std::vector<std::string> coordinate_labels(width);
    auto label_block=[&](std::size_t offset,const HybridMode& mode,const std::vector<std::string>& labels,
        std::size_t stage,const char* role) {
        for(std::size_t j=0;j<labels.size();++j) {
            const auto& coordinate=labels[j];
            coordinate_labels[offset+j]=std::string(role)+":"+std::to_string(stage)+":"+
                std::to_string(mode.id.value.size())+":"+mode.id.value+":"+
                std::to_string(coordinate.size())+":"+coordinate;
        }
    };
    label_block(state_offsets[0],*modes[0],modes[0]->state_coordinate_labels,0,"post");
    for(std::size_t t=0;t<system.horizon;++t) {
        label_block(control_offsets[t],*modes[t],modes[t]->control_coordinate_labels,t,"control");
        label_block(pre_offsets[t],*modes[t],modes[t]->state_coordinate_labels,t+1,"pre");
        label_block(state_offsets[t+1],*modes[t+1],modes[t+1]->state_coordinate_labels,t+1,"post");
    }
    Matrix A{inequalities.size(),width,{}}; A.values.reserve(inequalities.size()*width);
    for(const auto& row:inequalities) A.values.insert(A.values.end(),row.begin(),row.end());
    Matrix E{equalities.size(),width,{}}; E.values.reserve(equalities.size()*width);
    for(const auto& row:equalities) E.values.insert(E.values.end(),row.begin(),row.end());
    auto ai=numeric::snapshot(A); auto ei=numeric::snapshot(E);
    auto ab=numeric::snapshot_vector(bounds); auto eb=numeric::snapshot_vector(equality_values);
    if(!std::holds_alternative<numeric::MatrixView>(ai)||!std::holds_alternative<numeric::MatrixView>(ei)||
       !std::holds_alternative<numeric::VectorView>(ab)||!std::holds_alternative<numeric::VectorView>(eb))
        return Diagnostic{DiagnosticCode::invalid_input,"hybrid.relation.storage","Joint relation data failed numeric validation"};
    std::string relation_id = "hybrid-joint";
    for (const auto& edge : path.edges)
        relation_id += ":" + std::to_string(edge.value.size()) + ":" + edge.value;
    auto made=sets::make_h({SetId{std::move(relation_id)},width,std::move(coordinate_labels)},
        {std::get<numeric::MatrixView>(ai),std::get<numeric::VectorView>(ab),std::get<numeric::MatrixView>(ei),std::get<numeric::VectorView>(eb)});
    if(const auto* d=std::get_if<Diagnostic>(&made)) return *d;
    if(cancellation.stop_requested()) return stopped();
    return std::get<sets::SetData>(std::move(made));
}
} // namespace

HybridRelationResult compose_hybrid_path_relation(const HybridSystem& system,
    const HybridRequest& request,const HybridPath& path,HybridRelationLimits limits,
    std::stop_token cancellation) {
    return compose_hybrid_path_relation_impl(system,request,path,limits,cancellation,nullptr);
}

HybridComposedPathRelationResult compose_hybrid_path_relation_with_report(
    const HybridSystem& system,const HybridRequest& request,const HybridPath& path,
    HybridRelationLimits limits,std::stop_token cancellation) {
    std::vector<HybridRelationOperationRecord> operations;
    auto result=compose_hybrid_path_relation_impl(system,request,path,limits,cancellation,&operations);
    if(const auto* diagnostic=std::get_if<Diagnostic>(&result))
        return HybridPathCompositionFailureReport{path,limits,std::move(operations),*diagnostic};
    if(const auto* stopped=std::get_if<OperationStopped>(&result))
        return HybridPathCompositionFailureReport{path,limits,std::move(operations),*stopped};
    return HybridComposedPathRelation{std::get<sets::SetData>(std::move(result)),limits,std::move(operations)};
}

HybridObjectiveLiftResult lift_hybrid_terminal_objective(const HybridSystem& system,
    const HybridRequest& request, const HybridPath& path, HybridRelationLimits limits) {
    const auto errors=check_hybrid_profile(system,request);
    if(!errors.empty()) return errors.front();
    if(path.modes.size()!=system.horizon+1 || path.edges.size()!=system.horizon ||
       path.modes.front()!=request.initial.mode ||
       std::find(request.allowed_terminal_modes.begin(),request.allowed_terminal_modes.end(),path.modes.back())==request.allowed_terminal_modes.end())
        return invalid("hybrid.path","Path must match the horizon and request endpoints");
    std::vector<const HybridMode*> modes;
    modes.reserve(path.modes.size());
    for(const auto& id:path.modes) {
        const auto* mode=find_mode(system,id);
        if(!mode) return invalid("hybrid.path.modes","Path references an unknown mode");
        modes.push_back(mode);
    }
    std::size_t width=modes.front()->state_dimension;
    for(std::size_t t=0;t<system.horizon;++t) {
        const auto edge=std::find_if(system.edges.begin(),system.edges.end(),[&](const auto& candidate){return candidate.id==path.edges[t];});
        if(edge==system.edges.end() || edge->source!=path.modes[t] || edge->target!=path.modes[t+1])
            return invalid("hybrid.path.edges","Each path edge must connect its adjacent modes");
        for(const auto amount:{modes[t]->control_dimension,modes[t]->state_dimension,modes[t+1]->state_dimension}) {
            if(width>std::numeric_limits<std::size_t>::max()-amount)
                return invalid("hybrid.objective.width","Joint coordinate count overflows size_t");
            width+=amount;
        }
    }
    if(width>limits.max_variables)
        return Diagnostic{DiagnosticCode::unsupported,"hybrid.objective.variables","Lifted objective exceeds its variable limit"};
    const auto terminal_dimension=modes.back()->state_dimension;
    const auto terminal_offset=width-terminal_dimension;
    const auto objective=std::find_if(request.terminal_objectives.begin(),request.terminal_objectives.end(),
        [&](const HybridModeObjective& entry){return entry.mode==path.modes.back();});
    if(objective==request.terminal_objectives.end())
        return invalid("hybrid.terminal_objectives","Path terminal mode has no admitted objective");
    return std::visit([&](const auto& value)->HybridObjectiveLiftResult {
        using T=std::decay_t<decltype(value)>;
        if constexpr(std::is_same_v<T,LinearTerminal>) {
            Vector coefficients(width);
            std::copy(value.coefficients.begin(),value.coefficients.end(),coefficients.begin()+static_cast<std::ptrdiff_t>(terminal_offset));
            return TerminalObjective{LinearTerminal{std::move(coefficients),value.offset}};
        } else if constexpr(std::is_same_v<T,QuadraticTerminal>) {
            if((width!=0 && width>std::numeric_limits<std::size_t>::max()/width) ||
               width*width>limits.max_matrix_elements)
                return Diagnostic{DiagnosticCode::unsupported,"hybrid.objective.storage","Lifted quadratic objective exceeds its storage limit"};
            Matrix q{width,width,Vector(width*width)};
            Vector linear(width);
            for(std::size_t i=0;i<terminal_dimension;++i) {
                linear[terminal_offset+i]=value.linear[i];
                for(std::size_t j=0;j<terminal_dimension;++j)
                    q.values[(terminal_offset+i)*width+terminal_offset+j]=value.Q.values[i*terminal_dimension+j];
            }
            return TerminalObjective{QuadraticTerminal{std::move(q),std::move(linear),value.offset}};
        } else {
            if((width!=0 && value.map.rows>std::numeric_limits<std::size_t>::max()/width) ||
               value.map.rows*width>limits.max_matrix_elements)
                return Diagnostic{DiagnosticCode::unsupported,"hybrid.objective.storage","Lifted residual map exceeds its storage limit"};
            Matrix map{value.map.rows,width,Vector(value.map.rows*width)};
            for(std::size_t i=0;i<value.map.rows;++i)
                for(std::size_t j=0;j<terminal_dimension;++j)
                    map.values[i*width+terminal_offset+j]=value.map.values[i*terminal_dimension+j];
            return TerminalObjective{ResidualNormTerminal{std::move(map),value.target}};
        }
    },objective->objective);
}

} // namespace csl::model
