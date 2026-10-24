#!/usr/bin/env bash
# Copy one file out of the production web component, verified by checksum.
#
#   tools/prod_fetch.sh /tmp/report.csv docs/v2/reports/report.csv
#
# `doctl apps console` silently drops output past roughly 16 KB in one
# session, so a big CSV printed with --out - arrives truncated. This instead
# gzips + base64-encodes the file inside production, pulls it back in 12 KB
# slices (one tools/prod_run.sh call each), reassembles it locally and
# compares the MD5 with production's. Any mismatch fails loudly; nothing is
# written to the destination unless the checksum matches.
set -euo pipefail

if [ $# -ne 2 ]; then
  echo "usage: tools/prod_fetch.sh <remote file> <local file>" >&2
  exit 64
fi
remote="$1"
dest="$2"
here="$(cd "$(dirname "$0")" && pwd)"
run() { bash "$here/prod_run.sh" "$1" 2>/dev/null; }

encoded="/tmp/.prod_fetch_$$.b64"
meta="$(run "test -f '$remote' || { echo MISSING; exit 1; }; md5sum < '$remote' | cut -c1-32; gzip -9c '$remote' | base64 -w0 > '$encoded'; wc -c < '$encoded'")"
if echo "$meta" | grep -q MISSING; then
  echo "prod_fetch: $remote does not exist in production" >&2
  exit 1
fi
want_md5="$(echo "$meta" | sed -n 1p | tr -d '[:space:]')"
total="$(echo "$meta" | sed -n 2p | tr -d '[:space:]')"
chunk=12000

tmp="$(mktemp)"
trap 'rm -f "$tmp" "$tmp.gz"' EXIT
start=1
while [ "$start" -le "$total" ]; do
  end=$((start + chunk - 1))
  part="$(run "cut -c ${start}-${end} '$encoded'" | tr -d '\r\n')"
  expected=$(( end > total ? total - start + 1 : chunk ))
  if [ "${#part}" -ne "$expected" ]; then
    echo "prod_fetch: slice ${start}-${end} came back with ${#part} chars, expected ${expected}" >&2
    exit 1
  fi
  printf '%s' "$part" >> "$tmp"
  start=$((end + 1))
done
run "rm -f '$encoded'" >/dev/null || true

base64 -d < "$tmp" > "$tmp.gz"
gunzip -c "$tmp.gz" > "$tmp"
got_md5="$(md5sum < "$tmp" | cut -c1-32)"
if [ "$got_md5" != "$want_md5" ]; then
  echo "prod_fetch: checksum mismatch (production $want_md5, local $got_md5); nothing written" >&2
  exit 1
fi
mkdir -p "$(dirname "$dest")"
cp "$tmp" "$dest"
echo "prod_fetch: $dest  $(wc -c < "$dest") bytes, md5 $got_md5 (matches production)"
