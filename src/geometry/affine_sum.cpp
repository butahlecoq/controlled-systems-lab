#include <csl/geometry/affine_sum.hpp>

#include <csl/numeric/data.hpp>
#include <csl/sets/data.hpp>
#include "exact_dyadic.hpp"
#include "exact_convex_combination.hpp"
#include "conversion/exact_h_box.hpp"
#include "conversion/exact_h_interval.hpp"
#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>
#include <span>

namespace csl::geometry {
namespace {
Diagnostic diagnostic(DiagnosticCode code, std::string field, std::string reason) {
    return {code, std::move(field), std::move(reason)};
}
Unsupported unsupported(std::string field, std::string reason,
        DiagnosticCode code = DiagnosticCode::unsupported) {
    return Unsupported{{diagnostic(code, std::move(field), std::move(reason))}};
}
bool stopped(const ExecutionContext& context) {
    return context.cancellation.stop_requested() ||
        (context.deadline && std::chrono::steady_clock::now() >= *context.deadline);
}
StopReason stop_reason(const ExecutionContext& context) {
    return context.cancellation.stop_requested() ? StopReason::cancelled : StopReason::resource_limit;
}
bool finite_policy(const NumericalPolicy& policy) {
    return std::isfinite(policy.absolute_tolerance) && policy.absolute_tolerance >= 0.0 &&
        std::isfinite(policy.relative_tolerance) && policy.relative_tolerance >= 0.0 &&
        policy.absolute_tolerance <= std::numeric_limits<double>::max() - policy.relative_tolerance;
}
std::string identity(const registry::Provenance& provenance) {
    if (!provenance.actual) return "unresolved";
    return provenance.actual->id.value + "@" + provenance.actual->version;
}
std::string lp_query_problem_id(const GeometryRequestIdentity& request) {
    // Length-prefix each field so distinct concurrent geometry requests never
    // alias the problem IDs used by the registered hull-membership LP queries.
    const auto field = [](const std::string& value) {
        return std::to_string(value.size()) + ":" + value;
    };
    return "affine-sum/" + field(request.problem.value) + field(request.request.value) +
        field(request.ideal_output.value);
}

struct FiniteSet {
    std::size_t dimension{};
    std::vector<std::string> labels;
    std::vector<Vector> points;
    std::vector<std::string> assumptions;
    // Hausdorff L-infinity distance from the represented input set to the
    // hull of these stored vertices. Zero means the input itself was finite V.
    std::optional<double> input_to_vertices_error = 0.0;
};

bool candidate_error(const AffineImage& image, std::span<const double> point,
        std::size_t row, double candidate, detail::exact_detail::Integer& error) {
    using namespace detail::exact_detail;
    for (std::size_t col = 0; col < point.size(); ++col)
        if (!add_product(error, decode(image.map.values[row * point.size() + col]), decode(point[col])))
            return false;
    if (!add_dyadic(error, decode(image.offset[row]))) return false;
    auto rounded = decode(candidate);
    rounded.negative = !rounded.negative;
    if (!add_dyadic(error, rounded)) return false;
    error.negative = false;
    return true;
}

bool candidate_error(double lhs, double rhs, double candidate,
        detail::exact_detail::Integer& error) {
    using namespace detail::exact_detail;
    if (!add_dyadic(error, decode(lhs)) || !add_dyadic(error, decode(rhs))) return false;
    auto rounded = decode(candidate);
    rounded.negative = !rounded.negative;
    if (!add_dyadic(error, rounded)) return false;
    error.negative = false;
    return true;
}

void retain_maximum_error(const detail::exact_detail::Integer& error,
        detail::exact_detail::Integer& maximum) {
    using namespace detail::exact_detail;
    if (compare_magnitude(error, maximum) > 0) maximum = error;
}

bool conversion_residual_admissible(const sets::HRepresentation& input,
        const std::vector<Vector>& vertices, NumericalPolicy policy, double reported_residual) {
    long double maximum_allowed=static_cast<long double>(policy.absolute_tolerance)+
        static_cast<long double>(policy.relative_tolerance);
    if(!std::isfinite(maximum_allowed)) return false;
    const auto check_row=[&](const numeric::MatrixView& matrix,const numeric::VectorView& bounds,
            std::size_t row,std::span<const double> point,bool equality) {
        long double activity=0.0L;
        for(std::size_t column=0;column<point.size();++column)
            activity+=static_cast<long double>(matrix(row,column))*static_cast<long double>(point[column]);
        const long double bound=static_cast<long double>(bounds[row]);
        const long double scale=std::max({1.0L,std::abs(activity),std::abs(bound)});
        const long double allowed=static_cast<long double>(policy.absolute_tolerance)+
            static_cast<long double>(policy.relative_tolerance)*scale;
        if(!std::isfinite(activity)||!std::isfinite(allowed)) return false;
        maximum_allowed=std::max(maximum_allowed,allowed);
        const long double residual=equality ? std::abs(activity-bound) : std::max(0.0L,activity-bound);
        return residual<=allowed;
    };
    for(const auto& point:vertices) {
        if(point.size()!=input.inequalities.cols()) return false;
        for(std::size_t row=0;row<input.inequalities.rows();++row)
            if(!check_row(input.inequalities,input.upper_bounds,row,point,false)) return false;
        for(std::size_t row=0;row<input.equalities.rows();++row)
            if(!check_row(input.equalities,input.equality_values,row,point,true)) return false;
    }
    return std::isfinite(static_cast<long double>(reported_residual)) &&
        std::isfinite(maximum_allowed) &&
        static_cast<long double>(reported_residual)<=maximum_allowed;
}

OperationOutcome operation_error(Unsupported failure) { return OperationOutcome{std::move(failure)}; }
OperationOutcome operation_stop(OperationStopped stop) { return OperationOutcome{std::move(stop)}; }

std::variant<FiniteSet, OperationOutcome> finite_vertices(const SetHandle& handle,
        const OperationRequest& parent, const ExecutionContext& context,
        const AffineSumDependencies& dependencies) {
    auto imported = sets::from_handle(handle);
    if (const auto* error = std::get_if<Diagnostic>(&imported))
        return operation_error(unsupported(error->field, error->explanation, error->code));
    auto data = std::get<sets::SetData>(std::move(imported));
    const auto metadata = data.metadata();
    const auto representation = data.representation();
    const auto* input_h=std::get_if<sets::HRepresentation>(&representation);
    FiniteSet result{metadata->set.dimension, metadata->coordinate_labels, {}, {}};
    if (std::holds_alternative<sets::EmptyRepresentation>(representation)) return result;
    if (const auto* singleton = std::get_if<sets::SingletonRepresentation>(&representation)) {
        const auto values = singleton->point.values();
        result.points.emplace_back(values.begin(), values.end());
        return result;
    }
    if (std::holds_alternative<sets::UniversalRepresentation>(representation)) {
        if (result.dimension != 0)
            return operation_error(unsupported("affine-sum.universal", "Positive-dimensional universal sets are not finite V polyhedra."));
        result.points.emplace_back(); // R^0 contains the one empty vector.
        result.assumptions.emplace_back("R^0 is represented by its unique empty-coordinate point");
        return result;
    }
    const auto* v = std::get_if<sets::VRepresentation>(&representation);
    if (v) {
        if (v->rays.rows() != 0)
            return unsupported("affine-sum.rays", "Unbounded V representations with rays are unsupported.");
        if (v->vertices.rows() == 0) return result;
        result.points.reserve(v->vertices.rows());
        for (std::size_t row = 0; row < v->vertices.rows(); ++row) {
            Vector point(result.dimension);
            for (std::size_t col = 0; col < result.dimension; ++col) {
                point[col] = v->vertices(row, col);
                if (!std::isfinite(point[col]))
                    return operation_error(unsupported("affine-sum.coordinates", "Vertex coordinates must be finite.", DiagnosticCode::invalid_input));
            }
            result.points.push_back(std::move(point));
        }
        return result;
    }

    if (!dependencies.conversion)
        return operation_error(unsupported("affine-sum.conversion", "H input requires an explicitly selected H-to-V converter."));
    ConversionRequest request{
        {parent.identity.problem,
         {parent.identity.request.value + "/affine-sum-convert/" + handle.id.value},
         {parent.identity.ideal_output.value + "/converted/" + handle.id.value}},
        handle, {"csl.polyhedron.v"}, parent.assurance};
    auto prepared_result = dependencies.conversion->prepare(request);
    if (std::holds_alternative<registry::Rejection>(prepared_result))
        return operation_error(unsupported("affine-sum.conversion", "Selected H-to-V converter rejected the concrete request."));
    auto prepared = std::get<registry::PreparedPipeline<registry::ConversionPort>>(std::move(prepared_result));
    auto workspaces = prepared.create();
    auto converted = std::get<0>(workspaces)->run(context);
    if (const auto* stop = std::get_if<OperationStopped>(&converted)) return operation_stop(*stop);
    if (const auto* rejection = std::get_if<Unsupported>(&converted)) return operation_error(*rejection);
    const auto& transformed = std::get<OperationResult>(converted);
    if (transformed.relation != SetRelation::equivalent)
        return operation_error(unsupported("affine-sum.conversion.relation", "H-to-V conversion must return an equivalent relation."));
    if (auto errors = check_geometry_evidence(transformed.evidence, request); !errors.empty())
        return operation_error(Unsupported{std::move(errors)});
    const auto* conversion_check=std::get_if<NumericalCheck>(&transformed.evidence.support);
    if (!conversion_check || !std::isfinite(conversion_check->absolute_tolerance) ||
        conversion_check->absolute_tolerance<0.0 ||
        !std::isfinite(conversion_check->relative_tolerance) || conversion_check->relative_tolerance<0.0 ||
        !std::isfinite(conversion_check->max_residual) || conversion_check->max_residual<0.0 ||
        conversion_check->verifier.value.empty() ||
        conversion_check->absolute_tolerance>context.numerical.absolute_tolerance ||
        conversion_check->relative_tolerance>context.numerical.relative_tolerance)
        return operation_error(unsupported("affine-sum.conversion.evidence",
            "H-to-V conversion requires finite numerical evidence from a named verifier within the caller tolerance."));
    auto converted_data = sets::from_handle(transformed.output);
    if (const auto* error = std::get_if<Diagnostic>(&converted_data))
        return operation_error(unsupported(error->field, error->explanation, error->code));
    auto converted_set = std::get<sets::SetData>(std::move(converted_data));
    const auto converted_representation = converted_set.representation();
    const auto* converted_v = std::get_if<sets::VRepresentation>(&converted_representation);
    if (!converted_v || converted_v->rays.rows() != 0)
        return operation_error(unsupported("affine-sum.conversion.output", "Selected converter did not produce a bounded finite V representation."));
    if (converted_set.metadata()->set.dimension != result.dimension)
        return operation_error(unsupported("affine-sum.conversion.dimension", "Converter changed the ambient dimension."));
    result.labels = converted_set.metadata()->coordinate_labels;
    if (result.labels != metadata->coordinate_labels)
        return operation_error(unsupported("affine-sum.conversion.labels", "Selected converter changed the input coordinate labels."));
    for (std::size_t row = 0; row < converted_v->vertices.rows(); ++row) {
        Vector point(result.dimension);
        for (std::size_t col = 0; col < result.dimension; ++col) {
            point[col] = converted_v->vertices(row,col);
            if (!std::isfinite(point[col]))
                return operation_error(unsupported("affine-sum.conversion.coordinates", "Converted vertices must be finite."));
        }
        result.points.push_back(std::move(point));
    }
    if(!input_h || !conversion_residual_admissible(*input_h,result.points,context.numerical,
            conversion_check->max_residual))
        return operation_error(unsupported("affine-sum.conversion.residual",
            "H-to-V vertices or reported maximum residual exceed the caller-compatible row-scaled policy."));
    result.assumptions = transformed.evidence.assumptions;
    result.input_to_vertices_error.reset();
    if (input_h->inequalities.cols() == 1) {
        const auto coverage = detail::certify_h_interval(*input_h, *converted_v);
        if (const auto* bound = std::get_if<double>(&coverage))
            result.input_to_vertices_error = *bound;
    } else {
        const auto coverage = detail::certify_h_box(*input_h, *converted_v);
        if (const auto* bound = std::get_if<double>(&coverage))
            result.input_to_vertices_error = *bound;
    }
    result.assumptions.emplace_back("H-to-V conversion evidence is numerical and conditional on the selected converter");
    if (result.input_to_vertices_error)
        result.assumptions.emplace_back("H/V coverage was independently checked against exact stored-dyadic ambient-one or supported axis-aligned box rows");
    return result;
}

bool valid_reduction(const PointCloud& cloud, const HullReduction& reduction,
                     NumericalPolicy policy, double& maximum_residual) {
    if (reduction.status != ReductionStatus::complete) return false;
    const std::size_t count = cloud.points.size();
    std::vector<unsigned char> retained(count, 0);
    std::vector<const RemovalCertificate*> certificates(count, nullptr);
    for (auto point : reduction.retained) {
        if (point >= count || retained[point]) return false;
        retained[point] = 1;
    }
    for (const auto& certificate : reduction.removed) {
        if (certificate.removed >= count || retained[certificate.removed] || certificates[certificate.removed]) return false;
        certificates[certificate.removed] = &certificate;
    }
    for (std::size_t point = 0; point < count; ++point)
        if (!retained[point] && !certificates[point]) return false;

    const auto tolerance_for = [&](long double value, long double reconstruction_error) {
        return static_cast<long double>(policy.absolute_tolerance) +
            static_cast<long double>(policy.relative_tolerance) *
            std::max(1.0L,std::abs(value)+reconstruction_error);
    };
    std::vector<std::size_t> remaining_children(count,0), ready;
    std::vector<long double> weight_sums(count,0.0L), error_bounds(count,0.0L);
    std::vector<std::vector<std::pair<std::size_t,long double>>> parents(count);
    std::size_t removed_count=0;
    for(std::size_t point=0;point<count;++point) {
        if(retained[point]) continue;
        ++removed_count;
        const auto& certificate=*certificates[point];
        if(!std::isfinite(certificate.evidence.max_residual) || certificate.evidence.max_residual<0.0 ||
            !std::isfinite(certificate.evidence.absolute_tolerance) || certificate.evidence.absolute_tolerance<0.0 ||
            !std::isfinite(certificate.evidence.relative_tolerance) || certificate.evidence.relative_tolerance<0.0 ||
            certificate.combination.empty()) return false;
        for(const auto& term:certificate.combination) {
            if(term.point>=count || !std::isfinite(term.weight) || term.weight<0.0) return false;
            weight_sums[point]+=static_cast<long double>(term.weight);
            if(!retained[term.point]) {
                if(remaining_children[point]==std::numeric_limits<std::size_t>::max()) return false;
                ++remaining_children[point];
                parents[term.point].emplace_back(point,static_cast<long double>(term.weight));
            }
        }
        const long double normalization_tolerance=static_cast<long double>(policy.absolute_tolerance)+
            static_cast<long double>(policy.relative_tolerance);
        if(!std::isfinite(weight_sums[point]) ||
            std::abs(weight_sums[point]-1.0L)>normalization_tolerance) return false;
        // Compute each local reconstruction residual from the original candidate
        // coordinates; subsequent certificate dependencies are handled below.
        for(std::size_t coordinate=0;coordinate<cloud.points[point].size();++coordinate) {
            long double reconstructed=0.0L;
            for(const auto& term:certificate.combination)
                reconstructed+=(static_cast<long double>(term.weight)/weight_sums[point])*
                    static_cast<long double>(cloud.points[term.point][coordinate]);
            const long double residual=std::abs(reconstructed-static_cast<long double>(cloud.points[point][coordinate]));
            if(!std::isfinite(residual)) return false;
            error_bounds[point]=std::max(error_bounds[point],residual);
        }
    }
    // A certificate for x_i may refer to another removed point x_j. Propagate
    // conservative infinity-norm residual bounds from final retained points
    // through this DAG in linear memory and time in the certificate edge count.
    for(std::size_t point=0;point<count;++point)
        if(certificates[point] && remaining_children[point]==0) ready.push_back(point);
    std::size_t processed=0;
    for(std::size_t cursor=0;cursor<ready.size();++cursor) {
        const auto child=ready[cursor]; ++processed;
        for(const auto& [parent,weight]:parents[child]) {
            error_bounds[parent]+=(weight/weight_sums[parent])*error_bounds[child];
            if(!std::isfinite(error_bounds[parent]) || remaining_children[parent]==0) return false;
            if(--remaining_children[parent]==0) ready.push_back(parent);
        }
    }
    if(processed!=removed_count) return false;
    for(std::size_t point=0;point<count;++point) {
        if(retained[point]) continue;
        for(const double coordinate:cloud.points[point]) {
            const long double allowed=tolerance_for(static_cast<long double>(coordinate),error_bounds[point]);
            if(!std::isfinite(allowed) || error_bounds[point]>allowed) return false;
        }
        const double reported_residual=static_cast<double>(error_bounds[point]);
        if(!std::isfinite(reported_residual)) return false;
        maximum_residual=std::max(maximum_residual,reported_residual);
    }
    return !reduction.retained.empty() || count == 0;
}

class AffineSumWorkspace final : public SetOperatorWorkspace {
    OperationRequest request_;
    AffineSumDependencies dependencies_;
    AffineSumOptions options_;

