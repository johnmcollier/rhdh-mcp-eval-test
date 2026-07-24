# RHDH MCP Evaluation

Campaign artifacts for evaluating Red Hat Developer Hub / Backstage MCP tools
from [`rhdh-plugins/workspaces/mcp-integrations`](https://github.com/redhat-developer/rhdh-plugins/tree/main/workspaces/mcp-integrations).

**Canonical repo:** https://github.com/redhat-ai-dev/rhdh-mcp-eval

Packaging follows
[developer-lightspeed-evaluation](https://github.com/redhat-ai-dev/developer-lightspeed-evaluation):
shared gold dataset, per-model traces + scores, comparison graphs.
Scoring uses [lightspeed-evaluation](https://github.com/lightspeed-core/lightspeed-evaluation)
(`lightspeed-eval` CLI). This is not the Lightspeed RAG / `lsdataset` pipeline.

## Layout

| Path | Purpose |
| --- | --- |
| `categories.yaml` | Task category definitions |
| `dataset/eval_data.yaml` | Shared gold (queries, expected tool calls / responses) |
| `config/system-offline-tool-and-judge.yaml` | Offline tool_eval + judge panel |
| `evaluation-result/<model>/` | Per-model dataset + scores + graphs |
| `evaluation-result/*.png` | Cross-model comparison graphs |
| `scripts/` | Gold builder, multi-provider trace gen, campaign runner |

## Fixture assumptions

Local `mcp-integrations` demo catalog:

- Owners such as `payments-team`, `security-team`, `accounts-team`
- Entities such as `consent-management-api`, payment APIs
- **Template kind count is 0** → `execute-template` not scored; write coverage uses dry-run validate
- TechDocs indexing may be empty; retrieve-content is optional when fetch returns none

Prefer overlay tools (`*-mcp-extras.*`) over upstream duplicates.

## Prerequisites

1. Backstage/RHDH MCP on the backend: `http://localhost:7007/api/mcp-actions/v1`
2. `MCP_TOKEN` matching static MCP external access
3. OpenAI API key (agent models + `gpt-4o-mini` judge)
4. Vertex ADC for Gemini agents/judges (`GOOGLE_APPLICATION_CREDENTIALS`, project `rhdh-ai`)
5. Llama OpenAI-compatible endpoint + token (see campaign script defaults)
6. Clone of `lightspeed-evaluation` with `uv sync`

Credentials stay in the environment or gitignored local files.

## Full campaign (RHIDP-14578)

Agent models under test (aligned with Developer Lightspeed 1.10):

- `gpt-4o-mini`, `gpt-5-mini`, `gpt-5.5`
- `gemini-2.5-pro`, `gemini-2.5-flash-lite`
- `llama-31-8b` (`redhataillama-31-8b-instruct` via OpenShift vLLM/3scale)

Metrics:

| Metric | Role |
| --- | --- |
| `custom:tool_eval` | Tool selection / arguments |
| `custom:answer_correctness` | Response vs expected_response (judge panel) |
| `ragas:faithfulness` | Response vs MCP tool contexts (judge panel) |

Judge panel: `vertex_ai/gemini-2.5-pro` + `openai/gpt-4o-mini` (aggregation: max).

```bash
python3 -m venv .venv && .venv/bin/pip install -r scripts/requirements.txt

export MCP_TOKEN=...
# OpenAI / Vertex / Llama secrets as used by scripts/run_campaign.sh

chmod +x scripts/run_campaign.sh
./scripts/run_campaign.sh
```

Or step by step:

```bash
.venv/bin/python scripts/build_gold_dataset.py

.venv/bin/python scripts/generate_traces.py \
  --provider openai --model gpt-4o-mini --model-dir gpt-4o-mini \
  --openai-key-file "$HOME/Documents/openai-token.txt"

# ... repeat for other models (see scripts/run_campaign.sh)

cd /path/to/lightspeed-evaluation
uv run lightspeed-eval \
  --system-config "$REPO/config/system-offline-tool-and-judge.yaml" \
  --eval-data "$REPO/evaluation-result/gpt-4o-mini/evaluation_dataset.yaml" \
  --output-dir "$REPO/evaluation-result/gpt-4o-mini"

.venv/bin/python scripts/generate_comparison_graphs.py "$REPO/evaluation-result"
```

## Related

- Tools under test: `rhdh-plugins/workspaces/mcp-integrations`
- Runner: https://github.com/lightspeed-core/lightspeed-evaluation
- Pattern reference: https://github.com/redhat-ai-dev/developer-lightspeed-evaluation
- Jira: RHIDP-14578 (evals); RHIDP-14577 (feasibility)
