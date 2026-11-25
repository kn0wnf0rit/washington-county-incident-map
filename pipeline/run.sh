#!/usr/bin/env bash
# Full rebuild: fetch weekly CSVs -> clean/dedupe -> geocode -> write index.html + data/ into the repo root.
set -euo pipefail
cd "$(dirname "$0")"
python3 fetch.py "${1:-00000000}"
python3 clean.py
python3 geocode_county.py osm_county.txt > build/geocode.log 2>&1 || { tail -5 build/geocode.log; exit 1; }
tail -3 build/geocode.log
python3 build_site.py ../
