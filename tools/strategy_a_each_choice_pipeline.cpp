#include <csl/adapters/convex/highs.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <csl/adapters/polyhedral/qhull.hpp>
#include <csl/geometry/affine_sum.hpp>
#include <csl/geometry/basis_reuse_reducer.hpp>
#include <csl/geometry/box_parallelotope.hpp>
#include <csl/geometry/hull_reducer.hpp>
#include <csl/geometry/legacy_btulshor.hpp>
#include <csl/geometry/polyhedral_projection.hpp>
#include <csl/geometry/quickhull_2d.hpp>
#include <csl/geometry/source_index_hull.hpp>
#include <csl/optimization/linear_program.hpp>
#include <csl/optimization/phase_one.hpp>
#include <csl/problem/resolved_problem.hpp>
#include <csl/registry/strategy_catalogue.hpp>
#include <csl/synthesis/control_recovery.hpp>
#include <csl/synthesis/strategy_a/strategy.hpp>
#include <csl/synthesis/terminal_minimizers.hpp>

#include <algorithm>
#include <atomic>
#include <cmath>
#include <functional>
#include <iomanip>
#include <iostream>
#include <memory>
#include <set>
#include <sstream>
#include <stdexcept>

#ifndef CSL_PIPELINE_HAS_HIGHS
#define CSL_PIPELINE_HAS_HIGHS 0
#endif
#ifndef CSL_PIPELINE_HAS_QHULL
#define CSL_PIPELINE_HAS_QHULL 0
#endif

