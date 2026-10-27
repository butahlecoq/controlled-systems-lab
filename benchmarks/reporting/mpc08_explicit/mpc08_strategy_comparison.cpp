#include <csl/adapters/convex/highs.hpp>
#include <csl/adapters/lp/highs.hpp>
#include <csl/adapters/polyhedral/qhull.hpp>
#include <csl/geometry/affine_sum.hpp>
#include <csl/input/scenario_loader.hpp>
#include <csl/optimization/convex_backend.hpp>
#include <csl/registry/registry.hpp>
#include <csl/synthesis/strategy_a/strategy.hpp>
#include <csl/synthesis/strategy_b/direct_joint.hpp>

#include <chrono>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <type_traits>
#include <vector>

using namespace csl;
using namespace csl::registry;

namespace {
using Clock = std::chrono::steady_clock;

template<class T, class... R>
T take(std::variant<T, R...> value, std::string_view name) {
    if (auto* result = std::get_if<T>(&value)) return std::move(*result);
    std::ostringstream message;
    message << name << " failed";
    std::visit([&](const auto& error) {
        using E = std::decay_t<decltype(error)>;
        if constexpr (std::is_same_v<E, Rejection>) {
            for (const auto& diagnostic : error.diagnostics)
                message << ": " << diagnostic.field << " " << diagnostic.explanation;
        } else if constexpr (std::is_same_v<E, Unsupported>) {
            for (const auto& diagnostic : error.diagnostics)
                message << ": " << diagnostic.field << " " << diagnostic.explanation;
        }
    }, value);
    throw std::runtime_error(message.str());
}

template<class Port>
PreparedProvider<Port> selected(Registration<Port> registration, std::string representation) {
    Registry<Port> registry;
    const Method method{registration.identity.id, registration.identity.version};
    if (registry.add(std::move(registration))) throw std::runtime_error("provider registration failed");
    Requirements requirements;
    requirements.output.representation = {std::move(representation)};
    if constexpr (std::is_same_v<Port, GeometryPort> || std::is_same_v<Port, ConversionPort>)
        requirements.output.relation = SetRelation::equivalent;
    return take(prepare_provider(select_provider(registry, method, requirements)), "provider selection");
}

struct Query {
    std::string id, p_exact, v_exact, u_exact, value_exact;
    double p{}, v{}, u{}, value{};
};

std::vector<Query> read_queries(const char* path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open exact reference queries");
    std::string line;
    if (!std::getline(input, line)) throw std::runtime_error("query CSV is empty");
    std::vector<Query> queries;
    while (std::getline(input, line)) {
        std::istringstream row(line);
        std::vector<std::string> fields;
        std::string field;
        while (std::getline(row, field, ',')) fields.push_back(field);
        if (fields.size() != 7) throw std::runtime_error("query CSV row must have seven fields");
        queries.push_back({fields[0], fields[1], fields[2], fields[3], fields[4],
                           std::stod(fields[5]), std::stod(fields[6]), 0.0, 0.0});
        const auto parse_rational = [](const std::string& text) {
            const auto slash = text.find('/');
            if (slash == std::string::npos) return std::stod(text);
            return std::stod(text.substr(0, slash)) / std::stod(text.substr(slash + 1));
        };
        queries.back().u = parse_rational(fields[3]);
        queries.back().value = parse_rational(fields[4]);
    }
    if (queries.empty()) throw std::runtime_error("no exact reference queries");
    return queries;
}

SetHandle input_box() {
    auto h = sets::make_h({{"mpc08-control-box"}, 1, {"u0"}},
        {take(numeric::snapshot(Matrix{2,1,{1,-1}}), "control matrix"),
         take(numeric::snapshot_vector(Vector{1,1}), "control bounds"),
         take(numeric::snapshot(Matrix{0,1,{}}), "control equalities"),
         take(numeric::snapshot_vector(Vector{}), "control equality values")});
    return take(std::move(h), "control set").as_handle();
}

SetHandle terminal_set() {
    auto h = sets::make_h({{"mpc08-invariant-terminal-set"}, 2, {}},
        {take(numeric::snapshot(Matrix{4,2,{1,1,-1,-1,1,2,-1,-2}}), "terminal matrix"),
         take(numeric::snapshot_vector(Vector{1,1,1,1}), "terminal bounds"),
         take(numeric::snapshot(Matrix{0,2,{}}), "terminal equalities"),
         take(numeric::snapshot_vector(Vector{}), "terminal equality values")});
    return take(std::move(h), "terminal set").as_handle();
}

problem::ResolvedProblem resolve(const Query& query) {
    const LinearStage flow{Matrix{2,2,{1,1,0,1}}, Matrix{2,1,{0,1}},
                            Matrix{2,0,{}}, Vector{0,0}};
    Problem source{{"mpc08-double-integrator-horizon-1"},
        std::make_shared<const SystemModel>(SystemModel{{{2,1,0}, TimeDomain::discrete, flow}, {}}),
        {0,1}, KnownInitial{{query.p,query.v}}, ContinuousDomain{{input_box()}},
        {UniversalSet{2}, terminal_set()}, {}, {}, InformationPattern::nominal_open_loop,
        QuadraticTerminal{Matrix{2,2,{2,0,0,2}}, Vector{0,0}, 0}};
    return take(problem::resolve(source,
        {problem::UncertaintyStructure::stage_product_uncoupled, {}, {}}), "problem resolution");
}

struct Providers {
    std::shared_ptr<StrategyRegistry> strategies;
    std::shared_ptr<Registry<GeometryPort>> projections, affines;
    std::shared_ptr<Registry<ConversionPort>> conversions;
    std::shared_ptr<Registry<LPPort>> lps;
    std::shared_ptr<Registry<ConvexPort>> convexes;
    ModuleId lp_id, convex_id, strategy_a_id, strategy_b_id;
};

std::string json_escape(std::string_view value) {
    std::string out;
    for (const unsigned char ch : value) {
        switch (ch) {
        case '"': out += "\\\""; break;
        case '\\': out += "\\\\"; break;
        case '\n': out += "\\n"; break;
        case '\r': out += "\\r"; break;
        case '\t': out += "\\t"; break;
        default: if (ch >= 0x20) out += static_cast<char>(ch); break;
        }
    }
    return out;
}

std::string stop_summary(const SynthesisStopEvidence& stop) {
    std::string summary;
    const auto append = [&](const Diagnostics& diagnostics) {
        for (const auto& diagnostic : diagnostics) {
            if (!summary.empty()) summary += "; ";
            summary += diagnostic.field + ": " + diagnostic.explanation;
        }
    };
    std::visit([&](const auto& evidence) {
        using T = std::decay_t<decltype(evidence)>;
        if constexpr (std::is_same_v<T, ScopedOperationStopped>) summary = evidence.stop.diagnostics;
        else if constexpr (std::is_same_v<T, ScopedRequestRejection>) append(evidence.diagnostics);
        else if constexpr (std::is_same_v<T, ContractValidationFailure>) append(evidence.diagnostics);
    }, stop);
    return summary;
}

Providers make_providers() {
    auto lp = take(adapters::lp::make_highs_registration(), "HiGHS LP registration");
    auto convex = take(adapters::convex::make_highs_registration(), "HiGHS convex registration");
    const auto lp_id=lp.identity.id, convex_id=convex.identity.id;
    auto converter = take(adapters::polyhedral::make_qhull_registration(lp), "Qhull registration");
    auto projection = geometry::polyhedral::make_projection_registration();
    auto affine = geometry::make_affine_sum_registration({
        selected(geometry::make_lp_hull_reducer_registration(), ""),
        selected(lp, "csl.program-result.v1"),
        selected(converter, "csl.polyhedron.v")});

    Providers result;
    result.projections = std::make_shared<Registry<GeometryPort>>();
    result.affines = std::make_shared<Registry<GeometryPort>>();
    result.conversions = std::make_shared<Registry<ConversionPort>>();
    result.lps = std::make_shared<Registry<LPPort>>();
    result.convexes = std::make_shared<Registry<ConvexPort>>();
    const Method pm{projection.identity.id,{}}, am{affine.identity.id,{}},
        cm{converter.identity.id,{}}, lm{lp.identity.id,{}}, qm{convex.identity.id,{}};
    if (result.projections->add(projection) || result.affines->add(affine) ||
        result.conversions->add(converter) || result.lps->add(lp) || result.convexes->add(convex))
        throw std::runtime_error("provider registry failed");
    Requirements h, v, program;
    h.output.representation = {"csl.polyhedron.h"}; h.output.relation = SetRelation::equivalent;
    v.output.representation = {"csl.polyhedron.v"}; v.output.relation = SetRelation::equivalent;
    program.output.representation = {"csl.program-result.v1"};
    auto checked = take(check_providers(select_provider(*result.projections,pm,h),
        select_provider(*result.affines,am,v), select_provider(*result.conversions,cm,h),
        select_provider(*result.lps,lm,program), select_provider(*result.convexes,qm,program)), "Strategy A providers");
    auto a = synthesis::strategy_a::make_registration(std::move(checked));
    auto b = synthesis::strategy_b::make_registration(*result.lps, *result.convexes);
    const auto a_id = a.identity.id, b_id = b.identity.id;
    result.strategies = std::make_shared<StrategyRegistry>();
    if (result.strategies->add(std::move(a)) || result.strategies->add(std::move(b)))
        throw std::runtime_error("strategy registry failed");
    result.lp_id = lp_id; result.convex_id = convex_id;
    result.strategy_a_id = a_id; result.strategy_b_id = b_id;
    return result;
}

bool candidate_contains(const SynthesisResult& result, const Query& query,
                        std::string& labels, std::size_t& inequalities,
                        std::size_t& equalities) {
    if (!result.family) return false;
    const auto* candidate = std::get_if<CandidateFamily>(&result.family->outcome());
    if (!candidate || !candidate->relation.payload) return false;
    const sets::SetData* data = candidate->relation.payload->h_relation_for_recording();
    if (const auto* history = dynamic_cast<const synthesis::strategy_a::CandidateHistory*>(candidate->relation.payload.get()))
        data = &history->history.relation;
    if (!data) return false;
    const auto representation = data->representation();
    const auto* h = std::get_if<sets::HRepresentation>(&representation);
    if (!h) return false;
    inequalities = h->inequalities.rows(); equalities = h->equalities.rows();
    const auto metadata = data->metadata();
    for (std::size_t i=0; i<metadata->coordinate_labels.size(); ++i) {
        if (i) labels += ";";
        labels += metadata->coordinate_labels[i];
    }
    const Vector point{query.p,query.v,query.p+query.v,query.v+query.u,query.u};
    if (h->inequalities.cols() != point.size() || h->equalities.cols() != point.size()) return false;
    constexpr double tolerance = 2e-6;
    for (std::size_t r=0; r<h->inequalities.rows(); ++r) {
        double lhs=0; for (std::size_t c=0; c<point.size(); ++c) lhs += h->inequalities(r,c)*point[c];
        if (lhs > h->upper_bounds[r] + tolerance) return false;
    }
    for (std::size_t r=0; r<h->equalities.rows(); ++r) {
        double lhs=0; for (std::size_t c=0; c<point.size(); ++c) lhs += h->equalities(r,c)*point[c];
        if (std::abs(lhs-h->equality_values[r]) > tolerance) return false;
    }
    return true;
}

void run_one(Providers& providers, const Query& query, bool use_a,
             std::size_t repetition, bool warmup) {
    const auto started=Clock::now();
    std::string status="failed", error, labels;
    bool result_optimal=false, candidate_member=false;
    bool family_present=false;
    int termination_code=-1, outcome_code=-1;
    std::size_t rows=0, equalities=0;
    std::string strategy_id, stop_details;
    try {
        const auto resolved=resolve(query);
        FamilyRequest family;
        family.profile="nominal_open_loop";
        family.objective=resolved.identity(); family.target=FamilyTarget::candidate_relaxation;
        family.assurance=Assurance::numerical; family.representation={"csl.polyhedron.h"};
        StrategyConfiguration configuration;
        configuration.strategy=use_a?providers.strategy_a_id:providers.strategy_b_id;
        configuration.lp=providers.lp_id; configuration.convex=providers.convex_id;
        configuration.representation=family.representation;
        strategy_id=configuration.strategy.value;
        const StrategyRequest request{resolved,configuration,family,{},{}};
        Requirements output;
        output.output.representation=family.representation;
        output.output.family=family.target;
        const auto prepared=take(providers.strategies->prepare(request,output),"strategy preparation");
        auto workspace=prepared.create();
        if (!workspace) throw std::runtime_error("strategy workspace is null");
        ExecutionContext context; context.numerical=family.numerical;
        context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
        auto result=take(workspace->run(context),"strategy run");
        family_present=result.family.has_value();
        termination_code=static_cast<int>(result.termination);
        outcome_code=static_cast<int>(result.outcome.value);
        result_optimal=result.termination==Termination::completed && result.outcome.value==MathematicalOutcome::optimal;
        stop_details=stop_summary(result.stop);
        candidate_member=candidate_contains(result,query,labels,rows,equalities);
        const auto membership_status=candidate_member?"candidate_contains_analytic_unique_history":
            (result.family?"candidate_excludes_analytic_unique_history":"no_candidate_family");
        status=result.termination==Termination::completed?membership_status:
            "noncompleted_"+std::string(membership_status);
    } catch (const std::exception& exception) {
        error=exception.what();
    }
    const auto elapsed=std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-started).count();
    std::cout << "{\"schema\":\"csl.mpc08-explicit-candidate-observation/1\",\"query_id\":\""
        << query.id << "\",\"strategy\":\"" << json_escape(strategy_id) << "\",\"warmup\":"
        << (warmup?"true":"false") << ",\"repetition\":" << repetition
        << ",\"status\":\"" << status << "\",\"termination_optimal\":"
        << (result_optimal?"true":"false") << ",\"family_present\":" << (family_present?"true":"false")
        << ",\"termination_code\":" << termination_code << ",\"outcome_code\":" << outcome_code
        << ",\"candidate_contains_exact_reference_history\":"
        << (candidate_member?"true":"false") << ",\"action_and_value_match_exact_reference\":null"
        << ",\"expected_value_exact\":\"" << query.value_exact
        << "\",\"candidate_inequality_rows\":" << rows << ",\"candidate_equality_rows\":" << equalities
        << ",\"coordinate_labels\":\"" << json_escape(labels) << "\",\"elapsed_ns\":" << elapsed
        << ",\"stop_details\":\"" << json_escape(stop_details)
        << "\",\"error\":\"" << json_escape(error) << "\"}\n";
}

