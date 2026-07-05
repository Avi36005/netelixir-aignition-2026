#!/usr/bin/env bash
# ROAScast scored core — single entry point for the grading pipeline.
# Runs end-to-end in ONE invocation: feature generation, then prediction.
# Fails loudly rather than emitting a bad output file.
set -euo pipefail

# Repo root, so the script works no matter the caller's CWD.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

# Three positional args with sensible defaults (runs locally with no args).
DATA_DIR="${1:-./data}"
MODEL_PATH="${2:-./pickle/model.pkl}"
OUTPUT_PATH="${3:-./output/predictions.csv}"

# Pick an available interpreter — grader environments vary. A candidate must
# actually EXECUTE (Windows ships a fake "python3" Store stub that fails).
PY=""
for cand in python3 python; do
  if command -v "$cand" >/dev/null 2>&1 && "$cand" -c "import sys" >/dev/null 2>&1; then
    PY="$cand"
    break
  fi
done
if [ -z "$PY" ]; then
  echo "ERROR: no working python interpreter found on PATH" >&2
  exit 1
fi

mkdir -p "$(dirname "$OUTPUT_PATH")"
FEATURES="$(dirname "$OUTPUT_PATH")/_features.parquet"

echo "[run.sh] data=$DATA_DIR  model=$MODEL_PATH  out=$OUTPUT_PATH"
echo "[run.sh] interpreter: $($PY --version 2>&1)"

# 1) Build the features the model expects from whatever is in DATA_DIR.
"$PY" "$ROOT/src/generate_features.py" --data-dir "$DATA_DIR" --out "$FEATURES"

# 2) Load the pickled model and write predictions.
"$PY" "$ROOT/src/predict.py" --features "$FEATURES" --model "$MODEL_PATH" --output "$OUTPUT_PATH"

echo "[run.sh] Done. Predictions written to $OUTPUT_PATH"
