#include <gmpxx.h>
#include <nlohmann/json.hpp>

#include <algorithm>
#include <array>
#include <cmath>
#include <fstream>
#include <iostream>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <utility>
#include <vector>

namespace {
using Json = nlohmann::json;
using Rational = mpq_class;
using Vector = std::vector<Rational>;
using Matrix = std::vector<Vector>;
constexpr std::size_t horizon = 3;
static_assert(std::numeric_limits<double>::is_iec559 &&
              std::numeric_limits<double>::digits == 53);

void require(bool condition, const char *message) {
  if (!condition)
    throw std::runtime_error(message);
}

Rational exact(const Json &entry) {
  const auto value = entry.get<double>();
  require(std::isfinite(value), "expected finite binary64 input");
  return Rational(value);
}

Vector decode_vector(const Json &input) {
  Vector output;
  for (const auto &entry : input)
    output.push_back(exact(entry));
  return output;
}

Matrix decode_matrix(const Json &input) {
  const auto rows = input.at("rows").get<std::size_t>();
  const auto cols = input.at("cols").get<std::size_t>();
  const auto values = decode_vector(input.at("values"));
  require(values.size() == rows * cols, "matrix shape mismatch");
  Matrix output(rows, Vector(cols));
  auto source = values.begin();
  for (auto &row : output)
    for (auto &value : row)
      value = *source++;
  return output;
}

Json encode(const Vector &input) {
  auto result = Json::array();
  for (const auto &entry : input)
    result.push_back(entry.get_str());
  return result;
}

Rational dot(const Vector &a, const Vector &b) {
  require(a.size() == b.size(), "dot product dimension mismatch");
  Rational result;
  for (std::size_t i = 0; i < a.size(); ++i)
    result += a[i] * b[i];
  return result;
}

Vector image(const Matrix &A, const Vector &x) {
  Vector result;
  for (const auto &row : A)
    result.push_back(dot(row, x));
  return result;
}

Matrix transpose(const Matrix &A) {
  require(!A.empty(), "empty matrix");
  Matrix result(A.front().size(), Vector(A.size()));
  for (std::size_t i = 0; i < A.size(); ++i)
    for (std::size_t j = 0; j < result.size(); ++j)
      result[j][i] = A[i][j];
  return result;
}

Vector add(Vector a, const Vector &b) {
  require(a.size() == b.size(), "vector sum dimension mismatch");
  for (std::size_t i = 0; i < a.size(); ++i)
    a[i] += b[i];
  return a;
}

class Factorization {
  Matrix lu;
  std::vector<std::size_t> row_order;
  bool nonsingular_{true};

public:
  explicit Factorization(Matrix A) : lu(std::move(A)), row_order(lu.size()) {
    require(
        std::all_of(lu.begin(), lu.end(),
                    [&](const auto &row) { return row.size() == lu.size(); }),
        "expected square transition matrix");
    std::iota(row_order.begin(), row_order.end(), std::size_t{0});
    for (std::size_t k = 0; k < lu.size(); ++k) {
      auto pivot = k;
      while (pivot < lu.size() && lu[pivot][k] == 0)
        ++pivot;
      if (pivot == lu.size()) {
        nonsingular_ = false;
        return;
      }
      std::swap(lu[k], lu[pivot]);
      std::swap(row_order[k], row_order[pivot]);
      for (std::size_t i = k + 1; i < lu.size(); ++i) {
        if (lu[i][k] == 0)
          continue;
        lu[i][k] /= lu[k][k];
        for (std::size_t j = k + 1; j < lu.size(); ++j)
          if (lu[k][j] != 0)
            lu[i][j] -= lu[i][k] * lu[k][j];
      }
    }
  }

  bool nonsingular() const { return nonsingular_; }

