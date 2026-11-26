#include <csl/adapters/nlp/casadi_history_optimizer.hpp>
#include <casadi/casadi.hpp>

#include <algorithm>
#include <charconv>
#include <cmath>
#include <limits>
#include <stdexcept>

namespace csl::adapters::nlp {
namespace {
using casadi::DM;
using casadi::MX;

DM dense(const Matrix &matrix) {
    DM out = DM::zeros(static_cast<casadi_int>(matrix.rows), static_cast<casadi_int>(matrix.cols));
    for (std::size_t i = 0; i < matrix.rows; ++i)
        for (std::size_t j = 0; j < matrix.cols; ++j)
            out(static_cast<casadi_int>(i), static_cast<casadi_int>(j)) =
                matrix.values[i * matrix.cols + j];
    return DM::sparsify(out);
}
DM dense(const numeric::MatrixView &matrix) {
    DM out =
        DM::zeros(static_cast<casadi_int>(matrix.rows()), static_cast<casadi_int>(matrix.cols()));
    for (std::size_t i = 0; i < matrix.rows(); ++i)
        for (std::size_t j = 0; j < matrix.cols(); ++j)
            out(static_cast<casadi_int>(i), static_cast<casadi_int>(j)) = matrix(i, j);
    return DM::sparsify(out);
}
bool fits_casadi_dimension(std::size_t dimension) {
    return dimension <= static_cast<std::size_t>(std::numeric_limits<casadi_int>::max());
}
bool fits_casadi_request(const optimization::HistoryOptimizationRequest &request) {
    if (!fits_casadi_dimension(request.source_cost.quadratic.dimension))
        return false;
    const auto representation = request.domain.original.relation.representation();
    if (const auto *h = std::get_if<sets::HRepresentation>(&representation))
        if (!fits_casadi_dimension(h->inequalities.rows()) ||
            !fits_casadi_dimension(h->inequalities.cols()) ||
            !fits_casadi_dimension(h->equalities.rows()) ||
            !fits_casadi_dimension(h->equalities.cols()))
            return false;
    for (const auto &term : request.source_cost.residual_norms)
        if (!fits_casadi_dimension(term.map.rows) || !fits_casadi_dimension(term.map.cols))
            return false;
    for (const auto &member : request.domain.memberships) {
        const bool fits = std::visit(
            [](const auto &selected) {
                using T = std::decay_t<decltype(selected)>;
                if constexpr (std::is_same_v<T, optimization::HistoryHMembership>) {
                    const auto h =
                        std::get<sets::HRepresentation>(selected.selected.representation());
                    return fits_casadi_dimension(h.inequalities.rows()) &&
                           fits_casadi_dimension(h.equalities.rows());
                } else if constexpr (std::is_same_v<T, optimization::HistoryLiftedHMembership>) {
                    return true;
                } else if constexpr (std::is_same_v<T, optimization::HistoryAxisBoxMembership>) {
                    return fits_casadi_dimension(selected.radii.size());
                } else if constexpr (std::is_same_v<T, optimization::HistoryZonotopeMembership>) {
                    return fits_casadi_dimension(selected.generators.cols);
                } else if constexpr (std::is_same_v<T,
                                                    optimization::HistoryParallelotopeMembership>) {
                    return fits_casadi_dimension(selected.frame.cols);
                } else if constexpr (std::is_same_v<T, optimization::HistoryBallFactorMembership>) {
                    return fits_casadi_dimension(selected.selected.factor.cols);
                } else {
                    const auto v =
                        std::get<sets::VRepresentation>(selected.selected.representation());
                    return fits_casadi_dimension(v.vertices.rows());
                }
            },
            member.shape);
        if (!fits)
            return false;
    }
    return true;
}
Vector values(const DM &vector) { return static_cast<Vector>(vector); }
Vector values(const numeric::VectorView &vector) {
    return Vector(vector.values().begin(), vector.values().end());
}
bool valid_scaling(const CasadiHistoryScaling &scaling, Dimensions dimensions) {
    const auto valid = [](const Vector &values, std::size_t size) {
        return values.size() == size && std::all_of(values.begin(), values.end(), [](double value) {
                   return std::isfinite(value) && value > 0.0;
               });
    };
    return valid(scaling.state, dimensions.state) && valid(scaling.control, dimensions.control);
}

Diagnostic invalid_scaling() {
    return {DiagnosticCode::invalid_input, "history.casadi_ipopt.scaling",
            "Provide one finite positive scale per physical state and control coordinate."};
}

std::string scale_vector_text(const Vector &values) {
    std::string result = "[";
    for (const auto value : values) {
        if (result.size() > 1)
            result += ',';
        // The general format emits enough digits to recover the same double.
        char buffer[64];
        const auto converted = std::to_chars(buffer, buffer + sizeof(buffer), value);
        if (converted.ec != std::errc{})
            throw std::runtime_error("Physical scale does not fit its diagnostic representation.");
        result.append(buffer, converted.ptr);
    }
    result += ']';
    return result;
}

std::string scaling_evidence(const std::optional<CasadiHistoryScaling> &scaling) {
    return scaling ? "; state_scales=" + scale_vector_text(scaling->state) +
                         "; control_scales=" + scale_vector_text(scaling->control)
                   : "";
}

DM constraint_scaling(const numeric::MatrixView &matrix, const Vector &scales) {
    if (scales.empty())
        return DM(1);
    Vector rows(matrix.rows(), 1e-12);
    for (std::size_t row = 0; row < matrix.rows(); ++row) {
        for (std::size_t column = 0; column < matrix.cols(); ++column)
            rows[row] = std::max(rows[row], std::abs(matrix(row, column)) * scales[column]);
        if (!std::isfinite(rows[row]))
            throw std::overflow_error("A physical history constraint row scale is nonfinite.");
    }
    return DM(rows);
}

void constrain(casadi::Opti &opti, const MX &z, const sets::SetData &domain, const Vector &scales) {
    const auto representation = domain.representation();
    const auto *h = std::get_if<sets::HRepresentation>(&representation);
    if (!h) {
        if (const auto *point = std::get_if<sets::SingletonRepresentation>(&representation)) {
            const auto rhs = DM(values(point->point));
            opti.subject_to(z == rhs, scales.empty() ? DM(1) : DM(scales));
            return;
        }
        if (std::holds_alternative<sets::UniversalRepresentation>(representation))
            return;
        throw std::runtime_error("empty or unsupported whole-history domain");
    }
    if (h->inequalities.rows())
        opti.subject_to(MX::mtimes(dense(h->inequalities), z) <= DM(values(h->upper_bounds)),
                        constraint_scaling(h->inequalities, scales));
    if (h->equalities.rows())
        opti.subject_to(MX::mtimes(dense(h->equalities), z) == DM(values(h->equality_values)),
                        constraint_scaling(h->equalities, scales));
}
using MembershipVariable = std::optional<MX>;

std::vector<MembershipVariable>
constrain_memberships(casadi::Opti &opti, const MX &history,
                      const optimization::HistoryDomain &domain,
                      const std::vector<optimization::HistoryMembershipWitness> &initial,
                      const Vector &state_scales) {
    const DM row_scale = state_scales.empty() ? DM(1) : DM(state_scales);
    std::vector<MembershipVariable> variables;
    const auto n = domain.original.coordinates.dimensions.state;
    for (std::size_t i = 0; i < domain.memberships.size(); ++i) {
        const auto &member = domain.memberships[i];
        // Request validation bounds the stage and state dimension by the full
        // history size; widen each factor before multiplying in CasADi's index
        // type so the size_t product cannot overflow first.
        const auto first = static_cast<casadi_int>(member.stage.value) * static_cast<casadi_int>(n);
        const auto state = history(casadi::Slice(first, first + static_cast<casadi_int>(n)));
        std::visit(
            [&](const auto &selected) {
                using T = std::decay_t<decltype(selected)>;
                if constexpr (std::is_same_v<T, optimization::HistoryHMembership>) {
                    constrain(opti, state, selected.selected, state_scales);
                    variables.push_back(std::nullopt);
                } else if constexpr (std::is_same_v<T, optimization::HistoryLiftedHMembership>) {
                    // These rows already constrain the canonical history.
                    variables.push_back(std::nullopt);
                } else {
                    Matrix factor;
                    Vector center;
                    Vector seed;
                    if constexpr (std::is_same_v<T, optimization::HistoryAxisBoxMembership>) {
                        factor = Matrix{n, n, Vector(n * n, 0.0)};
                        for (std::size_t j = 0; j < n; ++j)
                            factor.values[j * n + j] = selected.radii[j];
                        center = selected.center;
                        seed =
                            std::get<optimization::HistoryAxisBoxWitness>(initial[i]).coefficients;
                    } else if constexpr (std::is_same_v<T,
                                                        optimization::HistoryZonotopeMembership>) {
                        factor = selected.generators;
                        center = selected.center;
                        seed =
                            std::get<optimization::HistoryZonotopeWitness>(initial[i]).coefficients;
                    } else if constexpr (std::is_same_v<
                                             T, optimization::HistoryParallelotopeMembership>) {
                        factor = selected.frame;
                        center = selected.center;
                        seed = std::get<optimization::HistoryParallelotopeWitness>(initial[i])
                                   .coefficients;
                    } else if constexpr (std::is_same_v<
                                             T, optimization::HistoryBallFactorMembership>) {
                        factor = selected.selected.factor;
                        center = selected.selected.center;
                        seed = std::get<optimization::HistoryBallFactorWitness>(initial[i])
                                   .coefficients;
                    } else {
                        const auto representation = selected.selected.representation();
                        const auto &vertices =
                            std::get<sets::VRepresentation>(representation).vertices;
                        factor = Matrix{n, vertices.rows(), Vector(n * vertices.rows(), 0.0)};
                        center = Vector(n, 0.0);
                        for (std::size_t row = 0; row < vertices.rows(); ++row)
                            for (std::size_t col = 0; col < n; ++col)
                                factor.values[col * factor.cols + row] = vertices(row, col);
                        seed =
                            std::get<optimization::HistoryVSimplexWitness>(initial[i]).coefficients;
                    }
                    if (factor.cols == 0) {
                        opti.subject_to(state == DM(center), row_scale);
                        variables.push_back(std::nullopt);
                        return;
                    }
                    const auto coefficients = opti.variable(static_cast<casadi_int>(factor.cols));
                    opti.subject_to(state == DM(center) + MX::mtimes(dense(factor), coefficients),
                                    row_scale);
                    if constexpr (std::is_same_v<T, optimization::HistoryAxisBoxMembership> ||
                                  std::is_same_v<T, optimization::HistoryZonotopeMembership>) {
                        opti.subject_to(opti.bounded(-1, coefficients, 1));
                    } else if constexpr (std::is_same_v<
                                             T, optimization::HistoryParallelotopeMembership>) {
                        if (!state_scales.empty())
                            opti.set_linear_scale(coefficients, row_scale, DM(seed));
                        opti.subject_to(
                            opti.bounded(DM(selected.lower), coefficients, DM(selected.upper)),
                            row_scale);
                    } else if constexpr (std::is_same_v<
                                             T, optimization::HistoryBallFactorMembership>) {
                        opti.subject_to(MX::dot(coefficients, coefficients) <= 1);
                    } else {
                        opti.subject_to(coefficients >= 0);
                        opti.subject_to(MX::dot(DM::ones(static_cast<casadi_int>(factor.cols)),
                                                coefficients) == 1);
                    }
                    opti.set_initial(coefficients, DM(seed));
                    variables.push_back(coefficients);
                }
            },
            member.shape);
    }
    return variables;
}

optimization::HistoryMembershipWitness make_witness(const optimization::HistoryMembership &member,
                                                    Vector coefficients) {
    return std::visit(
        [&](const auto &selected) -> optimization::HistoryMembershipWitness {
            using T = std::decay_t<decltype(selected)>;
            if constexpr (std::is_same_v<T, optimization::HistoryHMembership> ||
                          std::is_same_v<T, optimization::HistoryLiftedHMembership>)
                return optimization::HistoryHWitness{};
            else if constexpr (std::is_same_v<T, optimization::HistoryAxisBoxMembership>)
                return optimization::HistoryAxisBoxWitness{std::move(coefficients)};
            else if constexpr (std::is_same_v<T, optimization::HistoryZonotopeMembership>)
                return optimization::HistoryZonotopeWitness{std::move(coefficients)};
            else if constexpr (std::is_same_v<T, optimization::HistoryParallelotopeMembership>)
                return optimization::HistoryParallelotopeWitness{std::move(coefficients)};
            else if constexpr (std::is_same_v<T, optimization::HistoryBallFactorMembership>)
                return optimization::HistoryBallFactorWitness{std::move(coefficients)};
            else
                return optimization::HistoryVSimplexWitness{std::move(coefficients)};
        },
        member.shape);
}
class NativeWorkspace final : public optimization::HistoryOptimizerWorkspace {
    std::optional<CasadiHistoryScaling> scaling_;
    bool detect_dependencies_;