namespace {
using namespace csl;

std::string matrix_text(const numeric::MatrixView& matrix);
std::optional<double> smallest_nonzero(const numeric::MatrixView& matrix);

std::string quote(std::string_view value) {
    std::ostringstream out;
    out << '"';
    for (const unsigned char ch : value) {
        switch (ch) {
        case '"': out << "\\\""; break;
        case '\\': out << "\\\\"; break;
        case '\n': out << "\\n"; break;
        case '\r': out << "\\r"; break;
        case '\t': out << "\\t"; break;
        default:
            if (ch < 0x20) out << "\\u00" << "0123456789abcdef"[ch >> 4] << "0123456789abcdef"[ch & 0xf];
            else out << static_cast<char>(ch);
        }
    }
    out << '"';
    return out.str();
}

template<class T, class... E> T take(std::variant<T, E...> value) {
    if (!std::holds_alternative<T>(value))
        throw std::runtime_error("public pipeline rejected a declared probe input");
    return std::get<T>(std::move(value));
}

struct LPChoice {
    registry::Registration<registry::LPPort> registration;
    std::string profile;
};

class CountingLPWorkspace final : public LPWorkspace {
    std::unique_ptr<LPWorkspace> inner_;
    std::shared_ptr<std::atomic<std::size_t>> calls_;
    ProgramOutcome do_solve(const LinearProgram& program, const ExecutionContext& context) override {
        ++*calls_;
        return inner_->solve(program, context);
    }
public:
    CountingLPWorkspace(std::unique_ptr<LPWorkspace> inner,
        std::shared_ptr<std::atomic<std::size_t>> calls)
        : inner_(std::move(inner)), calls_(std::move(calls)) {}
    LPWorkspace& inner() noexcept { return *inner_; }
};

class CountingConvexWorkspace final : public ConvexWorkspace {
    std::unique_ptr<ConvexWorkspace> inner_;
    std::shared_ptr<std::atomic<std::size_t>> calls_;
    ProgramOutcome do_solve(const ConvexProgram& program, const ExecutionContext& context) override {
        ++*calls_;
        return inner_->solve(program, context);
    }
public:
    CountingConvexWorkspace(std::unique_ptr<ConvexWorkspace> inner,
        std::shared_ptr<std::atomic<std::size_t>> calls)
        : inner_(std::move(inner)), calls_(std::move(calls)) {}
};

class ObservingConverterWorkspace final : public RepresentationConverterWorkspace {
    std::unique_ptr<RepresentationConverterWorkspace> inner_;
    std::vector<std::string>* observations_;
    std::string upstream_provider_;
public:
    ObservingConverterWorkspace(std::unique_ptr<RepresentationConverterWorkspace> inner,
            std::vector<std::string>* observations, std::string upstream_provider)
        : inner_(std::move(inner)), observations_(observations), upstream_provider_(std::move(upstream_provider)) {}
    SetTransformOutcome convert(const ConversionRequest& request, const ExecutionContext& context) override {
        auto result=inner_->convert(request,context);
        if (const auto* converted=std::get_if<OperationResult>(&result)) {
            auto data=sets::from_handle(converted->output);
            if (const auto* set=std::get_if<sets::SetData>(&data)) {
                const auto representation=set->representation();
                if (const auto* h=std::get_if<sets::HRepresentation>(&representation)) {
                    const auto minimum=smallest_nonzero(h->inequalities);
                    std::ostringstream trace;
                    trace << std::setprecision(17) << "Qhull 8.0.2 Qx V-to-H conversion output: upstream="
                        << upstream_provider_ << "; request="
                        << request.identity.request.value << "; input=" << request.input.id.value
                        << "; output=" << converted->output.id.value << "; min_nonzero_A=";
                    if (minimum) trace << *minimum; else trace << "none";
                    trace << "; H=" << matrix_text(h->inequalities) << "; b=";
                    for (std::size_t i=0;i<h->upper_bounds.size();++i) { if(i)trace << ','; trace << h->upper_bounds[i]; }
                    const auto input=sets::from_handle(request.input);
                    if (const auto* input_set=std::get_if<sets::SetData>(&input)) {
                        const auto input_representation=input_set->representation();
                        if (const auto* v=std::get_if<sets::VRepresentation>(&input_representation))
                            trace << "; ordered_V_vertices=" << matrix_text(v->vertices)
                                << "; rays=" << matrix_text(v->rays);
                    }
                    for (const auto& assumption:converted->evidence.assumptions)
                        if (assumption.find("Qhull")!=std::string::npos) trace << "; algorithm=" << assumption;
                    observations_->push_back(trace.str());
                }
            }
        }
        return result;
    }
};

std::vector<LPChoice> lp_choices() {
    std::vector<LPChoice> choices;
#if CSL_PIPELINE_HAS_HIGHS
    choices.push_back({take(adapters::lp::make_highs_registration()), "highs"});
#endif
    choices.push_back({take(optimization::phase_one::make_registration()), "phase_one_bland"});
    const auto tie_options = [](const LinearProgram& program) {
        optimization::phase_one::Options options;
        options.structural_entering_priorities.resize(program.objective().size());
        for (std::size_t i = 0; i < options.structural_entering_priorities.size(); ++i)
            options.structural_entering_priorities[i] = static_cast<std::uint32_t>(i);
        return options;
    };
    registry::Registration<registry::LPPort> tie_registration{
        {ModuleId{"phase-one-priority-tie"}, "1"},
        [tie_options](const LinearProgram& program, const registry::Requirements& requirements) {
            return std::get<registry::Registration<registry::LPPort>>(
                optimization::phase_one::make_registration(tie_options(program))).capabilities(program, requirements);
        },
        [tie_options](const LinearProgram& program) {
            return std::get<registry::Registration<registry::LPPort>>(
                optimization::phase_one::make_registration(tie_options(program))).factory(program);
        },
        [tie_options](const LinearProgram& program, LPWorkspace& workspace) {
            return std::get<registry::Registration<registry::LPPort>>(
                optimization::phase_one::make_registration(tie_options(program))).basis_factory(program, workspace);
        }};
    choices.push_back({std::move(tie_registration), "phase_one_priority_tie"});
    return choices;
}

struct ReducerChoice {
    std::string id;
    std::function<registry::Registration<registry::HullReducerPort>(
        const registry::Registration<registry::LPPort>&)> registration;
};

std::vector<ReducerChoice> reducer_choices() {
    using LP = registry::Registration<registry::LPPort>;
    using Hull = registry::Registration<registry::HullReducerPort>;
    return {
        {"csl.hull.lp-membership", [](const LP&) { return geometry::make_lp_hull_reducer_registration(); }},
        {"csl.hull.phase-one-basis-bulk", [](const LP& lp) { return geometry::make_basis_reuse_hull_reducer_registration(lp); }},
        {"csl.hull.ordered-membership", [](const LP&) { return geometry::make_ordered_hull_reducer_registration(); }},
        {"csl.hull.itis17.a43-certified-basis-reuse", [](const LP&) { return geometry::make_itis17_a43_hull_reducer_registration(); }},
        {"csl.hull.itis17.a43-artificial-basis", [](const LP&) {
            return geometry::make_itis17_a43_paper_hull_reducer_registration(geometry::A43PivotRule::phase_one_order);
        }},
        {"csl.hull.itis17.a43-largest-norm-tie", [](const LP&) {
            return geometry::make_itis17_a43_paper_hull_reducer_registration(geometry::A43PivotRule::largest_norm_tie);
        }},
        {"csl.hull.itis17.a44-incremental-lp", [](const LP&) { return geometry::make_itis17_a44_hull_reducer_registration(); }},
        {"csl.hull.itis17.a44-paper-farthest-incremental-lp", [](const LP&) { return geometry::make_itis17_a44_paper_hull_reducer_registration(); }},
        {"csl.hull.grouped-membership", [](const LP&) { return geometry::make_grouped_hull_reducer_registration(); }},
        {"csl.hull.recursive-split-merge", [](const LP& lp) { return geometry::make_recursive_hull_reducer_registration(lp); }}
    };
}

struct BoxBounds2D {
    double x_lower;
    double x_upper;
    double y_lower;
    double y_upper;
};

struct ControlProblemShape {
    Vector initial_state;
    BoxBounds2D initial_state_box;
    BoxBounds2D control_box;
    BoxBounds2D next_state_box;
};

ControlProblemShape standard_control_problem_shape() {
    return {{0,0}, {-1,1,-1,1}, {0,1,0,1}, {0,1,0,1}};
}

ControlProblemShape terminal_membership_indexing_shape() {
    return {{2,3}, {1,2,2,3}, {0,1,1,2}, {2,3,4,5}};
}

SetHandle box(std::string id, std::string x, std::string y, const BoxBounds2D& bounds) {
    return take(sets::make_h({SetId{std::move(id)}, 2, {std::move(x), std::move(y)}},
        {take(numeric::snapshot(Matrix{4, 2, {1,0,-1,0,0,1,0,-1}})),
         take(numeric::snapshot_vector(Vector{bounds.x_upper,-bounds.x_lower,
             bounds.y_upper,-bounds.y_lower})),
         take(numeric::snapshot(Matrix{0,2,{}})), take(numeric::snapshot_vector(Vector{}))})).as_handle();
}

problem::ResolvedProblem control_problem(bool quadratic, const ControlProblemShape& shape) {
    TerminalObjective objective = quadratic
        ? TerminalObjective{QuadraticTerminal{Matrix{2,2,{2,0,0,2}}, Vector{0,0}, 0}}
        : TerminalObjective{LinearTerminal{Vector{-1,0}, 0}};
    Problem source{{quadratic ? "issue944-planar-quadratic" : "issue944-planar-linear"},
        std::make_shared<const SystemModel>(SystemModel{{{2,2,0}, TimeDomain::discrete,
            LinearStage{Matrix{2,2,{1,0,0,1}}, Matrix{2,2,{1,0,0,1}}, Matrix{2,0,{}}, Vector{0,0}}}, {}}),
        {0,1}, KnownInitial{shape.initial_state}, ContinuousDomain{{
            box("issue944-u", "u0", "u1", shape.control_box)}},
        {box("issue944-x0", "position", "velocity", shape.initial_state_box),
         box("issue944-x1", "position", "velocity", shape.next_state_box)}, {}, {},
        InformationPattern::nominal_open_loop, std::move(objective)};
    return take(problem::resolve(source, {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}}));
}

