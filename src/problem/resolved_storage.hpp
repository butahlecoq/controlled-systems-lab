#pragma once
#include <csl/problem/validator.hpp>

namespace csl::problem::detail {
struct ContentStorage { std::vector<std::byte> bytes; ContentDigest digest; };
struct ResolvedStorage {
    Problem description;
    std::string label;
    model::LinearSystem model;
    ControlDomains controls;
    InitialData initial;
    ExternalData external;
    Constraints constraints;
    optimization::Objective objective;
    std::vector<ContentBinding> content;
};
struct ResolvedAccess {
    static ResolvedContent content(std::shared_ptr<const ContentStorage> storage) {return ResolvedContent{std::move(storage)};}
    static ResolvedProblem problem(std::shared_ptr<const ResolvedStorage> storage) {return ResolvedProblem{std::move(storage)};}
    static PreparedResolvedStrategy prepared(ResolvedProblem p,registry::PreparedStrategy prepared) {return PreparedResolvedStrategy{p,std::move(prepared)};}
};
Result<ContentDigest> identity_digest(const Problem&,std::span<const ContentBinding>);
std::vector<std::byte> encode_problem(const Problem&,std::span<const ContentBinding>);
} // namespace csl::problem::detail
