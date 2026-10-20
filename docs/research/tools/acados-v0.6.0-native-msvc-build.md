# acados v0.6.0 native MSVC build recipe

Status: the build and OCP-QP smoke check passed on the Windows build host on 2026-10-20. This is not a benchmark or an integration dependency. An initial direct compile used `/MD` and emitted `LNK4098`; after matching the pinned acados Release runtime with `/MT`, the compile and solve were rerun successfully with no linker warning. The repository change is documentation only.

## Pinned source

The checkout used the exact upstream release commit `503364817c872d474ab5bed219c26760ac267769` (release v0.6.0), detached, with every recursive Git submodule checked out at the gitlink recorded by that commit. No acados or submodule source file was edited. After configure and build, `git status --short` in the acados checkout was empty.

Key submodule revisions observed:

| Submodule | Commit |
| --- | --- |
| `external/blasfeo` | `d6251233923c9b475fe894fb729fb63ab693e301` |
| `external/hpipm` | `e3a56c1caddd7f12d125d84f337b9a9e5c186271` |
| `external/hpmpc` | `da0f9791034cb09bb0904d73504e948d8ea4d0a5` |
| `external/daqp` | `dc13508052b658b97c672a8c223029fd9c0d42b5` |
| `external/osqp` | `0dd00a578cf1c2691c5c379965d504c75bf6cfad` |
| `external/qpdunes` | `4f5bdb4ff19a4a2896abe5bfd8fbde5710f34950` |
| `external/qpoases` | `125e94fa638f00350608871fc165789b1d1762f1` |
| `interfaces/acados_template/tera_renderer` | `a480a64b0a2cc15d4b1e6146e986388709ac0716` |

The other recursive submodules (`examples/acados_python/tests/test_data`, `external/Clarabel.cpp` and its `Clarabel.rs` child, `external/catch`, and `external/jsonlab`) were also initialized at the pinned gitlinks. The optional QP solver libraries were present in the checkout but disabled in the acados configuration below.

## Host and toolchain

- Windows build 22631, x64.
- Visual Studio 2022 Community, MSBuild 17.14.19, MSVC x64 compiler 19.44.35215.0.
- CMake 3.31.6 (`CMake 3.31.6-msvc6`), Visual Studio generator `Visual Studio 17 2022`, platform `x64`.
- Release configuration, static libraries, generic BLASFEO and HPIPM targets, OpenMP off.
- No WSL or Docker fallback was used.

The pinned installation guide describes its native MSVC workflow as preliminary and lists Visual Studio 2017 and 2019. This run used the installed Visual Studio 2022 toolchain instead; it validates this exact host/toolchain combination only.

## Clean checkout and configure

Use paths without spaces for the scratch checkout, build and install directories. From PowerShell:

```powershell
$ErrorActionPreference = 'Stop'
$acadosRoot = 'D:\work\PhD\builds\acados-v0.6.0-source'
$buildDir = 'D:\work\PhD\builds\acados-v0.6.0-build'
$installDir = 'D:\work\PhD\builds\acados-v0.6.0-install'
$cmake = 'C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe'

git clone https://github.com/acados/acados.git $acadosRoot
git -C $acadosRoot checkout --detach 503364817c872d474ab5bed219c26760ac267769
git -C $acadosRoot submodule update --init --recursive

& $cmake -S $acadosRoot -B $buildDir -G 'Visual Studio 17 2022' -A x64 `
  "-DACADOS_INSTALL_DIR=$installDir" `
  -DBUILD_SHARED_LIBS=OFF `
  -DBLASFEO_TARGET=GENERIC `
  -DHPIPM_TARGET=GENERIC `
  -DACADOS_WITH_OPENMP=OFF `
  -DACADOS_WITH_QPOASES=OFF `
  -DACADOS_WITH_DAQP=OFF `
  -DACADOS_WITH_HPMPC=OFF `
  -DACADOS_WITH_QPDUNES=OFF `
  -DACADOS_WITH_OSQP=OFF `
  -DACADOS_WITH_CLARABEL=OFF `
  -DACADOS_WITH_QORE=OFF `
  -DACADOS_WITH_OOQP=OFF `
  -DACADOS_EXAMPLES=OFF `
  -DACADOS_UNIT_TESTS=OFF
if ($LASTEXITCODE -ne 0) { throw 'acados configure failed' }

