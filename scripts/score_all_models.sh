#!/usr/bin/env bash
# Score all per-model evaluation datasets offline (tool_eval + judges).
# Runs two models in parallel; each lightspeed-eval process stays single-threaded
# (ragas faithfulness is not safe under ThreadPoolExecutor concurrency).
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
SYSTEM_CONFIG="${SYSTEM_CONFIG:-$ROOT/config/system-offline-tool-and-judge.yaml}"
LOGDIR="${LOGDIR:-/tmp/mcp-score-models}"
MASTER_LOG="${MASTER_LOG:-/tmp/mcp-score.log}"
mkdir -p "$LOGDIR"
: >"$MASTER_LOG"

score_one() {
  local m="$1"
  local log="$LOGDIR/$m.log"
  echo "===== START $m $(date +%H:%M:%S) =====" | tee -a "$MASTER_LOG"
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
    echo "COPIED $m summary total=$n" | tee -a "$MASTER_LOG"
  else
    echo "NO_SUMMARY $m" | tee -a "$MASTER_LOG"
  fi
  return "$ec"
}

MODELS=(
  gpt-4o-mini
  gpt-5-mini
  gpt-5.5
  gemini-2.5-pro
  gemini-2.5-flash-lite
  llama-31-8b
)

# Clean prior partial summaries
for m in "${MODELS[@]}"; do
  rm -f "$ROOT/evaluation-result/$m/${m}_summary.json" \
        "$ROOT/evaluation-result/$m/${m}_summary.txt"
  rm -f "$ROOT/evaluation-result/$m"/evaluation_*_summary.json \
        "$ROOT/evaluation-result/$m"/evaluation_*_summary.txt \
        "$ROOT/evaluation-result/$m"/evaluation_*_detailed.csv
done

i=0
n=${#MODELS[@]}
while (( i < n )); do
  pids=()
  for (( j=0; j<2 && i+j<n; j++ )); do
    m="${MODELS[$((i+j))]}"
    score_one "$m" &
    pids+=("$!")
  done
  for pid in "${pids[@]}"; do
    wait "$pid" || true
  done
  i=$((i + 2))
done

echo "SCORE_BATCH_DONE $(date +%H:%M:%S)" | tee -a "$MASTER_LOG"