template<class Port>
registry::PreparedProvider<Port> selected(registry::Registration<Port> entry, std::string representation) {
    registry::Registry<Port> registry;
    const registry::Method method{entry.identity.id, entry.identity.version};
    if (const auto rejection = registry.add(std::move(entry)))
        throw std::runtime_error("duplicate built-in provider while preparing the 2D pipeline");
    registry::Requirements requirements;
    requirements.output.assurance = Assurance::numerical;
    if constexpr (!std::is_same_v<Port, registry::HullReducerPort> &&
            !std::is_same_v<Port, registry::SourceIndexHullPort>)
        requirements.output.representation = {std::move(representation)};
    if constexpr (std::is_same_v<Port, registry::GeometryPort> || std::is_same_v<Port, registry::ConversionPort>)
        requirements.output.relation = SetRelation::equivalent;
    return take(registry::prepare_provider(registry::select_provider(registry, method, requirements)));
}

bool contains(const sets::HRepresentation& h, const Vector& point, double tolerance = 1e-8) {
    if (point.size() != h.inequalities.cols()) return false;
    for (std::size_t row = 0; row < h.inequalities.rows(); ++row) {
        double value = 0;
        for (std::size_t column = 0; column < point.size(); ++column) value += h.inequalities(row,column) * point[column];
        if (value > h.upper_bounds[row] + tolerance) return false;
    }
    for (std::size_t row = 0; row < h.equalities.rows(); ++row) {
        double value = 0;
        for (std::size_t column = 0; column < point.size(); ++column) value += h.equalities(row,column) * point[column];
        if (std::abs(value - h.equality_values[row]) > tolerance) return false;
    }
    return true;
}

std::set<std::pair<int,int>> polygon_vertices(const sets::HRepresentation& h) {
    std::set<std::pair<int,int>> points;
    for (std::size_t i = 0; i < h.inequalities.rows(); ++i) {
        for (std::size_t j = i + 1; j < h.inequalities.rows(); ++j) {
            const double a = h.inequalities(i,0), b = h.inequalities(i,1);
            const double c = h.inequalities(j,0), d = h.inequalities(j,1);
            const double determinant = a*d - b*c;
            if (std::abs(determinant) < 1e-12) continue;
            const double x = (h.upper_bounds[i]*d - b*h.upper_bounds[j]) / determinant;
            const double y = (a*h.upper_bounds[j] - h.upper_bounds[i]*c) / determinant;
            if (!contains(h, {x,y})) continue;
            const int ix = static_cast<int>(std::llround(x));
            const int iy = static_cast<int>(std::llround(y));
            if (std::abs(x-ix) < 1e-8 && std::abs(y-iy) < 1e-8) points.emplace(ix,iy);
        }
    }
    return points;
}

bool h_is_unit_square(const sets::HRepresentation& h) {
    if (h.inequalities.cols() != 2 || h.equalities.rows() != 0) return false;
    const std::set<std::pair<int,int>> corners{{0,0},{0,1},{1,0},{1,1}};
    if (polygon_vertices(h) != corners) return false;
    bool left=false, right=false, bottom=false, top=false;
    for (std::size_t row=0; row<h.inequalities.rows(); ++row) {
        const double x=h.inequalities(row,0), y=h.inequalities(row,1), b=h.upper_bounds[row];
        if (y==0 && x<0 && b==0) left=true;
        if (y==0 && x>0 && b==x) right=true;
        if (x==0 && y<0 && b==0) bottom=true;
        if (x==0 && y>0 && b==y) top=true;
        for (const auto& [cx,cy] : corners)
            if (x*cx+y*cy > b+1e-8) return false;
    }
    return left && right && bottom && top;
}

std::string terminal_provider(const synthesis::strategy_a::CandidateHistory& history) {
    if (!history.terminal || !history.terminal->provider) return "not_used";
    return history.terminal->provider->actual ? history.terminal->provider->actual->id.value :
        history.terminal->provider->requested.id.value;
}

std::string termination_name(Termination value) {
    switch (value) {
    case Termination::completed: return "completed";
    case Termination::operation_rejected: return "operation_rejected";
    case Termination::contract_rejected: return "contract_rejected";
    case Termination::resource_limit: return "resource_limit";
    case Termination::cancelled: return "cancelled";
    case Termination::deadline_expired: return "deadline_expired";
    case Termination::numerical_failure: return "numerical_failure";
    }
    return "unknown";
}

struct Trial {
    std::string task;
    std::string reducer;
    std::string vertex_lp;
    std::string terminal_lp;
    std::string terminal_choice;
    std::string status;
    std::string terminal_actual{"not_used"};
    std::string history_recovery_status{"not_attempted"};
    std::string history_recovery_api{"csl.synthesis.recover_joint_history@1"};
    std::string history_selection_provider{"csl.lp.highs"};
    std::string history_selection_program;
    Vector history_selection_objective;
    std::vector<std::string> calls;
    std::vector<std::string> conversion_calls;
    std::vector<std::string> program_boundary_observations;
    std::vector<Vector> forward_vertices;
    std::vector<Vector> terminal_point;
    Vector selected_history;
    std::vector<std::string> selected_history_coordinates;
    bool geometry_check{};
    bool returned_relation{};
    bool selected_history_in_returned_family{};
    bool selected_history_in_terminal_family{};
    bool selected_control_in_terminal_family{};
    std::size_t vertex_lp_calls{};
    std::size_t converter_lp_calls{};
    std::size_t terminal_lp_calls{};
    std::size_t terminal_convex_calls{};
    std::size_t history_selection_lp_calls{};
    std::string reason;
};