& $cmake --build $buildDir --target acados --config Release --parallel 4
if ($LASTEXITCODE -ne 0) { throw 'acados Release build failed' }
```

The configure output should identify MSVC 19.44, Windows x64, Release, `BLASFEO_TARGET=GENERIC`, `HPIPM_TARGET=GENERIC`, static libraries, OpenMP off, and the requested install directory. The command builds the core `acados` target and its required BLASFEO and HPIPM dependencies; it does not build or install optional solver integrations.

## OCP-QP smoke solve

The unmodified upstream C example `examples/c/ocp_qp.c` directly exercises `ocp_qp_solve` with `FULL_CONDENSING_HPIPM`. Its CMake target is inside an `if(NOT CMAKE_CXX_COMPILER_ID MATCHES "MSVC")` block in the pinned `examples/c/CMakeLists.txt`, so it is not generated for this native compiler. To keep the upstream source unchanged and still exercise the supported OCP-QP API, compile that source directly against the just-built static libraries:

```powershell
$smokeDir = Join-Path $buildDir 'smoke'
New-Item -ItemType Directory -Path $smokeDir -Force | Out-Null
$vsDevCmd = 'C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\VsDevCmd.bat'

$compile = 'call "' + $vsDevCmd + '" -no_logo -arch=x64 -host_arch=x64 >nul && ' +
  'cl /nologo /O2 /MT /Fo"' + $smokeDir + '\ocp_qp.obj" ' +
  '/I"' + $acadosRoot + '" ' +
  '/I"' + $acadosRoot + '\interfaces" ' +
  '/I"' + $acadosRoot + '\external" ' +
  '/I"' + $acadosRoot + '\external\hpipm\include" ' +
  '/I"' + $acadosRoot + '\external\blasfeo\include" ' +
  '/Fe"' + $smokeDir + '\ocp_qp.exe" ' +
  '"' + $acadosRoot + '\examples\c\ocp_qp.c" ' +
  '"' + $buildDir + '\acados\Release\acados.lib" ' +
  '"' + $buildDir + '\external\hpipm\Release\hpipm.lib" ' +
  '"' + $buildDir + '\external\blasfeo\Release\blasfeo.lib"'

& cmd.exe /d /c $compile
if ($LASTEXITCODE -ne 0) { throw 'OCP-QP smoke compile failed' }
& (Join-Path $smokeDir 'ocp_qp.exe')
if ($LASTEXITCODE -ne 0) { throw 'OCP-QP smoke solve failed' }
```

Observed result on the recorded host:

- The corrected compile and executable exit codes were both zero. The example prints a failure message and exits with status 1 if `ocp_qp_solve` returns anything other than `ACADOS_SUCCESS` (defined as zero); no failure message appeared.
- Solver: full-condensing HPIPM; reported QP iterations: 3.
- Infinity-norm residuals: stationarity `2.819966e-13`, dynamics `0`, inequality `3.330669e-15`, complementarity `8.785453e-15`.

The example prints timing fields, but this recipe makes no performance claim and does not use them as evidence.

The `/MT` option matches the pinned top-level CMake file, which appends `/MT` to the C and C++ Release flags under MSVC. The first `/MD` compile emitted linker warning `LNK4098`; the corrected `/MT` compile was rerun, completed with exit code zero and emitted no linker warning.

## Deviations and limits

- The installed acados documentation for v0.6.0 calls the MSVC route preliminary and documents VS 2017/2019. This run used VS 2022. It proves a successful build and smoke solve for the recorded configuration, not general Windows support.
- The upstream CMake example target is excluded under MSVC. The example source itself was compiled unchanged with MSVC and linked to the Release static libraries; no CMake or acados source modifications were made.
- Only the core acados, BLASFEO and HPIPM libraries required by the smoke solve were built. Optional QP solvers, unit tests, MATLAB/Octave interfaces and Python interfaces were not built or tested.
- The separate install prefix was configured but `INSTALL` was not run; the smoke executable linked the build-tree libraries.
- The smoke solve is a functionality check only. It does not validate all OCP-QP dimensions, solvers or platform configurations.

## Sources checked on 2026-10-20

- [acados v0.6.0 release and pinned commit](https://github.com/acados/acados/releases/tag/v0.6.0).
- [Pinned v0.6.0 installation guide](https://github.com/acados/acados/blob/503364817c872d474ab5bed219c26760ac267769/docs/installation/index.md), including its preliminary native MSVC workflow and compiler notes.
- [Pinned OCP-QP C example](https://github.com/acados/acados/blob/503364817c872d474ab5bed219c26760ac267769/examples/c/ocp_qp.c), which selects full-condensing HPIPM, checks the solver return code and prints residuals.
- [Pinned C examples CMake configuration](https://github.com/acados/acados/blob/503364817c872d474ab5bed219c26760ac267769/examples/c/CMakeLists.txt), which excludes that target for MSVC.
- [Pinned acados CMake options and target configuration](https://github.com/acados/acados/blob/503364817c872d474ab5bed219c26760ac267769/CMakeLists.txt).
