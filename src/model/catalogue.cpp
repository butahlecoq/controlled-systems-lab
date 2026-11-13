#include <csl/model/catalogue.hpp>
#include <csl/model/flexible_pitch.hpp>
#include <csl/model/spatial_flight_catalogue.hpp>

#include <algorithm>
#include <array>
#include <numeric>
#include <string>

namespace csl::model::catalogue {
namespace {
constexpr std::array states{Coordinate{"x1", "unspecified"},
    Coordinate{"x2", "unspecified"}, Coordinate{"x3", "unspecified"}};
constexpr std::array controls{Coordinate{"u", "unspecified"}};
constexpr std::array two_controls{Coordinate{"u1", "unspecified"}, Coordinate{"u2", "unspecified"}};
constexpr std::array four_states{Coordinate{"x1", "unspecified"}, Coordinate{"x2", "unspecified"},
    Coordinate{"x3", "unspecified"}, Coordinate{"x4", "unspecified"}};
constexpr std::string_view source_hash =
    "029d55dd5b2d2ff1682bb42ffead7e2f5f0133df78864ae5ee583028200a88e5";
constexpr std::array operations{
    std::string_view{"csl::model::snapshot"}, std::string_view{"csl::model::LinearSystem::step"},
    std::string_view{"csl.geometry.generators.operations/AffineImage"},
    std::string_view{"csl.geometry.generators.operations/MinkowskiSum"},
    std::string_view{"csl.geometry.generators.v-conversion"}};
constexpr std::array generator_operations{
    std::string_view{"csl::model::snapshot"}, std::string_view{"csl::model::LinearSystem::step"},
    std::string_view{"csl::geometry::generators::affine_image"},
    std::string_view{"csl::geometry::generators::minkowski_sum"}};
constexpr std::array entries{
    CaseInfo{"bulaev-2016-slide33/illustrated-seven/1", "Three-state reachability: illustrated seven transitions",
        states, controls, 7, "integer stage; physical unit unspecified",
        {"Shorikov and Bulaev, 16 November 2016 presentation", source_hash,
         "slide 33: model; slides 35-41: sets at stages 1-7",
         "Numeric paper data; seven transitions follow the illustrated sequence. The printed update range would instead give eight."}, operations},
    CaseInfo{"bulaev-2016-slide33/literal-eight/1", "Three-state reachability: literal eight transitions",
        states, controls, 8, "integer stage; physical unit unspecified",
        {"Shorikov and Bulaev, 16 November 2016 presentation", source_hash,
         "slide 33: model and inclusive update range 0 through 7",
         "Numeric paper data; eight transitions interpret the printed update range literally. Figures show only stages 1-7."}, operations},
    CaseInfo{"archival-2017-4d-scalar-reachability/1", "Four-state scalar-input reachability: fifteen transitions",
        four_states, controls, 15, "integer stage; physical unit unspecified",
        {"Bulaev, Goranov and Kalyov: Constructing optimal programmed control for complex mechanical objects",
         "565ae84cf2c2661df47ce98a7a3d6c2ffa5cc9f220bf81a54f3b8a64c73a1c2a",
         "UralENIN 2017 author DOC; locally rendered page 11, comparison table page 12",
         "Forward comparison case only; initial bounds do not constrain later states. Fifteen transitions follow the printed range 0-14 and table stages 1-15. Decimal coefficients are transcribed to binary64."}, generator_operations}
};
constexpr std::array slide50_entries{
    CaseInfo{"bulaev-2016-slide50/authored-box/illustrated-five/1", "Slide 50: authored initial box, five transitions",
        states, two_controls, 5, "integer stage; physical unit unspecified",
        {"Shorikov and Bulaev, 16 November 2016 presentation", source_hash,
         "slide 50: A, B and U; slides 51-57: initial vertex count and illustrated stages",
         "Printed dynamics and independent input bounds; separately authored X0 box with radii (0.5,1,1). The original 78 initial vertices are unavailable. Five transitions follow the figures; this is not a reproduction of their initial set."}, operations},
    CaseInfo{"bulaev-2016-slide50/authored-box/literal-six/1", "Slide 50: authored initial box, six transitions",
        states, two_controls, 6, "integer stage; physical unit unspecified",
        {"Shorikov and Bulaev, 16 November 2016 presentation", source_hash,
         "slide 50: A, B, U and inclusive update range 0 through 5",
         "Printed dynamics and independent input bounds; separately authored X0 box with radii (0.5,1,1). The original 78 initial vertices are unavailable. Six transitions interpret the printed range literally; this is not a reproduction of their initial set."}, operations}
};
}

std::span<const CaseInfo> discrete_reachability_cases() {
    static const auto all = [] {
        std::vector<CaseInfo> result(entries.begin(), entries.end());
        const auto flexible = flexible_pitch_cases();
        result.insert(result.end(), flexible.begin(), flexible.end());
        result.insert(result.end(), slide50_entries.begin(), slide50_entries.end());
        const auto spatial = spatial_flight_cases();
        result.insert(result.end(), spatial.begin(), spatial.end());
        return result;
    }();
    return all;
}

std::variant<DiscreteReachabilityCase, Diagnostics, OperationStopped>
make_discrete_reachability_case(std::string_view id) {
    for (const auto& flexible : flexible_pitch_cases()) {
        if (flexible.id != id) continue;
        auto result = make_flexible_pitch_case(id);
        if (const auto* error = std::get_if<Diagnostics>(&result)) return *error;
        return std::move(std::get<FlexiblePitchCase>(result).reachability);
    }
    for (const auto& spatial : spatial_flight_cases()) {
        if (spatial.id != id) continue;
        auto result = make_spatial_flight_case(id);
        if (const auto* error = std::get_if<Diagnostics>(&result)) return *error;
        if (const auto* stopped = std::get_if<OperationStopped>(&result)) return *stopped;
        return std::move(std::get<SpatialFlightCase>(result).reachability);
    }
    const auto cases = discrete_reachability_cases();
    const auto entry = std::find_if(cases.begin(), cases.end(),
        [id](const CaseInfo& candidate) { return candidate.id == id; });
    if (entry == cases.end())
        return Diagnostics{{DiagnosticCode::invalid_input, "model.catalogue.id", "Unknown native discrete reachability case: " + std::string(id)}};

    const std::string prefix(entry->id);
    const bool archival_four_state = entry->id == "archival-2017-4d-scalar-reachability/1";
    const bool slide50 = entry->id.starts_with("bulaev-2016-slide50/");
    const auto control_count = entry->controls.size();
    const Vector radii = archival_four_state ? Vector{0.052, 5, 0.018, 1} : Vector{0.5, 1, 1};
    const auto dimension = radii.size();
    Matrix initial_map{dimension, dimension, Vector(dimension * dimension, 0)};
    std::vector<sets::FactorId> initial_factors;
    std::vector<std::string> labels;
    for (std::size_t j = 0; j < dimension; ++j) {
        initial_map.values[j * dimension + j] = radii[j];
        labels.emplace_back(entry->states[j].name);
        initial_factors.push_back({prefix + "/initial/" + labels.back()});
    }
    auto initial = sets::make_generator_set({{prefix + "/initial"}, Vector(dimension, 0),
        std::move(initial_map), std::move(initial_factors), {0, dimension, {}}, {}, std::move(labels)});
    if (const auto* error = std::get_if<Diagnostics>(&initial)) return *error;
    std::vector<sets::GeneratorSet> inputs;
    inputs.reserve(entry->transitions);
    for (std::size_t k = 0; k < entry->transitions; ++k) {
        const auto stage = prefix + "/control/" + std::to_string(k);
        Matrix generators{control_count, control_count, Vector(control_count * control_count, 0)};
        std::vector<sets::FactorId> factors;
        std::vector<std::string> control_labels;
        for (std::size_t j = 0; j < control_count; ++j) {
            generators.values[j * control_count + j] = slide50 ? 1.0 : (archival_four_state ? 0.14 : 2.0);
            control_labels.emplace_back(entry->controls[j].name);
            factors.push_back({stage + "/" + control_labels.back()});
        }
        auto input = sets::make_generator_set({{stage}, Vector(control_count, (archival_four_state || slide50) ? 0.0 : -1.0),
            std::move(generators), std::move(factors), {0, control_count, {}}, {}, std::move(control_labels)});
        if (const auto* error = std::get_if<Diagnostics>(&input)) return *error;
        inputs.push_back(std::get<sets::GeneratorSet>(std::move(input)));
    }
    Vector times(entry->transitions + 1);
    std::iota(times.begin(), times.end(), 0.0);
    const auto coefficients = archival_four_state
        ? LinearStage{{4, 4, {1, 0, 0.03, 0, 0.014, 1, 0.0001, 0.03,
              0.114, 0, 1, -0.0002, 0.915, 0, 0.014, 1}},
              {4, 1, {-0.0024, 0.0051, -0.157, 0.339}}, {4, 0, {}}, Vector(4, 0)}
        : slide50 ? LinearStage{{3, 3, {0.1, -0.1, 0.8, -1.8, 0, 0.12, 0, 0.64, 0.35}},
              {3, 2, {0, 0, 0.2, 0, 0, 1}}, {3, 0, {}}, Vector(3, 0)}
        : LinearStage{{3, 3, {1, 0, 0, 0, 1, 0, -3, -4, 0}},
              {3, 1, {3, 2, 0}}, {3, 0, {}}, Vector(3, 0)};
    SystemModel model{{{dimension, control_count, 0}, TimeDomain::discrete, coefficients}, {}};
    return DiscreteReachabilityCase{*entry, std::move(model), std::move(times),
        std::get<sets::GeneratorSet>(std::move(initial)), std::move(inputs)};
}

} // namespace csl::model::catalogue