  Vector solve(const Vector &rhs) const {
    require(nonsingular_ && rhs.size() == lu.size(), "invalid linear solve");
    Vector x(rhs.size());
    for (std::size_t i = 0; i < x.size(); ++i) {
      x[i] = rhs[row_order[i]];
      for (std::size_t j = 0; j < i; ++j)
        if (lu[i][j] != 0)
          x[i] -= lu[i][j] * x[j];
    }
    for (std::size_t i = x.size(); i-- > 0;) {
      for (std::size_t j = i + 1; j < x.size(); ++j)
        if (lu[i][j] != 0)
          x[i] -= lu[i][j] * x[j];
      x[i] /= lu[i][i];
    }
    return x;
  }
};

Vector direction(const Vector &left, const Vector &right, const Rational &a,
                 const Rational &b) {
  Vector result;
  for (std::size_t i = 0; i < left.size(); ++i)
    result.push_back(a * left[i] + b * right[i]);
  return result;
}

Json run(const Json &data) {
  const auto A = decode_matrix(data.at("A"));
  const auto B = decode_matrix(data.at("B"));
  const auto G = decode_matrix(data.at("G"));
  const auto offset = decode_vector(data.at("offset"));
  const auto initial = decode_vector(data.at("initial"));
  const auto plane = data.at("plane").get<std::array<std::size_t, 2>>();
  const Factorization primal(A), dual(transpose(A));
  Json result{{"schema", "csl.archived-exact-predecessor-certificate/1"},
              {"model_id", data.at("model_id")},
              {"plane", plane}};
  if (!primal.nonsingular() || !dual.nonsingular()) {
    result["status"] = "unsupported-singular-transition";
    return result;
  }
  require(data.at("external").size() == horizon, "forecast grid mismatch");
  const auto Bt = transpose(B);
  std::array<Vector, horizon + 1> center;
  std::array<Vector, horizon> drift;
  center[0] = initial;
  for (std::size_t k = 0; k < horizon; ++k) {
    drift[k] = add(offset, image(G, decode_vector(data.at("external").at(k))));
    center[k + 1] = add(image(A, center[k]), drift[k]);
  }
  Vector radius;
  for (const auto &value : center.back())
    radius.push_back(std::max(Rational{1}, Rational{abs(value)}) / 10);
  result["target_center"] = encode(center.back());
  result["target_radius"] = encode(radius);
  std::array<std::array<Vector, horizon + 1>, 2> basis;
  auto dual_basis = Json::array();
  for (std::size_t coord = 0; coord < basis.size(); ++coord) {
    auto &sequence = basis[coord];
    sequence[0] = Vector(initial.size());
    sequence[0].at(plane[coord]) = 1;
    auto encoded = Json::array({encode(sequence[0])});
    for (std::size_t j = 0; j < horizon; ++j) {
      sequence[j + 1] = dual.solve(sequence[j]);
      encoded.push_back(encode(sequence[j + 1]));
    }
    dual_basis.push_back(std::move(encoded));
  }
  result["dual_basis"] = std::move(dual_basis);
  auto samples = Json::array();
  for (const auto &input : data.at("full_history").at("samples")) {
    const auto k = input.at("stage").get<std::size_t>();
    require(k <= horizon, "invalid sample stage");
    const auto d = decode_vector(input.at("direction"));
    require(d.size() == 2, "expected planar direction");
    std::vector<Vector> actions(horizon - k);
    auto y =
        direction(basis[0][horizon - k], basis[1][horizon - k], d[0], d[1]);
    auto x = center.back();
    for (std::size_t i = 0; i < x.size(); ++i)
      x[i] += sgn(y[i]) * radius[i];
    for (std::size_t j = horizon; j > k; --j) {
      y = direction(basis[0][j - k], basis[1][j - k], d[0], d[1]);
      const auto c = image(Bt, y);
      auto &u = actions[j - k - 1];
      for (const auto &entry : c)
        u.emplace_back(-sgn(entry));
      const auto effect = add(drift[j - 1], image(B, u));
      for (std::size_t i = 0; i < x.size(); ++i)
        x[i] -= effect[i];
      x = primal.solve(x);
    }
    const Rational value = d[0] * x.at(plane[0]) + d[1] * x.at(plane[1]);
    auto inputs = Json::array();
    for (const auto &u : actions)
      inputs.push_back(encode(u));
    samples.push_back({{"stage", k},
                       {"direction", input.at("direction")},
                       {"support", value.get_str()},
                       {"state", encode(x)},
                       {"controls", std::move(inputs)}});
  }
  require(samples.size() == 32,
          "expected four stages with eight sampled directions");
  result["samples"] = std::move(samples);
  result["status"] = "certificate-candidate";
  return result;
}
} // namespace

int main(int argc, char **argv) try {
  require(argc == 2, "Usage: predecessor archived-model.json");
  std::ifstream source(argv[1]);
  require(static_cast<bool>(source), "cannot read source JSON");
  std::cout << run(Json::parse(source)).dump(2) << '\n';
} catch (const std::exception &error) {
  std::cerr << error.what() << '\n';
  return 1;
}