std::optional<Vector> select_history_from_terminal_family(
        const problem::ResolvedProblem& problem, const sets::SetData& terminal_family,
        const std::string& task, Trial& trial) {
    auto recovered=synthesis::recover_joint_history(problem,terminal_family);
    trial.calls.push_back("public recovery API invocation: provider=csl.synthesis.recover_joint_history@1; source="+
        terminal_family.metadata()->id.value);
    if (const auto* errors=std::get_if<Diagnostics>(&recovered)) {
        trial.history_recovery_status="recovery_rejected";
        if (!errors->empty()) trial.reason=errors->front().field+": "+errors->front().explanation;
        return {};
    }
    const auto& relation=std::get<synthesis::JointHistoryRelation>(recovered).relation;
    const auto representation=relation.representation();
    const auto* h=std::get_if<sets::HRepresentation>(&representation);
    if (!h) {
        trial.history_recovery_status="selection_rejected";
        trial.reason="public history recovery did not return native H geometry";
        return {};
    }

    const std::size_t columns=h->inequalities.cols();
    SparseMatrix constraints{0,columns,{0},{},{}};
    std::vector<Interval> row_bounds;
    const auto append_rows=[&](const numeric::MatrixView& matrix, const numeric::VectorView& values,
            bool equality) {
        for (std::size_t row=0;row<matrix.rows();++row) {
            for (std::size_t column=0;column<columns;++column) {
                const auto coefficient=matrix(row,column);
                if (coefficient==0) continue;
                constraints.column_indices.push_back(column);
                constraints.values.push_back(coefficient);
            }
            constraints.row_offsets.push_back(constraints.values.size());
            row_bounds.push_back(equality ? Interval{values[row],values[row]} : Interval{{},values[row]});
            ++constraints.rows;
        }
    };
    append_rows(h->inequalities,h->upper_bounds,false);
    append_rows(h->equalities,h->equality_values,true);

    // This deterministic tie-break selects a concrete point from the recovered
    // terminal-optimal history family. It is a separate consumer LP role; it
    // does not replace the Strategy A terminal objective or vertex reducer LP.
    Vector objective(columns,0.0);
    constexpr std::size_t state_dimension=2;
    constexpr std::size_t horizon=1;
    constexpr std::size_t first_control=(horizon+1)*state_dimension;
    if (columns!=first_control+state_dimension) {
        trial.history_recovery_status="selection_rejected";
        trial.reason="recovered history width differs from the declared one-step task";
        return {};
    }
    for (std::size_t i=0;i<state_dimension;++i) {
        objective[state_dimension+i]=1.0;
        objective[first_control+i]=1.0;
    }
    trial.history_selection_objective=objective;
    trial.history_selection_program="issue944-history-selection:"+task;
    const ProgramIdentity identity{problem.identity(),ProgramId{trial.history_selection_program}};
    auto made=optimization::make_linear_program({identity,objective,0.0,std::move(constraints),
        std::vector<Interval>(columns),std::move(row_bounds)});
    if (const auto* errors=std::get_if<Diagnostics>(&made)) {
        trial.history_recovery_status="selection_rejected";
        if (!errors->empty()) trial.reason=errors->front().field+": "+errors->front().explanation;
        return {};
    }

    auto registration=take(adapters::lp::make_highs_registration());
    auto calls=std::make_shared<std::atomic<std::size_t>>(0);
    const auto factory=registration.factory;
    registration.factory=[factory,calls](const LinearProgram& program) {
        return std::make_unique<CountingLPWorkspace>(factory(program),calls);
    };
    if (registration.basis_factory) {
        const auto basis=registration.basis_factory;
        registration.basis_factory=[basis](const LinearProgram& program,LPWorkspace& workspace) {
            auto& counting=dynamic_cast<CountingLPWorkspace&>(workspace);
            return basis(program,counting.inner());
        };
    }
    const auto provider=selected(std::move(registration),"csl.program-result.v1");
    auto prepared=provider.prepare(std::get<LinearProgram>(made));
    if (const auto* rejection=std::get_if<registry::Rejection>(&prepared)) {
        trial.history_recovery_status="selection_rejected";
        if (!rejection->diagnostics.empty()) trial.reason=rejection->diagnostics.front().field+": "+rejection->diagnostics.front().explanation;
        return {};
    }
    auto pipeline=std::get<registry::PreparedPipeline<registry::LPPort>>(std::move(prepared));
    const auto provenance=pipeline.provenance().front();
    if (provenance.actual) trial.history_selection_provider=provenance.actual->id.value;
    auto workspaces=pipeline.create();
    const auto outcome=std::get<0>(workspaces)->run({.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}})});
    trial.history_selection_lp_calls=calls->load();
    trial.calls.push_back("recovered-history selection LP invocation: role=history_selection; provider="+
        trial.history_selection_provider+"; program="+trial.history_selection_program+
        "; calls="+std::to_string(trial.history_selection_lp_calls));
    if (const auto* unsupported=std::get_if<Unsupported>(&outcome)) {
        trial.history_recovery_status="selection_rejected";
        if (!unsupported->diagnostics.empty()) trial.reason=unsupported->diagnostics.front().field+": "+unsupported->diagnostics.front().explanation;
        return {};
    }
    const auto& solved=std::get<ProgramResult>(outcome);
    if (solved.termination!=Termination::completed || !solved.primal) {
        trial.history_recovery_status="selection_rejected";
        trial.reason=solved.raw_diagnostics.empty()?"recovered-history LP returned no completed primal":solved.raw_diagnostics;
        return {};
    }
    if (!contains(*h,*solved.primal)) {
        trial.history_recovery_status="selection_rejected";
        trial.reason="recovered-history LP primal is outside the public recovery relation";
        return {};
    }
    trial.history_recovery_status="completed";
    return *solved.primal;
}

std::string json_vector(const Vector& point) {
    std::ostringstream out;
    out << '[';
    for (std::size_t i=0; i<point.size(); ++i) { if (i) out << ','; out << point[i]; }
    out << ']';
    return out.str();
}

std::string matrix_text(const numeric::MatrixView& matrix) {
    std::ostringstream out;
    out << std::setprecision(17) << '[';
    for (std::size_t r=0;r<matrix.rows();++r) {
        if (r) out << ';';
        for (std::size_t c=0;c<matrix.cols();++c) {
            if (c) out << ',';
            out << matrix(r,c);
        }
    }
    out << ']';
    return out.str();
}

std::optional<double> smallest_nonzero(const numeric::MatrixView& matrix) {
    std::optional<double> minimum;
    for (std::size_t r=0;r<matrix.rows();++r) for (std::size_t c=0;c<matrix.cols();++c) {
        const auto value=std::abs(matrix(r,c));
        if (value!=0 && (!minimum || value<*minimum)) minimum=value;
    }
    return minimum;
}

