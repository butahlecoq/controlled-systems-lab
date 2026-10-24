# Strategy A nominal linear exact profile: 2D example

Open [`index.html`](index.html) for the complete one-step 2D fixture, labelled
optimal-face plot, independently checkable answer, reproduction command and
assurance limits. [`records.json`](records.json) retains the complete inputs,
observed public result and source identity. This is a functional profile
example, not a timing report.

The example ran from installed package commit `8b94095edf6b14ba6f3d35e237293e639e48f0aa` in the isolated
consumer created by `installed_public_client`. The run returned objective 1
and a registry-verified complete optimal face `x+y=1`, `0<=x,y<=1`.

Regenerate from the repository root using the [example source](../../../examples/nominal_linear_exact_2d.cpp):

```sh
cmake --build build --target nominal_linear_exact_2d
./build/examples/nominal_linear_exact_2d
```

The verifier interprets finite binary64 values as exact dyadics and checks the
represented problem. Numerical forward geometry and optimization providers
are not certified; validated arithmetic, generic family coverage and
performance are not claimed.
