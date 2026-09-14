"""Runs only in the disposable container. No shell or orchestration tools."""

import asyncio
import json
import os
import sys
from pathlib import Path

from agents import (
    Agent,
    ItemHelpers,
    OpenAIResponsesModel,
    Runner,
    function_tool,
    set_tracing_disabled,
)
from openai import AsyncOpenAI

ROOT = Path("/workspace/skills")
READ = set()


def emit(kind, **fields):
    print(json.dumps({"type": kind, **fields}), flush=True)


@function_tool
async def list_resources() -> str:
    """List the selected skills and their supporting files."""
    paths = sorted(str(p.relative_to(ROOT)) for p in ROOT.rglob("*") if p.is_file())
    emit("planner.resources", paths=paths)
    return "\n".join(paths)


@function_tool
async def read_resource(path: str, offset: int = 0) -> str:
    """Read a UTF-8 selected skill resource, in chunks of 24000 characters."""
    target = (ROOT / path).resolve()
    if not target.is_relative_to(ROOT.resolve()) or not target.is_file() or offset < 0:
        raise ValueError("Resource outside selected skills or invalid offset")
    content = target.read_text(encoding="utf-8")
    if offset == 0:
        READ.add(str(target.relative_to(ROOT)))
    emit(
        "planner.resource_read",
        path=path,
        offset=offset,
        characters=len(content[offset : offset + 24000]),
    )
    return content[offset : offset + 24000]


async def main():
    model, instructions, user_input = sys.argv[1:]
    set_tracing_disabled(True)
    client = AsyncOpenAI(
        api_key=os.environ["CODEX_API_KEY"], base_url="http://127.0.0.1:9000/v1"
    )
    agent = Agent(
        name="Notebook planner",
        instructions=instructions,
        model=OpenAIResponsesModel(model=model, openai_client=client),
        tools=[list_resources, read_resource],
    )
    emit("planner.started", model=model)
    result = Runner.run_streamed(agent, input=user_input, max_turns=40)
    async for event in result.stream_events():
        if event.type == "run_item_stream_event":
            item = event.item
            if item.type == "message_output_item":
                emit(
                    "item.completed",
                    item={
                        "type": "agent_message",
                        "text": ItemHelpers.text_message_output(item),
                    },
                )
            elif item.type in ("tool_call_item", "tool_call_output_item"):
                emit("planner.activity", name=event.name)
    required = {str(p.relative_to(ROOT)) for p in ROOT.glob("*/SKILL.md")}
    if not required <= READ:
        raise ValueError("Planner did not read every selected SKILL.md")
    if not isinstance(result.final_output, str):
        raise ValueError("Missing text output")
    Path("/workspace/plan.md").write_text(result.final_output)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:
        emit("error", message="Planning failed: " + type(error).__name__)
        sys.exit(1)