void emit_trial(std::ostream& out, const Trial& trial, bool include_control_terminal_probe = false) {
    out << "{\"task\":" << quote(trial.task)
        << ",\"controller\":\"csl.synthesis.reach-back@1\",\"representation\":\"csl.polyhedron.h\""
        << ",\"vertex_reducer\":" << quote(trial.reducer)
        << ",\"vertex_lp_provider\":" << quote(trial.vertex_lp)
        << ",\"converter\":\"csl.conversion.qhull\",\"converter_lp_provider\":\"csl.lp.highs\""
        << ",\"terminal_lp_provider\":" << quote(trial.terminal_lp)
        << ",\"terminal_optimizer_choice\":" << quote(trial.terminal_choice)
        << ",\"terminal_optimizer_actual\":" << quote(trial.terminal_actual)
        << ",\"history_recovery_api\":" << quote(trial.history_recovery_api)
        << ",\"history_recovery_status\":" << quote(trial.history_recovery_status)
        << ",\"history_selection_provider\":" << quote(trial.history_selection_provider)
        << ",\"history_selection_program\":" << quote(trial.history_selection_program)
        << ",\"history_selection_objective\":" << json_vector(trial.history_selection_objective)
        << ",\"status\":" << quote(trial.status)
        << ",\"lp_call_counts\":{\"vertex\":" << trial.vertex_lp_calls
        << ",\"converter\":" << trial.converter_lp_calls
        << ",\"terminal_lp\":" << trial.terminal_lp_calls
        << ",\"terminal_convex\":" << trial.terminal_convex_calls
        << ",\"history_selection\":" << trial.history_selection_lp_calls << '}'
        << ",\"independent_check\":{\"forward_hull_is_unit_square\":" << (trial.geometry_check ? "true" : "false")
        << ",\"selected_history_in_returned_family\":" << (trial.selected_history_in_returned_family ? "true" : "false")
        << ",\"selected_history_in_terminal_family\":" << (trial.selected_history_in_terminal_family ? "true" : "false");
    if (include_control_terminal_probe)
        out << ",\"selected_control_in_terminal_family\":"
            << (trial.selected_control_in_terminal_family ? "true" : "false");
    out << ",\"candidate_relation_returned\":" << (trial.returned_relation ? "true" : "false") << '}'
        << ",\"forward_vertices\":[";
    for (std::size_t i=0; i<trial.forward_vertices.size(); ++i) { if (i) out << ','; out << json_vector(trial.forward_vertices[i]); }
    out << "],\"terminal_point\":[";
    for (std::size_t i=0; i<trial.terminal_point.size(); ++i) { if (i) out << ','; out << json_vector(trial.terminal_point[i]); }
    out << "],\"selected_history\":" << json_vector(trial.selected_history)
        << ",\"selected_history_coordinates\":[";
    for (std::size_t i=0; i<trial.selected_history_coordinates.size(); ++i) { if (i) out << ','; out << quote(trial.selected_history_coordinates[i]); }
    out << "],\"conversion_calls\":[";
    for (std::size_t i=0; i<trial.conversion_calls.size(); ++i) { if (i) out << ','; out << quote(trial.conversion_calls[i]); }
    out << "],\"program_boundary_observations\":[";
    for (std::size_t i=0; i<trial.program_boundary_observations.size(); ++i) { if (i) out << ','; out << quote(trial.program_boundary_observations[i]); }
    out << "],\"operation_call_evidence\":[";
    for (std::size_t i=0; i<trial.calls.size(); ++i) { if (i) out << ','; out << quote(trial.calls[i]); }
    out << "]";
    if (!trial.reason.empty()) out << ",\"first_unmet\":" << quote(trial.reason);
    out << '}';
}

