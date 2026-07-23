# Scripts

## `generate_traces.py`

Runs an OpenAI tool-calling agent against Backstage MCP and writes `tool_calls`
into an eval YAML (default: `dataset/eval_data.with-traces.yaml`).

```bash
python3 -m venv .venv
.venv/bin/pip install -r scripts/requirements.txt

export MCP_TOKEN=...
export MCP_URL=http://localhost:7007/api/mcp-actions/v1

.venv/bin/python scripts/generate_traces.py \
  --openai-key-file "$HOME/path/to/openai-key" \
  --no-response
```

Use `--in-place` to overwrite `dataset/eval_data.yaml`, or `--output` for a separate file.
Without `--in-place`, the default output is gitignored.

Score with `lightspeed-eval` and `config/system-offline-tool-eval.yaml` (see root README).
