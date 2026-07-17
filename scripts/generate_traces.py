#!/usr/bin/env python3
"""Generate tool_calls traces for MCP eval_data.yaml using OpenAI + Backstage MCP.

Example:
  export MCP_TOKEN=...   # Backstage/RHDH MCP bearer token

  ./scripts/generate_traces.py \\
    --eval-data dataset/eval_data.yaml \\
    --mcp-url http://localhost:7007/api/mcp-actions/v1 \\
    --openai-key-file /path/to/openai-key \\
    --in-place
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import yaml
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from openai import OpenAI

DEFAULT_MCP_URL = "http://localhost:7007/api/mcp-actions/v1"
DEFAULT_MODEL = "gpt-4o-mini"
MAX_TOOL_ROUNDS = 8

# OpenAI function names must match ^[a-zA-Z0-9_-]+$
# Backstage MCP tools use dots: software-catalog-mcp-extras.query-catalog-entities
DOT_REPLACEMENT = "__"

SYSTEM_PROMPT = """You are an assistant that must use Backstage MCP tools to answer.
Always call at least one tool when tools can help. Prefer the most specific tool.
Do not invent tool names. Use only the tools provided.
Tool names use double underscores where the real MCP name has a dot
(e.g. software-catalog-mcp-extras__query-catalog-entities)."""


def load_yaml(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, list):
        raise SystemExit(f"Expected a YAML list in {path}")
    return data


def dump_yaml(path: Path, data: list[dict[str, Any]]) -> None:
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
    """lightspeed-eval format: list of steps; each step is a list of parallel calls."""
    return [
        [{"tool_name": step["tool_name"], "arguments": step["arguments"]}]
        for step in steps
    ]


def resolve_openai_key(key_file: Path | None) -> str:
    if key_file is not None:
        key = key_file.expanduser().read_text().strip()
        if not key:
            raise SystemExit(f"OpenAI key file is empty: {key_file}")
        return key
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise SystemExit(
            "OPENAI_API_KEY is required, or pass --openai-key-file"
        )
    return key


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


async def run_agent_turn(
    openai_client: OpenAI,
    session: ClientSession,
    openai_tools: list[dict[str, Any]],
    query: str,
    model: str,
) -> tuple[list[dict[str, Any]], str]:
    """Returns (trace steps with real MCP tool names, final assistant text)."""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": query},
    ]
    trace: list[dict[str, Any]] = []

    for _ in range(MAX_TOOL_ROUNDS):
        response = await asyncio.to_thread(
            openai_client.chat.completions.create,
            model=model,
            messages=messages,
            tools=openai_tools,
            tool_choice="auto",
            temperature=0,
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
            return trace, (msg.content or "")

        for tc in msg.tool_calls:
            openai_name = tc.function.name
            mcp_name = to_mcp_name(openai_name)
            args = normalize_args(tc.function.arguments)
            try:
                result = await session.call_tool(mcp_name, args)
                output = content_to_text(result)
            except Exception as exc:  # noqa: BLE001 - record and continue
                output = f"ERROR calling {mcp_name}: {exc}"
            trace.append(
                {
                    "tool_name": mcp_name,
                    "arguments": args,
                    "result": output[:2000],
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": output[:8000],
                }
            )

    return trace, ""


async def generate(
    eval_path: Path,
    output_path: Path,
    mcp_url: str,
    mcp_token: str,
    model: str,
    openai_key_file: Path | None,
    store_response: bool = True,
) -> None:
    conversations = load_yaml(eval_path)
    openai_client = OpenAI(api_key=resolve_openai_key(openai_key_file))
    headers = {"Authorization": f"Bearer {mcp_token}"}

    async with streamablehttp_client(mcp_url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            tools = list(listed.tools)
            if not tools:
                raise SystemExit(f"No tools listed from {mcp_url}")
            print(f"Loaded {len(tools)} MCP tools from {mcp_url}")
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
                    steps, answer = await run_agent_turn(
                        openai_client, session, openai_tools, query, model
                    )
                    turn["tool_calls"] = to_eval_tool_calls(steps)
                    if store_response and answer:
                        turn["response"] = answer
                    elif "response" in turn:
                        del turn["response"]
                    names = [s["tool_name"] for s in steps]
                    print(f"    -> {names or ['(no tools)']}")

    dump_yaml(output_path, conversations)
    print(f"Wrote {output_path}")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--eval-data",
        type=Path,
        default=repo_root / "dataset" / "eval_data.yaml",
        help="Input eval_data.yaml",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path (default: <eval-data>.with-traces.yaml)",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Overwrite --eval-data",
    )
    parser.add_argument(
        "--mcp-url",
        default=os.environ.get("MCP_URL", DEFAULT_MCP_URL),
    )
    parser.add_argument(
        "--mcp-token",
        default=os.environ.get("MCP_TOKEN"),
        help="Bearer token (or set MCP_TOKEN)",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("OPENAI_MODEL", DEFAULT_MODEL),
    )
    parser.add_argument(
        "--openai-key-file",
        type=Path,
        default=None,
        help="Read OpenAI API key from a file (avoids exporting OPENAI_API_KEY)",
    )
    parser.add_argument(
        "--no-response",
        action="store_true",
        help="Do not store the final assistant response (keeps the YAML smaller)",
    )
    args = parser.parse_args()

    if not args.mcp_token:
        raise SystemExit("MCP_TOKEN env var or --mcp-token is required")

    if args.in_place:
        output = args.eval_data
    elif args.output:
        output = args.output
    else:
        output = args.eval_data.with_name(
            args.eval_data.stem + ".with-traces.yaml"
        )

    asyncio.run(
        generate(
            eval_path=args.eval_data,
            output_path=output,
            mcp_url=args.mcp_url,
            mcp_token=args.mcp_token,
            model=args.model,
            openai_key_file=args.openai_key_file,
            store_response=not args.no_response,
        )
    )


if __name__ == "__main__":
    main()
