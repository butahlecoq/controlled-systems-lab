#include <csl/geometry/approximation.hpp>
#include <csl/geometry/zonotope_reduction.hpp>
#include <csl/registry/provider.hpp>
#include <csl/sets/generator_sets.hpp>

#include <array>
#include <chrono>
#include <cstdlib>
#include <functional>
#include <iostream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <variant>
#include <vector>

using namespace csl;
using namespace csl::geometry::approximation;

namespace {
template<class T,class... Alternatives> T take(std::variant<T,Alternatives...> value) {
    if(!std::holds_alternative<T>(value))throw std::runtime_error("Invalid APP-03 fixture");
    return std::get<T>(std::move(value));
}
sets::GeneratorSet source(std::string_view name,Vector center,Matrix generators,
                          std::vector<sets::FactorId> factors,Matrix equalities={},
                          Vector equality_values={}) {
    if(equalities.rows==0)equalities.cols=factors.size();
    return take(sets::make_generator_set({{std::string(name)},std::move(center),
        std::move(generators),std::move(factors),std::move(equalities),
        std::move(equality_values),
        {"x","y"}}));
}
struct Case {
    std::string_view name;
    std::string_view basis;
    int output_generators;
    std::function<bool(std::chrono::nanoseconds&)> call;
};
bool batch(const Case& item,std::string_view phase,int repetition,int calls) {
    std::chrono::nanoseconds elapsed{};
    for(int index=0;index<calls;++index)
        if(!item.call(elapsed))return false;
    std::cout<<phase<<','<<item.name<<','<<repetition<<','<<calls
             <<",completed,true,"<<elapsed.count()<<','<<item.basis<<','
             <<item.output_generators<<'\n';
    return true;
}
}

int main(int argc,char** argv) {
    if(argc!=2 || (std::string_view(argv[1])!="smoke" &&
                   std::string_view(argv[1])!="measure"))return EXIT_FAILURE;
    registry::Registry<registry::ApproximationPort> covers;
    if(covers.add(make_axis_cover_registration({"app03-cover"})))return EXIT_FAILURE;
    const registry::Method cover_method{{"csl.geometry.zonotope.axis-cover"},std::nullopt};
    registry::Registry<registry::ConversionPort> conversions;
    if(conversions.add(make_zero_generator_removal_registration({"app03-exact"})))
        return EXIT_FAILURE;
    const registry::Method conversion_method{{"csl.geometry.zonotope.zero-removal"},std::nullopt};

    const auto diamond=source("diamond-source",{0,0},
        {2,3,{1,0,0.5,0,1,0.5}},{{"x"},{"y"},{"diagonal"}});
    const auto constrained=source("constrained-source",{0,0},
        {2,4,{2,0,0.5,0.25,0,1,0.5,0.25}},
        {{"shared"},{"vertical"},{"diagonal"},{"small"}},
        {1,4,{0,1,0,0}},{0});
    const auto sparse=source("zero-column-source",{1,2},
        {2,3,{2,0,0,0,0,3}},{{"x"},{"zero"},{"y"}});
    const ApproximationRequest diamond_request{{{"app03-report"},{"diamond"},{"diamond-physical"}},
        diamond.as_handle(),{"csl.zonotope"},SetRelation::outer,2,Assurance::numerical};
    const ApproximationRequest constrained_request{{{"app03-report"},{"constrained"},{"constrained-physical"}},
        constrained.as_handle(),{"csl.zonotope"},SetRelation::outer,3,Assurance::numerical};
    const ConversionRequest sparse_request{{{"app03-report"},{"zero-column"},{"zero-column-physical"}},
        sparse.as_handle(),{"csl.zonotope"},Assurance::numerical};

    const auto cover_case=[&](const ApproximationRequest& request,
                              const Vector& expected,std::size_t factors,
                              std::chrono::nanoseconds& elapsed) {
        const auto start=std::chrono::steady_clock::now();
        const auto outcome=run_registered(covers,cover_method,request,ExecutionContext{});
        const auto end=std::chrono::steady_clock::now();
        elapsed+=std::chrono::duration_cast<std::chrono::nanoseconds>(end-start);
        const auto* enclosed=std::get_if<EnclosedApproximation>(&outcome);
        if(!enclosed || enclosed->basis!=StructuralBasis::generator_axis_cover ||
           enclosed->result.relation!=SetRelation::outer ||
           enclosed->result.evidence.reference.identity!=request.identity ||
           enclosed->result.evidence.error_bound)return false;
        const auto native=sets::from_generator_handle(enclosed->result.output);
        const auto* output=std::get_if<sets::GeneratorSet>(&native);
        return output && output->factor_ids().size()==factors &&
            output->generators().values==expected && output->equalities().rows==0;
    };
    const auto exact_case=[&](std::chrono::nanoseconds& elapsed) {
        registry::Requirements requirements;
        requirements.output.representation={"csl.zonotope"};
        requirements.output.relation=SetRelation::equivalent;
        const auto start=std::chrono::steady_clock::now();
        auto selected=take(registry::prepare_provider(
            registry::select_provider(conversions,conversion_method,requirements)));
        auto prepared=take(selected.prepare(sparse_request));
        auto [workspace]=prepared.create();
        auto outcome=workspace->run(ExecutionContext{});
        const auto end=std::chrono::steady_clock::now();
        elapsed+=std::chrono::duration_cast<std::chrono::nanoseconds>(end-start);
        const auto* result=std::get_if<OperationResult>(&outcome);
        if(!result || result->relation!=SetRelation::equivalent ||
           result->evidence.reference.identity!=sparse_request.identity)return false;
        const auto native=sets::from_generator_handle(result->output);
        const auto* output=std::get_if<sets::GeneratorSet>(&native);
        return output && output->center()==Vector{1,2} &&
            output->generators().values==Vector{2,0,0,3} &&
            output->factor_ids()==std::vector<sets::FactorId>{{"x"},{"y"}};
    };
    const std::array<Case,3> cases{{
        {"diamond-axis-cover","generator-axis-cover",2,
         [&](auto& elapsed){return cover_case(diamond_request,{1.5,0,0,1.5},2,elapsed);}},
        {"constrained-axis-cover","generator-axis-cover",3,
         [&](auto& elapsed){return cover_case(constrained_request,{2,0.75,0,0,0,1.75},3,elapsed);}},
        {"zero-column-exact","physical-equivalence",2,exact_case}
    }};
    std::cout<<"phase,case,repetition,calls,status,verified,elapsed_ns,basis,output_generators\n";
    if(std::string_view(argv[1])=="smoke") {
        for(const auto& item:cases)if(!batch(item,"smoke",0,1))return EXIT_FAILURE;
    } else {
        for(const auto& item:cases)if(!batch(item,"warmup",0,100))return EXIT_FAILURE;
        for(int repetition=0;repetition<7;++repetition)
            for(int offset=0;offset<3;++offset)
                if(!batch(cases[(offset+repetition)%3],"trial",repetition,100))
                    return EXIT_FAILURE;
    }
    return EXIT_SUCCESS;
}
