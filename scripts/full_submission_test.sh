#!/usr/bin/env bash
# ROAScast FULL submission QA — mimics the grader end-to-end, many ways.
# Usage: bash scripts/full_submission_test.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
cd "$ROOT"
echo "[qa] repo root : $ROOT"

# Pick a working interpreter (same probe as run.sh).
PY=""
for cand in python3 python; do
  if command -v "$cand" >/dev/null 2>&1 && "$cand" -c "import sys" >/dev/null 2>&1; then
    PY="$cand"; break
  fi
done
[ -z "$PY" ] && { echo "FAIL: no working python"; exit 1; }
echo "[qa] python    : $("$PY" --version 2>&1)"

fail() { echo; echo "=============== FULL SUBMISSION TEST: FAIL ==============="; echo "reason: $1"; exit 1; }
step() { echo; echo "--- $1"; }

step "clean old outputs"
rm -rf output tmp_test_output
rm -f features.parquet features.csv

step "model loading test"
"$PY" - <<'PYEOF'
import sys, os
sys.path.insert(0, "src")
import joblib
model = joblib.load("pickle/model.pkl")
print(type(model))
print("MODEL_LOAD_PASS")
PYEOF

step "explicit argument test"
bash run.sh ./data ./pickle/model.pkl ./output/predictions.csv || fail "explicit-arg run"
"$PY" scripts/validate_submission.py ./output/predictions.csv || fail "explicit-arg validation"

step "default argument test"
rm -rf output
bash run.sh || fail "default-arg run"
"$PY" scripts/validate_submission.py ./output/predictions.csv || fail "default-arg validation"

step "custom output path test"
rm -rf tmp_test_output
bash run.sh ./data ./pickle/model.pkl ./tmp_test_output/custom_predictions.csv \
  || fail "custom-output run"
"$PY" scripts/validate_submission.py ./tmp_test_output/custom_predictions.csv \
  || fail "custom-output validation"
rm -rf tmp_test_output

step "output freshness test (no append)"
bash run.sh ./data ./pickle/model.pkl ./output/predictions.csv >/dev/null
first_count=$(wc -l < ./output/predictions.csv)
bash run.sh ./data ./pickle/model.pkl ./output/predictions.csv >/dev/null
second_count=$(wc -l < ./output/predictions.csv)
[ "$first_count" -eq "$second_count" ] \
  || fail "append detected: $first_count -> $second_count lines"
echo "rows stable at $second_count lines across reruns"

step "no API key test"
rm -rf output
env -u OPENAI_API_KEY -u GEMINI_API_KEY -u GROQ_API_KEY \
    -u ANTHROPIC_API_KEY -u OLLAMA_HOST \
  bash run.sh ./data ./pickle/model.pkl ./output/predictions.csv \
  || fail "keyless run"
"$PY" scripts/validate_submission.py ./output/predictions.csv || fail "keyless validation"

step "dynamic data folder test"
DDIR="${TMPDIR:-/tmp}/roascast_data_test"
rm -rf "$DDIR"; mkdir -p "$DDIR"
cp data/*.csv "$DDIR/"
rm -rf output
bash run.sh "$DDIR" ./pickle/model.pkl ./output/predictions.csv || fail "dynamic-dir run"
"$PY" scripts/validate_submission.py ./output/predictions.csv --data-dir "$DDIR" \
  || fail "dynamic-dir validation"
rm -rf "$DDIR"

step "stability: run the judge command 5 times"
for i in 1 2 3 4 5; do
  rm -rf output
  bash run.sh ./data ./pickle/model.pkl ./output/predictions.csv >/dev/null \
    || fail "flaky failure on run $i"
  "$PY" scripts/validate_submission.py ./output/predictions.csv >/dev/null \
    || fail "flaky validation failure on run $i"
  echo "run $i/5: OK"
done

echo
echo "=============== FINAL SUBMISSION TEST PASS ==============="
echo "judge command verified: ./run.sh ./data ./pickle/model.pkl ./output/predictions.csv"
