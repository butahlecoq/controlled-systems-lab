#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>
#include <Eigen/Dense>
#include <Highs.h>
#include <nlohmann/json.hpp>
#include <cmath>

namespace {
HighsModel one_variable(double lower, double upper, double cost) {
    HighsModel model;
    model.lp_.num_col_ = 1;
    model.lp_.num_row_ = 0;
    model.lp_.col_cost_ = {cost};
    model.lp_.col_lower_ = {lower};
    model.lp_.col_upper_ = {upper};
    model.lp_.a_matrix_.format_ = MatrixFormat::kColwise;
    model.lp_.a_matrix_.start_ = {0,0};
    return model;
}
void configure(Highs& solver) {
    REQUIRE(solver.setOptionValue("output_flag",false) == HighsStatus::kOk);
    REQUIRE(solver.setOptionValue("threads",1) == HighsStatus::kOk);
}
}

TEST_CASE("Eigen: affine map respects row-major neutral buffer and singular transitions") {
    const double a[] = {0,1,0,0};
    using RowMajor = Eigen::Matrix<double,2,2,Eigen::RowMajor>;
    Eigen::Map<const RowMajor> A(a);
    Eigen::Vector2d x(2,3), offset(4,5);
    Eigen::Vector2d next = A*x+offset;
    CHECK(next[0] == 7);
    CHECK(next[1] == 5);
    CHECK(A.fullPivLu().rank() == 1);
}
TEST_CASE("HiGHS LP: feasibility, optimum, infeasibility and unboundedness stay distinct") {
    Highs solver;
    configure(solver);
    auto model = one_variable(0,4,1);
    // x >= 2, min x => x=2, value=2.
    model.lp_.num_row_ = 1;
    model.lp_.row_lower_ = {2}; model.lp_.row_upper_ = {kHighsInf};
    model.lp_.a_matrix_.start_ = {0,1};
    model.lp_.a_matrix_.index_ = {0}; model.lp_.a_matrix_.value_ = {1};
    REQUIRE(solver.passModel(model) == HighsStatus::kOk);
    REQUIRE(solver.run() == HighsStatus::kOk);
    REQUIRE(solver.getModelStatus() == HighsModelStatus::kOptimal);
    CHECK(solver.getSolution().col_value[0] == doctest::Approx(2));
    CHECK(solver.getObjectiveValue() == doctest::Approx(2));
    // Same constraints, zero objective probes phase-I style feasibility without a basis requirement.
    model.lp_.col_cost_ = {0};
    REQUIRE(solver.passModel(model) == HighsStatus::kOk);
    REQUIRE(solver.run() == HighsStatus::kOk);
    REQUIRE(solver.getModelStatus() == HighsModelStatus::kOptimal);
    CHECK(solver.getSolution().col_value[0] >= 2-1e-8);
    CHECK(solver.getSolution().col_value[0] <= 4+1e-8);
    model.lp_.row_lower_ = {5};
    REQUIRE(solver.passModel(model) == HighsStatus::kOk);
    REQUIRE(solver.run() == HighsStatus::kOk);
    CHECK(solver.getModelStatus() == HighsModelStatus::kInfeasible);
    REQUIRE(solver.passModel(one_variable(0,kHighsInf,-1)) == HighsStatus::kOk);
    REQUIRE(solver.run() == HighsStatus::kOk);
    CHECK(solver.getModelStatus() == HighsModelStatus::kUnbounded);
}
TEST_CASE("HiGHS convex QP: PSD residual square retains minimizer; report original norm") {
    Highs solver;
    configure(solver);
    // ||[x-3, 4]||_2, x in [0,2]. Square: x^2-6x+25; Q=2.
    auto model = one_variable(0,2,-6);
    model.lp_.offset_ = 25;
    model.hessian_.dim_ = 1;
    model.hessian_.format_ = HessianFormat::kTriangular;
    model.hessian_.start_ = {0,1}; model.hessian_.index_ = {0}; model.hessian_.value_ = {2};
    REQUIRE(solver.passModel(model) == HighsStatus::kOk);
    REQUIRE(solver.run() == HighsStatus::kOk);
    REQUIRE(solver.getModelStatus() == HighsModelStatus::kOptimal);
    const double x = solver.getSolution().col_value[0];
    CHECK(x == doctest::Approx(2));
    CHECK(solver.getObjectiveValue() == doctest::Approx(17));
    CHECK(std::hypot(x-3,4) == doctest::Approx(4.123105625617661));
}
TEST_CASE("HiGHS semidefinite QP: flat coordinate does not imply unique optimizer") {
    Highs solver;
    configure(solver);
    HighsModel model;
    model.lp_.num_col_ = 2; model.lp_.num_row_ = 0;
    model.lp_.col_cost_ = {-2,0}; model.lp_.offset_ = 1;
    model.lp_.col_lower_ = {0,0}; model.lp_.col_upper_ = {2,1};
    model.lp_.a_matrix_.format_ = MatrixFormat::kColwise;
    model.lp_.a_matrix_.start_ = {0,0,0};
    model.hessian_.dim_ = 2; model.hessian_.format_ = HessianFormat::kTriangular;
    model.hessian_.start_ = {0,1,1}; model.hessian_.index_ = {0}; model.hessian_.value_ = {2};
    REQUIRE(solver.passModel(model) == HighsStatus::kOk);
    REQUIRE(solver.run() == HighsStatus::kOk);
    REQUIRE(solver.getModelStatus() == HighsModelStatus::kOptimal);
    CHECK(solver.getSolution().col_value[0] == doctest::Approx(1).epsilon(1e-6));
    CHECK(solver.getObjectiveValue() == doctest::Approx(0).epsilon(1e-6));
    // Analytical family is {1} x [0,1]. This probe tests one optimizer, not a family adapter.
}
TEST_CASE("HiGHS independent instances retain separate problems and results") {
    Highs first, second;
    configure(first); configure(second);
    REQUIRE(first.passModel(one_variable(1,2,1)) == HighsStatus::kOk);
    REQUIRE(second.passModel(one_variable(5,7,-1)) == HighsStatus::kOk);
    REQUIRE(first.run() == HighsStatus::kOk);
    REQUIRE(second.run() == HighsStatus::kOk);
    CHECK(first.getSolution().col_value[0] == doctest::Approx(1));
    CHECK(second.getSolution().col_value[0] == doctest::Approx(7));
    CHECK(first.getObjectiveValue() == doctest::Approx(1));
    CHECK(second.getObjectiveValue() == doctest::Approx(-7));
}
TEST_CASE("JSON: parse neutral authored values and reject malformed syntax") {
    auto j = nlohmann::json::parse(R"({"version":1,"initial":[0,2],"strategy":"joint"})");
    CHECK(j.at("initial").get<std::vector<double>>() == std::vector<double>{0,2});
    CHECK(j.at("strategy").get<std::string>() == "joint");
    CHECK_THROWS_AS(static_cast<void>(nlohmann::json::parse("{broken")), nlohmann::json::parse_error);
}
