#include <csl/optimization/worst_case_vertex.hpp>
#include <cmath>
#include <limits>

namespace csl::optimization {
namespace {
Unsupported unsupported(std::string field, std::string explanation,
                        DiagnosticCode code = DiagnosticCode::unsupported) {
    return {{{code, std::move(field), std::move(explanation)}}};
}
std::optional<OperationStopped> stopped(const ExecutionContext& context) {
    if(context.cancellation.stop_requested())
        return OperationStopped{StopReason::cancelled, "Worst-case vertex evaluation cancelled."};
    if(context.deadline && std::chrono::steady_clock::now() >= *context.deadline)
        return OperationStopped{StopReason::deadline_expired, "Worst-case vertex evaluation deadline expired."};
    return {};
}
}

WorstCaseVertexOutcome worst_case_vertex(const sets::SetData& domain,
    const Objective& objective, std::size_t max_vertices,
    const ExecutionContext& context) {
    if(objective.policy().assurance != Assurance::numerical)
        return unsupported("worst_case.assurance", "Validated arithmetic is unavailable.");
    if(domain.metadata()->set.dimension != objective.dimension())
        return unsupported("worst_case.dimension", "Set and objective dimensions differ.", DiagnosticCode::invalid_input);
    const auto representation = domain.representation();
    if(std::holds_alternative<sets::EmptyRepresentation>(representation)) return WorstCaseEmpty{};
    const auto* vertices = std::get_if<sets::VRepresentation>(&representation);
    const auto* singleton = std::get_if<sets::SingletonRepresentation>(&representation);
    if(!vertices && !singleton)
        return unsupported("worst_case.representation", "A complete bounded native V description or singleton is required.");
    if(vertices && vertices->rays.rows() != 0)
        return unsupported("worst_case.bounded", "V rays make the set unbounded.");
    const auto count = singleton ? 1 : vertices->vertices.rows();
    if(count == 0) return WorstCaseEmpty{};
    if(count > max_vertices)
        return unsupported("worst_case.capacity", "Vertex count exceeds the caller limit.");
    if(const auto stop=stopped(context)) return *stop;
    double maximum = -std::numeric_limits<double>::infinity();
    Vector argmax;
    for(std::size_t row=0; row<count; ++row) {
        if(const auto stop=stopped(context)) return *stop;
        Vector point(objective.dimension());
        for(std::size_t col=0; col<point.size(); ++col)
            point[col] = singleton ? singleton->point[col] : vertices->vertices(row,col);
        const auto evaluation=evaluate(objective,point);
        if(const auto* error=std::get_if<Diagnostic>(&evaluation))
            return unsupported(error->field,error->explanation,error->code);
        if(const auto* stop=std::get_if<OperationStopped>(&evaluation))return *stop;
        const auto value=std::get<double>(evaluation);
        if(!std::isfinite(value))
            return OperationStopped{StopReason::numerical_failure,"Nonfinite objective evaluation."};
        if(value>maximum) {maximum=value;argmax=std::move(point);}
    }
    return WorstCaseValue{maximum,std::move(argmax),count,Assurance::numerical};
}
} // namespace csl::optimization
