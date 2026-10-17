# A33 constrained QLPHULL Python 3 port

This is the active A33 driver plus A16 and the constrained sibling
`Modified_SM` helper, transcribed to Python 3. Read [provenance](PROVENANCE.md)
and [deviations](DEVIATIONS.md) before using its output.

With Python 3.13 and `numpy==2.3.2` available:

```sh
python tools/legacy-ports/A33/verify_sources.py
python -m unittest discover -s tools/legacy-ports/A33 -p test_port.py -v
python tools/legacy-ports/A33/port.py tools/legacy-ports/A33/fixtures/square.json
```

The verifier requires owner-authorized access to the hash-matching archive.
Use `--archive-root PATH` if mounted elsewhere; tests and the port do not need
the archive. The input JSON has a `points` array of coordinate rows. The CLI
emits one JSON record with `algorithm_status` (`completed`, `failed`, or
`inconclusive`), stage/reason, the source's `itrt`, separate helper counts and
observed pivots, output points if completed, and independent `quality` status
(`verified`, `incorrect`, or `inconclusive`). A noncompleted algorithm exits 2
after emitting its record. The quality oracle permits at most 64 finite 2D
input/output points; beyond that it reports `inconclusive`.

The included square is a deterministic dyadic synthetic input, not a B03
reproduction or performance workload. Nothing in this directory runs an
old-versus-new comparison or a benchmark.
