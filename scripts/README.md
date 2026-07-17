# Scripts

## `generate_traces.py`

Run an OpenAI tool-calling agent against Backstage MCP and fill `tool_calls`
(and optional `response`) in `dataset/eval_data.yaml`.

### Setup (once)

```bash
python3 -m venv .venv
.venv/bin/pip install -r scripts/requirements.txt
```

### Run

```bash
export MCP_TOKEN=...          # Backstage/RHDH MCP bearer token
# optional: export MCP_URL=http://localhost:7007/api/mcp-actions/v1
# optional: export OPENAI_MODEL=gpt-4o-mini

.venv/bin/python scripts/generate_traces.py \
  --openai-key-file /path/to/openai-key \
  --in-place
```

Without `--in-place`, writes `dataset/eval_data.with-traces.yaml` (gitignored).

Then score with lightspeed-eval:

```bash
export OPENAI_API_KEY=...     # framework boot only for offline tool_eval
REPO="$(pwd)"
cd /path/to/lightspeed-evaluation
uv run lightspeed-eval \
  --system-config "$REPO/config/system-offline-tool-eval.yaml" \
  --eval-data "$REPO/dataset/eval_data.yaml"
```
