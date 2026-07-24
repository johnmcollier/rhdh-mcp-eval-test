#!/usr/bin/env bash
# Detached, parallel, crash-hardened scoring for all 6 models.
# Safe to close Cursor after this starts (nohup).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PYTHONUNBUFFERED=1
export GOOGLE_APPLICATION_CREDENTIALS="${GOOGLE_APPLICATION_CREDENTIALS:-$HOME/.config/gcloud/application_default_credentials.json}"
export GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT:-rhdh-ai}"
export VERTEXAI_PROJECT="${VERTEXAI_PROJECT:-rhdh-ai}"
export VERTEXAI_LOCATION="${VERTEXAI_LOCATION:-us-central1}"
if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  OPENAI_API_KEY="$(python3 -c "print(open('$HOME/Documents/openai-token.txt').read().strip())")"
  export OPENAI_API_KEY
fi

EVAL_BIN="${EVAL_BIN:-$HOME/git/lightspeed-evaluation/.venv/bin/lightspeed-eval}"
SYSTEM_CONFIG="$ROOT/config/system-offline-tool-and-judge.yaml"
LOGDIR=/tmp/mcp-score-models
MASTER_LOG=/tmp/mcp-score.log
# 99 turns × 3 metrics (tool_eval + answer_correctness + faithfulness)
EXPECTED=297
# Run this many models concurrently (each already uses max_threads: 50)
MODEL_PARALLEL="${MODEL_PARALLEL:-3}"

mkdir -p "$LOGDIR"
: >"$MASTER_LOG"

score_one() {
  local m="$1"
  local log="$LOGDIR/${m}.log"
  echo "===== START $m $(date +%H:%M:%S) =====" | tee -a "$MASTER_LOG"
  rm -f "$ROOT/evaluation-result/$m/${m}_summary.json" \
        "$ROOT/evaluation-result/$m/${m}_summary.txt"
  rm -f "$ROOT/evaluation-result/$m"/evaluation_*_summary.json \
        "$ROOT/evaluation-result/$m"/evaluation_*_summary.txt \
        "$ROOT/evaluation-result/$m"/evaluation_*_detailed.csv
  set +e
  "$EVAL_BIN" \
    --system-config "$SYSTEM_CONFIG" \
    --eval-data "$ROOT/evaluation-result/$m/evaluation_dataset.yaml" \
    --output-dir "$ROOT/evaluation-result/$m" \
    >"$log" 2>&1
  local ec=$?
  set -e
  echo "===== EXIT $ec $m $(date +%H:%M:%S) =====" | tee -a "$MASTER_LOG"
  local latest
  latest="$(ls -t "$ROOT/evaluation-result/$m"/evaluation_*_summary.json 2>/dev/null | head -1 || true)"
  if [[ -n "$latest" ]]; then
    local base="${latest%_summary.json}"
    cp "${base}_summary.json" "$ROOT/evaluation-result/$m/${m}_summary.json"
    cp "${base}_summary.txt" "$ROOT/evaluation-result/$m/${m}_summary.txt"
    local n
    n="$(python3 -c "import json; print(json.load(open('${base}_summary.json')).get('total_evaluations',0))")"
    if (( n >= EXPECTED )); then
      echo "OK $m total=$n" | tee -a "$MASTER_LOG"
    else
      echo "INCOMPLETE $m total=$n need=$EXPECTED" | tee -a "$MASTER_LOG"
    fi
  else
    echo "NO_SUMMARY $m" | tee -a "$MASTER_LOG"
  fi
}

MODELS=(
  gpt-4o-mini
  gpt-5-mini
  gpt-5.5
  gemini-2.5-pro
  gemini-2.5-flash-lite
  llama-31-8b
)

i=0
n=${#MODELS[@]}
while (( i < n )); do
  pids=()
  for (( j=0; j<MODEL_PARALLEL && i+j<n; j++ )); do
    m="${MODELS[$((i+j))]}"
    score_one "$m" &
    pids+=("$!")
  done
  for pid in "${pids[@]}"; do
    wait "$pid" || true
  done
  i=$((i + MODEL_PARALLEL))
done

echo "SCORE_CAMPAIGN_DONE $(date +%H:%M:%S)" | tee -a "$MASTER_LOG"

# Write a one-line status digest
python3 - <<'PY' | tee -a "$MASTER_LOG"
import json
from pathlib import Path
root = Path("/Users/jcollier/git/rhdh-mcp-evaluation/evaluation-result")
for m in ["gpt-4o-mini","gpt-5-mini","gpt-5.5","gemini-2.5-pro","gemini-2.5-flash-lite","llama-31-8b"]:
    p = root / m / f"{m}_summary.json"
    if not p.exists():
        print(f"DIGEST {m}: MISSING")
        continue
    d = json.loads(p.read_text())
    o = d["summary_stats"]["overall"]
    print(f"DIGEST {m}: {o['PASS']}/{o['TOTAL']} ({o['pass_rate']:.1f}%)")
PY
