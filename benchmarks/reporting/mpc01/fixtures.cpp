#include "fixtures.hpp"

#include <csl/input/scenario_loader.hpp>
#include <csl/model/linear_system.hpp>
#include <csl/optimization/objectives.hpp>
#include <csl/problem/resolved_problem.hpp>
#include <csl/sets/data.hpp>
#include <nlohmann/json.hpp>

#include <cmath>
#include <fstream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <span>
#include <type_traits>

namespace csl::mpc01 {
namespace {

Matrix copy_matrix(const numeric::MatrixView& source) {
    Matrix result(source.rows(), Vector(source.cols()));
    for (std::size_t i = 0; i < source.rows(); ++i) {
        for (std::size_t j = 0; j < source.cols(); ++j) result[i][j] = source(i, j);
    }
    return result;
}

std::string digest_text(const std::string& text) {
    const auto bytes = std::as_bytes(std::span{text.data(), text.size()});
    auto snapshot = problem::snapshot_content(bytes);
    if (const auto* error = std::get_if<Diagnostic>(&snapshot)) {
        throw std::runtime_error("cannot hash analytic fixture: " + error->explanation);
    }
    return problem::hex(std::get<problem::ResolvedContent>(snapshot).digest());
}

Vector copy_vector(const numeric::VectorView& source) {
    return Vector(source.values().begin(), source.values().end());
}

using BoxResult = std::variant<std::optional<Box>, std::string>;
using json = nlohmann::json;

double rational(const json& value) {
    if (!value.is_string()) throw std::runtime_error("exact numeric values must be strings");
    const auto text = value.get<std::string>();
    const auto slash = text.find('/');
    const long double numerator = std::stold(text.substr(0, slash));
    const long double denominator = slash == std::string::npos
                                        ? 1.0L
                                        : std::stold(text.substr(slash + 1));
    if (denominator == 0.0L) throw std::runtime_error("zero rational denominator");
    const double result = static_cast<double>(numerator / denominator);
    if (!std::isfinite(result)) throw std::runtime_error("nonfinite rational value");
    return result;
}

Vector rational_vector(const json& values) {
    Vector result;
    result.reserve(values.size());
    for (const auto& value : values) result.push_back(rational(value));
    return result;
}

Matrix rational_matrix(const json& values, std::size_t rows, std::size_t columns) {
    if (values.size() != rows * columns) throw std::runtime_error("matrix coefficient count mismatch");
    Matrix result(rows, Vector(columns));
    for (std::size_t i = 0; i < rows; ++i) {
        for (std::size_t j = 0; j < columns; ++j) {
            result[i][j] = rational(values[i * columns + j]);
        }
    }
    return result;
}

BoxResult as_axis_aligned_box(const AdmissibleSet& set, std::size_t dimension,
                              const std::string& path) {
    if (std::holds_alternative<UniversalSet>(set)) return std::optional<Box>{};
    if (const auto* singleton = std::get_if<Singleton>(&set)) {
        if (singleton->point.size() != dimension) return path + ": singleton dimension mismatch";
        return std::optional<Box>{Box{singleton->point, singleton->point}};
    }
    const auto* handle = std::get_if<SetHandle>(&set);
    if (!handle) return path + ": empty sets are unsupported in a feasible MPC fixture";
    auto native = sets::from_handle(*handle);
    if (const auto* error = std::get_if<Diagnostic>(&native)) {
        return path + ": cannot read set representation: " + error->explanation;
    }
    const auto representation = std::get<sets::SetData>(std::move(native)).representation();
    const auto* h = std::get_if<sets::HRepresentation>(&representation);
    if (!h || h->equalities.rows() != 0) {
        return path + ": only equality-free H-represented boxes are supported";
    }
    Box box{Vector(dimension, -std::numeric_limits<double>::infinity()),
            Vector(dimension, std::numeric_limits<double>::infinity())};
    for (std::size_t row = 0; row < h->inequalities.rows(); ++row) {
        std::optional<std::size_t> coordinate;
        double coefficient = 0.0;
        for (std::size_t column = 0; column < dimension; ++column) {
            const double value = h->inequalities(row, column);
            if (value == 0.0) continue;
            if (coordinate) return path + ": non-axis-aligned halfspace is unsupported";
            coordinate = column;
            coefficient = value;
        }
        const double bound = h->upper_bounds[row];
        if (!coordinate) {
            if (bound < 0.0) return path + ": contradictory zero halfspace";
            continue;
        }
        if (coefficient > 0.0) {
            box.upper[*coordinate] = std::min(box.upper[*coordinate], bound / coefficient);
        } else {
            box.lower[*coordinate] = std::max(box.lower[*coordinate], bound / coefficient);
        }
    }
    for (std::size_t i = 0; i < dimension; ++i) {
        if (box.lower[i] > box.upper[i]) return path + ": inconsistent interval bounds";
        if (!std::isfinite(box.lower[i]) && !std::isfinite(box.upper[i])) {
            // A fully universal box is represented by no bounds at all.
            return path + ": unconstrained H row set should be represented as universal";
        }
    }
    return std::optional<Box>{std::move(box)};
}

FixtureLoad from_loaded_scenario(const input::LoadedScenario& loaded,
                                const std::filesystem::path& path) {
    const auto resolved = loaded.problem();
    const auto system = resolved.model();
    const auto dimensions = system.dimensions();
    const auto nx = dimensions.state;
    const auto nu = dimensions.control;
    const auto horizon = system.horizon();
    const auto initial_description = resolved.initial().description();
    const auto* known = std::get_if<KnownInitial>(initial_description.get());
    if (!known) return "#421 loader requires a known initial state";

    MpcCase result;
    result.id = "double-integrator-421-v1";
    result.version = "1";
    result.source_kind = "closed-issue-generality-fixture";
    result.source_ref = path.generic_string();
    const auto provenance = loaded.source();
    result.canonical_input_sha256 = problem::hex(provenance->content.digest());
    const auto source_bytes = provenance->content.bytes();
    result.canonical_input_bytes.assign(reinterpret_cast<const char*>(source_bytes.data()), source_bytes.size());
    result.initial_state = known->point;
    result.dynamics.reserve(horizon);
    for (std::size_t t = 0; t < horizon; ++t) {
        auto stage = system.stage(StageIndex{t});
        if (const auto* error = std::get_if<Diagnostic>(&stage)) {
            return "cannot read #421 dynamics stage " + std::to_string(t) + ": " + error->explanation;
        }
        const auto& dynamics = std::get<model::DynamicsStage>(stage);
        result.dynamics.push_back({copy_matrix(dynamics.A), copy_matrix(dynamics.B),
                                   copy_vector(dynamics.offset)});
    }
    const auto objective = resolved.objective();
    result.terminal_cost = std::visit([](const auto& coefficients) -> TerminalCost {
        using Cost = std::decay_t<decltype(coefficients)>;
        if constexpr (std::is_same_v<Cost, optimization::QuadraticCoefficients>) {
            return QuadraticTerminalCost{copy_matrix(coefficients.Q),
                                         copy_vector(coefficients.linear), coefficients.offset};
        } else if constexpr (std::is_same_v<Cost, optimization::ResidualCoefficients>) {
            return AffineResidualNormTerminalCost{copy_matrix(coefficients.map),
                                                  copy_vector(coefficients.target)};
        } else {
            throw std::runtime_error("#421 fixture requires a quadratic or residual norm objective");
        }
    }, objective.coefficients());

    result.stages.resize(horizon + 1);
    const auto state_sets = resolved.constraints().states();
    if (state_sets->size() != horizon + 1) return "#421 state-set count is not horizon+1";
    const auto controls = resolved.controls().description();
    const auto* continuous = std::get_if<ContinuousDomain>(controls.get());
    if (!continuous || continuous->stages.size() != horizon) {
        return "#421 fixture requires one continuous control set per stage";
    }
    for (std::size_t t = 0; t <= horizon; ++t) {
        auto state_box = as_axis_aligned_box(state_sets->at(t), nx,
                                             "#421 states[" + std::to_string(t) + "]");
        if (const auto* error = std::get_if<std::string>(&state_box)) return *error;
        result.stages[t].state = std::get<std::optional<Box>>(std::move(state_box));
        if (t < horizon) {
            auto control_box = as_axis_aligned_box(continuous->stages[t], nu,
                                                   "#421 controls[" + std::to_string(t) + "]");
            if (const auto* error = std::get_if<std::string>(&control_box)) return *error;
            result.stages[t].control = std::get<std::optional<Box>>(std::move(control_box));
        }
    }
    if (const auto metadata = loaded.metadata()) {
        if (metadata->state_labels) result.state_labels = *metadata->state_labels;
        if (metadata->state_units) result.state_units = *metadata->state_units;
        if (metadata->control_labels) result.control_labels = *metadata->control_labels;
        if (metadata->control_units) result.control_units = *metadata->control_units;
    }
    if (auto error = validate(result)) {
        return "invalid resolved #421 fixture at " + error->path + ": " + error->message;
    }
    return result;
}

} // namespace

MpcCase make_ts01() {
    MpcCase result;
    result.id = "ts01-exact-v1";
    result.version = "1";
    result.source_kind = "analytic-contract";
    result.source_ref = "docs/superpowers/specs/2026-10-12-class-level-system-architecture.md#ts01";
    result.canonical_input_bytes = R"({"schema":"csl.mpc01-fixture/1","id":"ts01-exact-v1","x0":[0],"A":[[1],[1]],"B":[[1],[1]],"u":[[0,1],[0,1]],"cost":{"kind":"quadratic","Q":[[2]],"linear":[-2],"offset":1}})";
    result.canonical_input_sha256 = digest_text(result.canonical_input_bytes);
    result.initial_state = {0.0};
    result.dynamics = {{{{1.0}}, {{1.0}}, {0.0}}, {{{1.0}}, {{1.0}}, {0.0}}};
    result.stages = {{{}, Box{{0.0}, {1.0}}}, {{}, Box{{0.0}, {1.0}}}, {{}, {}}};
    result.terminal_cost = QuadraticTerminalCost{{{2.0}}, {-2.0}, 1.0};
    return result;
}

MpcCase make_ts02() {
    auto result = make_ts01();
    result.id = "ts02-constant-v1";
    result.source_ref = "docs/contracts/complete-family-verifier-seam-blocker.md#ts02";
    result.terminal_cost = QuadraticTerminalCost{{{0.0}}, {0.0}, 3.0};
    result.canonical_input_bytes = R"({"schema":"csl.mpc01-fixture/1","id":"ts02-constant-v1","x0":[0],"A":[[1],[1]],"B":[[1],[1]],"u":[[0,1],[0,1]],"cost":{"kind":"quadratic","Q":[[0]],"linear":[0],"offset":3}})";
    result.canonical_input_sha256 = digest_text(result.canonical_input_bytes);
    return result;
}

MpcCase make_ts03_singular() {
    MpcCase result;
    result.id = "ts03-singular-v1";
    result.version = "1";
    result.source_kind = "analytic-contract";
    result.source_ref = "docs/architecture/framework-composition.md#ts03";
    result.canonical_input_bytes = R"({"schema":"csl.mpc01-fixture/1","id":"ts03-singular-v1","x0":[0],"A":[[0],[0]],"B":[[1],[1]],"u":[[0,1],[0,1]],"cost":{"kind":"quadratic","Q":[[2]],"linear":[-2],"offset":1}})";
    result.canonical_input_sha256 = digest_text(result.canonical_input_bytes);
    result.initial_state = {0.0};
    result.dynamics = {{{{0.0}}, {{1.0}}, {0.0}}, {{{0.0}}, {{1.0}}, {0.0}}};
    result.stages = {{{}, Box{{0.0}, {1.0}}}, {{}, Box{{0.0}, {1.0}}}, {{}, {}}};
    result.terminal_cost = QuadraticTerminalCost{{{2.0}}, {-2.0}, 1.0};
    return result;
}

MpcCase make_infeasible() {
    MpcCase result;
    result.id = "infeasible-integrator-v1";
    result.version = "1";
    result.source_kind = "analytic-contract";
    result.source_ref = "benchmarks/reporting/mpc01/fixtures.cpp#make_infeasible";
    result.canonical_input_bytes = R"({"schema":"csl.mpc01-fixture/1","id":"infeasible-integrator-v1","x0":[0],"A":[[1]],"B":[[1]],"u":[[0,0]],"x1":[1,1],"cost":{"kind":"quadratic","Q":[[2]],"linear":[0],"offset":0}})";
    result.canonical_input_sha256 = digest_text(result.canonical_input_bytes);
    result.initial_state = {0.0};
    result.dynamics = {{{{1.0}}, {{1.0}}, {0.0}}};
    result.stages = {{{}, Box{{0.0}, {0.0}}}, {Box{{1.0}, {1.0}}, {}}};
    result.terminal_cost = QuadraticTerminalCost{{{2.0}}, {0.0}, 0.0};
    return result;
}

MpcCase make_unbounded() {
    MpcCase result;
    result.id = "unbounded-integrator-v1";
    result.version = "1";
    result.source_kind = "analytic-contract";
    result.source_ref = "benchmarks/reporting/mpc01/fixtures.cpp#make_unbounded";
    result.canonical_input_bytes = R"({"schema":"csl.mpc01-fixture/1","id":"unbounded-integrator-v1","x0":[0],"A":[[1]],"B":[[1]],"u":[null],"cost":{"kind":"quadratic","Q":[[0]],"linear":[-1],"offset":0}})";
    result.canonical_input_sha256 = digest_text(result.canonical_input_bytes);
    result.initial_state = {0.0};
    result.dynamics = {{{{1.0}}, {{1.0}}, {0.0}}};
    result.stages = {{{}, std::nullopt}, {{}, {}}};
    result.terminal_cost = QuadraticTerminalCost{{{0.0}}, {-1.0}, 0.0};
    return result;
}

FixtureLoad load_double_integrator_421(const std::filesystem::path& path) {
    auto loaded = input::load_scenario_file(path);
    if (const auto* error = std::get_if<input::InputFailure>(&loaded)) {
        return "#421 scenario load failure at " + error->path + ": " + error->observed;
    }
    if (const auto* unsupported = std::get_if<input::UnsupportedInput>(&loaded)) {
        return "#421 scenario uses unsupported input " + unsupported->feature + " at " + unsupported->path;
    }
    const auto* scenario = std::get_if<input::LoadedScenario>(&loaded);
    if (!scenario) return "#421 scenario load was stopped";
    if (scenario->metadata()->id != "double-integrator-generality") {
        return "scenario ID does not match the closed #421 fixture";
    }
    return from_loaded_scenario(*scenario, path);
}

FixtureLoad load_b04_reference_v1(const std::filesystem::path& path) {
    try {
        std::ifstream input_file(path, std::ios::binary);
        if (!input_file) return "cannot open b04-reference-v1 canonical case: " + path.string();
        const std::string canonical_bytes((std::istreambuf_iterator<char>(input_file)), {});
        const json document = json::parse(canonical_bytes);
        if (document.at("case_id") != "b04-reference-v1") {
            return "case identity does not match b04-reference-v1";
        }
        const auto horizon = document.at("horizon").get<std::size_t>();
        const auto nx = document.at("state_dimension").get<std::size_t>();
        const auto nu = document.at("control_dimension").get<std::size_t>();
        if (horizon != 16 || nx != 4 || nu != 1) {
            return "b04-reference-v1 must retain its canonical 4-state, 1-control, horizon-16 dimensions";
        }
        const auto& dynamics = document.at("dynamics");
        if (document.at("state_indices") != json::array({0, horizon}) ||
            document.at("control_indices") != json::array({0, horizon - 1})) {
            return "B04 state/control index ranges differ from the canonical trajectory convention";
        }
        MpcCase result;
        result.id = "b04-reference-v1";
        result.version = "1";
        result.source_kind = "article-derived-owner-authorized-reference";
        result.source_ref = path.generic_string();
        result.canonical_input_bytes = canonical_bytes;
        result.canonical_input_sha256 = digest_text(result.canonical_input_bytes);
        result.initial_state = rational_vector(document.at("initial_state"));
        const auto a = rational_matrix(dynamics.at("A_row_major"), nx, nx);
        const auto b = rational_vector(dynamics.at("B"));
        const auto affine = rational_vector(dynamics.at("affine"));
        if (b.size() != nx || affine.size() != nx) return "B04 dynamics vector dimensions are invalid";
        result.dynamics.assign(horizon, StageDynamics{a, Matrix{{b[0]}, {b[1]}, {b[2]}, {b[3]}}, affine});

        result.stages.resize(horizon + 1);
        const auto control_lower = rational(document.at("control_bounds_each_stage").at("lower"));
        const auto control_upper = rational(document.at("control_bounds_each_stage").at("upper"));
        if (control_lower != -1.0 || control_upper != 1.0) {
            return "B04 control domain differs from its separately authorized reference identity";
        }
        for (std::size_t t = 0; t < horizon; ++t) {
            result.stages[t].control = Box{{control_lower}, {control_upper}};
        }
        const auto& bound_stages = document.at("state_bound_stages");
        if (bound_stages != json::array({0, horizon})) return "B04 state bounds must apply only at stages 0 and 16";
        for (auto stage : {std::size_t{0}, horizon}) {
            Box box{Vector(nx, -std::numeric_limits<double>::infinity()),
                    Vector(nx, std::numeric_limits<double>::infinity())};
            for (const auto& coordinate_bound : document.at("state_bounds_each_stage")) {
                const auto coordinate = coordinate_bound.at("coordinate").get<std::size_t>();
                if (coordinate >= nx) return "B04 state-bound coordinate is outside the state vector";
                box.lower[coordinate] = rational(coordinate_bound.at("lower"));
                box.upper[coordinate] = rational(coordinate_bound.at("upper"));
            }
            result.stages[stage].state = std::move(box);
        }

        const auto& objective = document.at("terminal_objective");
        if (objective.at("kind") != "affine_residual_euclidean_norm") {
            return "B04 objective convention is not the canonical affine residual norm";
        }
        const auto rows = objective.at("matrix_rows").get<std::size_t>();
        const auto columns = objective.at("matrix_cols").get<std::size_t>();
        if (rows != 5 || columns != nx ||
            objective.at("reported_value_convention") != "euclidean_norm_not_squared_norm") {
            return "B04 residual norm dimensions or value convention changed";
        }
        result.terminal_cost = AffineResidualNormTerminalCost{
            rational_matrix(objective.at("W_row_major"), rows, columns),
            rational_vector(objective.at("target"))};
        result.state_labels = {"oxidizer_flow", "oxidizer_working_stock", "fuel_flow", "fuel_working_stock"};
        result.state_units = {"kg/s", "kg", "kg/s", "kg"};
        result.control_labels = {"control"};
        result.control_units = {"kg/s"};
        if (auto error = validate(result)) {
            return "invalid b04-reference-v1 at " + error->path + ": " + error->message;
        }
        return result;
    } catch (const std::exception& error) {
        return std::string("b04-reference-v1 load failure: ") + error.what();
    }
}

} // namespace csl::mpc01