Trial execute(const std::string& task, const std::string& reducer_id, const std::string& vertex_lp_id,
        const std::string& terminal_lp_id, const std::string& terminal_choice, bool source_index,
        const ControlProblemShape& shape = standard_control_problem_shape()) {
    Trial trial{task, reducer_id, vertex_lp_id, terminal_lp_id, terminal_choice};
    auto choices = lp_choices();
    const auto find_lp = [&](const std::string& id) -> registry::Registration<registry::LPPort> {
        const auto found = std::find_if(choices.begin(), choices.end(), [&](const auto& choice) {
            return choice.registration.identity.id.value == id;
        });
        if (found == choices.end()) throw std::runtime_error("unknown LP choice: " + id);
        return found->registration;
    };
    std::optional<registry::Registration<registry::LPPort>> vertex_lp;
    if (!source_index) vertex_lp = find_lp(vertex_lp_id);
    auto terminal_lp = find_lp(terminal_lp_id == "not_used" ? "csl.lp.highs" : terminal_lp_id);
    {
        const auto capability = terminal_lp.capabilities;
        const auto provider = terminal_lp.identity.id.value;
        auto* observations = &trial.program_boundary_observations;
        terminal_lp.capabilities = [capability, provider, observations](const LinearProgram& program,
                const registry::Requirements& requirements) {
            auto result=capability(program,requirements);
            const auto minimum=smallest_nonzero(program.constraints());
            const auto* rejection=std::get_if<Diagnostics>(&result);
            if (rejection || (minimum && *minimum<=1e-12)) {
                std::ostringstream record;
                record << std::setprecision(17) << "LP capability boundary: provider=" << provider
                    << "; problem=" << program.identity().problem.value << "; program=" << program.identity().program.value
                    << "; rows=" << program.constraints().rows() << "; columns=" << program.constraints().cols()
                    << "; min_nonzero_A=";
                if (minimum) record << *minimum; else record << "none";
                record << "; objective=";
                for (std::size_t i=0;i<program.objective().size();++i) { if(i)record << ','; record << program.objective()[i]; }
                record << "; A=" << matrix_text(program.constraints());
                if (rejection) for (const auto& diagnostic:*rejection)
                    record << "; rejected=" << diagnostic.field << ": " << diagnostic.explanation;
                observations->push_back(record.str());
            }
            return result;
        };
    }
    auto vertex_lp_calls = std::make_shared<std::atomic<std::size_t>>(0);
    auto terminal_lp_calls = std::make_shared<std::atomic<std::size_t>>(0);
    auto terminal_convex_calls = std::make_shared<std::atomic<std::size_t>>(0);
    auto converter_lp_calls = std::make_shared<std::atomic<std::size_t>>(0);
    if (vertex_lp) {
        const auto factory = vertex_lp->factory;
        vertex_lp->factory = [factory, vertex_lp_calls](const LinearProgram& program) {
            return std::make_unique<CountingLPWorkspace>(factory(program), vertex_lp_calls);
        };
        if (vertex_lp->basis_factory) {
            const auto basis = vertex_lp->basis_factory;
            vertex_lp->basis_factory = [basis](const LinearProgram& program, LPWorkspace& workspace) {
                auto& counting = dynamic_cast<CountingLPWorkspace&>(workspace);
                return basis(program, counting.inner());
            };
        }
    }
    {
        const auto factory = terminal_lp.factory;
        terminal_lp.factory = [factory, terminal_lp_calls](const LinearProgram& program) {
            return std::make_unique<CountingLPWorkspace>(factory(program), terminal_lp_calls);
        };
        if (terminal_lp.basis_factory) {
            const auto basis = terminal_lp.basis_factory;
            terminal_lp.basis_factory = [basis](const LinearProgram& program, LPWorkspace& workspace) {
                auto& counting = dynamic_cast<CountingLPWorkspace&>(workspace);
                return basis(program, counting.inner());
            };
        }
    }
    auto conversion_observations = std::make_shared<std::vector<adapters::polyhedral::ConversionObservation>>();
    adapters::polyhedral::QhullOptions qhull_options;
    qhull_options.observe = [conversion_observations](const auto& observation) {
        conversion_observations->push_back(observation);
    };
    auto converter_lp = find_lp("csl.lp.highs");
    {
        const auto factory=converter_lp.factory;
        converter_lp.factory=[factory,converter_lp_calls](const LinearProgram& program) {
            return std::make_unique<CountingLPWorkspace>(factory(program),converter_lp_calls);
        };
        if (converter_lp.basis_factory) {
            const auto basis=converter_lp.basis_factory;
            converter_lp.basis_factory=[basis](const LinearProgram& program, LPWorkspace& workspace) {
                auto& counting=dynamic_cast<CountingLPWorkspace&>(workspace);
                return basis(program,counting.inner());
            };
        }
    }
    auto converter_result = adapters::polyhedral::make_qhull_registration(std::move(converter_lp), qhull_options);
    if (!std::holds_alternative<registry::Registration<registry::ConversionPort>>(converter_result)) {
        trial.status = "backend_unavailable";
        trial.reason = "csl.conversion.qhull registration unavailable";
        return trial;
    }
    auto converter_registration = std::get<registry::Registration<registry::ConversionPort>>(std::move(converter_result));
    {
        const auto factory=converter_registration.factory;
        auto* observations=&trial.program_boundary_observations;
        converter_registration.factory=[factory,observations,upstream=reducer_id](const ConversionRequest& request) {
            return std::make_unique<ObservingConverterWorkspace>(factory(request),observations,upstream+"@1.0.0");
        };
    }
    auto projection = geometry::polyhedral::make_projection_registration();
    registry::Registration<registry::GeometryPort> affine;
    if (source_index) {
        registry::Registry<registry::SourceIndexHullPort> source_registry;
        for (auto entry : {geometry::make_quickhull_source_index_registration(),
                geometry::make_legacy_kpabep_source_index_registration()}) {
            if (const auto rejection = source_registry.add(std::move(entry)))
                throw std::runtime_error("source-index candidate registration rejected");
        }
        registry::Requirements source_requirements;
        source_requirements.output.assurance = Assurance::numerical;
        auto selected_source = registry::prepare_provider(registry::select_provider(source_registry,
            {ModuleId{reducer_id}, "1.0.0"}, source_requirements));
        if (!std::holds_alternative<registry::PreparedProvider<registry::SourceIndexHullPort>>(selected_source)) {
            trial.status = "incompatible";
            trial.reason = "source-index registration rejected for the finite binary64 2D profile";
            return trial;
        }
        affine = geometry::make_affine_sum_registration(geometry::SourceIndexAffineSumDependencies{
            std::get<registry::PreparedProvider<registry::SourceIndexHullPort>>(std::move(selected_source)),
            selected(converter_registration, "csl.polyhedron.v"), {}});
    } else {
        const auto reducers = reducer_choices();
        const auto selected_reducer = std::find_if(reducers.begin(), reducers.end(), [&](const auto& item) { return item.id == reducer_id; });
        if (selected_reducer == reducers.end()) throw std::runtime_error("unknown reducer choice: " + reducer_id);
        auto registration = selected_reducer->registration(*vertex_lp);
        affine = geometry::make_affine_sum_registration(geometry::AffineSumDependencies{
            selected(std::move(registration), "csl.polyhedron.v"),
            selected(*vertex_lp, "csl.program-result.v1"),
            selected(converter_registration, "csl.polyhedron.v")});
    }
    auto convex_registration = adapters::convex::make_highs_registration();
    if (!std::holds_alternative<registry::Registration<registry::ConvexPort>>(convex_registration)) {
        trial.status = "backend_unavailable";
        trial.reason = "csl.convex.highs registration unavailable";
        return trial;
    }
    registry::Registry<registry::GeometryPort> projections, affines;
    registry::Registry<registry::ConversionPort> conversions;
    registry::Registry<registry::LPPort> terminal_lps;
    registry::Registry<registry::ConvexPort> convexes;
    const auto pm = registry::Method{projection.identity.id, projection.identity.version};
    const auto am = registry::Method{affine.identity.id, affine.identity.version};
    const auto cm = registry::Method{converter_registration.identity.id, converter_registration.identity.version};
    const auto lm = registry::Method{terminal_lp.identity.id, terminal_lp.identity.version};
    auto convex = std::get<registry::Registration<registry::ConvexPort>>(std::move(convex_registration));
    {
        const auto capability=convex.capabilities;
        auto* observations=&trial.program_boundary_observations;
        convex.capabilities=[capability,observations](const ConvexProgram& program,
                const registry::Requirements& requirements) {
            auto result=capability(program,requirements);
            const auto& qp=program.quadratic_program();
            const auto minimum=smallest_nonzero(qp.constraints());
            const auto* rejection=std::get_if<Diagnostics>(&result);
            if (rejection || (minimum && *minimum<=1e-12)) {
                std::ostringstream record;
                record << std::setprecision(17) << "Convex capability boundary: provider=csl.convex.highs"
                    << "; problem=" << qp.identity().problem.value << "; program=" << qp.identity().program.value
                    << "; rows=" << qp.constraints().rows() << "; columns=" << qp.constraints().cols()
                    << "; min_nonzero_A=";
                if (minimum) record << *minimum; else record << "none";
                record << "; A=" << matrix_text(qp.constraints()) << "; H=" << matrix_text(qp.hessian());
                if (rejection) for (const auto& diagnostic:*rejection)
                    record << "; rejected=" << diagnostic.field << ": " << diagnostic.explanation;
                observations->push_back(record.str());
            }
            return result;
        };
    }
    {
        const auto factory = convex.factory;
        convex.factory = [factory, terminal_convex_calls](const ConvexProgram& program) {
            return std::make_unique<CountingConvexWorkspace>(factory(program), terminal_convex_calls);
        };
    }
    const auto qm = registry::Method{convex.identity.id, convex.identity.version};
    if (projections.add(projection) || affines.add(affine) || conversions.add(converter_registration) ||
            terminal_lps.add(terminal_lp) || convexes.add(convex))
        throw std::runtime_error("selected public provider registration was rejected");
    registry::Requirements h, v, program;
    h.output.representation = {"csl.polyhedron.h"}; h.output.relation = SetRelation::equivalent;
    v.output.representation = {"csl.polyhedron.v"}; v.output.relation = SetRelation::equivalent;
    program.output.representation = {"csl.program-result.v1"};
    auto checked = registry::check_providers(
        registry::select_provider(projections, pm, h), registry::select_provider(affines, am, v),
        registry::select_provider(conversions, cm, h), registry::select_provider(terminal_lps, lm, program),
        registry::select_provider(convexes, qm, program));
    if (!std::holds_alternative<registry::CheckedProviders<registry::GeometryPort, registry::GeometryPort,
            registry::ConversionPort, registry::LPPort, registry::ConvexPort>>(checked)) {
        trial.status = "incompatible";
        trial.reason = "Strategy A dependency selection rejected";
        return trial;
    }
    auto strategy = synthesis::strategy_a::make_registration(
        std::get<registry::CheckedProviders<registry::GeometryPort, registry::GeometryPort,
            registry::ConversionPort, registry::LPPort, registry::ConvexPort>>(std::move(checked)));
    registry::StrategyRegistry strategies;
    if (strategies.add(std::move(strategy))) throw std::runtime_error("Strategy A registration rejected");
    auto problem = control_problem(task == "quadratic", shape);
    FamilyRequest family;
    family.objective = problem.identity();
    family.profile = "nominal_open_loop";
    family.target = FamilyTarget::candidate_relaxation;
    family.assurance = Assurance::numerical;
    family.representation = {"csl.polyhedron.h"};
    StrategyConfiguration configuration;
    configuration.strategy = {"csl.synthesis.reach-back"};
    configuration.representation = {"csl.polyhedron.h"};
    registry::StrategyRequest request{problem, configuration, family, "1", {}};
    registry::Requirements output;
    output.output.representation = {"csl.polyhedron.h"};
    output.output.family = family.target;
    output.output.completeness = registry::Completeness::unestablished;
    auto prepared = strategies.prepare(request, output);
    if (!std::holds_alternative<registry::PreparedStrategy>(prepared)) {
        trial.status = "incompatible";
        trial.reason = "Strategy A request admission failed";
        return trial;
    }
    auto workspace = std::get<registry::PreparedStrategy>(std::move(prepared)).create();
    const auto outcome = workspace->run({.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}})});
    trial.vertex_lp_calls = vertex_lp_calls->load();
    trial.converter_lp_calls = converter_lp_calls->load();
    trial.terminal_lp_calls = terminal_lp_calls->load();
    trial.terminal_convex_calls = terminal_convex_calls->load();
    if (const auto* unsupported = std::get_if<Unsupported>(&outcome)) {
        trial.status = "unsupported";
        if (!unsupported->diagnostics.empty()) trial.reason = unsupported->diagnostics.front().field + ": " + unsupported->diagnostics.front().explanation;
        return trial;
    }
    const auto& result = std::get<SynthesisResult>(outcome);
    trial.status = termination_name(result.termination);
    if (result.termination != Termination::completed || !result.family) {
    if (const auto* stop = std::get_if<ScopedRequestRejection>(&result.stop); stop && !stop->diagnostics.empty())
            trial.reason = stop->diagnostics.front().field + ": " + stop->diagnostics.front().explanation;
    else if (const auto* stop = std::get_if<ScopedOperationStopped>(&result.stop)) trial.reason = stop->stop.diagnostics;
        else trial.reason = "Strategy A returned no candidate family";
    }
    for (const auto& observation : *conversion_observations) {
        std::ostringstream call;
        call << observation.converter.id.value << " " << observation.input_representation << "->"
             << observation.output_representation << " outcome=" << observation.outcome
             << " lp=" << observation.lp_backend.id.value << " request=" << observation.request.request.value;
        trial.conversion_calls.push_back(call.str());
    }
    if (result.family) {
        const auto* candidate = std::get_if<CandidateFamily>(&result.family->outcome());
        if (candidate) {
            const auto* history = dynamic_cast<const synthesis::strategy_a::CandidateHistory*>(candidate->relation.payload.get());
            if (history) {
                trial.returned_relation = true;
                trial.terminal_actual = terminal_provider(*history);
                if (history->terminal && history->terminal->optimization && history->terminal->optimization->primal)
                    trial.terminal_point.push_back(*history->terminal->optimization->primal);
                for (const auto& stage : history->forward.stages) {
                    for (const auto& evidence : stage.operation_lineage)
                        for (const auto& assumption : evidence.assumptions) trial.calls.push_back(assumption);
                    const auto imported = sets::from_handle(stage.marginal.output);
                    if (const auto* set = std::get_if<sets::SetData>(&imported)) {
                        const auto representation = set->representation();
                        if (const auto* hrep = std::get_if<sets::HRepresentation>(&representation)) {
                            for (const auto& point : polygon_vertices(*hrep))
                                trial.forward_vertices.push_back(Vector{static_cast<double>(point.first), static_cast<double>(point.second)});
                            trial.geometry_check = h_is_unit_square(*hrep);
                        }
                    }
                }
                const auto& joint_relation = history->history.relation;
                trial.selected_history_coordinates = {"x0.position","x0.velocity","x1.position","x1.velocity","u0.0","u0.1"};
                const auto joint_representation = joint_relation.representation();
                const auto* joint_h = std::get_if<sets::HRepresentation>(&joint_representation);
                if (history->terminal && history->terminal->relation && joint_h) {
                    const auto selected_history=select_history_from_terminal_family(
                        problem,*history->terminal->relation,task,trial);
                    if (selected_history) {
                        trial.selected_history=*selected_history;
                        trial.selected_history_in_returned_family=contains(*joint_h,trial.selected_history);
                        const auto terminal_representation=history->terminal->relation->representation();
                        if (const auto* terminal_h=std::get_if<sets::HRepresentation>(&terminal_representation)) {
                            if (trial.selected_history.size()==6) {
                                const Vector selected_terminal{trial.selected_history[2],trial.selected_history[3]};
                                trial.selected_history_in_terminal_family=contains(*terminal_h,selected_terminal);
                                const Vector control{trial.selected_history[4],trial.selected_history[5]};
                                trial.selected_control_in_terminal_family=contains(*terminal_h,control);
                            }
                        }
                    }
                }
            }
        }
    }
    return trial;
}

