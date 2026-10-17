# A29 ordered QLPHULL Python 3 port

The active A29 driver and A30 membership helper are transcribed together.
Read [provenance](PROVENANCE.md) and [deviations](DEVIATIONS.md) before using
results.

With Python 3.13 and `numpy==2.3.2` available:

```sh
python tools/legacy-ports/A29/verify_sources.py
python -m unittest discover -s tools/legacy-ports/A29 -p test_port.py -v
python tools/legacy-ports/A29/port.py tools/legacy-ports/A29/fixtures/square.json
```

`verify_sources.py` needs owner-authorized access to the hash-matching local
archive and accepts `--archive-root PATH` for another authorized mount. The
port and tests do not read archived sources. Input JSON has a `points` array
of coordinate rows. The CLI emits one JSON record with algorithm status,
stage/reason, output if completed, source hashes, A30 call and pivot counts,
and independent quality status. A failed or inconclusive algorithm exits 2
after emitting the record. Exact quality checking supports at most 64 finite
2D input/output points; anything outside its scope is `inconclusive`.

The included square is synthetic, not a B03 input or old-versus-modern
comparison. This command does not benchmark the port.
