#include <csl/synthesis/hybrid_admission.hpp>

#include <iostream>
#include <memory>
#include <stdexcept>
#include <utility>
#include <variant>

int main() {
    using namespace csl;
    using namespace csl::model;
    using namespace csl::synthesis;

    registry::Registry<registry::LPPort> admission_providers;
    registry::Registration<registry::LPPort> admission_registration{
        {{"installed-admission"},"1"},
        [](const LinearProgram&,const registry::Requirements&)->registry::Capability {
            return registry::Offer{};
        },
        [](const LinearProgram&){return std::unique_ptr<LPWorkspace>{};}, {},
        [](const registry::RequestEnvelope& envelope,const registry::Requirements&) {
            const auto status=envelope.operation=="hybrid.linear-optimization" &&
                envelope.maximum_columns<=8?registry::AdmissionStatus::supported:
                    registry::AdmissionStatus::unsupported;
            return registry::AdmissionDeclaration{status,{},true};
        }};
    if (admission_providers.add(std::move(admission_registration)))
        throw std::runtime_error("Installed provider registration with admission declaration failed");
    auto prepared_admission=registry::prepare_provider(registry::select_provider(
        admission_providers,{{"installed-admission"},{}}));
    const auto* admission_provider=std::get_if<registry::PreparedProvider<registry::LPPort>>(
        &prepared_admission);
    if (admission_provider==nullptr || admission_provider->declare_support(
            {"hybrid.linear-optimization",4,8,32,"linear"}).status!=registry::AdmissionStatus::supported)
        throw std::runtime_error("Installed prepared provider did not expose conservative admission");

    registry::Registry<registry::ConvexPort> convex_providers;
    if (convex_providers.add({{{"installed-unused-convex"},"1"},
            [](const ConvexProgram&,const registry::Requirements&)->registry::Capability {
                return registry::Offer{};
            },
            [](const ConvexProgram&){return std::unique_ptr<ConvexWorkspace>{};}}))
        throw std::runtime_error("Installed unused convex provider registration failed");
    auto prepared_convex=registry::prepare_provider(registry::select_provider(
        convex_providers,{{"installed-unused-convex"},{}}));
    auto* convex_provider=std::get_if<registry::PreparedProvider<registry::ConvexPort>>(&prepared_convex);
    if (convex_provider==nullptr)
        throw std::runtime_error("Installed convex provider selection failed");

    auto inequalities = numeric::snapshot(Matrix{0, 4, {}});
    auto bounds = numeric::snapshot_vector(Vector{});
    auto equalities = numeric::snapshot(Matrix{2, 4, {-1, 0, 1, 0, 0, -1, 0, 1}});
    auto rhs = numeric::snapshot_vector(Vector{0, 0});
    if (!std::holds_alternative<numeric::MatrixView>(inequalities) ||
        !std::holds_alternative<numeric::VectorView>(bounds) ||
        !std::holds_alternative<numeric::MatrixView>(equalities) ||
        !std::holds_alternative<numeric::VectorView>(rhs))
        throw std::runtime_error("Could not store the exact 2D reset relation");
    auto reset = sets::make_h({{"installed-identity-reset"}, 4, {}},
        {std::get<numeric::MatrixView>(inequalities), std::get<numeric::VectorView>(bounds),
         std::get<numeric::MatrixView>(equalities), std::get<numeric::VectorView>(rhs)});
    if (!std::holds_alternative<sets::SetData>(reset))
        throw std::runtime_error("Could not construct the exact 2D reset relation");

    HybridMode source{{"source"}, 2, 1, {"x", "y"}, {"u"}};
    source.flow = LinearStage{Matrix{2, 2, {1, 0, 0, 1}}, Matrix{2, 1, {1, 0}},
        Matrix{2, 0, {}}, Vector{0, 0}};
    source.control_sets = {Singleton{{1}}};
    source.invariants = {UniversalSet{2}, UniversalSet{2}};
    HybridMode target{{"target"}, 2, 0, {"x", "y"}, {}};
    target.flow = LinearStage{Matrix{2, 2, {1, 0, 0, 1}}, Matrix{2, 0, {}},
        Matrix{2, 0, {}}, Vector{0, 0}};
    target.control_sets = {UniversalSet{0}};
    target.invariants = {UniversalSet{2}, UniversalSet{2}};
    const HybridSystem system{1, {source, target},
        {{{"switch"}, {"source"}, {"target"}, {UniversalSet{2}},
          {std::get<sets::SetData>(reset).as_handle()}}}};
    const HybridRequest request{{{"source"}, {-1, 0}}, {{"target"}},
        {{{"target"}, LinearTerminal{{1, 0}, 0}, "x", "m"}}};
    const HybridPath path{{{"source"}, {"target"}}, {{"switch"}}};
    JointHDirectTrajectoryAdapter trajectory;
    HybridExecutionSelection selection;
    selection.trajectory=std::make_shared<JointHDirectTrajectoryAdapter>();
    selection.lp=*admission_provider;
    selection.convex=*convex_provider;
    auto request_admission=admit_hybrid_request(system,request,selection,
        {1,4},{32,128,4096},{},{});
    auto* admission_token=std::get_if<HybridAdmissionToken>(&request_admission);
    if(admission_token==nullptr||!admission_token->report().admitted||
       admission_token->report().paths.size()!=1||admission_token->report().paths.front()!=path)
        throw std::runtime_error("Installed request-wide admission did not retain the complete path inventory");
    auto refined=refine_hybrid_request(std::move(*admission_token),{"installed-refinement"},{});
    const auto* prepared_request=std::get_if<HybridPreparedExecution>(&refined);
    if(prepared_request==nullptr||!prepared_request->report().admitted||
       prepared_request->report().paths.size()!=1)
        throw std::runtime_error("Installed transactional hybrid refinement did not prepare the path request");
    HybridExecutionSelection reachability_selection;
    reachability_selection.reachability=std::make_shared<JointHReachabilityAdapter>();
    auto reachability_admission=admit_hybrid_request(system,request,reachability_selection,
        {1,4},{32,128,4096},{},{});
    auto* reachability_token=std::get_if<HybridAdmissionToken>(&reachability_admission);
    if(reachability_token==nullptr)
        throw std::runtime_error("Installed exact reachability request was not admitted");
    auto reachability_refinement=refine_hybrid_request(std::move(*reachability_token),{},{});
    auto* prepared_reachability=std::get_if<HybridPreparedExecution>(&reachability_refinement);
    if(prepared_reachability==nullptr)
        throw std::runtime_error("Installed exact reachability refinement failed");
    const auto reachability_run=execute_hybrid_request(std::move(*prepared_reachability),{});
    if(!reachability_run.branches.empty()||reachability_run.reachability.size()!=1)
        throw std::runtime_error("Installed coordinated execution did not retain exact reachability");
    const auto admitted_portfolio=build_hybrid_portfolio_programs(trajectory,system,request,
        {"installed-admitted-hybrid"},{1,4},{32,128,4096},*admission_provider,*convex_provider);
    const auto* admitted=std::get_if<std::vector<HybridPathProgram>>(&admitted_portfolio);
    if (admitted==nullptr || admitted->size()!=1 || admitted->front().path!=path)
        throw std::runtime_error("Installed provider-aware hybrid admission did not build its admitted path");

    const auto result = build_hybrid_path_program(system, request, path,
        {"installed-hybrid-2d"}, {32, 128, 4096});
    const auto* program = std::get_if<HybridPathProgram>(&result);
    if (program == nullptr || program->path != path)
        throw std::runtime_error("Installed hybrid path program did not preserve the requested 2D branch");

    const auto relation = program->joint_relation.representation();
    const auto* h = std::get_if<sets::HRepresentation>(&relation);
    const Vector literal_joint_state{-1, 0, 1, 0, 0, 0, 0};
    if (h == nullptr || h->inequalities.rows() != 0 || h->equalities.rows() != literal_joint_state.size())
        throw std::runtime_error("Installed hybrid path program returned a different exact 2D relation shape");
    for (std::size_t row = 0; row < h->equalities.rows(); ++row) {
        double value = 0;
        for (std::size_t column = 0; column < h->equalities.cols(); ++column)
            value += h->equalities(row, column) * literal_joint_state[column];
        if (value != h->equality_values[row])
            throw std::runtime_error("Installed hybrid path program rejected the literal 2D trajectory");
    }

    std::cout << "Installed hybrid path program client: exact 2D branch program passed\n";
    return 0;
}
