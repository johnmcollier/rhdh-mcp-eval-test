#!/usr/bin/env python3
"""Generate MCP tool traces for gold eval_data using OpenAI / Vertex / vLLM agents.

Examples:
  # OpenAI
  ./scripts/generate_traces.py --provider openai --model gpt-4o-mini \\
    --openai-key-file ~/Documents/openai-token.txt \\
    --model-dir gpt-4o-mini

  # Vertex Gemini
  ./scripts/generate_traces.py --provider vertex --model gemini-2.5-flash-lite \\
    --model-dir gemini-2.5-flash-lite

  # OpenAI-compatible vLLM / Llama
  ./scripts/generate_traces.py --provider openai_compatible \\
    --model redhataillama-31-8b-instruct \\
    --api-base https://.../ \\
    --api-key-file ~/Documents/vllm-token \\
    --model-dir llama-31-8b
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from openai import OpenAI

DEFAULT_MCP_URL = "http://localhost:7007/api/mcp-actions/v1"
MAX_TOOL_ROUNDS = 8
CONTEXT_CHARS = 4000
DOT_REPLACEMENT = "__"

SYSTEM_PROMPT = """You are an assistant that must use Backstage MCP tools to answer.
Always call at least one tool when tools can help. Prefer the most specific tool.
Prefer overlay tools (*-mcp-extras.*) over upstream duplicates when both exist.
Do not invent tool names. Use only the tools provided.
Tool names use double underscores where the real MCP name has a dot
(e.g. software-catalog-mcp-extras__query-catalog-entities)."""


def load_yaml(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, list):
        raise SystemExit(f"Expected a YAML list in {path}")
    return data


def dump_yaml(path: Path, data: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            data,
            sort_keys=False,
            default_flow_style=False,
            allow_unicode=True,
        )
    )


def to_openai_name(mcp_name: str) -> str:
    return mcp_name.replace(".", DOT_REPLACEMENT)


def to_mcp_name(openai_name: str) -> str:
    return openai_name.replace(DOT_REPLACEMENT, ".")


def mcp_tools_to_openai(tools: list[Any]) -> list[dict[str, Any]]:
    openai_tools = []
    for tool in tools:
        schema = tool.inputSchema or {"type": "object", "properties": {}}
        openai_tools.append(
            {
                "type": "function",
                "function": {
                    "name": to_openai_name(tool.name),
                    "description": tool.description or "",
                    "parameters": schema,
                },
            }
        )
    return openai_tools


def normalize_args(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {"_raw": raw}
        return parsed if isinstance(parsed, dict) else {"_raw": parsed}
    if isinstance(raw, dict):
        return raw
    return {"_raw": raw}


def to_eval_tool_calls(steps: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    return [
        [{"tool_name": step["tool_name"], "arguments": step["arguments"]}]
        for step in steps
    ]


def content_to_text(result: Any) -> str:
    parts: list[str] = []
    for block in result.content or []:
        text = getattr(block, "text", None)
        if text is not None:
            parts.append(text)
        else:
            parts.append(str(block))
    if parts:
        return "\n".join(parts)
    return json.dumps({"isError": getattr(result, "isError", False)})


def read_secret(path: Path | None, env_names: list[str]) -> str:
    if path is not None:
        key = path.expanduser().read_text().strip()
        if not key:
            raise SystemExit(f"Secret file empty: {path}")
        return key
    for name in env_names:
        val = os.environ.get(name, "").strip()
        if val:
            return val
    raise SystemExit(f"Need secret file or one of env vars: {', '.join(env_names)}")


def build_client(args: argparse.Namespace) -> tuple[OpenAI, str]:
    """Return (client, model_id_for_api)."""
    if args.provider == "openai":
        api_key = read_secret(args.openai_key_file, ["OPENAI_API_KEY"])
        return OpenAI(api_key=api_key), args.model

    if args.provider == "openai_compatible":
        api_key = read_secret(args.api_key_file, ["OPENAI_API_KEY", "VLLM_API_KEY"])
        base = args.api_base or os.environ.get("OPENAI_API_BASE")
        if not base:
            raise SystemExit("--api-base or OPENAI_API_BASE required for openai_compatible")
        return OpenAI(api_key=api_key, base_url=base.rstrip("/") + "/v1"), args.model

    if args.provider == "vertex":
        # LiteLLM OpenAI-compatible shim via google-genai is awkward; use openai
        # client against Vertex OpenAI endpoint is not universal. Use litellm
        # through a thin wrapper via OpenAI-compatible vertex publishing if set,
        # else call via litellm.completion in the agent loop.
        raise SystemExit("vertex provider uses litellm path; handled in run_agent_turn")

    raise SystemExit(f"Unknown provider: {args.provider}")


def completion_kwargs(
    model: str,
    messages: list[dict[str, Any]],
    openai_tools: list[dict[str, Any]],
    *,
    temperature: float | None,
    parallel_tool_calls: bool | None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "tools": openai_tools,
        "tool_choice": "auto",
    }
    # gpt-5* rejects temperature=0 (only default 1)
    if temperature is not None and not model.startswith("gpt-5"):
        kwargs["temperature"] = temperature
    if parallel_tool_calls is not None:
        kwargs["parallel_tool_calls"] = parallel_tool_calls
    return kwargs


async def run_agent_turn_openai(
    client: OpenAI,
    session: ClientSession,
    openai_tools: list[dict[str, Any]],
    query: str,
    model: str,
    *,
    temperature: float | None = 0,
    parallel_tool_calls: bool | None = None,
) -> tuple[list[dict[str, Any]], str, list[str]]:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": query},
    ]
    trace: list[dict[str, Any]] = []
    contexts: list[str] = []

    for _ in range(MAX_TOOL_ROUNDS):
        response = await asyncio.to_thread(
            client.chat.completions.create,
            **completion_kwargs(
                model,
                messages,
                openai_tools,
                temperature=temperature,
                parallel_tool_calls=parallel_tool_calls,
            ),
        )
        msg = response.choices[0].message
        assistant_msg: dict[str, Any] = {"role": "assistant", "content": msg.content}
        if msg.tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments or "{}",
                    },
                }
                for tc in msg.tool_calls
            ]
        messages.append(assistant_msg)

        if not msg.tool_calls:
            return trace, (msg.content or ""), contexts

        # Some endpoints (Llama/vLLM) only allow a single tool call per turn.
        tool_calls = list(msg.tool_calls)
        if parallel_tool_calls is False and len(tool_calls) > 1:
            tool_calls = tool_calls[:1]
            messages[-1]["tool_calls"] = [
                {
                    "id": tool_calls[0].id,
                    "type": "function",
                    "function": {
                        "name": tool_calls[0].function.name,
                        "arguments": tool_calls[0].function.arguments or "{}",
                    },
                }
            ]

        for tc in tool_calls:
            mcp_name = to_mcp_name(tc.function.name)
            args = normalize_args(tc.function.arguments)
            try:
                result = await session.call_tool(mcp_name, args)
                output = content_to_text(result)
            except Exception as exc:  # noqa: BLE001
                output = f"ERROR calling {mcp_name}: {exc}"
            trace.append({"tool_name": mcp_name, "arguments": args})
            contexts.append(output[:CONTEXT_CHARS])
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": output[:8000],
                }
            )

    return trace, "", contexts


async def run_agent_turn_litellm_vertex(
    session: ClientSession,
    openai_tools: list[dict[str, Any]],
    query: str,
    model: str,
) -> tuple[list[dict[str, Any]], str, list[str]]:
    import litellm

    litellm.drop_params = True
    model_name = model if model.startswith("vertex_ai/") else f"vertex_ai/{model}"
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": query},
    ]
    # Convert OpenAI tools to litellm tools format (same shape)
    trace: list[dict[str, Any]] = []
    contexts: list[str] = []

    for _ in range(MAX_TOOL_ROUNDS):
        response = await asyncio.to_thread(
            litellm.completion,
            model=model_name,
            messages=messages,
            tools=openai_tools,
            tool_choice="auto",
            temperature=0,
        )
        msg = response.choices[0].message
        content = msg.get("content") if isinstance(msg, dict) else msg.content
        tool_calls = msg.get("tool_calls") if isinstance(msg, dict) else msg.tool_calls

        assistant_msg: dict[str, Any] = {"role": "assistant", "content": content}
        if tool_calls:
            serialized = []
            for tc in tool_calls:
                if isinstance(tc, dict):
                    serialized.append(tc)
                else:
                    serialized.append(
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments or "{}",
                            },
                        }
                    )
            assistant_msg["tool_calls"] = serialized
        messages.append(assistant_msg)

        if not tool_calls:
            return trace, (content or ""), contexts

        for tc in tool_calls:
            if isinstance(tc, dict):
                tc_id = tc["id"]
                fn = tc["function"]
                openai_name = fn["name"]
                raw_args = fn.get("arguments") or "{}"
            else:
                tc_id = tc.id
                openai_name = tc.function.name
                raw_args = tc.function.arguments or "{}"
            mcp_name = to_mcp_name(openai_name)
            args = normalize_args(raw_args)
            try:
                result = await session.call_tool(mcp_name, args)
                output = content_to_text(result)
            except Exception as exc:  # noqa: BLE001
                output = f"ERROR calling {mcp_name}: {exc}"
            trace.append({"tool_name": mcp_name, "arguments": args})
            contexts.append(output[:CONTEXT_CHARS])
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": output[:8000],
                }
            )

    return trace, "", contexts


def strip_runtime_fields(conversations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep gold fields; drop prior traces."""
    cleaned = []
    for conv in conversations:
        c = {
            "conversation_group_id": conv["conversation_group_id"],
            "description": conv.get("description"),
            "tag": conv.get("tag"),
            "turns": [],
        }
        for turn in conv.get("turns") or []:
            t = {
                "turn_id": turn["turn_id"],
                "query": turn["query"],
                "expected_tool_calls": turn.get("expected_tool_calls"),
            }
            if turn.get("expected_response") is not None:
                t["expected_response"] = turn["expected_response"]
            if turn.get("expected_intent") is not None:
                t["expected_intent"] = turn["expected_intent"]
            c["turns"].append(t)
        cleaned.append(c)
    return cleaned


