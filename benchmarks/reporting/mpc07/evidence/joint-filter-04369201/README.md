# MPC07 joint diagonal-filter evidence

Capture source `04369201`, separately reused native public-CSL ConvexPort bridge
source `b3978a98`, SHA256 266e1cda61b064b4603ff6499d76dc4db59106e4e673905f585c54caafa9c533.
All 72 exact reconstructed policies verify: 12 warmups and 60 measured attempts,
five alternating repetitions for each of four policies/filters at T=2/4/8.

JOINT-FILTER.md gives every physical matrix/bound, causal reconstruction,
scaled-response equality, uncertainty-vertex counterpart and exact lower/upper
proof. The figure shows the physical uncertainty strip inside the jointly
optimized filter versus the old fixed envelope, then selected terminal support
boxes and physical uncertainty vertices. It is not a full winning-set plot.

The source implements Chen v3 equations (24), (26), (36), (37)–(39) with a declared positive
block-diagonal filter and a scalar uncertain A entry. Position virtual filter
floor 1/1024 keeps the two-state filter invertible, while the actual position
forcing is zero. Model/controls/information match across classes. No author code
or unlicensed MATLAB/toolboxes/solver is adopted. The source audit's author code
pin `3f687329` and null license qualification remain unchanged. Full nondiagonal
filters, uncertainB, other dimensions and closed-loop/terminal conditions are
not implemented by this profile. No API/required dependency/library release.

For this special terminal-only toy, the joint virtual squared upper bound is
(65/64)^(2(T-1)); it attains the independently proved physical causal lower
bound. Fixed 5/4 filter values 9/4, 4, 9 are virtual-policy bounds, not physical lower
bounds. Every record separates virtual_profile_oracle_squared,
physical_unrestricted_lower_squared, and their two gaps. Prescribed-gain and
symmetry-optimal zero-input fixed-plan baselines remain separate restrictions.

LP variables at T=2/4/8 are 48/150/522, with 79/235/787 rows and 156/524/1908 nonzeros.
The free normalized H vector has T(T-1) coefficients (2/12/56), the diagonal
filter has 2T entries (4/8/16), and the explicit response has 2T(T+1) entries
(12/40/144), plus exact support auxiliaries. Baselines deliberately use the same
constrained skeleton, not minimal production implementations. Counts are exact
formulation dimensions; timings do not prove asymptotic runtime.

Performance verdict is inconclusive. Source/parse/registry setup, public-port
run, supervised process, Python preparation and exact checking stay distinct.
Native port run includes adapter checks, not an isolated LP or MPC-update
latency. A separate Python profile does not establish a native limiter or tuned
performance winner. Native resource/stop scopes remain the recorded POSIX
one-worker limits and Linux direct-child CPU/RSS accounting.

## Saved-data checks, no native binary

Verify outer SHA256SUMS, extract offline.zip into a fresh directory, enter
mpc07-joint-report and verify its SHA256SUMS. With an existing full source
checkout containing `04369201` and `b3978a98`, run:

```sh
python -B - <<'PY'
import sys
from pathlib import Path
sys.path.insert(0,'<FULL_SOURCE_CHECKOUT>/benchmarks/reporting/mpc07')
from report import checked_records,metrics
env,rows,policies,hashes=checked_records(Path('RAW'),repository=Path('<FULL_SOURCE_CHECKOUT>'))
print('checked rows',len(rows));print(metrics(rows))
PY
```

The standard-library checker requires POSIX Python and local Git objects;
archive hashes alone cannot authenticate a Git commit. -B prevents bytecode
writes in immutable sources. No native solve or integration is run. Replot from
that source checkout using the pinned Matplotlib 3.11.2 report environment and
report.py --capture <EXTRACT>/RAW --output <NEW>. No recorded absolute host path
is a portable command. The outer HTML only redirects the raw-data link to ZIP;
its original complete reading layer remains byte-preserved inside offline.zip.

## Retained earlier attempts and errata

Earlier-attempts.zip retains 12 WIP diagnostics and the full initial 72-attempt
0075400d capture. One original T8 gain response was rejected for a3.5e-18
numerical auxiliary difference; exact reconstruction now derives the response
from repaired H/filter and records the bounded native adjustment. Its raw result
was not altered. The initial `0075400d` capture then had a misleading derived field
physical_lower_oracle_squared for the class/virtual oracle. It is explicitly
superseded by the corrected fields above: native programs/values were unchanged,
and all its raw/check/source bytes remain archived. Those earlier records do
not enter the corrected 60 measured attempts. Independent review and root-owned
checked deployment remain pending; this does not close #603.