void run_online_qp(Providers& providers, const Query& query, std::size_t repetition, bool warmup) {
    const auto started=Clock::now();
    std::string status="online_qp_failed", error;
    bool optimal=false, matches_reference=false;
    int termination_code=-1, outcome_code=-1;
    double input_value=0, objective_at_primal=0;
    std::optional<double> objective_lower, objective_upper;
    try {
        const auto resolved=resolve(query);
        const double lower=std::max({-1.0,-1.0-query.p-2*query.v,(-1.0-query.p-3*query.v)/2});
        const double upper=std::min({1.0,1.0-query.p-2*query.v,(1.0-query.p-3*query.v)/2});
        if (lower>upper) throw std::runtime_error("query is outside the feasible initial domain");
        const auto program=optimization::make_convex_program({
            {resolved.identity(),{"mpc08-condensed-online-qp:"+query.id}},
            QuadraticTerminal{Matrix{1,1,{2.0}},Vector{2*query.v},
                (query.p+query.v)*(query.p+query.v)+query.v*query.v},
            SparseMatrix{0,1,{0},{},{}},{{lower,upper}},{},{}});
        if (const auto* failure=std::get_if<Diagnostics>(&program)) {
            std::ostringstream message; for (const auto& item:*failure) message<<item.field<<": "<<item.explanation<<"; ";
            throw std::runtime_error(message.str());
        }
        if (!std::holds_alternative<ConvexProgram>(program))
            throw std::runtime_error("online QP construction stopped");
        Requirements requirements; requirements.output.representation={"csl.program-result.v1"};
        const Method method{providers.convex_id,{}};
        auto provider=take(prepare_provider(select_provider(*providers.convexes,method,requirements)),"online QP provider selection");
        auto pipeline=take(provider.prepare(std::get<ConvexProgram>(program)),"online QP preparation");
        auto [workspace]=pipeline.create();
        if (!workspace) throw std::runtime_error("online QP workspace is null");
        ExecutionContext context; context.numerical={1e-8,1e-8};
        context.resources=std::make_shared<const ResourcePolicy>(ResourcePolicy{1,1,1,{}});
        auto solved=workspace->run(context);
        if (const auto* unsupported=std::get_if<Unsupported>(&solved)) {
            std::ostringstream message; for (const auto& item:unsupported->diagnostics)
                message<<item.field<<": "<<item.explanation<<"; ";
            throw std::runtime_error(message.str());
        }
        const auto& result=std::get<ProgramResult>(solved);
        termination_code=static_cast<int>(result.termination);
        outcome_code=static_cast<int>(result.outcome.value);
        if (result.objective.lower) objective_lower=result.objective.lower->value;
        if (result.objective.upper) objective_upper=result.objective.upper->value;
        optimal=result.termination==Termination::completed&&result.outcome.value==MathematicalOutcome::optimal&&
            result.primal.has_value()&&result.primal->size()==1;
        if (result.primal&&result.primal->size()==1) {
            input_value=result.primal->front();
            objective_at_primal=(query.p+query.v)*(query.p+query.v)+
                (query.v+input_value)*(query.v+input_value);
            const bool action_matches=std::abs(input_value-query.u)<=2e-6;
            const bool value_matches=std::abs(objective_at_primal-query.value)<=2e-6;
            matches_reference=optimal&&action_matches&&value_matches;
        }
        status=matches_reference?"online_qp_matches_exact_reference":"online_qp_result_mismatch";
    } catch (const std::exception& exception) { error=exception.what(); }
    const auto elapsed=std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-started).count();
    std::cout<<"{\"schema\":\"csl.mpc08-explicit-candidate-observation/1\",\"query_id\":\""
        <<query.id<<"\",\"strategy\":\"online-condensed-qp\",\"warmup\":"<<(warmup?"true":"false")
        <<",\"repetition\":"<<repetition<<",\"status\":\""<<status<<"\",\"termination_optimal\":"
        <<(optimal?"true":"false")<<",\"family_present\":false,\"termination_code\":"<<termination_code
        <<",\"outcome_code\":"<<outcome_code<<",\"candidate_contains_exact_reference_history\":"
        <<"false,\"action_and_value_match_exact_reference\":"<<(matches_reference?"true":"false")
        <<",\"input_value\":"<<std::setprecision(17)<<input_value
        <<",\"objective_at_primal\":"<<std::setprecision(17)<<objective_at_primal
        <<",\"objective_lower\":";
    if (objective_lower) std::cout<<std::setprecision(17)<<*objective_lower; else std::cout<<"null";
    std::cout<<",\"objective_upper\":";
    if (objective_upper) std::cout<<std::setprecision(17)<<*objective_upper; else std::cout<<"null";
    std::cout
        <<",\"expected_value_exact\":\""<<query.value_exact<<"\",\"candidate_inequality_rows\":0"
        <<",\"candidate_equality_rows\":0,\"coordinate_labels\":\"\",\"elapsed_ns\":"<<elapsed
        <<",\"stop_details\":\"\",\"error\":\""<<json_escape(error)<<"\"}\n";
}
}

int main(int argc,char** argv) try {
    if (argc!=2) { std::cerr << "Usage: csl_mpc08_explicit_compare <exact-queries.csv>\n"; return 2; }
    const auto queries=read_queries(argv[1]);
    auto providers=make_providers();
    constexpr std::size_t measured=5;
    for (const auto& query:queries) {
        for (int method=0; method<2; ++method) run_one(providers,query,method==0,0,true);
        run_online_qp(providers,query,0,true);
        for (std::size_t repetition=1; repetition<=measured; ++repetition) {
            if (repetition%3==1) {
                run_one(providers,query,true,repetition,false);
                run_one(providers,query,false,repetition,false);
                run_online_qp(providers,query,repetition,false);
            } else if (repetition%3==2) {
                run_online_qp(providers,query,repetition,false);
                run_one(providers,query,false,repetition,false);
                run_one(providers,query,true,repetition,false);
            } else {
                run_one(providers,query,false,repetition,false);
                run_online_qp(providers,query,repetition,false);
                run_one(providers,query,true,repetition,false);
            }
        }
    }
    return 0;
} catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 1;
}
