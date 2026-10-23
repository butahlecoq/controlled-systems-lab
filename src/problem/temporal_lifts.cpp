#include <csl/problem/temporal_lifts.hpp>

#include <algorithm>
#include <cmath>
#include <limits>

namespace csl::problem {
namespace {
Diagnostic invalid(std::string field, std::string explanation) {
    return {DiagnosticCode::invalid_input, std::move(field), std::move(explanation)};
}

Diagnostic unsupported(std::string field, std::string explanation) {
    return {DiagnosticCode::unsupported, std::move(field), std::move(explanation)};
}

std::optional<std::size_t> product(std::size_t left, std::size_t right) {
    if (right != 0 && left > std::numeric_limits<std::size_t>::max() / right) return {};
    return left * right;
}

struct HData {
    Matrix inequalities;
    Vector upper;
    Matrix equalities;
    Vector equality_values;
};

struct SupportedSet {
    bool empty{};
    HData h;
};

using SetResult = std::variant<SupportedSet, Diagnostic>;

HData universal_h(std::size_t dimension) {
    return {{0, dimension, {}}, {}, {0, dimension, {}}, {}};
}

SetResult as_h(const AdmissibleSet& source, std::size_t dimension, const std::string& field) {
    if (const auto* empty = std::get_if<EmptySet>(&source)) {
        if (empty->dimension != dimension) return invalid(field + ".dimension", "Set dimension must match its problem port.");
        return SupportedSet{true, universal_h(dimension)};
    }
    if (const auto* universal = std::get_if<UniversalSet>(&source)) {
        if (universal->dimension != dimension) return invalid(field + ".dimension", "Set dimension must match its problem port.");
        return SupportedSet{false, universal_h(dimension)};
    }
    if (const auto* singleton = std::get_if<Singleton>(&source)) {
        if (singleton->point.size() != dimension) return invalid(field + ".dimension", "Set dimension must match its problem port.");
        const auto area = product(dimension, dimension);
        if (!area) return unsupported(field + ".capacity", "Singleton constraint storage overflows size_t.");
        Matrix identity{dimension, dimension, Vector(*area, 0.0)};
        for (std::size_t i = 0; i < dimension; ++i) identity.values[i * dimension + i] = 1.0;
        return SupportedSet{false, {universal_h(dimension).inequalities, {}, std::move(identity), singleton->point}};
    }

    const auto imported = sets::from_handle(std::get<SetHandle>(source));
    if (const auto* error = std::get_if<Diagnostic>(&imported))
        return Diagnostic{error->code, field + "." + error->field, error->explanation};
    const auto& representation = std::get<sets::SetData>(imported).representation();
    if (const auto* h = std::get_if<sets::HRepresentation>(&representation)) {
        if (h->inequalities.cols() != dimension || h->equalities.cols() != dimension)
            return invalid(field + ".dimension", "Set dimension must match its problem port.");
        const auto inequality_size = product(h->inequalities.rows(), dimension);
        const auto equality_size = product(h->equalities.rows(), dimension);
        if (!inequality_size || !equality_size)
            return unsupported(field + ".capacity", "H representation storage overflows size_t.");
        HData result{{h->inequalities.rows(), dimension, {}}, {}, {h->equalities.rows(), dimension, {}}, {}};
        result.inequalities.values.reserve(*inequality_size);
        result.upper.reserve(h->upper_bounds.size());
        result.equalities.values.reserve(h->equalities.rows() * dimension);
        result.equality_values.reserve(h->equality_values.size());
        for (std::size_t i = 0; i < h->inequalities.rows(); ++i) {
            for (std::size_t j = 0; j < dimension; ++j) result.inequalities.values.push_back(h->inequalities(i, j));
            result.upper.push_back(h->upper_bounds[i]);
        }
        for (std::size_t i = 0; i < h->equalities.rows(); ++i) {
            for (std::size_t j = 0; j < dimension; ++j) result.equalities.values.push_back(h->equalities(i, j));
            result.equality_values.push_back(h->equality_values[i]);
        }
        return SupportedSet{false, std::move(result)};
    }
    if (std::holds_alternative<sets::EmptyRepresentation>(representation))
        return SupportedSet{true, universal_h(dimension)};
    if (std::holds_alternative<sets::UniversalRepresentation>(representation))
        return SupportedSet{false, universal_h(dimension)};
    if (const auto* singleton = std::get_if<sets::SingletonRepresentation>(&representation)) {
        const auto area = product(dimension, dimension);
        if (!area) return unsupported(field + ".capacity", "Singleton constraint storage overflows size_t.");
        if (singleton->point.size() != dimension)
            return invalid(field + ".dimension", "Set dimension must match its problem port.");
        Matrix identity{dimension, dimension, Vector(*area, 0.0)};
        Vector point(dimension);
        for (std::size_t i = 0; i < dimension; ++i) {
            identity.values[i * dimension + i] = 1.0;
            point[i] = singleton->point[i];
        }
        return SupportedSet{false, {universal_h(dimension).inequalities, {}, std::move(identity), std::move(point)}};
    }
    return unsupported(field + ".representation", "The exact memory lift requires native H sets; V representations and ordinary zonotopes are not converted.");
}

SetResult product_set(const AdmissibleSet& left, std::size_t left_dimension,
    const AdmissibleSet& right, std::size_t right_dimension, const std::string& field) {
    auto left_h = as_h(left, left_dimension, field + ".left");
    if (const auto* error = std::get_if<Diagnostic>(&left_h)) return *error;
    auto right_h = as_h(right, right_dimension, field + ".right");
    if (const auto* error = std::get_if<Diagnostic>(&right_h)) return *error;
    const auto& a = std::get<SupportedSet>(left_h);
    const auto& b = std::get<SupportedSet>(right_h);
    if (left_dimension > std::numeric_limits<std::size_t>::max() - right_dimension ||
        a.h.inequalities.rows > std::numeric_limits<std::size_t>::max() - b.h.inequalities.rows ||
        a.h.equalities.rows > std::numeric_limits<std::size_t>::max() - b.h.equalities.rows)
        return unsupported(field + ".capacity", "Product dimensions or row counts overflow size_t.");
    if (a.empty || b.empty) return SupportedSet{true, universal_h(left_dimension + right_dimension)};
    const auto width = left_dimension + right_dimension;
    const auto inequalities = a.h.inequalities.rows + b.h.inequalities.rows;
    const auto equalities = a.h.equalities.rows + b.h.equalities.rows;
    const auto inequality_size = product(inequalities, width);
    const auto equality_size = product(equalities, width);
    if (!inequality_size || !equality_size)
        return unsupported(field + ".capacity", "Product constraint storage overflows size_t.");

    HData joined{{inequalities, width, Vector(*inequality_size, 0.0)}, {},
                 {equalities, width, Vector(*equality_size, 0.0)}, {}};
    joined.upper.reserve(inequalities);
    joined.equality_values.reserve(equalities);
    const auto append_rows = [&](const HData& from, std::size_t row_offset, std::size_t column_offset) {
        for (std::size_t i = 0; i < from.inequalities.rows; ++i) {
            for (std::size_t j = 0; j < from.inequalities.cols; ++j)
                joined.inequalities.values[(row_offset + i) * width + column_offset + j] =
                    from.inequalities.values[i * from.inequalities.cols + j];
            joined.upper.push_back(from.upper[i]);
        }
    };
    append_rows(a.h, 0, 0);
    append_rows(b.h, a.h.inequalities.rows, left_dimension);
    const auto append_equalities = [&](const HData& from, std::size_t row_offset, std::size_t column_offset) {
        for (std::size_t i = 0; i < from.equalities.rows; ++i) {
            for (std::size_t j = 0; j < from.equalities.cols; ++j)
                joined.equalities.values[(row_offset + i) * width + column_offset + j] =
                    from.equalities.values[i * from.equalities.cols + j];
            joined.equality_values.push_back(from.equality_values[i]);
        }
    };
    append_equalities(a.h, 0, 0);
    append_equalities(b.h, a.h.equalities.rows, left_dimension);
    return SupportedSet{false, std::move(joined)};
}

using AdmissibleResult = std::variant<AdmissibleSet, Diagnostic>;
AdmissibleResult publish_set(const SupportedSet& value, std::size_t dimension, std::string id) {
    if (value.empty) return AdmissibleSet{EmptySet{dimension}};
    const auto h = numeric::snapshot(value.h.inequalities);
    const auto upper = numeric::snapshot_vector(value.h.upper);
    const auto e = numeric::snapshot(value.h.equalities);
    const auto equality_values = numeric::snapshot_vector(value.h.equality_values);
    for (const auto* item : {&h, &e}) if (const auto* error = std::get_if<Diagnostic>(item)) return *error;
    for (const auto* item : {&upper, &equality_values}) if (const auto* error = std::get_if<Diagnostic>(item)) return *error;
    auto result = sets::make_h({{std::move(id)}, dimension, {}},
        {std::get<numeric::MatrixView>(h), std::get<numeric::VectorView>(upper),
         std::get<numeric::MatrixView>(e), std::get<numeric::VectorView>(equality_values)});
    if (const auto* error = std::get_if<Diagnostic>(&result)) return *error;
    return AdmissibleSet{std::get<sets::SetData>(std::move(result)).as_handle()};
}

using ObjectiveResult = std::variant<TerminalObjective, Diagnostic>;
ObjectiveResult lift_objective(const TerminalObjective& objective, std::size_t state_width,
    std::size_t lifted_width) {
    return std::visit([&](const auto& value) -> ObjectiveResult {
        using T = std::decay_t<decltype(value)>;
        if constexpr (std::is_same_v<T, LinearTerminal>) {
            Vector coefficients(lifted_width, 0.0);
            std::copy(value.coefficients.begin(), value.coefficients.end(), coefficients.begin());
            return LinearTerminal{std::move(coefficients), value.offset};
        } else if constexpr (std::is_same_v<T, QuadraticTerminal>) {
            const auto area = product(lifted_width, lifted_width);
            if (!area) return invalid("problem.temporal_lift.objective.capacity", "Lifted objective storage overflows size_t.");
            Matrix q{lifted_width, lifted_width, Vector(*area, 0.0)};
            for (std::size_t i = 0; i < state_width; ++i)
                for (std::size_t j = 0; j < state_width; ++j)
                    q.values[i * lifted_width + j] = value.Q.values[i * state_width + j];
            Vector linear(lifted_width, 0.0);
            std::copy(value.linear.begin(), value.linear.end(), linear.begin());
            return QuadraticTerminal{std::move(q), std::move(linear), value.offset};
        } else {
            const auto area = product(value.map.rows, lifted_width);
            if (!area) return invalid("problem.temporal_lift.objective.capacity", "Lifted residual storage overflows size_t.");
            Matrix map{value.map.rows, lifted_width, Vector(*area, 0.0)};
            for (std::size_t i = 0; i < value.map.rows; ++i)
                for (std::size_t j = 0; j < state_width; ++j)
                    map.values[i * lifted_width + j] = value.map.values[i * state_width + j];
            return ResidualNormTerminal{std::move(map), value.target};
        }
    }, objective);
}

Diagnostic validate_history(const SlewCoordinateMap& map, const ControlHistory& history) {
    const auto n = map.original.dimensions.state;
    const auto m = map.original.dimensions.control;
    const auto t = map.original.horizon;
    if (n > std::numeric_limits<std::size_t>::max() - m || t == std::numeric_limits<std::size_t>::max() ||
        map.initial_memory.size() != m ||
        !std::all_of(map.initial_memory.begin(), map.initial_memory.end(), [](double value) { return std::isfinite(value); }) ||
        n + m > static_cast<std::size_t>(std::numeric_limits<std::ptrdiff_t>::max()) ||
        t > static_cast<std::size_t>(std::numeric_limits<std::ptrdiff_t>::max()))
        return invalid("problem.temporal_lift.history.capacity", "History dimensions, initial memory or coordinate offsets are inconsistent or exceed iterator range.");
    if (history.states.size() != t + 1 || history.controls.size() != t)
        return invalid("problem.temporal_lift.history.stages", "Original history must contain T+1 states and T controls.");
    for (std::size_t i = 0; i <= t; ++i)
        if (history.states[i].size() != n || !std::all_of(history.states[i].begin(), history.states[i].end(), [](double x) { return std::isfinite(x); }))
            return invalid("problem.temporal_lift.history.states", "Every original state must be finite and match the state dimension.");
    for (std::size_t i = 0; i < t; ++i)
        if (history.controls[i].size() != m || !std::all_of(history.controls[i].begin(), history.controls[i].end(), [](double x) { return std::isfinite(x); }))
            return invalid("problem.temporal_lift.history.controls", "Every original control must be finite and match the control dimension.");
    return {DiagnosticCode::invalid_input, {}, {}};
}

} // namespace

SlewLiftResult lift_one_step_slew(const Problem& authored, const SlewMemoryRequest& request) {
    if (!authored.model) return invalid("problem.temporal_lift.model", "A model is required.");
    auto publication = resolve(authored, {UncertaintyStructure::stage_product_uncoupled, {}, {}});
    if (const auto* error = std::get_if<Diagnostic>(&publication)) return *error;
    if (const auto* stopped = std::get_if<OperationStopped>(&publication)) return *stopped;
    const auto source = std::get<ResolvedProblem>(std::move(publication)).description();
    const auto dimensions = source->model->dynamics.dimensions;
    const auto horizon = source->model->dynamics.time_domain == TimeDomain::discrete ? source->times.size() - 1 : 0;
    if (source->model->dynamics.time_domain != TimeDomain::discrete)
        return unsupported("problem.temporal_lift.time_domain", "Only discrete-time dynamics are supported.");
    if (source->information != InformationPattern::nominal_open_loop || source->external || dimensions.external != 0 ||
        !source->model->observations.empty())
        return unsupported("problem.temporal_lift.profile", "The memory lift supports nominal open-loop problems without external or observation channels.");
    if (!std::holds_alternative<KnownInitial>(source->initial))
        return unsupported("problem.temporal_lift.initial", "A known initial state is required.");
    const auto* controls = std::get_if<ContinuousDomain>(&source->controls);
    if (!controls) return unsupported("problem.temporal_lift.controls", "Continuous controls are required.");
    if (source->temporal && source->temporal->joint_map.rows != 0)
        return unsupported("problem.temporal_lift.temporal", "The one-step slew lift does not combine with an existing temporal relation.");
    if (request.later_increments.size() != (horizon == 0 ? 0 : horizon - 1))
        return invalid("problem.temporal_lift.increments", "Supply one increment set for each stage after stage zero.");

    Vector initial_memory;
    const AdmissibleSet* first_increment = nullptr;
    if (std::holds_alternative<UnconstrainedFirstAction>(request.first_action)) {
        initial_memory.assign(dimensions.control, 0.0);
    } else {
        const auto& first = std::get<RateLimitedFirstAction>(request.first_action);
        if (first.previous_control.size() != dimensions.control ||
            !std::all_of(first.previous_control.begin(), first.previous_control.end(), [](double x) { return std::isfinite(x); }))
            return invalid("problem.temporal_lift.previous_control", "Previous control must be finite and match the control dimension.");
        initial_memory = first.previous_control;
        first_increment = &first.increment_set;
    }

    if (dimensions.state > std::numeric_limits<std::size_t>::max() - dimensions.control)
        return unsupported("problem.temporal_lift.capacity", "Augmented state dimension overflows size_t.");
    const auto n = dimensions.state;
    const auto m = dimensions.control;
    const auto augmented_n = n + m;
    if (augmented_n > static_cast<std::size_t>(std::numeric_limits<std::ptrdiff_t>::max()))
        return unsupported("problem.temporal_lift.capacity", "Augmented state offsets exceed iterator range.");
    if (augmented_n != 0 && augmented_n > std::numeric_limits<std::size_t>::max() / augmented_n)
        return unsupported("problem.temporal_lift.capacity", "Augmented transition matrix size overflows size_t.");
    if (m != 0 && augmented_n > std::numeric_limits<std::size_t>::max() / m)
        return unsupported("problem.temporal_lift.capacity", "Augmented input matrix size overflows size_t.");

    const auto initial = std::get<KnownInitial>(source->initial).point;
    Vector augmented_initial(augmented_n);
    std::copy(initial.begin(), initial.end(), augmented_initial.begin());
    std::copy(initial_memory.begin(), initial_memory.end(), augmented_initial.begin() + static_cast<std::ptrdiff_t>(n));

    std::vector<LinearStage> stages;
    stages.reserve(horizon);
    for (std::size_t t = 0; t < horizon; ++t) {
        const LinearStage* original = nullptr;
        if (const auto* constant = std::get_if<LinearStage>(&source->model->dynamics.stages)) original = constant;
        else original = &std::get<std::vector<LinearStage>>(source->model->dynamics.stages)[t];
        Matrix a{augmented_n, augmented_n, Vector(augmented_n * augmented_n, 0.0)};
        Matrix b{augmented_n, m, Vector(augmented_n * m, 0.0)};
        Vector offset(augmented_n, 0.0);
        for (std::size_t i = 0; i < n; ++i) {
            offset[i] = original->offset[i];
            for (std::size_t j = 0; j < n; ++j) a.values[i * augmented_n + j] = original->A.values[i * n + j];
            for (std::size_t j = 0; j < m; ++j) {
                a.values[i * augmented_n + n + j] = original->B.values[i * m + j];
                b.values[i * m + j] = original->B.values[i * m + j];
                a.values[(n + j) * augmented_n + n + j] = 1.0;
                b.values[(n + j) * m + j] = 1.0;
            }
        }
        stages.push_back({std::move(a), std::move(b), {augmented_n, 0, {}}, std::move(offset)});
    }

    std::vector<AdmissibleSet> lifted_states;
    lifted_states.reserve(horizon + 1);
    std::vector<AdmissibleSet> lifted_controls;
    lifted_controls.reserve(horizon);
    for (std::size_t t = 0; t <= horizon; ++t) {
        const AdmissibleSet memory = t == 0 ? AdmissibleSet{Singleton{initial_memory}} : controls->stages[t - 1];
        auto state = product_set(source->states[t], n, memory, m, "problem.temporal_lift.states[" + std::to_string(t) + "]");
        if (const auto* error = std::get_if<Diagnostic>(&state)) return *error;
        auto published = publish_set(std::get<SupportedSet>(state), augmented_n, source->id.value + ".slew.state." + std::to_string(t));
        if (const auto* error = std::get_if<Diagnostic>(&published)) return *error;
        lifted_states.push_back(std::get<AdmissibleSet>(std::move(published)));
        if (t == horizon) continue;

        const AdmissibleSet& increment = t == 0
            ? (first_increment ? *first_increment : controls->stages.front())
            : request.later_increments[t - 1];
        auto supported = as_h(increment, m, "problem.temporal_lift.increments[" + std::to_string(t) + "]");
        if (const auto* error = std::get_if<Diagnostic>(&supported)) return *error;
        auto control = publish_set(std::get<SupportedSet>(supported), m, source->id.value + ".slew.increment." + std::to_string(t));
        if (const auto* error = std::get_if<Diagnostic>(&control)) return *error;
        lifted_controls.push_back(std::get<AdmissibleSet>(std::move(control)));
    }

    const auto lifted_width = product(horizon + 1, augmented_n);
    const auto lifted_control_width = product(horizon, m);
    if (!lifted_width || !lifted_control_width || *lifted_width > std::numeric_limits<std::size_t>::max() - *lifted_control_width)
        return unsupported("problem.temporal_lift.capacity", "Lifted joint coordinate width overflows size_t.");
    auto lifted_objective = lift_objective(source->objective, n, augmented_n);
    if (const auto* error = std::get_if<Diagnostic>(&lifted_objective)) return *error;
    const auto lifted_id = source->id.value.empty() ? "slew-memory-lift" : source->id.value + ".slew-memory-lift";
    Problem result{{lifted_id}, std::make_shared<const SystemModel>(SystemModel{
        {{augmented_n, m, 0}, TimeDomain::discrete, std::move(stages)}, {} }), source->times,
        KnownInitial{std::move(augmented_initial)}, ContinuousDomain{std::move(lifted_controls)},
        std::move(lifted_states), {}, {}, InformationPattern::nominal_open_loop,
        std::get<TerminalObjective>(std::move(lifted_objective))};

    const auto original_state_width = product(horizon + 1, n);
    const auto original_control_width = product(horizon, m);
    if (!original_state_width || !original_control_width || *original_state_width > std::numeric_limits<std::size_t>::max() - *original_control_width)
        return unsupported("problem.temporal_lift.capacity", "Original joint coordinate width overflows size_t.");
    SlewCoordinateMap map{{dimensions, horizon}, {{augmented_n, m, 0}, horizon}, initial_memory, {}, {}, {}};
    map.original_state_to_lifted_state.reserve(*original_state_width);
    for (std::size_t t = 0; t <= horizon; ++t)
        for (std::size_t j = 0; j < n; ++j) map.original_state_to_lifted_state.push_back(t * augmented_n + j);
    map.original_control_to_lifted_memory.reserve(*original_control_width);
    map.lifted_increment_to_original_control.reserve(*original_control_width);
    for (std::size_t t = 0; t < horizon; ++t)
        for (std::size_t j = 0; j < m; ++j) {
            map.original_control_to_lifted_memory.push_back((t + 1) * augmented_n + n + j);
            map.lifted_increment_to_original_control.push_back(*original_state_width + t * m + j);
        }
    return SlewMemoryLift{std::move(result), std::move(map)};
}

HistoryMapResult lift_history(const SlewCoordinateMap& map, const ControlHistory& original) {
    const auto failure = validate_history(map, original);
    if (!failure.field.empty()) return failure;
    const auto n = map.original.dimensions.state;
    const auto m = map.original.dimensions.control;
    LiftedControlHistory lifted;
    lifted.augmented_states.reserve(original.states.size());
    lifted.increments.reserve(original.controls.size());
    for (std::size_t t = 0; t < original.states.size(); ++t) {
        Vector state(n + m);
        std::copy(original.states[t].begin(), original.states[t].end(), state.begin());
        const auto& memory = t == 0 ? map.initial_memory : original.controls[t - 1];
        std::copy(memory.begin(), memory.end(), state.begin() + static_cast<std::ptrdiff_t>(n));
        lifted.augmented_states.push_back(std::move(state));
        if (t < original.controls.size()) {
            Vector increment(m);
            for (std::size_t j = 0; j < m; ++j) {
                increment[j] = original.controls[t][j] - memory[j];
                if (!std::isfinite(increment[j]))
                    return invalid("problem.temporal_lift.history.increments", "Control difference exceeds finite numeric range.");
            }
            lifted.increments.push_back(std::move(increment));
        }
    }
    return lifted;
}

HistoryMapResult recover_history(const SlewCoordinateMap& map, const LiftedControlHistory& lifted,
    double absolute_tolerance, double relative_tolerance) {
    const auto n = map.original.dimensions.state;
    const auto m = map.original.dimensions.control;
    const auto t = map.original.horizon;
    if (n > std::numeric_limits<std::size_t>::max() - m ||
        n + m > static_cast<std::size_t>(std::numeric_limits<std::ptrdiff_t>::max()))
        return invalid("problem.temporal_lift.history.capacity", "Lifted history coordinate offsets exceed iterator range.");
    if (!std::isfinite(absolute_tolerance) || absolute_tolerance < 0.0 ||
        !std::isfinite(relative_tolerance) || relative_tolerance < 0.0 ||
        !std::isfinite(absolute_tolerance + relative_tolerance))
        return invalid("problem.temporal_lift.history.tolerance", "Recovery tolerances must be finite and nonnegative.");
    if (map.initial_memory.size() != m ||
        !std::all_of(map.initial_memory.begin(), map.initial_memory.end(), [](double value) { return std::isfinite(value); }))
        return invalid("problem.temporal_lift.history.initial_memory", "Initial memory must match the original control dimension.");
    if (lifted.augmented_states.size() != t + 1 || lifted.increments.size() != t)
        return invalid("problem.temporal_lift.history.stages", "Lifted history must contain T+1 augmented states and T increments.");
    ControlHistory original;
    original.states.reserve(t + 1);
    original.controls.reserve(t);
    for (std::size_t stage = 0; stage <= t; ++stage) {
        const auto& state = lifted.augmented_states[stage];
        if (state.size() != n + m || !std::all_of(state.begin(), state.end(), [](double x) { return std::isfinite(x); }))
            return invalid("problem.temporal_lift.history.augmented_states", "Every augmented state must be finite and match the lifted dimension.");
        if (stage == 0) for (std::size_t j = 0; j < m; ++j) {
            const double expected = map.initial_memory[j];
            const double scale = std::max({1.0, std::abs(expected), std::abs(state[n + j])});
            if (std::abs(state[n + j] - expected) > absolute_tolerance + relative_tolerance * scale)
                return invalid("problem.temporal_lift.history.initial_memory", "Lifted initial memory does not match the declared prior control.");
        }
        original.states.emplace_back(state.begin(), state.begin() + static_cast<std::ptrdiff_t>(n));
        if (stage < t) {
            const auto& increment = lifted.increments[stage];
            if (increment.size() != m || !std::all_of(increment.begin(), increment.end(), [](double x) { return std::isfinite(x); }))
                return invalid("problem.temporal_lift.history.increments", "Every increment must be finite and match the control dimension.");
            const auto& next = lifted.augmented_states[stage + 1];
            if (next.size() != n + m)
                return invalid("problem.temporal_lift.history.augmented_states", "Every augmented state must match the lifted dimension.");
            for (std::size_t j = 0; j < m; ++j) {
                const double expected = state[n + j] + increment[j];
                const double actual = next[n + j];
                if (!std::isfinite(expected))
                    return invalid("problem.temporal_lift.history.recurrence", "Memory recurrence exceeds finite numeric range.");
                const double scale = std::max({1.0, std::abs(expected), std::abs(actual)});
                const long double residual = std::abs(static_cast<long double>(actual) - expected);
                const long double allowed = static_cast<long double>(absolute_tolerance) +
                    static_cast<long double>(relative_tolerance) * scale;
                if (residual > allowed)
                    return invalid("problem.temporal_lift.history.recurrence", "Lifted increment does not satisfy p[t+1]=p[t]+v[t].");
            }
            original.controls.emplace_back(next.begin() + static_cast<std::ptrdiff_t>(n), next.end());
        }
    }
    return original;
}

} // namespace csl::problem
