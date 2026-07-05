#!/usr/bin/env bash
# ROAScast full submission QA — mimics the grader end-to-end, then validates.
# Usage: bash scripts/full_submission_test.sh
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
cd "$ROOT"

# Pick a working interpreter (same probe as run.sh).
PY=""
for cand in python3 python; do
  if command -v "$cand" >/dev/null 2>&1 && "$cand" -c "import sys" >/dev/null 2>&1; then
    PY="$cand"; break
  fi
done
[ -z "$PY" ] && { echo "FAIL: no working python"; exit 1; }

fail() { echo; echo "=================== FULL SUBMISSION TEST: FAIL ==================="; echo "reason: $1"; exit 1; }

# 1-3) fresh state
rm -rf output
rm -f features.parquet features.csv
mkdir -p output

# 4) the exact grader command
bash run.sh ./data ./pickle/model.pkl ./output/predictions.csv \
  || fail "run.sh exited non-zero"

# 6) output exists
[ -s ./output/predictions.csv ] || fail "output/predictions.csv missing or empty"

# 7) deep validation
"$PY" scripts/validate_submission.py ./output/predictions.csv --data-dir ./data \
  || fail "predictions.csv failed validation"

# freshness: second run must overwrite, not append
LINES1=$(wc -l < ./output/predictions.csv)
bash run.sh ./data ./pickle/model.pkl ./output/predictions.csv >/dev/null 2>&1 \
  || fail "second run.sh invocation failed"
LINES2=$(wc -l < ./output/predictions.csv)
[ "$LINES1" -eq "$LINES2" ] || fail "output appended, not overwritten ($LINES1 -> $LINES2 lines)"

echo
echo "=================== FULL SUBMISSION TEST: PASS ==================="
echo "rows (incl. header): $LINES2  |  output: ./output/predictions.csv"
