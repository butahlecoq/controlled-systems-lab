#pragma once

#include <csl/core/values.hpp>
#include <memory>
#include <variant>

namespace csl {
enum class SetProperty { unknown, yes, no };
struct SetMetadata {
    std::size_t dimension;
    RepresentationId representation;
    SetProperty convex, polyhedral, bounded;
};
class SetPayload { public: virtual ~SetPayload() = default; };
struct SetHandle { SetMetadata metadata; std::shared_ptr<const SetPayload> payload; SetId id; };
struct EmptySet { std::size_t dimension; };
struct UniversalSet { std::size_t dimension; };
struct Singleton { Vector point; };
using AdmissibleSet = std::variant<EmptySet, UniversalSet, Singleton, SetHandle>;
} // namespace csl
