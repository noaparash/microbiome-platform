#!/usr/bin/env bash
# Time every tool on each dataset, one process per analysis, at most 60 minutes each.
# Usage: bash run_all.sh <python> <work folder> <results.jsonl> <dataset spec>...
#   dataset spec: name|counts|labels|metabolites (empty fields allowed)
# Each dataset gets a fresh cache, so its first analysis ("preprocess") pays MIPMLP;
# LOCATE's z-scored table is computed again (a different table).
set -u
PY=$1; WORK=$2; OUT=$3; shift 3
HERE=$(dirname "$0")
for spec in "$@"; do
  IFS='|' read -r name counts labels metabolites <<< "$spec"
  for goal in preprocess differ predict group metabolites; do
    args=(--counts "$counts")
    [ -n "$labels" ] && args+=(--labels "$labels")
    [ -n "$metabolites" ] && args+=(--metabolites "$metabolites")
    if [ "$goal" = metabolites ] && [ -z "$metabolites" ]; then continue; fi
    if [[ "$goal" =~ ^(differ|predict)$ ]] && [ -z "$labels" ]; then continue; fi
    timeout 3600 "$PY" -I "$HERE/time_tools.py" "$name" "$goal" "$WORK/$name/runs" "$WORK/$name/cache" "$OUT" "${args[@]}" \
      > "$WORK/$name-$goal.log" 2>&1
    code=$?
    peak=$(cat "$OUT.$name-$goal.peak" 2>/dev/null || echo null)  # saved every 10 s by time_tools.py
    if [ $code -eq 124 ]; then
      echo "{\"dataset\": \"$name\", \"goal\": \"$goal\", \"status\": \"time-out (over 60 min)\", \"peak_memory_gb\": $peak}" >> "$OUT"
    elif [ $code -ne 0 ]; then
      echo "{\"dataset\": \"$name\", \"goal\": \"$goal\", \"status\": \"crashed (exit $code)\", \"peak_memory_gb\": $peak}" >> "$OUT"
    fi
    rm -f "$OUT.$name-$goal.peak"
    tail -1 "$WORK/$name-$goal.log"
  done
done
