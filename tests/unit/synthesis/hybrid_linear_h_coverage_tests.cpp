#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <csl/sets/data.hpp>
#include <csl/synthesis/hybrid_path_program.hpp>
#include <doctest/doctest.h>

using namespace csl;
using namespace csl::synthesis;
namespace {
template <class T, class... E> T take(std::variant<T, E...> value) {
  REQUIRE(std::holds_alternative<T>(value));
  return std::get<T>(std::move(value));
}
numeric::MatrixView matrix(Matrix m) { return take(numeric::snapshot(m)); }
numeric::VectorView vector(Vector v) {
  return take(numeric::snapshot_vector(v));
}
sets::SetData point(Vector v) {
  const auto dimension = v.size();
  return take(
      sets::make_singleton({{"point"}, dimension, {}}, vector(std::move(v))));
}
sets::SetData vertex_point(std::size_t dimension) {
  return take(sets::make_v(
      {{"vertex-point"}, dimension, {}},
      {matrix({1, dimension, Vector(dimension)}), matrix({0, dimension, {}})}));
}
struct Fixture {
  model::HybridSystem system;
  model::HybridRequest request;
  std::vector<HybridPathProgram> programs;
  std::vector<HybridPathOptimalFaceCandidate> candidates;
};
Fixture fixture(bool parallel = false, bool with_worse = false) {
  const std::size_t horizon = parallel ? 1 : 0;
  model::HybridMode mode{
      {"mode"},
      1,
      0,
      {"x"},
      {},
      LinearStage{{1, 1, {1}}, {1, 0, {}}, {1, 0, {}}, {0}},
      std::vector<AdmissibleSet>(horizon, UniversalSet{0}),
      std::vector<AdmissibleSet>(horizon + 1, UniversalSet{1})};
  model::HybridSystem system{horizon, {mode}, {}};
  if (parallel)
    for (const auto *id : {"edge-a", "edge-b"})
      system.edges.push_back({{id},
                              {"mode"},
                              {"mode"},
                              {UniversalSet{1}},
                              {point({0, 0}).as_handle()}});
  if (with_worse)
    system.edges.push_back({{"edge-worse"},
                            {"mode"},
                            {"mode"},
                            {UniversalSet{1}},
                            {point({0, 1}).as_handle()}});
  model::HybridRequest request{{{"mode"}, {0}},
                               {{"mode"}},
                               {{{"mode"},
                                 LinearTerminal{{with_worse ? 1. : 0.}, 0},
                                 "terminal",
                                 "units"}}};
  auto programs = take(build_hybrid_portfolio_programs(
      system, request, {"coverage-status"}, {1, 4}, {16, 128, 4096}));
  std::vector<HybridPathOptimalFaceCandidate> candidates;
  for (const auto &program : programs) {
    const auto &linear = std::get<LinearProgram>(program.program);
    Vector anchor(linear.variables().size(), 0);
    if (with_worse && program.path.edges.front().value == "edge-worse")
      anchor.back() = 1;
    ProgramResult solved{Termination::completed,
                         {linear.identity(),
                          MathematicalOutcome::optimal,
                          SymbolicArgument{"literal singleton trajectory",
                                           "singleton objective evaluation"},
                          {}},
                         anchor,
                         {},
                         "literal exact singleton"};
    candidates.push_back(take(
        build_hybrid_path_optimal_face_candidate(program, solved, {0, 0})));
  }
  return {std::move(system), std::move(request), std::move(programs),
          std::move(candidates)};
}
HybridFamilyVerificationReport verify(const Fixture &f) {
  ExactLinearHHybridFamilyVerifier verifier;
  ExecutionContext context;
  context.numerical = {0, 0};
  return take(verify_hybrid_portfolio_family(
      verifier, f.system, f.request, f.programs, f.candidates, {1, 4},
      HybridVerifierInvocation{context}));
}
} // namespace
TEST_CASE("exact H coverage aggregation preserves established and unsupported "
          "proofs") {
  auto f = fixture();
  CHECK(verify(f).complete_family_coverage ==
        HybridVerificationStatus::established);
  // The V point is the same mathematical singleton, outside this verifier's H
  // domain.
  f.candidates[0].relation = vertex_point(1);
  const auto unknown = verify(f);
  REQUIRE(unknown.branches.size() == 1);
  CHECK(unknown.branches[0].continuous_coverage ==
        HybridVerificationStatus::unsupported);
  CHECK(unknown.global_objective_optimality ==
        HybridVerificationStatus::established);
  CHECK(unknown.complete_family_coverage ==
        HybridVerificationStatus::unsupported);
}
TEST_CASE("exact H coverage keeps a proven face counterexample despite another "
          "unknown proof") {
  auto f = fixture(true);
  f.candidates[0].relation = vertex_point(3);
  f.candidates[1].relation = point({1, 0, 0});
  const auto result = verify(f);
  REQUIRE(result.branches.size() == 2);
  CHECK(result.branches[0].continuous_coverage ==
        HybridVerificationStatus::unsupported);
  CHECK(result.branches[1].continuous_coverage ==
        HybridVerificationStatus::refuted);
  CHECK(result.complete_family_coverage == HybridVerificationStatus::refuted);
}
TEST_CASE("exact H coverage distinguishes unknown from disproven program "
          "provenance") {
  auto f = fixture();
  f.programs[0].joint_relation = vertex_point(1);
  CHECK(verify(f).complete_family_coverage ==
        HybridVerificationStatus::unsupported);
  f.programs[0].joint_relation = point({1});
  f.candidates[0].relation = vertex_point(1);
  CHECK(verify(f).complete_family_coverage ==
        HybridVerificationStatus::refuted);
}
TEST_CASE("a disproven program refutes coverage even when another objective is "
          "unsupported") {
  auto f = fixture(true);
  // The raw relation has three coordinates; the augmented objective requires
  // four.
  f.programs[0].relation_limits.max_variables = 3;
  f.programs[1].joint_relation = point({1, 0, 0});
  const auto result = verify(f);
  CHECK(result.global_objective_optimality ==
        HybridVerificationStatus::unsupported);
  CHECK(result.complete_family_coverage == HybridVerificationStatus::refuted);
}

TEST_CASE("a proven suboptimal candidate refutes coverage across an unknown "
          "objective") {
  auto f = fixture(true, true);
  f.programs[0].relation_limits.max_variables = 3;
  const auto result = verify(f);
  REQUIRE(result.branches.size() == 3);
  CHECK(result.branches[2].objective_optimality ==
        HybridVerificationStatus::refuted);
  CHECK(result.branches[2].continuous_coverage ==
        HybridVerificationStatus::refuted);
  CHECK(result.global_objective_optimality ==
        HybridVerificationStatus::unsupported);
  CHECK(result.complete_family_coverage == HybridVerificationStatus::refuted);
}
