#pragma once

#include <csl/optimization/objectives.hpp>
#include <csl/sets/data.hpp>
#include <utility>

namespace csl::optimization {

struct WorstCaseIntervalBuilder;

struct WorstCaseIntervalRequest {
    ProblemId problem;
    RequestId request;
    sets::SetData domain;
    Objective objective;
    std::size_t max_vertices;
};

// Outward binary64 bounds on the exact-real supremum over the convex hull of
// the request's stored V rows and the exact-real objective described by its
// stored binary64 coefficients. The request ID binds those immutable inputs.
class WorstCaseIntervalBounds {
public:
    const ProblemId& problem() const noexcept { return problem_; }
    const RequestId& request() const noexcept { return request_; }
    const SetId& domain() const noexcept { return domain_; }
    double lower() const noexcept { return lower_; }
    double upper() const noexcept { return upper_; }
private:
    WorstCaseIntervalBounds(ProblemId problem, RequestId request, SetId domain,
            double lower, double upper)
        : problem_(std::move(problem)), request_(std::move(request)),
          domain_(std::move(domain)), lower_(lower), upper_(upper) {}
    ProblemId problem_;
    RequestId request_;
    SetId domain_;
    double lower_;
    double upper_;
    friend struct WorstCaseIntervalBuilder;
};
struct WorstCaseIntervalEmpty {};
using WorstCaseIntervalOutcome = std::variant<WorstCaseIntervalBounds,
    WorstCaseIntervalEmpty, Unsupported, OperationStopped>;

// The interval upper bound uses the domain's coordinate box, so it remains
// valid without a floating-point convexity or PSD claim. It can be conservative.
WorstCaseIntervalOutcome worst_case_interval(const WorstCaseIntervalRequest&,
    const ExecutionContext& context = {});

} // namespace csl::optimization