    std::string configuration_evidence() const {
        auto evidence = scaling_evidence(scaling_);
        if (detect_dependencies_)
            evidence += "; dependency_detector=mumps; dependency_detection_with_rhs=yes";
        return evidence;
    }

  public:
    NativeWorkspace(std::optional<CasadiHistoryScaling> scaling, bool detect_dependencies)
        : scaling_(std::move(scaling)), detect_dependencies_(detect_dependencies) {}

    optimization::RawHistorySolveOutcome
    solve_candidate(const optimization::HistoryOptimizationRequest &request,
                    const ExecutionContext &context) override {
        const auto *supplied = std::get_if<optimization::SuppliedStart>(&request.start);
        if (!supplied)
            return Diagnostic{
                DiagnosticCode::unsupported, "history.start",
                "CasADi/IPOPT requires an explicitly supplied feasible full-history start."};
        const auto coordinates = request.domain.original.coordinates;
        if (scaling_ && !valid_scaling(*scaling_, coordinates.dimensions))
            return invalid_scaling();
        const auto &initial_history = supplied->history;
        if (!fits_casadi_request(request))
            return Diagnostic{
                DiagnosticCode::unsupported, "history.casadi_ipopt.dimensions",
                "A canonical history or constraint dimension exceeds CasADi's integer index range."};
        if (context.cancellation.stop_requested())
            return OperationStopped{StopReason::cancelled,
                                    "Native CasADi history optimization cancelled before solve"};
        if (context.deadline && std::chrono::steady_clock::now() >= *context.deadline)
            return OperationStopped{
                StopReason::deadline_expired,
                "Native CasADi history optimization deadline expired before solve"};
        try {
            const auto &cost = request.source_cost;
            const auto size = request.source_cost.quadratic.dimension;
            casadi::Opti opti;
            const auto z = opti.variable(static_cast<casadi_int>(size));
            Vector history_scales, state_scales;
            if (scaling_) {
                state_scales = scaling_->state;
                history_scales.reserve(size);
                for (std::size_t k = 0; k <= coordinates.horizon; ++k)
                    history_scales.insert(history_scales.end(), state_scales.begin(),
                                          state_scales.end());
                for (std::size_t k = 0; k < coordinates.horizon; ++k)
                    history_scales.insert(history_scales.end(), scaling_->control.begin(),
                                          scaling_->control.end());
                opti.set_linear_scale(z, DM(history_scales), DM(initial_history));
            }
            opti.set_initial(z, DM(initial_history));
            constrain(opti, z, request.domain.original.relation, history_scales);
            const auto membership_variables = constrain_memberships(
                opti, z, request.domain, supplied->membership_witnesses, state_scales);
            const auto &q = cost.quadratic;
            MX objective = 0.5 * MX::mtimes(std::vector<MX>{z.T(), dense(q.Q), z}) +
                           MX::dot(DM(q.linear), z) + q.offset;
            for (const auto &term : cost.residual_norms) {
                Matrix weighted = term.map;
                Vector target = term.target;
                for (std::size_t i = 0; i < weighted.rows; ++i) {
                    const double factor = std::sqrt(term.weights[i]);
                    target[i] *= factor;
                    for (std::size_t j = 0; j < weighted.cols; ++j)
                        weighted.values[i * weighted.cols + j] *= factor;
                }
                const auto residual = MX::mtimes(dense(weighted), z) - DM(target);
                const auto epigraph = opti.variable();
                if (term.map.rows == 1) {
                    // |r| <= t is exactly linear and implies t >= 0.
                    opti.subject_to(residual(0) <= epigraph);
                    opti.subject_to(-residual(0) <= epigraph);
                } else {
                    opti.subject_to(epigraph >= 0);
                    opti.subject_to(MX::dot(residual, residual) <= epigraph * epigraph);
                }
                double squared = 0;
                for (std::size_t i = 0; i < weighted.rows; ++i) {
                    double value = -target[i];
                    for (std::size_t j = 0; j < size; ++j)
                        value += weighted.values[i * size + j] * initial_history[j];
                    squared += value * value;
                }
                opti.set_initial(epigraph, std::sqrt(squared) + 1e-3);
                objective += term.coefficient * epigraph;
            }
            opti.minimize(objective);
            const auto dual_count = opti.g().numel();
            opti.set_initial(opti.lam_g(), DM::zeros(dual_count));
            const auto initial_primal = values(opti.debug().value(z, opti.initial()));
            const auto initial_dual = values(opti.debug().value(opti.lam_g(), opti.initial()));
            std::vector<optimization::HistoryMembershipWitness> membership_readbacks;
            for (std::size_t i = 0; i < membership_variables.size(); ++i) {
                auto coefficients =
                    membership_variables[i]
                        ? values(opti.debug().value(*membership_variables[i], opti.initial()))
                        : Vector{};
                membership_readbacks.push_back(
                    make_witness(request.domain.memberships[i], std::move(coefficients)));
            }
            if (initial_dual.size() != static_cast<std::size_t>(dual_count) ||
                std::any_of(initial_dual.begin(), initial_dual.end(),
                            [](double value) { return value != 0; }))
                return Diagnostic{
                    DiagnosticCode::evidence_mismatch, "history.casadi_ipopt.initial_duals",
                    "CasADi initial dual readback differs from this NLP's zero dual vector or constraint dimension."};
            casadi::Dict options{{"sb", "yes"},
                                 {"print_level", 0},
                                 {"max_iter", 6000},
                                 {"tol", 1e-11},
                                 {"acceptable_tol", 1e-10},
                                 {"compl_inf_tol", 1e-12},
                                 {"bound_relax_factor", 0.0},
                                 {"warm_start_init_point", "yes"}};
            if (scaling_)
                options["nlp_scaling_method"] = "none";
            if (detect_dependencies_) {
                options["dependency_detector"] = "mumps";
                options["dependency_detection_with_rhs"] = "yes";
            }
            if (context.deadline)
                options["max_wall_time"] =
                    std::max(0.001, std::chrono::duration<double>(*context.deadline -
                                                                  std::chrono::steady_clock::now())
                                        .count());
            opti.solver("ipopt", {{"print_time", false}}, options);
            const auto solution = opti.solve();
            if (context.cancellation.stop_requested())
                return OperationStopped{
                    StopReason::cancelled,
                    "Native CasADi history optimization cancelled during solve"};
            if (context.deadline && std::chrono::steady_clock::now() >= *context.deadline)
                return OperationStopped{StopReason::deadline_expired,
                                        "Native CasADi history optimization deadline reached"};
            const auto diagnostics =
                "native C++ CasADi " + std::string(casadi::CasadiMeta::version()) + "; IPOPT; " +
                opti.stats().at("return_status").to_string() + "; iterations=" +
                std::to_string(static_cast<double>(opti.stats().at("iter_count"))) +
                "; all history coordinates free; local numerical" + configuration_evidence();
            std::vector<optimization::HistoryMembershipWitness> membership_witnesses;
            for (std::size_t i = 0; i < membership_variables.size(); ++i) {
                auto coefficients = membership_variables[i]
                                        ? values(solution.value(*membership_variables[i]))
                                        : Vector{};
                membership_witnesses.push_back(
                    make_witness(request.domain.memberships[i], std::move(coefficients)));
            }
            return optimization::RawHistorySolve{
                values(solution.value(z)), static_cast<double>(solution.value(objective)),
                optimization::SuppliedReadbacks{
                    initial_history, initial_primal, Vector(initial_dual.size(), 0.0), initial_dual,
                    supplied->membership_witnesses, std::move(membership_readbacks)},
                diagnostics, std::move(membership_witnesses)};
        } catch (const std::exception &error) {
            if (context.cancellation.stop_requested())
                return OperationStopped{StopReason::cancelled,
                                        "Native CasADi history optimization cancelled"};
            if (context.deadline && std::chrono::steady_clock::now() >= *context.deadline)
                return OperationStopped{StopReason::deadline_expired,
                                        "Native CasADi history optimization deadline expired"};
            return Diagnostic{DiagnosticCode::unsupported, "history.casadi_ipopt",
                              std::string(error.what()) + configuration_evidence()};
        }
    }
};

registry::Registration<registry::HistoryOptimizerPort>
make_registration(ModuleId id, std::optional<CasadiHistoryScaling> scaling,
                  bool detect_dependencies = false) {
    return {
        {std::move(id), "1"},
        [scaling](const optimization::HistoryOptimizationRequest &request,
                  const registry::Requirements &) -> registry::Capability {
            const auto diagnostics = optimization::check_history_optimization_request(request);
            if (!diagnostics.empty())
                return diagnostics;
            if (scaling && !valid_scaling(*scaling, request.domain.original.coordinates.dimensions))
                return Diagnostics{invalid_scaling()};
            if (!std::holds_alternative<optimization::SuppliedStart>(request.start))
                return Diagnostics{
                    {DiagnosticCode::unsupported, "history.start",
                     "CasADi/IPOPT requires an explicitly supplied feasible full-history start."}};
            return registry::Offer{
                {{"csl.whole-history-source-cost.v1"}, Assurance::numerical, {}, {}, {}}};
        },
        [scaling = std::move(scaling),
         detect_dependencies](const optimization::HistoryOptimizationRequest &)
            -> std::unique_ptr<optimization::HistoryOptimizerWorkspace> {
            return std::make_unique<NativeWorkspace>(scaling, detect_dependencies);
        }};
}
}

registry::Registration<registry::HistoryOptimizerPort>
make_casadi_history_optimizer_registration() {
    return make_registration({"csl.nlp.casadi-ipopt.history-cost"}, {});
}

registry::Registration<registry::HistoryOptimizerPort>
make_casadi_scaled_history_optimizer_registration(CasadiHistoryScaling scaling) {
    return make_registration({"csl.nlp.casadi-ipopt.scaled-history-cost"}, std::move(scaling));
}
registry::Registration<registry::HistoryOptimizerPort>
make_casadi_mumps_history_optimizer_registration(std::optional<CasadiHistoryScaling> scaling) {
    return make_registration({"csl.nlp.casadi-ipopt.mumps-history-cost"}, std::move(scaling), true);
}
} // namespace csl::adapters::nlp
