#!/usr/bin/env bash
# Score models until each has EXPECTED evaluations (99 turns × N metrics).
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
# 99 turns × 2 metrics (tool_eval + answer_correctness)
EXPECTED="${EXPECTED:-198}"
PARALLEL="${PARALLEL:-2}"
mkdir -p "$LOGDIR"
: >>"$MASTER_LOG"

is_complete() {
  local m="$1"
  local p="$ROOT/evaluation-result/$m/${m}_summary.json"
  [[ -f "$p" ]] || return 1
  python3 -c "import json,sys; sys.exit(0 if json.load(open('$p')).get('total_evaluations',0)>=$EXPECTED else 1)"
}

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
    echo "COPIED $m summary total=$n (need $EXPECTED)" | tee -a "$MASTER_LOG"
  else
    echo "NO_SUMMARY $m" | tee -a "$MASTER_LOG"
  fi
}

MODELS=("$@")
if [[ ${#MODELS[@]} -eq 0 ]]; then
  MODELS=(gpt-4o-mini gpt-5-mini gpt-5.5 gemini-2.5-pro gemini-2.5-flash-lite llama-31-8b)
fi

todo=()
for m in "${MODELS[@]}"; do
  if is_complete "$m"; then
    echo "SKIP complete $m" | tee -a "$MASTER_LOG"
  else
    todo+=("$m")
  fi
done

i=0
n=${#todo[@]}
echo "TODO ${n} models: ${todo[*]}" | tee -a "$MASTER_LOG"
while (( i < n )); do
  pids=()
  for (( j=0; j<PARALLEL && i+j<n; j++ )); do
    m="${todo[$((i+j))]}"
    score_one "$m" &
    pids+=("$!")
  done
  for pid in "${pids[@]}"; do
    wait "$pid" || true
  done
  i=$((i + PARALLEL))
done
echo "SCORE_REMAINING_DONE $(date +%H:%M:%S)" | tee -a "$MASTER_LOG"