void emit_matrix(std::ostream& out) {
    const std::vector<std::pair<std::string,std::string>> tasks{{"linear","linear"},{"quadratic","quadratic"}};
    const auto lps = lp_choices();
    const auto reducers = reducer_choices();
    std::vector<Trial> trials;
    for (const auto& task : tasks) {
        const auto terminal_choice = task.first == "linear" ? "csl.lp.highs" : "csl.convex.highs";
        for (const auto& lp : lps) for (const auto& reducer : reducers) {
            if (task.first == "linear") {
                for (const auto& terminal : lps)
                    trials.push_back(execute(task.first, reducer.id, lp.registration.identity.id.value,
                        terminal.registration.identity.id.value, terminal_choice, false));
            } else {
                trials.push_back(execute(task.first, reducer.id, lp.registration.identity.id.value,
                    "not_used", terminal_choice, false));
            }
        }
        for (const auto& reducer : {std::string{"csl.hull.source.quickhull-2d"},
                std::string{"csl.hull.source.btulshor-kpabep"}}) {
            if (task.first == "linear") {
                for (const auto& terminal : lps)
                    trials.push_back(execute(task.first, reducer, "not_used", terminal.registration.identity.id.value,
                        terminal_choice, true));
            } else {
                trials.push_back(execute(task.first, reducer, "not_used", "not_used", terminal_choice, true));
            }
        }
    }
    out << "{\"schema\":\"csl.strategy-a-each-choice-pipeline/2\","
        << "\"scope\":\"one-step nominal Strategy A candidate construction plus public terminal-family recovery and numerical history selection\","
        << "\"task\":{\"dynamics\":\"x_next=x+u\",\"state_dimension\":2,\"control_dimension\":2,\"horizon\":1,"
        << "\"initial_state_box\":[[-1,1],[-1,1]],\"control_box\":[0,1],\"next_state_box\":[[0,1],[0,1]],"
            << "\"linear_terminal_objective\":[-1,0],\"quadratic_terminal_center\":[0,0]},"
        << "\"choice_inventory\":{\"hull_reducers\":10,\"vertex_lp_profiles\":[\"csl.lp.highs\",\"phase-one-bland\",\"phase-one-priority-tie\"],"
        << "\"source_index_reducers\":[\"csl.hull.source.quickhull-2d\",\"csl.hull.source.btulshor-kpabep\"],"
        << "\"converter\":\"csl.conversion.qhull@1.0.0+qhull.8.0.2\",\"terminal_optimizer_choices\":[\"csl.lp.highs\",\"csl.convex.highs\"],"
        << "\"history_recovery_api\":\"csl.synthesis.recover_joint_history@1\",\"history_selection_provider\":\"csl.lp.highs@1\"},\"attempts\":[";
    for (std::size_t i=0; i<trials.size(); ++i) { if (i) out << ','; emit_trial(out, trials[i]); }
    out << "]}\n";
}