async def generate(args: argparse.Namespace) -> None:
    conversations = strip_runtime_fields(load_yaml(args.eval_data))
    headers = {"Authorization": f"Bearer {args.mcp_token}"}

    client: OpenAI | None = None
    if args.provider in ("openai", "openai_compatible"):
        client, model = build_client(args)
    else:
        model = args.model
        # Ensure Vertex env
        if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
            default_adc = Path.home() / ".config/gcloud/application_default_credentials.json"
            if default_adc.exists():
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(default_adc)
        os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "rhdh-ai")
        os.environ.setdefault("VERTEXAI_PROJECT", "rhdh-ai")
        os.environ.setdefault("VERTEXAI_LOCATION", "us-central1")

    async with streamablehttp_client(args.mcp_url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            tools = list(listed.tools)
            if not tools:
                raise SystemExit(f"No tools listed from {args.mcp_url}")
            print(f"Loaded {len(tools)} MCP tools from {args.mcp_url}")
            openai_tools = mcp_tools_to_openai(tools)

            for conv in conversations:
                cid = conv.get("conversation_group_id", "?")
                for turn in conv.get("turns") or []:
                    tid = turn.get("turn_id", "?")
                    query = turn.get("query")
                    if not query:
                        print(f"  skip {cid}/{tid}: no query")
                        continue
                    print(f"  run {cid}/{tid}: {query[:80]!r}")
                    try:
                        if args.provider == "vertex":
                            steps, answer, contexts = await run_agent_turn_litellm_vertex(
                                session, openai_tools, query, model
                            )
                        else:
                            assert client is not None
                            parallel = (
                                False if args.provider == "openai_compatible" else None
                            )
                            steps, answer, contexts = await run_agent_turn_openai(
                                client,
                                session,
                                openai_tools,
                                query,
                                model,
                                temperature=0,
                                parallel_tool_calls=parallel,
                            )
                    except Exception as exc:  # noqa: BLE001
                        print(f"    !! turn failed: {exc}")
                        turn["tool_calls"] = []
                        turn["response"] = f"ERROR generating turn: {exc}"
                        turn["contexts"] = []
                        continue
                    turn["tool_calls"] = to_eval_tool_calls(steps)
                    if contexts:
                        turn["contexts"] = contexts
                    if answer:
                        turn["response"] = answer
                    names = [s["tool_name"] for s in steps]
                    print(f"    -> {names or ['(no tools)']}")

    digest = hashlib.sha256(
        yaml.safe_dump(conversations, sort_keys=True).encode()
    ).hexdigest()[:8]
    model_dir = args.model_dir or args.model.replace("/", "-").replace(":", "-")
    out_dir = args.output_dir / model_dir
    out_path = out_dir / f"evaluation_dataset_{digest}.yaml"
    dump_yaml(out_path, conversations)
    # Also write a stable latest pointer name for scoring scripts
    latest = out_dir / "evaluation_dataset.yaml"
    dump_yaml(latest, conversations)
    print(f"Wrote {out_path}")
    print(f"Wrote {latest}")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--eval-data",
        type=Path,
        default=repo_root / "dataset" / "eval_data.yaml",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repo_root / "evaluation-result",
        help="Parent directory for per-model folders",
    )
    parser.add_argument(
        "--model-dir",
        default=None,
        help="Folder name under output-dir (e.g. gpt-4o-mini, llama-31-8b)",
    )
    parser.add_argument("--mcp-url", default=os.environ.get("MCP_URL", DEFAULT_MCP_URL))
    parser.add_argument("--mcp-token", default=os.environ.get("MCP_TOKEN"))
    parser.add_argument(
        "--provider",
        choices=["openai", "vertex", "openai_compatible"],
        required=True,
    )
    parser.add_argument("--model", required=True, help="Model id for the provider")
    parser.add_argument("--openai-key-file", type=Path, default=None)
    parser.add_argument("--api-key-file", type=Path, default=None)
    parser.add_argument("--api-base", default=None)
    args = parser.parse_args()

    if not args.mcp_token:
        raise SystemExit("MCP_TOKEN env var or --mcp-token is required")

    asyncio.run(generate(args))


if __name__ == "__main__":
    main()
