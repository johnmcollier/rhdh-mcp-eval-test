#!/usr/bin/env bash
# Run full RHIDP-14578 multi-model MCP campaign (traces + offline scoring).
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
LS_EVAL="${LIGHTSPEED_EVAL:-$HOME/git/lightspeed-evaluation}"
EVAL_BIN="${LS_EVAL}/.venv/bin/lightspeed-eval"
PY="${REPO}/.venv/bin/python"

export MCP_URL="${MCP_URL:-http://localhost:7007/api/mcp-actions/v1}"
export MCP_TOKEN="${MCP_TOKEN:-password}"
export GOOGLE_APPLICATION_CREDENTIALS="${GOOGLE_APPLICATION_CREDENTIALS:-$HOME/.config/gcloud/application_default_credentials.json}"
export GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT:-rhdh-ai}"
export VERTEXAI_PROJECT="${VERTEXAI_PROJECT:-rhdh-ai}"
export VERTEXAI_LOCATION="${VERTEXAI_LOCATION:-us-central1}"
export OPENAI_API_KEY="${OPENAI_API_KEY:-$(tr -d '\n' < "$HOME/Documents/openai-token.txt")}"

LLAMA_BASE="${LLAMA_BASE:-https://meta-llama-31-8b-3scale-apicast-production.apps.rosa.redhat-ai-dev.m6no.p3.openshiftapps.com:443}"

if [[ ! -x "$EVAL_BIN" ]]; then
  echo "lightspeed-eval not found at $EVAL_BIN" >&2
  exit 1
fi

trace() {
  local provider="$1" model="$2" model_dir="$3"
  shift 3
  echo "======== TRACE $model_dir ($provider / $model) ========"
  "$PY" "$REPO/scripts/generate_traces.py" \
    --provider "$provider" \
    --model "$model" \
    --model-dir "$model_dir" \
    --eval-data "$REPO/dataset/eval_data.yaml" \
    --output-dir "$REPO/evaluation-result" \
    --mcp-url "$MCP_URL" \
    --mcp-token "$MCP_TOKEN" \
    "$@"
}

score() {
  local model_dir="$1"
  local data="$REPO/evaluation-result/$model_dir/evaluation_dataset.yaml"
  echo "======== SCORE $model_dir ========"
  "$EVAL_BIN" \
    --system-config "$REPO/config/system-offline-tool-and-judge.yaml" \
    --eval-data "$data" \
    --output-dir "$REPO/evaluation-result/$model_dir"
  # Rename latest summary to stable model name if present
  local latest
  latest="$(ls -t "$REPO/evaluation-result/$model_dir"/evaluation_*_summary.json 2>/dev/null | head -1 || true)"
  if [[ -n "$latest" ]]; then
    local base="${latest%_summary.json}"
    cp "${base}_summary.json" "$REPO/evaluation-result/$model_dir/${model_dir}_summary.json"
    cp "${base}_summary.txt" "$REPO/evaluation-result/$model_dir/${model_dir}_summary.txt"
  fi
}

# Build shared gold if needed
"$PY" "$REPO/scripts/build_gold_dataset.py"

# Agent models (match Lightspeed campaign set)
trace openai gpt-4o-mini gpt-4o-mini --openai-key-file "$HOME/Documents/openai-token.txt"
trace openai gpt-5-mini gpt-5-mini --openai-key-file "$HOME/Documents/openai-token.txt"
trace openai gpt-5.5 gpt-5.5 --openai-key-file "$HOME/Documents/openai-token.txt"
trace vertex gemini-2.5-pro gemini-2.5-pro
trace vertex gemini-2.5-flash-lite gemini-2.5-flash-lite
trace openai_compatible redhataillama-31-8b-instruct llama-31-8b \
  --api-base "$LLAMA_BASE" \
  --api-key-file "$HOME/Documents/vllm-token"

for m in gpt-4o-mini gpt-5-mini gpt-5.5 gemini-2.5-pro gemini-2.5-flash-lite llama-31-8b; do
  score "$m"
done

"$PY" "$REPO/scripts/generate_comparison_graphs.py" "$REPO/evaluation-result"
echo "Campaign complete."
