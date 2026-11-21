#!/usr/bin/env bash
set -euo pipefail
d=$(realpath "$(dirname "$0")")
out="$d/$1"
mkdir "$out"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
{
date -u
uname -m
c++ --version | head -1
sha256sum "$d/build/catalogue_episode" "$d/catalogue_episode.cpp"
} > "$out/environment.txt"
for n in $(seq 1 35); do
  if timeout --signal=TERM --kill-after=5s 60s prlimit --as=2147483648 -- \
      "$d/build/catalogue_episode" "$n" > "$out/$n.json" 2> "$out/$n.stderr"; then
    rc=0
  else
    rc=$?
  fi
  printf '%s\n' "$rc" > "$out/$n.exit"
done
