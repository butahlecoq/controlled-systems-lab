#include <csl/artifacts/plot_data.hpp>

int main() {
    csl::artifacts::PlotMetadata metadata;
    metadata.time_unit="s";
    csl::artifacts::PlotData plot;
    plot.state_axis.kind=csl::artifacts::PlotAxis::Kind::physical_time;
    plot.control_axis.kind=csl::artifacts::PlotAxis::Kind::physical_time;
    plot.control_hold=csl::artifacts::ControlHold::left;
    return metadata.time_unit && plot.control_hold==csl::artifacts::ControlHold::left ? 0 : 1;
}
