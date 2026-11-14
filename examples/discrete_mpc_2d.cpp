#include <csl/adapters/convex/highs.hpp>
#include <csl/controllers/discrete_mpc.hpp>
#include <csl/registry/registry.hpp>

#include <cmath>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string>
#include <string_view>
#include <variant>

namespace {
using namespace csl;
using namespace csl::controllers;
using namespace csl::optimization;
using namespace csl::registry;

template <class T, class... E> T take(std::variant<T, E...> value) {
    if (auto *result = std::get_if<T>(&value))
        return std::move(*result);
    throw std::runtime_error("Native discrete MPC example operation failed");
}

NominalMpcTask make_task(bool disturbance_replayed) {
    const auto model = take<model::catalogue::DiscreteModelData>(
        model::catalogue::make_discrete_model("catalogue-2026/model-7/1"));
    constexpr std::size_t horizon = 8;
    const auto nx = model.coefficients.A.rows;
    const auto nu = model.coefficients.B.cols;
    const auto nw = model.coefficients.E.cols;

    Matrix q{nx, nx, Vector(nx * nx, 0.0)};
    q.values[0] = 2.0;
    q.values[nx + 1] = 1.0;
    Matrix r{nu, nu, Vector(nu * nu, 0.0)};
    r.values[0] = 0.5;
    Matrix q_terminal{nx, nx, Vector(nx * nx, 0.0)};
    q_terminal.values[0] = 4.0;
    q_terminal.values[nx + 1] = 2.0;

    AuthoredTaskChoices choices;
    choices.problem_id = {"example.discrete-mpc-2d"};
    choices.program_id = {"example.discrete-mpc-2d.nominal-qp"};
    choices.profile_id = "catalogue-model-7-source-bounds-v1";
    choices.objective_id = "authored-zero-reference-quadratic-v1";
    choices.horizon_id = "authored-fixed-eight-stage-v1";
    choices.final_stage = horizon;
    for (std::size_t stage = 0; stage < horizon; ++stage)
        choices.running_costs.push_back(
            {q, Matrix{nx, nu, Vector(nx * nu, 0.0)}, r, Vector(nx, 0.0), Vector(nu, 0.0), 0.0});
    choices.terminal_cost = {q_terminal, Vector(nx, 0.0), 0.0};
    choices.forecast_external.assign(horizon, Vector(nw, 0.0));
    choices.forecast_id = "declared-zero-nominal-forecast-v1";
    choices.replay_external.assign(horizon, Vector(nw, 0.0));
    if (disturbance_replayed) {
        for (auto &external : choices.replay_external) {
            external[0] = -3.0;
            external[1] = 4.0;
        }
    }
    choices.replay_id = disturbance_replayed ? "declared-constant-disturbance-replay-v1"
                                             : "forecast-matched-replay-v1";

    auto admission = make_source_task_profile(model.info.id, choices);
    return take<NominalMpcTask>(std::move(admission));
}

MpcEpisodeEvidence run(const NominalMpcTask &task, EpisodePolicy policy,
                       const ConvexProgram &capability_probe,
                       const Registration<ConvexPort> &registration) {
    Requirements requirements;
    requirements.output.representation = {"csl.program-result.v1"};
    const auto capability = registration.capabilities(capability_probe, requirements);
    const auto *offer = std::get_if<Offer>(&capability);
    if (!offer || offer->output.assurance != Assurance::numerical ||
        offer->output.representation.value != "csl.program-result.v1")
        throw std::runtime_error("HiGHS does not advertise the required numerical QP capability");
    auto workspace = registration.factory(capability_probe);
    if (!workspace)
        throw std::runtime_error("HiGHS returned no ConvexWorkspace");
    const ExecutionContext context{
        std::make_shared<const ResourcePolicy>(ResourcePolicy{1, 1, 1, {}}),
        {},
        {},
        {1e-8, 1e-8},
        "discrete-mpc-2d"};
    auto evidence = execute_nominal_episode(task, policy, *workspace, context);
    if (evidence.stop != EpisodeStop::completed || !evidence.realized_objective ||
        evidence.realized_states.size() != task.final_stage + 1 ||
        evidence.applied_controls.size() != task.final_stage)
        throw std::runtime_error("Native episode did not complete with a realized objective");
    return evidence;
}

bool close(double left, double right) { return std::abs(left - right) <= 1e-7; }

void require_matching(const MpcEpisodeEvidence &left, const MpcEpisodeEvidence &right) {
    if (left.realized_states.size() != right.realized_states.size() ||
        left.applied_controls.size() != right.applied_controls.size())
        throw std::runtime_error("Matched deterministic episodes have different lengths");
    for (std::size_t stage = 0; stage < left.realized_states.size(); ++stage)
        for (std::size_t coordinate = 0; coordinate < left.realized_states[stage].size();
             ++coordinate)
            if (!close(left.realized_states[stage][coordinate],
                       right.realized_states[stage][coordinate]))
                throw std::runtime_error("Matched open-loop and MPC states differ");
    for (std::size_t stage = 0; stage < left.applied_controls.size(); ++stage)
        for (std::size_t coordinate = 0; coordinate < left.applied_controls[stage].size();
             ++coordinate)
            if (!close(left.applied_controls[stage][coordinate],
                       right.applied_controls[stage][coordinate]))
                throw std::runtime_error("Matched open-loop and MPC controls differ");
}

void write_rows(std::ofstream &output, std::string_view scenario, std::string_view policy,
                const MpcEpisodeEvidence &episode) {
    for (std::size_t stage = 0; stage < episode.realized_states.size(); ++stage) {
        output << scenario << ',' << policy << ',' << stage << ",state,";
        for (std::size_t coordinate = 0; coordinate < episode.realized_states[stage].size();
             ++coordinate) {
            if (coordinate != 0)
                output << ';';
            output << episode.realized_states[stage][coordinate];
        }
        output << ",\n";
    }
    for (std::size_t stage = 0; stage < episode.applied_controls.size(); ++stage) {
        output << scenario << ',' << policy << ',' << stage << ",control,,";
        for (std::size_t coordinate = 0; coordinate < episode.applied_controls[stage].size();
             ++coordinate) {
            if (coordinate != 0)
                output << ';';
            output << episode.applied_controls[stage][coordinate];
        }
        output << '\n';
    }
}
} // namespace

