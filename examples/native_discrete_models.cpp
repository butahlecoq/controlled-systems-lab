#include <csl/model/discrete_catalogue.hpp>
#include <csl/model/linear_system.hpp>

#include <cmath>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <locale>
#include <set>
#include <stdexcept>
#include <string>

namespace {
template <class T, class... Errors> T take(std::variant<T, Errors...> result) {
    if (auto *value = std::get_if<T>(&result))
        return std::move(*value);
    throw std::runtime_error("The native model operation did not return a value");
}

void matrix(std::ostream &out, std::string_view id, std::string_view kind,
            const csl::Matrix &values) {
    for (std::size_t row = 0; row < values.rows; ++row)
        for (std::size_t column = 0; column < values.cols; ++column)
            out << id << ',' << kind << ',' << row << ',' << column << ','
                << values.values[row * values.cols + column] << '\n';
}

void vector(std::ostream &out, std::string_view id, std::string_view kind,
            const csl::Vector &values) {
    for (std::size_t row = 0; row < values.size(); ++row)
        out << id << ',' << kind << ',' << row << ",0," << values[row] << '\n';
}
} // namespace

int main(int argc, char **argv) try {
    using namespace csl;
    using namespace csl::model::catalogue;
    if (argc > 2)
        throw std::runtime_error("Usage: native_discrete_models [new-output-directory]");
    std::ofstream output;
    if (argc == 2) {
        const std::filesystem::path directory(argv[1]);
        if (!std::filesystem::create_directory(directory))
            throw std::runtime_error("Output directory must be new");
        output.open(directory / "models.csv");
        if (!output)
            throw std::runtime_error("Cannot create model records");
        output.imbue(std::locale::classic());
        output << std::setprecision(std::numeric_limits<double>::max_digits10)
               << "model,kind,row,column,value\n";
    }
    std::size_t models = 0, coordinates = 0;
    std::set<std::string> ids;
    for (const auto &info : discrete_models()) {
        if (!ids.emplace(info.id).second)
            throw std::runtime_error("Repeated native model identity");
        const auto data = take<DiscreteModelData>(make_discrete_model(info.id));
        const auto system = take<model::LinearSystem>(
            model::snapshot(data.system_model(), Vector{0, data.time_step.value}));
        const auto next =
            take<Vector>(system.step({0}, data.initial_state, Vector(data.controls.size(), 0),
                                     Vector(data.external.size(), 0)));
        for (const auto value : next)
            if (!std::isfinite(value))
                throw std::runtime_error("Nonfinite native state");
        ++models;
        coordinates += next.size();
        if (output.is_open()) {
            matrix(output, info.id, "A", data.coefficients.A);
            matrix(output, info.id, "B", data.coefficients.B);
            matrix(output, info.id, "G", data.coefficients.E);
            vector(output, info.id, "x0", data.initial_state);
            if (data.nominal_external)
                vector(output, info.id, "nominal_w", *data.nominal_external);
            vector(output, info.id, "zero_input_first_step", next);
        }
    }
    if (output.is_open()) {
        output.close();
        if (!output)
            throw std::runtime_error("Writing native model records failed");
    }
    std::cout
        << "Native discrete model data: " << models << " models; " << coordinates
        << " state coordinates stepped through public APIs\n"
        << "Source-qualified model data only; no control task or empirical calibration claim.\n";
} catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return 1;
}