void emit_terminal_membership_indexing_regression(std::ostream& out) {
    const auto shape = terminal_membership_indexing_shape();
    const auto trial = execute("linear", "csl.hull.lp-membership", "csl.lp.highs",
        "csl.lp.highs", "csl.lp.highs", false, shape);
    out << "{\"schema\":\"csl.strategy-a-terminal-membership-indexing-regression/1\","
        << "\"task\":{\"dynamics\":\"x_next=x+u\",\"initial_state\":[2,3],"
        << "\"initial_state_box\":[[1,2],[2,3]],\"control_box\":[[0,1],[1,2]],"
        << "\"next_state_box\":[[2,3],[4,5]]},\"attempt\":";
    emit_trial(out, trial, true);
    out << "}\n";
}
}

int main(int argc, char** argv) try {
#if !CSL_PIPELINE_HAS_HIGHS || !CSL_PIPELINE_HAS_QHULL
    std::cout << "{\"schema\":\"csl.strategy-a-each-choice-pipeline/2\",\"status\":\"backend_unavailable\","
        << "\"first_unmet\":\"This probe requires compiled HiGHS LP, HiGHS convex and Qhull providers.\"}\n";
#else
    if (argc == 2 && std::string_view(argv[1]) == "--terminal-membership-indexing-regression")
        emit_terminal_membership_indexing_regression(std::cout);
    else if (argc == 1)
        emit_matrix(std::cout);
    else
        throw std::invalid_argument("unsupported pipeline runner argument");
#endif
    return 0;
} catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
}
