#pragma once

#include <csl/geometry/quickhull_2d.hpp>
#include <csl/model/catalogue.hpp>

#include <algorithm>
#include <array>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <limits>
#include <optional>
#include <sstream>
#include <stdexcept>

namespace native_catalogue_example {
using namespace csl;
using Cloud = std::vector<Vector>;
struct CapturedCase {
    model::catalogue::CaseInfo info;
    std::vector<Cloud> stages;
    std::array<std::pair<std::size_t, std::size_t>, 2> projection_axes{{{0, 1}, {0, 2}}};
    bool physical_coordinates{false};
};
inline geometry::QuickHull2D projected_hull(const Cloud &cloud) {
    auto result = geometry::quickhull_2d(cloud);
    if (auto *hull = std::get_if<geometry::QuickHull2D>(&result))
        return std::move(*hull);
    throw std::runtime_error("Native projection hull failed");
}

inline void write_svg(const std::filesystem::path &file, const std::vector<CapturedCase> &cases,
                      bool print, std::optional<std::pair<std::size_t, std::size_t>> panel = {}) {
    std::ofstream out(file);
    out.exceptions(std::ios::badbit | std::ios::failbit);
    out << std::setprecision(9);
    const char *background = print ? "#ffffff" : "#16161e";
    const char *foreground = print ? "#202124" : "#e0def4";
    std::size_t maximum_stage = 0;
    for (const auto &data : cases)
        maximum_stage = std::max(maximum_stage, data.stages.size() - 1);
    auto color = [&](std::size_t stage) {
        const std::array first = print ? std::array{104, 70, 140} : std::array{196, 167, 231};
        const std::array last = print ? std::array{167, 77, 38} : std::array{246, 193, 119};
        const double weight =
            maximum_stage ? static_cast<double>(stage) / static_cast<double>(maximum_stage) : 0;
        std::ostringstream text;
        text << '#' << std::hex << std::setfill('0');
        for (std::size_t i = 0; i < 3; ++i)
            text << std::setw(2) << static_cast<int>(first[i] + (last[i] - first[i]) * weight);
        return text.str();
    };
    const int canvas_width = panel ? 550 : 1100;
    const auto legend_columns = panel ? 5 : 9;
    const auto legend_rows = (maximum_stage + legend_columns) / legend_columns;
    const auto canvas_height =
        panel ? 460 + 27 * legend_rows : 390 * cases.size() + 133 + 27 * legend_rows;
    out << "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 " << canvas_width << ' '
        << canvas_height << "\" role=\"img\" aria-labelledby=\"title desc\">"
        << "<title id=\"title\">Native reachable sets, all stages</title>"
        << "<desc id=\"desc\">Full-state generator sets are computed before selecting the displayed coordinate planes. "
        << "Each row retains its declared horizon; no control objective is supplied.</desc>"
        << "<rect width=\"" << canvas_width << "\" height=\"" << canvas_height << "\" fill=\""
        << background << "\"/>"
        << "<g font-family=\"sans-serif\" fill=\"" << foreground << "\"><text x=\""
        << canvas_width / 2 << "\" y=\"31\" text-anchor=\"middle\" font-size=\"23"
        << "\">Native full-state reachability projections</text>";
    for (std::size_t row = 0; row < cases.size(); ++row) {
        const auto &data = cases[row];
        for (std::size_t column = 0; column < 2; ++column) {
            if (panel && *panel != std::pair{row, column})
                continue;
            const auto [horizontal, vertical] = data.projection_axes[column];
            double xmin = std::numeric_limits<double>::infinity(), xmax = -xmin, ymin = xmin,
                   ymax = -xmin;
            for (const auto &cloud : data.stages)
                for (const auto &p : cloud) {
                    xmin = std::min(xmin, p[horizontal]);
                    xmax = std::max(xmax, p[horizontal]);
                    ymin = std::min(ymin, p[vertical]);
                    ymax = std::max(ymax, p[vertical]);
                }
            const double dx = (xmax - xmin) * 0.06, dy = (ymax - ymin) * 0.06;
            xmin -= dx;
            xmax += dx;
            ymin -= dy;
            ymax += dy;
            const double left = static_cast<double>(panel ? 75 : 75 + 535 * column) +
                                (data.physical_coordinates ? 50 : 0);
            const double top = static_cast<double>(panel ? 72 : 88 + 390 * row);
            const double width = data.physical_coordinates ? 380 : 430, height = 285;
            auto x = [&](double value) { return left + width * (value - xmin) / (xmax - xmin); };
            auto y = [&](double value) { return top + height * (ymax - value) / (ymax - ymin); };
            auto label = [](double value) {
                std::ostringstream text;
                text << std::setprecision(3) << value;
                return text.str();
            };
            out << "<text x=\"" << left + width / 2 << "\" y=\"" << top - 13
                << "\" text-anchor=\"middle\" font-size=\"" << (panel ? 23 : 17) << "\">"
                << data.info.transitions << " transitions: x" << horizontal + 1 << "-x"
                << vertical + 1 << "</text>";
            for (int tick = 0; tick <= 4; ++tick) {
                const double xv = xmin + (xmax - xmin) * tick / 4,
                             yv = ymin + (ymax - ymin) * tick / 4;
                out << "<path d=\"M " << x(xv) << ' ' << top << " v " << height << " M " << left
                    << ' ' << y(yv) << " h " << width << "\" fill=\"none\" stroke=\"" << foreground
                    << "\" opacity=\"0.12\"/>"
                    << "<text x=\"" << x(xv) << "\" y=\"" << top + height + 22
                    << "\" text-anchor=\"middle\" font-size=\""
                    << (panel ? (data.physical_coordinates ? 20 : 23) : 13) << "\">" << label(xv)
                    << "</text>"
                    << "<text x=\"" << left - 8 << "\" y=\"" << y(yv) + 4
                    << "\" text-anchor=\"end\" font-size=\""
                    << (panel ? (data.physical_coordinates ? 20 : 23) : 13) << "\">" << label(yv)
                    << "</text>";
            }
            for (std::size_t k = 0; k < data.stages.size(); ++k) {
                Cloud projection;
                for (const auto &p : data.stages[k])
                    projection.push_back({p[horizontal], p[vertical]});
                const auto hull = projected_hull(projection);
                out << "<polygon points=\"";
                for (const auto index : hull.vertex_indices)
                    out << x(projection[index][0]) << ',' << y(projection[index][1]) << ' ';
                out << "\" fill=\"" << color(k) << "\" fill-opacity=\"0.06\" stroke=\"" << color(k)
                    << "\" stroke-width=\"1.8\"/>";
            }
            out << "<rect x=\"" << left << "\" y=\"" << top << "\" width=\"" << width
                << "\" height=\"" << height << "\" fill=\"none\" stroke=\"" << foreground << "\"/>"
                << "<text x=\"" << left + width / 2 << "\" y=\"" << top + height + 45
                << "\" text-anchor=\"middle\" font-size=\""
                << (panel ? (data.physical_coordinates ? 17 : 23) : 15) << "\">"
                << (data.physical_coordinates
                        ? std::string(data.info.states[horizontal].name) + " (" +
                              std::string(data.info.states[horizontal].unit) + ")"
                        : "x" + std::to_string(horizontal + 1) + " (source unit unspecified)")
                << "</text>"
                << "<text transform=\"translate(" << left - (data.physical_coordinates ? 105 : 55)
                << ',' << top + height / 2 << ") rotate(-90)\" text-anchor=\"middle\" font-size=\""
                << (panel ? (data.physical_coordinates ? 17 : 23) : 15) << "\">"
                << (data.physical_coordinates ? "" : "x")
                << (data.physical_coordinates
                        ? std::string(data.info.states[vertical].name) + " (" +
                              std::string(data.info.states[vertical].unit) + ")"
                        : std::to_string(vertical + 1) + " (unit unspecified)")
                << "</text>";
        }
    }
    const auto legend_size = panel ? cases[panel->first].stages.size() : maximum_stage + 1;
    for (std::size_t k = 0; k < legend_size; ++k) {
        const auto left = panel ? 40 + 100 * (k % 5) : 125 + 100 * (k % 9);
        const auto top = panel ? 427 + 27 * (k / 5) : 390 * cases.size() + 90 + 27 * (k / 9);
        out << "<path d=\"M " << left << ' ' << top << " h 25\" stroke=\"" << color(k)
            << "\" stroke-width=\"3\"/><text x=\"" << left + 32 << "\" y=\"" << top + 5
            << "\" font-size=\"" << (panel ? 23 : 15) << "\">k=" << k << "</text>";
    }
    out << "<text x=\"" << canvas_width / 2 << "\" y=\"" << canvas_height - 12
        << "\" text-anchor=\"middle\" font-size=\"" << (panel ? 12 : 14)
        << "\">Full-state propagation before projection; numerical affine model.</text></g></svg>\n";
}

} // namespace native_catalogue_example