int main(int argc, char **argv) try {
    if (argc != 2)
        throw std::runtime_error("Usage: discrete_mpc_2d NEW_OUTPUT_DIRECTORY");
    const std::filesystem::path output_directory(argv[1]);
    if (!std::filesystem::create_directory(output_directory))
        throw std::runtime_error("Output directory must be new");
    const auto registration =
        take<Registration<ConvexPort>>(adapters::convex::make_highs_registration());

    const auto matched_task = make_task(false);
    const auto matched_probe = std::get<ConvexProgram>(
        compile_mpc_decision(matched_task, StageIndex{0}, matched_task.initial.point));
    const auto open_loop =
        run(matched_task, EpisodePolicy::nominal_open_loop, matched_probe, registration);
    const auto matched_mpc =
        run(matched_task, EpisodePolicy::observed_state_mpc, matched_probe, registration);
    require_matching(open_loop, matched_mpc);

    const auto replay_task = make_task(true);
    const auto replay_probe = std::get<ConvexProgram>(
        compile_mpc_decision(replay_task, StageIndex{0}, replay_task.initial.point));
    const auto open_loop_replay =
        run(replay_task, EpisodePolicy::nominal_open_loop, replay_probe, registration);
    const auto observed_mpc_replay =
        run(replay_task, EpisodePolicy::observed_state_mpc, replay_probe, registration);
    std::optional<std::size_t> first_divergence;
    for (std::size_t stage = 1; stage < replay_task.final_stage; ++stage)
        if (!first_divergence && !close(open_loop_replay.applied_controls[stage][0],
                                        observed_mpc_replay.applied_controls[stage][0]))
            first_divergence = stage;
    if (!first_divergence)
        throw std::runtime_error("Declared replay disturbance did not change a later MPC action");

    std::ofstream csv(output_directory / "episode.csv");
    if (!csv)
        throw std::runtime_error("Could not create episode.csv");
    csv << std::setprecision(std::numeric_limits<double>::max_digits10)
        << "scenario,policy,stage,kind,state,control\n";
    write_rows(csv, "forecast-matched", "open-loop", open_loop);
    write_rows(csv, "forecast-matched", "observed-mpc", matched_mpc);
    write_rows(csv, "forecast-zero-replay-disturbed", "open-loop", open_loop_replay);
    write_rows(csv, "forecast-zero-replay-disturbed", "observed-mpc", observed_mpc_replay);

    std::cout
        << std::fixed << std::setprecision(6)
        << "Matched open-loop/MPC episodes agree; declared replay disturbance changes a later "
           "observed-state MPC action. first_action="
        << open_loop.applied_controls.front().front()
        << " first_divergence_stage=" << *first_divergence
        << " open_loop_action=" << open_loop_replay.applied_controls[*first_divergence].front()
        << " mpc_action=" << observed_mpc_replay.applied_controls[*first_divergence].front()
        << " provider=" << registration.identity.id.value << '@' << registration.identity.version
        << '\n';
    return 0;
} catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return 1;
}