    OperationOutcome apply_supported(const ExecutionContext& context) {
        if (request_.assurance != Assurance::numerical)
            return unsupported("geometry.assurance", "Affine images and sums provide numerical evidence only.");
        if (request_.required_relation != SetRelation::equivalent)
            return unsupported("geometry.relation", "This implementation returns only its numerical equivalent relation.");
        if (!finite_policy(context.numerical))
            return unsupported("geometry.numerical", "Finite nonnegative numerical tolerances are required.", DiagnosticCode::invalid_input);
        if (const auto errors = check_operation_shape(request_); !errors.empty()) return Unsupported{errors};
        if (const auto* image = std::get_if<AffineImage>(&request_.operation)) {
            if (!std::all_of(image->map.values.begin(), image->map.values.end(),
                    [](double value) { return std::isfinite(value); }) ||
                !std::all_of(image->offset.begin(), image->offset.end(),
                    [](double value) { return std::isfinite(value); }))
                return unsupported("affine-sum.parameters", "Affine map and offset must contain only finite values.", DiagnosticCode::invalid_input);
        }
        if (stopped(context)) return OperationStopped{stop_reason(context), "Stopped before affine/sum execution."};

        SetHandle left_handle, right_handle;
        if (const auto* image = std::get_if<AffineImage>(&request_.operation)) left_handle = image->input;
        else if (const auto* sum = std::get_if<MinkowskiSum>(&request_.operation)) {
            left_handle = sum->left; right_handle = sum->right;
        } else return unsupported("geometry.operation", "Only affine images and Minkowski sums are implemented.");

        auto left_result = finite_vertices(left_handle, request_, context, dependencies_);
        if (auto* failed = std::get_if<OperationOutcome>(&left_result)) return std::move(*failed);
        auto left = std::get<FiniteSet>(std::move(left_result));
        std::optional<FiniteSet> right;
        if (std::holds_alternative<MinkowskiSum>(request_.operation)) {
            auto right_result = finite_vertices(right_handle, request_, context, dependencies_);
            if (auto* failed = std::get_if<OperationOutcome>(&right_result)) return std::move(*failed);
            right = std::get<FiniteSet>(std::move(right_result));
            if (left.labels != right->labels)
                return unsupported("geometry.coordinates", "Minkowski operands must use identical coordinate labels.", DiagnosticCode::invalid_input);
        }

        std::size_t output_dimension = left.dimension;
        std::vector<std::string> labels = left.labels;
        std::size_t candidate_count = 0;
        if (const auto* image = std::get_if<AffineImage>(&request_.operation)) {
            output_dimension = image->map.rows;
            labels = options_.affine_output_labels;
            if (!labels.empty() && labels.size() != output_dimension)
                return unsupported("affine-sum.output_labels", "Output labels must be empty or match the affine image dimension.", DiagnosticCode::invalid_input);
            candidate_count = left.points.size();
        } else {
            if (left.dimension != right->dimension)
                return unsupported("affine-sum.dimension", "Minkowski operands have different ambient dimensions.", DiagnosticCode::invalid_input);
            if (!left.points.empty() && right->points.size() > std::numeric_limits<std::size_t>::max() / left.points.size())
                return unsupported("affine-sum.capacity", "Candidate count overflows size_t.");
            candidate_count = left.points.size() * right->points.size();
        }
        if (options_.max_candidates && candidate_count > *options_.max_candidates)
            return unsupported("affine-sum.capacity", "Generated point cloud exceeds the caller's candidate admission limit.");
        if (output_dimension != 0 && candidate_count > std::numeric_limits<std::size_t>::max() / output_dimension)
            return unsupported("affine-sum.capacity", "Candidate coordinate storage overflows size_t.");
        if (candidate_count > std::vector<Vector>{}.max_size() ||
            candidate_count * output_dimension > std::vector<double>{}.max_size())
            return unsupported("affine-sum.capacity", "Candidate cloud exceeds the container's representable size.");
        if (stopped(context)) return OperationStopped{stop_reason(context), "Stopped before candidate generation."};

        Vector candidates;
        candidates.reserve(candidate_count * output_dimension);
        const std::size_t result_id_dimension = output_dimension;
        const bool exact_bound_applicable = left.input_to_vertices_error.has_value() &&
            (!right || right->input_to_vertices_error.has_value());
        detail::exact_detail::Integer maximum_candidate_error;
        if (const auto* image = std::get_if<AffineImage>(&request_.operation)) {
            for (const auto& point : left.points) {
                if (stopped(context)) return OperationStopped{stop_reason(context), "Stopped during affine image generation."};
                for (std::size_t row = 0; row < output_dimension; ++row) {
                    double value = image->offset[row];
                    for (std::size_t col = 0; col < left.dimension; ++col) value += image->map.values[row * left.dimension + col] * point[col];
                    if (!std::isfinite(value)) return unsupported("affine-sum.arithmetic", "Affine image produced a non-finite coordinate.");
                    if (exact_bound_applicable) {
                        detail::exact_detail::Integer error;
                        if (!candidate_error(*image, point, row, value, error))
                            return unsupported("affine-sum.error_bound", "Exact dyadic affine error exceeded its checked arithmetic range.");
                        retain_maximum_error(error, maximum_candidate_error);
                    }
                    candidates.push_back(value);
                }
            }
        } else {
            for (const auto& a : left.points) for (const auto& b : right->points) {
                if (stopped(context)) return OperationStopped{stop_reason(context), "Stopped during Minkowski sum generation."};
                for (std::size_t coordinate = 0; coordinate < output_dimension; ++coordinate) {
                    const double value = a[coordinate] + b[coordinate];
                    if (!std::isfinite(value)) return unsupported("affine-sum.arithmetic", "Minkowski sum produced a non-finite coordinate.");
                    if (exact_bound_applicable) {
                        detail::exact_detail::Integer error;
                        if (!candidate_error(a[coordinate], b[coordinate], value, error))
                            return unsupported("affine-sum.error_bound", "Exact dyadic Minkowski error exceeded its checked arithmetic range.");
                        retain_maximum_error(error, maximum_candidate_error);
                    }
                    candidates.push_back(value);
                }
            }
        }
        Matrix point_matrix{candidate_count,result_id_dimension,std::move(candidates)};
        auto point_view = numeric::snapshot(point_matrix);
        if (const auto* error = std::get_if<Diagnostic>(&point_view)) return unsupported(error->field,error->explanation,error->code);
        Matrix ray_matrix{0,result_id_dimension,{}};
        auto ray_view = numeric::snapshot(ray_matrix);
        if (const auto* error = std::get_if<Diagnostic>(&ray_view)) return unsupported(error->field,error->explanation,error->code);
        auto generated = sets::make_v({{"affine-sum-generated"},result_id_dimension,labels},
            {std::get<numeric::MatrixView>(point_view),std::get<numeric::MatrixView>(ray_view)});
        if (const auto* error = std::get_if<Diagnostic>(&generated)) return unsupported(error->field,error->explanation,error->code);

        PointCloud cloud{ProblemId{lp_query_problem_id(request_.identity)},{}};
        cloud.points.reserve(candidate_count);
        const auto view = std::get<sets::SetData>(generated).representation();
        const auto& generated_vertices = std::get<sets::VRepresentation>(view).vertices;
        for (std::size_t row=0; row<generated_vertices.rows(); ++row) {
            Vector point(result_id_dimension);
            for (std::size_t col=0; col<result_id_dimension; ++col) point[col]=generated_vertices(row,col);
            cloud.points.push_back(std::move(point));
        }
        if (stopped(context)) return OperationStopped{stop_reason(context), "Stopped before hull reduction."};

        auto hull_prepared_result = dependencies_.hull.prepare(cloud);
        double max_residual=0.0;
        bool reduction_usable=false;
        std::optional<HullReduction> reduction;
        if (std::holds_alternative<registry::PreparedPipeline<registry::HullReducerPort>>(hull_prepared_result)) {
            auto hull_prepared=std::get<registry::PreparedPipeline<registry::HullReducerPort>>(std::move(hull_prepared_result));
            auto hull_workspaces=hull_prepared.create();
            auto lp_runner=std::make_unique<registry::RegisteredLPQueryRunner>(dependencies_.lp);
            auto reduction_result=std::get<0>(hull_workspaces)->run_with(context,*lp_runner);
            if (auto* complete=std::get_if<HullReduction>(&reduction_result)) {
                reduction=std::move(*complete);
                const auto& checked=*reduction;
                reduction_usable=checked.lp_calls==lp_runner->records().size() &&
                    valid_reduction(cloud,checked,context.numerical,max_residual);
                if (reduction_usable) {
                    for (const auto& certificate:checked.removed) {
                        if (stopped(context))
                            return OperationStopped{stop_reason(context), "Stopped while checking exact hull certificates."};
                        if (!detail::exact_convex_combination(cloud,certificate.removed,
                                std::span<const ConvexCombination>{certificate.combination})) {
                            reduction_usable=false;
                            break;
                        }
                    }
                }
            }
        }
        std::vector<std::size_t> output_indices;
        if (reduction_usable) output_indices=reduction->retained;
        else {
            output_indices.resize(cloud.points.size());
            std::iota(output_indices.begin(),output_indices.end(),std::size_t{0});
        }
        std::vector<double> retained_values;
        if (result_id_dimension != 0 && output_indices.size() > std::numeric_limits<std::size_t>::max()/result_id_dimension)
            return unsupported("affine-sum.capacity", "Retained cloud storage overflows size_t.");
        if (output_indices.size() > std::vector<double>{}.max_size() / std::max<std::size_t>(result_id_dimension,1))
            return unsupported("affine-sum.capacity", "Retained cloud exceeds the container's representable size.");
        retained_values.reserve(output_indices.size()*result_id_dimension);
        for(const auto index:output_indices) retained_values.insert(retained_values.end(),cloud.points[index].begin(),cloud.points[index].end());
        Matrix retained_matrix{output_indices.size(),result_id_dimension,std::move(retained_values)};
        auto retained_view=numeric::snapshot(retained_matrix);
        if(const auto* error=std::get_if<Diagnostic>(&retained_view)) return unsupported(error->field,error->explanation,error->code);
        auto output=sets::make_v({{request_.identity.ideal_output.value},result_id_dimension,labels},
            {std::get<numeric::MatrixView>(retained_view),std::get<numeric::MatrixView>(ray_view)});
        if(const auto* error=std::get_if<Diagnostic>(&output)) return unsupported(error->field,error->explanation,error->code);

        std::vector<std::string> assumptions{
            "binary64 affine and sum arithmetic; caller tolerance screens reduction evidence but cannot authorize deletion",
            reduction_usable ?
                "reducer retained indices applied only after exact binary64 convex-combination checks for every removal and complete acyclic dependency and partition validation" :
                "all generated candidates retained because the complete reduction failed exact binary64 certification or structural validation",
            "NumericalCheck.max_residual records the maximum attempted reducer reconstruction residual in binary64; it is not an output error bound and does not authorize candidate removal",
            "numerical equivalent relation is an algorithm claim, not exact equality or validated inclusion for the intended real-valued model",
            exact_bound_applicable ?
                "published L-infinity error bound composes exact represented-dyadic candidate generation with direct V inputs or independently checked ambient-one/axis-aligned-box H/V coverage; exact deletion preserves the generated hull" :
                "no independently checked global H/V coverage bound is available for every converted operand; no operation error bound is reported",
            "finite and mixed action catalogues are not accepted by this SetHandle operation",
            "selected hull reducer: " + identity(dependencies_.hull.provenance()),
            "selected LP provider: " + identity(dependencies_.lp.provenance())};
        if(dependencies_.conversion)
            assumptions.push_back("selected H-to-V converter: " + identity(dependencies_.conversion->provenance()));
        assumptions.insert(assumptions.end(),left.assumptions.begin(),left.assumptions.end());
        if(right) assumptions.insert(assumptions.end(),right->assumptions.begin(),right->assumptions.end());
        const std::vector<SetId> inputs = std::visit([](const auto& operation) -> std::vector<SetId> {
            using T=std::decay_t<decltype(operation)>;
            if constexpr(std::is_same_v<T,AffineImage>) return {operation.input.id};
            else if constexpr(std::is_same_v<T,MinkowskiSum>) return {operation.left.id,operation.right.id};
            else return {};
        },request_.operation);
        GeometryEvidence evidence{{request_.identity,inputs},GeometryClaimScope::set_relation,
            NumericalCheck{context.numerical.absolute_tolerance,context.numerical.relative_tolerance,
                max_residual,{"csl.geometry.affine-sum"}},
            std::move(assumptions),{}};
        if (exact_bound_applicable) {
            using namespace detail::exact_detail;
            Integer propagated_input_error;
            if (candidate_count != 0) {
                if (const auto* image = std::get_if<AffineImage>(&request_.operation)) {
                    const double input_error = *left.input_to_vertices_error;
                    for (std::size_t row = 0; row < output_dimension; ++row) {
                        Integer row_error;
                        for (std::size_t col = 0; col < left.dimension; ++col) {
                            auto coefficient = decode(image->map.values[row * left.dimension + col]);
                            coefficient.negative = false;
                            if (!add_product(row_error, coefficient, decode(input_error)))
                                return unsupported("affine-sum.error_bound", "Exact affine conversion-bound propagation exceeded its checked arithmetic range.");
                        }
                        retain_maximum_error(row_error, propagated_input_error);
                    }
                } else {
                    if (!add_dyadic(propagated_input_error, decode(*left.input_to_vertices_error)) ||
                        !add_dyadic(propagated_input_error, decode(*right->input_to_vertices_error)))
                        return unsupported("affine-sum.error_bound", "Exact Minkowski conversion-bound composition exceeded its checked arithmetic range.");
                }
            }
            if (!add_signed(propagated_input_error, maximum_candidate_error))
                return unsupported("affine-sum.error_bound", "Exact composed geometry error exceeded its checked arithmetic range.");
            const auto outward = outward_binary64(propagated_input_error);
            if (!outward)
                return unsupported("affine-sum.error_bound", "Exact dyadic candidate error has no finite binary64 outward bound.");
            evidence.error_bound = GeometryErrorBound{{"csl.geometry.metric.l-infinity"}, *outward,
                "maximum absolute output-coordinate units; empty-to-empty distance is defined as zero"};
        }
        if(auto errors=check_geometry_evidence(evidence,request_);!errors.empty()) return Unsupported{std::move(errors)};
        return OperationResult{std::get<sets::SetData>(std::move(output)).as_handle(),SetRelation::equivalent,std::move(evidence)};
    }
public:
    AffineSumWorkspace(OperationRequest request, AffineSumDependencies dependencies, AffineSumOptions options)
        : request_(std::move(request)), dependencies_(std::move(dependencies)), options_(std::move(options)) {}
    OperationOutcome apply(const OperationRequest& request, const ExecutionContext& context) override {
        static_cast<void>(request); // GeometryPort binds and snapshots this immutable request before workspace creation.
        return apply_supported(context);
    }
};
} // namespace

registry::Registration<registry::GeometryPort> make_affine_sum_registration(
        AffineSumDependencies dependencies, AffineSumOptions options) {
    return {{{"csl.geometry.affine-sum"},"1.0.0"},
        [](const OperationRequest& request,const registry::Requirements& requirements) -> registry::Capability {
            if(request.assurance!=Assurance::numerical || requirements.output.assurance!=Assurance::numerical)
                return Diagnostics{{DiagnosticCode::unsupported,"geometry.assurance","Affine images and Minkowski sums require numerical assurance."}};
            if(request.required_relation!=SetRelation::equivalent ||
                (requirements.output.relation && *requirements.output.relation!=SetRelation::equivalent))
                return Diagnostics{{DiagnosticCode::unsupported,"geometry.relation","Only numerical equivalent set operations are supported."}};
            if(!std::holds_alternative<AffineImage>(request.operation) && !std::holds_alternative<MinkowskiSum>(request.operation))
                return Diagnostics{{DiagnosticCode::unsupported,"geometry.operation","Only affine images and Minkowski sums are implemented."}};
            registry::Output output; output.representation={"csl.polyhedron.v"}; output.assurance=Assurance::numerical; output.relation=SetRelation::equivalent;
            return registry::Offer{output};
        },
        [dependencies=std::move(dependencies),options=std::move(options)](const OperationRequest& request) mutable {
            return std::make_unique<AffineSumWorkspace>(request,dependencies,options);
        }};
}
} // namespace csl::geometry
