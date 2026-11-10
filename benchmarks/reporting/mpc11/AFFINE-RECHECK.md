# Post-capture numerical affine recheck

The original pilot archives, plotted arrays, figure receipt and historical
checker snapshots remain unchanged. The publication manifest separately pins
the current affine/nonlinear checkers and their historical counterparts.

The original checker compared SHA-256 digests of independently recomputed
floating coefficients. With the same locked NumPy/SciPy wheels and unchanged
fuel archive, selecting OpenBLAS Sandybridge instead of Haswell changes 84
recomputed values, by at most 1.1102230246251565e-16. The original digest check
rejects that otherwise unchanged experiment. These digests identify stored
bytes; they do not establish portable floating derivation equality.

The current checker preserves exact stored file, submitted-program, model and
result identity hashes. It independently rebuilds the authored model and checks
its numerical values with absolute tolerance 1e-13 and relative tolerance
1e-12. Keys, shapes, integer indices, strings and declared transformations still
match exactly. It then rebuilds each program/transform from the authenticated
saved inputs, with the same numerical comparison for floating derivations.
Derived program hash fields are checked by the stored-identity layer rather
than compared to a hash of potentially different floating rounding.

The nonlinear reader also checks the recomputed affine witness numerically
against its exactly bound saved witness, then uses the saved identity for trace
association. Under Sandybridge, 27 LV replay entries differ by at most
2.842170943040401e-14; the physical state/control witness identity is unchanged.
Recomputed sampled metrics use the same tolerance. The original witness/trace
bytes, request associations and statuses remain unchanged. Every consumed
submitted, joint or unscaled program validates its own exact canonical hash
before any floating comparison.

This is a numerical model/transform consistency check, not an exact arithmetic
proof or a certified matrix-exponential error bound. Existing numerical witness,
replay, objective and stationarity checks retain their separate scopes. The
publication additionally pins every original archive and plotted value exactly;
no tolerance permits replacing those bytes. Tests retain rejection of rebound
model declarations, objective/row/bound changes and incorrect variable maps,
and exercise the unchanged original archive under a different BLAS kernel.

No solver/integrator rerun, new numerical result, required dependency, public API
or library release is introduced. The optional Linux CPython wheel lock remains
unchanged.

The publication checks case identities, statuses, completed counts and original
objectives against the frozen figure receipt. Current NMPC numerical diagnostic
arrays and rebuild residuals are checked by the actual saved checker and recorded
separately in the CI checking log. The qualified premerge job retains that log
as a source/run-bound Actions artifact for 30 days; publisher logs retain their
own checking evidence. Host-specific diagnostics never enter immutable Pages
bytes or route identity. They are not required to reproduce the
historical diagnostic bits. The original receipt, sampled histories and plotted
arrays retain exact byte/value binding. Nonfinite or negative current diagnostics
and changed identities, status, counts or materially different objectives refuse
publication.
