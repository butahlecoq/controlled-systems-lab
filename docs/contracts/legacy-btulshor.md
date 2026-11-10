# Source-faithful BTULSHOR geometry routines

`CSL::legacy_btulshor` exposes a C++ translation of the REACH, KPABEP and MODIF
procedures identified by source SHA-256
`06fa90d5977ab49174abbf866899000f511fad46eac4a1e72388bbe27090a442`. It keeps
the procedures' operation order, strict comparisons, first-winner ties, phase
changes, `1e-5` KPABEP tolerance and `1E11` ratio sentinel. The port uses
binary64 `double`; it does not claim historical compiler bit identity.

Results preserve the raw source p status. MODIF status 1, 2 or 3 describes the
source routine's branch outcome; a `Stopped` result instead describes malformed
input, resource bounds, nonfinite arithmetic, exhausted pivot budget or an
invalid injected dependency. Status 3 is not reinterpreted as a hull failure or
success certificate. In KPABEP, status 2 triggers the source retain/swap branch.
The separate source fallback retains the first point when `l=0` and `j=2`.
Empty KPABEP input is handled at the wrapper boundary without invoking the
original routine.

The source routines own their storage conventions. MODIF copies its input matrix
and vector, and KPABEP/REACH operate on private arrays. REACH uses an `n` stride
for BEP while primitive controls contain `nr` coordinates; it pads the private
array and refuses `nr > n`, which the literal source layout cannot represent.
All matrix requests at the public boundary are row-major. Retained indices and
reach source records track original caller entries through source compactions.

The `ModifPort` and `KpabepPort` arguments allow callers to substitute either
routine explicitly. Port identities are caller-owned strings. Injected results
are checked for dimensions and valid source statuses before the dependent
routine uses them. Optional traces are bounded and truncation does not change
numerical decisions.

This module is a raw numerical routine for comparison and reproduction. It does
not provide an exact hull certificate, a modern LP adapter, or post-result
repair. The Pascal source and private extraction tooling are not redistributed.

## Delivery impact

This adds a public C++ header and a separately linkable static CMake target. It
adds no runtime or build dependency and installs the contract with the existing
geometry documentation. Release/package preparation should record the new
`CSL::legacy_btulshor` target and installed header; no registry package is
needed for a CMake library.
