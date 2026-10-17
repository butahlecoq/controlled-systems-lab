#pragma once

#include <csl/artifacts/run_statistics.hpp>
#include <csl/geometry/bounded_hull_checker.hpp>

#include <string>
#include <string_view>

namespace csl::artifacts {

// Canonical, inert checker observation. Decoding a recorded "verified" status
// does not rerun or trust the checker; consumers must recheck source data.
ArtifactResult<std::string> encode_bounded_hull_check(const geometry::HullCheckRecord&);
ArtifactResult<geometry::HullCheckRecord> decode_bounded_hull_check(std::string_view);

} // namespace csl::artifacts
